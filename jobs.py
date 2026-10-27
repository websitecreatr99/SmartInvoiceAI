import os

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")


def job_dir(job_id: str) -> str:
    return os.path.join(STORAGE_DIR, "jobs", job_id)


def input_dir(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "input")


def ocr_dir(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "ocr")


def results_dir(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "results")
