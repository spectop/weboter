from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from weboter.app.client import WorkflowServiceClient
from weboter.app.config import load_app_config


MCP_INSTRUCTIONS = """
Weboter 是一个通过远程 service 执行 workflow 的 MCP adapter。

使用要点：
- 先调用 service_status，确认 service.health.status 为 ok。
- workflow_list 返回的是 service 感知的逻辑名，不带 .json 后缀；多层目录会显示为点号名，例如 pack_a.pack_b.do_sth。
- 需要执行现有受管 workflow 时，优先使用 workflow_submit_managed(name=...)；如果要调试首个节点，直接在提交时带上 pause_before_start 或 breakpoints。
- 需要上传本地 workflow 文件时，使用 workflow_submit_upload(path=...)；同样支持在提交时预设调试参数。
- 如果不确定环境里有哪些 action / control，先调用 action_list、control_list 看摘要，再用 action_get、control_get 读取单项参数契约。
- task_* 用于查看任务结果和日志；session_* 用于运行中介入、观察快照、配置断点、修改 workflow 和执行通用页面脚本。
- `session_snapshots` 默认只返回快照摘要和可获取 section；需要详细内容时，再调用 `session_snapshot_detail` 按 section 展开。
- `session_workflow` 默认只返回 workflow 摘要和有限节点列表；需要某个节点的完整定义时，再调用 `session_workflow_node_detail`。
- 日志类与列表类工具在 MCP 层默认只返回较小窗口；如果需要更多，再显式提高参数或分批读取。
- 默认不要猜测磁盘上的真实文件路径；优先依赖 workflow_list 返回的逻辑名。
- 如果只需要观察，使用只读工具；涉及执行、页面脚本或 workflow 修改时，再使用 operator/admin 能力。
- `pause` 适合让已停住的会话继续保持暂停；真正想“停在第一个节点前”时，应优先在 workflow_submit_* 阶段传入 `pause_before_start=True`。
""".strip()


QUICKSTART_PROMPT = """
你正在使用 Weboter MCP。

推荐工作顺序：
1. 调用 service_status 检查 service 是否可用。
2. 调用 workflow_list 查看当前 service 可感知的 workflow 逻辑名。
3. 如果只是正常执行，调用 workflow_submit_managed 或 workflow_submit_upload。
4. 如果你要调试首个节点，提交时直接传 `pause_before_start=True`；如果你要停在特定节点前，提交时直接传 `breakpoints=[{"phase": "before_step", "node_id": "..."}]`。
5. 提交结果里的 `task.session_id` 就是本次会话 ID，不需要等任务跑完再查 session。
6. 用 task_get、task_logs 跟踪任务状态；如果 session 已停住，再用 session_get、session_snapshots、session_workflow 读取第一现场。
7. 如果不确定某个 action / control 需要什么参数，先用 action_get / control_get 读取契约，再决定如何 patch workflow。
8. 需要改流程时，优先用 session_patch_node、session_add_node、session_jump_node、session_set_context。
9. 需要页面调试时，优先用 session_page_snapshot 获取 HTML/截图，再用 session_page_run_script 执行受控 Playwright 脚本。
10. 修改完成后用 session_resume 恢复，或用 session_abort 终止。

典型 debug 流程：
- 停在开始前：`workflow_submit_managed(name="demo", pause_before_start=True)`
- 停在指定节点前：`workflow_submit_managed(name="demo", breakpoints=[{"phase": "before_step", "node_id": "login"}])`
- 查 action / control 契约：`action_list()` -> `action_get("builtin.OpenPage")` / `control_get("builtin.NextNode")`
- 读取上下文：`session_get(session_id)` + `session_snapshots(session_id)` + `session_workflow(session_id)`
- 调页面：先 `session_page_snapshot(session_id)`，再 `session_page_run_script(session_id, code=...)`
- 改流程：`session_patch_node(...)` / `session_add_node(...)` / `session_jump_node(...)`
- 放行继续：`session_resume(session_id)`

命名规则：
- workflow 名称不带 .json。
- 多层目录映射为点号名称，例如 pack_a/pack_b/do_sth.json -> pack_a.pack_b.do_sth。
- 默认遵循渐进式披露：先读摘要，再按节点、section 或 key 取详情，避免一次性拉取巨量上下文。
""".strip()


