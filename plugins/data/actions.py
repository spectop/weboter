"""
Data 插件 - 提供常见的数据加工动作

包含：
  - JsonParse / JsonStringify
  - JsonGetPath
  - RegexExtract
  - Base64Encode / Base64Decode
  - DictMerge
  - ListUnique
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from weboter.public.contracts.action import ActionBase
from weboter.public.contracts.interface import InputFieldDeclaration, OutputFieldDeclaration
from weboter.public.contracts.io_pipe import IOPipe


def _resolve_json_path(data: Any, path: str) -> Any:
    """解析简单 JSON 路径，支持 a.b[0].c 形式。"""
    if not path:
        return data

    tokens: list[Any] = []
    cur = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if cur:
                tokens.append(cur)
                cur = ""
            i += 1
            continue
        if ch == "[":
            if cur:
                tokens.append(cur)
                cur = ""
            j = path.find("]", i)
            if j == -1:
                raise ValueError(f"无效 path，缺少 ]: {path}")
            idx_text = path[i + 1 : j].strip()
            if not idx_text.isdigit():
                raise ValueError(f"数组下标必须是非负整数: {idx_text}")
            tokens.append(int(idx_text))
            i = j + 1
            continue
        cur += ch
        i += 1
    if cur:
        tokens.append(cur)

    value = data
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(value, list):
                raise TypeError(f"当前值不是 list，无法使用下标 {token}")
            value = value[token]
        else:
            if not isinstance(value, dict):
                raise TypeError(f"当前值不是 dict，无法读取 key: {token}")
            value = value[token]
    return value


class JsonParse(ActionBase):
    name: str = "JsonParse"
    description: str = "将 JSON 字符串解析为对象"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="text",
            description="JSON 字符串",
            required=True,
            accepted_types=["string"],
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="data", description="解析后的对象", type="any")
    ]

    async def execute(self, io: IOPipe) -> None:
        text = io.inputs["text"]
        io.outputs["data"] = json.loads(text)


class JsonStringify(ActionBase):
    name: str = "JsonStringify"
    description: str = "将对象序列化为 JSON 字符串"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="data",
            description="任意可 JSON 序列化对象",
            required=True,
            accepted_types=["any"],
        ),
        InputFieldDeclaration(
            name="pretty",
            description="是否美化输出",
            required=False,
            accepted_types=["boolean"],
            default=False,
        ),
        InputFieldDeclaration(
            name="ensure_ascii",
            description="是否转义非 ASCII 字符",
            required=False,
            accepted_types=["boolean"],
            default=False,
        ),
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="text", description="JSON 字符串", type="string")
    ]

    async def execute(self, io: IOPipe) -> None:
        data = io.inputs["data"]
        pretty = bool(io.inputs.get("pretty") or False)
        ensure_ascii = bool(io.inputs.get("ensure_ascii") or False)
        io.outputs["text"] = json.dumps(
            data,
            ensure_ascii=ensure_ascii,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )


class JsonGetPath(ActionBase):
    name: str = "JsonGetPath"
    description: str = "从 JSON 对象中按路径提取字段，支持 a.b[0].c"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="data",
            description="JSON 对象（dict/list）",
            required=True,
            accepted_types=["dict", "list"],
        ),
        InputFieldDeclaration(
            name="path",
            description="路径表达式，如 a.b[0].c；空字符串返回整个 data",
            required=False,
            accepted_types=["string"],
            default="",
        ),
        InputFieldDeclaration(
            name="default",
            description="提取失败时返回的默认值（当 strict=false 时）",
            required=False,
            accepted_types=["any"],
            default=None,
        ),
        InputFieldDeclaration(
            name="strict",
            description="true: 提取失败抛错；false: 返回 default",
            required=False,
            accepted_types=["boolean"],
            default=True,
        ),
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="value", description="提取结果", type="any"),
        OutputFieldDeclaration(name="found", description="是否成功找到", type="bool"),
    ]

    async def execute(self, io: IOPipe) -> None:
        data = io.inputs["data"]
        path = str(io.inputs.get("path") or "")
        strict = bool(io.inputs.get("strict") if "strict" in io.inputs else True)
        default_value = io.inputs.get("default")

        try:
            value = _resolve_json_path(data, path)
            io.outputs["value"] = value
            io.outputs["found"] = True
        except Exception:
            if strict:
                raise
            io.outputs["value"] = default_value
            io.outputs["found"] = False


class RegexExtract(ActionBase):
    name: str = "RegexExtract"
    description: str = "使用正则表达式提取文本，支持单个或全部匹配"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(name="text", description="输入文本", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="pattern", description="正则表达式", required=True, accepted_types=["string"]),
        InputFieldDeclaration(
            name="group",
            description="分组索引（默认 0=整个匹配）",
            required=False,
            accepted_types=["number"],
            default=0,
        ),
        InputFieldDeclaration(
            name="all",
            description="是否返回全部匹配",
            required=False,
            accepted_types=["boolean"],
            default=False,
        ),
        InputFieldDeclaration(
            name="flags",
            description="正则标志，支持 i,m,s（可组合）",
            required=False,
            accepted_types=["string"],
            default="",
        ),
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="value", description="首个匹配（all=false）", type="any"),
        OutputFieldDeclaration(name="values", description="全部匹配（all=true）", type="list"),
        OutputFieldDeclaration(name="matched", description="是否匹配到", type="bool"),
    ]

    async def execute(self, io: IOPipe) -> None:
        text = io.inputs["text"]
        pattern = io.inputs["pattern"]
        group = int(io.inputs.get("group") or 0)
        want_all = bool(io.inputs.get("all") or False)
        flag_text = str(io.inputs.get("flags") or "")

        re_flags = 0
        if "i" in flag_text:
            re_flags |= re.IGNORECASE
        if "m" in flag_text:
            re_flags |= re.MULTILINE
        if "s" in flag_text:
            re_flags |= re.DOTALL

        compiled = re.compile(pattern, re_flags)

        if want_all:
            matches = list(compiled.finditer(text))
            values = [m.group(group) for m in matches]
            io.outputs["values"] = values
            io.outputs["matched"] = len(values) > 0
            io.outputs["value"] = values[0] if values else None
            return

        match = compiled.search(text)
        if not match:
            io.outputs["value"] = None
            io.outputs["values"] = []
            io.outputs["matched"] = False
            return

        io.outputs["value"] = match.group(group)
        io.outputs["values"] = [match.group(group)]
        io.outputs["matched"] = True


class Base64Encode(ActionBase):
    name: str = "Base64Encode"
    description: str = "将字符串进行 Base64 编码"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(name="text", description="原始文本", required=True, accepted_types=["string"]),
        InputFieldDeclaration(
            name="encoding",
            description="字符编码",
            required=False,
            accepted_types=["string"],
            default="utf-8",
        ),
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="base64", description="Base64 字符串", type="string")
    ]

    async def execute(self, io: IOPipe) -> None:
        text = io.inputs["text"]
        encoding = str(io.inputs.get("encoding") or "utf-8")
        io.outputs["base64"] = base64.b64encode(text.encode(encoding)).decode("ascii")


class Base64Decode(ActionBase):
    name: str = "Base64Decode"
    description: str = "将 Base64 字符串解码为文本"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(name="base64", description="Base64 字符串", required=True, accepted_types=["string"]),
        InputFieldDeclaration(
            name="encoding",
            description="目标字符编码",
            required=False,
            accepted_types=["string"],
            default="utf-8",
        ),
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="text", description="解码后的文本", type="string")
    ]

    async def execute(self, io: IOPipe) -> None:
        b64 = io.inputs["base64"]
        encoding = str(io.inputs.get("encoding") or "utf-8")
        io.outputs["text"] = base64.b64decode(b64.encode("ascii")).decode(encoding)


class DictMerge(ActionBase):
    name: str = "DictMerge"
    description: str = "合并多个 dict，后者覆盖前者同名 key"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="items",
            description="待合并的 dict 列表",
            required=True,
            accepted_types=["list"],
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="result", description="合并结果", type="dict")
    ]

    async def execute(self, io: IOPipe) -> None:
        items = io.inputs["items"]
        if not isinstance(items, list):
            raise TypeError("items 必须是 list")
        result: dict[str, Any] = {}
        for obj in items:
            if not isinstance(obj, dict):
                raise TypeError("items 中每个元素都必须是 dict")
            result.update(obj)
        io.outputs["result"] = result


class ListUnique(ActionBase):
    name: str = "ListUnique"
    description: str = "列表去重并保持原有顺序"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(name="items", description="原始列表", required=True, accepted_types=["list"])
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="result", description="去重后的列表", type="list")
    ]

    async def execute(self, io: IOPipe) -> None:
        items = io.inputs["items"]
        if not isinstance(items, list):
            raise TypeError("items 必须是 list")

        result: list[Any] = []
        seen_hashable: set[Any] = set()
        seen_unhashable: list[Any] = []

        for item in items:
            try:
                marker = ("h", item)
                if marker in seen_hashable:
                    continue
                seen_hashable.add(marker)
                result.append(item)
            except TypeError:
                # 不可哈希对象使用线性比较，保证语义正确
                exists = any(item == old for old in seen_unhashable)
                if exists:
                    continue
                seen_unhashable.append(item)
                result.append(item)

        io.outputs["result"] = result


