// make this crap easier to read
function toggleUpload() {
	const fileInput = document.getElementById("file-input");
	const uploadBtn = document.getElementById("upload-btn");
	const fileListContainer = document.getElementById("file-list");

	if (!fileListContainer) {
		const container = document.createElement("div");
		container.id = "file-list";
		container.style.cssText = `
			max-height:200px;overflow-y:auto;border:1px solid #ddd;
			border-radius:4px;padding:10px;margin:10px 0;
			background:#f9f9f9;font-size:12px;max-width:50%;`;
		fileInput.parentNode.insertBefore(container, uploadBtn);
	}

	// use DataTransfer to manage files (allows removal/replacement)
	if (!window.selectedFilesDT) window.selectedFilesDT = new DataTransfer();
	const dt = window.selectedFilesDT;
	if (fileInput.files.length > 0) {
		// add new files, skipping dupes by name
		Array.from(fileInput.files).forEach(file => {
			const exists = Array.from(dt.files).some(f => f.name === file.name && f.size === file.size);
			if (!exists) dt.items.add(file);
		});
		fileInput.files = dt.files;	// update input to reflect current files
	}
	fileListContainer.innerHTML = "";
	if (dt.files.length === 0) {
		fileListContainer.innerHTML = `<em style="color:#999;">no files selected</em>`;
		uploadBtn.disabled = true;
		return;
	}
	let totalSize = 0;
	Array.from(dt.files).forEach((file, index) => {
		const fileItem = document.createElement("div");
		fileItem.style.marginBottom = "5px";
		fileItem.style.position = "relative";
		totalSize += file.size;
		fileItem.innerHTML = `
			<span style="color:#666;font-size:11px;">${index+1}.</span> 
			${file.name} <span style="color:#666;font-size:11px;">(${formatBytes(file.size)})</span>
			<button class="remove-file" data-index="${index}" style="
				position:absolute;right:5px;top:0;padding:2px 6px;
				background:#dc3545;color:white;border:none;border-radius:3px;
				font-size:10px;cursor:pointer;font-weight:bold;
			">✕</button>`;
		fileListContainer.appendChild(fileItem);
	});
	fileListContainer.innerHTML += `<div style="font-weight:bold;margin-top:5px;color:#007cba;">
		total: ${dt.files.length} file(s), ${formatBytes(totalSize)}
	</div>`;
	// bind remove handlers
	fileListContainer.querySelectorAll(".remove-file").forEach(btn => {
		btn.onclick = function(e) {
			e.stopPropagation();
			const idx = parseInt(this.dataset.index);
			const newDT = new DataTransfer();
			Array.from(dt.files).forEach((f, i) => {
				if (i !== idx) newDT.items.add(f);
			});
			window.selectedFilesDT = newDT;
			fileInput.files = newDT.files;
			toggleUpload();  // refresh list
		};
	});
	uploadBtn.disabled = false;
	uploadBtn.textContent = `upload ${dt.files.length} file(s)`;
}

let currentEventSource = null;
let currentAbortController = null;

function startDirDownload(dirLink) {
	const dirName = dirLink.title?.replace("Download ", "")
		|| dirLink.textContent.trim().replace("⬇️", "").trim();
	const ssePath = dirLink.href.replace("?download=1", "")
		+ "?sse=1";
	const downloadPath = dirLink.href;
	const container = document.getElementById("download-status");
	currentAbortController = new AbortController();
	container.innerHTML = `
		<div id="progress-container">
			<span>⏳ zipping "${dirName}"...</span>
			<div style="flex:1;">
				<div id="progress-bar">
					<div id="progress-fill"></div>
				</div>
				<div id="progress-text">0%</div>
			</div>
			<button id="cancel-btn">❌ cancel</button>
		</div>
	`;
	container.style.display = "block";
	// cancel button handler
	document.getElementById("cancel-btn").onclick = function() {
		if (currentEventSource) currentEventSource.close();
		if (currentAbortController) currentAbortController.abort();
		container.innerHTML = `❌ "${dirName}" zipping cancelled`;
		setTimeout(() => container.style.display = "none", 2000);
	};

	if (currentEventSource) currentEventSource.close();
	const eventSource = new EventSource(
		ssePath,
		{ signal: currentAbortController.signal }
	);
	currentEventSource = eventSource;

	eventSource.onmessage = function(event) {
		try {
			const data = JSON.parse(event.data);
			if (data.complete) {
				container.innerHTML = `✅ "${dirName}.zip" ready (${formatBytes(data.size)})`;
				document.getElementById("cancel-btn")?.remove();
				setTimeout(() => {
					window.location.href = downloadPath;
					container.style.display = "none";
				}, 800);
				eventSource.close();
				return;
			}
			if (data.error || data.cancelled) {
				container.innerHTML = `${data.message || "zipping cancelled"}`;
				setTimeout(() => container.style.display = "none", 3000);
				eventSource.close();
				return;
			}

			const percent = Math.round(data.percent);
			document.getElementById("progress-fill").style.width = percent + "%";
			document.getElementById("progress-text").textContent = 
				`${percent}% (${formatBytes(data.processed_bytes)} / ${formatBytes(data.total_size)})`;
		} catch(e) {}
	};
	eventSource.onerror = function() {
		container.innerHTML = `connection failed for "${dirName}"`;
		setTimeout(() => container.style.display = "none", 3000);
		eventSource.close();
	};
}

