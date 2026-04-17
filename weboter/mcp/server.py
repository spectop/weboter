import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from weboter.app.client import WorkflowServiceClient


MCP_INSTRUCTIONS = """
Weboter 是一个通过远程 service 执行 workflow 的 MCP adapter。

使用要点：
- 先调用 service_status，确认 service.health.status 为 ok。
- workflow_list 返回的是 service 感知的逻辑名，不带 .json 后缀；多层目录会显示为点号名，例如 pack_a.pack_b.do_sth。
- 需要执行现有受管 workflow 时，优先使用 workflow_submit_managed(name=...)。
- 需要上传本地 workflow 文件时，使用 workflow_submit_upload(path=...)。
- task_* 用于查看任务结果和日志；session_* 用于运行中介入、观察快照、修改上下文、跳转节点和页面操作。
- 默认不要猜测磁盘上的真实文件路径；优先依赖 workflow_list 返回的逻辑名。
- 如果只需要观察，使用只读工具；涉及执行、页面操作或 workflow 修改时，再使用 operator/admin 能力。
""".strip()


QUICKSTART_PROMPT = """
你正在使用 Weboter MCP。

推荐工作顺序：
1. 调用 service_status 检查 service 是否可用。
2. 调用 workflow_list 查看当前 service 可感知的 workflow 逻辑名。
3. 若要执行受管 workflow，调用 workflow_submit_managed，并传入 workflow_list 返回的 name。
4. 执行后用 task_list、task_get、task_logs 跟踪结果。
5. 如果任务进入可介入阶段，再用 session_list、session_get、session_snapshots 和 session_* / session_page_* 工具处理。

命名规则：
- workflow 名称不带 .json。
- 多层目录映射为点号名称，例如 pack_a/pack_b/do_sth.json -> pack_a.pack_b.do_sth。
""".strip()


def _build_client() -> WorkflowServiceClient:
    service_url = os.environ.get("WEBOTER_SERVICE_URL", "").strip()
    if not service_url:
        raise RuntimeError("WEBOTER_SERVICE_URL 未配置")
    api_token = os.environ.get("WEBOTER_API_TOKEN", "").strip() or None
    return WorkflowServiceClient(base_url=service_url, api_token=api_token, caller_name="mcp")


def _profile_tools(profile: str) -> set[str]:
    tool_sets = {
        "readonly": {
            "service_status",
            "service_logs",
            "workflow_list",
            "task_list",
            "task_get",
            "task_logs",
            "session_list",
            "session_get",
            "session_snapshots",
        },
        "operator": {
            "service_status",
            "service_logs",
            "workflow_list",
            "workflow_submit_upload",
            "workflow_submit_managed",
            "task_list",
            "task_get",
            "task_logs",
            "session_list",
            "session_get",
            "session_snapshots",
            "session_pause",
            "session_resume",
            "session_abort",
            "session_set_context",
            "session_jump_node",
            "session_patch_node",
            "session_export_workflow",
            "session_page_snapshot",
            "session_page_evaluate",
            "session_page_goto",
            "session_page_click",
            "session_page_fill",
        },
        "admin": {
            "service_status",
            "service_logs",
            "workflow_list",
            "workflow_submit_upload",
            "workflow_submit_managed",
            "workflow_delete_managed",
            "task_list",
            "task_get",
            "task_logs",
            "session_list",
            "session_get",
            "session_snapshots",
            "session_pause",
            "session_resume",
            "session_abort",
            "session_set_context",
            "session_jump_node",
            "session_patch_node",
            "session_add_node",
            "session_export_workflow",
            "session_page_snapshot",
            "session_page_evaluate",
            "session_page_goto",
            "session_page_click",
            "session_page_fill",
        },
    }
    return tool_sets.get(profile, tool_sets["operator"])


