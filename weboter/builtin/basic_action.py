import logging

from weboter.public.contracts import *
import playwright.async_api as pw

try:
    from playwright_stealth import Stealth
except Exception:
    Stealth = None
# async_playwright, Browser, Page


class SubFlow(ActionBase):
    """Action to execute a sub flow."""
    name: str = "SubFlow"
    description: str = "Execute a sub flow defined in a separate file"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="flow_id",
            description="The ID of the sub flow to execute",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="data_in",
            description="A list of VarPicker to specify which variables to pass to the sub flow, src -> $flow.dst",
            required=False,
            accepted_types=["list"],
            default=[]
        ),
        InputFieldDeclaration(
            name="data_out",
            description="A list of VarPicker to specify which variables to extract from the sub flow after execution, src -> $output.dst",
            required=False,
            accepted_types=["list"],
            default=[]
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, io: IOPipe):
        executor = io.executor
        if not executor:
            raise ValueError("Executor is required in IOPipe context to execute sub flow.")
        if not hasattr(executor, "sub_flow_func") or not callable(executor.sub_flow_func):
            raise ValueError("Executor does not have a callable 'sub_flow_func' method to execute sub flow.")
        flow_id = io.inputs.get("flow_id")
        if not flow_id:
            raise ValueError("Input 'flow_id' is required to execute sub flow.")
        await executor.sub_flow_func(io)

class OpenBrowser(ActionBase):
    """Action to open a web browser instance."""
    name: str = "OpenBrowser"
    description: str = "Open a web browser instance"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="browser_type",
            description="Type of the browser to open (chromium, firefox, webkit)",
            required=False,
            accepted_types=["string"],
            default="chromium"
        ),
        InputFieldDeclaration(
            name="headless",
            description="Whether to run browser in headless mode",
            required=False,
            accepted_types=["boolean"],
            default=True
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="browser",
            description="The opened browser instance",
            type="Browser"
        )
    ]

    async def execute(self, io: IOPipe):
        inputs = io.inputs
        browser_type = inputs.get("browser_type")
        headless = inputs.get("headless", True)

        pw_instance = await pw.async_playwright().start()

        if browser_type == "chromium":
            browser = await pw_instance.chromium.launch(headless=headless)
        elif browser_type == "firefox":
            browser = await pw_instance.firefox.launch(headless=headless)
        elif browser_type == "webkit":
            browser = await pw_instance.webkit.launch(headless=headless)
        else:
            raise ValueError(f"Unsupported browser type: {browser_type}")
        
        browser_context = await browser.new_context()
        if Stealth is not None:
            stealth = Stealth()
            await stealth.apply_stealth_async(browser_context)

        io.outputs['browser'] = browser
        # 特殊变量会被额外处理
        io.outputs['__pw_inst__'] = pw_instance
        io.outputs['__browser__'] = browser
        io.outputs['__browser_context__'] = browser_context

class OpenPage(ActionBase):
    """Action to open a web page given a URL."""
    name: str = "OpenPage"
    description: str = "Open a web page by URL"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="url",
            description="The URL of the web page to open",
            required=True,
            accepted_types=["string"]
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="page",
            description="The opened web page object",
            type="WebPage"
        )
    ]

    async def execute(self, io: IOPipe):
        inputs = io.inputs
        url = inputs.get("url")
        if not url:
            raise ValueError("Input 'url' is required.")
        if not io.browser:
            raise ValueError("Browser instance is required in context.")
        if not isinstance(io.browser, pw.BrowserContext):
            raise ValueError("Browser in context is not a valid BrowserContext object.")
        
        page = await io.browser.new_page()
        await page.goto(url)
        
        output = io.outputs
        if not output.get("pages"):
            output["pages"] = []
        if not isinstance(output["pages"], list):
            raise ValueError("Output 'pages' must be a list.")
        
        io.outputs['page'] = page
        # 特殊变量会被额外处理
        io.outputs['__page__'] = page

