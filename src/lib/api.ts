import type { Extraction, JobStatus, ResultItem } from "./types";

// Requests go through the /api rewrite in next.config.ts to the FastAPI app.

/** Mirrors SUPPORTED_EXTENSIONS in the API: PDFs and images are OCR'd, the rest read as text. */
export const ACCEPTED_EXTENSIONS = [
  ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
  ".txt", ".csv", ".tsv", ".md", ".json", ".xml", ".html", ".htm", ".docx",
];

export function isSupported(file: File) {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

async function errorMessage(res: Response, fallback: string) {
  const data = await res.json().catch(() => null);
  return typeof data?.detail === "string" ? data.detail : `${fallback} (${res.status})`;
}

/** Queue a job of its own for these files, so concurrent users never share uploads. */
export async function createJob(files: File[], columns: string[]): Promise<{ job_id: string; files: string[] }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (columns.length) form.append("columns", JSON.stringify(columns));
  const res = await fetch("/api/jobs", { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res, "Upload failed"));
  return res.json();
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await errorMessage(res, "Status check failed"));
  return res.json();
}

/** DataExtractionHandler.validate_data returns a JSON string, so saved files may be double-encoded. */
export function parseExtraction(item: ResultItem): Extraction | null {
  let data: unknown = item.structured_data;
  try {
    while (typeof data === "string") data = JSON.parse(data);
  } catch {
    return null;
  }
  if (data && typeof data === "object" && Array.isArray((data as Extraction).extraction)) {
    return data as Extraction;
  }
  return null;
}
