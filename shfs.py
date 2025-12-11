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
import io
import base64
import zipfile
import shutil
import socket
import json
import ssl

from dotenv import load_dotenv

import socket

load_dotenv()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_FILE = os.path.join(THIS_DIR, "style.css")
JS_FILE = os.path.join(THIS_DIR, "script.js")
USERNAME = os.getenv("HTTP_USER")
PASSWORD = os.getenv("HTTP_PASS")
DEFAULT_CERT = os.path.join(THIS_DIR, "server.crt")
DEFAULT_KEY = os.path.join(THIS_DIR, "server.key")
CERT_FILE = os.path.join(THIS_DIR, os.getenv("SSL_CERT", DEFAULT_CERT))
CERT_KEY = os.path.join(THIS_DIR, os.getenv("SSL_KEY", DEFAULT_KEY))
CREDENTIALS = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
try:
	# returns your ip for some reason
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
		s.connect(("8.8.8.8", 80))
		IPV4_ADDRESS = s.getsockname()[0]
except Exception:
	IPV4_ADDRESS = "127.0.0.1"
PORT = 9999 # baka baka

# target folder for uploads, change this to whatever path you like, for example:
# DIRECTORY = "C:\Users\User\Desktop\"
# set it to "." to use current working directory instead (this folder)
DIRECTORY = os.getenv("FOLDER") # "."
if DIRECTORY and os.path.isdir(DIRECTORY):
	os.chdir(DIRECTORY)
else:
	print(f"Warning: DIRECTORY {DIRECTORY} is not set or does not exist. "
			"Using current working directory."
		)
SERVER_DIRECTORY_IP_AND_PORT = f"{IPV4_ADDRESS}:{PORT}/"

"""
to-do
- visually remove this file in root (NOT DELETE) or make undeletable instead, idk
- ui looks like crap on desktop
- make CREDENTIALS more secure because what you're doing is complete ass

done/implemented
- add a password
- move the up one level and root buttons closer to the table
- add a file and directory count, and total items indicator somewhere
- uploading a file to folders other than the root is broken
- show "nothing to see here" inside empty directories when opened
- any file named exactly "index.html" can't be opened, unintended redirect loop
- download a directory but compress it first
- make each dir clickable on the root/path/path/... etc
- can't download invdividual files directly using download button on microsoft edge
- how to automatically get valid ipv4 address from ipconfig
- show the list of the files to be uploaded instead of being crammed like that
- how to make downloads faster
- checkbox and zip for multi-download with the name of the directory
- btn is null when clicking on checkboxes
"""

