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

    def create(self, filenames: List[str]) -> str:
        job_id = str(uuid.uuid4())
        path = self._dir(job_id)
        os.makedirs(os.path.join(path, "results"))
        with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"job_id": job_id, "files": filenames, "created_at": time.time()}, f)
        return job_id

    def delete(self, job_id: str):
        path = self._dir(job_id)
        if path:
            shutil.rmtree(path, ignore_errors=True)

    def exists(self, job_id: str) -> bool:
        path = self._dir(job_id)
        return bool(path) and os.path.isfile(os.path.join(path, "meta.json"))

    def save_result(self, result: dict) -> bool:
        """Record one worker result. Returns False for unknown jobs."""
        job_id = result.get("job_id")
        if not self.exists(job_id):
            return False
        stem = os.path.splitext(os.path.basename(result.get("filename") or ""))[0]
        if not stem:
            return False

        if result.get("ok"):
            name, content = f"{stem}.json", json.dumps(result.get("structured_data"), ensure_ascii=False, indent=4)
        else:
            name, content = f"{stem}.error", str(result.get("error") or "Unknown error")

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
            files = json.load(f)["files"]

        results = []
        for pdf in files:
            stem = os.path.splitext(pdf)[0]
            ok_path = os.path.join(path, "results", f"{stem}.json")
            err_path = os.path.join(path, "results", f"{stem}.error")
            if os.path.exists(ok_path):
                with open(ok_path, encoding="utf-8") as f:
                    results.append({"filename": f"{stem}.json", "structured_data": json.load(f)})
            elif os.path.exists(err_path):
                with open(err_path, encoding="utf-8") as f:
                    results.append({"filename": f"{stem}.json", "error": f.read()})

        done, total = len(results), len(files)
        status = "done" if done == total else "processing" if done else "queued"
        return {"job_id": job_id, "status": status, "progress": {"done": done, "total": total}, "results": results}
