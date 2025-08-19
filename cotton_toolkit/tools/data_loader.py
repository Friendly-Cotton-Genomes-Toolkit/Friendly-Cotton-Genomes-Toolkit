# cotton_toolkit/tools/data_loader.py
import gzip
import io
import sqlite3
import threading

import pandas as pd
import os
from typing import Optional, Callable
import logging

from cotton_toolkit.config.models import MainConfig
from cotton_toolkit import PREPROCESSED_DB_NAME
from cotton_toolkit.core.convertXlsx2csv import _find_header_row
from cotton_toolkit.utils.file_utils import _sanitize_table_name

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 修改: 创建 logger 实例
logger = logging.getLogger("cotton_toolkit.tools.data_loader")


def load_annotation_data(
        file_path: str
) -> Optional[pd.DataFrame]:
    """
    【简化版】加载一个标准化的注释CSV文件。
    此函数假定输入的CSV文件第一行是表头。
    """
    if not os.path.exists(file_path):
        # 修改: 使用 logger.error
        logger.error(_("Annotation file not found at: {}").format(file_path))
        return None

    try:
        df = pd.read_csv(file_path, header=0, sep=',')

        if df.empty:
            # 修改: 使用 logger.warning
            logger.warning(_("Annotation file '{}' is empty.").format(os.path.basename(file_path)))
            return None

        df.dropna(subset=['GeneID', 'TermID'], inplace=True)
        df['GeneID'] = df['GeneID'].astype(str)
        df['TermID'] = df['TermID'].astype(str)

        if 'Description' not in df.columns:
            df['Description'] = df['TermID']
        if 'Namespace' not in df.columns:
            df['Namespace'] = 'KEGG' if 'ko' in df['TermID'].iloc[0] else 'unknown'

        return df

    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Failed to load and process standardized file {}. Reason: {}").format(file_path, e))
        return None


def create_homology_df(
        config: MainConfig,
        file_path: str,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
) -> pd.DataFrame:
    """
    智能加载同源数据到Pandas DataFrame。

    该函数实现了两级加载策略以提高性能和鲁棒性：
    1.  **快速路径 (首选)**: 尝试从一个预处理好的、集中的SQLite数据库中加载数据。
        这个数据库路径被硬编码为 `genomes/genomes.db`。
    2.  **回退路径 (兼容)**: 如果从数据库加载失败（例如，数据库不存在、表不存在或发生任何错误），
        它会自动切换回原始的、较慢的文件解析模式，直接读取并解析 .xlsx, .txt, .gz 等原始文件。

    Args:
        config (MainConfig): 主配置对象，用于定位项目的根目录。
        file_path (str): 原始同源数据文件的路径 (例如 '.../data/Garb_homology_ath.txt.gz')。
        progress_callback (Optional[Callable]): 用于更新进度的回调函数。
        cancel_event (Optional[threading.Event]): 用于中途取消操作的线程事件。

    Returns:
        pd.DataFrame: 加载了同源数据的DataFrame，如果取消或失败则返回空的DataFrame。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    # --- 快速路径：优先尝试从SQLite数据库读取 ---
    try:
        # 1. 根据config文件的位置动态确定项目根目录，并构建数据库的绝对路径
        project_root = os.path.dirname(config.config_file_abs_path_)
        db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)

        # 2. 根据输入的文件名，生成对应的数据库表名
        version_id = os.path.basename(os.path.dirname(file_path))
        table_name = _sanitize_table_name(os.path.basename(file_path), version_id=version_id)

        # 3. 检查数据库文件是否存在，不存在则直接触发回退
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"SQLite database not found at {db_path}")

        logger.info(f"正在尝试从SQLite数据库 '{PREPROCESSED_DB_NAME}' 的表 '{table_name}' 中快速加载...")
        progress(10, "正在连接到预处理数据库...")
        if cancel_event and cancel_event.is_set(): return pd.DataFrame()

        # 4. 连接数据库并执行查询
        with sqlite3.connect(db_path) as conn:
            # 检查表是否存在，避免因表不存在而报错
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cursor.fetchone() is None:
                raise ValueError(f"Table '{table_name}' not found in the database.")

            # 使用pandas直接从SQL查询结果创建DataFrame
            progress(50, f"正在从表 '{table_name}' 读取数据...")
            df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)
            progress(100, "从数据库加载成功。")
            logger.info("成功从SQLite数据库加载数据。")
            return df

    except Exception as e:
        # 如果在上述任何步骤中出现异常，记录警告并准备执行回退逻辑
        logger.warning(f"无法从SQLite数据库加载 ({e})。将回退到直接解析原始文件: {os.path.basename(file_path)}")

    # --- 回退路径：直接解析原始文件 (兼容旧模式) ---
    progress(0, f"回退模式：正在打开文件: {os.path.basename(file_path)}...")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"同源文件未找到: {file_path}")

    lowered_path = file_path.lower()
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']

    with open(file_path, 'rb') as f_raw:
        is_gz = lowered_path.endswith('.gz')
        # 根据是否为 .gz 文件选择不同的打开方式
        file_obj = gzip.open(f_raw, 'rb') if is_gz else f_raw
        try:
            if cancel_event and cancel_event.is_set(): return pd.DataFrame()

            # 判断是Excel文件还是文本文件
            progress(20, "正在解析文件结构...")
            if lowered_path.endswith(('.xlsx', '.xlsx.gz', '.xls', '.xls.gz')):
                # --- Excel文件处理逻辑 ---
                xls = pd.ExcelFile(file_obj)
                all_sheets_data = []
                num_sheets = len(xls.sheet_names)
                for i, sheet_name in enumerate(xls.sheet_names):
                    if cancel_event and cancel_event.is_set():
                        logger.info("在处理Excel工作表时请求取消。")
                        return pd.DataFrame()

                    progress(20 + int(60 * (i / num_sheets)), f"正在处理工作表: {sheet_name}...")
                    preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
                    header_row_index = _find_header_row(preview_df, header_keywords)

                    if header_row_index is not None:
                        sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                        sheet_df.dropna(how='all', inplace=True)
                        all_sheets_data.append(sheet_df)

                if not all_sheets_data:
                    raise ValueError("在Excel文件的任何工作表中都未能找到有效的表头或数据。")

                if cancel_event and cancel_event.is_set(): return pd.DataFrame()
                progress(80, "正在合并所有工作表...")
                return pd.concat(all_sheets_data, ignore_index=True)
            else:
                # --- 文本文件 (txt, tsv等) 处理逻辑 ---
                if cancel_event and cancel_event.is_set(): return pd.DataFrame()
                progress(50, "正在读取文本数据...")
                # 使用io.TextIOWrapper确保正确处理编码，sep=r'\s+'可以匹配一个或多个空白字符（包括空格和制表符）
                return pd.read_csv(io.TextIOWrapper(file_obj, encoding='utf-8', errors='ignore'), sep=r'\s+',
                                   engine='python', comment='#')
        except Exception as e:
            logger.error(f"读取同源文件 '{file_path}' 时出错: {e}")
            raise
        finally:
            progress(100, "文件加载完成。")
            if is_gz and hasattr(file_obj, 'close'):
                file_obj.close()
