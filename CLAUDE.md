# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Weboter is a Python workflow automation framework for browser交互. Workflows are defined as JSON files containing nodes that execute actions with flow control.

## Architecture

The framework follows a role-based architecture with these core components:

### Role Layer (`weboter/role/`)
- **ActionBase**: Base class for all actions (operations performed on web pages)
- **ControlBase**: Base class for controls (flow control logic that determines next node)
- **IOBase**: Base for input/output handling
- **interface.py**: Defines `InputFieldDeclaration` and `OutputFieldDeclaration` for schema

### Core Engine (`weboter/core/engine/`)
- **ActionManager**: Enhanced with type safety and package lifecycle management:
  - Strongly typed container (Dict[str, ActionPackage])
  - `replace_package()` with pre-existence check
  - New `unregister_package()` support
  - Improved docstrings
- **ControlManager**: Upgraded with similar enhancements:
  - Type-safe implementation
  - Verified package existence in `replace_package()`
  - Added `unregister_package()` method
  - Detailed method documentation
- **Job**: Encapsulates a single workflow execution
- **Runtime**: Provides execution context for a job
- **Scheduler**: Manages workflow scheduling
- **Executor**: (Placeholder) Executes workflow nodes

### Model Layer (`weboter/model/`)
- **Model**: Defines Node and Link data structures for workflow graphs
- **DataContext**: Manages data flow and context during execution

### Builtin Actions and Controls (`weboter/builtin/`)
- **Actions**: OpenPage, ClickItem, FillInput
- **Controls**: NextNode

Extending: Add new actions/controls by creating classes in `builtin/` and registering them in `builtin/__init__.py`:
```python
package_name = "builtin"
actions = [OpenPage, ClickItem, FillInput]  # add new ones here
controls = [NextNode]  # add new ones here

# 动态更新机制（需包已存在）:
action_manager.replace_package("builtin", actions)  # replace existing
control_manager.register_package("custom", [CustomControl])  # register new

# 卸载不再需要的包:
action_manager.unregister_package("deprecated")
control_manager.unregister_package("legacy")
```

## Workflow Format

Workflows are JSON files in `workflows/` with this structure:
```json
{
    "name": "Workflow Name",
    "nodes": [
        {
            "id": "node1",
            "action": "builtin.OpenPage",
            "input": {"url": "https://example.com"},
            "control": "builtin.NextNode",
            "params": {"next_node": "node2"}
        }
    ]
}
```

Environment variables are referenced as `$env{variable_name}` in input values.

## Naming Convention

Action and control registration uses dotted names: `builtin.OpenPage`, `custom.MyAction`. The first part is the package module name (set in `package_name` variable), the second is the class name.
