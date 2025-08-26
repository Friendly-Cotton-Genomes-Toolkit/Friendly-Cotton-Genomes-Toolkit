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
        error_msg = _("输入文件不存在: {}").format(input_path)
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

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
            df = pd.read_csv(input_path, compression='gzip' if is_gzipped else None, on_bad_lines='warn',
                             header=0)  # 假定有表头

        # --- 3. 处理 TXT 文件 (智能识别分隔符) ---
        elif filename.endswith('.txt') or filename.endswith('.txt.gz'):
            opener = gzip.open if is_gzipped else open
            mode = 'rt' if is_gzipped else 'r'
            with opener(input_path, mode, encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                if '\t' in first_line:
                    sep = '\t'
                    logger.info(_("检测到 TXT 文件的分隔符为: '{}'").format('Tab'))
                    # 检查逗号
                elif ',' in first_line:
                    sep = ','
                    logger.info(_("检测到 TXT 文件的分隔符为: '{}'").format('Comma'))
                    # 检查多个连续空格（至少2个）
                elif '  ' in first_line:
                    sep = r'\s+'  # 使用正则表达式匹配一个或多个空白字符
                    logger.info(_("检测到 TXT 文件的分隔符为: '{}'").format('Multiple Spaces'))
                else:
                    sep = None
                    logger.warning(_("无法自动检测 TXT 文件的分隔符，尝试使用默认空格。"))

            # 分隔符是多个空格
            engine = 'python' if sep == r'\s+' else 'c'

            # 使用嗅探到的分隔符或默认空格读取，并明确指出无表头
            df = pd.read_csv(input_path, sep=sep, compression='gzip' if is_gzipped else None,
                             on_bad_lines='warn', header=None, engine=engine)

        else:
            logger.warning(_("不支持的文件格式或无法识别的文件: {}").format(filename))
            return None

        # --- 统一列名与表头自定义 ---
        if df is not None:
            # 检查列名是否为默认整数（无表头）
            if all(isinstance(c, int) for c in df.columns):

                # 【核心修改】
                custom_headers = ['Query', 'Match', 'Description']
                original_num_cols = len(df.columns)

                # 确保 DataFrame 至少有三列
                if original_num_cols < len(custom_headers):
                    for i in range(len(custom_headers) - original_num_cols):
                        df[original_num_cols + i] = pd.NA

                # 填充自定义表头
                new_columns = []
                for i in range(len(df.columns)):
                    if i < len(custom_headers):
                        new_columns.append(custom_headers[i])
                    else:
                        # 如果列数超过预设表头，使用原始的默认命名
                        new_columns.append(f'Column_{i + 1}')

                df.columns = new_columns
                logger.info(_("检测到无表头，已使用预设表头 'Query', 'Match', 'Description'。"))

            logger.info(_("成功将 '{}' 加载到DataFrame。").format(filename))

            # --- 处理包含 "|" 的列，将其拆分为多行 ---
            logger.info(_("正在检查并拆分包含 '|' 的单元格..."))
            for col in df.columns:
                if df[col].dtype == 'object' and df[col].astype(str).str.contains('|', regex=False).any():
                    logger.info(_("发现列 '{}' 包含 '|' 分隔符，正在执行拆分...").format(col))
                    try:
                        df[col] = df[col].astype(str).str.split('|')
                        df = df.explode(col)
                        logger.info(_("列 '{}' 拆分成功，DataFrame已更新。").format(col))
                    except Exception as e:
                        logger.warning(_("处理列 '{}' 时拆分失败: {}").format(col, e))

            return df

    except Exception as e:
        error_msg = _("处理文件 '{}' 时发生错误: {}").format(os.path.basename(input_path).lower(), e)
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def normalize_to_csv(input_path: str, output_path: str) -> Optional[str]:
    """
    将支持的输入文件转换为一个标准的CSV文件。

    :param input_path: 输入文件的路径。
    :param output_path: 输出CSV文件的路径。
    :return: 如果成功，返回输出文件的路径，否则返回None。
    """
    df = normalize_to_dataframe(input_path)
    logger.debug(f"DataFrame is None: {df is None}")

    if df is not None:
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                logger.debug(f"csv尝试写入到: {output_path}")

            df.to_csv(output_path, index=False, encoding='utf-8-sig')  # 使用 utf-8-sig 以便Excel正确打开
            logger.info(_("已成功将文件转换为CSV格式: {}").format(output_path))
            return output_path
        except Exception as e:
            error_msg = _("无法将DataFrame写入CSV文件 '{}': {}").format(output_path, e)
            logger.error(error_msg)
            raise IOError(error_msg) from e

    return None
