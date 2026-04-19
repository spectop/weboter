from dataclasses import asdict

from weboter.public.contracts.control import ControlBase

class ControlPackage:

    def __init__(self, name: str):
        self.name = name
        self.controls = {}
    
    def get_control(self, control_name: str) -> ControlBase | None:
        return self.controls.get(control_name, None)
    
    # pass derived class of ControlBase, store it's instance in controls dict
    def add_control(self, control_cls: type[ControlBase]) -> bool:
        control_instance = control_cls()
        control_name = control_cls.name
        if control_name in self.controls:
            return False
        self.controls[control_name] = control_instance
        return True


from typing import Dict, Type, List, Union

class ControlManager:

    def __init__(self):
        self._packages: Dict[str, ControlPackage] = {}

    def has_package(self, name: str) -> bool:
        return name in self._packages
    
    def register_package(self, name: str, package) -> bool:
        # if package is ControlPackage instance, use inner method
        if isinstance(package, ControlPackage):
            return self.__register_package_inner(name, package)
        # if package is a list of ControlBase derived classes
        if isinstance(package, list):
            control_package = ControlPackage(name)
            for control_cls in package:
                control_package.add_control(control_cls)
            return self.__register_package_inner(name, control_package)
        # unknown package type
        return False

    def __register_package_inner(self, name: str, package: ControlPackage) -> bool:
        if name in self._packages:
            return False
        self._packages[name] = package
        return True
    
    def replace_package(self, name: str, package: Union[ControlPackage, List[Type[ControlBase]]]) -> bool:
        """替换已注册的包（必须先存在）"""
        # 存在性检查
        if not self.has_package(name):
            return False

        if isinstance(package, ControlPackage):
            return self.__replace_package_inner(name, package)
        if isinstance(package, list):
            control_package = ControlPackage(name)
            for control_cls in package:
                control_package.add_control(control_cls)
            return self.__replace_package_inner(name, control_package)
        return False

    def unregister_package(self, name: str) -> bool:
        """卸载指定的包"""
        if name in self._packages:
            del self._packages[name]
            return True
        return False

    def __replace_package_inner(self, name: str, package: ControlPackage) -> bool:
        self._packages[name] = package
        return True
    
    def get_control(self, full_name: str) -> ControlBase | None:
        """根据全名获取控制器实例，格式: "package.ControlClass" """
        if '.' not in full_name:
            return None
        parts = full_name.split('.')
        if len(parts) != 2:
            return None
        package_name, control_name = parts
        return self.__get_control(package_name, control_name)
    
    def __get_control(self, package_name: str, control_name: str) -> ControlBase | None:
        package = self._packages.get(package_name, None)
        if not package:
            return None
        return package.get_control(control_name)

    def list_controls(self) -> list[dict]:
        items: list[dict] = []
        for package_name, package in sorted(self._packages.items()):
            for control_name, control in sorted(package.controls.items()):
                items.append(self._describe_control(package_name, control_name, control))
        return items

    def describe_control(self, full_name: str) -> dict | None:
        if '.' not in full_name:
            return None
        package_name, control_name = full_name.split('.', 1)
        package = self._packages.get(package_name)
        if package is None:
            return None
        control = package.get_control(control_name)
        if control is None:
            return None
        return self._describe_control(package_name, control_name, control)

    def _describe_control(self, package_name: str, control_name: str, control: ControlBase) -> dict:
        outputs = getattr(control, "outputs", None)
        serialized_outputs = [asdict(outputs)] if outputs is not None else []
        return {
            "kind": "control",
            "package": package_name,
            "name": control_name,
            "full_name": f"{package_name}.{control_name}",
            "description": getattr(control, "description", "") or "",
            "inputs": [asdict(item) for item in getattr(control, "inputs", [])],
            "outputs": serialized_outputs,
        }
    

control_manager = ControlManager()