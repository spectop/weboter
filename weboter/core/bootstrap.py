from weboter.builtin import actions, controls, package_name
from weboter.core.engine.action_manager import action_manager
from weboter.core.engine.control_manager import control_manager


def ensure_builtin_packages_registered() -> None:
    if action_manager.has_package(package_name):
        action_manager.replace_package(package_name, actions)
    else:
        action_manager.register_package(package_name, actions)

    if control_manager.has_package(package_name):
        control_manager.replace_package(package_name, controls)
    else:
        control_manager.register_package(package_name, controls)