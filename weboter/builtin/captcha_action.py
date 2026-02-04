import asyncio
from weboter.public.contracts import *
import playwright.async_api as pw
import cv2
import numpy as np

def search_rect(image, **kwargs):
    # 转为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # 提升亮度以突出缺口
    boffset = kwargs.get("boffset", 50)
    brightened = cv2.add(gray, 255 - boffset)
    otsu = cv2.threshold(brightened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # 去除噪声
    denoised = otsu
    for i in range(5):
        denoised = cv2.medianBlur(denoised, 5)
        denoised = cv2.threshold(denoised, 130, 255, cv2.THRESH_BINARY)[1]
    # 查找轮廓并筛选
    denoised = cv2.bitwise_not(denoised)
    contours, _ = cv2.findContours(denoised, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result_contours = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 10 or h < 10:
            continue
        area = cv2.contourArea(cnt)
        af = area / (w * h)
        if af < 0.2:
            continue
        result_contours.append((af, x, y, w, h, cnt))

    if len(result_contours) == 0:
        return None
    if len(result_contours) == 1:
        _, x, y, w, h, _ = result_contours[0]
        return (x, y, w, h)
    
    # 评估并返回最佳轮廓
    require_w = kwargs.get("require_w", 0)
    require_h = kwargs.get("require_h", 0)
    mark = 0
    best_rect = None
    for af, x, y, w, h, cnt in result_contours:
        diff_w = 0 if require_w == 0 else abs(w - require_w) / require_w
        diff_h = 0 if require_h == 0 else abs(h - require_h) / require_h
        sc_ = af * np.exp(- (diff_w + diff_h))
        if sc_ > mark:
            mark = sc_
            best_rect = (x, y, w, h)
    return best_rect

def generate_move_track(src_pos: tuple, dst_pos: tuple, total_time: float = 1.0, steps: int = 30):
    """
    Generate a list of (x, y) positions to simulate a slide movement from src_pos to dst_pos.
    """
    track = []
    src_x, src_y = src_pos
    dst_x, dst_y = dst_pos
    delta_x = (dst_x - src_x) / steps
    delta_y = (dst_y - src_y) / steps
    for i in range(steps):
        move_x = src_x + delta_x * (i + 1)
        move_y = src_y + delta_y * (i + 1)
        track.append((move_x, move_y))
    return track

async def simulate_slide_track(page: pw.Page, slider_element: pw.Locator, track: list[tuple]):
    box = await slider_element.bounding_box()
    if box is None:
        raise ValueError("Slider element bounding box not found.")
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    for x, y in track:
        await page.mouse.move(x, y)
        await asyncio.sleep(0.01)
    await page.mouse.up()

class SimpleSlideCaptcha(ActionBase):
    """
    A simple slide captcha action that simulates a user sliding a puzzle piece to complete the captcha.
    """
    name: str = "SimpleSlideCaptcha"
    description: str = "Simulates sliding a puzzle piece to complete a captcha."
    inputs: list[InputFieldDeclaration] = [
        InputFieldDeclaration(
            name="image",
            description="The locator for the captcha image element.",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="slider",
            description="The locator for the slider element.",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="bar",
            description="The locator for the slide-bar element.",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        InputFieldDeclaration(
            name="retry",
            description="The locator for the retry button element.",
            required=True,
            accepted_types=["LocatorDefine"]
        ),
        # brightness offset
        InputFieldDeclaration(
            name="boffset",
            description="The brightness offset.",
            required=False,
            accepted_types=["number"],
            default=20
        ),
        # k/b fix
        InputFieldDeclaration(
            name="fix_k",
            description="The 'k' parameter for the keyboard movement fix.",
            required=False,
            accepted_types=["number"],
            default=1.0
        ),
        InputFieldDeclaration(
            name="fix_b",
            description="The 'b' parameter for the keyboard movement fix.",
            required=False,
            accepted_types=["number"],
            default=0.0
        ),
        # suggested width/height
        InputFieldDeclaration(
            name="suggest_w",
            description="The suggested width of the missing piece.",
            required=False,
            accepted_types=["number", "string"],
            default=0
        ),
        InputFieldDeclaration(
            name="suggest_h",
            description="The suggested height of the missing piece.",
            required=False,
            accepted_types=["number", "string"],
            default=0
        )
    ]
    outputs: list[OutputFieldDeclaration] = []

    async def execute(self, context: dict):
        inputs = context.get("inputs", {})

        if "image" not in inputs or "slider" not in inputs or "bar" not in inputs or "retry" not in inputs:
            raise ValueError("Missing required input locators: 'image', 'slider', 'bar', or 'retry'.")
        
        image_locator = LocatorDefine.from_dict(inputs["image"])
        slider_locator = LocatorDefine.from_dict(inputs["slider"])
        bar_locator = LocatorDefine.from_dict(inputs["bar"])
        retry_locator = LocatorDefine.from_dict(inputs["retry"])

        fix_k = inputs.get("fix_k", 1.0)
        fix_b = inputs.get("fix_b", 0.0)
        boffset = inputs.get("boffset", 20)
        suggest_w = inputs.get("suggest_w", 0)
        suggest_h = inputs.get("suggest_h", 0)

        page = context.get("current_page")
        if page is None:
            raise ValueError("No current page found in context.")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page in context is not a valid Page object.")
        
        image_element = utils.get_locator(page, image_locator)
        slider_element = utils.get_locator(page, slider_locator)
        bar_element = utils.get_locator(page, bar_locator)
        retry_element = utils.get_locator(page, retry_locator)

        await image_element.wait_for(state="visible", timeout=10000)
        image_bb = await image_element.bounding_box()
        await slider_element.wait_for(state="visible", timeout=10000)
        await bar_element.wait_for(state="visible", timeout=10000)
        slider_bb = await slider_element.bounding_box()
        bar_bb = await bar_element.bounding_box()
        move_limit = bar_bb["width"] - slider_bb["width"]
        if isinstance(suggest_w, str):
            if suggest_w.endswith("%"):
                percent = float(suggest_w[:-1]) / 100.0
                suggest_w = int(image_bb["width"] * percent)
            else:
                suggest_w = int(suggest_w)
        if isinstance(suggest_h, str):
            if suggest_h.endswith("%"):
                percent = float(suggest_h[:-1]) / 100.0
                suggest_h = int(image_bb["height"] * percent)
            else:
                suggest_h = int(suggest_h)

        left_tries = 5
        while left_tries > 0:
            left_tries -= 1
            await asyncio.sleep(5)
            await image_element.wait_for(state="visible", timeout=10000)
            image_content = await image_element.screenshot()
            rect = search_rect(
                cv2.imdecode(np.frombuffer(image_content, np.uint8), cv2.IMREAD_COLOR),
                boffset=boffset,
                require_w=suggest_w,
                require_h=suggest_h
            )
            if rect is None:
                await retry_element.click()
                continue
            # 计算滑动距离
            center_x = rect[0] + rect[2] // 2
            slide_distance = center_x * move_limit / image_bb["width"]
            # 计算修正后的滑动距离
            fixed_distance = fix_k * slide_distance + fix_b
            print(f"Calculated slide distance: {slide_distance}, fixed distance: {fixed_distance}")
            # 执行滑动操作
            track = generate_move_track(
                (slider_bb["x"] + slider_bb["width"] / 2, slider_bb["y"] + slider_bb["height"] / 2),
                (slider_bb["x"] + slider_bb["width"] / 2 + fixed_distance, slider_bb["y"] + slider_bb["height"] / 2),
                total_time=5.0,
                steps=30
            )
            await simulate_slide_track(page, slider_element, track)

            # 检查 image_element 是否还存在，存在则表示失败
            await asyncio.sleep(2)
            exists = await image_element.is_visible()
            if not exists:
                print("Slide captcha solved successfully.")
                return
            else:
                print("Slide captcha attempt failed, retrying...")
                await retry_element.click()
            
            await asyncio.sleep(5)