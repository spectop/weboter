import json
from pathlib import Path
from typing import Optional
from weboter.public.model import Node, Flow, NodeOutputConfig

class WorkflowIOError(Exception):
    """工作流读写操作异常基类"""
    pass

class WorkflowReader:

    @staticmethod
    def from_jstr(json_str: str) -> Flow:
        """从JSON字符串读取工作流数据"""
        try:
            data = json.loads(json_str)

            nodes = [
                Node(
                    node_id=node['id'],
                    name=node.get('name', ''),
                    description=node.get('description', ''),
                    action=node['action'],
                    inputs=node.get('inputs', {}),
                    outputs=[NodeOutputConfig(**output) for output in node.get('outputs', [])],
                    control=node.get('control', ''),
                    params=node.get('params', {}),
                    log=node.get('log', 'short')
                ) for node in data['nodes']
            ]

            sub_flows = [
                WorkflowReader.from_jstr(json.dumps(sub_flow_data)) for sub_flow_data in data.get('sub_flows', [])
            ]

            return Flow(flow_id=data['id'],
                        name=data['name'],
                        description=data.get('description', ''),
                        start_node_id=data.get('start_node_id', '__start__'),
                        nodes=nodes,
                        sub_flows=sub_flows,
                        log=data.get('log', 'short'))

        except json.JSONDecodeError as e:
            raise WorkflowIOError(f"JSON解析错误: {e}")
        except KeyError as e:
            raise WorkflowIOError(f"缺少必要字段: {e}")

    @staticmethod
    def from_json(file_path: Path) -> Flow:
        """从JSON文件读取工作流数据"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return WorkflowReader.from_jstr(json.dumps(data))
        except OSError as e:
            raise WorkflowIOError(f"文件读取失败: {e}")

class WorkflowWriter:
    @staticmethod
    def _flow_to_dict(flow: Flow) -> dict:
        """将 Flow 对象递归序列化为 JSON 兼容的字典"""
        return {
            "id": flow.flow_id,
            "name": flow.name,
            "description": flow.description,
            "start_node_id": flow.start_node_id,
            "nodes": [
                {
                    "id": node.node_id,
                    "name": node.name,
                    "description": node.description,
                    "action": node.action,
                    "inputs": node.inputs,
                    "outputs": [output.__dict__ for output in node.outputs],
                    "control": node.control,
                    "params": node.params,
                    "log": node.log,
                }
                for node in flow.nodes
            ],
            "sub_flows": [
                WorkflowWriter._flow_to_dict(sub_flow) for sub_flow in flow.sub_flows
            ],
            "log": flow.log,
        }

    @staticmethod
    def to_json(workflow: Flow, file_path: Path, indent: int = 2):
        """将工作流数据写入JSON文件"""
        data = WorkflowWriter._flow_to_dict(workflow)

        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)

        except OSError as e:
            raise WorkflowIOError(f"文件写入失败: {e}")