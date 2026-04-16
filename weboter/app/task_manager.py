from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any
from uuid import uuid4

from weboter.app.service import WorkflowService


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SUCCEEDED = "succeeded"
TASK_STATUS_FAILED = "failed"
TERMINAL_TASK_STATUSES = {TASK_STATUS_SUCCEEDED, TASK_STATUS_FAILED}


@dataclass
class TaskRecord:
    task_id: str
    workflow_path: str
    workflow_name: str
    status: str
    trigger: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    log_path: str | None = None
    error: str | None = None


class TaskManager:
    def __init__(
        self,
        workflow_service: WorkflowService,
        system_logger: logging.Logger,
        max_workers: int = 2,
    ):
        self.workflow_service = workflow_service
        self.system_logger = system_logger
        self.task_root = self.workflow_service.data_root / "tasks"
        self.task_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="weboter-task")

    def submit(self, workflow_path: Path, trigger: str) -> TaskRecord:
        task_id = uuid4().hex[:12]
        log_path = self.task_root / f"{task_id}.log"
        record = TaskRecord(
            task_id=task_id,
            workflow_path=str(workflow_path),
            workflow_name=workflow_path.stem,
            status=TASK_STATUS_QUEUED,
            trigger=trigger,
            created_at=self._now(),
            log_path=str(log_path),
        )
        self._save(record)
        self.system_logger.info("任务已创建: %s -> %s", task_id, workflow_path)
        self._executor.submit(self._run_task, task_id)
        return record

    def list_tasks(self, limit: int = 20) -> list[TaskRecord]:
        task_files = sorted(self.task_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        records = [self._load_from_file(task_file) for task_file in task_files[:limit]]
        return records

    def get_task(self, task_id: str) -> TaskRecord:
        task_file = self._resolve_task_file(task_id)
        return self._load_from_file(task_file)

    def read_task_log(self, task_id: str, lines: int = 200) -> dict[str, Any]:
        record = self.get_task(task_id)
        log_path = Path(record.log_path or "")
        if not log_path.is_file():
            return {"task_id": task_id, "log_path": str(log_path), "content": ""}
        return {
            "task_id": task_id,
            "log_path": str(log_path),
            "content": self._tail_text(log_path, lines),
        }

    def wait_for_task(self, task_id: str, timeout: float | None = None, interval: float = 0.5) -> TaskRecord:
        deadline = None if timeout is None else time.time() + timeout
        while True:
            record = self.get_task(task_id)
            if record.status in TERMINAL_TASK_STATUSES:
                return record
            if deadline is not None and time.time() >= deadline:
                raise TimeoutError(f"Wait task timeout: {task_id}")
            time.sleep(interval)

    def _run_task(self, task_id: str) -> None:
        record = self.get_task(task_id)
        logger = logging.getLogger(f"weboter.task.{task_id}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(record.log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        try:
            record.status = TASK_STATUS_RUNNING
            record.started_at = self._now()
            self._save(record)
            self.system_logger.info("任务开始执行: %s", task_id)
            self.workflow_service.run_workflow(Path(record.workflow_path), logger=logger)
            record.status = TASK_STATUS_SUCCEEDED
            record.finished_at = self._now()
            self._save(record)
            self.system_logger.info("任务执行成功: %s", task_id)
        except Exception as exc:
            logger.exception("任务执行失败")
            record.status = TASK_STATUS_FAILED
            record.error = str(exc)
            record.finished_at = self._now()
            self._save(record)
            self.system_logger.exception("任务执行失败: %s", task_id)
        finally:
            logger.removeHandler(file_handler)
            file_handler.close()

    def _task_file(self, task_id: str) -> Path:
        return self.task_root / f"{task_id}.json"

    def _resolve_task_file(self, task_id: str) -> Path:
        exact_match = self._task_file(task_id)
        if exact_match.is_file():
            return exact_match

        matches = sorted(self.task_root.glob(f"{task_id}*.json"))
        if not matches:
            raise FileNotFoundError(f"Task not found: {task_id}")
        if len(matches) > 1:
            candidates = ", ".join(path.stem for path in matches[:5])
            raise ValueError(f"Task id prefix is ambiguous: {task_id} -> {candidates}")
        return matches[0]

    def _save(self, record: TaskRecord) -> None:
        with self._lock:
            with open(self._task_file(record.task_id), "w", encoding="utf-8") as file_obj:
                json.dump(asdict(record), file_obj, ensure_ascii=False, indent=2)

    def _load_from_file(self, task_file: Path) -> TaskRecord:
        with open(task_file, "r", encoding="utf-8") as file_obj:
            return TaskRecord(**json.load(file_obj))

    @staticmethod
    def _tail_text(path: Path, lines: int) -> str:
        content = path.read_text(encoding="utf-8")
        return "\n".join(content.splitlines()[-lines:])

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")