from .interface import LocatorDefine
import playwright.async_api as pw

def get_locator(obj: pw.Page | pw.Locator, locator_def: LocatorDefine) -> pw.Locator:
    """Recursively get a Playwright Locator from a LocatorDefine, supporting nested sub locators."""
    if locator_def.type == "text":
        current = obj.get_by_text(locator_def.element, **locator_def.ext)
    elif locator_def.type == "role":
        current = obj.get_by_role(locator_def.element, **locator_def.ext)
    elif locator_def.type == "label":
        current = obj.get_by_label(locator_def.element, **locator_def.ext)
    elif locator_def.type == "placeholder":
        current = obj.get_by_placeholder(locator_def.element, **locator_def.ext)
    elif locator_def.type == "alt":
        current = obj.get_by_alt_text(locator_def.element, **locator_def.ext)
    elif locator_def.type == "title":
        current = obj.get_by_title(locator_def.element, **locator_def.ext)
    elif locator_def.type == "testid":
        current = obj.get_by_test_id(locator_def.element, **locator_def.ext)
    elif locator_def.type == "css":
        current = obj.locator(locator_def.element, **locator_def.ext)
    elif locator_def.type == "xpath":
        current = obj.locator(f"xpath={locator_def.element}", **locator_def.ext)
    else:
        raise ValueError(f"Unsupported locator type: {locator_def.type}")
    
    if isinstance(locator_def.pos, int):
        current = current.nth(locator_def.pos)
    elif locator_def.pos == "first":
        current = current.first
    elif locator_def.pos == "last":
        current = current.last
    elif locator_def.pos == "all":
        pass  # keep all matches
    else:
        pass
    
    if locator_def.sub:
        return get_locator(current, locator_def.sub)
    return current
