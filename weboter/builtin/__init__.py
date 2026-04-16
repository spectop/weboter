from . import basic_action
from . import basic_control

package_name = "builtin"

captcha_actions = []

try:
    from . import captcha_action

    captcha_actions = [
        captcha_action.SimpleSlideCaptcha,
        captcha_action.SimpleSlideNCC,
    ]
except ModuleNotFoundError as exc:
    if exc.name not in {"cv2", "numpy"}:
        raise
    captcha_actions = []

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
    basic_action.WriteTextFile,
    basic_action.FetchUrl,
]

actions.extend(captcha_actions)

controls = [
    basic_control.NextNode,
    basic_control.LoopUntil,
]

__all__ = ["actions", "controls", "package_name"]