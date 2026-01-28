from weboter.public.model import *

class DataContext:

    @classmethod
    def contains_var(cls, key: str) -> bool:
        """
        检查输入的变量名是否是可用的变量：形如 $env{name}
        """
        if not key.startswith('$'):
            return False
        if '{' not in key or '}' not in key:
            return False
        return True
    
    def __init__(self):
        self.data = {
            'env': {},
            'global': {},
            'flow': {},
            'prev_outputs': {},
            'cur_outputs': {}
        }

    def get_data(self, key: str):
        """
        根据变量名获取对应的值
        变量名形如 $env{name}、$global{name}、$flow{name}、$prev_outputs{name}、$cur_outputs{name}
        """
        if not self.contains_var(key):
            raise KeyError(f"输入的变量名格式不正确: {key}")
        
        prefix_end = key.index('{')
        suffix_start = key.index('}')
        prefix = key[1:prefix_end]
        var_name = key[prefix_end + 1:suffix_start]

        if prefix not in self.data:
            raise KeyError(f"未知的变量前缀: {prefix}")

        # name 允许 aa.bb.cc 的形式
        collection = self.data[prefix]
        parts = var_name.split('.')
        value = collection
        for part in parts:
            if part not in value:
                raise KeyError(f"变量未定义: {key}")
            value = value[part]
        return value

    def set_data(self, key: str, value):
        """
        根据变量名设置对应的值
        变量名形如 $env{name}、$global{name}、$flow{name}、$prev_outputs{name}、$cur_outputs{name}
        """
        if not self.contains_var(key):
            raise KeyError(f"输入的变量名格式不正确: {key}")
        
        prefix_end = key.index('{')
        suffix_start = key.index('}')
        prefix = key[1:prefix_end]
        var_name = key[prefix_end + 1:suffix_start]

        if prefix not in self.data:
            raise KeyError(f"未知的变量前缀: {prefix}")

        # name 允许 aa.bb.cc 的形式
        collection = self.data[prefix]
        parts = var_name.split('.')
        current = collection
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

class Runtime:
    
    def __init__(self):
        self.flow: Flow | None = None
        self.nodes = {}
        self.data_context = DataContext()
        self.__load_environment()
        self.current_node_id: str | None = None
    
    def finished(self) -> bool:
        return self.current_node_id == '__end__'
    
    def init_with_flow(self, flow: Flow):
        self.flow = flow
        self.nodes = {node.node_id: node for node in flow.nodes}
        self.current_node_id = flow.start_node_id if flow.start_node_id else None

    def get_value(self, key: str):
        return self.data_context.get_data(key)
    
    def set_value(self, key: str, value):
        self.data_context.set_data(key, value)

    def set_current_node(self, node_id: str):
        if node_id not in self.nodes:
            raise KeyError(f"节点ID未找到: {node_id}")
        self.current_node_id = node_id
    
    def get_node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise KeyError(f"节点ID未找到: {node_id}")
        return self.nodes[node_id]

    def __load_environment(self):
        # 加载环境变量到数据上下文
        import os
        for key, value in os.environ.items():
            self.data_context.set_data(f"$env{{{key}}}", value)
    