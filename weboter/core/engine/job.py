from dataclasses import dataclass
from enum import Enum

class JobStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class Job:
    status: JobStatus
    flow_id: str # 所属 flow id
    node_id: str # 需要处理该 job 的 node id
    link_id: str # 控制流向此 node 的 link id
    input: dict # 将是处理完给到 action 的最终输入
    output: dict # action 处理完后的输出