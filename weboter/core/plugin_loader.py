from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.metadata as metadata
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

from weboter.app.config import AppConfig, load_app_config
from weboter.core.bootstrap import ensure_builtin_packages_registered
from weboter.core.engine.action_manager import action_manager
from weboter.core.engine.control_manager import control_manager
from weboter.public.contracts.action import ActionBase
from weboter.public.contracts.control import ControlBase


ENTRY_POINT_GROUP = "weboter.plugins"


@dataclass
class _PluginDescriptor:
    source: str
    module_name: str
    package_name: str
    actions: list[type[ActionBase]]
    controls: list[type[ControlBase]]


_registered_action_packages: set[str] = set()
_registered_control_packages: set[str] = set()
_initialized = False
_initialized_plugin_root: str | None = None
_load_seq = 0


def ensure_plugins_initialized(config: AppConfig | None = None) -> None:
    global _initialized, _initialized_plugin_root
    target_config = config or load_app_config()
    plugin_root = str(target_config.plugin_root_path())
    if _initialized and _initialized_plugin_root == plugin_root:
        return
    refresh_plugins(config=target_config)
    _initialized = True
    _initialized_plugin_root = plugin_root


def refresh_plugins(config: AppConfig | None = None) -> dict[str, Any]:
    global _initialized_plugin_root
    target_config = config or load_app_config()
    ensure_builtin_packages_registered()
    _unregister_previous_plugins()

    loaded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    descriptors = _discover_plugins(target_config, errors)
    for descriptor in descriptors:
        try:
            _register_plugin(descriptor)
            loaded.append(
                {
                    "source": descriptor.source,
                    "module": descriptor.module_name,
                    "package": descriptor.package_name,
                    "action_count": len(descriptor.actions),
                    "control_count": len(descriptor.controls),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "source": descriptor.source,
                    "module": descriptor.module_name,
                    "package": descriptor.package_name,
                    "error": str(exc),
                }
            )

    _initialized_plugin_root = str(target_config.plugin_root_path())

    return {
        "plugin_root": str(target_config.plugin_root_path()),
        "loaded": loaded,
        "loaded_count": len(loaded),
        "errors": errors,
        "error_count": len(errors),
    }


def _unregister_previous_plugins() -> None:
    for package_name in sorted(_registered_action_packages):
        action_manager.unregister_package(package_name)
    for package_name in sorted(_registered_control_packages):
        control_manager.unregister_package(package_name)
    _registered_action_packages.clear()
    _registered_control_packages.clear()


def _discover_plugins(config: AppConfig, errors: list[dict[str, str]]) -> list[_PluginDescriptor]:
    descriptors: list[_PluginDescriptor] = []
    seen_modules: set[str] = set()

    for descriptor in _discover_directory_plugins(config.plugin_root_path(), errors):
        if descriptor.module_name in seen_modules:
            continue
        seen_modules.add(descriptor.module_name)
        descriptors.append(descriptor)

    for descriptor in _discover_installed_plugins(errors):
        if descriptor.module_name in seen_modules:
            continue
        seen_modules.add(descriptor.module_name)
        descriptors.append(descriptor)

    return descriptors


def _discover_directory_plugins(plugin_root: Path, errors: list[dict[str, str]]) -> list[_PluginDescriptor]:
    if not plugin_root.is_dir():
        return []

    descriptors: list[_PluginDescriptor] = []
    for child in sorted(plugin_root.iterdir()):
        if not child.is_dir():
            continue
        init_file = child / "__init__.py"
        if not init_file.is_file():
            continue
        module_name = _next_dynamic_module_name(child.name)
        try:
            module = _load_module_from_path(module_name, init_file)
            descriptors.append(_build_descriptor(module, source=f"plugin_root:{child}"))
        except Exception as exc:
            errors.append(
                {
                    "source": f"plugin_root:{child}",
                    "module": module_name,
                    "error": str(exc),
                }
            )
    return descriptors


