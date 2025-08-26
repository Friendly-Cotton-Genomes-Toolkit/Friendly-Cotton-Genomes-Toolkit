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
from typing import Optional, List, Union, Callable

from cotton_toolkit.config.loader import get_genome_data_sources
from cotton_toolkit.config.models import MainConfig
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


def _check_cancel_in_loop(line_count: int, cancel_event: Optional[threading.Event]):
    """每处理10000行检查一次取消事件，以平衡性能和响应速度。"""
    if line_count % 10000 == 0 and cancel_event and cancel_event.is_set():
        raise InterruptedError("File processing cancelled by user.")


def _read_annotation_text_file(file_path: str, cancel_event: Optional[threading.Event] = None) -> Optional[pd.DataFrame]:
    """
     为GO, KEGG, IPR等注释文本文件设计的解析器。
    - 严格将每一行解析为三列：Query, Match, Description。
    - 将第一个连续的空白块作为列分隔符。
    - 分号(;)不被视为分隔符。
    - 对'Match'列中的'|'进行行展开。
    """
    logger.debug(f"Using dedicated annotation parser for: {os.path.basename(file_path)}")

    processed_data = []
    header = ['Query', 'Match', 'Description']
    line_count = 0

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            for line in f:
                _check_cancel_in_loop(line_count, cancel_event)
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
        error_msg = _("处理注释文件 {} 失败；原因: {}").format(os.path.basename(file_path),e)
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise IOError(error_msg) from e


def _read_fasta_to_dataframe(file_path: str, id_regex: Optional[str] = None, cancel_event: Optional[threading.Event] = None) -> Optional[pd.DataFrame]:
    """
    将FASTA文件解析为DataFrame，并强制使用传入的正则表达式清理ID。
    """
    logger.debug(f"正在为文件: {os.path.basename(file_path)} 使用专用的FASTA解析器 (Regex: {id_regex})")
    fasta_data = []
    line_count = 0

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            current_id = None
            current_sequence = []
            for line in f:
                _check_cancel_in_loop(line_count, cancel_event)
                line = line.strip()
                if not line:
                    continue
                if line.startswith('>'):
                    if current_id:
                        fasta_data.append([current_id, "".join(current_sequence)])

                    header_line = line[1:]  # 移除 '>'
                    # 强制使用传入的正则表达式进行清理和提取
                    if id_regex:
                        match = re.search(id_regex, header_line)
                        if match:
                            current_id = match.group(1) if match.groups() else match.group(0)
                        else:
                            # 如果正则不匹配，作为后备，取第一个空白前的内容
                            current_id = header_line.split()[0]
                            logger.debug(
                                f"Regex failed for header: '{header_line}'. Using fallback ID: '{current_id}'")
                    else:
                        current_id = header_line.split()[0]
                    current_sequence = []
                elif current_id:
                    current_sequence.append(line)
            if current_id:
                fasta_data.append([current_id, "".join(current_sequence)])
        if not fasta_data:
            return None
        df = pd.DataFrame(fasta_data, columns=['Gene', 'Seq'])
        logger.info(_("成功解析FASTA文件 '{}'，共找到 {} 个条目。").format(os.path.basename(file_path),len(df)))
        return df
    except Exception as e:
        error_msg = _("处理FASTA文件 '{}' 失败。原因: {}").format(os.path.basename(file_path),e)
        logger.error(error_msg)
        raise IOError(error_msg) from e

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


def _read_excel_to_dataframe(file_path: str, cancel_event: Optional[threading.Event] = None) -> Optional[pd.DataFrame]:
    """
    智能读取单个Excel文件（xlsx或xlsx.gz），合并所有Sheet页为一个DataFrame。
    """
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']  # 沿用之前的关键词
    logger.debug(f"Reading Excel file: {os.path.basename(file_path)}")

    try:
        open_func = gzip.open if file_path.lower().endswith('.gz') else open
        with open_func(file_path, 'rb') as f:
            if cancel_event and cancel_event.is_set(): raise InterruptedError

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
            return pd.DataFrame()

        combined_df = pd.concat(all_data_frames, ignore_index=True)
        combined_df.dropna(how='all', inplace=True)
        return combined_df

    except Exception as e:
        error_msg = _("处理Excel文件 '{}' 失败。原因: {}").formatg(os.path.basename(file_path),e)
        logger.error(error_msg)
        raise IOError(error_msg) from e


