from ..role.control import ControlBase
from ..role.interface import InputFieldDeclaration, OutputFieldDeclaration

class NextNode(ControlBase):
    """Control to specify the next node in the workflow."""
    name: str = "NextNode"
    description: str = "Specify the next node in the workflow"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="next_node",
            description="The ID of the next node to execute",
            required=True,
            accepted_types=["string"]
        )
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="string"
    )

    async def calc_next(self, context: dict) -> str:
        input = context.get("input", {})
        next_node = input.get("next_node")
        if not next_node:
            raise ValueError("Input 'next_node' is required.")

        context["output"] = next_node
        return next_node