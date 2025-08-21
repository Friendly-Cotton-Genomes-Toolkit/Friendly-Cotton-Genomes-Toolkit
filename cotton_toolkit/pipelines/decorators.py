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
            # 没有就报错
            cancel_event = kwargs['cancel_event']

            progress = lambda p, m: None

            def check_cancel():
                if cancel_event and cancel_event.is_set():
                    logger.info(_("任务 '{}' 已被用户取消。").format(task_name))
                    return True
                return False

            kwargs['check_cancel'] = check_cancel
            kwargs['progress_callback'] = progress

            logger.info(_("--- 开始执行流水线任务: {} ---").format(task_name))
            progress(0, _("{} - 任务启动...").format(task_name))

            if check_cancel():
                return None

            try:
                result = func(*args, **kwargs)
                logger.info(_("--- 流水线任务成功完成: {} ---").format(task_name))
                progress(100, _("{} - 任务完成。").format(task_name))
                return result
            except Exception as e:
                logger.exception(_("流水线任务 '{}' 发生意外错误: {}").format(task_name, e))
                progress(100, _("{} - 任务因错误而终止。").format(task_name))
                return None

        return wrapper

    return decorator