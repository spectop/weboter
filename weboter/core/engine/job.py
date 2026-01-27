from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from weboter.core.workflow_io import WorkflowReader
from weboter.public.model.workflow import Workflow, resolve_env_vars

class JobStatus(Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class NodeExecutionState:
    """表示节点执行状态"""
    node_id: str
    status: JobStatus
    inputs: Dict[str, str]
    outputs: Optional[Dict[str, str]] = None

@dataclass
class Job:
    """表示工作流执行任务"""
    workflow: Workflow
    status: JobStatus = JobStatus.PENDING
    current_node_index: int = 0
    node_states: List[NodeExecutionState] = field(default_factory=list)

    @classmethod
    def from_file(cls, workflow_path: Path):
        """从工作流文件创建Job实例"""
        workflow = WorkflowReader.from_json(workflow_path)
        return cls(workflow=workflow)

    def execute_current_node(self, runtime_context: Dict):
        """执行当前节点"""
        if self.current_node_index >= len(self.workflow.nodes):
            return

        current_node = self.workflow.nodes[self.current_node_index]

        # 创建节点状态
        node_state = NodeExecutionState(
            node_id=current_node.id,
            status=JobStatus.RUNNING,
            inputs=resolve_env_vars(current_node.inputs)
        )
        self.node_states.append(node_state)

        # 执行逻辑（示例）
        # TODO: 集成ActionManager
        print(f"执行节点: {current_node.id} ({current_node.action})")
        print(f"输入: {node_state.inputs}")

        # 成功执行后更新状态
        node_state.outputs = {"status": "success"}
        node_state.status = JobStatus.COMPLETED

        # 移动到下一个节点
        self.current_node_index += 1
        if self.current_node_index >= len(self.workflow.nodes):
            self.status = JobStatus.COMPLETED

    def start(self):
        """开始工作流执行"""
        self.status = JobStatus.RUNNING