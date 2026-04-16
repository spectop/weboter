import argparse
import json
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weboter")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="启动或管理后台 service")
    serve_parser.add_argument("action", choices=["start", "stop", "status"])
    serve_parser.add_argument("--host", default=DEFAULT_SERVICE_HOST, help="service 监听地址")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_SERVICE_PORT, help="service 监听端口，默认自动分配")
    serve_parser.add_argument("--json", action="store_true", help="以 JSON 输出 service 结果")
    serve_parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)

    workflow_parser = subparsers.add_parser("workflow", help="管理或执行 workflow")
    workflow_parser.add_argument("--upload", type=Path, help="上传单个 workflow 文件到本地 service 目录")
    workflow_parser.add_argument("--dir", dest="directory", type=Path, help="从指定目录读取 workflow")
    workflow_parser.add_argument("--name", help="目录模式下选择具体 workflow 文件名，可省略 .json")
    workflow_parser.add_argument("--list", action="store_true", help="列出目录中的 workflow 文件")
    workflow_parser.add_argument("--execute", action="store_true", help="解析后立即执行 workflow")
    workflow_parser.add_argument("--local", action="store_true", help="不经过后台 service，直接在当前进程执行")
    workflow_parser.add_argument("--json", action="store_true", help="以 JSON 输出 workflow 结果")

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

    if "uploaded" in result:
        print(f"uploaded: {result['uploaded']}")
    if "resolved" in result:
        print(f"resolved: {result['resolved']}")
    if "executed" in result:
        print(f"executed: {result['executed']}")
    for item in result.get("items", []):
        print(item)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        workflow_service = WorkflowService()
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
        except (RuntimeError, ServiceClientError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command != "workflow":
        parser.print_help()
        return 1

    if bool(args.upload) == bool(args.directory):
        parser.error("workflow 命令必须且只能指定 --upload 或 --dir 其中之一")

    service = WorkflowService()
    client = WorkflowServiceClient(service)

    try:
        if args.upload:
            if args.local:
                _print_result(service.handle_upload_request(args.upload, args.execute), args.json)
            else:
                _print_result(client.upload_workflow(args.upload, args.execute), args.json)
            return 0

        if args.list:
            if args.local:
                _print_result(service.handle_directory_request(args.directory, args.name, True, False), args.json)
            else:
                _print_result(client.handle_directory(args.directory, args.name, True, False), args.json)
            return 0

        if args.local:
            _print_result(service.handle_directory_request(args.directory, args.name, False, args.execute), args.json)
        else:
            _print_result(client.handle_directory(args.directory, args.name, False, args.execute), args.json)
        return 0
    except (FileNotFoundError, NotADirectoryError, ValueError, ServiceClientError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2