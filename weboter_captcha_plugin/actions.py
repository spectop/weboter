"""
OCR 验证码插件动作。

包含：
  - OcrReadText：对指定页面区域做 OCR，返回文本与候选框。
  - ClickTextOrderCaptcha：读取提示词，并在验证码图上按顺序点击目标文字。

依赖：
  - numpy
  - opencv-python
  - rapidocr-onnxruntime
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from weboter.public.contracts import ActionBase, IOPipe, InputFieldDeclaration, LocatorDefine, OutputFieldDeclaration, utils


_OCR_ENGINE = None


def _load_ocr_runtime():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "缺少 OCR 依赖，请先安装：pip install -e '.[captcha_ocr]'"
        ) from exc
    return cv2, np, RapidOCR


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _cv2, _np, RapidOCR = _load_ocr_runtime()
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


@dataclass
class OcrItem:
    text: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "score": self.score,
            "box": [self.x1, self.y1, self.x2, self.y2],
            "center": [(self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2],
        }


def _ensure_locator(value: Any, field_name: str) -> LocatorDefine:
    if isinstance(value, LocatorDefine):
        return value
    if isinstance(value, dict):
        return LocatorDefine.from_dict(value)
    raise ValueError(f"{field_name} 必须是 LocatorDefine")


def _normalize_box(box: Any) -> tuple[float, float, float, float]:
    if not isinstance(box, (list, tuple)) or not box:
        raise ValueError(f"无效 OCR box: {box}")
    if len(box) == 4 and all(isinstance(item, (int, float)) for item in box):
        x1, y1, x2, y2 = box
        return float(x1), float(y1), float(x2), float(y2)

    xs = []
    ys = []
    for point in box:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        xs.append(float(point[0]))
        ys.append(float(point[1]))
    if not xs or not ys:
        raise ValueError(f"无法解析 OCR box: {box}")
    return min(xs), min(ys), max(xs), max(ys)


def _parse_ocr_items(raw_items: Any, min_score: float) -> list[OcrItem]:
    parsed: list[OcrItem] = []
    for item in list(raw_items or []):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box, text, score = item[0], item[1], item[2]
        text_str = str(text or "").strip()
        score_value = float(score or 0.0)
        if not text_str or score_value < min_score:
            continue
        x1, y1, x2, y2 = _normalize_box(box)
        parsed.append(OcrItem(text=text_str, score=score_value, x1=x1, y1=y1, x2=x2, y2=y2))
    parsed.sort(key=lambda current: (round(current.y1, 1), current.x1))
    return parsed


async def _read_locator_image(locator) -> tuple[Any, int, int]:
    cv2, np, _RapidOCR = _load_ocr_runtime()
    image_bytes = await locator.screenshot()
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("截图解码失败")
    height, width = image.shape[:2]
    return image, width, height


async def _ocr_locator(locator, min_score: float) -> list[OcrItem]:
    ocr = _get_ocr_engine()
    image, _width, _height = await _read_locator_image(locator)
    raw_items, _elapsed = ocr(image)
    return _parse_ocr_items(raw_items, min_score=min_score)


def _items_to_text(items: list[OcrItem], join_with: str) -> str:
    return join_with.join(item.text for item in items)


def _extract_target_chars(prompt_text: str, clean_pattern: str) -> list[str]:
    text = prompt_text.strip()
    if clean_pattern:
        text = re.sub(clean_pattern, "", text)
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)


def _candidate_points(items: list[OcrItem]) -> dict[str, list[tuple[float, float]]]:
    result: dict[str, list[tuple[float, float]]] = {}
    for item in items:
        text = item.text
        if not text:
            continue
        width = max(item.x2 - item.x1, 1.0)
        char_width = width / max(len(text), 1)
        center_y = (item.y1 + item.y2) / 2
        for index, char in enumerate(text):
            center_x = item.x1 + char_width * (index + 0.5)
            result.setdefault(char, []).append((center_x, center_y))
    return result


async def _locator_visible(locator) -> bool:
    try:
        return await locator.is_visible()
    except Exception:
        return False


class OcrReadText(ActionBase):
    name = "OcrReadText"
    description = "对指定页面区域执行 OCR，输出文本与候选框"
    inputs = [
        InputFieldDeclaration(name="image", description="待识别区域 locator", required=True, accepted_types=["LocatorDefine"]),
        InputFieldDeclaration(name="min_score", description="最小识别置信度", required=False, accepted_types=["number"], default=0.3),
        InputFieldDeclaration(name="join_with", description="拼接文本分隔符", required=False, accepted_types=["string"], default="\n"),
    ]
    outputs = [
        OutputFieldDeclaration(name="text", description="拼接后的识别文本", type="string"),
        OutputFieldDeclaration(name="items", description="逐项识别结果", type="list"),
        OutputFieldDeclaration(name="count", description="识别项数量", type="int"),
    ]

    async def execute(self, io: IOPipe):
        page = io.page
        if page is None:
            raise ValueError("当前上下文没有 page")

        image_locator = _ensure_locator(io.inputs.get("image"), "image")
        min_score = float(io.inputs.get("min_score") or 0.3)
        join_with = str(io.inputs.get("join_with") or "\n")
        locator = utils.get_locator(page, image_locator)
        items = await _ocr_locator(locator, min_score=min_score)
        io.outputs["text"] = _items_to_text(items, join_with)
        io.outputs["items"] = [item.to_dict() for item in items]
        io.outputs["count"] = len(items)


class ClickTextOrderCaptcha(ActionBase):
    name = "ClickTextOrderCaptcha"
    description = "读取提示词并按顺序点击验证码图中的目标文字"
    inputs = [
        InputFieldDeclaration(name="captcha_image", description="验证码点击区域 locator", required=True, accepted_types=["LocatorDefine"]),
        InputFieldDeclaration(name="prompt_image", description="提示词区域 locator；与 prompt_text 二选一", required=False, accepted_types=["LocatorDefine"], default=None),
        InputFieldDeclaration(name="prompt_text", description="直接提供提示词文本；与 prompt_image 二选一", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="confirm_button", description="确认按钮 locator", required=False, accepted_types=["LocatorDefine"], default=None),
        InputFieldDeclaration(name="retry_button", description="失败后重试按钮 locator", required=False, accepted_types=["LocatorDefine"], default=None),
        InputFieldDeclaration(name="success_indicator", description="成功态指示 locator", required=False, accepted_types=["LocatorDefine"], default=None),
        InputFieldDeclaration(name="failure_indicator", description="失败态指示 locator", required=False, accepted_types=["LocatorDefine"], default=None),
        InputFieldDeclaration(name="min_score", description="最小识别置信度", required=False, accepted_types=["number"], default=0.3),
        InputFieldDeclaration(name="clean_pattern", description="清理提示词前缀的正则", required=False, accepted_types=["string"], default=r"请依次点击[:：\s]*"),
        InputFieldDeclaration(name="max_retry", description="最大尝试次数", required=False, accepted_types=["number"], default=3),
        InputFieldDeclaration(name="click_delay_ms", description="两次点击之间延迟毫秒", required=False, accepted_types=["number"], default=200),
        InputFieldDeclaration(name="retry_wait_ms", description="重试前等待毫秒", required=False, accepted_types=["number"], default=1000),
        InputFieldDeclaration(name="post_click_wait_ms", description="点击完成后的判定等待毫秒", required=False, accepted_types=["number"], default=1200),
        InputFieldDeclaration(name="strict", description="失败时是否直接抛错", required=False, accepted_types=["boolean"], default=True),
    ]
    outputs = [
        OutputFieldDeclaration(name="prompt_text", description="最终使用的提示词", type="string"),
        OutputFieldDeclaration(name="target_chars", description="目标字符序列", type="list"),
        OutputFieldDeclaration(name="clicked_points", description="点击坐标序列", type="list"),
        OutputFieldDeclaration(name="recognized_items", description="验证码 OCR 结果", type="list"),
        OutputFieldDeclaration(name="attempts", description="实际尝试次数", type="int"),
        OutputFieldDeclaration(name="success", description="是否成功", type="bool"),
    ]

    async def execute(self, io: IOPipe):
        page = io.page
        if page is None:
            raise ValueError("当前上下文没有 page")

        captcha_image = _ensure_locator(io.inputs.get("captcha_image"), "captcha_image")
        prompt_image_value = io.inputs.get("prompt_image")
        prompt_text = str(io.inputs.get("prompt_text") or "").strip()
        if not prompt_text and not prompt_image_value:
            raise ValueError("prompt_text 与 prompt_image 至少提供一个")

        min_score = float(io.inputs.get("min_score") or 0.3)
        clean_pattern = str(io.inputs.get("clean_pattern") or r"请依次点击[:：\s]*")
        max_retry = max(int(io.inputs.get("max_retry") or 3), 1)
        click_delay = float(io.inputs.get("click_delay_ms") or 200) / 1000.0
        retry_wait = float(io.inputs.get("retry_wait_ms") or 1000) / 1000.0
        post_click_wait = float(io.inputs.get("post_click_wait_ms") or 1200) / 1000.0
        strict = bool(io.inputs.get("strict") if "strict" in io.inputs else True)

        captcha_locator = utils.get_locator(page, captcha_image)
        prompt_locator = utils.get_locator(page, _ensure_locator(prompt_image_value, "prompt_image")) if prompt_image_value else None
        confirm_locator = utils.get_locator(page, _ensure_locator(io.inputs.get("confirm_button"), "confirm_button")) if io.inputs.get("confirm_button") else None
        retry_locator = utils.get_locator(page, _ensure_locator(io.inputs.get("retry_button"), "retry_button")) if io.inputs.get("retry_button") else None
        success_locator = utils.get_locator(page, _ensure_locator(io.inputs.get("success_indicator"), "success_indicator")) if io.inputs.get("success_indicator") else None
        failure_locator = utils.get_locator(page, _ensure_locator(io.inputs.get("failure_indicator"), "failure_indicator")) if io.inputs.get("failure_indicator") else None

        if not prompt_text and prompt_locator is not None:
            prompt_items = await _ocr_locator(prompt_locator, min_score=min_score)
            prompt_text = _items_to_text(prompt_items, " ")

        target_chars = _extract_target_chars(prompt_text, clean_pattern)
        if not target_chars:
            raise ValueError(f"未能从提示词中提取目标字符: {prompt_text}")

        attempts = 0
        last_items: list[OcrItem] = []
        last_points: list[dict[str, float | str]] = []

        while attempts < max_retry:
            attempts += 1
            last_points = []
            captcha_items = await _ocr_locator(captcha_locator, min_score=min_score)
            last_items = captcha_items
            point_map = _candidate_points(captcha_items)
            used_indices: dict[str, int] = {}

            box = await captcha_locator.bounding_box()
            if box is None:
                raise ValueError("captcha_image 无法获取 bounding box")
            image, width_px, height_px = await _read_locator_image(captcha_locator)
            _ = image
            scale_x = box["width"] / max(width_px, 1)
            scale_y = box["height"] / max(height_px, 1)

            missing_char = None
            for char in target_chars:
                candidates = point_map.get(char, [])
                index = used_indices.get(char, 0)
                if index >= len(candidates):
                    missing_char = char
                    break
                used_indices[char] = index + 1
                center_x, center_y = candidates[index]
                click_x = center_x * scale_x
                click_y = center_y * scale_y
                await captcha_locator.click(position={"x": click_x, "y": click_y}, force=True)
                last_points.append({"char": char, "x": click_x, "y": click_y})
                await asyncio.sleep(click_delay)

            if missing_char is None:
                if confirm_locator is not None:
                    await confirm_locator.click(force=True)
                await asyncio.sleep(post_click_wait)

                captcha_visible = await _locator_visible(captcha_locator)
                success_visible = await _locator_visible(success_locator) if success_locator is not None else False
                failure_visible = await _locator_visible(failure_locator) if failure_locator is not None else False
                success = success_visible or (not captcha_visible and not failure_visible) or (success_locator is None and failure_locator is None)
                if success:
                    io.outputs["prompt_text"] = prompt_text
                    io.outputs["target_chars"] = target_chars
                    io.outputs["clicked_points"] = last_points
                    io.outputs["recognized_items"] = [item.to_dict() for item in captcha_items]
                    io.outputs["attempts"] = attempts
                    io.outputs["success"] = True
                    return

            if attempts < max_retry and retry_locator is not None:
                await retry_locator.click(force=True)
                await asyncio.sleep(retry_wait)

        io.outputs["prompt_text"] = prompt_text
        io.outputs["target_chars"] = target_chars
        io.outputs["clicked_points"] = last_points
        io.outputs["recognized_items"] = [item.to_dict() for item in last_items]
        io.outputs["attempts"] = attempts
        io.outputs["success"] = False
        if strict:
            raise RuntimeError("按字序点击验证码处理失败")