class ClickItem(ActionBase):
    """Action to click an item on the web page given a locator."""
    name: str = "ClickItem"
    description: str = "Click an item on the web page by locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The CSS locator of the item to click",
            required=False,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="locators",
            description="候选 locator 列表（LocatorDefine 数组），按顺序逐一尝试，任一成功即停止。与 locator 字段互补，适合动态页面。",
            required=False,
            accepted_types=["LocatorDefine[]"]
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Maximum time to wait for the selector (in milliseconds)",
            required=False,
            accepted_types=["integer"],
            default=5000
        ),
        InputFieldDeclaration(
            name="scope",
            description="The scope to search for the locator, can be 'page' or a variable reference to a WebElement",
            required=False,
            accepted_types=["string"],
            default="page"
        ),
        InputFieldDeclaration(
            name="no_error",
            description="Set True make this action become ClickIfExists, which will not raise error even the element is not found",
            required=False,
            accepted_types=["boolean"],
            default=False
        ),
        InputFieldDeclaration(
            name="force",
            description="Whether to force the click even if the target is covered by another element",
            required=False,
            accepted_types=["boolean"],
            default=False
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, io: IOPipe):
        inputs = io.inputs

        scope = inputs.get("scope", "page")
        if "locator" not in inputs and "locators" not in inputs:
            raise ValueError("Input 'locator' or 'locators' is required.")

        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        if scope == "page":
            page = io.page
            if not page:
                raise ValueError("Current page is required in context.")
            if not isinstance(page, pw.Page):
                raise ValueError("Current page in context is not a valid Page object.")
            scope = page

        no_error = inputs.get("no_error", False)
        force = inputs.get("force", False)

        # 构建候选 locator 列表：先从 locators，再从 locator
        raw_locators: list = []
        if inputs.get("locators"):
            raw_locators.extend(inputs["locators"])
        if inputs.get("locator") is not None:
            raw_locators.append(inputs["locator"])

        if len(raw_locators) == 1:
            # 单候选直接执行，保持原有行为
            element = utils.get_locator(scope, LocatorDefine.deserialize(raw_locators[0]))
            if no_error:
                try:
                    await element.click(timeout=timeout, force=force)
                except pw.TimeoutError:
                    pass
            else:
                await element.click(timeout=timeout, force=force)
        else:
            # 多候选：逐一尝试，全部失败时按 no_error 决定是否抛出
            per_timeout = max(1000, timeout // len(raw_locators))
            last_error: Exception | None = None
            for raw in raw_locators:
                element = utils.get_locator(scope, LocatorDefine.deserialize(raw))
                try:
                    await element.click(timeout=per_timeout, force=force)
                    last_error = None
                    break
                except pw.TimeoutError as exc:
                    last_error = exc
            if last_error is not None and not no_error:
                raise last_error

class FillInput(ActionBase):
    """Action to fill an input field on the web page given a locator."""
    name: str = "FillInput"
    description: str = "Fill an input field on the web page by locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The CSS locator of the input field to fill",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="text",
            description="The text to fill into the input field",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Maximum time to wait for the selector (in milliseconds)",
            required=False,
            accepted_types=["integer"],
            default=5000
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, io: IOPipe):
        inputs = io.inputs

        if "locator" not in inputs or "text" not in inputs:
            raise ValueError("Input 'locator' and 'text' are required.")

        page = io.page
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        locator = LocatorDefine.deserialize(inputs["locator"])
        text = inputs["text"]
        element = utils.get_locator(page, locator)
        await element.fill(text, timeout=timeout)

class WaitElement(ActionBase):
    """Action to wait for an element to appear on the web page given a locator."""
    name: str = "WaitElement"
    description: str = "Wait for an element on the web page by locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The CSS locator of the element to wait for",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Maximum time to wait for the selector (in milliseconds)",
            required=False,
            accepted_types=["integer"],
            default=5000
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="element_found",
            description="Whether the element was found within the timeout",
            type="boolean"
        )
    ]

    async def execute(self, io: IOPipe):
        inputs = io.inputs

        if "locator" not in inputs:
            raise ValueError("Input 'locator' is required.")

        page = io.page
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        locator = LocatorDefine.deserialize(inputs.get("locator"))
        element = utils.get_locator(page, locator)

        try:
            await element.wait_for(state="visible", timeout=timeout)
            io.outputs["element_found"] = True
        except pw.TimeoutError:
            io.outputs["element_found"] = False

