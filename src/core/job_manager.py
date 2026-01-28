from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Job:
    job_id: str
    q: "queue.Queue[str]"
    cancel_event: threading.Event
    status: str  # queued|running|done|error|cancelling|cancelled
    output: str


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str) -> Job:
        with self._lock:
            job = Job(
                job_id=job_id,
                q=queue.Queue(),
                cancel_event=threading.Event(),
                status="queued",
                output="",
            )
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def log(self, job_id: str, msg: str) -> None:
        job = self.get(job_id)
        if job:
            job.q.put(msg)

    def set_status(self, job_id: str, status: str) -> None:
        job = self.get(job_id)
        if job:
            job.status = status

    def set_output(self, job_id: str, output: str) -> None:
        job = self.get(job_id)
        if job:
            job.output = output

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False

        # kalau sudah selesai/error, nggak usah cancel
        if job.status in ("done", "error", "cancelled"):
            return False

        job.status = "cancelling"
        job.cancel_event.set()
        job.q.put("[CANCEL] Cancel requested by user.")
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        job = self.get(job_id)
        return bool(job and job.cancel_event.is_set())
