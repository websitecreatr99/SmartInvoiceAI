import json
import os
import shutil
import time
import uuid
from typing import List, Optional


class JobStore:
    """Job state on disk: storage/jobs/<job_id>/{meta.json, results/}.

    Run several API replicas against one shared volume and any of them can
    answer status requests or record results coming back from the workers.
    """

    def __init__(self, root: str):
        self.root = root

    def _dir(self, job_id: str) -> Optional[str]:
        try:
            uuid.UUID(str(job_id))
        except ValueError:
            return None
        return os.path.join(self.root, "jobs", str(job_id))

    def create(self, filenames: List[str], columns: Optional[List[str]] = None) -> str:
        job_id = str(uuid.uuid4())
        path = self._dir(job_id)
        os.makedirs(os.path.join(path, "results"))
        with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"job_id": job_id, "files": filenames, "columns": columns or [], "created_at": time.time()}, f)
        return job_id

    def delete(self, job_id: str):
        path = self._dir(job_id)
        if path:
            shutil.rmtree(path, ignore_errors=True)

    def exists(self, job_id: str) -> bool:
        path = self._dir(job_id)
        return bool(path) and os.path.isfile(os.path.join(path, "meta.json"))

    def created_at(self, job_id: str) -> float:
        with open(os.path.join(self._dir(job_id), "meta.json"), encoding="utf-8") as f:
            return json.load(f)["created_at"]

    def save_result(self, result: dict) -> bool:
        """Record one worker result. Returns False for unknown jobs."""
        job_id = result.get("job_id")
        if not self.exists(job_id):
            return False
        # Full filename, not the stem: a.pdf and a.png in one job are different documents.
        filename = os.path.basename(result.get("filename") or "")
        if not filename:
            return False

        if result.get("ok"):
            data = {key: result[key] for key in ("structured_data", "fields") if key in result}
            name, content = f"{filename}.json", json.dumps(data, ensure_ascii=False, indent=4)
        else:
            name, content = f"{filename}.error", str(result.get("error") or "Unknown error")

        # Write-then-rename so readers never see a half-written result.
        folder = os.path.join(self._dir(job_id), "results")
        tmp = os.path.join(folder, f".{name}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, os.path.join(folder, name))
        return True

    def status(self, job_id: str) -> Optional[dict]:
        if not self.exists(job_id):
            return None
        path = self._dir(job_id)
        with open(os.path.join(path, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        files = meta["files"]

        # Results come back in upload order as each file finishes, so clients can append them as they arrive.
        results = []
        for name in files:
            ok_path = os.path.join(path, "results", f"{name}.json")
            err_path = os.path.join(path, "results", f"{name}.error")
            if os.path.exists(ok_path):
                with open(ok_path, encoding="utf-8") as f:
                    results.append({"filename": name, **json.load(f)})
            elif os.path.exists(err_path):
                with open(err_path, encoding="utf-8") as f:
                    results.append({"filename": name, "error": f.read()})

        done, total = len(results), len(files)
        status = "done" if done == total else "processing" if done else "queued"
        return {
            "job_id": job_id,
            "status": status,
            "progress": {"done": done, "total": total},
            "files": files,
            "columns": meta.get("columns", []),
            "results": results,
        }
