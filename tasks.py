import json
import os

from celery_app import celery_app
from jobs import input_dir, ocr_dir, results_dir
from src.common import DataExtractionHandler
from src.logger_config import setup_logger

logger = setup_logger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


@celery_app.task(bind=True, name="tasks.process_job")
def process_job(self, job_id: str):
    """OCR every PDF in a job, extract structured data with the LLM, and save one JSON per PDF."""
    # Heavy imports (PaddleOCR, LangChain) load only in worker processes.
    from ocr_pipeline import ModelHandler, extract_text_from_pdf

    pdfs = sorted(f for f in os.listdir(input_dir(job_id)) if f.lower().endswith(".pdf"))
    os.makedirs(results_dir(job_id), exist_ok=True)

    model_handler = ModelHandler(GEMINI_MODEL)
    handler = DataExtractionHandler()
    summary = []

    for i, pdf in enumerate(pdfs):
        self.update_state(state="PROGRESS", meta={"done": i, "total": len(pdfs), "current": pdf})
        name = os.path.splitext(pdf)[0]
        try:
            ocr_lines = extract_text_from_pdf(os.path.join(input_dir(job_id), pdf), ocr_dir(job_id))
            ocr_text = "\n".join(f"{text} (conf: {conf})" for text, conf in ocr_lines)

            extracted = model_handler.extract_with_gemini(ocr_text=ocr_text)
            if not extracted:
                raise RuntimeError("LLM extraction returned no data")

            validated = handler.validate_data(extracted)
            if validated.startswith("Validation Error"):
                raise RuntimeError(validated)

            handler.save_json_to_file(validated, os.path.join(results_dir(job_id), f"{name}.json"))
            summary.append({"filename": f"{name}.json", "ok": True})
        except Exception as e:
            logger.error(f"Job {job_id}: failed on {pdf}: {e}", exc_info=True)
            with open(os.path.join(results_dir(job_id), f"{name}.error"), "w", encoding="utf-8") as f:
                f.write(str(e))
            summary.append({"filename": f"{name}.json", "ok": False, "error": str(e)})

    return {"done": len(pdfs), "total": len(pdfs), "files": summary}
