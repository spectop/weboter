from weboter.public.model import Flow, Node
from .runtime import Runtime
from .action_manager import action_manager
from .control_manager import control_manager
from weboter.public.contracts import *

class Scheduler:
    
    def __init__(self):
        self.runtime: Runtime = Runtime()
        self.workflow: Flow | None = None
        self.action_manager = action_manager
        self.control_manager = control_manager
        self.__ctx__ = {}

    def load_workflow(self, flow: Flow):
        self.workflow = flow
        self.runtime.init_with_flow(flow)

    def prepare_inputs(self, node: Node):
        inputs = {}
        # add static inputs
        for key, value in node.inputs.items():
            inputs[key] = value
        self.__ctx__['inputs'] = inputs

    async def exec_action(self, action_name: str):
        action : ActionBase = self.action_manager.get_action(action_name)
        if not action:
            raise ValueError(f"Action '{action_name}' not found")
        await action.execute(self.__ctx__)

    def prepare_params(self, node: Node):
        params = {}
        # add static params
        for key, value in node.params.items():
            params[key] = value
        self.__ctx__['params'] = params

    async def exec_control(self, control_name: str):
        control : ControlBase = self.control_manager.get_control(control_name)
        if not control:
            raise ValueError(f"Control '{control_name}' not found")
        next_node_id = await control.calc_next(self.__ctx__)
        return next_node_id
    
    async def step_one(self):
        if self.runtime.finished():
            return
        
        node_id = self.runtime.current_node_id
        if not node_id:
            raise ValueError("No current node to execute")
        node: Node = self.runtime.get_node(node_id)
        if not node:
            raise ValueError(f"Node '{node_id}' not found")
        if not node.control:
            raise ValueError(f"Node '{node_id}' has no control to execute")
        
        if node.action:
            self.prepare_inputs(node)
            await self.exec_action(node.action)
        
        self.prepare_params(node)
        next_node_id = await self.exec_control(node.control)
        self.runtime.set_current_node(next_node_id)
    
    async def run(self):
        if not self.workflow:
            raise ValueError("No workflow loaded")
        if not self.workflow.start_node_id:
            raise ValueError("Workflow has no start node defined")
        
        while not self.runtime.finished():
            await self.step_one()
        