DEBUG_PLAYBOOK_PROMPT = """
Weboter MCP 调试手册。

适用场景：
- 想在第一个节点执行前停住
- 想在某个特定节点前停住
- 任务已经报错，想读取第一现场并修复
- 需要动态修改 workflow 或直接调试页面

推荐顺序：
1. 确认 service 可用：`service_status()`
2. 提交执行时直接预设调试策略：
    - 首节点停住：`pause_before_start=True`
    - 指定节点停住：`breakpoints=[{"phase": "before_step", "node_id": "target"}]`
3. 从返回结果中读取 `task.session_id`
4. 用 `session_get()`、`session_snapshots()`、`session_workflow()` 建立上下文
5. 需要修改流程时，按需使用：
    - `session_set_context()`：改运行时上下文
    - `session_patch_node()`：改现有节点定义
    - `session_add_node()`：补新节点
    - `session_jump_node()`：跳转执行路径
6. 需要页面探索时：
    - 先 `session_page_snapshot()`
    - 再 `session_page_run_script()`
7. 验证完成后：
    - 继续执行：`session_resume()`
    - 放弃执行：`session_abort()`

经验规则：
- 不要先执行再补断点；优先在 `workflow_submit_*` 阶段把调试策略带上
- 不要猜 action / control 参数名；先用 `action_get()` / `control_get()` 看声明
- 不要一开始就写页面脚本；先看 `session_page_snapshot()` 返回的 HTML / 截图
- 不要直接猜 workflow 文件路径；优先用 `workflow_list()` 返回的逻辑名
""".strip()


TOOL_SELECTION_PROMPT = """
Weboter MCP 工具选择指南。

如果你不知道该用哪个工具，可以按下面分流：

1. 想确认系统是否在线
- `service_status`
- `service_logs`

2. 想找 workflow 或发起执行
- `workflow_list`
- `workflow_submit_managed`
- `workflow_submit_upload`
- `workflow_delete_managed`（仅 admin）

3. 想确认环境里有哪些 action / control 以及参数约定
- `action_list`
- `action_get`
- `control_list`
- `control_get`

4. 想跟踪任务结果
- `task_list`
- `task_get`
- `task_logs`

5. 想观察会话当前状态
- `session_list`
- `session_get`
- `session_snapshots`
- `session_workflow`
- `session_snapshot_detail`
- `session_workflow_node_detail`
- `session_runtime_value`

6. 想让执行停住或继续
- `workflow_submit_*` + `pause_before_start`
- `workflow_submit_*` + `breakpoints`
- `session_interrupt`
- `session_pause`
- `session_resume`
- `session_abort`

7. 想修改执行中的 workflow
- `session_set_context`
- `session_patch_node`
- `session_add_node`
- `session_jump_node`
- `session_export_workflow`

8. 想调试页面
- `session_page_snapshot`
- `session_page_run_script`

其中：
- `session_interrupt` 是“下一个节点前停住”
- `session_pause` 更适合已停住状态下维持暂停，不适合抢停正在快速运行的节点
- `session_page_run_script` 是通用页面调试入口，优先于堆很多 click/fill 类离散工具
""".strip()


def _build_client() -> WorkflowServiceClient:
    config = load_app_config()
    service_url = (config.mcp.service_url or "").strip()
    if not service_url:
        raise RuntimeError("WEBOTER_SERVICE_URL 未配置；外部 MCP adapter 只负责连接已启动的 Weboter service")
    api_token = config.client.api_token
    return WorkflowServiceClient(
        base_url=service_url,
        api_token=api_token,
        caller_name=config.mcp.caller_name,
    )


def _profile_tools(profile: str) -> set[str]:
    tool_sets = {
        "readonly": {
            "service_status",
            "service_logs",
            "action_list",
            "action_get",
            "control_list",
            "control_get",
            "workflow_list",
            "task_list",
            "task_get",
            "task_logs",
            "session_list",
            "session_get",
            "session_snapshots",
            "session_snapshot_detail",
            "session_workflow_node_detail",
            "session_runtime_value",
        },
        "operator": {
            "service_status",
            "service_logs",
            "action_list",
            "action_get",
            "control_list",
            "control_get",
            "workflow_list",
            "workflow_submit_upload",
            "workflow_submit_managed",
            "task_list",
            "task_get",
            "task_logs",
            "session_list",
            "session_get",
            "session_snapshots",
            "session_snapshot_detail",
            "session_pause",
            "session_interrupt",
            "session_resume",
            "session_abort",
            "session_set_context",
            "session_jump_node",
            "session_patch_node",
            "session_add_node",
            "session_workflow",
            "session_workflow_node_detail",
            "session_runtime_value",
            "session_update_breakpoints",
            "session_clear_breakpoints",
            "session_export_workflow",
            "session_page_snapshot",
            "session_page_run_script",
        },
        "admin": {
            "service_status",
            "service_logs",
            "action_list",
            "action_get",
            "control_list",
            "control_get",
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
            "session_snapshot_detail",
            "session_pause",
            "session_interrupt",
            "session_resume",
            "session_abort",
            "session_set_context",
            "session_jump_node",
            "session_patch_node",
            "session_add_node",
            "session_workflow",
            "session_workflow_node_detail",
            "session_runtime_value",
            "session_update_breakpoints",
            "session_clear_breakpoints",
            "session_export_workflow",
            "session_page_snapshot",
            "session_page_run_script",
        },
    }
    return tool_sets.get(profile, tool_sets["operator"])


