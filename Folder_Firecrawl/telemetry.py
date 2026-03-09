import json
import time
from datetime import datetime
from typing import Any


class TraceLogger:
    """
    Simple execution trace logger for agent runs.

    Tracks:
    - steps executed
    - tool usage
    - durations
    - errors
    - results
    """

    def __init__(self, instruction: str, mode: str):
        self.run_id = self._generate_run_id()
        self.instruction = instruction
        self.mode = mode
        self.created_at = self.now_iso()
        self.steps = []

    def _generate_run_id(self) -> str:
        return f"{int(time.time() * 1000)}"

    def now_iso(self) -> str:
        return datetime.utcnow().isoformat()

    def log_step(
        self,
        step_number: int,
        tool: str,
        args: dict,
        start_perf: float,
        start_time_iso: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ):
        duration = round(time.perf_counter() - start_perf, 4)

        preview = None
        if result is not None:
            preview = str(result)
            if len(preview) > 500:
                preview = preview[:500] + "..."

        self.steps.append(
            {
                "step_number": step_number,
                "tool": tool,
                "args": args,
                "started_at": start_time_iso,
                "finished_at": self.now_iso(),
                "duration_seconds": duration,
                "status": status,
                "error": error,
                "result_preview": preview,
            }
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "instruction": self.instruction,
            "created_at": self.created_at,
            "steps": self.steps,
        }

    def save(self, path: str = "latest_run_trace.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)