class SleepFor(ActionBase):
    """Action to pause execution for a specified duration."""
    name: str = "SleepFor"
    description: str = "Pause execution for a specified duration in seconds"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="duration",
            description="Duration to sleep in seconds",
            required=True,
            accepted_types=["number"],
            default=3
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, io: IOPipe):
        import asyncio
        inputs = io.inputs
        duration = inputs.get("duration")
        if duration is None:
            raise ValueError("Input 'duration' is required.")
        if not isinstance(duration, (int, float)):
            raise ValueError("Input 'duration' must be a number.")
        
        await asyncio.sleep(duration)

class EmptyAction(ActionBase):
    """A no-op action that does nothing."""
    name: str = "EmptyAction"
    description: str = "An action that does nothing"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="message",
            description="An optional message to log",
            required=False,
            accepted_types=["string"],
            default=""
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, io: IOPipe):
        message = io.inputs.get("message", "")
        if message:
            io.logger.info(f"   EmptyAction: {message}")

class ExtractData(ActionBase):
    """Action to get data from the web page using a locator."""
    name: str = "ExtractData"
    description: str = "Get data from the web page using a locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The locator of the element to get data from",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="data_source",
            description="The type of data to extract (text, html, attr)",
            required=False,
            accepted_types=["string"],
            default="text"
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Maximum time to wait for the selector (in milliseconds)",
            required=False,
            accepted_types=["integer"],
            default=5000
        ),
        InputFieldDeclaration(
            name="scope",
            description="The scope to search for the locator, can be 'page' or a variable reference to a WebElement",
            required=False,
            accepted_types=["string"],
            default="page"
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="data",
            description="The extracted data from the located element",
            type="string"
        )
    ]

    async def execute(self, io: IOPipe):
        inputs = io.inputs
        
        scope = inputs.get("scope", "page")
        if "locator" not in inputs:
            raise ValueError("Input 'locator' is required.")

        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000
        
        data_source = inputs.get("data_source", "text")

        if scope == "page":
            page = io.page
            if not page:
                raise ValueError("Current page is required in context.")
            if not isinstance(page, pw.Page):
                raise ValueError("Current page in context is not a valid Page object.")
            scope = page
        else:
            pass

        locator = LocatorDefine.deserialize(inputs["locator"])
        element = utils.get_locator(scope, locator)
        await element.wait_for(state="visible", timeout=timeout)
        
        if data_source == "text":
            data = await element.inner_text()
        elif data_source == "html":
            data = await element.inner_html()
        elif data_source.startswith("attr:"):
            attr_name = data_source.split(":", 1)[1]
            data = await element.get_attribute(attr_name)
        else:
            raise ValueError(f"Unsupported data source type: {data_source}")

        io.logger.debug(f"   Extracted data: {data}")
        io.outputs["data"] = data

class GetElement(ActionBase):
    """Action to get a web element using a locator."""
    name: str = "GetElement"
    description: str = "Get a web element using a locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The locator of the element to get",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Maximum time to wait for the selector (in milliseconds)",
            required=False,
            accepted_types=["integer"],
            default=5000
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="element",
            description="The located web element",
            type="WebElement"
        )
    ]

    async def execute(self, io: IOPipe):
        inputs = io.inputs
        
        if not inputs.get("locator"):
            raise ValueError("Input 'locator' is required.")
        locator = LocatorDefine.deserialize(inputs["locator"])

        page = io.page
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        element = utils.get_locator(page, locator)
        await element.wait_for(state="visible", timeout=timeout)
        io.outputs["element"] = element

class NextElement(ActionBase):
    """
    Action to get the next sibling element of a given element.
    If the current element is the last child, it will return null.
    """
    name: str = "NextElement"
    description: str = "Get the next sibling element of a given element"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="element",
            description="The web element to find the next sibling of",
            required=True,
            accepted_types=["Locator"]
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="next_element",
            description="The next sibling web element",
            type="Locator"
        )
    ]

    async def execute(self, io: IOPipe):
        element = io.inputs.get("element")
        if not element:
            raise ValueError("Input 'element' is required.")
        if not isinstance(element, pw.Locator):
            raise ValueError("Input 'element' must be a valid Locator object.")
        
        next_element = element.locator("xpath=following-sibling::*[1]")
        count = await next_element.count()
        if count == 0:
            io.outputs["next_element"] = None
        else:
            io.outputs["next_element"] = next_element

