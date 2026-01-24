from weboter.public import ActionBase, InputFieldDeclaration, OutputFieldDeclaration
import playwright.async_api as pw

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
        input = context.get("input", {})
        url = input.get("url")
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
        output["page"] = page
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
        input = context.get("input", {})
        selector = input.get("selector")
        if not selector:
            raise ValueError("Input 'selector' is required.")

        page = context.get("current_page")
        if not page:
            raise ValueError("Current page is required in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        timeout = input.get("timeout", 5000)
        if not isinstance(timeout, (int, float)):
            timeout = 5000
        
        await page.click(selector, timeout=timeout)
        