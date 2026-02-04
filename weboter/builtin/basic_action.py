from weboter.public.contracts import *
import playwright.async_api as pw
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

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})
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
        
        context["browser"] = browser
        context["pw_inst"] = pw_instance
        context["output"] = {"browser": browser}

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

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})
        url = inputs.get("url")
        if not url:
            raise ValueError("Input 'url' is required.")

        browser = context.get("browser")
        if not browser:
            raise ValueError("Browser instance is required in context.")
        if not isinstance(browser, pw.Browser):
            raise ValueError("Browser in context is not a valid Browser object.")
        
        page = await browser.new_page()
        await page.goto(url)
        
        output = {}
        if not output.get("pages"):
            output["pages"] = []
        if not isinstance(output["pages"], list):
            raise ValueError("Output 'pages' must be a list.")
        output["pages"].append(page)
        context["output"] = output
        context["current_page"] = page

class ClickItem(ActionBase):
    """Action to click an item on the web page given a locator."""
    name: str = "ClickItem"
    description: str = "Click an item on the web page by locator"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="locator",
            description="The CSS locator of the item to click",
            required=True,
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="locator_type",
            description="Type of the locator (role, text, label, placeholder, alt, title, testid, css, xpath)",
            required=False,
            accepted_types=["string"],
            default="text"
        ),
        InputFieldDeclaration(
            name="locator_ext",
            description="Additional locator information (if needed)",
            required=False,
            accepted_types=["dict"],
            default={}
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

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})
        locator = inputs.get("locator")
        if not locator:
            raise ValueError("Input 'locator' is required.")

        page = context.get("current_page")
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        locator_ext = inputs.get("locator_ext", {})

        locator_type = inputs.get("locator_type", "text")
        if locator_type == "role":
            element = page.get_by_role(locator, **locator_ext)
        elif locator_type == "text":
            element = page.get_by_text(locator, **locator_ext)
        elif locator_type == "label":
            element = page.get_by_label(locator, **locator_ext)
        elif locator_type == "placeholder":
            element = page.get_by_placeholder(locator, **locator_ext)
        elif locator_type == "alt":
            element = page.get_by_alt_text(locator, **locator_ext)
        elif locator_type == "title":
            element = page.get_by_title(locator, **locator_ext)
        elif locator_type == "testid":
            element = page.get_by_test_id(locator, **locator_ext)
        elif locator_type == "css":
            element = page.locator(locator, **locator_ext)
        elif locator_type == "xpath":
            element = page.locator(f"xpath={locator}", **locator_ext)
        else:
            raise ValueError(f"Unsupported locator type: {locator_type}")
        
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
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="locator_type",
            description="Type of the locator (role, text, label, placeholder, alt, title, testid, css, xpath)",
            required=False,
            accepted_types=["string"],
            default="text"
        ),
        InputFieldDeclaration(
            name="locator_ext",
            description="Additional locator information (if needed)",
            required=False,
            accepted_types=["dict"],
            default={}
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

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})
        locator = inputs.get("locator")
        if not locator:
            raise ValueError("Input 'locator' is required.")
        text = inputs.get("text")
        if text is None:
            raise ValueError("Input 'text' is required.")

        page = context.get("current_page")
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        locator_ext = inputs.get("locator_ext", {})

        locator_type = inputs.get("locator_type", "text")
        if locator_type == "role":
            element = page.get_by_role(locator, **locator_ext)
        elif locator_type == "text":
            element = page.get_by_text(locator, **locator_ext)
        elif locator_type == "label":
            element = page.get_by_label(locator, **locator_ext)
        elif locator_type == "placeholder":
            element = page.get_by_placeholder(locator, **locator_ext)
        elif locator_type == "alt":
            element = page.get_by_alt_text(locator, **locator_ext)
        elif locator_type == "title":
            element = page.get_by_title(locator, **locator_ext)
        elif locator_type == "testid":
            element = page.get_by_test_id(locator, **locator_ext)
        elif locator_type == "css":
            element = page.locator(locator, **locator_ext)
        elif locator_type == "xpath":
            element = page.locator(f"xpath={locator}", **locator_ext)
        else:
            raise ValueError(f"Unsupported locator type: {locator_type}")

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
            accepted_types=["string"]
        ),
        InputFieldDeclaration(
            name="locator_type",
            description="Type of the locator (role, text, label, placeholder, alt, title, testid, css, xpath)",
            required=False,
            accepted_types=["string"],
            default="text"
        ),
        InputFieldDeclaration(
            name="locator_ext",
            description="Additional locator information (if needed)",
            required=False,
            accepted_types=["dict"],
            default={}
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

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})
        locator = inputs.get("locator")
        if not locator:
            raise ValueError("Input 'locator' is required.")

        page = context.get("current_page")
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000

        locator_ext = inputs.get("locator_ext", {})

        locator_type = inputs.get("locator_type", "text")
        if locator_type == "role":
            element = page.get_by_role(locator, **locator_ext)
        elif locator_type == "text":
            element = page.get_by_text(locator, **locator_ext)
        elif locator_type == "label":
            element = page.get_by_label(locator, **locator_ext)
        elif locator_type == "placeholder":
            element = page.get_by_placeholder(locator, **locator_ext)
        elif locator_type == "alt":
            element = page.get_by_alt_text(locator, **locator_ext)
        elif locator_type == "title":
            element = page.get_by_title(locator, **locator_ext)
        elif locator_type == "testid":
            element = page.get_by_test_id(locator, **locator_ext)
        elif locator_type == "css":
            element = page.locator(locator, **locator_ext)
        elif locator_type == "xpath":
            element = page.locator(f"xpath={locator}", **locator_ext)
        else:
            raise ValueError(f"Unsupported locator type: {locator_type}")
        
        try:
            await element.wait_for(state="visible", timeout=timeout)
            found = True
        except pw.TimeoutError:
            found = False
        context["output"] = {"element_found": found}

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

    async def execute(self, context: dict):
        import asyncio
        inputs = context.get("inputs", {})
        duration = inputs.get("duration")
        if duration is None:
            raise ValueError("Input 'duration' is required.")
        if not isinstance(duration, (int, float)):
            raise ValueError("Input 'duration' must be a number.")
        
        await asyncio.sleep(duration)