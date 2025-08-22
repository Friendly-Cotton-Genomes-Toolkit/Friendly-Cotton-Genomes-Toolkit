# cotton_toolkit/pipelines/decorators.py
import functools
import logging
import threading
from typing import Callable

try:
    from builtins import _
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines.decorators")


def pipeline_task(task_name: str):
    """
    一个装饰器，用于封装流水线任务的通用逻辑：
    - 统一的日志记录
    - 进度回调初始化
    - 中断事件检查
    - 全局异常捕获
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cancel_event = kwargs.get('cancel_event')
            if not cancel_event:
                # 如果调用者没有提供 cancel_event，创建一个默认的以避免崩溃
                cancel_event = threading.Event()
                kwargs['cancel_event'] = cancel_event


            # 如果调用者（如此处的UI层）提供了进度回调，就使用它
            # 否则，使用一个什么也不做的默认回调
            progress = kwargs.get('progress_callback', lambda p, m: None)

            def check_cancel():
                if cancel_event.is_set():
                    logger.info(_("任务 '{}' 已被用户取消。").format(task_name))
                    return True
                return False

            # 将检查函数和最终要使用的进度回调注入到 kwargs 中
            # 这样，被装饰的函数（如 run_ai_task）就可以统一使用它们
            kwargs['check_cancel'] = check_cancel
            kwargs['progress_callback'] = progress

            logger.info(_("--- 开始执行流水线任务: {} ---").format(task_name))
            # 确保即使后台任务没有立即报告进度，UI上也会显示启动信息
            progress(0, _("{} - 任务启动...").format(task_name))

            if check_cancel():
                return None

            try:
                result = func(*args, **kwargs)
                if not check_cancel():  # 只有在任务未被取消时才显示成功
                    logger.info(_("--- 流水线任务成功完成: {} ---").format(task_name))
                    progress(100, _("{} - 任务完成。").format(task_name))
                return result
            except Exception as e:
                logger.exception(_("流水线任务 '{}' 发生意外错误: {}").format(task_name, e))
                progress(100, _("{} - 任务因错误而终止。").format(task_name))
                # 可以在这里添加一个额外的回调来显示错误对话框
                return None

        return wrapper

    return decorator