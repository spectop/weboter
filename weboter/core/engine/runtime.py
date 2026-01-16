from weboter.model.model import Flow, Node, Link
class Runtime:
    
    def __init__(self):
        self.flow: Flow | None = None
        self.nodes = {}
        self.links = {}
    
    def init_with_flow(self, flow: Flow):
        self.flow = flow
        self.nodes = {node.node_id: node for node in flow.nodes}
        self.links = {link.link_id: link for link in flow.links}