from weboter.public.contracts import IOPipe
from .runtime import Runtime

class IOPipeImpl(IOPipe):

    def __init__(self):
        super().__init__()
        self.__runtime: Runtime | None = None

    def set_runtime(self, runtime: Runtime):
        self.__runtime = runtime

    @property
    def cur_node(self) -> str:
        """Get the current node ID."""
        if not self.__runtime:
            raise ValueError("Runtime is not set in IOPipeImpl.")
        return self.__runtime.current_node_id or ""

    @property
    def flow_data(self) -> dict:
        """Get the flow-level data storage."""
        if not self.__runtime:
            raise ValueError("Runtime is not set in IOPipeImpl.")
        return self.__runtime.data_context.data.get('flow', {})
    
    @flow_data.setter
    def flow_data(self, value: dict):
        if not self.__runtime:
            raise ValueError("Runtime is not set in IOPipeImpl.")
        self.__runtime.data_context.data['flow'] = value