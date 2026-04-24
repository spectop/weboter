import argparse
from dataclasses import asdict
import getpass
import json
import logging
import os
import textwrap
from pathlib import Path
import sys

from weboter.app.client import ServiceClientError, WorkflowServiceClient
from weboter.app.config import load_app_config
from weboter.app.panel import PanelAuthManager


DEFAULT_SERVICE_HOST = "127.0.0.1"
DEFAULT_SERVICE_PORT = 0


def _load_local_service_stack() -> tuple:
    try:
        from weboter.app.server import (
            list_service_processes,
            restart_background_service,
            serve_foreground,
            service_status,
            start_background_service,
            stop_background_service,
        )
        from weboter.app.service import WorkflowService
        from weboter.app.task_manager import TaskManager
    except ImportError as exc:
        raise RuntimeError(
            "当前安装不包含本地 service / 执行器依赖；请重新安装 `python -m pip install -e '.[service]'`"
        ) from exc
    return WorkflowService, TaskManager, serve_foreground, service_status, start_background_service, stop_background_service, restart_background_service, list_service_processes


def build_parser() -> argparse.ArgumentParser:
    config = load_app_config()
    parser = argparse.ArgumentParser(
        prog="weboter",
        description="Weboter 本地 workflow service 与 CLI 工具",
        epilog=textwrap.dedent(
            """
            快速开始:
              weboter service start
              weboter workflow --list
              weboter workflow --dir workflows --name demo_empty --execute --wait
              weboter task list
              weboter service logs --lines 50
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, help="指定 Weboter YAML 配置文件路径")
    subparsers = parser.add_subparsers(dest="command")

    service_parser = subparsers.add_parser(
        "service",
        help="启动或管理后台 service",
        description="管理 Weboter 后台 service。用于启动、停止、查看状态和查看系统日志。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter service start
                            weboter service restart
              weboter service status --json
                            weboter service ps
              weboter service logs --lines 100
              weboter service stop
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    service_parser.add_argument("action", choices=["start", "restart", "stop", "status", "logs", "ps", "refresh-plugins"])
    service_parser.add_argument("--host", default=None, help=f"service 监听地址，默认读取配置文件（当前 {config.service.host}）")
    service_parser.add_argument("--port", type=int, default=None, help=f"service 监听端口，默认读取配置文件（当前 {config.service.port}）")
    service_parser.add_argument("--lines", type=int, default=200, help="查看日志时输出的最后行数")
    service_parser.add_argument("--json", action="store_true", help="以 JSON 输出 service 结果")
    service_parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)

    env_parser = subparsers.add_parser(
        "env",
        help="管理 service 内部环境变量",
        description="管理 service 内部受管环境变量，支持点号分组，并可在 workflow 中通过 $env{group.key} 引用。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter env list
                            weboter env tree
              weboter env list --group xxx
              weboter env get xxx.username
              weboter env set xxx.username alice
                            weboter env import --path env.json
                            weboter env export --path env.json --reveal
              weboter env set xxx.password --value @secret.txt
              weboter env delete xxx.password
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    env_parser.add_argument("action", choices=["list", "tree", "get", "set", "delete", "import", "export"])
    env_parser.add_argument("name", nargs="?", help="环境变量名，例如 xxx.username")
    env_parser.add_argument("value_arg", nargs="?", help="set 时的值，或 @文件路径")
    env_parser.add_argument("--group", help="按分组查看，例如 xxx")
    env_parser.add_argument("--value", help="set 时的值，优先于位置参数")
    env_parser.add_argument("--path", type=Path, help="import/export 时使用的 JSON 文件路径")
    env_parser.add_argument("--replace", action="store_true", help="import 时整体替换原有 env store")
    env_parser.add_argument("--json", action="store_true", help="以 JSON 输出环境变量结果")
    env_parser.add_argument("--reveal", action="store_true", help="get 时显示原始值，而不是掩码")

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="管理或执行 workflow",
        description=(
            "管理或执行 workflow。\n"
            "默认情况下，未指定 --dir 时会使用 service 托管目录 .weboter/workflows。\n"
            "workflow 名称使用 service 感知的逻辑名；多层目录会映射为点号形式，例如 pack_a.pack_b.do_sth。"
        ),
        epilog=textwrap.dedent(
            """
            示例:
              weboter workflow --list
                                                        weboter workflow demo_empty --show
                                                        weboter workflow demo_empty --delete
              weboter workflow --upload workflows/demo_empty.json
                            weboter workflow demo_empty --execute --wait
                                                        weboter workflow pack_a.pack_b.do_sth --execute
                            weboter workflow demo_empty --dir workflows --execute --json
              weboter workflow --dir workflows --list --local
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_parser.add_argument("--upload", type=Path, help="上传单个 workflow 文件到本地 service 目录")
    workflow_parser.add_argument("--dir", dest="directory", type=Path, help="从指定目录读取 workflow")
    workflow_parser.add_argument("--name", help="目录模式下选择 workflow 逻辑名，例如 demo_empty 或 pack_a.pack_b.do_sth")
    workflow_parser.add_argument("workflow_name", nargs="?", help="workflow 逻辑名，也可用 --name 指定")
    workflow_parser.add_argument("--list", action="store_true", help="递归列出目录中的 workflow 逻辑名")
    workflow_parser.add_argument("--show", action="store_true", help="查看某个 workflow 的解析结果")
    workflow_parser.add_argument("--delete", action="store_true", help="删除某个 workflow 文件")
    workflow_parser.add_argument("--execute", action="store_true", help="解析后立即执行 workflow")
    workflow_parser.add_argument("--pause-before-start", action="store_true", help="提交执行时要求在第一个节点前停住")
    workflow_parser.add_argument("--breakpoints", help="提交执行时预设断点，支持 JSON 字符串或 @文件路径")
    workflow_parser.add_argument("--wait", action="store_true", help="提交执行任务后等待任务结束")
    workflow_parser.add_argument("--timeout", type=float, default=0, help="等待任务完成的超时时间，0 表示不限")
    workflow_parser.add_argument("--local", action="store_true", help="不经过后台 service，直接在当前进程执行")
    workflow_parser.add_argument("--json", action="store_true", help="以 JSON 输出 workflow 结果")

    task_parser = subparsers.add_parser(
        "task",
        help="查看和管理任务",
                description="查看历史任务、等待任务完成、读取任务日志。service 停止后仍可读取本地历史记录。task_id 支持唯一前缀匹配。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter task list
              weboter task get <task_id>
              weboter task show <task_id>
                            weboter task show 3d61013
              weboter task logs <task_id> --lines 100
              weboter task wait <task_id> --timeout 30
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    task_parser.add_argument("action", choices=["list", "get", "show", "logs", "wait"])
    task_parser.add_argument("task_id", nargs="?", help="任务 ID")
    task_parser.add_argument("--limit", type=int, default=20, help="任务列表数量")
    task_parser.add_argument("--lines", type=int, default=200, help="查看日志时输出的最后行数")
    task_parser.add_argument("--timeout", type=float, default=0, help="等待任务完成的超时时间，0 表示不限")
    task_parser.add_argument("--json", action="store_true", help="以 JSON 输出任务结果")

    session_parser = subparsers.add_parser(
        "session",
        help="查看和控制执行会话",
        description="查看执行会话、快照、workflow 摘要，并对运行中的 session 执行调试操作。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter session list
              weboter session get <session_id>
              weboter session snapshots <session_id> --limit 10
              weboter session snapshot-detail <session_id> --snapshot-index 3 --sections runtime,page
              weboter session workflow <session_id>
              weboter session workflow-node-detail <session_id> --node-id login
              weboter session runtime-value <session_id> --key '$flow{form}'
              weboter session run-node <session_id> --node @temp-node.json
              weboter session run-node <session_id> --node @temp-node.json --jump-target marker
              weboter session update-breakpoints <session_id> --breakpoints '[{"phase":"before_step","node_id":"login"}]'
              weboter session page-run-script <session_id> --code @script.py --arg '{"mode":"debug"}'
              weboter session resume <session_id>
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    session_parser.add_argument(
        "action",
        choices=[
            "list",
            "get",
            "snapshots",
            "snapshot-detail",
            "pause",
            "interrupt",
            "resume",
            "abort",
            "set-context",
            "jump-node",
            "patch-node",
            "add-node",
            "run-node",
            "workflow",
            "workflow-node-detail",
            "runtime-value",
            "update-breakpoints",
            "clear-breakpoints",
            "export-workflow",
            "page-snapshot",
            "page-run-script",
        ],
    )
    session_parser.add_argument("session_id", nargs="?", help="会话 ID")
    session_parser.add_argument("--limit", type=int, default=20, help="列表或快照摘要的返回数量")
    session_parser.add_argument("--snapshot-index", type=int, help="快照索引")
    session_parser.add_argument("--sections", help="逗号分隔的详情 section，例如 runtime,page")
    session_parser.add_argument("--reason", default="interrupt_next", help="interrupt 的原因")
    session_parser.add_argument("--key", help="上下文或 runtime key")
    session_parser.add_argument("--value", help="JSON 值，或无法解析 JSON 时按字符串处理")
    session_parser.add_argument("--node-id", help="节点 ID")
    session_parser.add_argument("--patch", help="节点 patch JSON，或 @文件路径")
    session_parser.add_argument("--node", help="节点定义 JSON，或 @文件路径")
    session_parser.add_argument("--jump-target", help="run-node 后跳转到的目标节点 ID；不传则回到原节点")
    session_parser.add_argument("--breakpoints", help="断点 JSON 数组，或 @文件路径")
    session_parser.add_argument("--breakpoint-ids", help="逗号分隔的 breakpoint id 列表")
    session_parser.add_argument("--append", action="store_true", help="update-breakpoints 时以追加模式工作，而不是替换")
    session_parser.add_argument("--path", help="导出 workflow 的目标路径")
    session_parser.add_argument("--code", help="页面脚本内容，或 @文件路径")
    session_parser.add_argument("--arg", help="页面脚本参数 JSON，或无法解析 JSON 时按字符串处理")
    session_parser.add_argument("--timeout-ms", type=int, default=5000, help="页面脚本超时，单位毫秒")
    session_parser.add_argument("--json", action="store_true", help="以 JSON 输出会话结果")

    panel_parser = subparsers.add_parser(
        "panel",
        help="管理 Web 面板单用户账号",
        description="管理 Web 面板登录账号。当前采用单用户模式，可通过 CLI 重置用户名和密码。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter panel status
              weboter panel reset-auth --username admin --password 'new-pass'
              weboter panel reset-auth --username admin
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    panel_parser.add_argument("action", choices=["status", "reset-auth"])
    panel_parser.add_argument("--username", help="reset-auth 时的新用户名")
    panel_parser.add_argument("--password", help="reset-auth 时的新密码；不传则交互输入")
    panel_parser.add_argument("--json", action="store_true", help="以 JSON 输出面板结果")

    return parser


def _load_text_arg(raw: str | None) -> str | None:
    if raw is None:
        return None
    if raw.startswith("@"):
        return Path(raw[1:]).expanduser().read_text(encoding="utf-8")
    return raw


def _load_json_arg(raw: str | None, *, allow_plain_string: bool = False):
    text = _load_text_arg(raw)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if allow_plain_string:
            return text
        raise ValueError(f"无法解析 JSON 参数: {raw}")


def _print_result(result: dict, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    secret_notice = result.get("secret_notice")
    if isinstance(secret_notice, dict) and secret_notice:
        print("Weboter secrets (首次启动提示，仅显示一次):")
        for key, value in secret_notice.items():
            print(f"- {key}: {value}")

    if result.get("status") in {"started", "already-running", "restarted"}:
        print(f"service {result['status']}: pid={result.get('pid')} {result.get('host')}:{result.get('port')}")
        return
    if result.get("status") in {"running"}:
        print(f"service running: pid={result.get('pid')} {result.get('host')}:{result.get('port')}")
        return
    if result.get("status") in {"stopped", "stop-requested", "killed"}:
        print(f"service {result['status']}: pid={result.get('pid')}")
        return
    if "task_id" in result and "status" in result:
        print(f"task {result['task_id']}: {result['status']} ({result.get('workflow_name')})")
        if result.get("error"):
            print(f"error: {result['error']}")
        return
    if "task" in result:
        task = result["task"]
        if "uploaded" in result:
            print(f"uploaded: {result['uploaded']}")
        if "resolved" in result:
            print(f"resolved: {result['resolved']}")
        print(f"task created: {task['task_id']} [{task['status']}] {task['workflow_name']}")
        return
    if "deleted" in result:
        print(f"deleted: {result['deleted']}")
        return
    if "items" in result and result["items"] and isinstance(result["items"][0], dict) and "task_id" in result["items"][0]:
        for item in result["items"]:
            print(f"{item['task_id']}  {item['status']}  {item['workflow_name']}  {item['created_at']}")
        return
    if "items" in result and result["items"] and isinstance(result["items"][0], dict) and "session_id" in result["items"][0]:
        for item in result["items"]:
            print(f"{item['session_id']}  {item.get('status')}  {item.get('current_phase')}  {item.get('current_node_id')}")
        return
    if "content" in result and "log_path" in result:
        print(f"log: {result['log_path']}")
        if result.get("content"):
            print(result["content"])
        return
    if "items" in result and result["items"] and isinstance(result["items"][0], dict) and "pgid" in result["items"][0]:
        for item in result["items"]:
            cmdline = " ".join(item.get("cmdline") or []) or item.get("comm") or ""
            print(f"{item['pid']}  ppid={item['ppid']}  pgid={item['pgid']}  state={item['state']}  kind={item.get('kind')}  {cmdline}")
        return
    if "items" in result and result["items"] and isinstance(result["items"][0], dict) and "masked_value" in result["items"][0]:
        groups = result.get("groups") or []
        if groups:
            print("groups:")
            for group in groups:
                print(f"- {group['name']} ({group['item_count']})")
        for item in result["items"]:
            print(f"{item['name']}  value={item.get('masked_value')}")
        return
    if "groups" in result and result.get("groups") and not result.get("items"):
        print("groups:")
        for group in result["groups"]:
            print(f"- {group['name']} ({group['item_count']})")
        return
    if "tree" in result and isinstance(result["tree"], dict):
        _print_env_tree(result["tree"])
        return
    if "name" in result and "value" in result:
        print(f"{result['name']}  value={result.get('value')}")
        return
    if "saved_path" in result:
        print(f"saved: {result['saved_path']}")
        return
    if "saved" in result:
        print(f"saved: {result['saved']} = {result.get('masked_value')}")
        return
    if "imported" in result:
        print(f"imported: count={result.get('item_count')} replace={result.get('replace')}")
        return
    if "panel_user" in result:
        print(f"panel user: {result['panel_user']} (updated_at={result.get('updated_at')})")
        return
    if "username" in result and "needs_reset" in result:
        print(f"panel status: username={result['username']} needs_reset={result['needs_reset']}")
        return

    if "loaded" in result and "loaded_count" in result and "error_count" in result:
        print(f"plugin refresh: loaded={result['loaded_count']} errors={result['error_count']}")
        for item in result.get("loaded") or []:
            print(f"- {item['package']} ({item['source']}) actions={item['action_count']} controls={item['control_count']}")
        for item in result.get("errors") or []:
            print(f"! {item.get('module') or item.get('package')}: {item.get('error')}")
        return

    if "uploaded" in result:
        print(f"uploaded: {result['uploaded']}")
    if "resolved" in result:
        print(f"resolved: {result['resolved']}")
    if "executed" in result:
        print(f"executed: {result['executed']}")
    for item in result.get("items", []):
        print(item)


def _tail_local_file(path: Path, lines: int) -> dict:
    if not path.is_file():
        return {"log_path": str(path), "content": ""}
    content = path.read_text(encoding="utf-8")
    return {"log_path": str(path), "content": "\n".join(content.splitlines()[-lines:])}


def _write_json_file(path: Path, payload: dict) -> dict:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved_path": str(target)}


def _print_env_tree(node: dict, depth: int = 0) -> None:
    name = node.get("name") or "<root>"
    print(f"{'  ' * depth}{name} ({node.get('item_count', 0)})")
    for child in node.get("children") or []:
        _print_env_tree(child, depth + 1)


def _build_local_task_manager(service, task_manager_cls):
    logger = logging.getLogger("weboter.cli.local")
    logger.setLevel(logging.WARNING)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return task_manager_cls(service, logger)


def _resolve_workflow_directory(args: argparse.Namespace, service) -> Path:
    if args.directory:
        return args.directory
    return service.workflow_store


def _resolve_remote_workflow_directory(args: argparse.Namespace, client: WorkflowServiceClient) -> Path:
    if args.directory:
        return args.directory
    state = client.service_state()
    return Path(state["workspace_root"]) / ".weboter" / "workflows"


def main() -> int:
    config_arg_parser = argparse.ArgumentParser(add_help=False)
    config_arg_parser.add_argument("--config", type=Path)
    config_args, _ = config_arg_parser.parse_known_args()
    if config_args.config:
        os.environ["WEBOTER_CONFIG"] = str(config_args.config.expanduser().resolve())

    parser = build_parser()
    args = parser.parse_args()
    config = load_app_config()

    if args.command == "panel":
        try:
            from weboter.app.service import WorkflowService
        except ImportError as exc:
            print(f"error: 无法加载 service 依赖: {exc}", file=sys.stderr)
            return 2
        service = WorkflowService()
        auth = PanelAuthManager(service.data_root)
        try:
            if args.action == "status":
                _print_result(auth.summary(), args.json)
                return 0
            if args.action == "reset-auth":
                username = (args.username or "").strip()
                if not username:
                    parser.error("panel reset-auth 需要 --username")
                password = args.password
                if password is None:
                    first = getpass.getpass("输入新密码: ")
                    second = getpass.getpass("再次输入新密码: ")
                    if first != second:
                        raise ValueError("两次输入的密码不一致")
                    password = first
                record = auth.reset_credentials(username, password, needs_reset=False)
                _print_result(
                    {
                        "panel_user": record.username,
                        "updated_at": record.updated_at,
                    },
                    args.json,
                )
                return 0
        except (ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "service":
        try:
            WorkflowService, _, serve_foreground, service_status, start_background_service, stop_background_service, restart_background_service, list_service_processes = _load_local_service_stack()
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        workflow_service = WorkflowService()
        client = WorkflowServiceClient(workflow_service)
        try:
            if args.action == "start":
                host = args.host or config.service.host or DEFAULT_SERVICE_HOST
                port = args.port if args.port is not None else config.service.port
                if args.foreground:
                    return serve_foreground(host, port, workflow_service)
                _print_result(start_background_service(host, port, workflow_service), args.json)
                return 0
            if args.action == "restart":
                current_state = workflow_service.read_service_state()
                host = args.host or (current_state.host if current_state and current_state.host else config.service.host or DEFAULT_SERVICE_HOST)
                if args.port is not None:
                    port = args.port
                elif current_state and current_state.port:
                    port = current_state.port
                else:
                    port = config.service.port
                _print_result(restart_background_service(host, port, workflow_service), args.json)
                return 0
            if args.action == "stop":
                _print_result(stop_background_service(workflow_service), args.json)
                return 0
            if args.action == "status":
                _print_result(service_status(workflow_service), args.json)
                return 0
            if args.action == "logs":
                try:
                    _print_result(client.service_logs(args.lines), args.json)
                except ServiceClientError:
                    _print_result(_tail_local_file(workflow_service.service_log_path, args.lines), args.json)
                return 0
            if args.action == "ps":
                try:
                    _print_result(client.service_processes(), args.json)
                except ServiceClientError:
                    _print_result(list_service_processes(workflow_service), args.json)
                return 0
            if args.action == "refresh-plugins":
                try:
                    _print_result(client.refresh_plugins(), args.json)
                except ServiceClientError:
                    _print_result(workflow_service.refresh_plugins(), args.json)
                return 0
        except (RuntimeError, ServiceClientError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "env":
        service = None
        client = WorkflowServiceClient()
        try:
            WorkflowService, _, _, _, _, _, _, _ = _load_local_service_stack()
            service = WorkflowService()
            client = WorkflowServiceClient(service)
        except RuntimeError:
            pass
        try:
            if args.action == "list":
                if service is not None:
                    _print_result(service.list_env(args.group), args.json)
                else:
                    _print_result(client.list_env(args.group), args.json)
                return 0
            if args.action == "tree":
                if service is not None:
                    _print_result(service.env_tree(args.group), args.json)
                else:
                    _print_result(client.env_tree(args.group), args.json)
                return 0
            if args.action == "import":
                if args.path is None:
                    parser.error("env import 需要 --path")
                payload = _load_json_arg(f"@{args.path}")
                if service is not None:
                    _print_result(service.import_env(payload, replace=args.replace), args.json)
                else:
                    _print_result(client.import_env(payload, replace=args.replace), args.json)
                return 0
            if args.action == "export":
                if service is not None:
                    result = service.export_env(args.group, reveal=args.reveal)
                else:
                    result = client.export_env(args.group, reveal=args.reveal)
                if args.path is not None:
                    _print_result(_write_json_file(args.path, result["data"]), args.json)
                else:
                    _print_result(result, args.json)
                return 0
            if not args.name:
                parser.error("env 命令除 list/tree/import/export 外必须提供 name")
            if args.action == "get":
                if service is not None:
                    _print_result(service.get_env(args.name, reveal=args.reveal), args.json)
                else:
                    _print_result(client.get_env(args.name, reveal=args.reveal), args.json)
                return 0
            if args.action == "set":
                raw_value = args.value if args.value is not None else args.value_arg
                if raw_value is None:
                    parser.error("env set 需要 value")
                value = _load_json_arg(raw_value, allow_plain_string=True)
                if service is not None:
                    _print_result(service.set_env(args.name, value), args.json)
                else:
                    _print_result(client.set_env(args.name, value), args.json)
                return 0
            if args.action == "delete":
                if service is not None:
                    _print_result(service.delete_env(args.name), args.json)
                else:
                    _print_result(client.delete_env(args.name), args.json)
                return 0
        except (RuntimeError, ServiceClientError, OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "task":
        workflow_service = None
        local_task_manager = None
        client = WorkflowServiceClient()
        try:
            WorkflowService, TaskManager, *_ = _load_local_service_stack()
            workflow_service = WorkflowService()
            client = WorkflowServiceClient(workflow_service)
            local_task_manager = _build_local_task_manager(workflow_service, TaskManager)
        except RuntimeError:
            pass
        try:
            if args.action == "list":
                try:
                    _print_result(client.list_tasks(args.limit), args.json)
                except ServiceClientError:
                    if local_task_manager is None:
                        raise
                    _print_result({"items": [asdict(item) for item in local_task_manager.list_tasks(args.limit)]}, args.json)
                return 0
            if not args.task_id:
                parser.error("task 命令除 list 外必须提供 task_id")
            if args.action in {"get", "show"}:
                try:
                    _print_result(client.get_task(args.task_id), args.json)
                except ServiceClientError:
                    if local_task_manager is None:
                        raise
                    _print_result(asdict(local_task_manager.get_task(args.task_id)), args.json)
                return 0
            if args.action == "logs":
                try:
                    _print_result(client.get_task_logs(args.task_id, args.lines), args.json)
                except ServiceClientError:
                    if local_task_manager is None:
                        raise
                    _print_result(local_task_manager.read_task_log(args.task_id, args.lines), args.json)
                return 0
            if args.action == "wait":
                _print_result(client.wait_for_task(args.task_id, args.timeout), args.json)
                return 0
        except (ServiceClientError, FileNotFoundError, ValueError, TimeoutError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "session":
        client = WorkflowServiceClient()
        try:
            if args.action == "list":
                _print_result(client.list_sessions(args.limit), args.json)
                return 0

            if not args.session_id:
                parser.error("session 命令除 list 外必须提供 session_id")

            if args.action == "get":
                _print_result(client.get_session(args.session_id), args.json)
                return 0
            if args.action == "snapshots":
                _print_result(client.get_session_snapshots(args.session_id, args.limit), args.json)
                return 0
            if args.action == "snapshot-detail":
                if args.snapshot_index is None:
                    parser.error("session snapshot-detail 需要 --snapshot-index")
                sections = [item.strip() for item in (args.sections or "").split(",") if item.strip()] or None
                _print_result(client.get_session_snapshot_detail(args.session_id, args.snapshot_index, sections), args.json)
                return 0
            if args.action == "pause":
                _print_result(client.pause_session(args.session_id), args.json)
                return 0
            if args.action == "interrupt":
                _print_result(client.interrupt_session(args.session_id, args.reason), args.json)
                return 0
            if args.action == "resume":
                _print_result(client.resume_session(args.session_id), args.json)
                return 0
            if args.action == "abort":
                _print_result(client.abort_session(args.session_id), args.json)
                return 0
            if args.action == "set-context":
                if not args.key:
                    parser.error("session set-context 需要 --key")
                _print_result(client.set_session_context(args.session_id, args.key, _load_json_arg(args.value, allow_plain_string=True)), args.json)
                return 0
            if args.action == "jump-node":
                if not args.node_id:
                    parser.error("session jump-node 需要 --node-id")
                _print_result(client.jump_session_node(args.session_id, args.node_id), args.json)
                return 0
            if args.action == "patch-node":
                if not args.node_id or not args.patch:
                    parser.error("session patch-node 需要 --node-id 和 --patch")
                _print_result(client.patch_session_node(args.session_id, args.node_id, _load_json_arg(args.patch)), args.json)
                return 0
            if args.action == "add-node":
                if not args.node:
                    parser.error("session add-node 需要 --node")
                _print_result(client.add_session_node(args.session_id, _load_json_arg(args.node)), args.json)
                return 0
            if args.action == "run-node":
                if not args.node:
                    parser.error("session run-node 需要 --node")
                _print_result(
                    client.run_session_temporary_node(
                        args.session_id,
                        _load_json_arg(args.node),
                        jump_to_node_id=args.jump_target,
                    ),
                    args.json,
                )
                return 0
            if args.action == "workflow":
                _print_result(client.get_session_workflow(args.session_id), args.json)
                return 0
            if args.action == "workflow-node-detail":
                if not args.node_id:
                    parser.error("session workflow-node-detail 需要 --node-id")
                _print_result(client.get_session_workflow_node(args.session_id, args.node_id), args.json)
                return 0
            if args.action == "runtime-value":
                if not args.key:
                    parser.error("session runtime-value 需要 --key")
                _print_result(client.get_session_runtime_value(args.session_id, args.key), args.json)
                return 0
            if args.action == "update-breakpoints":
                if not args.breakpoints:
                    parser.error("session update-breakpoints 需要 --breakpoints")
                _print_result(
                    client.configure_session_breakpoints(
                        args.session_id,
                        _load_json_arg(args.breakpoints),
                        replace=not args.append,
                    ),
                    args.json,
                )
                return 0
            if args.action == "clear-breakpoints":
                breakpoint_ids = [item.strip() for item in (args.breakpoint_ids or "").split(",") if item.strip()] or None
                _print_result(client.clear_session_breakpoints(args.session_id, breakpoint_ids), args.json)
                return 0
            if args.action == "export-workflow":
                if not args.path:
                    parser.error("session export-workflow 需要 --path")
                _print_result(client.export_session_workflow(args.session_id, args.path), args.json)
                return 0
            if args.action == "page-snapshot":
                _print_result(client.get_session_page(args.session_id), args.json)
                return 0
            if args.action == "page-run-script":
                if not args.code:
                    parser.error("session page-run-script 需要 --code")
                _print_result(
                    client.run_session_page_script(
                        args.session_id,
                        _load_text_arg(args.code) or "",
                        _load_json_arg(args.arg, allow_plain_string=True),
                        args.timeout_ms,
                    ),
                    args.json,
                )
                return 0
        except (ServiceClientError, FileNotFoundError, ValueError, TimeoutError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command != "workflow":
        parser.print_help()
        return 1

    if args.upload and args.directory:
        parser.error("workflow 命令不能同时指定 --upload 和 --dir")
    if args.name and args.workflow_name and args.name != args.workflow_name:
        parser.error("workflow 名称不能同时通过位置参数和 --name 指定为不同值")
    workflow_name = args.name or args.workflow_name
    if sum([bool(args.list), bool(args.show), bool(args.delete), bool(args.execute)]) > 1:
        parser.error("workflow 命令的 --list、--show、--delete、--execute 只能选择一个")
    if args.delete and args.upload:
        parser.error("workflow 删除不能和 --upload 一起使用")
    if args.wait and not args.execute:
        parser.error("--wait 只能和 --execute 一起使用")
    if (args.pause_before_start or args.breakpoints) and not args.execute:
        parser.error("--pause-before-start 和 --breakpoints 只能和 --execute 一起使用")
    if (args.show or args.delete or args.execute) and not workflow_name:
        parser.error("--show、--delete、--execute 模式需要通过位置参数或 --name 指定 workflow")
    if args.local and (args.pause_before_start or args.breakpoints):
        parser.error("--local 模式不支持 --pause-before-start 或 --breakpoints，因为本地执行不会创建 session")
    if not args.upload and not any([args.directory, args.list, workflow_name, args.show, args.delete, args.execute]):
        parser.error("workflow 命令至少需要一个操作，例如 --list、--upload、--show、--delete 或 --execute")

    workflow_breakpoints = _load_json_arg(args.breakpoints) if args.breakpoints else None

    service = None
    client = WorkflowServiceClient()
    try:
        WorkflowService, *_ = _load_local_service_stack()
        service = WorkflowService()
        client = WorkflowServiceClient(service)
    except RuntimeError:
        pass

    if args.local and service is None:
        print("error: 当前安装不包含本地 service / 执行器依赖；请重新安装 `python -m pip install -e '.[service]'`", file=sys.stderr)
        return 2

    if service is not None:
        workflow_directory = _resolve_workflow_directory(args, service)
    else:
        try:
            workflow_directory = _resolve_remote_workflow_directory(args, client)
        except ServiceClientError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        if args.upload:
            if args.local or (service is not None and not args.execute):
                _print_result(service.handle_upload_request(args.upload, args.execute), args.json)
            else:
                result = client.upload_workflow(
                    args.upload,
                    args.execute,
                    pause_before_start=args.pause_before_start,
                    breakpoints=workflow_breakpoints,
                )
                _print_result(result, args.json)
                if args.wait and result.get("task"):
                    _print_result(client.wait_for_task(result["task"]["task_id"], args.timeout), args.json)
            return 0

        if args.list:
            if args.local or (service is not None and not args.execute):
                _print_result(service.handle_directory_request(workflow_directory, workflow_name, True, False, False), args.json)
            else:
                _print_result(client.handle_directory(workflow_directory, workflow_name, True, False, False), args.json)
            return 0

        if args.delete:
            if args.local or (service is not None and not args.execute):
                _print_result(service.handle_directory_request(workflow_directory, workflow_name, False, True, False), args.json)
            else:
                _print_result(client.handle_directory(workflow_directory, workflow_name, False, True, False), args.json)
            return 0

        if args.local or (service is not None and not args.execute):
            _print_result(service.handle_directory_request(workflow_directory, workflow_name, False, False, args.execute), args.json)
        else:
            result = client.handle_directory(
                workflow_directory,
                workflow_name,
                False,
                False,
                args.execute,
                pause_before_start=args.pause_before_start,
                breakpoints=workflow_breakpoints,
            )
            _print_result(result, args.json)
            if args.wait and result.get("task"):
                _print_result(client.wait_for_task(result["task"]["task_id"], args.timeout), args.json)
        return 0
    except (FileNotFoundError, NotADirectoryError, ValueError, ServiceClientError) as exc:
        message = str(exc)
        if isinstance(exc, ServiceClientError) and args.execute and not args.local:
            message = f"{message}；可先执行 `weboter service start`，或临时使用 `--local`"
        print(f"error: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())