def create_mcp_server() -> FastMCP:
    client = _build_client()
    profile = os.environ.get("WEBOTER_MCP_PROFILE", "operator").strip() or "operator"
    enabled_tools = _profile_tools(profile)
    server = FastMCP("weboter", instructions=MCP_INSTRUCTIONS)

    @server.prompt()
    def quickstart() -> str:
        """读取 Weboter 的推荐使用顺序与命名规则。"""
        return QUICKSTART_PROMPT

    def managed_workflow_directory() -> str:
        state = client.service_state()
        return f"{state['workspace_root'].rstrip('/')}" + "/.weboter/workflows"

    if "service_status" in enabled_tools:
        @server.tool()
        def service_status() -> dict[str, Any]:
            """读取 Weboter service 当前状态。"""
            state = client.service_state()
            health = client.health()
            return {
                "service": state,
                "health": health,
            }

    if "service_logs" in enabled_tools:
        @server.tool()
        def service_logs(lines: int = 200) -> dict[str, Any]:
            """读取 Weboter service 系统日志。"""
            return client.service_logs(lines)

    if "workflow_list" in enabled_tools:
        @server.tool()
        def workflow_list(directory: str | None = None) -> dict[str, Any]:
            """列出 workflow。未传 directory 时列出 service 管理目录中的 workflow。"""
            target_directory = directory or managed_workflow_directory()
            return client.handle_directory(target_directory, list_only=True)

    if "workflow_submit_upload" in enabled_tools:
        @server.tool()
        def workflow_submit_upload(path: str, execute: bool = True) -> dict[str, Any]:
            """上传一个 workflow 文件到 service，并可选立即提交执行。"""
            return client.upload_workflow(Path(path), execute=execute)

    if "workflow_submit_managed" in enabled_tools:
        @server.tool()
        def workflow_submit_managed(name: str, directory: str | None = None) -> dict[str, Any]:
            """从指定目录或 service 管理目录中选择 workflow，并提交执行。"""
            target_directory = directory or managed_workflow_directory()
            return client.handle_directory(target_directory, workflow_name=name, execute=True)

    if "workflow_delete_managed" in enabled_tools:
        @server.tool()
        def workflow_delete_managed(name: str, directory: str | None = None) -> dict[str, Any]:
            """从指定目录或 service 管理目录删除 workflow。"""
            target_directory = directory or managed_workflow_directory()
            return client.handle_directory(target_directory, workflow_name=name, delete=True)

    if "task_list" in enabled_tools:
        @server.tool()
        def task_list(limit: int = 20) -> dict[str, Any]:
            """列出最近任务。"""
            return client.list_tasks(limit)

    if "task_get" in enabled_tools:
        @server.tool()
        def task_get(task_id: str) -> dict[str, Any]:
            """读取单个任务详情，支持唯一前缀。"""
            return client.get_task(task_id)

    if "task_logs" in enabled_tools:
        @server.tool()
        def task_logs(task_id: str, lines: int = 200) -> dict[str, Any]:
            """读取任务日志，支持唯一前缀。"""
            return client.get_task_logs(task_id, lines)

    if "session_list" in enabled_tools:
        @server.tool()
        def session_list(limit: int = 20) -> dict[str, Any]:
            """列出最近执行会话。"""
            return client.list_sessions(limit)

    if "session_get" in enabled_tools:
        @server.tool()
        def session_get(session_id: str) -> dict[str, Any]:
            """读取单个执行会话详情，支持唯一前缀。"""
            return client.get_session(session_id)

    if "session_snapshots" in enabled_tools:
        @server.tool()
        def session_snapshots(session_id: str, limit: int = 20) -> dict[str, Any]:
            """读取执行会话快照。"""
            return client.get_session_snapshots(session_id, limit)

    if "session_pause" in enabled_tools:
        @server.tool()
        def session_pause(session_id: str) -> dict[str, Any]:
            """请求暂停某个执行会话。"""
            return client.pause_session(session_id)

    if "session_resume" in enabled_tools:
        @server.tool()
        def session_resume(session_id: str) -> dict[str, Any]:
            """恢复某个执行会话。"""
            return client.resume_session(session_id)

    if "session_abort" in enabled_tools:
        @server.tool()
        def session_abort(session_id: str) -> dict[str, Any]:
            """中止某个执行会话。"""
            return client.abort_session(session_id)

    if "session_set_context" in enabled_tools:
        @server.tool()
        def session_set_context(session_id: str, key: str, value: Any) -> dict[str, Any]:
            """修改执行会话上下文变量，例如 $flow{name}。"""
            return client.set_session_context(session_id, key, value)

    if "session_jump_node" in enabled_tools:
        @server.tool()
        def session_jump_node(session_id: str, node_id: str) -> dict[str, Any]:
            """将执行会话跳转到指定节点。"""
            return client.jump_session_node(session_id, node_id)

    if "session_patch_node" in enabled_tools:
        @server.tool()
        def session_patch_node(session_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
            """修改执行中 workflow 某个节点的定义。"""
            return client.patch_session_node(session_id, node_id, patch)

    if "session_add_node" in enabled_tools:
        @server.tool()
        def session_add_node(session_id: str, node: dict[str, Any]) -> dict[str, Any]:
            """向执行中 workflow 动态添加一个节点。"""
            return client.add_session_node(session_id, node)

    if "session_export_workflow" in enabled_tools:
        @server.tool()
        def session_export_workflow(session_id: str, path: str) -> dict[str, Any]:
            """导出当前执行会话中的 workflow 定义到文件。"""
            return client.export_session_workflow(session_id, path)

    if "session_page_snapshot" in enabled_tools:
        @server.tool()
        def session_page_snapshot(session_id: str) -> dict[str, Any]:
            """抓取当前页面快照，返回 HTML 和截图路径。"""
            return client.get_session_page(session_id)

    if "session_page_evaluate" in enabled_tools:
        @server.tool()
        def session_page_evaluate(session_id: str, script: str, arg: Any | None = None) -> dict[str, Any]:
            """在当前页面执行一段 Playwright evaluate 脚本。"""
            return client.evaluate_session_page(session_id, script, arg)

    if "session_page_goto" in enabled_tools:
        @server.tool()
        def session_page_goto(session_id: str, url: str) -> dict[str, Any]:
            """控制当前页面跳转到指定 URL。"""
            return client.session_page_goto(session_id, url)

    if "session_page_click" in enabled_tools:
        @server.tool()
        def session_page_click(session_id: str, locator: str, timeout: int = 5000) -> dict[str, Any]:
            """控制当前页面点击指定 locator。"""
            return client.session_page_click(session_id, locator, timeout)

    if "session_page_fill" in enabled_tools:
        @server.tool()
        def session_page_fill(session_id: str, locator: str, value: str, timeout: int = 5000) -> dict[str, Any]:
            """控制当前页面填写指定 locator。"""
            return client.session_page_fill(session_id, locator, value, timeout)

    return server


def main() -> None:
    server = create_mcp_server()
    transport = os.environ.get("WEBOTER_MCP_TRANSPORT", "stdio").strip() or "stdio"
    server.run(transport=transport)


if __name__ == "__main__":
    main()