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

    async def calc_next(self, io: IOPipe) -> str:
        next_node = io.params.get("next_node", None)
        if not next_node:
            raise ValueError("Params 'next_node' is required.")
        return next_node

class LoopUntil(ControlBase):
    """Control to loop until a condition is met."""
    name: str = "LoopUntil"
    description: str = "Loop until a specified condition is met"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="loop_back",
            description="The ID of the node to loop back to",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="loop_out",
            description="The ID of the node to exit the loop",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="var",
            description="The variable to check the condition against",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="value",
            description="The value to compare the variable with",
            required=True,
            accepted_types=["string", "number", "boolean"],
            default=True
        ),
        InputFieldDeclaration(
            name="loop_tries",
            description="Maximum number of loop attempts, 0 means infinite",
            required=False,
            accepted_types=["number"],
            default=0
        ),
        InputFieldDeclaration(
            name="loop_fail_node",
            description="The node to go to if loop fails (only if loop_tries > 0, same as loop_out if not set)",
            required=False,
            accepted_types=["string"],
            default=""
        )
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="string"
    )

    async def calc_next(self, io: IOPipe) -> str:
        loop_back = io.params.get("loop_back")
        loop_out = io.params.get("loop_out")
        var = io.params.get("var", None)
        value = io.params.get("value")
        loop_tries = io.params.get("loop_tries", 0)
        loop_fail_node = io.params.get("loop_fail_node", "")

        if not loop_back or not loop_out or not var:
            raise ValueError("Params 'loop_back', 'loop_out', and 'var' are required.")

        if var == value:
            return loop_out
        
        if loop_tries > 0:
            cur_node_id = io.cur_node
            counter_name = f"__loop_counter_{cur_node_id}__"
            if counter_name not in io.flow_data:
                io.flow_data[counter_name] = loop_tries
            io.flow_data[counter_name] -= 1
            if io.flow_data[counter_name] <= 0:
                if loop_fail_node:
                    return loop_fail_node
                return loop_out
        
        return loop_back
            