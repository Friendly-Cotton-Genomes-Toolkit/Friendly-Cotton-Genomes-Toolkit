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
    将一个可能包含多个sheet的Excel文件（支持.gz压缩）转换为一个单一的CSV文件。
    - 使用第一个sheet的第3行作为最终CSV文件的表头。
    - 合并所有sheet从第4行开始的数据。

    Args:
        excel_path (str): 输入的Excel文件路径。
        output_csv_path (str): 输出的CSV文件路径。
        logger_func (Callable): 用于记录日志的回调函数。

    Returns:
        bool: 如果转换成功则返回 True，否则返回 False。
    """
    try:
        logger_func(f"INFO: Converting Excel file: {os.path.basename(excel_path)}")

        open_func = gzip.open if excel_path.lower().endswith('.gz') else open

        with open_func(excel_path, 'rb') as f:
            buffer = io.BytesIO(f.read())

        xls = pd.ExcelFile(buffer, engine='openpyxl')
        sheet_names = xls.sheet_names

        if not sheet_names:
            logger_func(f"WARNING: Excel file '{os.path.basename(excel_path)}' has no sheets.")
            return False

        # --- 步骤 1: 从第一个sheet的第3行提取表头 ---
        first_sheet_name = sheet_names[0]
        try:
            # skiprows=2 跳过前2行, nrows=1 只读取1行 (即第3行)
            header_df = pd.read_excel(xls, sheet_name=first_sheet_name, header=None, skiprows=2, nrows=1)
            if header_df.empty:
                raise ValueError("Header row is empty.")
            # 将表头行转换为列表，并将可能存在的空值(NaN)替换为 'Unnamed'
            csv_header = [str(h) if pd.notna(h) else f'Unnamed_{i}' for i, h in enumerate(header_df.iloc[0].tolist())]
        except Exception as e:
            logger_func(f"ERROR: Could not read header from the 3rd row of the first sheet '{first_sheet_name}'. Reason: {e}")
            return False

        # --- 步骤 2: 从所有sheet的第4行开始读取数据 ---
        all_sheets_data = []
        for sheet_name in sheet_names:
            # 对于每一个sheet (包括第一个), 都跳过前3行读取数据
            sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=3)
            all_sheets_data.append(sheet_df)

        # --- 步骤 3: 合并数据并应用提取的表头 ---
        if not all_sheets_data:
            logger_func(f"WARNING: No data found in any sheet after skipping the first 3 rows.")
            return False

        combined_df = pd.concat(all_sheets_data, ignore_index=True)
        combined_df.dropna(how='all', inplace=True)

        if combined_df.empty:
            logger_func(f"WARNING: No data left after combining all sheets and removing empty rows.")
            return False

        # 动态调整表头和数据列数，防止错位
        num_data_cols = len(combined_df.columns)
        num_header_cols = len(csv_header)

        if num_data_cols > num_header_cols:
            # 如果数据列多于表头列，为多出的数据列添加占位表头
            csv_header.extend([f'ExtraCol_{i+1}' for i in range(num_data_cols - num_header_cols)])
        elif num_header_cols > num_data_cols:
            # 如果表头列多于数据列，截断表头以匹配数据
            csv_header = csv_header[:num_data_cols]

        combined_df.columns = csv_header

        # 将最终的DataFrame保存为CSV文件
        combined_df.to_csv(output_csv_path, index=False)

        logger_func(f"SUCCESS: Converted file saved to: {os.path.basename(output_csv_path)}")
        return True

    except Exception as e:
        logger_func(f"ERROR: Failed to convert Excel file '{os.path.basename(excel_path)}'. Reason: {e}")
        return False