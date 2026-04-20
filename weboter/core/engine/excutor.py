import logging

from .runtime import Runtime, DataContext
from .action_manager import action_manager
from .control_manager import control_manager
from .io_pipe_impl import IOPipeImpl
from weboter.public.contracts import *
from weboter.public.model import *


class Executor:
    
    def __init__(self, **kwargs):
        self.runtime: Runtime = Runtime(managed_env=kwargs.get("managed_env"))
        self.workflow: Flow | None = None
        self.action_manager = action_manager
        self.control_manager = control_manager
        
        logger = kwargs.get("logger", None)
        self.hooks = kwargs.get("hooks")
        if logger and isinstance(logger, logging.Logger):
            self.logger = logger
        else:
            self.logger = None # 由于 flow 在加载工作流之前是未知的，因此无法在此处创建 logger，等工作流加载后再创建
            pass

    def load_workflow(self, flow: Flow):
        self.workflow = flow
        self.runtime.init_with_flow(flow)
        
        # 创建 logger
        if self.logger is None:
            self.logger = logging.getLogger(f"Executor({flow.name})")
            self.logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.info(f">> Workflow '{flow.name}' loaded with {len(flow.nodes)} nodes and {len(flow.sub_flows)} sub-flows")
        if self.hooks and hasattr(self.hooks, "on_workflow_loaded"):
            import asyncio
            maybe_coro = self.hooks.on_workflow_loaded(self, flow)
            if asyncio.iscoroutine(maybe_coro):
                # load_workflow may be called before any event loop exists.
                pass

    def extract_outputs(self, node: Node, io: IOPipeImpl):
        pw_inst = io.outputs.get('__pw_inst__', None)
        if pw_inst:
            self.runtime.set_value("$global{{__pw_inst__}}", pw_inst)
        
        # use browser_context and hide the original browser
        browser = io.outputs.get('__browser__', None)
        browser_context = io.outputs.get('__browser_context__', None)
        if browser and browser_context:
            self.runtime.set_value("$global{{__browser__}}", browser_context)
            self.runtime.set_value("$global{{__original_browser__}}", browser)
        
        page = io.outputs.get('__page__', None)
        if page:
            self.runtime.set_value("$global{{current_page}}", page)
            pages = self.runtime.get_value("$global{{pages}}") or []
            if page not in pages:
                pages.append(page)
                self.runtime.set_value("$global{{pages}}", pages)
        
        # add outputs and prev_outputs
        self.runtime.store_outputs(io.outputs, node.outputs)
    
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
        inst.pw_inst = self.runtime.get_value("$global{{__pw_inst__}}")
        inst.browser = self.runtime.get_value("$global{{__browser__}}")
        inst.page = self.runtime.get_value("$global{{current_page}}")
        inst.executor = self
        inst.logger = self.logger
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
            if isinstance(value, str) and DataContext.contains_var(value):
                value = self.runtime.get_value(value)
            inst.params[key] = value
        inst.executor = self
        inst.logger = self.logger
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
        
        if node.log == "none" or self.workflow.log == "none":
            self.logger.setLevel(logging.WARNING)
        else:
            self.logger.setLevel(logging.DEBUG)

        self.logger.info("")
        self.logger.info(f"=> Executing node '{node.name}' (ID: {node.node_id})")
        if self.hooks and hasattr(self.hooks, "before_step"):
            await self.hooks.before_step(self, node)
        
        if node.action:
            action_io = self.prepare_action_io(node)
            if node.log == "short" or self.workflow.log == "short":
                self.logger.info(f"   Action: {node.action}")
            else:
                self.logger.info(f"   Action: {node.action} with inputs {action_io.inputs}")
            await self.exec_action(node.action, action_io)
            self.extract_outputs(node, action_io)
            self.logger.info(f"   Action Done.")

        # subflow action 有可能通过跳转到 __exit__ 来提前结束流程
        # 因此在执行控制流之前需要检查流程是否已经结束
        if self.runtime.should_exit():
            self.logger.info(f"   Current flow should exit!")
            self.runtime.set_current_node('__exit__')
            return
        
        control_io = self.prepare_control_io(node)
        if node.log == "short" or self.workflow.log == "short":
            self.logger.info(f"   Control: {node.control}")
        else:
            self.logger.info(f"   Control: {node.control} with params {control_io.params}")
        next_node_id = await self.exec_control(node.control, control_io)
        self.logger.info(f"   Next node: '{self.runtime.get_node_name(next_node_id)}' (ID: {next_node_id})")
        self.runtime.set_current_node(next_node_id)
        self.runtime.switch_outputs()
        if self.hooks and hasattr(self.hooks, "after_step"):
            await self.hooks.after_step(self, node, next_node_id)
    
    async def run(self):
        if not self.workflow:
            raise ValueError("No workflow loaded")
        if not self.workflow.start_node_id:
            raise ValueError("Workflow has no start node defined")

        if self.hooks and hasattr(self.hooks, "on_workflow_loaded"):
            await self.hooks.on_workflow_loaded(self, self.workflow)
        
        while not self.runtime.finished():
            try:
                await self.step_one()
            except Exception as exc:
                if self.hooks and hasattr(self.hooks, "on_error"):
                    handled = await self.hooks.on_error(self, exc)
                    if handled:
                        continue
                raise

        if self.hooks and hasattr(self.hooks, "on_finished"):
            await self.hooks.on_finished(self)

    def get_subflow(self, flow_id: str) -> Flow:
        if not self.workflow:
            raise ValueError("No workflow loaded")
        for sub_flow in self.workflow.sub_flows:
            if sub_flow.flow_id == flow_id:
                return sub_flow
        raise ValueError(f"Sub flow '{flow_id}' not found")
        
    async def sub_flow_func(self, io: IOPipeImpl):
        flow_id = io.inputs.get("flow_id")
        if not flow_id:
            raise ValueError("Param 'flow_id' is required for sub_flow_func")

        self.logger.info(f'   Starting sub flow with ID: {flow_id} >>>>>>>>')
        self.logger.info('')
        executor = Executor(
            logger=self.logger,
            hooks=self.hooks,
            managed_env=self.runtime.data_context.data.get("env", {}),
        )
        flow = self.get_subflow(flow_id)
        if not flow:
            raise ValueError(f"Sub flow '{flow_id}' not found")

        sub_rt = executor.runtime

        # copy global vars
        sub_rt.copy_data(self.runtime, prefix="global")

        in_pickers = [VarPicker(picker) for picker in io.inputs.get("data_in", [])]
        # 将 picker.src 获取的值存储到 picker.dst 中，如果 dst 没有以 $ 开头，则默认存储到 flow 作用域中
        for picker in in_pickers:
            value = self.runtime.get_value(picker.src)
            if picker.value is not None:
                value = picker.value
            dst = picker.dst
            if not dst.startswith("$"):
                sub_rt.set_value(f"$flow{{{dst}}}", value)
            else:
                sub_rt.set_value(dst, value)

        executor.load_workflow(flow)
        await executor.run()

        out_pickers = [VarPicker(picker) for picker in io.inputs.get("data_out", [])]
        # todo: 将子流程中的 picker.src 获取的值存储到 picker.dst 中，如果 dst 没有以 $ 开头，则默认存储到当前节点的输出中
        for picker in out_pickers:
            value = sub_rt.get_value(picker.src)
            if picker.value is not None:
                value = picker.value
            dst = picker.dst
            if not dst.startswith("$"):
                io.outputs[dst] = value
            else:
                self.runtime.set_value(dst, value)
        
        if sub_rt.should_exit():
            self.runtime.set_current_node('__exit__')

        self.logger.info(f'   Sub flow with ID: {flow_id} finished <<<<<<<<')
        