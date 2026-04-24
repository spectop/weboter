from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManagedEnvStore:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        with open(self.path, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
        return payload if isinstance(payload, dict) else {}

    def list_items(self, group: str | None = None) -> dict[str, Any]:
        data = self.load()
        target = self._resolve_group(data, group)
        items = []
        self._collect_items(target, prefix=group or "", items=items)
        groups = self._collect_groups(data)
        return {
            "group": group,
            "items": [self._summarize_item(item) for item in items],
            "groups": groups,
        }

    def get(self, name: str, reveal: bool = False) -> dict[str, Any]:
        data = self.load()
        value = self._resolve_name(data, name)
        return {
            "name": name,
            "value": value if reveal else self._mask_value(value),
            "masked": not reveal,
            "value_type": self._value_type(value),
        }

    def set(self, name: str, value: Any) -> dict[str, Any]:
        data = self.load()
        self._assign_name(data, name, value)
        self._save(data)
        return {
            "saved": name,
            "value_type": self._value_type(value),
            "masked_value": self._mask_value(value),
        }

    def delete(self, name: str) -> dict[str, Any]:
        data = self.load()
        self._delete_name(data, name)
        self._save(data)
        return {"deleted": name}

    def export_env_mapping(self) -> dict[str, Any]:
        return self.load()

    def tree(self, group: str | None = None) -> dict[str, Any]:
        data = self.load()
        if group:
            try:
                target = self._resolve_group(data, group)
            except KeyError:
                # 分组不存在，返回空树而不是报错
                return {
                    "group": group,
                    "tree": {"name": group, "item_count": 0, "group_count": 0, "children": []},
                }
        else:
            target = data
        return {
            "group": group,
            "tree": self._build_tree(group or "", target),
        }

    def import_items(self, payload: dict[str, Any], replace: bool = False) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("环境变量导入内容必须是对象")
        data = {} if replace else self.load()
        self._merge_dict(data, payload)
        self._save(data)
        return {
            "imported": True,
            "replace": replace,
            "item_count": self._count_leaf_items(payload),
        }

    def export_items(self, group: str | None = None, reveal: bool = False) -> dict[str, Any]:
        data = self.load()
        target = self._resolve_group(data, group) if group else data
        payload = self._clone_data(target)
        if not reveal:
            payload = self._mask_mapping(payload)
        return {
            "group": group,
            "masked": not reveal,
            "data": payload,
        }

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    def _resolve_group(self, data: dict[str, Any], group: str | None) -> dict[str, Any]:
        if not group:
            return data
        value = self._resolve_name(data, group)
        if not isinstance(value, dict):
            raise KeyError(f"环境变量分组不存在: {group}")
        return value

    def _resolve_name(self, data: dict[str, Any], name: str) -> Any:
        current: Any = data
        for part in self._split_name(name):
            if not isinstance(current, dict) or part not in current:
                raise KeyError(f"环境变量不存在: {name}")
            current = current[part]
        return current

    def _assign_name(self, data: dict[str, Any], name: str, value: Any) -> None:
        parts = self._split_name(name)
        current = data
        for part in parts[:-1]:
            next_value = current.get(part)
            if next_value is None:
                next_value = {}
                current[part] = next_value
            if not isinstance(next_value, dict):
                raise ValueError(f"环境变量分组路径冲突: {name}")
            current = next_value
        current[parts[-1]] = value

    def _delete_name(self, data: dict[str, Any], name: str) -> None:
        parents: list[tuple[dict[str, Any], str]] = []
        current = data
        for part in self._split_name(name)[:-1]:
            if part not in current or not isinstance(current[part], dict):
                raise KeyError(f"环境变量不存在: {name}")
            parents.append((current, part))
            current = current[part]
        leaf = self._split_name(name)[-1]
        if leaf not in current:
            raise KeyError(f"环境变量不存在: {name}")
        del current[leaf]
        for parent, part in reversed(parents):
            if isinstance(parent.get(part), dict) and not parent[part]:
                del parent[part]

    def _collect_items(self, data: dict[str, Any], prefix: str, items: list[dict[str, Any]]) -> None:
        for key, value in sorted(data.items()):
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._collect_items(value, name, items)
                continue
            items.append({"name": name, "value": value})

    def _collect_groups(self, data: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key, value in sorted(data.items()):
            if not isinstance(value, dict):
                continue
            name = f"{prefix}.{key}" if prefix else key
            items.append({"name": name, "item_count": self._count_leaf_items(value)})
            items.extend(self._collect_groups(value, name))
        return items

    def _build_tree(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        children = []
        item_count = 0
        for key, value in sorted(data.items()):
            child_name = f"{name}.{key}" if name else key
            if isinstance(value, dict):
                child = self._build_tree(child_name, value)
                children.append(child)
                item_count += child["item_count"]
            else:
                item_count += 1
        return {
            "name": name,
            "item_count": item_count,
            "group_count": len(children),
            "children": children,
        }

    def _merge_dict(self, target: dict[str, Any], payload: dict[str, Any]) -> None:
        for key, value in payload.items():
            if isinstance(value, dict):
                existing = target.get(key)
                if existing is None:
                    existing = {}
                    target[key] = existing
                if not isinstance(existing, dict):
                    raise ValueError(f"环境变量分组路径冲突: {key}")
                self._merge_dict(existing, value)
                continue
            target[key] = value

    def _clone_data(self, data: dict[str, Any]) -> dict[str, Any]:
        copied: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                copied[key] = self._clone_data(value)
            else:
                copied[key] = value
        return copied

    def _mask_mapping(self, data: dict[str, Any]) -> dict[str, Any]:
        masked: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                masked[key] = self._mask_mapping(value)
            else:
                masked[key] = self._mask_value(value)
        return masked

    def _count_leaf_items(self, data: dict[str, Any]) -> int:
        total = 0
        for value in data.values():
            if isinstance(value, dict):
                total += self._count_leaf_items(value)
            else:
                total += 1
        return total

    def _summarize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        value = item["value"]
        return {
            "name": item["name"],
            "group": item["name"].rsplit(".", 1)[0] if "." in item["name"] else "",
            "value_type": self._value_type(value),
            "masked_value": self._mask_value(value),
        }

    def _mask_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if not value:
                return ""
            if len(value) <= 4:
                return "*" * len(value)
            return f"{value[:2]}***{value[-2:]}"
        if isinstance(value, (int, float, bool)):
            return "***"
        if isinstance(value, list):
            return f"[list:{len(value)}]"
        if isinstance(value, dict):
            return f"{{dict:{len(value)}}}"
        return "***"

    def _value_type(self, value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "dict"
        return type(value).__name__

    def _split_name(self, name: str) -> list[str]:
        parts = [item.strip() for item in name.split(".") if item.strip()]
        if not parts:
            raise ValueError("环境变量名不能为空")
        return parts