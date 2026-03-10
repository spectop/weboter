from weboter.public.contracts import *
import playwright.async_api as pw
from playwright_stealth import Stealth
# async_playwright, Browser, Page
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
        stealth = Stealth()
        await stealth.apply_stealth_async(browser_context)
        
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
        
        io.outputs['__page__'] = page

class ClickItem(ActionBase):
    """Action to click an item on the web page given a locator."""
    name: str = "ClickItem"
    description: str = "Click an item on the web page by locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The CSS locator of the item to click",
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
    outputs: list[OutputFieldDeclaration] = []

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

        locator = LocatorDefine.from_dict(inputs["locator"])
        element = utils.get_locator(page, locator)

        await element.click(timeout=timeout)

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

        locator = LocatorDefine.from_dict(inputs["locator"])
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

        locator = LocatorDefine.from_dict(inputs.get("locator"))
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
            print(f"EmptyAction: {message}")

class ExtraData(ActionBase):
    """Action to get data from the web page using a locator."""
    name: str = "ExtraData"
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
        
        if not inputs.get("locator"):
            raise ValueError("Input 'locator' is required.")
        locator = LocatorDefine.from_dict(inputs["locator"])

        page = io.page
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000
        data_source = inputs.get("data_source", "text")
        

        element = utils.get_locator(page, locator)
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
        
        # for testing
        print(f"Extracted data: {data}")

        io.outputs["data"] = data