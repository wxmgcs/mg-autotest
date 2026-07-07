"""
步骤执行器 - 共享模块

统一执行工作流中单个步骤的逻辑，供 workflow_builder 和 workflow_runner 调用。
后续新增步骤类型只需修改此文件，双方自动生效。
"""

import os
import time
import datetime

import cv2

from mg_autotest.core.logger import get_logger
from mg_autotest.core.image_matcher import find_image, find_and_click

logger = get_logger(__name__)

# ── 目录配置（由各模块启动时设置） ──
TEMPLATE_DIR = "templates"
SCREENSHOTS_DIR = "screenshots"


def execute_single_step(d, step: dict) -> dict:
    """
    执行单个步骤，返回 {success, result/error} 字典。

    支持的 step.type:
      click, text, long_click, swipe, wait, back, screenrecord, screenshot

    供 workflow_builder / workflow_runner 等外部模块调用。
    """
    step_type = step.get("type", "click")
    try:
        if step_type == "click":
            template = step.get("template", "")
            threshold = float(step.get("threshold", 0.8))
            timeout = float(step.get("timeout", 10))
            ox = int(step.get("offsetX", 0))
            oy = int(step.get("offsetY", 0))
            tpl_path = os.path.join(TEMPLATE_DIR, template)
            if not os.path.isfile(tpl_path):
                return {"success": False, "error": f"Template not found: {template}"}
            ok = find_and_click(d, tpl_path, threshold=threshold,
                                timeout=timeout, offset_x=ox, offset_y=oy)
            return {"success": ok, "result": "clicked" if ok else "not found"}

        elif step_type == "text":
            text = step.get("text", "")
            d.send_keys(text)
            return {"success": True, "result": f"sent text: {text}"}

        elif step_type == "long_click":
            template = step.get("template", "")
            threshold = float(step.get("threshold", 0.8))
            timeout = float(step.get("timeout", 10))
            ox = int(step.get("offsetX", 0))
            oy = int(step.get("offsetY", 0))
            duration = float(step.get("duration", 1.0))
            tpl_path = os.path.join(TEMPLATE_DIR, template)
            if not os.path.isfile(tpl_path):
                return {"success": False, "error": f"Template not found: {template}"}
            result = find_image(d, tpl_path, threshold=threshold, timeout=timeout)
            if result is None:
                return {"success": False, "error": "template not found"}
            cx, cy, _ = result
            d.long_click(cx + ox, cy + oy, duration=duration)
            return {"success": True, "result": f"long clicked ({cx+ox},{cy+oy})"}

        elif step_type == "swipe":
            sx = int(step.get("sx", 0))
            sy = int(step.get("sy", 0))
            ex = int(step.get("ex", 0))
            ey = int(step.get("ey", 0))
            duration = float(step.get("duration", 0.1))
            d.swipe(sx, sy, ex, ey, duration=duration)
            return {"success": True, "result": f"swiped ({sx},{sy}) -> ({ex},{ey})"}

        elif step_type == "wait":
            seconds = float(step.get("seconds", 2))
            time.sleep(seconds)
            return {"success": True, "result": f"waited {seconds}s"}

        elif step_type == "back":
            d.press("back")
            return {"success": True, "result": "pressed back"}

        elif step_type == "screenrecord":
            return {"success": True, "result": "screenrecord marker (recording controlled by --record flag)"}

        elif step_type == "screenshot":
            img = d.screenshot(format="opencv")
            if img is None:
                return {"success": False, "error": "截图失败"}
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{ts}.png"
            cv2.imwrite(os.path.join(SCREENSHOTS_DIR, filename), img)
            logger.info(f"截图已保存: {SCREENSHOTS_DIR}/{filename}")
            return {"success": True, "result": f"截图已保存: {filename}"}

        else:
            return {"success": False, "error": f"unknown type: {step_type}"}

    except Exception as e:
        logger.error(f"单步执行异常: {e}")
        return {"success": False, "error": str(e)}
