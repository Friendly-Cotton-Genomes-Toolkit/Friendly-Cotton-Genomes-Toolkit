# cotton_toolkit/utils/file_utils.py
import os
import pandas as pd
import gzip
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def prepare_input_file(
        original_path: str,
        status_callback: Callable[[str], None],
        temp_dir: str  # 需要一个目录来存放转换后的文件
) -> Optional[str]:
    """
    【通用版】预处理一个输入文件，确保其为标准的CSV格式，并使用缓存。
    支持 .csv, .txt, .xlsx 及其 .gz 压缩版本。

    :param original_path: 原始文件路径
    :param status_callback: 日志回调函数
    :param temp_dir: 用于存放缓存/转换后文件的目录
    :return: 标准化后的CSV文件路径，如果失败则返回None
    """
    if not os.path.exists(original_path):
        status_callback(f"ERROR: 输入文件不存在: {original_path}")
        return None

    # 创建缓存目录
    os.makedirs(temp_dir, exist_ok=True)

    # 定义缓存文件名
    base_name = os.path.basename(original_path)
    cache_file_name = f"{os.path.splitext(base_name)[0]}_standardized.csv"
    cached_csv_path = os.path.join(temp_dir, cache_file_name)

    # --- 缓存检查逻辑 (源自 enrichment_analyzer.py) ---
    if os.path.exists(cached_csv_path):
        try:
            original_mtime = os.path.getmtime(original_path)
            cached_mtime = os.path.getmtime(cached_csv_path)
            if cached_mtime >= original_mtime:
                status_callback(f"INFO: 发现有效的缓存文件，将直接使用: {os.path.basename(cached_csv_path)}")
                return cached_csv_path
        except OSError as e:
            status_callback(f"WARNING: 无法检查文件时间戳: {e}")

    status_callback(f"INFO: 正在处理新文件或已更新的文件: {base_name}")

    # --- 统一加载逻辑 ---
    df = None
    try:
        filename_lower = base_name.lower()

        # 使用上一个回复中我们已经完善的加载逻辑
        if filename_lower.endswith(('.xlsx', '.xlsx.gz')):
            opener = gzip.open if filename_lower.endswith('.gz') else open
            with opener(original_path, 'rb') as f:
                df = pd.read_excel(f, engine='openpyxl')

        elif filename_lower.endswith(('.csv', '.csv.gz')):
            df = pd.read_csv(original_path, compression='gzip' if filename_lower.endswith('.gz') else None)

        elif filename_lower.endswith(('.txt', '.txt.gz')):
            with (gzip.open(original_path, 'rt', encoding='utf-8') if filename_lower.endswith('.gz') else
            open(original_path, 'r', encoding='utf-8')) as f:
                line = f.readline()
                sep = '\t' if '\t' in line else ','
            df = pd.read_csv(original_path, sep=sep, compression='gzip' if filename_lower.endswith('.gz') else None)

        else:
            status_callback(f"ERROR: 不支持的文件格式: {base_name}")
            return None

        if df is not None:
            # --- 统一写入缓存 ---
            df.to_csv(cached_csv_path, index=False, encoding='utf-8-sig')
            status_callback(f"INFO: 文件已成功转换为标准CSV并缓存: {os.path.basename(cached_csv_path)}")
            return cached_csv_path

    except Exception as e:
        status_callback(f"ERROR: 处理文件 {base_name} 时发生严重错误: {e}")
        return None

    return None