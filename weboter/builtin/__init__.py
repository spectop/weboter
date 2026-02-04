from . import basic_action
from . import basic_control
from . import captcha_action

package_name = "builtin"

actions = [
    # basic
    basic_action.OpenBrowser,
    basic_action.OpenPage,
    basic_action.ClickItem,
    basic_action.FillInput,
    basic_action.WaitElement,
    basic_action.SleepFor,
    # captcha
    captcha_action.SimpleSlideCaptcha,
]

controls = [
    basic_control.NextNode,
    basic_control.LoopUntil,
]

__all__ = ["actions", "controls", "package_name"]