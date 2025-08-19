# cotton_toolkit/core/convertFiles2sqlite.py
import traceback
import logging
import pandas as pd
import sqlite3
import os
import threading
import gzip
import io
import re
from typing import Optional, List, Union

from cotton_toolkit.utils.file_utils import _sanitize_table_name

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# --- 使用统一的日志系统 ---
logger = logging.getLogger("cotton_toolkit.core.convertFiles2sqlite")


def _read_annotation_text_file(file_path: str) -> Optional[pd.DataFrame]:
    """
    【全新专用函数】为GO, KEGG, IPR等注释文本文件设计的解析器。
    - 严格将每一行解析为三列：Query, Match, Description。
    - 将第一个连续的空白块作为列分隔符。
    - 分号(;)不被视为分隔符。
    - 对'Match'列中的'|'进行行展开。
    """
    logger.debug(f"Using dedicated annotation parser for: {os.path.basename(file_path)}")

    processed_data = []
    header = ['Query', 'Match', 'Description']

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 使用正则表达式 `\s+` 匹配第一个连续的空白块，且只分割2次，产生最多3个部分
                parts = re.split(r'\s+', line, maxsplit=2)

                # 补齐至三列
                while len(parts) < 3:
                    parts.append(None)

                processed_data.append(parts[:3])  # 只取前三列，防止意外

        if not processed_data:
            logger.warning(f"No valid data lines found in '{os.path.basename(file_path)}'")
            return pd.DataFrame(columns=header)

        df = pd.DataFrame(processed_data, columns=header)

        # --- 后续处理：行展开（逻辑保持不变） ---
        df['Match'] = df['Match'].astype(str).fillna('')
        if df['Match'].str.contains(r'\|', regex=True).any():
            logger.debug(f"Found '|' in 'Match' column. Proceeding with row expansion.")
            df['Match'] = df['Match'].str.split('|')
            df = df.explode('Match', ignore_index=True)

        # 清理所有列的前后空格
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

        logger.info(f"Successfully parsed annotation file '{os.path.basename(file_path)}' into 3 columns.")
        return df

    except Exception as e:
        logger.error(f"Failed to process annotation file '{os.path.basename(file_path)}'. Reason: {e}")
        logger.debug(traceback.format_exc())
        return None


def _find_header_row_excel(sheet_df: pd.DataFrame, keywords: List[str]) -> Optional[int]:
    """在一个Excel工作表中寻找包含指定关键字的表头行，检查前5行。"""
    for i in range(min(5, len(sheet_df))):
        try:
            row_values = [str(v).lower() for v in sheet_df.iloc[i].values]
            if any(keyword.lower() in row_values for keyword in keywords):
                return i
        except IndexError:
            continue
    return None


def _read_excel_to_dataframe(file_path: str) -> Optional[pd.DataFrame]:
    """
    智能读取单个Excel文件（xlsx或xlsx.gz），合并所有Sheet页为一个DataFrame。
    """
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']  # 沿用之前的关键词
    logger.debug(f"Reading Excel file: {os.path.basename(file_path)}")

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rb') as f:
            # 读取到内存中以提高性能
            file_content = io.BytesIO(f.read())
            xls = pd.ExcelFile(file_content, engine='openpyxl')

        all_data_frames = []
        for sheet_name in xls.sheet_names:
            preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
            header_row_index = _find_header_row_excel(preview_df, header_keywords)

            if header_row_index is not None:
                logger.debug(f"Header found in sheet '{sheet_name}' at row {header_row_index + 1}.")
                sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                sheet_df.dropna(how='all', inplace=True)
                if not sheet_df.empty:
                    all_data_frames.append(sheet_df)
            else:
                logger.warning(f"No valid header found in sheet '{sheet_name}'. Skipping this sheet.")

        if not all_data_frames:
            logger.error(f"No data could be extracted from any sheet in Excel file: {os.path.basename(file_path)}")
            return None

        combined_df = pd.concat(all_data_frames, ignore_index=True)
        combined_df.dropna(how='all', inplace=True)
        return combined_df

    except Exception as e:
        logger.error(f"Failed to process Excel file '{os.path.basename(file_path)}'. Reason: {e}")
        return None


