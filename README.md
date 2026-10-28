# InvoiceAI Frontend

Next.js UI for InvoiceAI. Drop in invoices, purchase orders or other business documents, optionally name the columns you want, and watch the extracted data arrive file by file. Every value links back to the document line it was read from.

## Running

The app proxies `/api/*` to the FastAPI app (`app.py` on the `fastapi` branch) at `http://127.0.0.1:5000`. Set `BACKEND_URL` to point elsewhere. Processing needs the rest of the stack (RabbitMQ and at least one worker): see the `fastapi` branch README.

With the backend running:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Checks: `npx tsc --noEmit`, `npm run lint`, `npm run build`.

## How it works

1. **Upload.** Pick or drop files. Accepted types mirror the API's `SUPPORTED_EXTENSIONS`: PDFs and images (`.png .jpg .jpeg .tif .tiff .bmp .webp`) are OCR'd; `.txt .csv .tsv .md .json .xml .html .htm .docx` are read as text. Duplicates (same name and size) are ignored.
2. **Columns (optional).** Add the fields you want as chips (Enter or comma adds one; pasting a list adds them all). Leave it empty to use the invoice schema (header + line items).
3. **Run.** The UI sends one `POST /jobs` (multipart `files`, plus `columns` as a JSON list), so every run is its own job and concurrent users never share uploads. It then polls `GET /jobs/{job_id}` every 1.5 s (for up to 15 minutes) and shows each file's result as soon as its worker finishes.
4. **Pipeline stepper.** Upload → OCR → AI → Done. The workers don't report the OCR → AI hand-off, so that step is estimated. Failed and partly failed runs show which step went wrong and how many documents were affected.
5. **Results.** Three views:
   - **Table**: one row per extracted row across all files, each value with its source page and line. Exports as CSV.
   - **Visual**: header and line-item cards (invoice schema only, so it's hidden when you name your own columns).
   - **JSON**: the raw output. Copy or download.

## Structure

- `src/app/page.tsx` – page layout, job submission and polling, failure summary
- `src/components/UploadPanel.tsx` – file picker and the columns input
- `src/components/Pipeline.tsx` – pipeline stepper, including failed and partly failed steps
- `src/components/ResultsPanel.tsx` – file selector, Table / Visual / JSON views, copy and download
- `src/components/FieldsTable.tsx` – the table view and its CSV export
- `src/components/DocumentView.tsx`, `JsonView.tsx` – visual and JSON views
- `src/lib/api.ts` – `POST /jobs` and `GET /jobs/{job_id}`, accepted file types, parsing of `structured_data`
- `src/lib/types.ts` – TypeScript mirror of the worker's Pydantic models (`src/common.py` on the `worker` branch) and the API's job status
