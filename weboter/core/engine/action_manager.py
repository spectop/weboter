from dataclasses import asdict

from weboter.public.contracts.action import ActionBase

class ActionPackage:

    def __init__(self, name: str):
        self.name = name
        self.actions = {}
    
    def get_action(self, action_name: str) -> ActionBase | None:
        return self.actions.get(action_name, None)
    
    # pass derived class of ActionBase, store it's instance in actions dict
    def add_action(self, action_cls: type[ActionBase]) -> bool:
        action_instance = action_cls()
        action_name = action_cls.name
        if action_name in self.actions:
            return False
        self.actions[action_name] = action_instance
        return True


from typing import Dict, Type, List, Union

class ActionManager:

    def __init__(self):
        self._packages: Dict[str, ActionPackage] = {}

    def has_package(self, name: str) -> bool:
        return name in self._packages
    
    def register_package(self, name: str, package) -> bool:
        # if package is ActionPackage instance, use inner method
        if isinstance(package, ActionPackage):
            return self.__register_package_inner(name, package)
        # if package is a list of ActionBase derived classes
        if isinstance(package, list):
            action_package = ActionPackage(name)
            for action_cls in package:
                action_package.add_action(action_cls)
            return self.__register_package_inner(name, action_package)
        # unknown package type
        return False

    def __register_package_inner(self, name: str, package: ActionPackage) -> bool:
        if name in self._packages:
            return False
        self._packages[name] = package
        return True
    
    def replace_package(self, name: str, package: Union[ActionPackage, List[Type[ActionBase]]]) -> bool:
        """替换已注册的包（必须先存在）"""
        # 存在性检查
        if not self.has_package(name):
            return False

        if isinstance(package, ActionPackage):
            return self.__replace_package_inner(name, package)
        if isinstance(package, list):
            action_package = ActionPackage(name)
            for action_cls in package:
                action_package.add_action(action_cls)
            return self.__replace_package_inner(name, action_package)
        return False

    def unregister_package(self, name: str) -> bool:
        """卸载指定的包"""
        if name in self._packages:
            del self._packages[name]
            return True
        return False

    def __replace_package_inner(self, name: str, package: ActionPackage) -> bool:
        """
        Replace an existing action package with a new one.
        Useful for replace built-in actions with user defined actions.
        """
        self._packages[name] = package
        return True
    
    def get_action(self, full_name: str) -> ActionBase | None:
        """
        获取指定的动作实例
        full_action_name 格式: "package.ActionClass"
        如果 package 为空，则使用内置包
        """
        if '.' in full_name:
            package_name, action_name = full_name.split('.', 1)
        else:
            package_name = ""
            action_name = full_name
        return self.__get_action(package_name, action_name)
    
    def __get_action(self, package_name: str, action_name: str) -> ActionBase | None:
        # if package_name is empty, use builtin package
        if not package_name:
            package_name = "builtin"
        if package_name not in self._packages:
            return None
        package = self._packages[package_name]
        return package.get_action(action_name)

    def list_actions(self) -> list[dict]:
        items: list[dict] = []
        for package_name, package in sorted(self._packages.items()):
            for action_name, action in sorted(package.actions.items()):
                items.append(self._describe_action(package_name, action_name, action))
        return items

    def describe_action(self, full_name: str) -> dict | None:
        if '.' in full_name:
            package_name, action_name = full_name.split('.', 1)
        else:
            package_name = "builtin"
            action_name = full_name
        package = self._packages.get(package_name)
        if package is None:
            return None
        action = package.get_action(action_name)
        if action is None:
            return None
        return self._describe_action(package_name, action_name, action)

    def _describe_action(self, package_name: str, action_name: str, action: ActionBase) -> dict:
        full_name = f"{package_name}.{action_name}" if package_name else action_name
        return {
            "kind": "action",
            "package": package_name,
            "name": action_name,
            "full_name": full_name,
            "description": getattr(action, "description", "") or "",
            "inputs": [asdict(item) for item in getattr(action, "inputs", [])],
            "outputs": [asdict(item) for item in getattr(action, "outputs", [])],
        }


action_manager = ActionManager()