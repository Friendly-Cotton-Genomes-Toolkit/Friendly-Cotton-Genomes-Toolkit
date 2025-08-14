# cotton_toolkit/core/convertXlsx2csv.py
import traceback
import logging

import pandas as pd
import gzip
import io
import os
import threading
from typing import Optional, List

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# --- 使用统一的日志系统 ---
logger = logging.getLogger("cotton_toolkit.core.convertXlsx2csv")


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
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']

    try:
        logger.info(_("Starting intelligent conversion for: {}").format(os.path.basename(excel_path)))

        if cancel_event and cancel_event.is_set():
            logger.info(_("Conversion cancelled before starting."))
            return False

        open_func = gzip.open if excel_path.lower().endswith('.gz') else open
        with open_func(excel_path, 'rb') as f:
            xls = pd.ExcelFile(io.BytesIO(f.read()), engine='openpyxl')

        all_data_frames = []
        for sheet_name in xls.sheet_names:
            if cancel_event and cancel_event.is_set():
                logger.info(_("Conversion cancelled while processing sheets."))
                return False

            logger.debug(f"Processing sheet: '{sheet_name}'...")
            try:
                preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
                header_row_index = _find_header_row(preview_df, header_keywords)

                if header_row_index is not None:
                    logger.debug(_("Header found in sheet '{}' at row {}.").format(sheet_name, header_row_index + 1))
                    sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                    sheet_df.dropna(how='all', inplace=True)
                    all_data_frames.append(sheet_df)
                else:
                    logger.warning(_("No valid header found in sheet '{}'. Skipping this sheet.").format(sheet_name))
            except Exception as e:
                logger.error(_("Failed to process sheet '{}'. Reason: {}").format(sheet_name, e))

        if not all_data_frames:
            logger.error(_("No data could be extracted from any sheet in the Excel file."))
            return False

        combined_df = pd.concat(all_data_frames, ignore_index=True)
        combined_df.dropna(how='all', inplace=True)

        if cancel_event and cancel_event.is_set():
            logger.info(_("Conversion cancelled before writing file."))
            return False

        combined_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        logger.info(_("Successfully converted and saved to: {}").format(os.path.basename(output_csv_path)))
        return True

    except Exception as e:
        logger.exception(_("A critical error occurred during Excel to CSV conversion. Reason: {}").format(e))
        return False