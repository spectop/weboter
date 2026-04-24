from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class WorkflowUploadRequest(BaseModel):
    path: str
    execute: bool = False
    pause_before_start: bool = False
    breakpoints: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowDirectoryRequest(BaseModel):
    directory: str
    name: str | None = None
    list: bool = False
    delete: bool = False
    execute: bool = False
    pause_before_start: bool = False
    breakpoints: List[Dict[str, Any]] = Field(default_factory=list)


class SessionSetContextRequest(BaseModel):
    key: str
    value: Any


class SessionInterruptRequest(BaseModel):
    reason: str = "interrupt_next"


class SessionJumpRequest(BaseModel):
    node_id: str


class SessionConfigureBreakpointsRequest(BaseModel):
    breakpoints: list[dict[str, Any]]
    replace: bool = True


class SessionClearBreakpointsRequest(BaseModel):
    breakpoint_ids: list[str] | None = None


class SessionPatchNodeRequest(BaseModel):
    node_id: str
    patch: dict[str, Any]


class SessionAddNodeRequest(BaseModel):
    node: dict[str, Any]


class SessionRunNodeRequest(BaseModel):
    node: dict[str, Any]
    jump_to_node_id: str | None = None


class SessionExportWorkflowRequest(BaseModel):
    path: str


class SessionPageEvaluateRequest(BaseModel):
    script: str
    arg: Any | None = None


class SessionPageScriptRequest(BaseModel):
    code: str
    arg: Any | None = None
    timeout_ms: int = 5000


class SessionPageGotoRequest(BaseModel):
    url: str


class SessionPageClickRequest(BaseModel):
    locator: str
    timeout: int = 5000


class SessionPageFillRequest(BaseModel):
    locator: str
    value: str
    timeout: int = 5000


class PanelLoginRequest(BaseModel):
    username: str
    password: str


class EnvSetRequest(BaseModel):
    name: str
    value: Any


class EnvImportRequest(BaseModel):
    data: dict[str, Any]
    replace: bool = False
