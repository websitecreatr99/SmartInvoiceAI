import type { Extraction, JobStatus, ResultItem } from "./types";

// Requests go through the /api rewrite in next.config.ts to the FastAPI app, unless NEXT_PUBLIC_API_URL
// points the browser straight at a deployed API (which must list this site in its CORS_ORIGINS).
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/$/, "");

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
// The user's own Gemini key goes in a header, only with the upload. Without one the API answers with sample data.
export async function createJob(
  files: File[],
  columns: string[],
  apiKey?: string,
): Promise<{ job_id: string; files: string[]; demo?: boolean }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (columns.length) form.append("columns", JSON.stringify(columns));
  const headers: Record<string, string> = apiKey?.trim() ? { "X-Gemini-Api-Key": apiKey.trim() } : {};
  const res = await fetch(`${API_URL}/jobs`, { method: "POST", body: form, headers });
  if (!res.ok) throw new Error(await errorMessage(res, "Upload failed"));
  return res.json();
}

/** Whether jobs without a key get sample data (the default) or use the server's own key. */
export async function getConfig(): Promise<{ demo_without_key: boolean }> {
  try {
    const res = await fetch(`${API_URL}/config`, { cache: "no-store" });
    if (res.ok) return await res.json();
  } catch {
    // Older API without /config, or asleep: assume sample data, the safe thing to promise.
  }
  return { demo_without_key: true };
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/jobs/${jobId}`, { cache: "no-store" });
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
