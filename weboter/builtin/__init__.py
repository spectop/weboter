from . import basic_action
from . import basic_control
from weboter.public.contracts import ActionBase, IOPipe

package_name = "builtin"

captcha_actions = []


def _build_missing_dependency_action(name: str, missing_dependency: str) -> type[ActionBase]:
    class _MissingDependencyAction(ActionBase):
        description = f"Action '{name}' requires optional dependency '{missing_dependency}'."
        inputs = []
        outputs = []

        async def execute(self, io: IOPipe):
            raise RuntimeError(
                f"Action '{name}' requires optional dependency '{missing_dependency}'. "
                "Please install the captcha extras before executing it."
            )

    _MissingDependencyAction.name = name
    _MissingDependencyAction.__name__ = name
    return _MissingDependencyAction

try:
    from . import captcha_action

    captcha_actions = [
        captcha_action.SimpleSlideCaptcha,
        captcha_action.SimpleSlideNCC,
    ]
except ModuleNotFoundError as exc:
    if exc.name not in {"cv2", "numpy"}:
        raise
    captcha_actions = [
        _build_missing_dependency_action("SimpleSlideCaptcha", exc.name),
        _build_missing_dependency_action("SimpleSlideNCC", exc.name),
    ]

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
    basic_control.IfElse,
    basic_control.ByMap,
    basic_control.EndFlow,
]

__all__ = ["actions", "controls", "package_name"]