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
    【核心功能】读取一个文件（支持 .csv, .xlsx, .txt, 以及它们的 .gz 压缩版），
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
        if filename.endswith('.xlsx') or filename.endswith('.xlsx.gz'):
            opener = gzip.open if is_gzipped else open
            mode = 'rb'  # Excel文件需要以二进制模式读取
            with opener(input_path, mode) as f:
                df = pd.read_excel(f, engine='openpyxl')

        elif filename.endswith('.csv') or filename.endswith('.csv.gz'):
            # pandas可以直接处理压缩的csv
            df = pd.read_csv(input_path, compression='gzip' if is_gzipped else None, on_bad_lines='warn')

        elif filename.endswith('.txt') or filename.endswith('.txt.gz'):
            # TXT文件通常是制表符或逗号分隔，我们尝试自动嗅探
            with (gzip.open(input_path, 'rt', encoding='utf-8') if is_gzipped else
            open(input_path, 'r', encoding='utf-8')) as f:
                first_line = f.readline()
                # 简单嗅探分隔符
                if '\t' in first_line:
                    sep = '\t'
                else:
                    sep = ','

            df = pd.read_csv(input_path, sep=sep, compression='gzip' if is_gzipped else None, on_bad_lines='warn')

        else:
            logger.warning(_("不支持的文件格式或无法识别的文件: {}").format(filename))
            return None

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
            df.to_csv(output_path, index=False, encoding='utf-8-sig')  # 使用 utf-8-sig 以便Excel正确打开
            logger.info(_("已成功将文件转换为CSV格式: {}").format(output_path))
            return output_path
        except Exception as e:
            logger.error(_("无法将DataFrame写入CSV文件 '{}': {}").format(output_path, e))
            return None
    return None