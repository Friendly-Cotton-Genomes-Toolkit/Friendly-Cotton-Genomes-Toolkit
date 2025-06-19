# cotton_toolkit/core/file_normalizer.py

import pandas as pd
import gzip
import os
import openpyxl  # pandas 读取 .xlsx 文件需要此依赖
import logging
from typing import Optional

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.file_normalizer")


def normalize_to_dataframe(input_path: str) -> Optional[pd.DataFrame]:
    """
    读取一个文件（支持 .csv, .xlsx, .txt, 以及它们的 .gz 压缩版），
    并将其转换为一个 pandas DataFrame。

    GFF 文件是一个特例，不在此函数处理范围内，应由 gff_parser.py 处理。

    :param input_path: 输入文件的路径。
    :return: 包含文件数据的 pandas DataFrame，如果失败则返回 None。
    """
    if not os.path.exists(input_path):
        logger.error(_("输入文件不存在: {}").format(input_path))
        return None

    filename = os.path.basename(input_path).lower()
    is_gzipped = filename.endswith('.gz')

    df = None
    logger.info(_("正在尝试将 '{}' 标准化为DataFrame...").format(filename))

    try:
        # --- 1. 处理 Excel 文件 ---
        if filename.endswith('.xlsx') or filename.endswith('.xlsx.gz'):
            opener = gzip.open if is_gzipped else open
            mode = 'rb'  # Excel文件需要以二进制模式读取
            with opener(input_path, mode) as f:
                # 为了通用性，我们将合并所有sheet
                all_sheets = pd.read_excel(f, engine='openpyxl', sheet_name=None, header=None)
                df = pd.concat(all_sheets.values(), ignore_index=True)

        # --- 2. 处理 CSV 文件 ---
        elif filename.endswith('.csv') or filename.endswith('.csv.gz'):
            # pandas可以直接处理压缩的csv
            df = pd.read_csv(input_path, compression='gzip' if is_gzipped else None, on_bad_lines='warn', header=0) # 假定有表头

        # --- 3. 处理 TXT 文件 (智能识别分隔符) ---
        elif filename.endswith('.txt') or filename.endswith('.txt.gz'):
            opener = gzip.open if is_gzipped else open
            mode = 'rt' if is_gzipped else 'r'
            with opener(input_path, mode, encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                # 简单嗅探分隔符
                sep = '\t' if '\t' in first_line else ','
                logger.info(_("检测到 TXT 文件的分隔符为: '{}'").format('Tab' if sep == '\t' else 'Comma'))

            # 使用嗅探到的分隔符读取，并明确指出无表头
            df = pd.read_csv(input_path, sep=sep, compression='gzip' if is_gzipped else None, on_bad_lines='warn', header=None)

        else:
            logger.warning(_("不支持的文件格式或无法识别的文件: {}").format(filename))
            return None

        # --- 统一列名 ---
        # 为无表头的文件（如TXT）或合并后的Excel生成标准列名
        if df is not None and all(isinstance(c, int) for c in df.columns):
             df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]

        logger.info(_("成功将 '{}' 加载到DataFrame。").format(filename))
        return df

    except Exception as e:
        logger.error(_("处理文件 '{}' 时发生错误: {}").format(filename, e))
        return None


def normalize_to_csv(input_path: str, output_path: str) -> Optional[str]:
    """
    将支持的输入文件转换为一个标准的CSV文件。

    :param input_path: 输入文件的路径。
    :param output_path: 输出CSV文件的路径。
    :return: 如果成功，返回输出文件的路径，否则返回None。
    """
    df = normalize_to_dataframe(input_path)
    if df is not None:
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            df.to_csv(output_path, index=False, encoding='utf-8-sig')  # 使用 utf-8-sig 以便Excel正确打开
            logger.info(_("已成功将文件转换为CSV格式: {}").format(output_path))
            return output_path
        except Exception as e:
            logger.error(_("无法将DataFrame写入CSV文件 '{}': {}").format(output_path, e))
            return None
    return None