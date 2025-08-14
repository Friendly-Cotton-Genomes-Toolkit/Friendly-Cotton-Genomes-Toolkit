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


# --- ANSI颜色代码 ---
class AnsiColors:
    """定义ANSI颜色代码"""
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    FAINT = '\033[2m'


# --- 自定义日志处理器和流重定向 ---
class QueueHandler(logging.Handler):
    """一个将日志记录发送到队列的处理器。"""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        # QueueHandler不需要颜色，因为是给GUI使用的
        self.formatter = logging.Formatter(
            '[%(levelname)s] [%(asctime)s] <%(name)s> %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def emit(self, record: logging.LogRecord):
        self.log_queue.put(record)

class StreamToQueue:
    """一个将流（如sys.stdout）重定向到队列的类。"""

    def __init__(self, log_queue: queue.Queue, level: str = "INFO"):
        self.log_queue = log_queue
        self.level = level
        self.stream_logger = logging.getLogger("stdout")
        self.formatter = logging.Formatter(
            '[%(levelname)s] [%(asctime)s] <%(name)s> %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            record = self.stream_logger.makeRecord(
                self.stream_logger.name, self.level, fn=None, lno=None, msg=line,
                args=None, exc_info=None, func=None
            )
            formatted_message = self.formatter.format(record)
            self.log_queue.put((formatted_message, record.levelname))

    def flush(self):
        pass


# --- 带颜色的日志格式化器 ---
class ColoredFormatter(logging.Formatter):
    """一个为特定日志级别添加ANSI颜色的格式化器。"""

    def __init__(self, fmt: str, datefmt: str):
        super().__init__(fmt, datefmt)
        self.level_colors = {
            # DEBUG和INFO不指定颜色，使用系统默认色
            logging.WARNING: AnsiColors.YELLOW,
            logging.ERROR: AnsiColors.RED,
            logging.CRITICAL: AnsiColors.BOLD + AnsiColors.RED
        }

    def format(self, record: logging.LogRecord):
        # 获取颜色代码，如果没有则使用默认重置
        color_code = self.level_colors.get(record.levelno, AnsiColors.RESET)

        # 格式化消息并添加颜色
        message = super().format(record)

        # 将颜色代码插入到格式化消息的开头，并在结尾重置颜色
        colored_message = f"{color_code}{message}{AnsiColors.RESET}"
        return colored_message


# --- 统一的日志设置函数 ---

def setup_global_logger(
        log_level_str: str = "INFO",
        log_queue: Optional[queue.Queue] = None
):
    """
    设置全局统一的日志系统。
    """
    root_logger = logging.getLogger()
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # 清理已存在的处理器，避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 设置根日志级别
    root_logger.setLevel(logging.DEBUG)  # 捕获所有级别的日志，由处理器决定输出哪些

    # 定义通用的日志格式字符串，移除level name的填充
    log_format = '[%(levelname)s] [%(asctime)s] <%(name)s> %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # 1. 创建控制台处理器，并使用带颜色的格式化器
    console_formatter = ColoredFormatter(fmt=log_format, datefmt=date_format)
    console_handler = logging.StreamHandler(sys.__stdout__)  # 确保输出到原始控制台
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. 如果提供了队列（说明是在GUI环境中），则添加队列处理器并重定向stdout/stderr
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(log_level)  # GUI日志级别与控制台保持一致
        root_logger.addHandler(queue_handler)

        # 重定向print()和错误输出到GUI
        sys.stdout = StreamToQueue(log_queue, "INFO")
        sys.stderr = StreamToQueue(log_queue, "ERROR")

    fc = _("全局日志系统已初始化，级别设置为: {}")
    logging.info(fc.format(log_level_str))


def set_log_level(log_level_str: str):
    """动态调整所有处理器的日志级别。"""
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setLevel(log_level)
    logging.info(_("全局日志级别已更新为: {}").format(log_level_str))