def _read_text_to_dataframe(file_path: str) -> Optional[pd.DataFrame]:
    """
    【最终版】读取文本文件，兼容多种格式，强制添加三列表头，并处理“|”多值行。
    1. 依次尝试用Tab、逗号、任意空白作为分隔符读取文件。
    2. 使用严格的判断(必须解析出多于一列)，防止“假成功”。
    3. 在解析后，为DataFrame强制指定['Query', 'Match', 'Description']三列，不足则补为空列。
    4. 对'Match'列中的'|'进行行展开操作。
    """
    logger.debug(f"Starting robust parsing for text file: {os.path.basename(file_path)}")

    df: Optional[pd.DataFrame] = None
    parsing_method = "Unknown"

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rb') as f:
            content_bytes = f.read()
        content_str = content_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Failed to read file content for '{os.path.basename(file_path)}'. Reason: {e}")
        return None

    # --- 步骤 1: 使用多种后备策略尝试解析文件 ---
    # 策略1: 尝试用Tab分隔符
    try:
        df_temp = pd.read_csv(io.StringIO(content_str), sep='\t', header=None, comment='#', skip_blank_lines=True)
        if df_temp.shape[1] > 1:
            df = df_temp.dropna(how='all')
            parsing_method = "Tab"
            logger.debug(f"Successfully parsed with Tab separator.")
    except Exception:
        logger.debug("Parsing with Tab failed, trying next method.")

    # 策略2: 尝试用逗号分隔符
    if df is None:
        try:
            df_temp = pd.read_csv(io.StringIO(content_str), sep=',', header=None, comment='#', skip_blank_lines=True)
            if df_temp.shape[1] > 1:
                df = df_temp.dropna(how='all')
                parsing_method = "Comma"
                logger.debug(f"Successfully parsed with Comma separator.")
        except Exception:
            logger.debug("Parsing with Comma failed, trying next method.")

    # 策略3: 尝试用一个或多个空白作为分隔符
    if df is None:
        try:
            df = pd.read_csv(io.StringIO(content_str), sep=r'\s+', header=None, comment='#', skip_blank_lines=True,
                             engine='python').dropna(how='all')
            parsing_method = "Whitespace"
            logger.debug(f"Successfully parsed with Whitespace separator.")
        except Exception:
            logger.debug("Parsing with Whitespace failed, trying final fallback.")

    # 策略4: 最终的“逐行容错解析”后备方案
    if df is None:
        try:
            lines = [line.strip() for line in content_str.splitlines() if line.strip() and not line.startswith('#')]
            if lines:
                split_lines = [line.split() for line in lines]
                max_cols = max(len(row) for row in split_lines) if split_lines else 0
                if max_cols > 0:  # 只要有数据就进行处理
                    padded_data = [row + [None] * (max_cols - len(row)) for row in split_lines]
                    df = pd.DataFrame(padded_data).dropna(how='all')
                    parsing_method = "Line-by-line Fallback"
                    logger.debug(f"Successfully parsed with Line-by-line Fallback.")
        except Exception as e:
            logger.error(f"All parsing methods failed for '{os.path.basename(file_path)}'. Final error: {e}")
            return None

    if df is None or df.empty:
        logger.warning(f"File '{os.path.basename(file_path)}' contains no valid data after all parsing attempts.")
        return None

    logger.info(f"Successfully parsed '{os.path.basename(file_path)}' using method: {parsing_method}.")

    # --- 步骤 2: 强制添加指定的表头，并确保三列都存在 ---

    num_cols = df.shape[1]
    header = ['Query', 'Match', 'Description']

    # 根据解析出的实际列数，重命名并补齐
    if num_cols == 1:
        df.columns = ['Query']
        df['Match'] = None
        df['Description'] = None
    elif num_cols == 2:
        df.columns = ['Query', 'Match']
        df['Description'] = None
    else:  # num_cols >= 3
        # 只重命名我们关心的前三列
        df.rename(columns={i: header[i] for i in range(3)}, inplace=True)

    # 确保最终的列顺序是我们期望的
    # 如果原始列超过3列，这里会保留多余的列，如果不需要可以去掉
    final_columns = header + [col for col in df.columns if col not in header]
    df = df[final_columns]
    logger.debug(f"Applied header and ensured columns: {header}")

    # --- 步骤 3: 对 'Match' 列应用“行展开”逻辑 ---

    # 现在我们可以通过列名 'Match' 来安全地操作
    df['Match'] = df['Match'].astype(str).fillna('')

    if df['Match'].str.contains(r'\|', regex=True).any():
        logger.debug(f"Found '|' in 'Match' column. Proceeding with row expansion.")
        df['Match'] = df['Match'].str.split('|')
        df = df.explode('Match', ignore_index=True)
        # 清理可能产生的空字符串或None旁边的空格
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        logger.info(f"Successfully expanded rows based on '|' delimiter for '{os.path.basename(file_path)}'.")

    return df