def _read_text_to_dataframe(file_path: str) -> Optional[pd.DataFrame]:
    """
    读取文本文件，兼容多种格式，强制添加三列表头，并处理“|”多值行。
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
        error_msg = _("All parsing methods failed for '{}'. Final error: {}").format(os.path.basename(file_path),e)
        logger.error(error_msg)
        raise IOError(error_msg) from e

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


def process_single_file_to_sqlite(
        file_key: str,
        source_path: str,
        db_path: str,
        version_id: str,
        id_regex: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> bool:
    """
    Worker function to process a single annotation file and write it to a SQLite table.
    Now supports detailed progress reporting.
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError(_("文件处理过程被取消。"))

    table_name = _sanitize_table_name(os.path.basename(source_path), version_id=version_id)
    conn = None

    try:
        progress(0, _("开始处理..."))
        # Step 1: File reading and parsing
        check_cancel()
        progress(10, _("正在读取文件..."))

        dataframe = None
        filename_lower = source_path.lower()

        if file_key in ['predicted_cds', 'predicted_protein']:
            dataframe = _read_fasta_to_dataframe(source_path, id_regex=id_regex)
        elif filename_lower.endswith(('.xlsx', '.xlsx.gz')):
            dataframe = _read_excel_to_dataframe(source_path)
        elif file_key in ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']:
            dataframe = _read_annotation_text_file(source_path)
        else:
            dataframe = _read_text_to_dataframe(source_path)

        check_cancel()

        if dataframe is None or dataframe.empty:
            logger.warning(_("跳过文件 '{}'，因为未能读取到有效数据。").format(os.path.basename(source_path)))
            return False

        progress(50, _("文件读取完毕, 正在清洗ID..."))

        if id_regex and file_key not in ['predicted_cds', 'predicted_protein']:
            target_column = 'Query'
            if target_column in dataframe.columns:
                logger.debug(
                    _("正在对 {} 的 '{}' 列应用正则表达式...").format(os.path.basename(source_path), target_column))
                cleaned_ids = dataframe[target_column].astype(str).str.extract(id_regex).iloc[:, 0]
                dataframe[target_column] = cleaned_ids.fillna(dataframe[target_column])
                logger.info(_("成功清洗了 '{}' 列。").format(target_column))
            else:
                logger.warning(
                    f"文件 {os.path.basename(source_path)} 中未找到预期的 '{target_column}' 列，跳过清洗。")

        # Step 2: Database writing
        progress(75, _("正在写入数据库..."))
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            dataframe.to_sql(table_name, conn, if_exists='replace', index=False)
            conn.close()
            conn = None
        finally:
            if conn:
                conn.close()

        check_cancel()
        logger.info(_("成功将 '{}' 转换到表 '{}'。").format(os.path.basename(source_path), table_name))
        progress(100, _("处理完成"))
        return True

    except InterruptedError:
        logger.warning(_("文件 '{}' 的处理过程被取消。").format(os.path.basename(source_path)))
        progress(100, _("任务已取消"))
        # Cleanup logic for cancelled tasks
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.commit()
            conn.close()
            logger.info(_("成功清理表 '{}'。").format(table_name))
        except Exception as cleanup_e:
            return _("清理表 '{}' 时发生错误: {}").format(table_name, cleanup_e)

    except Exception as e:
        progress(100, _("处理失败"))
        return _("处理文件 '{}' 到表 '{}' 时发生错误。原因: {}").format(os.path.basename(source_path), table_name, e)


