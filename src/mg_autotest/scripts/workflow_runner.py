"""
Workflow Runner

读取 workflow_builder.py 编排生成的 JSON 文件，按步骤在手机上执行。
支持 click / text / long_click / wait / back 五种步骤类型。

用法:
    D:/aDisk/py3109-autotest/python.exe scripts/workflow_runner.py <workflow.json>
    D:/aDisk/py3109-autotest/python.exe scripts/workflow_runner.py              # 交互式选择
    D:/aDisk/py3109-autotest/python.exe scripts/workflow_runner.py --list       # 列出可用工作流
"""

import sys
import os
import json
import time
import datetime
import argparse
import threading
import shutil
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

import cv2
from mg_autotest.core.logger import get_logger, setup_logger
from mg_autotest.core.device import get_device, wake_screen, press_home
from mg_autotest.core.image_matcher import save_screenshot
from mg_autotest.core.watchers import setup_watchers
from mg_autotest.config import STATUS_BAR_HEIGHT, RECORD_INTERVAL, RECORD_RESIZE_RATIO, RECORD_GIF_COLORS
from mg_autotest.scripts.step_executor import execute_single_step

logger = get_logger(__name__)

WORKFLOW_DIR = "workflows"
TEMPLATE_DIR = "templates"
SCREENRECORDS_DIR = "screenrecords"
CONTINUE_ON_ERROR = False  # 默认遇错停止，--continue 则跳过继续


def list_workflows() -> list:
    """列出 workflows/ 目录下所有 .json 文件"""
    os.makedirs(WORKFLOW_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(WORKFLOW_DIR) if f.lower().endswith(".json"))
    return files


def select_workflows_interactive() -> list:
    """交互式让用户选择多个工作流文件"""
    files = list_workflows()
    if not files:
        print("   [Error] workflows/ 目录下没有 .json 文件")
        sys.exit(1)

    print("\n可用的工作流:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")

    print(f"\n输入编号选择（逗号/空格分隔，如: 1,3,5-7；留空=全部，q=退出）")
    while True:
        try:
            choice = input(f"\n请选择 (1-{len(files)}): ").strip().lower()
            if not choice:
                return files  # 空=全部
            if choice == 'q':
                sys.exit(0)
            selected = set()
            # 支持逗号、空格分隔，以及范围语法 5-7
            parts = choice.replace(',', ' ').split()
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if '-' in part:
                    a, b = part.split('-', 1)
                    for i in range(int(a.strip()), int(b.strip()) + 1):
                        idx = int(i)
                        if 1 <= idx <= len(files):
                            selected.add(idx)
                else:
                    idx = int(part)
                    if 1 <= idx <= len(files):
                        selected.add(idx)
            if selected:
                return [files[i - 1] for i in sorted(selected)]
        except (ValueError, IndexError):
            pass
        print("  无效选择，请重试")


def load_workflow(filepath: str) -> dict:
    """加载工作流 JSON 文件"""
    if not os.path.isfile(filepath):
        # 尝试在 workflows/ 目录下查找
        alt = os.path.join(WORKFLOW_DIR, filepath)
        if os.path.isfile(alt):
            filepath = alt
        else:
            logger.error(f"工作流文件不存在: {filepath}")
            return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "steps" not in data or not isinstance(data["steps"], list):
            logger.error(f"无效的工作流文件: {filepath} (缺少 steps 字段)")
            return None
        logger.info(f"已加载工作流: {filepath} ({len(data['steps'])} 步)")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {filepath} - {e}")
        return None
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return None


def execute_step(d, step: dict, step_num: int, total: int) -> bool:
    """
    执行单个步骤（含日志输出）。

    实际执行逻辑委托给 step_executor.execute_single_step。

    Args:
        d: uiautomator2 Device
        step: 步骤配置
        step_num: 当前步骤号
        total: 总步骤数

    Returns:
        True 成功，False 失败
    """
    desc = step.get("desc", f"Step {step_num}")
    if not step.get("enabled", True):
        logger.info(f"  [{step_num}/{total}] ⏭ {desc} (已禁用，跳过)")
        return True

    prefix = f"  [{step_num}/{total}]"
    logger.info(f"{prefix} ▶ {desc}")

    result = execute_single_step(d, step)
    if result.get("success"):
        detail = result.get("result", "")
        logger.info(f"{prefix} ✓ {detail}")
        return True
    else:
        err = result.get("error", "unknown")
        logger.warning(f"{prefix} ✗ {err}")
        return False


