"""
Simple HTTP file server.

TBD
code looks funky, and needs to be refactored asap
"""
import http.server
import socketserver
import cgi
import os
import time
import urllib
import html
import io
import base64
import zipfile
import shutil
import socket
import functools
import json
import ssl

from dotenv import load_dotenv

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv()
USERNAME = os.getenv("HTTP_USER")
PASSWORD = os.getenv("HTTP_PASS")
DEFAULT_CERT = os.path.join(THIS_DIR, "server.crt")
DEFAULT_KEY = os.path.join(THIS_DIR, "server.key")
CERT_FILE = os.path.join(THIS_DIR, os.getenv("SSL_CERT", DEFAULT_CERT))
CERT_KEY = os.path.join(THIS_DIR, os.getenv("SSL_KEY", DEFAULT_KEY))
CREDENTIALS = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()

IPV4_ADDRESS = os.getenv("IP_ADDR")
PORT = 9999 # baka baka
# target folder for uploads
# change this to whatever path you like, for example:
# DIRECTORY = "C:\Users\User\Desktop\"
# set it to "." to use current working directory instead (this folder)
DIRECTORY = os.getenv("FOLDER")
# DIRECTORY = "."
if DIRECTORY and os.path.isdir(DIRECTORY):
	os.chdir(DIRECTORY)
else:
	print(f"Warning: DIRECTORY {DIRECTORY} is not set or does not exist. Using current working directory.")
SERVER_DIRECTORY_IP_AND_PORT = f"{IPV4_ADDRESS}:{PORT}/"

"""
to-do
- visually remove this file in root (NOT DELETE) or make undeletable instead, idk
- checkbox and zip for multi-download with the name of the directory
- ui looks like crap on desktop
- show the list of the files to be uploaded instead of being crammed like that
- make each dir clickable on the root/path/path/... etc
- how to automatically get valid ipv4 address from ipconfig

done/implemented
- add a password
- move the up one level and root buttons closer to the table
- add a file and directory count, and total items indicator somewhere
- uploading a file to folders other than the root is broken
- show "nothing to see here" inside empty directories when opened
- any file named exactly "index.html" can't be opened, unintended redirect loop
- download a directory but compress it first
"""

