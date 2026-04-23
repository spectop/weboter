"""
HTTP 插件 - 提供常见的网络操作动作

包含：
  - HttpRequest  通用 HTTP 请求（支持任意方法）
  - HttpGet      GET 请求
  - HttpPost     POST 请求（JSON / 表单 / 原始 body）
  - HttpPut      PUT 请求
  - HttpDelete   DELETE 请求
  - HttpPatch    PATCH 请求
  - HttpHead     HEAD 请求（只返回头信息）

所有动作均使用标准库 urllib，无需额外依赖。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from weboter.public.contracts.action import ActionBase
from weboter.public.contracts.interface import InputFieldDeclaration, OutputFieldDeclaration
from weboter.public.contracts.io_pipe import IOPipe


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _do_request(
    method: str,
    url: str,
    headers: dict[str, str] | None,
    body: bytes | None,
    timeout: float,
) -> dict[str, Any]:
    """执行 HTTP 请求，返回 status_code / headers / body_text / json。"""
    req = urllib.request.Request(url, data=body, method=method.upper())
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code: int = resp.status
            resp_headers: dict[str, str] = dict(resp.headers)
            raw: bytes = resp.read()
    except urllib.error.HTTPError as exc:
        # HTTPError 仍然是有效响应，读取 body
        status_code = exc.code
        resp_headers = dict(exc.headers) if exc.headers else {}
        raw = exc.read() if hasattr(exc, "read") else b""
    except urllib.error.URLError as exc:
        raise RuntimeError(f"请求失败: {exc.reason}") from exc

    body_text = raw.decode("utf-8", errors="replace")

    # 尝试解析 JSON
    parsed_json: Any = None
    content_type = resp_headers.get("Content-Type", resp_headers.get("content-type", ""))
    if "json" in content_type or body_text.lstrip().startswith(("{", "[")):
        try:
            parsed_json = json.loads(body_text)
        except json.JSONDecodeError:
            pass

    return {
        "status_code": status_code,
        "headers": resp_headers,
        "body": body_text,
        "json": parsed_json,
        "ok": 200 <= status_code < 300,
    }


def _build_body_and_headers(
    io_inputs: dict[str, Any],
) -> tuple[bytes | None, dict[str, str]]:
    """根据输入参数构建请求体与 Content-Type 头。"""
    headers: dict[str, str] = dict(io_inputs.get("headers") or {})
    json_body = io_inputs.get("json_body")
    form_body = io_inputs.get("form_body")
    raw_body = io_inputs.get("body")

    body_bytes: bytes | None = None

    if json_body is not None:
        body_str = json_body if isinstance(json_body, str) else json.dumps(json_body, ensure_ascii=False)
        body_bytes = body_str.encode("utf-8")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    elif form_body:
        if isinstance(form_body, dict):
            body_bytes = urllib.parse.urlencode(form_body).encode("utf-8")
        else:
            body_bytes = str(form_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif raw_body is not None:
        body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body

    return body_bytes, headers


def _set_outputs(io: IOPipe, result: dict[str, Any]) -> None:
    io.outputs["status_code"] = result["status_code"]
    io.outputs["headers"] = result["headers"]
    io.outputs["body"] = result["body"]
    io.outputs["json"] = result["json"]
    io.outputs["ok"] = result["ok"]


# ──────────────────────────────────────────────
# 公共输入/输出声明片段
# ──────────────────────────────────────────────

_COMMON_INPUTS = [
    InputFieldDeclaration(
        name="url",
        description="目标 URL",
        required=True,
        accepted_types=["string"],
    ),
    InputFieldDeclaration(
        name="headers",
        description="请求头（dict）",
        required=False,
        accepted_types=["dict"],
        default=None,
    ),
    InputFieldDeclaration(
        name="timeout",
        description="超时秒数",
        required=False,
        accepted_types=["number"],
        default=30,
    ),
]

_COMMON_OUTPUTS = [
    OutputFieldDeclaration(name="status_code", description="HTTP 状态码", type="int"),
    OutputFieldDeclaration(name="headers", description="响应头 dict", type="dict"),
    OutputFieldDeclaration(name="body", description="响应体文本", type="string"),
    OutputFieldDeclaration(name="json", description="解析后的 JSON 对象（若适用）", type="any"),
    OutputFieldDeclaration(name="ok", description="状态码是否 2xx", type="bool"),
]

_BODY_INPUTS = [
    InputFieldDeclaration(
        name="json_body",
        description="以 JSON 发送的请求体（dict 或 JSON 字符串）",
        required=False,
        accepted_types=["dict", "string"],
        default=None,
    ),
    InputFieldDeclaration(
        name="form_body",
        description="以表单格式发送的请求体（dict）",
        required=False,
        accepted_types=["dict"],
        default=None,
    ),
    InputFieldDeclaration(
        name="body",
        description="原始请求体字符串",
        required=False,
        accepted_types=["string"],
        default=None,
    ),
]


# ──────────────────────────────────────────────
# 通用请求动作
# ──────────────────────────────────────────────

class HttpRequest(ActionBase):
    """发起任意方法的 HTTP 请求。"""

    name: str = "HttpRequest"
    description: str = "发起任意方法的 HTTP 请求（GET/POST/PUT/DELETE/PATCH/HEAD 等）"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="method",
            description="HTTP 方法（GET/POST/PUT/DELETE/PATCH/HEAD）",
            required=False,
            accepted_types=["string"],
            default="GET",
        ),
        *_COMMON_INPUTS,
        *_BODY_INPUTS,
        InputFieldDeclaration(
            name="params",
            description="URL 查询参数（dict），会追加到 url 后",
            required=False,
            accepted_types=["dict"],
            default=None,
        ),
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        method = str(io.inputs.get("method") or "GET").upper()
        url: str = io.inputs["url"]
        params = io.inputs.get("params")
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        timeout = float(io.inputs.get("timeout") or 30)
        body_bytes, headers = _build_body_and_headers(io.inputs)
        result = _do_request(method, url, headers, body_bytes, timeout)
        _set_outputs(io, result)


# ──────────────────────────────────────────────
# 快捷动作
# ──────────────────────────────────────────────

class HttpGet(ActionBase):
    """发起 HTTP GET 请求。"""

    name: str = "HttpGet"
    description: str = "发起 HTTP GET 请求"
    inputs: list[InputFieldDeclaration] = [
        *_COMMON_INPUTS,
        InputFieldDeclaration(
            name="params",
            description="URL 查询参数（dict），会追加到 url 后",
            required=False,
            accepted_types=["dict"],
            default=None,
        ),
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        params = io.inputs.get("params")
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        timeout = float(io.inputs.get("timeout") or 30)
        headers = dict(io.inputs.get("headers") or {})
        result = _do_request("GET", url, headers, None, timeout)
        _set_outputs(io, result)


class HttpPost(ActionBase):
    """发起 HTTP POST 请求。"""

    name: str = "HttpPost"
    description: str = "发起 HTTP POST 请求，支持 JSON body、表单或原始 body"
    inputs: list[InputFieldDeclaration] = [
        *_COMMON_INPUTS,
        *_BODY_INPUTS,
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        timeout = float(io.inputs.get("timeout") or 30)
        body_bytes, headers = _build_body_and_headers(io.inputs)
        result = _do_request("POST", url, headers, body_bytes, timeout)
        _set_outputs(io, result)


class HttpPut(ActionBase):
    """发起 HTTP PUT 请求。"""

    name: str = "HttpPut"
    description: str = "发起 HTTP PUT 请求，支持 JSON body、表单或原始 body"
    inputs: list[InputFieldDeclaration] = [
        *_COMMON_INPUTS,
        *_BODY_INPUTS,
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        timeout = float(io.inputs.get("timeout") or 30)
        body_bytes, headers = _build_body_and_headers(io.inputs)
        result = _do_request("PUT", url, headers, body_bytes, timeout)
        _set_outputs(io, result)


class HttpDelete(ActionBase):
    """发起 HTTP DELETE 请求。"""

    name: str = "HttpDelete"
    description: str = "发起 HTTP DELETE 请求"
    inputs: list[InputFieldDeclaration] = [
        *_COMMON_INPUTS,
        *_BODY_INPUTS,
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        timeout = float(io.inputs.get("timeout") or 30)
        body_bytes, headers = _build_body_and_headers(io.inputs)
        result = _do_request("DELETE", url, headers, body_bytes, timeout)
        _set_outputs(io, result)


class HttpPatch(ActionBase):
    """发起 HTTP PATCH 请求。"""

    name: str = "HttpPatch"
    description: str = "发起 HTTP PATCH 请求，支持 JSON body、表单或原始 body"
    inputs: list[InputFieldDeclaration] = [
        *_COMMON_INPUTS,
        *_BODY_INPUTS,
    ]
    outputs: list[OutputFieldDeclaration] = _COMMON_OUTPUTS

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        timeout = float(io.inputs.get("timeout") or 30)
        body_bytes, headers = _build_body_and_headers(io.inputs)
        result = _do_request("PATCH", url, headers, body_bytes, timeout)
        _set_outputs(io, result)


class HttpHead(ActionBase):
    """发起 HTTP HEAD 请求，只返回响应头。"""

    name: str = "HttpHead"
    description: str = "发起 HTTP HEAD 请求，只返回响应头"
    inputs: list[InputFieldDeclaration] = _COMMON_INPUTS
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(name="status_code", description="HTTP 状态码", type="int"),
        OutputFieldDeclaration(name="headers", description="响应头 dict", type="dict"),
        OutputFieldDeclaration(name="ok", description="状态码是否 2xx", type="bool"),
    ]

    async def execute(self, io: IOPipe) -> None:
        url: str = io.inputs["url"]
        timeout = float(io.inputs.get("timeout") or 30)
        headers = dict(io.inputs.get("headers") or {})
        result = _do_request("HEAD", url, headers, None, timeout)
        io.outputs["status_code"] = result["status_code"]
        io.outputs["headers"] = result["headers"]
        io.outputs["ok"] = result["ok"]


# ──────────────────────────────────────────────
# 插件导出
# ──────────────────────────────────────────────

