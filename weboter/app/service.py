import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from weboter.core.bootstrap import ensure_builtin_packages_registered
from weboter.core.engine.excutor import Executor
from weboter.core.workflow_io import WorkflowReader


@dataclass
class WorkflowResolution:
    source_path: Path
    managed_path: Path | None = None


class WorkflowService:
    def __init__(self, workspace_root: Path | None = None):
        default_root = Path(os.environ.get("WEBOTER_HOME", Path(__file__).resolve().parents[2]))
        self.workspace_root = (workspace_root or default_root).resolve()
        self.data_root = self.workspace_root / ".weboter"
        self.workflow_store = self.data_root / "workflows"
        self.workflow_store.mkdir(parents=True, exist_ok=True)

    def upload_workflow(self, source: Path) -> WorkflowResolution:
        source_path = source.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {source_path}")

        destination = self.workflow_store / source_path.name
        if source_path != destination:
            shutil.copy2(source_path, destination)
        return WorkflowResolution(source_path=destination, managed_path=destination)

    def resolve_from_directory(self, directory: Path, workflow_name: str | None = None) -> WorkflowResolution:
        directory_path = directory.expanduser().resolve()
        if not directory_path.is_dir():
            raise NotADirectoryError(f"Workflow directory not found: {directory_path}")

        if workflow_name:
            candidates = [
                directory_path / workflow_name,
                directory_path / f"{workflow_name}.json",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return WorkflowResolution(source_path=candidate)
            raise FileNotFoundError(f"Workflow '{workflow_name}' not found in: {directory_path}")

        json_files = sorted(directory_path.glob("*.json"))
        if len(json_files) != 1:
            raise ValueError(
                "Directory mode requires exactly one workflow file, or use --name to choose one"
            )
        return WorkflowResolution(source_path=json_files[0])

    def list_directory_workflows(self, directory: Path) -> list[Path]:
        directory_path = directory.expanduser().resolve()
        if not directory_path.is_dir():
            raise NotADirectoryError(f"Workflow directory not found: {directory_path}")
        return sorted(directory_path.glob("*.json"))

    def run_workflow(self, workflow_path: Path) -> Path:
        ensure_builtin_packages_registered()
        flow = WorkflowReader.from_json(workflow_path)
        executor = Executor()
        executor.load_workflow(flow)
        asyncio.run(executor.run())
        return workflow_path