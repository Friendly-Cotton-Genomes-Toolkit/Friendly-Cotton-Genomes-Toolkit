# cotton_toolkit/tools/annotator.py
import gzip
import io
import logging
import os
import pandas as pd
from typing import List, Dict, Optional, Callable

from ..config.models import MainConfig, GenomeSourceItem
from ..config.loader import get_local_downloaded_file_path
from ..utils.file_utils import smart_load_file

logger = logging.getLogger("cotton_toolkit.annotator")
_ = lambda text: text  # Placeholder for i18n


class Annotator:
    """
    一个用于处理基因功能注释的类。
    """

    def __init__(
            self,
            main_config: MainConfig,
            genome_info: GenomeSourceItem,
            status_callback: Optional[Callable[[str, str], None]] = None,
            progress_callback: Optional[Callable[[int, str], None]] = None,
            custom_db_dir: Optional[str] = None
    ):
        """
        初始化注释器。

        Args:
            main_config (MainConfig): 主配置对象。
            genome_info (GenomeSourceItem): 当前要注释的基因组的配置信息。
            status_callback (Callable): 用于报告状态更新的回调函数。
            progress_callback (Callable): 用于报告进度的回调函数。
        """
        self.config = main_config
        self.genome_info = genome_info
        self.log = status_callback if status_callback else lambda msg, level: logger.info(f"[{level}] {msg}")
        self.progress = progress_callback if progress_callback else lambda p, m: logger.info(f"[{p}%] {m}")
        self.db_cache: Dict[str, pd.DataFrame] = {}

        # --- 保存自定义目录路径 ---
        self.custom_db_dir = custom_db_dir
        if self.custom_db_dir:
            self.log(f"INFO: 将优先使用自定义注释数据库目录: {self.custom_db_dir}")

    def _load_annotation_db(self, db_key: str) -> Optional[pd.DataFrame]:
        """
        【已升级】加载指定的注释数据库文件。
        优先加载预处理后的 .csv 文件，如果不存在则尝试加载原始下载文件。
        """
        if db_key in self.db_cache:
            self.log(f"DEBUG: 从缓存加载 {db_key} 数据库。", "DEBUG")
            return self.db_cache[db_key]

        # 1. 首先获取原始下载文件的路径
        original_path = get_local_downloaded_file_path(self.config, self.genome_info, db_key)

        if not original_path:
            self.log(f"警告: 在配置中未找到 {db_key} 的下载信息。", "WARNING")
            return None

        # 2. 推断出预处理后的CSV文件路径
        processed_csv_path = os.path.splitext(original_path)[0] + '.csv'

        path_to_load = None
        # --- 核心逻辑：优先使用CSV ---
        if os.path.exists(processed_csv_path):
            self.log(f"INFO: 找到预处理的CSV文件，将使用它: {os.path.basename(processed_csv_path)}", "INFO")
            path_to_load = processed_csv_path
        elif os.path.exists(original_path):
            self.log(f"WARNING: 未找到预处理的CSV文件，将尝试读取原始下载文件: {os.path.basename(original_path)}",
                     "WARNING")
            path_to_load = original_path
        else:
            self.log(f"警告: 原始文件和预处理文件都未找到: {os.path.basename(original_path)}", "WARNING")
            return None

        # 使用强大的 smart_load_file 函数来读取（它能处理多种格式）
        df = smart_load_file(path_to_load, logger_func=self.log)

        if df is not None:
            self.db_cache[db_key] = df
            self.log(f"DEBUG: {db_key} 数据库加载成功。", "DEBUG")
            return df
        else:
            self.log(f"ERROR: 无法加载文件 {path_to_load}。", "ERROR")
            return None

    # annotate_genes 方法保持不变，因为它现在可以正确工作了
    def annotate_genes(self, gene_ids: List[str], annotation_types: List[str]) -> pd.DataFrame:
        """
        对给定的基因列表执行功能注释。
        """
        if not gene_ids:
            return pd.DataFrame()

        final_df = pd.DataFrame(gene_ids, columns=['Gene_ID']).set_index('Gene_ID')

        key_map = {
            'go': 'GO',
            'ipr': 'IPR',
            'kegg_orthologs': 'KEGG_orthologs',
            'kegg_pathways': 'KEGG_pathways'
        }

        total_steps = len(annotation_types)
        for i, anno_type in enumerate(annotation_types):
            self.progress(int((i / total_steps) * 100), _("正在处理 {} 注释...").format(anno_type))

            db_key = key_map.get(anno_type.lower())
            if not db_key:
                self.log(f"警告：未知的注释类型 '{anno_type}'，已跳过。", "WARNING")
                continue

            anno_df = self._load_annotation_db(db_key)
            if anno_df is None:
                continue

            anno_cols = self.config.annotation_tool.database_columns
            query_col = anno_cols.get('query', 'Query')
            match_col = anno_cols.get('match', 'Match')
            desc_col = anno_cols.get('description', 'Description')

            if query_col not in anno_df.columns:
                self.log(f"错误: 在 {anno_type} 注释文件中找不到查询列 '{query_col}'", "ERROR")
                continue

            matched_rows = anno_df[anno_df[query_col].isin(gene_ids)].copy()

            if matched_rows.empty:
                continue

            def aggregate_annotations(series):
                return "; ".join(series.dropna().astype(str).unique())

            agg_dict = {}
            if match_col in matched_rows.columns:
                agg_dict[match_col] = aggregate_annotations
            if desc_col in matched_rows.columns:
                agg_dict[desc_col] = aggregate_annotations

            if not agg_dict:
                self.log(f"警告：在 {anno_type} 文件中找不到匹配或描述列。", "WARNING")
                continue

            grouped = matched_rows.groupby(query_col).agg(agg_dict).reset_index()
            grouped = grouped.rename(columns={
                query_col: 'Gene_ID',
                match_col: f'{anno_type}_ID',
                desc_col: f'{anno_type}_Description'
            }).set_index('Gene_ID')

            final_df = final_df.join(grouped, how='left')

        self.progress(100, _("所有注释处理完成。"))
        return final_df.reset_index()


