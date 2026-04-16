import argparse
from pathlib import Path
import sys

from weboter.app.service import WorkflowService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weboter")
    subparsers = parser.add_subparsers(dest="command")

    workflow_parser = subparsers.add_parser("workflow", help="管理或执行 workflow")
    workflow_parser.add_argument("--upload", type=Path, help="上传单个 workflow 文件到本地 service 目录")
    workflow_parser.add_argument("--dir", dest="directory", type=Path, help="从指定目录读取 workflow")
    workflow_parser.add_argument("--name", help="目录模式下选择具体 workflow 文件名，可省略 .json")
    workflow_parser.add_argument("--list", action="store_true", help="列出目录中的 workflow 文件")
    workflow_parser.add_argument("--execute", action="store_true", help="解析后立即执行 workflow")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command != "workflow":
        parser.print_help()
        return 1

    if bool(args.upload) == bool(args.directory):
        parser.error("workflow 命令必须且只能指定 --upload 或 --dir 其中之一")

    service = WorkflowService()

    try:
        if args.upload:
            resolution = service.upload_workflow(args.upload)
            print(f"uploaded: {resolution.managed_path}")
            if args.execute:
                service.run_workflow(resolution.source_path)
                print(f"executed: {resolution.source_path}")
            return 0

        if args.list:
            workflows = service.list_directory_workflows(args.directory)
            for workflow in workflows:
                print(workflow)
            return 0

        resolution = service.resolve_from_directory(args.directory, args.name)
        print(f"resolved: {resolution.source_path}")
        if args.execute:
            service.run_workflow(resolution.source_path)
            print(f"executed: {resolution.source_path}")
        return 0
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2