# change class name because that's not what it even does and i don't know why you stuck with that
class UploadHandler(http.server.SimpleHTTPRequestHandler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.wfile = self.wfile
		try:
			self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		except Exception:
			pass


	def do_AUTHHEAD(self):
		self.send_response(401)
		self.send_header("WWW-Authenticate", 'Basic realm="File repository"')
		self.send_header("Content-type", "text/html")
		self.end_headers()


	def do_POST(self):
		if not self.require_auth():
			return None

		# get the actual directory path from request
		dir_path = self.translate_path(urllib.parse.unquote(self.path))
		if not dir_path or not os.path.isdir(dir_path):
			dir_path = "."  # fallback to current working directory if invalid

		form = cgi.FieldStorage(
			fp=self.rfile,
			headers=self.headers,
			environ={"REQUEST_METHOD":"POST"}
		)

		if "file" in form:
			file_item = form["file"]
			if file_item.filename and file_item.file:
				filename = os.path.basename(file_item.filename.strip())
				if filename:
					filepath = os.path.join(dir_path, filename)
					os.makedirs(os.path.dirname(filepath), exist_ok=True)
					with open(filepath, "wb") as f:
						f.write(file_item.file.read())

					self.send_response(303)
					self.send_header("Location", self.path)
					self.end_headers()
					return

		self.send_response(400)
		self.end_headers()
		self.wfile.write(b"No valid file selected")


	def do_GET(self):
		if not self.require_auth():
			return None

		# normalize abnd decode path
		parsed = urllib.parse.urlsplit(self.path)
		path_unquoted = urllib.parse.unquote(parsed.path)
		query_params = urllib.parse.parse_qs(parsed.query)
		# basename = os.path.basename(path_unquoted.rstrip("/")).lower()

		#  check sse first before directory download
		if query_params.get("sse") and os.path.isdir(self.translate_path(path_unquoted.rstrip("/"))):
			self.do_SSE(path_unquoted.rstrip("/"))
			return None

		# check for dir dl request
		# clean_path = path_unquoted.rstrip("/")
		if query_params.get("download") and os.path.isdir(self.translate_path(path_unquoted.rstrip("/"))):
			return self.serve_directory_zip(path_unquoted.rstrip("/"))

		# load index.html
		""" if basename == "index.html" and os.path.isfile(self.translate_path(self.path)):
			pass """

		# only force plain-text for ACTUAL text documents
		# "LICENSE" and "LICENCE" are for the license files commonly found in git repositories
		text_ext = (
			".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".env", ".lrc",
			"LICENSE", "LICENCE"
		)

		if self.path.endswith(text_ext):
			try:
				localpath = self.translate_path(self.path)
				if os.path.isfile(localpath):
					with open(localpath, "r", encoding="utf-8") as f:
						content = f.read()

					self.send_response(200)
					self.send_header(
						"Content-type", "text/plain; charset=utf-8")
					self.end_headers()
					self.wfile.write(content.encode("utf-8"))
					return

			except Exception:
				pass

		result = self.send_head()
		if result:
			# (file, size) - individual file
			if isinstance(result, tuple):
				f, total_size = result
				try:
					# shutil.copyfileobj(f, self.wfile)
					# microsoft edge case (pun?)
					self.connection.sendall(f.read())
					self.wfile.flush()
				finally:
					f.close()
			# directory listing
			else:
				try:
					shutil.copyfileobj(result, self.wfile)
				finally:
					try:
						result.close()
					except:
						pass
			return

		# fallback
		path = self.translate_path(self.path)
		if os.path.isdir(path):
			return self.list_directory(path)
		self.send_error(404, "File not found")


	def do_SSE(self, dir_path):
		if not self.require_auth():
			self.do_AUTHHEAD()
			return None

		path = self.translate_path(dir_path)
		if not os.path.isdir(path):
			self.send_error(404, "Directory not found")
			return None

		# sse headers first
		self.send_response(200)
		self.send_header("Content-Type", "text/event-stream")
		self.send_header("Cache-Control", "no-cache")
		self.send_header("Connection", "keep-alive")
		self.send_header("Access-Control-Allow-Origin", "*")
		self.end_headers()

		# precalculate total things
		total_size = 0
		total_files = 0
		for root, _, files in os.walk(path):
			for f in files:
				try:
					total_size += os.path.getsize(os.path.join(root, f))
					total_files += 1
				except:
					pass

		processed_bytes = 0
		file_count = 0
		cancelled = False


		def send_progress():
			nonlocal processed_bytes, file_count
			progress_data = {
				"processed_bytes":	processed_bytes,
				"total_size":		total_size,
				"file_count":		file_count,
				"total_files":		total_files,
				"percent":		min(100, (processed_bytes / total_size * 100)
									if total_size > 0 else 0)
			}
			self.wfile.write(
				f"data: {json.dumps(progress_data)}\n\n".encode("utf-8"))
			self.wfile.flush()
		
		# check if client dced
		def client_disconnected():
			try:
				self.wfile.write(b"")
				self.wfile.flush()
				return False
			except (BrokenPipeError, ConnectionResetError, OSError):
				return True

		send_progress()	# initial
		
		try:
			zip_buffer = io.BytesIO()
			with zipfile.ZipFile(
				zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6
			) as zf:
				# i know `dirs` isn't used, i just put it there for clarity
				for root, dirs, files in os.walk(path):
					if client_disconnected():
						cancelled = True
						break
					for file in files:
						if client_disconnected():
							cancelled = True
							break
						
						try:
							full_path = os.path.join(root, file)
							file_size = os.path.getsize(full_path)
							rel_path = os.path.relpath(
								full_path, os.path.dirname(path)
								).replace("\\", "/")

							zf.write(full_path, arcname=rel_path)
							processed_bytes += file_size
							file_count += 1

							if file_count % 3 == 0:
								send_progress()

						except Exception:
							continue
					if cancelled:
						break

			if cancelled:
				self.wfile.write(
					b"data: {\"cancelled\": true, \"message\": "
					b"\"Zipping cancelled by user\"}\n\n"
				)
			elif client_disconnected():
				return	# client gone, no need to send more
			else:
				send_progress()
				self.wfile.write(
					f"data: {{\"complete\": true, \"size\": "
					f"{len(zip_buffer.getvalue())}}}\n\n".encode("utf-8")
				)
			self.wfile.flush()
		except GeneratorExit:
			cancelled = True
			self.wfile.write(
				b'data: {"cancelled": true, "message": "Connection closed"}\n\n')
			self.wfile.flush()
		except Exception as e:
			self.wfile.write(f'data: {{"error": true, "message": "{str(e)}"}}\n\n'.encode('utf-8'))
			self.wfile.flush()


	""" def translate_path(self, path):
		path = super().translate_path(path)
		if os.path.commonpath((self.SERVE_ROOT, path)) != self.SERVE_ROOT:
			raise OSError("path outside serve root")
		return path """


	def list_directory(self, path):
		"""Inject custom HTML to directory path."""
		if not self.require_auth():
			return None

		f = io.BytesIO()
		displaypath = html.escape(urllib.parse.unquote(self.path))

		try:
			listdir = os.listdir(path)

			num_files = sum(1 for item in listdir if os.path.isfile(os.path.join(path, item)))
			num_dirs = sum(1 for item in listdir if os.path.isdir(os.path.join(path, item)))
			total_items = len(listdir)
			total_size_bytes = sum(os.path.getsize(os.path.join(path, item)) for item in listdir if os.path.isfile(os.path.join(path, item)))
		except OSError:
			self.send_error(404, "No permission to list directory")
			return None

		listdir.sort(
			key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))

		# why the hell would you write html, css, and js on a python file?
		# move these to a separate html file?
		# 2025/12/05 - don't
		f.write(b"""
		<!DOCTYPE html>
		<html>
			<head>
				<meta charset="utf-8">
				<meta name="viewport" content="width=device-width, initial-scale=1.0">
				<link rel="icon" type="image/x-icon" href="https://img.icons8.com/?size=100&id=kktvCbkDLbNb&format=png&color=000000">
				<title>files on https://""" + SERVER_DIRECTORY_IP_AND_PORT.encode() + """</title>
				<style>
					body {
						font-family: monospace;
						font-size: 12px;
						max-width: 600px;
						margin: auto;
						padding: 20px;
					}
					input[type=file], input[type=submit] {
						font-size: 18px;
						padding: 10px;
						width: 50%;
						margin: 10px 0;
					}
					#fileTable {
						width: 100%;
						border-collapse: collapse;
					}
					th {
						padding: 10px;
						border: 1px solid black;
						cursor: pointer;
						background:#f0f0f0;
					}
					td {
						border:1px solid black;
						padding:8px;
						vertical-align: top;
					}
					.scrollable-cell {
						max-width: 250px;
						overflow-x: auto;
						white-space: nowrap;
					}
				</style>
				<script>
					function toggleUpload() {
						const fileInput = document.getElementById("fileInput");
						const uploadBtn = document.getElementById("uploadBtn");
						uploadBtn.disabled = fileInput.files.length === 0;
						uploadBtn.textContent = fileInput.files.length > 0 ? 
							`Upload ${fileInput.files.length} file(s)` :
							"Upload files";
					}

					let currentEventSource = null;
					let currentAbortController = null;

					function startDirDownload(dirLink) {
						const dirName = dirLink.title?.replace("Download ", "")
							|| dirLink.textContent.trim().replace("⬇️", "").trim();
						const ssePath = dirLink.href.replace("?download=1", "")
							+ "?sse=1";
						const downloadPath = dirLink.href;
						
						const container = document.getElementById('download-status');
						currentAbortController = new AbortController();
						
						container.innerHTML = `
							<div style="display:flex;align-items:center;gap:10px;">
								<span>⏳ Zipping "${dirName}"...</span>
								<div style="flex:1;">
									<div id="progress-bar" style="width:100%;height:20px;background:#e0e0e0;border-radius:10px;overflow:hidden;">
										<div id="progress-fill" style="height:100%;background:#007cba;width:0%;transition:width 0.3s;"></div>
									</div>
									<div id="progress-text" style="font-size:11px;margin-top:4px;color:#666;">0%</div>
								</div>
								<button id="cancel-btn" style="padding:8px 12px;background:#dc3545;color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;">❌ Cancel</button>
							</div>
						`;
						container.style.display = 'block';
						
						// Cancel button handler
						document.getElementById('cancel-btn').onclick = function() {
							if (currentEventSource) currentEventSource.close();
							if (currentAbortController) currentAbortController.abort();
							container.innerHTML = `❌ "${dirName}" zipping cancelled`;
							setTimeout(() => container.style.display = 'none', 2000);
						};
						
						if (currentEventSource) currentEventSource.close();
						const eventSource = new EventSource(ssePath, { signal: currentAbortController.signal });
						currentEventSource = eventSource;
						
						eventSource.onmessage = function(event) {
							try {
								const data = JSON.parse(event.data);
								if (data.complete) {
									container.innerHTML = `✅ "${dirName}.zip" ready (${formatBytes(data.size)})`;
									document.getElementById('cancel-btn')?.remove();
									setTimeout(() => {
										window.location.href = downloadPath;
										container.style.display = 'none';
									}, 800);
									eventSource.close();
									return;
								}
								if (data.error || data.cancelled) {
									container.innerHTML = `❌ ${data.message || 'Zipping cancelled'}`;
									setTimeout(() => container.style.display = 'none', 3000);
									eventSource.close();
									return;
								}
								
								const percent = Math.round(data.percent);
								document.getElementById('progress-fill').style.width = percent + '%';
								document.getElementById('progress-text').textContent = 
									`${percent}% (${formatBytes(data.processed_bytes)} / ${formatBytes(data.total_size)})`;
							} catch(e) {}
						};
						
						eventSource.onerror = function() {
							container.innerHTML = `❌ Connection failed for "${dirName}"`;
							setTimeout(() => container.style.display = 'none', 3000);
							eventSource.close();
						};
					}

					function formatBytes(bytes) {
						if (!bytes) return '0 B';
						const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
						const i = Math.floor(Math.log(bytes) / Math.log(k));
						return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
					}

					// Existing file download + directory tracking (unchanged)
					document.addEventListener('click', function(e) {
						const downloadLink = e.target.closest('a[href]');
						if (downloadLink && downloadLink.href.includes('?download=1')) {
							e.preventDefault();
							startDirDownload(downloadLink);
						} else if (downloadLink && (downloadLink.getAttribute('download') || downloadLink.textContent.includes('⬇️'))) {
							const filename = downloadLink.title?.replace('Download ', '') || 'file';
							const container = document.getElementById('download-status');
							container.innerHTML = `⏳ Downloading "${filename}"...`;
							container.style.display = 'block';
							setTimeout(() => container.style.display = 'none', 25000);
						}
					}, true);
				</script>
			</head>
			<body>
				<form method="post" enctype="multipart/form-data" action=".">
					<input type="file" id="fileInput" name="file" multiple onchange="toggleUpload()">
					<input type="submit" id="uploadBtn" value="Upload files" disabled>
				</form>
		""".encode("utf-8"))

		f.write(f"<h3>📁 root{displaypath}</h3>".encode())

		if self.path == "/" or self.path.strip("/") == "":
			pass
		else:
			# remove trailing slash and split by "/"
			parts = [p for p in self.path.strip("/").split("/") if p]
			#remove last segment to go up one level
			if parts:
				parts.pop()
			# rebuild path or root
			parent_http = "/" + "/".join(parts) + "/"
			if parent_http == "//":
				parent_http = "/"

			f.write(f"""
				<div style="margin-bottom: 20px;">
					<a href="{parent_http}" style="display:inline-block;padding:10px 15px;background:#ddd;margin-right:10px;text-decoration:none;border-radius:4px;">up one level</a>
					<a href="/" style="display:inline-block;padding:10px 15px;background:#007cba;color:white;text-decoration:none;border-radius:4px;">go to root</a>
				</div>""".encode("utf-8")
			)

		f.write(b"""
		<div id="download-status" style="margin:20px 0;display:none;padding:12px;background:#e8f4fd;border:1px solid #007cba;border-radius:6px;font-weight:bold;"></div>
		""")

		directory_info = f"""
			<ul>
				<li>Directories: <b>{num_dirs}</b></li>
				<li>Files: <b>{num_files}</b></li>
				<li>Total items: <b>{total_items}</b></li>
				<li>Total size: <b>{self.format_size(total_size_bytes)} ({total_size_bytes:,} bytes)</b></li>
			</ul>""".encode()

		f.write(directory_info + b"""
			<div><i>refresh the page if changes do not reflect across devices</i></div>
			<table id="fileTable">
				<thead>
					<tr>
						<th onclick="sortTable(0)">Name</th>
						<th onclick="sortTable(1)">Type</th>
						<th onclick="sortTable(2)">Modified</th>
						<th onclick="sortTable(3)">Size</th>
					</tr>
				</thead>
				<tbody>"""
		)

		if total_items == 0:
			f.write(b"""
				<tr>
					<td colspan="4" style="text-align:center;padding:40px;font-style:italic;color:#666;">nothing to see here</td>
				</tr>"""
			)


		for item in listdir:
			fullname = os.path.join(path, item)
			mod_time = os.path.getmtime(fullname)
			mod_date = time.strftime('%Y-%m-%d %H:%M', time.localtime(mod_time))

			if os.path.isdir(fullname):
				f.write(f"""
					<tr>
						<td><div class="scrollable-cell">
							<a href="{urllib.parse.quote(item)}/?download=1" style="text-decoration:none;" download title="Download {item} as ZIP">⬇️</a>
							📁 <a href="{urllib.parse.quote(item)}/"><b>{item}</b>/</a>
						</div></td>
						<td>(folder)</td>
						<td>{mod_date}</td>
						<td>-</td>
					</tr>""".encode()
				)
			elif os.path.isfile(fullname):
				emoji = self.get_file_emoji(item)
				size = self.format_size(os.path.getsize(fullname))
				encoded = urllib.parse.quote(item)
				filetype = self.detect_filetype(item)
				f.write(f"""
					<tr>
						<td><div class="scrollable-cell">
							<a href="{encoded}" style="text-decoration:none;" download title="Download {item}">⬇️</a> {emoji} 
							<a href="{urllib.parse.quote(item)}">{item}</a>
						</div></td>
						<td>{filetype}</td>
						<td>{mod_date}</td>
						<td>{size}</td>
					</tr>""".encode()
				)

		f.write(b"</tbody></table></body></html>")
		length = f.tell()
		f.seek(0)

		self.send_response(200)
		self.send_header("Content-type", "text/html; charset=utf-8")
		self.send_header("Content-Length", str(length))
		self.end_headers()

		return f

		# UNREACHABLE STATEMENT
		try:
			fs = os.fstat(f.fileno())
			self.send_response(200)
			self.send_header("Content-type", ctype)
			self.send_header("Content-Length", str(fs[6]))
			# Last-Modified header
			self.send_header(
				"Last-Modified",
				self.date_time_string(fs.st_mtime)
			)
			self.end_headers()
			return f
		except:
			f.close()
			raise


	def send_head(self):
		"""Serve a file or force directory listing even if index.html exists."""

		if not self.require_auth():
			return None

		# translate URL path to local filesystem path
		path = self.translate_path(self.path)

		#if path is a directory
		if os.path.isdir(path):
			# if URL doesn't end with "/", redirect to the slash-version (same behavior as SimpleHTTPRequestHandler)
			if not self.path.endswith("/"):
				self.send_response(301)
				self.send_header("Location", f"{self.path}/")
				self.end_headers()
				return None

			# force custom directory listing (never auto-serve index.html)
			return self.list_directory(path)

		if not os.path.isfile(path):
			return None

		# not a directory - serve file normally (mimic SimpleHTTPRequestHandler)
		ctype = self.guess_type(path)
		try:
			f = open(path, "rb")
			fs = os.fstat(f.fileno())
			filename = os.path.basename(urllib.parse.unquote(self.path))

			self.send_response(200)
			self.send_header("Content-Type", ctype)
			# self.send_header("Content-Encoding", "identity")
			self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
			self.send_header("Content-Length", str(fs.st_size)) # read more smth about this
			# self.send_header("X-File-Size", str(total_size))
			# self.send_header("Accept-Ranges", "bytes")
			self.send_header("Cache-Control", "no-cache")
			self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
			self.end_headers()
			return (f, fs.st_size) # for progress bar(?)
		except OSError:
			self.send_error(404, "File not found")
			return None


	def format_size(self, size_bytes):
		if size_bytes == 0:
			return "0 B"
		for unit in ["B", "KB", "MB", "GB", "TB"]:
			if size_bytes < 1024.0:
				return f"{size_bytes:.1f} {unit}"
			size_bytes /= 1024.0
		return f"{size_bytes:.1f} PB"


	def get_file_emoji(self, filename):
		ext = os.path.splitext(filename)[1].lower()

		# you have to be aware that sometimes, two completely different file types can have the same extension
		# for example, both mpeg transport streams and typescript files use the ".ts" extension
		mapping = {
			"image": {
				".png", ".jpg", ".jpeg", ".gif",
				".bmp", ".webp", ".svg", ".tiff",
				".tif", ".ico", ".heif", ".jfif",
				".raw"
			},
			"video": {
				".mp4", ".mkv", ".mov", ".wmv",
				".flv", ".avi", ".webm", ".m4v",
				".3gp", ".mpeg", ".mpg"
			},
			"audio": {
				".mp3", ".flac", ".alac", ".ogg",
				".wav", ".ape", ".aac", ".wma",
				".midi", ".m4a", ".3gpp"
			},
			"doc": {
				".pdf", ".docx", ".doc", ".xlsx",
				".xls", ".pptx", ".ppt", ".epub",
				".odt", ".ods", ".odp", ".tex",
				".accdb"
			},
			"text": {
				".txt", ".rtf", ".md", ".csv",
				".lrc", ".srt", ".ass"
			},
			"archive": {
				".zip", ".rar", ".tar", ".7z",
				".gz", ".bz2", ".xz", ".iso",
				".lzma", ".cab"
			},
			"code": {
				".py", ".js", ".java", ".c",
				".cpp", ".cs", ".rb", ".php",
				".html", ".css", ".json", ".xml",
				".sh", ".bat", ".pl", ".go",
				".swift", ".ts", ".tsx", ".pyw"
			},
			"config": {
				".ini", ".cfg", ".conf", ".config",
				".yaml", ".yml", ".toml", ".properties"
			},
			"exe": {
				".exe", ".dll", ".bin", ".cmd",
				".com", ".msi", ".apk", ".app",
				".deb", ".rpm", ".iso", ".sys"
			},
			"font": {
				".ttf", ".otf", ".woff", ".woff2",
				".eot"
			},
			"rom": {
				".nes", ".smc", ".sfc",	# NES/SNES (existing)
				".gba", ".gbc", ".gb",	# Game Boy family
				".md", ".bin", ".gen",	# Sega Genesis/Mega Drive
				".sms", ".gg",			# Sega Master System/Game Gear
				".pce", ".sgx",			# PC Engine/TurboGrafx-16
				".nds", ".n64", ".z64",	# Nintendo DS/N64
				".psx", ".pbp", ".cue",	# PlayStation 1 (cue is ambiguous)
				".vb", ".lnx",			# Virtual Boy, Atari Lynx
				".ws", ".wsc", ".ngp",	# WonderSwan, Neo Geo Pocket
			}
		}

		emoji_map = {
			"image":	"🖼️",
			"video":	"🎥",
			"audio":	"🎵",
			"doc":		"📕",
			"text":		"📄",
			"archive":	"📦",
			"code":		"📜", # because "script"
			"config":	"⚙️",
			"exe":		"💻",
			"font":		"🔤" ,
			"rom":		"💿" 
		}

		for category, extensions in mapping.items():
			if ext in extensions:
				return emoji_map[category]

		return "📄"
	

	def detect_filetype(self, name):
		# pure dotfiles like ".env", ".gitignore", ".bashrc"
		if name.startswith(".") and "." not in name[1:]:
			return name[1:].lower()

		# normal extensions (.txt, .mp4, etc.)
		ext = os.path.splitext(name)[1]
		if ext:
			return ext[1:].lower()

		# no-extension known file types
		# for example, (most) license files in github are just "LICENSE" and not "LICENSE.txt" or ".license", etc.
		specials = {
			"LICENSE": "license",
			"LICENCE": "license",	# 🇬🇧
			"README": "readme",
			"MAKEFILE": "makefile",
			"DOCKERFILE": "dockerfile"
		}

		upper = name.upper()
		if upper in specials:
			return specials[upper]

		return "-"


	def serve_directory_zip(self, dir_path):
		path = self.translate_path(dir_path)
		if not os.path.isdir(path):
			self.send_error(404, "Directory not found")
			return None

		dir_name = os.path.basename(path) or "directory"
		dir_name_safe = urllib.parse.quote(dir_name)

		# estimate total size
		total_size = sum(
			os.path.getsize(os.path.join(root, f))
			for root, _, files in os.walk(path)
			for f in files
		)

		self.send_response(200)
		self.send_header("Content-Type", "application/zip; charset=UTF-8")
		self.send_header("Content-Encoding", "identity")
		self.send_header(
			"Content-Disposition",
			f"attachment; filename*=UTF-8''{dir_name_safe}.zip"
		)
		self.send_header("X-File-Size", str(total_size))
		self.send_header("Accept-Ranges", "bytes")
		self.send_header("Cache-Control", "no-cache")
		self.end_headers()

		""" with zipfile.ZipFile(self.wfile, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
			for root, dirs, files in os.walk(path):
				for file in files:
					try:
						full_path = os.path.join(root, file)
						rel_path = os.path.relpath(full_path, os.path.dirname(path))
						rel_path = rel_path.replace("\\", "/")  # cross-platform
						zf.write(full_path, arcname=rel_path)
						# fl;ush after each file to force data to browser
						self.wfile.flush()
					except Exception as e:
						print(f"Failed to add {file} to ZIP: {e}") """

		# stream directly to the socket
		zip_buffer = io.BytesIO()
		try:
			with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
				for root, dirs, files in os.walk(path):
					for file in files:
						try:
							full_path = os.path.join(root, file)
							rel_path = os.path.relpath(full_path, os.path.dirname(path)).replace("\\", "/")
							zf.write(full_path, arcname=rel_path)
						except Exception:
							continue
			zip_buffer.seek(0)
			shutil.copyfileobj(zip_buffer, self.wfile)
		finally:
			zip_buffer.close()

		self.wfile.flush()
		return None


	def write_unbuffered(self, data):
		self.connection.sendall(data)


	def check_auth(self):
		auth_header = self.headers.get("Authorization")
		return auth_header == f"Basic {CREDENTIALS}"


	def require_auth(self):
		if not self.check_auth():
			self.do_AUTHHEAD()
			self.wfile.write(b'<h1>Access Denied >:)</h1>')
			return False
		return True


if __name__ == "__main__":
	if DIRECTORY and os.path.isdir(DIRECTORY):
		os.chdir(DIRECTORY)
		# store original serve directory for translate_path
		UploadHandler.SERVE_ROOT = os.getcwd() if DIRECTORY and os.path.isdir(DIRECTORY) else os.getcwd()
		print(f"Serving files from: {UploadHandler.SERVE_ROOT}")

	httpd = socketserver.TCPServer((IPV4_ADDRESS, PORT), UploadHandler)

	context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	context.load_cert_chain(certfile=CERT_FILE, keyfile=CERT_KEY)
	httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
	print(f"\nGo to https://{SERVER_DIRECTORY_IP_AND_PORT}, accept self-signed certificate warning in browser")
	httpd.serve_forever()
"""
command in dir containing this file:
```
python -m http.server 9999 --cgi -b 192.168.1.22 (DON'T USE THIS)
python upload.py
```
Q: What the hell is this?
A: A HTTP file sharing thing written in python.
"""