def load_go_annotations(gaf_path: str, logger_func: Callable = print) -> pd.DataFrame:
    """
    从 GAF (或类似格式的 Excel/CSV) 文件中加载 GO 注释数据。

    这个新版本能够智能处理包含表头的文件，并能适应不同列数的文件，
    只要前两列是基因ID和GO ID即可。

    Args:
        gaf_path (str): GO 注释文件的路径 (可以是 .gz 压缩的)。
        logger_func (Callable): 用于记录日志的回调函数。

    Returns:
        pd.DataFrame: 包含 'GeneID' 和 'GO_ID' 列的 DataFrame。
                      如果文件有第三、四列，也会被保留。
    """
    logger_func(f"INFO: 正在从 {os.path.basename(gaf_path)} 加载GO注释数据...")
    logger_func(f"INFO: Loading annotation file: {gaf_path}")

    try:
        if gaf_path.endswith('.gz'):
            with gzip.open(gaf_path, 'rb') as f:
                content = f.read()
        else:
            with open(gaf_path, 'rb') as f:
                content = f.read()

        file_extension = os.path.splitext(gaf_path.replace('.gz', ''))[1]

        # --- 这是修改的核心 ---
        # 1. 自动读取表头 (header=0)
        # 2. 安全地重命名列
        if file_extension in ['.xlsx', '.xls']:
            df = pd.read_excel(io.BytesIO(content), header=0, engine='openpyxl')
        elif file_extension == '.csv':
            df = pd.read_csv(io.BytesIO(content), header=0)
        elif file_extension == '.txt':
            df = pd.read_csv(io.BytesIO(content), header=0, sep='\t')
        else:
            logger_func(f"ERROR: 不支持的文件格式: {file_extension}")
            raise ValueError(f"Unsupported file format: {file_extension}")

        # 获取原始列名
        original_columns = df.columns.tolist()

        # 定义程序内部需要的核心列名映射关系
        # 我们只关心前两列：基因ID 和 GO ID
        rename_map = {
            original_columns[0]: 'GeneID',
            original_columns[1]: 'GO_ID'
        }

        # 为了兼容性，如果存在第三列和第四列，也给它们一个标准名字
        if len(original_columns) > 2:
            rename_map[original_columns[2]] = 'GO_Term'
        if len(original_columns) > 3:
            # 兼容带有 Namespace 的文件
            rename_map[original_columns[3]] = 'Namespace'

        df.rename(columns=rename_map, inplace=True)
        # --- 修改结束 ---

        # 数据清洗：去除任何可能存在的空值行
        df.dropna(subset=['GeneID', 'GO_ID'], inplace=True)
        df = df.astype({'GeneID': str, 'GO_ID': str})

        logger_func(f"SUCCESS: Loaded and processed {len(df)} annotation entries.")
        return df[['GeneID', 'GO_ID'] + [col for col in ['GO_Term', 'Namespace'] if col in df.columns]]

    except Exception as e:
        logger_func(f"ERROR: 解析GO注释文件时出错: {e}", "ERROR")
        # 在GUI中显示更详细的错误
        raise RuntimeError(f"Failed to parse GO annotation file '{os.path.basename(gaf_path)}'. Reason: {e}") from e
