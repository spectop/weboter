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
                return None
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

    def store_outputs(self, outputs: dict, out_cfgs: list[NodeOutputConfig] | None = None):
        """
        存储当前节点的输出到数据上下文中，供后续节点使用
        """
        self.data['cur_outputs'] = outputs
        if not out_cfgs:
            return
        # 用户声明了输出转储配置，根据配置将输出转储到指定位置
        for cfg in out_cfgs:
            if cfg.src not in outputs:
                continue
            value = outputs[cfg.src]
            # 转换类型
            if cfg.cvt:
                try:
                    if cfg.cvt == "int":
                        value = int(value)
                    elif cfg.cvt == "float":
                        value = float(value)
                    elif cfg.cvt == "str":
                        value = str(value)
                    elif cfg.cvt == "bool":
                        value = bool(value)
                    else:
                        raise ValueError(f"Unsupported conversion type: {cfg.cvt}")
                except Exception as e:
                    raise ValueError(f"Failed to convert output '{cfg.src}' to type '{cfg.cvt}': {e}")
            # 存储到指定位置
            name = cfg.name if cfg.name else cfg.src
            if cfg.pos == "flow":
                # flow 表示存储到当前的工作流中，如果存在工作流嵌套，则只能在当前工作流内访问
                self.set_data(f"$flow{{{name}}}", value)
            elif cfg.pos == "global":
                # global 表示存储到全局中，所有工作流都可以访问
                self.set_data(f"$global{{{name}}}", value)
            else:
                raise ValueError(f"Unsupported output position: {cfg.pos}")
    
    def switch_outputs(self):
        """
        切换节点时调用，将当前输出切换到前一个输出，并清空当前输出
        """
        self.data['prev_outputs'] = self.data['cur_outputs']
        self.data['cur_outputs'] = {}

    def copy_data(self, other: 'DataContext', prefix: str = ""):
        """
        将另一个数据上下文的数据复制到当前上下文中，常用于子流程调用
        如 prefix="global"，则会将另一个上下文中 global 部分的数据复制到当前上下文的 global 部分
        """
        prefix_vec = prefix.split('.') if prefix else []
        # todo: 目前仅支持一层前缀，后续可以改进为支持多层前缀
        if len(prefix_vec) < 1:
            # 没有前缀，复制全部数据
            self.data = other.data
        else:
            # 仅复制指定前缀的数据
            prefix_key = prefix_vec[0]
            if prefix_key not in other.data:
                return
            self.data[prefix_key] = other.data[prefix_key]


class Runtime:
    
    def __init__(self):
        self.flow: Flow | None = None
        self.nodes = {}
        self.data_context = DataContext()
        self.__load_environment()
        self.current_node_id: str | None = None
    
    def finished(self) -> bool:
        return self.current_node_id == '__end__' or self.current_node_id == '__exit__'
    
    def should_exit(self) -> bool:
        return self.current_node_id == '__exit__'
    
    def init_with_flow(self, flow: Flow):
        self.flow = flow
        self.nodes = {node.node_id: node for node in flow.nodes}
        self.current_node_id = flow.start_node_id if flow.start_node_id else None

    def get_value(self, key: str):
        return self.data_context.get_data(key)
    
    def set_value(self, key: str, value):
        self.data_context.set_data(key, value)
    
    def store_outputs(self, outputs: dict, out_cfgs: list[NodeOutputConfig] | None = None):
        self.data_context.store_outputs(outputs, out_cfgs)

    def switch_outputs(self):
        self.data_context.switch_outputs()

    def set_current_node(self, node_id: str):
        if node_id == '__end__':
            self.current_node_id = node_id
            return
        if node_id == '__exit__':
            self.current_node_id = node_id
            return
        if node_id not in self.nodes:
            raise KeyError(f"节点ID未找到: {node_id}")
        self.current_node_id = node_id
    
    def get_node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise KeyError(f"节点ID未找到: {node_id}")
        return self.nodes[node_id]
    
    def get_node_name(self, node_id: str) -> str:
        if node_id not in self.nodes:
            return node_id
        return self.nodes[node_id].name

    def copy_data(self, other: 'Runtime', prefix: str = ""):
        self.data_context.copy_data(other.data_context, prefix)

    def __load_environment(self):
        # 加载环境变量到数据上下文
        import os
        for key, value in os.environ.items():
            self.data_context.set_data(f"$env{{{key}}}", value)
    