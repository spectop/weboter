from .interface import LocatorDefine
import playwright.async_api as pw

def get_locator(page: pw.Page, locator_def: LocatorDefine) -> pw.Locator:
    """Convert a LocatorDefine to a Playwright Locator."""
    if locator_def.type == "text":
        return page.get_by_text(locator_def.element, *locator_def.ext)
    elif locator_def.type == "role":
        return page.get_by_role(locator_def.element, *locator_def.ext)
    elif locator_def.type == "label":
        return page.get_by_label(locator_def.element, *locator_def.ext)
    elif locator_def.type == "placeholder":
        return page.get_by_placeholder(locator_def.element, *locator_def.ext)
    elif locator_def.type == "alt":
        return page.get_by_alt_text(locator_def.element, *locator_def.ext)
    elif locator_def.type == "title":
        return page.get_by_title(locator_def.element, *locator_def.ext)
    elif locator_def.type == "testid":
        return page.get_by_test_id(locator_def.element, *locator_def.ext)
    elif locator_def.type == "css":
        return page.locator(locator_def.element, *locator_def.ext)
    elif locator_def.type == "xpath":
        return page.locator(f"xpath={locator_def.element}", *locator_def.ext)
    else:
        raise ValueError(f"Unsupported locator type: {locator_def.type}")