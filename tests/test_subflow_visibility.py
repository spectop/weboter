import unittest
import sys
import types


if "playwright.async_api" not in sys.modules:
    async_api_module = types.ModuleType("playwright.async_api")

    class _StubPlaywright:
        pass

    class _StubBrowser:
        pass

    class _StubBrowserContext:
        pass

    class _StubPage:
        pass

    class _StubLocator:
        pass

    async_api_module.Playwright = _StubPlaywright
    async_api_module.Browser = _StubBrowser
    async_api_module.BrowserContext = _StubBrowserContext
    async_api_module.Page = _StubPage
    async_api_module.Locator = _StubLocator
    playwright_module = types.ModuleType("playwright")
    playwright_module.async_api = async_api_module
    sys.modules["playwright"] = playwright_module
    sys.modules["playwright.async_api"] = async_api_module

from weboter.core.engine.excutor import Executor
from weboter.public.model import Flow


class SubflowVisibilityTests(unittest.TestCase):
    def test_child_flow_can_see_sibling_from_parent_scope(self):
        sub_c = Flow(flow_id="sub_c", name="SubC", description="")
        sub_a = Flow(flow_id="sub_a", name="SubA", description="", sub_flows=[sub_c])
        sub_b = Flow(flow_id="sub_b", name="SubB", description="")
        main = Flow(
            flow_id="main",
            name="Main",
            description="",
            sub_flows=[sub_a, sub_b],
        )

        parent_executor = Executor()
        parent_executor.load_workflow(main)

        child_executor = Executor(
            ancestor_subflow_scopes=[dict(parent_executor._current_subflow_scope)]
        )
        child_executor.load_workflow(sub_b)

        resolved = child_executor.get_subflow("sub_a")
        self.assertEqual(resolved.flow_id, "sub_a")

    def test_child_flow_cannot_see_sibling_private_descendant(self):
        sub_c = Flow(flow_id="sub_c", name="SubC", description="")
        sub_a = Flow(flow_id="sub_a", name="SubA", description="", sub_flows=[sub_c])
        sub_b = Flow(flow_id="sub_b", name="SubB", description="")
        main = Flow(
            flow_id="main",
            name="Main",
            description="",
            sub_flows=[sub_a, sub_b],
        )

        parent_executor = Executor()
        parent_executor.load_workflow(main)

        child_executor = Executor(
            ancestor_subflow_scopes=[dict(parent_executor._current_subflow_scope)]
        )
        child_executor.load_workflow(sub_b)

        with self.assertRaisesRegex(ValueError, "sub_c"):
            child_executor.get_subflow("sub_c")
