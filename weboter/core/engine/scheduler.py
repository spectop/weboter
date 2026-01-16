from excutor import Excutor
from weboter.model.model import Flow, Node, Link

class Scheduler:
    
    def __init__(self):
        self.excutors = []
        self.runtime = None
        self.workflow: Flow | None = None

    def resize_excutors(self, size: int):
        current_size = len(self.excutors)
        if size > current_size:
            for _ in range(size - current_size):
                self.excutors.append(Excutor())
        elif size < current_size:
            self.excutors = self.excutors[:size]

    def load_workflow(self, workflow: Flow):
        self.workflow = workflow
    
    