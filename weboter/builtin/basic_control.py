from weboter.public.contracts import *


def _normalize_compare_value(value):
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "false"}:
            return lower == "true"
        try:
            if "." in lower:
                return float(lower)
            return int(lower)
        except ValueError:
            return value
    return value


def _match_with_operator(left, right, operator: str) -> bool:
    op = (operator or "eq").strip().lower()
    lv = _normalize_compare_value(left)
    rv = _normalize_compare_value(right)

    if op in {"eq", "=="}:
        return lv == rv
    if op in {"ne", "!="}:
        return lv != rv
    if op == "contains":
        if isinstance(lv, (list, tuple, set)):
            return rv in lv
        return str(rv) in str(lv)
    if op == "in":
        if isinstance(rv, (list, tuple, set)):
            return lv in rv
        return str(lv) in str(rv)

    if op in {"gt", ">", "lt", "<", "gte", ">=", "lte", "<="}:
        try:
            lf = float(lv)
            rf = float(rv)
        except (TypeError, ValueError):
            return False
        if op in {"gt", ">"}:
            return lf > rf
        if op in {"lt", "<"}:
            return lf < rf
        if op in {"gte", ">="}:
            return lf >= rf
        return lf <= rf

    raise ValueError(f"Unsupported compare operator: {operator}")

class NextNode(ControlBase):
    """Control to specify the next node in the workflow."""
    name: str = "NextNode"
    description: str = "Specify the next node in the workflow"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="next_node",
            description="The ID of the next node to execute",
            required=True,
            accepted_types=["NodeId"]
        )
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="NodeId"
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
            accepted_types=["NodeId"]
        ),
        InputFieldDeclaration(
            name="loop_out",
            description="The ID of the node to exit the loop",
            required=True,
            accepted_types=["NodeId"]
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
            accepted_types=["NodeId"],
            default=""
        )
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="NodeId"
    )

    async def calc_next(self, io: IOPipe) -> str:
        loop_back = io.params.get("loop_back")
        loop_out = io.params.get("loop_out")
        var = io.params.get("var", None)
        value = io.params.get("value")
        loop_tries = io.params.get("loop_tries", 0)
        loop_fail_node = io.params.get("loop_fail_node", "")

        if not loop_back or not loop_out:
            raise ValueError("Params 'loop_back' and 'loop_out' are required.")

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


class IfElse(ControlBase):
    """Control to choose next node by a comparison condition."""

    name: str = "IfElse"
    description: str = "Compare a variable and choose then_node / else_node"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="var",
            description="The current value to compare",
            required=True,
            accepted_types=["any"],
        ),
        InputFieldDeclaration(
            name="value",
            description="The expected value",
            required=True,
            accepted_types=["any"],
        ),
        InputFieldDeclaration(
            name="operator",
            description="eq/ne/gt/gte/lt/lte/contains/in",
            required=False,
            accepted_types=["string"],
            default="eq",
        ),
        InputFieldDeclaration(
            name="then_node",
            description="Next node when condition is true",
            required=True,
            accepted_types=["NodeId"],
        ),
        InputFieldDeclaration(
            name="else_node",
            description="Next node when condition is false",
            required=True,
            accepted_types=["NodeId"],
        ),
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="NodeId",
    )

    async def calc_next(self, io: IOPipe) -> str:
        then_node = io.params.get("then_node")
        else_node = io.params.get("else_node")
        if not then_node or not else_node:
            raise ValueError("Params 'then_node' and 'else_node' are required.")

        var = io.params.get("var")
        value = io.params.get("value")
        operator = io.params.get("operator", "eq")
        matched = _match_with_operator(var, value, operator)
        return then_node if matched else else_node


class ByMap(ControlBase):
    """Control to choose next node from a key->node map."""

    name: str = "ByMap"
    description: str = "Choose next node from route_map by key, fallback to default_node"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="key",
            description="Routing key",
            required=True,
            accepted_types=["string", "number", "boolean"],
        ),
        InputFieldDeclaration(
            name="route_map",
            description="A dict mapping key to node_id",
            required=True,
            accepted_types=["dict"],
        ),
        InputFieldDeclaration(
            name="default_node",
            description="Fallback node if key is not found",
            required=True,
            accepted_types=["NodeId"],
        ),
    ]
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="The ID of the next node to execute",
        type="NodeId",
    )

    async def calc_next(self, io: IOPipe) -> str:
        route_map = io.params.get("route_map")
        default_node = io.params.get("default_node")
        if not isinstance(route_map, dict):
            raise ValueError("Param 'route_map' must be a dict.")
        if not default_node:
            raise ValueError("Param 'default_node' is required.")

        key = io.params.get("key")
        if key in route_map:
            return route_map[key]

        key_text = str(key)
        if key_text in route_map:
            return route_map[key_text]

        return default_node


class EndFlow(ControlBase):
    """Control to end the current workflow."""

    name: str = "EndFlow"
    description: str = "Finish current workflow immediately"
    inputs: list[InputFieldDeclaration] = []
    outputs: OutputFieldDeclaration = OutputFieldDeclaration(
        name="next_node",
        description="Always returns __end__",
        type="NodeId",
    )

    async def calc_next(self, io: IOPipe) -> str:
        return "__end__"
            