# InvoiceAI Frontend

Next.js UI for InvoiceAI. Upload PDFs, run the OCR + LLM pipeline, and browse the extracted headers and line items visually or as JSON.

## Running

The app proxies `/api/*` to the Flask backend (`app.py`) on `http://127.0.0.1:5000`. Set `BACKEND_URL` to point elsewhere.

With the backend running:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Structure

- `src/app/page.tsx` – page layout and upload → process flow
- `src/components/` – upload panel, pipeline stepper, results (visual + JSON views)
- `src/lib/api.ts` – calls to the Flask `/upload` and `/process` endpoints
- `src/lib/types.ts` – TypeScript mirror of the Pydantic models in `src/common.py`
