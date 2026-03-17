from . import basic_action
from . import basic_control
from . import captcha_action

package_name = "builtin"

actions = [
    # special
    basic_action.SubFlow,  # special action for executing sub flows, it should not be used directly in nodes, but will be used by the excutor when executing sub flows
    # basic
    basic_action.OpenBrowser,
    basic_action.OpenPage,
    basic_action.ClickItem,
    basic_action.FillInput,
    basic_action.WaitElement,
    basic_action.SleepFor,
    basic_action.EmptyAction,
    basic_action.ExtractData,
    basic_action.GetElement,
    basic_action.NextElement,
    basic_action.PyEvalAction,
    # captcha
    captcha_action.SimpleSlideCaptcha,
    captcha_action.SimpleSlideNCC,
]

controls = [
    basic_control.NextNode,
    basic_control.LoopUntil,
]

__all__ = ["actions", "controls", "package_name"]