import asyncio
from weboter.core.engine.scheduler import Scheduler
from weboter.core.workflow_io import WorkflowReader, WorkflowWriter
from weboter.builtin import actions, controls
from weboter.core.engine.action_manager import action_manager
from weboter.core.engine.control_manager import control_manager

action_manager.register_package("builtin", actions)
control_manager.register_package("builtin", controls)

def main():
    flow = WorkflowReader.from_json("./workflows/sgcc.json")
    scheduler = Scheduler()
    scheduler.load_workflow(flow)
    # further test code can be added here
    asyncio.run(scheduler.run())

if __name__ == "__main__":
    main()