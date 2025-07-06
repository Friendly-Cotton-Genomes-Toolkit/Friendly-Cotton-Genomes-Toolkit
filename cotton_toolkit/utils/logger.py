# cotton_toolkit/utils/logger.py

import logging
import queue
import sys
from typing import Optional

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


# --- 自定义日志处理器和流重定向 ---

class QueueHandler(logging.Handler):
    """一个将日志记录发送到队列的处理器。"""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        self.log_queue.put((record.getMessage(), record.levelname))


class StreamToQueue:
    """一个将流（如sys.stdout）重定向到队列的类。"""

    def __init__(self, log_queue: queue.Queue, level: str = "INFO"):
        self.log_queue = log_queue
        self.level = level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.log_queue.put((line, self.level))

    def flush(self):
        pass  # 在多线程GUI应用中，flush通常是空操作


# --- 统一的日志设置函数 ---

def setup_global_logger(
        log_level_str: str = "INFO",
        log_queue: Optional[queue.Queue] = None
):
    """
    设置全局统一的日志系统。

    Args:
        log_level_str (str): 日志级别字符串 (e.g., "INFO", "DEBUG").
        log_queue (Optional[queue.Queue]): 如果提供，则会添加一个队列处理器以将日志发送到GUI。
    """
    root_logger = logging.getLogger()
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # 清理已存在的处理器，避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 设置根日志级别
    root_logger.setLevel(logging.DEBUG)  # 捕获所有级别的日志，由处理器决定输出哪些

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. 始终创建控制台处理器
    console_handler = logging.StreamHandler(sys.__stdout__)  # 确保输出到原始控制台
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. 如果提供了队列（说明是在GUI环境中），则添加队列处理器并重定向stdout/stderr
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(log_level)  # GUI日志级别与控制台保持一致
        root_logger.addHandler(queue_handler)

        # 重定向print()和错误输出到GUI
        sys.stdout = StreamToQueue(log_queue, "INFO")
        sys.stderr = StreamToQueue(log_queue, "ERROR")

    logging.info(_("全局日志系统已初始化，级别设置为: {}").format(log_level_str))


def set_log_level(log_level_str: str):
    """动态调整所有处理器的日志级别。"""
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setLevel(log_level)
    logging.info(_("全局日志级别已更新为: {}").format(log_level_str))