class PyEvalAction(ActionBase):
    """[Not Safe] Action to execute custom Python code."""
    name: str = "PyEvalAction"
    description: str = "Execute custom Python code with access to the IOPipe context"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="expr",
            description="The Python expression to evaluate",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="param1",
            description="Optional parameter 1",
            required=False,
            accepted_types=["any"]
        ),
        InputFieldDeclaration(
            name="param2",
            description="Optional parameter 2",
            required=False,
            accepted_types=["any"]
        ),
        InputFieldDeclaration(
            name="param3",
            description="Optional parameter 3",
            required=False,
            accepted_types=["any"]
        ),
        InputFieldDeclaration(
            name="param4",
            description="Optional parameter 4",
            required=False,
            accepted_types=["any"]
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="result",
            description="The result of the evaluated expression",
            type="any"
        )
    ]

    async def execute(self, io: IOPipe):
        expr = io.inputs.get("expr")
        if not expr:
            raise ValueError("Input 'expr' is required.")
        
        # Provide the IOPipe context to the expression
        local_context = {
            "io": io,
            "inputs": io.inputs,
            "outputs": io.outputs,
            "browser": io.browser,
            "page": io.page
        }
        # Add optional params to the local context
        for i in range(1, 5):
            param_name = f"param{i}"
            local_context[param_name] = io.inputs.get(param_name)

        # Evaluate the expression and store the result
        result = eval(expr, {}, local_context)
        io.outputs["result"] = result

class WriteTextFile(ActionBase):
    """Action to write text content to a file."""
    name: str = "WriteTextFile"
    description: str = "Write text content to a file on disk"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="path",
            description="The destination file path",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="content",
            description="The text content to write",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="encoding",
            description="The file encoding",
            required=False,
            accepted_types=["string"],
            default="utf-8"
        ),
        InputFieldDeclaration(
            name="append",
            description="Whether to append instead of overwrite",
            required=False,
            accepted_types=["boolean"],
            default=False
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="path",
            description="The written file path",
            type="string"
        ),
        OutputFieldDeclaration(
            name="bytes_written",
            description="How many bytes were written",
            type="integer"
        )
    ]

    async def execute(self, io: IOPipe):
        from pathlib import Path

        path = io.inputs.get("path")
        content = io.inputs.get("content")
        encoding = io.inputs.get("encoding", "utf-8")
        append = io.inputs.get("append", False)

        if not path:
            raise ValueError("Input 'path' is required.")
        if content is None:
            raise ValueError("Input 'content' is required.")

        target_path = Path(path).expanduser()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(target_path, mode, encoding=encoding) as file_obj:
            file_obj.write(content)

        io.outputs["path"] = str(target_path.resolve())
        io.outputs["bytes_written"] = len(content.encode(encoding))

class FetchUrl(ActionBase):
    """Action to fetch text content from an HTTP URL."""
    name: str = "FetchUrl"
    description: str = "Fetch text content from a URL"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="url",
            description="The target URL",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="timeout",
            description="Request timeout in seconds",
            required=False,
            accepted_types=["number"],
            default=15
        ),
        InputFieldDeclaration(
            name="encoding",
            description="Response encoding, empty means auto detect from headers",
            required=False,
            accepted_types=["string"],
            default=""
        )
    ]
    outputs: list[OutputFieldDeclaration] = [
        OutputFieldDeclaration(
            name="content",
            description="The fetched text content",
            type="string"
        ),
        OutputFieldDeclaration(
            name="final_url",
            description="The final URL after redirects",
            type="string"
        ),
        OutputFieldDeclaration(
            name="status_code",
            description="The HTTP status code",
            type="integer"
        )
    ]

    async def execute(self, io: IOPipe):
        import urllib.request

        url = io.inputs.get("url")
        timeout = io.inputs.get("timeout", 15)
        encoding = io.inputs.get("encoding", "")

        if not url:
            raise ValueError("Input 'url' is required.")
        if not isinstance(timeout, (int, float)):
            timeout = 15

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_content = response.read()
            response_encoding = encoding or response.headers.get_content_charset() or "utf-8"
            io.outputs["content"] = raw_content.decode(response_encoding, errors="ignore")
            io.outputs["final_url"] = response.geturl()
            io.outputs["status_code"] = getattr(response, "status", 200)