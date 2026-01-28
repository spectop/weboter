import json
from pathlib import Path
from typing import Optional
from weboter.public.model import Node, Flow

class WorkflowIOError(Exception):
    """工作流读写操作异常基类"""
    pass

class WorkflowReader:
    @staticmethod
    def from_json(file_path: Path) -> Flow:
        """从JSON文件读取工作流数据"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            nodes = [
                Node(
                    node_id=node['id'],
                    name=node.get('name', ''),
                    description=node.get('description', ''),
                    action=node['action'],
                    inputs=node.get('inputs', {}),
                    control=node.get('control', ''),
                    params=node.get('params', {})
                ) for node in data['nodes']
            ]

            return Flow(flow_id=data['id'],
                        name=data['name'],
                        description=data.get('description', ''),
                        start_node_id=data.get('start_node_id'),
                        nodes=nodes)

        except FileNotFoundError:
            raise WorkflowIOError(f"文件未找到: {file_path}")
        except json.JSONDecodeError as e:
            raise WorkflowIOError(f"JSON解析错误: {e}")
        except KeyError as e:
            raise WorkflowIOError(f"缺少必要字段: {e}")

class WorkflowWriter:
    @staticmethod
    def to_json(workflow: Flow, file_path: Path, indent: int = 2):
        """将工作流数据写入JSON文件"""
        data = {
            "id": workflow.flow_id,
            "name": workflow.name,
            "description": workflow.description,
            "start_node_id": workflow.start_node_id,
            "nodes": [
                {
                    "id": node.node_id,
                    "action": node.action,
                    "inputs": node.inputs,  # 使用'inputs'键保持兼容
                    "control": node.control,
                    "params": node.params
                } for node in workflow.nodes
            ]
        }

        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)

        except OSError as e:
            raise WorkflowIOError(f"文件写入失败: {e}")