# 📄 Invoice Extractor from Unstructured PDF Data

## InvoiceAI (PDF → Unstructured Data Extractor)

InvoiceAI is a lightweight tool that extracts **structured data** (headers, line items, schema) from **unstructured PDFs** using **OCR + AI**.  
It’s designed for **invoices, purchase orders, and other business documents** where accuracy and structure matter.

---

## 🚀 Getting Started

Follow these steps to set up and run the project locally.

### 1️⃣ Clone the Repository

git clone https://github.com/websitecreatr99/InvoiceAI.git
cd InvoiceAI

text

### 2️⃣ Install Dependencies
Make sure you have **Python 3.9+** installed. Then run:
pip install -r requirements.txt

text

### 3️⃣ Create Environment Variables
Create a `.env` file in the project root and add your **Gemini API Key**:
GEMINI_API_KEY=your_api_key_here

text
🔑 You can get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 4️⃣ Run the API
Start the FastAPI server on port 5000 with:
python app.py

text

---

## 🖥️ Usage
Interactive API docs are at [http://127.0.0.1:5000/docs](http://127.0.0.1:5000/docs). The UI lives on the `frontend` branch and talks to these endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/upload` | Save PDFs (multipart field `pdfs`) into `data/` |
| POST | `/delete` | Remove an uploaded PDF (`{"filename": "..."}`) |
| POST | `/process` | Run the pipeline and return structured JSON for each document |
| GET | `/health` | Liveness check |

---

## 📸 Preview Screenshot
<p align="center">
  <img src="assets/Screenshot 2025-08-28 125448.png" alt="InvoiceAI Preview" width="700">
</p>

---

## 📂 Project Structure
.
├── app.py # FastAPI app
├── ocr_pipeline.py # OCR + extraction pipeline
├── src/ # Pydantic schema, validation, logging
├── structured_output/ # Extracted JSON results
├── requirements.txt # Dependencies
└── .env # Your Gemini API key

text

---

## ✅ Features
- 📂 Upload multiple PDFs  
- ❌ Remove unwanted files before processing  
- 🧾 Extract structured JSON (headers, line items, schema)  
- 🎨 Simple, modern UI  

---

## 📜 License
This project is licensed under the **MIT License**.  
Free to use and modify.

---

