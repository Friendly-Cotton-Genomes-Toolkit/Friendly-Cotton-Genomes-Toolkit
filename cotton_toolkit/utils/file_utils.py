# cotton_toolkit/utils/file_utils.py
import os
import pandas as pd
import gzip
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def prepare_input_file(
        original_path: str,
        status_callback: Callable[[str, str], None],
        temp_dir: str
) -> Optional[str]:
    """
    【通用版】预处理一个输入文件，确保其为标准的CSV格式，并使用缓存。
    支持 .csv, .txt, .xlsx 及其 .gz 压缩版本。

    :param original_path: 原始文件路径
    :param status_callback: 日志回调函数 (msg, level)
    :param temp_dir: 用于存放缓存/转换后文件的目录
    :return: 标准化后的CSV文件路径，如果失败则返回None
    """
    if not os.path.exists(original_path):
        status_callback(f"ERROR: 输入文件不存在: {original_path}", "ERROR")
        return None

    os.makedirs(temp_dir, exist_ok=True)

    base_name = os.path.basename(original_path)
    # 标准化缓存文件名，去除所有原始扩展名
    cache_base_name = base_name.split('.')[0]
    cached_csv_path = os.path.join(temp_dir, f"{cache_base_name}_standardized.csv")

    # --- 缓存检查：如果原始文件未变，直接使用缓存 ---
    if os.path.exists(cached_csv_path):
        try:
            original_mtime = os.path.getmtime(original_path)
            cached_mtime = os.path.getmtime(cached_csv_path)
            if cached_mtime >= original_mtime:
                status_callback(f"发现有效的缓存文件，将直接使用: {os.path.basename(cached_csv_path)}", "INFO")
                return cached_csv_path
        except OSError as e:
            status_callback(f"无法检查文件时间戳: {e}", "WARNING")

    status_callback(f"正在处理新文件或已更新的文件: {base_name}", "INFO")

    # --- 调用核心规范器进行转换 ---
    try:
        # 这里直接调用我们刚刚创建的强大函数
        result_path = normalize_to_csv(original_path, cached_csv_path)
        if result_path:
            status_callback(f"文件已成功转换为标准CSV并缓存: {os.path.basename(cached_csv_path)}", "INFO")
            return result_path
        else:
            status_callback(f"文件规范化失败: {base_name}", "ERROR")
            return None
    except Exception as e:
        status_callback(f"处理文件 {base_name} 时发生严重错误: {e}", "ERROR")
        return None