// this is for the zipping folder decal
function formatBytes(bytes) {
	if (!bytes) return "0 B";
	const k = 1024, sizes = ["B", "KB", "MB", "GB"];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return (bytes / Math.pow(k, i)).toFixed(1) + " " + sizes[i];
}

document.addEventListener("click", function(e) {
	const downloadLink = e.target.closest("a[href]");
	if (
		downloadLink &&
		downloadLink.href.includes("?download=1")
	) {
		// only treat as a directory zipping operation if
		// the path ends with a slash
		const url = new URL(downloadLink.href);
		if (url.pathname.endsWith("/")) {
			e.preventDefault();
			startDirDownload(downloadLink);
		}
	} else if (
		downloadLink &&
		(downloadLink.getAttribute("download") ||
		downloadLink.textContent.includes("⬇️"))
	) {
		const filename = downloadLink.title?.replace("Download ", "") || "file";
		const container = document.getElementById("download-status");
		container.innerHTML = `⏳ downloading "${filename}"...`;
		container.style.display = 'block';
		setTimeout(() => container.style.display = 'none', 25000);
	}
}, true);

function detectDevice() {
	const ua = navigator.userAgent;
	const platform = navigator.platform;
	const language = navigator.language;
	const screenRes = `${screen.width}x${screen.height}`;
	// chrome-only thing
	const deviceMemory = navigator.deviceMemory || "-1";
	const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
	const isTablet = /iPad|Android(?!.*Mobile)|Tablet/i.test(ua);

	const deviceType = isMobile ? "Mobile" : (isTablet ? "Tablet" : "Desktop");

	const browser = ua.includes("Chrome") ? "Chrome" :
				ua.includes("Firefox") ? "Firefox" :
				ua.includes("Safari") ? "Safari" :
				ua.includes("Edge") ? "Edge" : "Other";
	
	const info = document.createElement("div");
	info.id = "client-info";
	info.style.cssText = `
		background:#e8f4fd;padding:12px;border:1px solid #007cba;
		border-radius:6px;margin:10px 0;font-size:13px;
		font-family:monospace;
	`;
	info.innerHTML = `
		<strong>${deviceType}</strong> | 
		${browser} on ${platform} | 
		${screenRes} | 
		${language} | 
		RAM: ${deviceMemory}GB
	`;
	const serverInfo = document.querySelector('div[style*="background:#f0f8ff"]');
	if (serverInfo)
		serverInfo.parentNode.insertBefore(info, serverInfo.nextSibling);
	else
		document.body.insertBefore(info, document.body.firstChild);
}

// run on page load
if (document.readyState === "loading")
	document.addEventListener("DOMContentLoaded", detectDevice);
else
	detectDevice();

let selectedItems = new Set();

function toggleAll(checkbox) {
	document.querySelectorAll('.file-select').forEach(cb => {
		cb.checked = checkbox.checked;
	});
	updateSelection();
}

function updateSelection() {
	selectedItems.clear();
	document.querySelectorAll('.file-select:checked').forEach(cb => {
		selectedItems.add(cb.value);
	});
	const count = selectedItems.size;
	const btn = document.getElementById('multi-download');
	btn.disabled = count === 0;
	btn.textContent = `⬇️ download selected (${count})`;
}

// Add to existing document.addEventListener("click"...)
document.addEventListener("change", function(e) {
	if (e.target.classList.contains('file-select')) {
		updateSelection();
	}
});

// multi-download function
function downloadSelected() {
	if (selectedItems.size === 0) return;

	const form = document.createElement("form");
	form.method = "POST";
	form.style.display = "none";
	form.enctype = "multipart/form-data";

	const multiDownloadInput = document.createElement("input");
	multiDownloadInput.type = "hidden";
	multiDownloadInput.name = "multi_download";
	multiDownloadInput.value = "1";
	form.appendChild(multiDownloadInput);

	selectedItems.forEach(item => {
		const itemInput = document.createElement("input");
		itemInput.type = "hidden";
		itemInput.name = "items[]";
		itemInput.value = item;
		form.appendChild(itemInput);
	});

	const container = document.getElementById("download-status");
	container.innerHTML = `zipping ${selectedItems.size} items...`;
	container.style.display = "block";

	// submit form, browser handles download natively
	document.body.appendChild(form);
	form.submit();
	document.body.removeChild(form);

	// update status after delay
	setTimeout(() => {
		container.innerHTML = "zipping complete";
		setTimeout(() => container.style.display = "none", 3000);
	}, 1000);
}