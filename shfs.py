"""
Simple HTTP file server.

TBD
code looks funky
"""

import http.server
import socketserver
import cgi
import os
import time
import urllib
import html
import io

from dotenv import load_dotenv

load_dotenv()

IPV4_ADDRESS = os.getenv("IP_ADD")
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
- add a password
- visually remove this file in root (NOT DELETE)
"""

class UploadHandler(http.server.SimpleHTTPRequestHandler):

	def index_path(self, path):
		return None


	# inject custom html to directory path
	def list_directory(self, path):
		try:
			listdir = os.listdir(path)
		except OSError:
			self.send_error(404, "No permission to list directory")
			return None
		
		listdir.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
		f = io.BytesIO()
		displaypath = html.escape(urllib.parse.unquote(self.path))

		# move these to a separate html file?
		f.write(b"""
		<!DOCTYPE html>
		<html>
			<head>
				<meta charset="utf-8">
				<meta name="viewport" content="width=device-width, initial-scale=1.0">
				<link rel="icon" type="image/x-icon" href="https://img.icons8.com/?size=100&id=kktvCbkDLbNb&format=png&color=000000">
				<title>files on """ + SERVER_DIRECTORY_IP_AND_PORT.encode() + b"""</title>
				<style>
					body { font-family: monospace; font-size:14px; max-width:600px; margin:auto; padding:20px; }
					input[type=file], input[type=submit] { font-size:18px; padding:10px; width:50%; margin:10px 0;}
					#fileTable { width:100%; border-collapse: collapse; }
					th { padding:10px; border:1px solid #ccc; cursor:pointer; background:#f0f0f0; }
					td { border:1px solid black; padding:8px; vertical-align: top; }
					.scrollable-cell { max-width: 250px; overflow-x: auto; white-space: nowrap; }
				</style>
				<script>
					function toggleUpload() {
						const fileInput = document.getElementById('fileInput');
						const uploadBtn = document.getElementById('uploadBtn');
						uploadBtn.disabled = fileInput.files.length === 0;
						uploadBtn.textContent = fileInput.files.length > 0 ? 
							`Upload ${fileInput.files.length} file(s)` : 'Upload Files';
					}

					function sortTable(n) {
						let table = document.getElementById("fileTable");
						let switching = true;
						let dir = "asc";
						while (switching) {
							switching = false;
							let rows = table.rows;
							for (let i = 1; i < (rows.length - 1); i++) {
								let shouldSwitch = false;
								let x = rows[i].getElementsByTagName("TD")[n];
								let y = rows[i + 1].getElementsByTagName("TD")[n];
								if(dir === "asc" && x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
									shouldSwitch = true; break;
								}
								if(dir === "desc" && x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
									shouldSwitch = true; break;
								}
							}
							if (shouldSwitch) {
								rows[i].parentNode.insertBefore(rows[i+1], rows[i]);
								switching = true;
							} else {
								if(dir === "asc") dir = "desc"; else dir = "asc";
							}
						}
					}
				</script>
			</head>
			<body>
		""")
		if self.path == "/" or self.path.strip("/") == "":
			f.write('<div style="margin-bottom: 20px;"><strong>root dir</strong></div>'.encode('utf-8'))
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

			f.write(f'<div style="margin-bottom: 20px;">'
				f'<a href="{parent_http}" style="display:inline-block;padding:10px 15px;background:#ddd;margin-right:10px;text-decoration:none;border-radius:4px;">up one level</a>'
				f'<a href="/" style="display:inline-block;padding:10px 15px;background:#007cba;color:white;text-decoration:none;border-radius:4px;">go to root</a>'
				f'</div>'.encode('utf-8'))

		f.write(f"<h1>📁 {displaypath or 'home'}</h1>".encode())
		f.write(b"""
		<form method="post" enctype="multipart/form-data" action=".">
			<input type="file" id="fileInput" name="file" multiple onchange="toggleUpload()">
			<input type="submit" id="uploadBtn" value="Upload files" disabled>
		</form>
		<table id="fileTable">
			<thead>
				<tr><th onclick="sortTable(0)">Name</th><th onclick="sortTable(1)">Modified</th><th onclick="sortTable(2)">Size</th></tr>
			</thead>
		<tbody>""")

		for item in listdir:
			fullname = os.path.join(path, item)
			mod_time = os.path.getmtime(fullname)
			mod_date = time.strftime('%Y-%m-%d %H:%M', time.localtime(mod_time))

			if os.path.isdir(fullname):
				f.write(f'<tr><td class="scrollable-cell">📁 <a href="{urllib.parse.quote(item)}/">{item}/</a></td>'.encode())
				f.write(f'<td>{mod_date}</td><td>-</td></tr>'.encode())
			elif os.path.isfile(fullname):
				emoji = self.get_file_emoji(item)
				size = self.format_size(os.path.getsize(fullname))
				f.write(f'<tr><td><div class="scrollable-cell">{emoji} <a href="{urllib.parse.quote(item)}">{item}</a></div></td>'.encode())
				f.write(f'<td>{mod_date}</td><td>{size}</td></tr>'.encode())

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

		# translate URL path to local filesystem path
		path = self.translate_path(self.path)

		#if path is a directory
		if os.path.isdir(path):
			# if URL doesn't end with "/", redirect to the slash-version (same behavior as SimpleHTTPRequestHandler)
			if not self.path.endswith("/"):
				new_path = self.path + "/"
				self.send_response(301)
				self.send_header("Location", new_path)
				self.end_headers()
				return None

			# force custom directory listing (never auto-serve index.html)
			return self.list_directory(path)

		# not a directory — serve file normally (mimic SimpleHTTPRequestHandler)
		ctype = self.guess_type(path)
		try:
			f = open(path, "rb")
		except OSError:
			self.send_error(404, "File not found")
			return None

		try:
			fs = os.fstat(f.fileno())
			self.send_response(200)
			self.send_header("Content-type", ctype)
			self.send_header("Content-Length", str(fs[6]))
			# Last-Modified header
			self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
			self.end_headers()
			return f
		except:
			f.close()
			raise


	def do_POST(self):
		# get the actual directory path from request
		dir_path = urllib.parse.unquote_plus(self.path.rstrip('/'))
		if not dir_path or dir_path == '/':
			dir_path = '.'
		
		form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD":"POST"})
		
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
		# normalize abnd decode path
		parsed = urllib.parse.urlsplit(self.path)
		path_unquoted = urllib.parse.unquote(parsed.path)
		basename = os.path.basename(path_unquoted.rstrip("/")).lower()

		# if the requested resource is index.html, go back to the parent
		# directory listing
		if basename == "index.html":
			parent = os.path.dirname(path_unquoted)
			if not parent.endswith("/"):
				parent += "/"
			if parent == "":
				parent = "/"

			# relative redirect to the parent directory
			self.send_response(303)
			self.send_header('Location', parent)
			self.end_headers()
			return

		# only force plain-text for ACTUAL text documents
		text_ext = (".txt", ".md", ".log", ".ini", ".cfg", ".conf")

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

		# serve EVERYTHING ELSE normally - css, js, html, json, etc
		return super().do_GET()


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
				".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
				".tiff", ".tif", ".ico", ".heif", ".jfif", ".raw"
			},
			"video": {
				".mp4", ".mkv", ".mov", ".wmv", ".flv", ".avi", ".webm", ".m4v",
				".3gp", ".mpeg", ".mpg"
			},
			"music": {
				".mp3", ".flac", ".alac", ".ogg", ".wav", ".ape", ".aac", ".wma",
				".midi", ".m4a"
			},
			"doc": {
				".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".epub",
				".odt", ".ods", ".odp", ".csv", ".tex", ".md"
			},
			"text": {
				".txt", ".rtf", ".md"
			},
			"archive": {
				".zip", ".rar", ".tar", ".7z", ".gz", ".bz2", ".xz", ".iso", ".lzma",
				".cab", ".apk"
			},
			"code": {
				".py", ".js", ".java", ".c", ".cpp", ".cs", ".rb", ".php", ".html",
				".css", ".json", ".xml", ".sh", ".bat", ".pl", ".go", ".swift", ".ts", ".tsx"
			},
			"config": {
				".ini", ".cfg", ".conf", ".config", ".yaml", ".yml", ".toml", ".properties"
			},
			"exe": {
				".exe", ".dll", ".bin", ".cmd", ".com", ".msi", ".apk", ".app", ".deb",
				".rpm", ".iso", ".sys"
			},
			"font": {
				".ttf", ".otf", ".woff", ".woff2", ".eot"
			}
		}

		emoji_map = {
			"image":	"🖼️",
			"video":	"🎥",
			"music":	"🎵",
			"doc":		"📕",
			"text":		"📄",
			"archive":	"📦",
			"code":		"📜", # because "script"
			"config":	"⚙️",
			"exe":		"💻",
			"font":		"🔤"
		}

		for category, extensions in mapping.items():
			if ext in extensions:
				return emoji_map[category]

		return "📄"


""" UploadHandler.extensions_map={
	'.manifest': 'text/cache-manifest',
	# '.html': 'text/html',
	'.png': 'image/png',
	'.jpg': 'image/jpg',
	'.svg': 'image/svg+xml',
	'.css': 'text/css',
	'.js': 'application/x-javascript',
	'': 'application/octet-stream', # default
} """

with socketserver.TCPServer((IPV4_ADDRESS, PORT), UploadHandler) as httpd:
	print(f"\nGO TO http://{SERVER_DIRECTORY_IP_AND_PORT}")
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