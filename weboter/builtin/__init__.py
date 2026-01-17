from . import basic_action
from . import basic_control

package_name = "builtin"

actions = [
    basic_action.OpenPage,
    basic_action.ClickItem,
]

controls = [
    basic_control.NextNode,
]

__all__ = ["actions", "controls", "package_name"]