class FileServerHandler(http.server.SimpleHTTPRequestHandler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.wfile = self.wfile
		self.request.settimeout(300)
		try:
			# nagle thing
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
			dir_path = "."	# fallback to current working directory if invalid

		form = cgi.FieldStorage(
			fp=self.rfile,
			headers=self.headers,
			environ={"REQUEST_METHOD":"POST"}
		)

		uploaded_count = 0
		if "file" in form:	# if there are multiple files to be uploaded
			file_items = form["file"]
			if isinstance(file_items, list):
				for file_item in file_items:
					if file_item.filename and file_item.file:
						filename = os.path.basename(file_item.filename.strip())
						if filename:
							filepath = os.path.join(dir_path, filename)
							os.makedirs(os.path.dirname(filepath),
								exist_ok=True)
							with open(filepath, "wb") as f:
								shutil.copyfileobj(file_item.file, f)
							uploaded_count += 1
			else:	# else single file
				if file_items.filename and file_items.file:
					filename = os.path.basename(file_items.filename.strip())
					if filename:
						filepath = os.path.join(dir_path, filename)
						os.makedirs(os.path.dirname(filepath), exist_ok=True)
						with open(filepath, "wb") as f:
							shutil.copyfileobj(file_items.file, f)
						uploaded_count += 1

		if form.getvalue("multi_download"):
			items = form.getlist("items[]")
			if not items:
				self.send_response(400)
				self.end_headers()
				return

			zip_buffer = io.BytesIO()
			try:
				with zipfile.ZipFile(
					zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6
				) as zf:
					for item_encoded in items:
						item_path = os.path.join(dir_path,
							urllib.parse.unquote(item_encoded))
						if os.path.exists(item_path):
							if os.path.isdir(item_path):
								# add directory recursively
								for root, _, files in os.walk(item_path):
									for file in files:
										full_path = os.path.join(root, file)
										rel_path = os.path.relpath(full_path,
											dir_path).replace("\\", "/")
										zf.write(full_path, arcname=rel_path)
							else:
								# add single file
								rel_path = os.path.basename(item_path)
								zf.write(item_path, arcname=rel_path)
				current_folder = os.path.basename(os.path.normpath(dir_path)) \
					or "selection"
				zip_filename = f"{current_folder}.zip"
				zip_buffer.seek(0)
				self.send_response(200)
				self.send_header("Content-Type", "application/zip")
				self.send_header("Content-Disposition",
					f'attachment; filename="{zip_filename}"')
				self.send_header("Content-Length",
					str(len(zip_buffer.getvalue())))
				self.end_headers()
				shutil.copyfileobj(zip_buffer, self.wfile)
			finally:
				zip_buffer.close()
			return

		if uploaded_count > 0:
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

		# serve css and js from script directory, yes, i know this is dumb
		# but since these files lie in a different dir than the one we're
		# hosting, this is needed
		parsed_path = urllib.parse.urlparse(self.path).path.lstrip("/")
		if parsed_path == "style.css" and os.path.exists(CSS_FILE):
			with open(CSS_FILE, "rb") as f:
				content = f.read()
			self.send_response(200)
			self.send_header("Content-Type", "text/css; charset=utf-8")
			self.send_header("Content-Length", str(len(content)))
			self.end_headers()
			self.wfile.write(content)
			return

		if parsed_path == "script.js" and os.path.exists(JS_FILE):
			with open(JS_FILE, "rb") as f:
				content = f.read()
			self.send_response(200)
			self.send_header("Content-Type",
				"application/javascript; charset=utf-8")
			self.send_header("Content-Length", str(len(content)))
			self.end_headers()
			self.wfile.write(content)
			return

		# normalize and decode path
		parsed = urllib.parse.urlsplit(self.path)
		path_unquoted = urllib.parse.unquote(parsed.path)
		query_params = urllib.parse.parse_qs(parsed.query)

		# check SSE first before directory download
		if query_params.get("sse"):
			target = self.translate_path(path_unquoted.rstrip("/"))
			if os.path.isdir(target):
				self.do_SSE(path_unquoted.rstrip("/"))
				return None
			else:
				# SSE requested for a file or missing path, return a clear error
				# send a small event-stream style error so EventSource receives 
				# the correct mime
				self.send_response(400)
				self.send_header("Content-Type", "text/event-stream")
				self.send_header("Cache-Control", "no-cache")
				self.send_header("Connection", "close")
				self.end_headers()
				try:
					# send a single SSE data block explaining failure
					self.wfile.write(
						b"data: {\"error\": true, \"message\": "
						b"\"SSE only available for directories\"}\n\n"
					)
					self.wfile.flush()
				except Exception:
					pass
				return None

		# check for dir dl request
		if query_params.get("download") and \
			os.path.isdir(self.translate_path(path_unquoted.rstrip("/"))):
			return self.serve_directory_zip(path_unquoted.rstrip("/"))

		# only force plain-text for ACTUAL text documents
		# "LICENSE" and "LICENCE" are for the license files commonly found in
		#  git repositories
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
					self.send_header("Content-type", "text/plain; charset=utf-8")
					self.end_headers()
					self.wfile.write(content.encode("utf-8"))
					return

			except Exception:
				pass

		result = self.send_head()
		if result:
			if isinstance(result, tuple):	# (file, size) - individual file
				f, total_size = result
				try:
					# microsoft edge case (pun?)
					CHUNK_SIZE = 65536  # 64KB chunks
					while True:
						chunk = f.read(CHUNK_SIZE)
						if not chunk: break
						self.wfile.write(chunk)
						self.wfile.flush()
					self.wfile.flush()
				finally:
					f.close()
			else:	# directory listing
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
				# do i need to do this?
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
				for root, _, files in os.walk(path):
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
			self.wfile.write(f'data: {{"error": true, "message": "{str(e)}"}}\n\n'.encode("utf-8"))
			self.wfile.flush()


	def generate_breadcrumbs(self, path):
		"""
		Generate breadcrumb HTML from current path.
		https://en.wikipedia.org/wiki/Breadcrumb_navigation
		/root/path1/path2/path3/... where all the paths are clickable
		"""
		parts = [p for p in path.strip("/").split("/") if p]
		breadcrumbs = []
		# root link (always present)
		breadcrumbs.append('<a href="/" class="breadcrumb-link">root</a>')
		# Build clickable path segments
		current_path = ""
		for i, part in enumerate(parts):
			display_name = urllib.parse.unquote(part)
			# encoded_part = urllib.parse.quote(part)
			current_path += f"/{part}"
			current_path_segments = parts[:i+1]
			# full path up to this segment
			full_http_path = "/" + "/".join(current_path_segments) + "/"
			breadcrumbs.append(
				f'<a href="{full_http_path}" class="breadcrumb-link">'
				f'{display_name}</a>'
			)

		return "/".join(breadcrumbs)


	def list_directory(self, path):
		"""Inject custom HTML to directory path."""
		if not self.require_auth():
			return None

		f = io.BytesIO()

		try:
			listdir = os.listdir(path)

			num_files = sum(
				1 for item in listdir
				if os.path.isfile(os.path.join(path, item)))
			num_dirs = sum(
				1 for item in listdir
				if os.path.isdir(os.path.join(path, item)))
			total_items = len(listdir)
			total_size_bytes = sum(
				os.path.getsize(os.path.join(path, item))
				for item in listdir if os.path.isfile(os.path.join(path, item)))
		except OSError:
			self.send_error(404, "No permission to list directory")
			return None

		listdir.sort(
			key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))

		f.write(f"""
		<!DOCTYPE html>
		<html>
			<head>
				<meta charset="utf-8">
				<meta name="viewport" content="width=device-width, initial-scale=1.0">
				<link rel="icon" type="image/x-icon" href="https://img.icons8.com/?id=kktvCbkDLbNb&format=png">
				<title>files on https://{SERVER_DIRECTORY_IP_AND_PORT}</title>
				<link rel="stylesheet" type="text/css" href="/style.css">
				<script type="text/javascript" src="/script.js"></script>
			</head>
			<body>
				<form method="post" enctype="multipart/form-data" action=".">
					<input type="file" id="file-input" name="file" multiple onchange="toggleUpload()">
					<div id="file-list"></div>
					<input type="submit" id="upload-btn" value="Upload files" disabled>
				</form>
				<h3>📁 {self.generate_breadcrumbs(self.path)}</h3>
		""".encode("utf-8"))

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

			f.write(f"""<a href="{parent_http}" id="up-one-level" title="up one level">⬆️</a>""".encode("utf-8"))

		f.write(f"""
			<a id="multi-download" disabled onclick="downloadSelected()">
				⬇️ download selected (0)
			</a>
			<div id="download-status"></div>""".encode("utf-8"))

		directory_info = f"""
			<ul>
				<li>Directories: <b>{num_dirs}</b></li>
				<li>Files: <b>{num_files}</b></li>
				<li>Total items: <b>{total_items}</b></li>
				<li>Total size: <b>{self.format_size(total_size_bytes)} ({total_size_bytes:,} bytes)</b></li>
			</ul>""".encode("utf-8")

		f.write(directory_info + b"""
			<div><i>(refresh the page if changes do not reflect across devices)</i></div>
			<table id="file-table">
				<thead>
					<tr>
						<th style="width:20px;"><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>	
						<th>Name</th>
						<th>Type</th>
						<th>Modified</th>
						<th>Size</th>
					</tr>
				</thead>
				<tbody>""")

		if total_items == 0:
			f.write(b"""
				<tr>
					<td id="empty-directory" colspan="5">nothing to see here</td>
				</tr>""")

		for item in listdir:
			fullname = os.path.join(path, item)
			mod_time = os.path.getmtime(fullname)
			mod_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(mod_time))

			if os.path.isdir(fullname):
				f.write(f"""
					<tr>
						<td style="width:20px;text-align:center;">
							<input type="checkbox" class="file-select"
								value="{urllib.parse.quote(item)}" 
								data-type="dir"
								data-path="{urllib.parse.quote(fullname)}">
						</td>
						<td><div class="scrollable-cell">
							<a href="{urllib.parse.quote(item)}/?download=1"
								class="directory-item"
								download title="download {item} as zip">⬇️</a>
							📁 <a href="{urllib.parse.quote(item)}/"
								class="directory-item"><b>{item}</b>/</a>
						</div></td>
						<td>(folder)</td>
						<td>{mod_date}</td>
						<td>-</td>
					</tr>""".encode("utf-8"))
			elif os.path.isfile(fullname):
				emoji = self.get_file_emoji(item)
				size = self.format_size(os.path.getsize(fullname))
				encoded = urllib.parse.quote(item)
				filetype = self.detect_filetype(item)
				# for some reason on edge, adding a "download" attribute on the
				# anchor below prevents it from downloading
				# you can download the file manually by right clicking and
				# saving it as a file, but that's stupid
				f.write(f"""
					<tr>
						<td style="width:20px;text-align:center;">
							<input type="checkbox" class="file-select"
								value="{urllib.parse.quote(item)}" 
								data-type="file"
								data-path="{urllib.parse.quote(fullname)}">
						</td>
						<td><div class="scrollable-cell">
							<a href="{encoded}?download=1/"
								class="directory-item"
								title="Download {item}">⬇️</a>
							{emoji} <a href="{encoded}"
								class="directory-item">{item}</a>
						</div></td>
						<td>{filetype}</td>
						<td>{mod_date}</td>
						<td title="{os.path.getsize(fullname):,} bytes">{size}</td>
					</tr>""".encode("utf-8"))

		f.write(b"</tbody></table></body></html>")
		length = f.tell()
		f.seek(0)

		self.send_response(200)
		self.send_header("Content-type", "text/html; charset=utf-8")
		self.send_header("Content-Length", str(length))
		self.end_headers()

		return f


	def send_head(self):
		"""Serve a file or force directory listing even if index.html exists."""

		if not self.require_auth():
			return None

		# translate url path to local filesystem path
		path = self.translate_path(self.path)

		#if path is a directory
		if os.path.isdir(path):
			# if url doesn't end with "/", redirect to the slash-version
			# (same behavior as SimpleHTTPRequestHandler)
			if not self.path.endswith("/"):
				self.send_response(301)
				self.send_header("Location", f"{self.path}/")
				self.end_headers()
				return None
			# force custom directory listing (never auto-serve index.html)
			return self.list_directory(path)

		if not os.path.isfile(path):
			self.send_error(404, "File not found")
			return None

		# not a directory, serve file normally (mimic SimpleHTTPRequestHandler)
		ctype = self.guess_type(path)
		try:
			f = open(path, "rb")
		except OSError:
			self.send_error(404, "File not found")
			return None
		
		fs = os.fstat(f.fileno())
		# there was a weird edge case here that it downloaded .7z files as .tgz
		parsed_path = urllib.parse.urlparse(self.path).path
		filename = os.path.basename(urllib.parse.unquote(parsed_path))

		parsed = urllib.parse.urlparse(self.path)
		params = urllib.parse.parse_qs(parsed.query)
		is_download = "download" in params

		self.send_response(200)
		self.send_header("Content-Type", ctype)
		self.send_header("Content-Length", str(fs.st_size)) # read more smth about this
		self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
		self.send_header("Cache-Control", "no-cache")
		# IMPORTANT DO NOT REMOVE
		if is_download:
			self.send_header(
				"Content-Disposition",
				f"attachment; filename=\"{filename}\""
			)
		else:
			self.send_header(
				"Content-Disposition",
				f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}"
			)
		self.end_headers()
		return (f, fs.st_size) # for progress bar(?)


	def format_size(self, size_bytes):
		if size_bytes == 0:
			return "0 B"
		elif size_bytes < 1024.0:
			return f"{size_bytes} B"
		# first unit doesn't matter
		for unit in ["", "KB", "MB", "GB", "TB"]:
			if size_bytes < 1024.0:
				return f"{size_bytes:.2f} {unit}"
			size_bytes /= 1024.0
		return f"{size_bytes:.1f} PB"


	def get_file_emoji(self, filename):
		ext = os.path.splitext(filename)[1].lower()

		# you have to be aware that sometimes, two completely different file
		# types can have the same extension
		# for example, both mpeg transport streams and typescript files use the
		# ".ts" extension
		mapping = {
			"image": {
				".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
				".tiff", ".tif", ".ico", ".heif", ".jfif", ".raw"
			},
			"video": {
				".mp4", ".mkv", ".mov", ".wmv", ".flv", ".avi", ".webm", ".m4v",
				".3gp", ".mpeg", ".mpg"
			},
			"audio": {
				".mp3", ".flac", ".alac", ".ogg", ".wav", ".ape", ".aac",
				".wma", ".midi", ".m4a", ".3gpp"
			},
			"doc": {
				".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
				".epub", ".odt", ".ods", ".odp", ".tex", ".accdb"
			},
			"text": {
				".txt", ".rtf", ".md", ".csv", ".lrc", ".srt", ".ass"
			},
			"archive": {
				".zip", ".rar", ".tar", ".7z", ".gz", ".bz2", ".xz", ".iso",
				".lzma", ".cab"
			},
			"code": {
				".py", ".js", ".java", ".c", ".cpp", ".cs", ".rb", ".php",
				".html", ".css", ".json", ".xml", ".sh", ".bat", ".pl", ".go",
				".swift", ".ts", ".tsx", ".pyw", "htm"
			},
			"config": {
				".ini", ".cfg", ".conf", ".config", ".yaml", ".yml", ".toml",
				".properties"
			},
			"exe": {
				".exe", ".dll", ".bin", ".cmd", ".com", ".msi", ".apk", ".app",
				".deb", ".rpm", ".iso", ".sys"
			},
			"font": {
				".ttf", ".otf", ".woff", ".woff2", ".eot"
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
		# for example, (most) license files in github are just "LICENSE" and not
		# "LICENSE.txt" or ".license", etc.
		specials = {
			"LICENSE":		"license",
			"LICENCE":		"license",	# 🇬🇧
			"README":		"readme",
			"MAKEFILE":		"makefile",
			"DOCKERFILE":	"dockerfile"
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

		# stream directly to the socket
		zip_buffer = io.BytesIO()
		try:
			with zipfile.ZipFile(
				zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6
			) as zf:
				for root, _, files in os.walk(path):
					for file in files:
						try:
							full_path = os.path.join(root, file)
							rel_path = os.path.relpath(
								full_path, os.path.dirname(path)
							).replace("\\", "/")
							zf.write(full_path, arcname=rel_path)
						except Exception:
							continue
			zip_buffer.seek(0)
			shutil.copyfileobj(zip_buffer, self.wfile)
		finally:
			zip_buffer.close()

		self.wfile.flush()
		return None


	def require_auth(self) -> bool:
		"""Checks if the user is authenticated."""
		auth_header = self.headers.get("Authorization")
		if not auth_header == f"Basic {CREDENTIALS}":
			self.do_AUTHHEAD()
			self.wfile.write(b"<h1>Access Denied >:)</h1>")
			return False
		return True


if __name__ == "__main__":
	if DIRECTORY and os.path.isdir(DIRECTORY):
		os.chdir(DIRECTORY)
		# store original serve directory for translate_path
		FileServerHandler.SERVE_ROOT = os.getcwd() \
			if DIRECTORY and os.path.isdir(DIRECTORY) else os.getcwd()
		print(f"Serving files from: {FileServerHandler.SERVE_ROOT}")

	httpd = socketserver.ThreadingTCPServer((IPV4_ADDRESS, PORT), FileServerHandler)
	httpd.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
	httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)	# 1MB
	httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
	context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	context.load_cert_chain(certfile=CERT_FILE, keyfile=CERT_KEY)
	httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
	print(
		f"\nGo to https://{SERVER_DIRECTORY_IP_AND_PORT}, "
		"accept self-signed certificate warning in browser"
	)
	httpd.serve_forever()
