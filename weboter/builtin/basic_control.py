from weboter.public.contracts import *

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
        params = context.get("params", {})
        next_node = params.get("next_node")
        if not next_node:
            raise ValueError("Params 'next_node' is required.")

        context["output"] = next_node
        return next_node