import json
import os
import subprocess
import sys
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

UPLOAD_FOLDER = "data"
STRUCTURED_OUTPUT_FOLDER = "structured_output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STRUCTURED_OUTPUT_FOLDER, exist_ok=True)

app = FastAPI(title="InvoiceAI", description="Extract structured data from unstructured invoice PDFs.")

# The Next.js frontend proxies /api/* here, but allow direct calls from its dev server too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeleteRequest(BaseModel):
    filename: str


def safe_path(filename: str) -> str:
    """Keep client-supplied names inside the upload folder."""
    name = os.path.basename(filename or "")
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return os.path.join(UPLOAD_FOLDER, name)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
def upload_files(pdfs: List[UploadFile] = File(...)):
    """Save uploaded PDFs into data/ folder"""
    saved_files = []

    for file in pdfs:
        save_path = safe_path(file.filename)
        with open(save_path, "wb") as f:
            f.write(file.file.read())
        saved_files.append(os.path.basename(save_path))

    return {"success": True, "uploaded": saved_files}


@app.post("/delete")
def delete_file(body: DeleteRequest):
    """Delete a PDF before processing if user cancels"""
    file_path = safe_path(body.filename)

    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"success": False, "error": "File not found"})

    os.remove(file_path)
    return {"success": True, "deleted": os.path.basename(file_path)}


@app.post("/process")
def process_files():
    """Run OCR pipeline on all uploaded PDFs and return structured JSONs"""
    results = []

    # Sync endpoint, so FastAPI runs this blocking call in its threadpool.
    try:
        subprocess.run([sys.executable, "ocr_pipeline.py"], check=True)
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"OCR pipeline failed: {str(e)}"}

    for filename in os.listdir(STRUCTURED_OUTPUT_FOLDER):
        if filename.endswith(".json"):
            file_path = os.path.join(STRUCTURED_OUTPUT_FOLDER, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({"filename": filename, "structured_data": data})
            except Exception as e:
                results.append({"filename": filename, "error": str(e)})

    return {"success": True, "results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