def convert_files_to_sqlite(
        input_folder_path: str,
        output_db_path: str,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    """
    递归地将一个目录及其所有子目录下的支持文件，转换为一个单一的SQLite数据库。

    功能特性:
    - 遍历子目录: 自动扫描所有子文件夹。
    - 版本化表名: 每个子目录名被视为一个 'version_id'，并作为其下所有文件
                  在数据库中对应表名的前缀 (例如 'HAU_v1_annotations')。
    - 多格式支持: 支持 .xlsx, .txt, .csv 等以及它们的 .gz 压缩版本。
    - 幂等性: 使用 'replace' 模式，重复运行会覆盖旧表，确保数据最新。

    Args:
        input_folder_path (str): 包含数据文件的根目录路径。
        output_db_path (str): 输出的SQLite数据库文件路径 (例如 'genomes/genomes.db')。
        cancel_event (Optional[threading.Event]): 用于中途取消操作的线程事件。

    Returns:
        bool: 如果所有操作成功完成，返回 True，否则返回 False。
    """
    logger.info(f"Starting recursive conversion from '{input_folder_path}' to SQLite DB '{output_db_path}'")

    if cancel_event and cancel_event.is_set():
        logger.info("Conversion cancelled before starting.")
        return False

    if not os.path.isdir(input_folder_path):
        logger.error(f"Input path is not a valid directory: {input_folder_path}")
        return False

    conn = None  # 在try块外初始化连接变量
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_db_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        conn = sqlite3.connect(output_db_path)
        supported_extensions = ('.xlsx', '.xlsx.gz', '.txt', '.txt.gz', '.csv', '.csv.gz')

        files_processed_count = 0

        # 使用 os.walk 递归地遍历所有子目录和文件
        for root, dirs, files in os.walk(input_folder_path):
            if cancel_event and cancel_event.is_set():
                logger.info("Conversion cancelled during directory traversal.")
                break

            for filename in files:
                if not filename.lower().endswith(supported_extensions):
                    continue

                # 从文件路径中提取 version_id (即相对于根输入目录的子目录名)
                relative_path = os.path.relpath(root, input_folder_path)
                version_id = relative_path if relative_path != '.' else None

                # 根据文件名和version_id生成带有版本前缀的表名
                table_name = _sanitize_table_name(filename, version_id=version_id)
                full_path = os.path.join(root, filename)

                dataframe = None
                logger.debug(f"Processing file '{full_path}' for table '{table_name}'...")

                # 根据文件类型选择合适的读取函数
                if filename.lower().endswith(('.xlsx', '.xlsx.gz')):
                    dataframe = _read_excel_to_dataframe(full_path)
                else:  # .txt, .csv, and their .gz versions
                    dataframe = _read_text_to_dataframe(full_path)

                # 如果成功读取到数据，则写入数据库
                if dataframe is not None and not dataframe.empty:
                    try:
                        # 使用 'replace' 模式，如果表已存在，则替换它
                        dataframe.to_sql(table_name, conn, if_exists='replace', index=False)
                        logger.info(
                            f"Successfully converted '{filename}' (version: {version_id or 'root'}) to table '{table_name}'.")
                        files_processed_count += 1
                    except Exception as e:
                        logger.error(
                            f"Error writing DataFrame from '{filename}' to SQLite table '{table_name}'. Reason: {e}")
                else:
                    logger.warning(f"Skipping file '{filename}' as no valid data could be read.")

        logger.info(f"Successfully processed {files_processed_count} files.")
        logger.info(f"Successfully completed conversion to SQLite database: {output_db_path}")
        return True

    except Exception as e:
        logger.exception(f"A critical error occurred during the conversion process. Reason: {e}")
        return False
    finally:
        # 确保数据库连接在任何情况下都会被关闭
        if conn:
            conn.close()
            logger.debug("Database connection closed.")


