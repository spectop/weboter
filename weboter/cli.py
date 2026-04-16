import argparse
from dataclasses import asdict
import json
import logging
import textwrap
from pathlib import Path
import sys

from weboter.app.client import ServiceClientError, WorkflowServiceClient
from weboter.app.server import (
    DEFAULT_SERVICE_HOST,
    DEFAULT_SERVICE_PORT,
    serve_foreground,
    service_status,
    start_background_service,
    stop_background_service,
)
from weboter.app.service import WorkflowService
from weboter.app.task_manager import TaskManager


def build_parser() -> argparse.ArgumentParser:
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
    subparsers = parser.add_subparsers(dest="command")

    service_parser = subparsers.add_parser(
        "service",
        help="启动或管理后台 service",
        description="管理 Weboter 后台 service。用于启动、停止、查看状态和查看系统日志。",
        epilog=textwrap.dedent(
            """
            示例:
              weboter service start
              weboter service status --json
              weboter service logs --lines 100
              weboter service stop
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    service_parser.add_argument("action", choices=["start", "stop", "status", "logs"])
    service_parser.add_argument("--host", default=DEFAULT_SERVICE_HOST, help="service 监听地址")
    service_parser.add_argument("--port", type=int, default=DEFAULT_SERVICE_PORT, help="service 监听端口，默认自动分配")
    service_parser.add_argument("--lines", type=int, default=200, help="查看日志时输出的最后行数")
    service_parser.add_argument("--json", action="store_true", help="以 JSON 输出 service 结果")
    service_parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="管理或执行 workflow",
        description=(
            "管理或执行 workflow。\n"
            "默认情况下，未指定 --dir 时会使用 service 托管目录 .weboter/workflows。"
        ),
        epilog=textwrap.dedent(
            """
            示例:
              weboter workflow --list
              weboter workflow --upload workflows/demo_empty.json
              weboter workflow --name demo_empty --execute --wait
              weboter workflow --dir workflows --name demo_empty --execute --json
              weboter workflow --dir workflows --list --local
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_parser.add_argument("--upload", type=Path, help="上传单个 workflow 文件到本地 service 目录")
    workflow_parser.add_argument("--dir", dest="directory", type=Path, help="从指定目录读取 workflow")
    workflow_parser.add_argument("--name", help="目录模式下选择具体 workflow 文件名，可省略 .json")
    workflow_parser.add_argument("--list", action="store_true", help="列出目录中的 workflow 文件")
    workflow_parser.add_argument("--execute", action="store_true", help="解析后立即执行 workflow")
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
              weboter task show <task_id>
                            weboter task show 3d61013
              weboter task logs <task_id> --lines 100
              weboter task wait <task_id> --timeout 30
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    task_parser.add_argument("action", choices=["list", "show", "logs", "wait"])
    task_parser.add_argument("task_id", nargs="?", help="任务 ID")
    task_parser.add_argument("--limit", type=int, default=20, help="任务列表数量")
    task_parser.add_argument("--lines", type=int, default=200, help="查看日志时输出的最后行数")
    task_parser.add_argument("--timeout", type=float, default=0, help="等待任务完成的超时时间，0 表示不限")
    task_parser.add_argument("--json", action="store_true", help="以 JSON 输出任务结果")

    return parser


def _print_result(result: dict, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if result.get("status") in {"started", "already-running"}:
        print(f"service {result['status']}: pid={result.get('pid')} {result.get('host')}:{result.get('port')}")
        return
    if result.get("status") in {"running"}:
        print(f"service running: pid={result.get('pid')} {result.get('host')}:{result.get('port')}")
        return
    if result.get("status") in {"stopped", "stop-requested"}:
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
    if "items" in result and result["items"] and isinstance(result["items"][0], dict) and "task_id" in result["items"][0]:
        for item in result["items"]:
            print(f"{item['task_id']}  {item['status']}  {item['workflow_name']}  {item['created_at']}")
        return
    if "content" in result and "log_path" in result:
        print(f"log: {result['log_path']}")
        if result.get("content"):
            print(result["content"])
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


def _build_local_task_manager(service: WorkflowService) -> TaskManager:
    logger = logging.getLogger("weboter.cli.local")
    logger.setLevel(logging.WARNING)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return TaskManager(service, logger)


def _resolve_workflow_directory(args: argparse.Namespace, service: WorkflowService) -> Path:
    if args.directory:
        return args.directory
    return service.workflow_store


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        workflow_service = WorkflowService()
        client = WorkflowServiceClient(workflow_service)
        try:
            if args.action == "start":
                if args.foreground:
                    return serve_foreground(args.host, args.port, workflow_service)
                _print_result(start_background_service(args.host, args.port, workflow_service), args.json)
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
        except (RuntimeError, ServiceClientError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "task":
        workflow_service = WorkflowService()
        client = WorkflowServiceClient(workflow_service)
        local_task_manager = _build_local_task_manager(workflow_service)
        try:
            if args.action == "list":
                try:
                    _print_result(client.list_tasks(args.limit), args.json)
                except ServiceClientError:
                    _print_result({"items": [asdict(item) for item in local_task_manager.list_tasks(args.limit)]}, args.json)
                return 0
            if not args.task_id:
                parser.error("task 命令除 list 外必须提供 task_id")
            if args.action == "show":
                try:
                    _print_result(client.get_task(args.task_id), args.json)
                except ServiceClientError:
                    _print_result(asdict(local_task_manager.get_task(args.task_id)), args.json)
                return 0
            if args.action == "logs":
                try:
                    _print_result(client.get_task_logs(args.task_id, args.lines), args.json)
                except ServiceClientError:
                    _print_result(local_task_manager.read_task_log(args.task_id, args.lines), args.json)
                return 0
            if args.action == "wait":
                _print_result(client.wait_for_task(args.task_id, args.timeout), args.json)
                return 0
        except (ServiceClientError, FileNotFoundError, ValueError, TimeoutError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command != "workflow":
        parser.print_help()
        return 1

    if args.upload and args.directory:
        parser.error("workflow 命令不能同时指定 --upload 和 --dir")
    if not args.upload and not any([args.directory, args.list, args.name, args.execute]):
        parser.error("workflow 命令至少需要一个操作，例如 --list、--upload 或 --execute")

    service = WorkflowService()
    client = WorkflowServiceClient(service)
    workflow_directory = _resolve_workflow_directory(args, service)

    try:
        if args.upload:
            if args.local or not args.execute:
                _print_result(service.handle_upload_request(args.upload, args.execute), args.json)
            else:
                result = client.upload_workflow(args.upload, args.execute)
                _print_result(result, args.json)
                if args.wait and result.get("task"):
                    _print_result(client.wait_for_task(result["task"]["task_id"], args.timeout), args.json)
            return 0

        if args.list:
            if args.local or not args.execute:
                _print_result(service.handle_directory_request(workflow_directory, args.name, True, False), args.json)
            else:
                _print_result(client.handle_directory(workflow_directory, args.name, True, False), args.json)
            return 0

        if args.local or not args.execute:
            _print_result(service.handle_directory_request(workflow_directory, args.name, False, args.execute), args.json)
        else:
            result = client.handle_directory(workflow_directory, args.name, False, args.execute)
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