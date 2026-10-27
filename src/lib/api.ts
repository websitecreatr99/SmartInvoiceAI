import type { Extraction, ResultItem } from "./types";

// Requests go through the /api rewrite in next.config.ts to the Flask app.

export async function uploadFiles(files: File[]): Promise<string[]> {
  const form = new FormData();
  files.forEach((f) => form.append("pdfs", f));
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  const data = await res.json();
  return data.uploaded ?? [];
}

export async function processFiles(): Promise<ResultItem[]> {
  const res = await fetch("/api/process", { method: "POST" });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) throw new Error(data?.error ?? `Processing failed (${res.status})`);
  return data.results;
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