def create_mcp_server() -> FastMCP:
    client = _build_client()
    profile = load_app_config().mcp.profile.strip() or "operator"
    enabled_tools = _profile_tools(profile)
    server = FastMCP("weboter", instructions=MCP_INSTRUCTIONS)

    @server.prompt()
    def quickstart() -> str:
        """Weboter MCP 快速上手：如何连通 service、提交 workflow、进入 session 调试。"""
        return QUICKSTART_PROMPT

    @server.prompt()
    def debug_playbook() -> str:
        """Weboter MCP 调试手册：如何在提交前预设断点、读取第一现场、修改 workflow 并恢复执行。"""
        return DEBUG_PLAYBOOK_PROMPT

    @server.prompt()
    def tool_selection() -> str:
        """Weboter MCP 工具选择指南：按目标选择 service、workflow、task、session 和页面调试工具。"""
        return TOOL_SELECTION_PROMPT

    def managed_workflow_directory() -> str:
        state = client.service_state()
        return f"{state['workspace_root'].rstrip('/')}" + "/.weboter/workflows"

    def clamp_limit(value: int, default: int, maximum: int) -> int:
        if value <= 0:
            return default
        return min(value, maximum)

    def clamp_lines(value: int, default: int = 50, maximum: int = 120) -> int:
        if value <= 0:
            return default
        return min(value, maximum)

    def summarize_named_items(result: dict[str, Any], limit: int) -> dict[str, Any]:
        items = result.get("items") or []
        if not isinstance(items, list):
            return result
        limited = items[:limit]
        return {
            "items": limited,
            "total_count": len(items),
            "returned_count": len(limited),
            "remaining_count": max(len(items) - len(limited), 0),
        }

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
        def service_logs(lines: int = 50) -> dict[str, Any]:
            """读取 Weboter service 系统日志。"""
            return client.service_logs(clamp_lines(lines))

    if "action_list" in enabled_tools:
        @server.tool()
        def action_list(limit: int = 50) -> dict[str, Any]:
            """列出当前环境已注册 action 的摘要。需要参数约定时，继续调用 action_get。"""
            return summarize_named_items(client.list_actions(), clamp_limit(limit, 50, 100))

    if "action_get" in enabled_tools:
        @server.tool()
        def action_get(full_name: str) -> dict[str, Any]:
            """读取单个 action 的完整契约，包括 description、inputs 和 outputs。"""
            return client.get_action(full_name)

    if "control_list" in enabled_tools:
        @server.tool()
        def control_list(limit: int = 50) -> dict[str, Any]:
            """列出当前环境已注册 control 的摘要。需要参数约定时，继续调用 control_get。"""
            return summarize_named_items(client.list_controls(), clamp_limit(limit, 50, 100))

    if "control_get" in enabled_tools:
        @server.tool()
        def control_get(full_name: str) -> dict[str, Any]:
            """读取单个 control 的完整契约，包括 description、inputs 和 outputs。"""
            return client.get_control(full_name)

    if "workflow_list" in enabled_tools:
        @server.tool()
        def workflow_list(directory: str | None = None, limit: int = 50) -> dict[str, Any]:
            """列出 workflow。未传 directory 时列出 service 管理目录中的 workflow。"""
            target_directory = directory or managed_workflow_directory()
            return summarize_named_items(client.handle_directory(target_directory, list_only=True), clamp_limit(limit, 50, 100))

    if "workflow_submit_upload" in enabled_tools:
        @server.tool()
        def workflow_submit_upload(
            path: str,
            execute: bool = True,
            pause_before_start: bool = False,
            breakpoints: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            """上传一个 workflow 文件到 service，并可选在创建 session 时预设起步即停或断点。"""
            return client.upload_workflow(
                Path(path),
                execute=execute,
                pause_before_start=pause_before_start,
                breakpoints=breakpoints,
            )

    if "workflow_submit_managed" in enabled_tools:
        @server.tool()
        def workflow_submit_managed(
            name: str,
            directory: str | None = None,
            pause_before_start: bool = False,
            breakpoints: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            """从指定目录或 service 管理目录中选择 workflow，并在提交时预设起步即停或断点。"""
            target_directory = directory or managed_workflow_directory()
            return client.handle_directory(
                target_directory,
                workflow_name=name,
                execute=True,
                pause_before_start=pause_before_start,
                breakpoints=breakpoints,
            )

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
            return client.list_tasks(clamp_limit(limit, 20, 50))

    if "task_get" in enabled_tools:
        @server.tool()
        def task_get(task_id: str) -> dict[str, Any]:
            """读取单个任务详情，支持唯一前缀。"""
            return client.get_task(task_id)

    if "task_logs" in enabled_tools:
        @server.tool()
        def task_logs(task_id: str, lines: int = 50) -> dict[str, Any]:
            """读取任务日志，支持唯一前缀。"""
            return client.get_task_logs(task_id, clamp_lines(lines))

    if "session_list" in enabled_tools:
        @server.tool()
        def session_list(limit: int = 20) -> dict[str, Any]:
            """列出最近执行会话。"""
            return client.list_sessions(clamp_limit(limit, 20, 50))

    if "session_get" in enabled_tools:
        @server.tool()
        def session_get(session_id: str) -> dict[str, Any]:
            """读取单个执行会话详情，支持唯一前缀。"""
            return client.get_session(session_id)

    if "session_snapshots" in enabled_tools:
        @server.tool()
        def session_snapshots(session_id: str, limit: int = 20) -> dict[str, Any]:
            """读取执行会话快照摘要。返回每个快照可进一步获取的 sections，而不是一次性返回全部内容。"""
            return client.get_session_snapshots(session_id, limit)

    if "session_snapshot_detail" in enabled_tools:
        @server.tool()
        def session_snapshot_detail(
            session_id: str,
            snapshot_index: int,
            sections: list[str] | None = None,
        ) -> dict[str, Any]:
            """按 snapshot index 和 sections 读取快照详情，例如 runtime、workflow、page、debug。"""
            return client.get_session_snapshot_detail(session_id, snapshot_index, sections)

    if "session_pause" in enabled_tools:
        @server.tool()
        def session_pause(session_id: str) -> dict[str, Any]:
            """请求暂停某个执行会话。"""
            return client.pause_session(session_id)

    if "session_interrupt" in enabled_tools:
        @server.tool()
        def session_interrupt(session_id: str, reason: str = "interrupt_next") -> dict[str, Any]:
            """请求在下一个节点执行前停住，用于调试时保留第一现场。"""
            return client.interrupt_session(session_id, reason)

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

    if "session_workflow" in enabled_tools:
        @server.tool()
        def session_workflow(session_id: str) -> dict[str, Any]:
            """读取当前执行会话中的 workflow 摘要。需要完整节点定义时，继续调用 session_workflow_node_detail。"""
            return client.get_session_workflow(session_id)

    if "session_workflow_node_detail" in enabled_tools:
        @server.tool()
        def session_workflow_node_detail(session_id: str, node_id: str) -> dict[str, Any]:
            """按 node_id 读取 workflow 中某个节点的完整定义。"""
            return client.get_session_workflow_node(session_id, node_id)

    if "session_runtime_value" in enabled_tools:
        @server.tool()
        def session_runtime_value(session_id: str, key: str) -> dict[str, Any]:
            """按 key 读取当前运行时中的单个值，并返回受限预览。"""
            return client.get_session_runtime_value(session_id, key)

    if "session_update_breakpoints" in enabled_tools:
        @server.tool()
        def session_update_breakpoints(
            session_id: str,
            breakpoints: list[dict[str, Any]],
            replace: bool = True,
        ) -> dict[str, Any]:
            """配置执行断点。断点支持 phase、node_id、node_name 和 once。"""
            return client.configure_session_breakpoints(session_id, breakpoints, replace=replace)

    if "session_clear_breakpoints" in enabled_tools:
        @server.tool()
        def session_clear_breakpoints(session_id: str, breakpoint_ids: list[str] | None = None) -> dict[str, Any]:
            """清除全部断点，或按 breakpoint id 选择性清除。"""
            return client.clear_session_breakpoints(session_id, breakpoint_ids)

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

    if "session_page_run_script" in enabled_tools:
        @server.tool()
        def session_page_run_script(
            session_id: str,
            code: str,
            arg: Any | None = None,
            timeout_ms: int = 5000,
        ) -> dict[str, Any]:
            """执行一段受控的 Playwright 页面脚本，返回脚本结果和最新页面快照。"""
            return client.run_session_page_script(session_id, code, arg, timeout_ms)

    return server


def main() -> None:
    server = create_mcp_server()
    transport = load_app_config().mcp.transport.strip() or "stdio"
    server.run(transport=transport)


if __name__ == "__main__":
    main()