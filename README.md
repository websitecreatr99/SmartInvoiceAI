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

### 4️⃣ Run the App
Start the application with:
python app.py

text

---

## 🖥️ Usage
1. Open your browser and go to: [http://127.0.0.1:5000/](http://127.0.0.1:5000/)  
2. Upload one or more **PDF files**  
3. Process them and view **extracted JSON schema** in the UI  
4. Cancel/remove unwanted files before processing  

---

## 📸 Preview Screenshot
<p align="center">
  <img src="assets/Screenshot 2025-08-28 125448.png" alt="InvoiceAI Preview" width="700">
</p>

---

## 📂 Project Structure
.
├── app.py # Main Flask app
├── ocr_pipeline.py # OCR + extraction pipeline
├── static/ # CSS & JS files
├── templates/ # HTML frontend
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