def _discover_installed_plugins(errors: list[dict[str, str]]) -> list[_PluginDescriptor]:
    descriptors: list[_PluginDescriptor] = []
    loaded_modules: set[str] = set()

    try:
        entry_points = metadata.entry_points().select(group=ENTRY_POINT_GROUP)
    except Exception:
        entry_points = []

    for entry in entry_points:
        try:
            plugin_obj = entry.load()
            module = _resolve_plugin_module(plugin_obj, default_module_name=entry.value)
            descriptor = _build_descriptor(module, source=f"entry_point:{entry.name}")
            descriptors.append(descriptor)
            loaded_modules.add(descriptor.module_name)
        except Exception as exc:
            errors.append(
                {
                    "source": f"entry_point:{entry.name}",
                    "module": getattr(entry, "value", entry.name),
                    "error": str(exc),
                }
            )

    for module_name in sorted(_discover_distribution_module_names()):
        if module_name in loaded_modules:
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            errors.append(
                {
                    "source": "installed",
                    "module": module_name,
                    "error": str(exc),
                }
            )
            continue
        if not _looks_like_plugin_module(module):
            continue
        try:
            descriptors.append(_build_descriptor(module, source="installed"))
            loaded_modules.add(module_name)
        except Exception as exc:
            errors.append(
                {
                    "source": "installed",
                    "module": module_name,
                    "error": str(exc),
                }
            )

    return descriptors


def _discover_distribution_module_names() -> set[str]:
    module_names: set[str] = set()
    for dist in metadata.distributions():
        dist_name = str(dist.metadata.get("Name", "")).strip().lower()
        if not dist_name.startswith("weboter-"):
            continue
        if dist_name == "weboter":
            continue

        top_level_text = dist.read_text("top_level.txt") or ""
        top_level_modules = [line.strip() for line in top_level_text.splitlines() if line.strip()]
        if not top_level_modules:
            top_level_modules = [dist_name.replace("-", "_")]
        for module_name in top_level_modules:
            if module_name.startswith("weboter"):
                module_names.add(module_name)
    return module_names


def _resolve_plugin_module(plugin_obj: Any, default_module_name: str) -> ModuleType:
    if isinstance(plugin_obj, ModuleType):
        return plugin_obj
    if callable(plugin_obj):
        resolved = plugin_obj()
        if isinstance(resolved, ModuleType):
            return resolved
    if isinstance(plugin_obj, str):
        return importlib.import_module(plugin_obj)
    return importlib.import_module(default_module_name.split(":", 1)[0])


def _build_descriptor(module: ModuleType, source: str) -> _PluginDescriptor:
    package_name = str(getattr(module, "package_name", "")).strip()
    if not package_name:
        raise ValueError("plugin module must define package_name")

    actions = _validate_action_classes(getattr(module, "actions", []))
    controls = _validate_control_classes(getattr(module, "controls", []))
    if not actions and not controls:
        raise ValueError("plugin module must provide at least one action or control")

    return _PluginDescriptor(
        source=source,
        module_name=module.__name__,
        package_name=package_name,
        actions=actions,
        controls=controls,
    )


def _validate_action_classes(items: Any) -> list[type[ActionBase]]:
    classes: list[type[ActionBase]] = []
    for item in list(items or []):
        if not isinstance(item, type) or not issubclass(item, ActionBase):
            raise TypeError(f"invalid action class: {item}")
        classes.append(item)
    return classes


def _validate_control_classes(items: Any) -> list[type[ControlBase]]:
    classes: list[type[ControlBase]] = []
    for item in list(items or []):
        if not isinstance(item, type) or not issubclass(item, ControlBase):
            raise TypeError(f"invalid control class: {item}")
        classes.append(item)
    return classes


def _register_plugin(descriptor: _PluginDescriptor) -> None:
    if descriptor.actions:
        if action_manager.has_package(descriptor.package_name):
            action_manager.replace_package(descriptor.package_name, descriptor.actions)
        else:
            action_manager.register_package(descriptor.package_name, descriptor.actions)
        _registered_action_packages.add(descriptor.package_name)

    if descriptor.controls:
        if control_manager.has_package(descriptor.package_name):
            control_manager.replace_package(descriptor.package_name, descriptor.controls)
        else:
            control_manager.register_package(descriptor.package_name, descriptor.controls)
        _registered_control_packages.add(descriptor.package_name)


def _looks_like_plugin_module(module: ModuleType) -> bool:
    package_name = str(getattr(module, "package_name", "")).strip()
    return bool(package_name and (hasattr(module, "actions") or hasattr(module, "controls")))


def _load_module_from_path(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _next_dynamic_module_name(folder_name: str) -> str:
    global _load_seq
    _load_seq += 1
    safe_name = folder_name.replace("-", "_").replace(".", "_")
    return f"weboter_plugin_{safe_name}_{_load_seq}"
