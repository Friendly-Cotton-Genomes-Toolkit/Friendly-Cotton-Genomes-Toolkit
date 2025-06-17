# cotton_toolkit/core/convertXlsx2csv.py

import pandas as pd
import gzip
import io
import os
from typing import Callable


def convert_excel_to_standard_csv(
        excel_path: str,
        output_csv_path: str,
        logger_func: Callable = print
) -> bool:
    """
    将一个可能包含多个sheet的Excel文件（支持.gz压缩）转换为一个单一的、标准的CSV文件。
    - 合并所有sheet的数据。
    - 忽略所有原始表头，并为合并后的数据设置标准表头 ['GeneID', 'TermID', 'Description', 'Namespace', ...]。

    Args:
        excel_path (str): 输入的Excel文件路径。
        output_csv_path (str): 输出的标准CSV文件路径。
        logger_func (Callable): 用于记录日志的回调函数。

    Returns:
        bool: 如果转换成功则返回 True，否则返回 False。
    """
    try:
        logger_func(f"INFO: Standardizing Excel file: {os.path.basename(excel_path)}")

        # 根据是否以 .gz 结尾来选择打开方式
        open_func = gzip.open if excel_path.lower().endswith('.gz') else open

        with open_func(excel_path, 'rb') as f:
            # 使用BytesIO作为内存中的二进制文件缓冲区
            buffer = io.BytesIO(f.read())

        # 读取所有sheet，header=None表示不将任何行作为表头
        all_sheets = pd.read_excel(buffer, sheet_name=None, header=None, engine='openpyxl')

        if not all_sheets:
            logger_func(f"WARNING: Excel file '{os.path.basename(excel_path)}' is empty or has no sheets.")
            return False

        # 使用concat将所有sheet的DataFrame垂直合并成一个
        combined_df = pd.concat(all_sheets.values(), ignore_index=True)

        # 去除完全为空的行
        combined_df.dropna(how='all', inplace=True)

        if combined_df.empty:
            logger_func(f"WARNING: After combining all sheets, no data was found in '{os.path.basename(excel_path)}'.")
            return False

        # 为合并后的数据设置标准化的列名
        num_columns = len(combined_df.columns)
        standard_headers = ['GeneID', 'TermID', 'Description', 'Namespace']
        # 根据实际列数动态生成表头
        new_headers = standard_headers[:num_columns]
        if num_columns > len(standard_headers):
            new_headers.extend([f'ExtraCol_{i + 1}' for i in range(num_columns - len(standard_headers))])

        combined_df.columns = new_headers

        # 将标准化的DataFrame保存为CSV文件，确保第一行是我们的标准表头
        combined_df.to_csv(output_csv_path, index=False)

        logger_func(f"SUCCESS: Standardized file saved to: {os.path.basename(output_csv_path)}")
        return True

    except Exception as e:
        logger_func(f"ERROR: Failed to convert Excel file '{os.path.basename(excel_path)}'. Reason: {e}")
        return False