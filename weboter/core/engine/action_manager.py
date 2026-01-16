from weboter.role.action import ActionBase


class ActionPackage:

    def __init__(self, name: str):
        self.name = name
        self.actions = {}
    
    def get_action(self, action_name: str) -> ActionBase | None:
        return self.actions.get(action_name, None)
    

class ActionManager:
    
    def __init__(self):
        self._packages = {}

    def has_package(self, name: str) -> bool:
        return name in self._packages

    def register_package(self, name: str, package: ActionPackage) -> bool:
        if name in self._packages:
            return False
        self._packages[name] = package
        return True
    
    def replace_package(self, name: str, package: ActionPackage) -> bool:
        """
        Replace an existing action package with a new one.
        Useful for replace built-in actions with user defined actions.
        """
        self._packages[name] = package
        return True
    
    def get_action(self, package_name: str, action_name: str) -> ActionBase | None:
        # if package_name is empty, use builtin package
        if not package_name:
            package_name = "builtin"
        if package_name not in self._packages:
            return None
        package = self._packages[package_name]
        return package.get_action(action_name)