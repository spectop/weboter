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
    """Action to click an item on the web page given a selector."""
    name: str = "ClickItem"
    description: str = "Click an item on the web page by selector"
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="selector",
            description="The CSS selector of the item to click",
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
        selector = inputs.get("selector")
        if not selector:
            raise ValueError("Input 'selector' is required.")

        page = context.get("current_page")
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = inputs.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000
        
        await page.click(selector, timeout=timeout)
        