from weboter.public.model import Flow, Node
from .runtime import Runtime, DataContext
from .action_manager import action_manager
from .control_manager import control_manager
from .io_pipe_impl import IOPipeImpl
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

    def extract_outputs(self, node: Node, io: IOPipeImpl):
        pw_inst = io.outputs.get('__pw_inst__', None)
        if pw_inst:
            self.__ctx__['pw_inst'] = pw_inst
        
        browser = io.outputs.get('__browser__', None)
        if browser:
            self.__ctx__['browser'] = browser
        
        page = io.outputs.get('__page__', None)
        if page:
            self.__ctx__['current_page'] = page
            pages = self.__ctx__.get('pages', [])
            if page not in pages:
                pages.append(page)
                self.__ctx__['pages'] = pages

    def prepare_inputs(self, node: Node):
        inputs = {}
        # add static inputs
        for key, value in node.inputs.items():
            # resolve from runtime if it's a variable
            if isinstance(value, str) and DataContext.contains_var(value):
                value = self.runtime.get_value(value)
            inputs[key] = value
        self.__ctx__['inputs'] = inputs
    
    def prepare_action_io(self, node: Node) -> IOPipeImpl:
        inst = IOPipeImpl()
        inst.set_runtime(self.runtime)
        # add static inputs
        for key, value in node.inputs.items():
            # resolve from runtime if it's a variable
            if isinstance(value, str) and DataContext.contains_var(value):
                value = self.runtime.get_value(value)
            inst.inputs[key] = value
        # set pw instance, browser, page from context if available
        inst.pw_inst = self.__ctx__.get('pw_inst', None)
        inst.browser = self.__ctx__.get('browser', None)
        inst.page = self.__ctx__.get('current_page', None)
        return inst

    async def exec_action(self, action_name: str, io: IOPipeImpl):
        action : ActionBase = self.action_manager.get_action(action_name)
        if not action:
            raise ValueError(f"Action '{action_name}' not found")
        await action.execute(io)

    def prepare_control_io(self, node: Node) -> IOPipeImpl:
        inst = IOPipeImpl()
        inst.set_runtime(self.runtime)
        # add static params
        for key, value in node.params.items():
            inst.params[key] = value
        return inst

    async def exec_control(self, control_name: str, io: IOPipeImpl) -> str:
        control : ControlBase = self.control_manager.get_control(control_name)
        if not control:
            raise ValueError(f"Control '{control_name}' not found")
        next_node_id = await control.calc_next(io)
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
            action_io = self.prepare_action_io(node)
            await self.exec_action(node.action, action_io)
            self.extract_outputs(node, action_io)
        
        control_io = self.prepare_control_io(node)
        next_node_id = await self.exec_control(node.control, control_io)
        self.runtime.set_current_node(next_node_id)
    
    async def run(self):
        if not self.workflow:
            raise ValueError("No workflow loaded")
        if not self.workflow.start_node_id:
            raise ValueError("Workflow has no start node defined")
        
        while not self.runtime.finished():
            await self.step_one()
        