def convert_files_to_sqlite(
        config: MainConfig,
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
    - 多格式支持: 支持 .xlsx, .txt, .csv, .fasta, .fa, .fna, .cds 等以及它们的 .gz 压缩版本。
    - 幂等性: 使用 'replace' 模式，重复运行会覆盖旧表，确保数据最新。

    Args:
        input_folder_path (str): 包含数据文件的根目录路径。
        output_db_path (str): 输出的SQLite数据库文件路径 (例如 'genomes/genomes.db')。
        cancel_event (Optional[threading.Event]): 用于中途取消操作的线程事件。

    Returns:
        bool: 如果所有操作成功完成，返回 True，否则返回 False。
    """
    logger.info(f"开始从 '{input_folder_path}' 到 SQLite数据库 '{output_db_path}' 的递归转换")
    if cancel_event and cancel_event.is_set(): return False
    if not os.path.isdir(input_folder_path): return False

    # 新增：提前获取基因组源信息
    genome_sources = get_genome_data_sources(config)

    conn = None
    try:
        output_dir = os.path.dirname(output_db_path)
        if output_dir: os.makedirs(output_dir, exist_ok=True)
        conn = sqlite3.connect(output_db_path)

        supported_extensions = ('.xlsx', '.xlsx.gz', '.txt', '.txt.gz', '.csv', '.csv.gz',
                                '.fasta', '.fasta.gz', '.fa', '.fa.gz', '.fna', '.fna.gz', '.cds', '.cds.gz')
        fasta_extensions = ('.fasta', '.fa', '.fna', '.cds')
        files_processed_count = 0

        for root, dirs, files in os.walk(input_folder_path):
            if cancel_event and cancel_event.is_set(): break
            for filename in files:
                file_lower = filename.lower()
                if not any(file_lower.endswith(ext) for ext in supported_extensions): continue

                relative_path = os.path.relpath(root, input_folder_path)
                version_id = relative_path if relative_path != '.' else None
                table_name = _sanitize_table_name(filename, version_id=version_id)
                full_path = os.path.join(root, filename)
                dataframe = None

                is_fasta = any(file_lower.endswith(ext) or file_lower.endswith(ext + '.gz') for ext in fasta_extensions)

                # 新增：为FASTA文件查找并应用特定的正则表达式
                id_regex_to_use = None
                if is_fasta and version_id:
                    current_genome_info = genome_sources.get(version_id)
                    if current_genome_info and current_genome_info.gene_id_regex:
                        id_regex_to_use = current_genome_info.gene_id_regex
                        logger.debug(f"为版本 '{version_id}' 找到基因ID正则表达式: {id_regex_to_use}")
                    else:
                        logger.warning(f"在配置中未找到版本 '{version_id}' 的基因ID正则表达式。")

                if is_fasta:
                    dataframe = _read_fasta_to_dataframe(full_path, id_regex=id_regex_to_use, cancel_event=cancel_event)
                elif file_lower.endswith(('.xlsx', '.xlsx.gz')):
                    dataframe = _read_excel_to_dataframe(full_path, cancel_event=cancel_event)
                else:
                    if cancel_event and cancel_event.is_set(): continue
                    dataframe = _read_text_to_dataframe(full_path)

                # 在写入数据库这个阻塞操作前，再次检查
                if cancel_event and cancel_event.is_set(): continue

                if dataframe is not None and not dataframe.empty:
                    try:
                        dataframe.to_sql(table_name, conn, if_exists='replace', index=False)
                        logger.info(
                            f"成功将 '{filename}' (版本: {version_id or 'root'}) 转换到表 '{table_name}'。")
                        files_processed_count += 1
                    except Exception as e:
                        logger.error(f"从 '{filename}' 写入SQLite表 '{table_name}' 时出错。原因: {e}")
                else:
                    logger.warning(f"跳过文件 '{filename}'，因为未能读取到有效数据。")

        logger.info(f"成功处理了 {files_processed_count} 个文件。")
        return True
    except Exception as e:
        logger.exception(f"在转换过程中发生严重错误。原因: {e}")
        return False
    finally:
        if conn: conn.close()


