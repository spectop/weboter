from dataclasses import dataclass

@dataclass
class Node:
    node_id: str # unique identifier for the node
    name: str # name of the node
    description: str # description of the node
    action: str # action to be performed at this node
    input: dict # fixed input for this node
    control: str # control logic for this node
    params: dict # fixed input used for control logic

@dataclass
class Link:
    link_id: str # unique identifier for the link
    prev: str # node_id of the previous node, _start_ means start node
    next: str # node_id of the next node
    input: dict # input data flows to next node

@dataclass
class Flow:
    flow_id: str # unique identifier for the flow
    name: str # name of the flow
    description: str # description of the flow
    nodes: list[Node] # list of nodes in the flow
    links: list[Link] # list of links between nodes