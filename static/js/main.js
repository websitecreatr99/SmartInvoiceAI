const fileInput = document.getElementById("pdf-upload");
const fileList = document.getElementById("file-list");
const resultsDiv = document.getElementById("results");
const processBtn = document.getElementById("process-btn");

let selectedFiles = [];

// 1️⃣ Handle file selection & show in sidebar
fileInput.addEventListener("change", () => {
  selectedFiles = Array.from(fileInput.files);
  renderFileList();
});

// Render selected files with remove option
function renderFileList() {
  fileList.innerHTML = "";
  selectedFiles.forEach((file, index) => {
    const div = document.createElement("div");
    div.className = "file-item";
    div.innerHTML = `
      <span class="file-name">${file.name}</span>
      <button class="file-remove" data-index="${index}">✖</button>
    `;
    fileList.appendChild(div);
  });

  // Attach remove handlers
  document.querySelectorAll(".file-remove").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const idx = e.target.dataset.index;
      selectedFiles.splice(idx, 1);
      renderFileList();
    });
  });
}

// 2️⃣ Process button click
processBtn.addEventListener("click", async () => {
  if (!selectedFiles.length) {
    alert("Please select at least one PDF file.");
    return;
  }

  resultsDiv.innerHTML = "<p>⏳ Uploading & Processing... please wait</p>";

  // Upload first
  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("pdfs", file));

  try {
    // Upload files
    await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    // Process uploaded files
    const response = await fetch("/process", {
      method: "POST",
    });

    const data = await response.json();

    if (data.success) {
      resultsDiv.innerHTML = "";
      data.results.forEach((item) => {
        const div = document.createElement("div");
        div.className = "extracted-text";
        div.innerHTML = `
          <h3>📄 ${item.filename}</h3>
          <pre>${JSON.stringify(item.structured_data, null, 2)}</pre>
        `;
        resultsDiv.appendChild(div);
      });
    } else {
      resultsDiv.innerHTML = `<p style="color:red;">❌ ${data.error}</p>`;
    }
  } catch (err) {
    console.error(err);
    resultsDiv.innerHTML =
      "<p style='color:red;'>⚠️ Error during processing</p>";
  }
});
