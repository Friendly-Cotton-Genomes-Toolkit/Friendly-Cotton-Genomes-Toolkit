# cotton_toolkit/core/convertXlsx2csv.py
import traceback

import pandas as pd
import gzip
import io
import os
import threading
from typing import Callable, Optional, List


def _find_header_row(sheet_df: pd.DataFrame, keywords: List[str]) -> Optional[int]:
    """在一个工作表中寻找包含指定关键字的表头行，检查前3行。"""
    for i in range(min(3, len(sheet_df))):
        row_values = [str(v).lower() for v in sheet_df.iloc[i].values]
        if any(keyword.lower() in row_values for keyword in keywords):
            return i
    return None


def convert_excel_to_standard_csv(
        excel_path: str,
        output_csv_path: str,
        status_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> bool:
    """
    智能地将一个Excel文件（可含多Sheet，支持.gz压缩）转换为一个单一的、干净的CSV文件。
    - 智能搜索表头：在每个Sheet的前3行中查找包含关键字的表头。
    - 合并所有Sheet：将所有找到的有效数据合并。
    - 清理空行：自动移除所有完全为空的行。
    - 支持取消：在处理过程中可被中断。
    """
    log = status_callback if status_callback else print
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']  # 用于识别表头的关键字

    try:
        log(f"INFO: Starting intelligent conversion for: {os.path.basename(excel_path)}", "INFO")

        if cancel_event and cancel_event.is_set():
            log("INFO: Conversion cancelled before starting.", "INFO");
            return False

        open_func = gzip.open if excel_path.lower().endswith('.gz') else open
        with open_func(excel_path, 'rb') as f:
            xls = pd.ExcelFile(io.BytesIO(f.read()), engine='openpyxl')

        all_data_frames = []
        for sheet_name in xls.sheet_names:
            if cancel_event and cancel_event.is_set():
                log("INFO: Conversion cancelled while processing sheets.", "INFO");
                return False

            log(f"DEBUG: Processing sheet: '{sheet_name}'...", "DEBUG")
            try:
                # 先读取一个预览版来找表头，避免加载整个大文件
                preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
                header_row_index = _find_header_row(preview_df, header_keywords)

                if header_row_index is not None:
                    log(f"DEBUG: Header found in sheet '{sheet_name}' at row {header_row_index + 1}.", "DEBUG")
                    # 找到表头后，从表头行开始重新读取整个sheet
                    sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                    # 清理完全是空值的行
                    sheet_df.dropna(how='all', inplace=True)
                    all_data_frames.append(sheet_df)
                else:
                    log(f"WARNING: No valid header found in sheet '{sheet_name}'. Skipping this sheet.", "WARNING")
            except Exception as e:
                log(f"ERROR: Failed to process sheet '{sheet_name}'. Reason: {e}", "ERROR")

        if not all_data_frames:
            log("ERROR: No data could be extracted from any sheet in the Excel file.", "ERROR")
            return False

        # 合并所有找到的数据
        combined_df = pd.concat(all_data_frames, ignore_index=True)
        # 再次清理，确保合并后没有空行
        combined_df.dropna(how='all', inplace=True)

        if cancel_event and cancel_event.is_set():
            log("INFO: Conversion cancelled before writing file.", "INFO");
            return False

        combined_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        log(f"SUCCESS: Successfully converted and saved to: {os.path.basename(output_csv_path)}", "INFO")
        return True

    except Exception as e:
        log(f"ERROR: A critical error occurred during Excel to CSV conversion. Reason: {e}", "ERROR")
        traceback.print_exc()
        return False