def run_workflow(filepath: str, continue_on_error: bool = False, record: bool = False,
                 initenv: bool = False):
    """运行工作流"""

    INITENV_TEMPLATE = "wx_filetranshelper.png"
    INITENV_MAX_ATTEMPTS = 10
    INITENV_INTERVAL = 0.5
    # 1. 加载工作流
    workflow = load_workflow(filepath)
    if workflow is None:
        return False

    steps = workflow.get("steps", [])
    if not steps:
        logger.warning("工作流中没有步骤")
        return True

    # 检查是否有 screenrecord 步骤，无则该标志位不生效
    has_screenrecord_step = any(s.get("type") == "screenrecord" for s in steps)
    if record and not has_screenrecord_step:
        logger.warning("工作流中无 screenrecord 步骤，--record 不生效")
        record = False

    # 2. 连接设备
    logger.info("正在连接设备...")
    try:
        d = get_device()
    except Exception as e:
        logger.error(f"设备连接失败: {e}")
        return False

    # 3. 初始化
    wake_screen(d)
    setup_watchers(d)
    time.sleep(1)

    # 3b. 环境初始化（如需）
    if initenv:
        logger.info("检查环境就绪...")
        tpl_path = os.path.join(TEMPLATE_DIR, INITENV_TEMPLATE)
        if not os.path.isfile(tpl_path):
            logger.error(f"初始化模板不存在: {tpl_path}")
            return False
        template_cv = cv2.imread(tpl_path)
        if template_cv is None:
            logger.error(f"无法读取模板: {tpl_path}")
            return False

        found = False
        for i in range(1, INITENV_MAX_ATTEMPTS + 1):
            logger.info(f"  [{i}/{INITENV_MAX_ATTEMPTS}] 检测 '{INITENV_TEMPLATE}'...")
            # 直接用原始匹配，不触发 find_image 的失败截图
            try:
                screenshot = d.screenshot(format="opencv")
                if screenshot is not None:
                    result = cv2.matchTemplate(screenshot, template_cv, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val >= 0.8:
                        h, w = template_cv.shape[:2]
                        cx = max_loc[0] + w // 2
                        cy = max_loc[1] + h // 2
                        logger.info(f"  检测到 '{INITENV_TEMPLATE}' 坐标: ({cx}, {cy}) 置信度: {max_val:.3f}")
                        found = True
                        break
            except Exception as e:
                logger.warning(f"  截图/匹配异常: {e}")

            logger.info(f"  未检测到 '{INITENV_TEMPLATE}', 执行 back")
            d.press("back")
            time.sleep(INITENV_INTERVAL)
        if not found:
            logger.error(f"环境初始化失败: 经过 {INITENV_MAX_ATTEMPTS} 次尝试仍未检测到 '{INITENV_TEMPLATE}'")
            return False
        logger.info("环境就绪，继续执行")

    # 4. 录制状态变量初始化
    record_stop_event = None
    record_thread = None
    frames_dir = None
    video_path = None
    workflow_name = Path(filepath).stem
    recording_started = False

    # 5. 执行
    total = len(steps)
    enabled_count = sum(1 for s in steps if s.get("enabled", True))
    logger.info(f"开始执行 ({enabled_count}/{total} 步启用)")
    logger.info("=" * 50)

    success_count = 0
    fail_count = 0
    skip_count = 0

    try:
        for i, step in enumerate(steps):
            step_num = i + 1
            if not step.get("enabled", True):
                skip_count += 1
                logger.info(f"  [{step_num}/{total}] ⏭ {step.get('desc', '')} (已禁用)")
                continue

            # screenrecord 步骤：标记录制起点
            if step.get("type") == "screenrecord":
                desc = step.get("desc", "screenrecord")
                if record and not recording_started:
                    os.makedirs(SCREENRECORDS_DIR, exist_ok=True)
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        frames_dir = os.path.join(SCREENRECORDS_DIR, f"{workflow_name}_{timestamp}_frames")
                        video_path = os.path.join(SCREENRECORDS_DIR, f"{workflow_name}_{timestamp}.gif")
                        os.makedirs(frames_dir, exist_ok=True)
                        record_stop_event = threading.Event()

                        def _capture_loop():
                            frame_index = 0
                            while not record_stop_event.is_set():
                                try:
                                    im = d.screenshot()
                                    if STATUS_BAR_HEIGHT > 0:
                                        im = im.crop((0, STATUS_BAR_HEIGHT, im.width, im.height))
                                    path = os.path.join(frames_dir, f"frame_{frame_index:04d}.png")
                                    im.save(path)
                                    frame_index += 1
                                except Exception as e:
                                    logger.error(f"截图失败: {e}")
                                record_stop_event.wait(RECORD_INTERVAL)

                        record_thread = threading.Thread(target=_capture_loop, daemon=True)
                        record_thread.start()
                        recording_started = True
                        logger.info(f"  [{step_num}/{total}] ▶ {desc} — 屏幕录制已开始")
                    except Exception as e:
                        logger.error(f"  [{step_num}/{total}] ✗ 启动录制失败: {e}")
                else:
                    logger.info(f"  [{step_num}/{total}] ▶ {desc}")
                continue

            ok = execute_step(d, step, step_num, total)
            if ok:
                success_count += 1
            else:
                fail_count += 1
                # 截图保存现场
                save_screenshot(d, f"step{step_num}_fail")
                if not continue_on_error:
                    logger.error(f"步骤 {step_num} 失败，终止执行")
                    break
    finally:
        # 6. 停止录制 → 合成 GIF
        if record_stop_event is not None:
            record_stop_event.set()
        if record_thread is not None:
            record_thread.join(timeout=5.0)

        if frames_dir is not None and video_path is not None:
            try:
                png_files = sorted(
                    os.path.join(frames_dir, f)
                    for f in os.listdir(frames_dir)
                    if f.endswith(".png")
                )
                if not png_files:
                    logger.warning("未截取到任何帧，跳过 GIF 生成")
                elif Image is None:
                    logger.warning(f"Pillow 未安装，无法合成 GIF，帧文件保留在: {frames_dir}")
                else:
                    frames = [Image.open(f) for f in png_files]
                    # 缩放 & 量化减色，降低 GIF 体积
                    opt_frames = []
                    for im in frames:
                        if RECORD_RESIZE_RATIO < 1.0:
                            w = int(im.width * RECORD_RESIZE_RATIO)
                            h = int(im.height * RECORD_RESIZE_RATIO)
                            im = im.resize((w, h), Image.LANCZOS)
                        im = im.quantize(colors=RECORD_GIF_COLORS, method=Image.MEDIANCUT)
                        opt_frames.append(im)
                    opt_frames[0].save(
                        video_path,
                        save_all=True,
                        append_images=opt_frames[1:],
                        duration=int(RECORD_INTERVAL * 1000),
                        loop=0,
                    )
                    logger.info(f"屏幕录制已保存: {video_path} ({len(frames)} 帧)")
                    shutil.rmtree(frames_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"GIF 合成失败: {e}")

    # 7. 汇总
    logger.info("=" * 50)
    logger.info(f"执行完成: ✓ {success_count} 成功, ✗ {fail_count} 失败, ⏭ {skip_count} 跳过")
    return fail_count == 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="执行 workflow_builder 生成的编排 JSON 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    python scripts/workflow_runner.py my_flow.json
    python scripts/workflow_runner.py flow1.json flow2.json    # 顺序执行多个
    python scripts/workflow_runner.py                          # 交互选择（支持多选）
    python scripts/workflow_runner.py --list                   # 列出可用工作流
    python scripts/workflow_runner.py flow1.json flow2.json --continue  # 遇错继续
        """,
    )
    parser.add_argument("workflows", nargs="*", default=None,
                        help="工作流 JSON 文件路径（多个用空格分隔，留空则交互选择）")
    parser.add_argument("--list", action="store_true",
                        help="列出 workflows/ 目录下所有工作流")
    parser.add_argument("--continue", dest="continue_on_error", action="store_true",
                        help="遇错时继续执行下一个步骤/工作流，不停止")
    parser.add_argument("--record", action="store_true",
                        help="录制屏幕操作，保存到 screenrecords/ 目录")
    parser.add_argument("--initenv", action="store_true",
                        help="执行前等待 wx_filetranshelper 出现，确保环境就绪")
    parser.add_argument("--templates-dir", default="templates",
                        help="模板图片目录 (默认: templates)")
    parser.add_argument("--workflows-dir", default="workflows",
                        help="工作流文件目录 (默认: workflows)")
    parser.add_argument("--screenrecords-dir", default="screenrecords",
                        help="录屏文件目录 (默认: screenrecords)")
    parser.add_argument("--screenshots-dir", default="screenshots",
                        help="截图保存目录 (默认: screenshots)")
    return parser.parse_args()


def main():
    setup_logger()
    args = parse_args()

    # 应用自定义目录（转绝对路径）
    global WORKFLOW_DIR, TEMPLATE_DIR, SCREENRECORDS_DIR
    WORKFLOW_DIR = os.path.abspath(args.workflows_dir)
    TEMPLATE_DIR = os.path.abspath(args.templates_dir)
    SCREENRECORDS_DIR = os.path.abspath(args.screenrecords_dir)
    screenshots_dir = os.path.abspath(args.screenshots_dir)
    # 同步到 step_executor 共享模块
    import mg_autotest.scripts.step_executor as _se
    _se.TEMPLATE_DIR = TEMPLATE_DIR
    _se.SCREENSHOTS_DIR = screenshots_dir

    print("=" * 50)
    print("  Workflow Runner")
    print("=" * 50)
    print(f"\n  模板目录:     {TEMPLATE_DIR}")
    print(f"  工作流目录:   {WORKFLOW_DIR}")
    print(f"  录屏目录:     {SCREENRECORDS_DIR}")
    print(f"  截图目录:     {screenshots_dir}")

    # --list 模式
    if args.list:
        files = list_workflows()
        if not files:
            print("\n  [Info] workflows/ 目录下没有 .json 文件")
        else:
            print(f"\n  共 {len(files)} 个工作流:")
            for f in files:
                print(f"    • {f}")
        return

    # 确定工作流文件列表
    workflow_files = args.workflows
    if not workflow_files:
        # 交互选择（支持多选）
        workflow_files = select_workflows_interactive()
    else:
        # 处理命令行传入的多个文件
        resolved = []
        for f in workflow_files:
            if os.path.isfile(f):
                resolved.append(f)
            else:
                alt = os.path.join(WORKFLOW_DIR, f)
                if os.path.isfile(alt):
                    resolved.append(alt)
                else:
                    print(f"\n  [Error] 文件不存在: {f}")
                    sys.exit(1)
        workflow_files = resolved

    # 运行一个或多个工作流
    print(f"\n  工作流数:   {len(workflow_files)}")
    print(f"  遇错继续:   {'是' if args.continue_on_error else '否（默认停止）'}")
    print(f"  屏幕录制:   {'是' if args.record else '否'}")
    print(f"  环境初始化: {'是' if args.initenv else '否'}")
    print()

    success_count = 0
    fail_count = 0
    for i, filepath in enumerate(workflow_files, 1):
        print(f"\n{'=' * 50}")
        print(f"  工作流 [{i}/{len(workflow_files)}]: {filepath}")
        print(f"{'=' * 50}")
        ok = run_workflow(filepath, continue_on_error=args.continue_on_error,
                          record=args.record, initenv=args.initenv)
        if ok:
            success_count += 1
        else:
            fail_count += 1
            if not args.continue_on_error:
                logger.warning(f"工作流 [{i}/{len(workflow_files)}] 失败，终止执行")
                break

    print(f"\n{'=' * 50}")
    if len(workflow_files) > 1:
        print(f"  全部完成: {success_count} 成功, {fail_count} 失败 / 共 {len(workflow_files)} 个")
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
