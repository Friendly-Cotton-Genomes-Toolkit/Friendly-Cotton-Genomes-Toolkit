# cotton_toolkit/tools/annotator.py

import logging
import os
import sqlite3
import pandas as pd
from typing import List, Dict, Optional, Callable

from .. import PREPROCESSED_DB_NAME
from ..config.models import MainConfig, GenomeSourceItem
from ..config.loader import get_local_downloaded_file_path
from ..utils.file_utils import smart_load_file, _sanitize_table_name

logger = logging.getLogger("cotton_toolkit.tools.annotator")


try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class Annotator:
    """
    【最终稳定版】一个用于处理基因功能注释的类。
    - 强制读取预处理后的CSV文件，不再回退读取原始Excel。
    - 使用基因组专属的正则表达式进行精确匹配。
    """

    def __init__(
            self,
            main_config: MainConfig,
            genome_id: str,
            genome_info: GenomeSourceItem,
            progress_callback: Optional[Callable[[int, str], None]] = None,
            **kwargs # 接受额外参数以保持接口兼容
    ):
        self.config = main_config
        self.genome_id = genome_id
        self.genome_info = genome_info
        self.progress = progress_callback if progress_callback else lambda p, m: logger.info(f"[{p}%] {m}")

        project_root = os.path.dirname(self.config.config_file_abs_path_)
        self.db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)

        if not os.path.exists(self.db_path):
            raise FileNotFoundError(_("预处理数据库未找到: {}。请先运行统一预处理脚本。").format(self.db_path))
    def _load_annotation_db(self, db_key: str) -> Optional[pd.DataFrame]:
        """
        只加载预处理后的 .csv 注释文件，并强制重命名表头。
        """
        if db_key in self.db_cache:
            return self.db_cache[db_key]

        original_path = get_local_downloaded_file_path(self.config, self.genome_info, db_key)
        if not original_path:
            logger.warning(_("警告: 在配置中未找到 {} 的下载信息。").format(db_key))
            return None

        if original_path.endswith('.xlsx.gz'):
            base_path = original_path.replace('.xlsx.gz', '')
        elif original_path.endswith('.txt.gz'):
            base_path = original_path.replace('.txt.gz', '')
        else:
            logger.error(_('未知的文件类型: {}').format(original_path))
            return None

        processed_csv_path = base_path + '.csv'

        if not os.path.exists(processed_csv_path):
            logger.error(_("未找到预处理好的注释文件 '{}'。").format(os.path.basename(processed_csv_path)))
            logger.error(_("请先运行 '数据下载' -> '预处理注释文件' 功能来生成它。"))
            return None

        logger.info(_("正在加载预处理的注释文件: {}").format(os.path.basename(processed_csv_path)))
        # 修改: smart_load_file 内部使用统一logger，因此无需传递 logger_func
        df = smart_load_file(processed_csv_path)

        if df is not None and not df.empty:
            logger.debug(_("从CSV加载的原始列名: {}").format(df.columns.tolist()))
            rename_map = {}
            if len(df.columns) > 0: rename_map[df.columns[0]] = 'Query'
            if len(df.columns) > 1: rename_map[df.columns[1]] = 'Match'
            if len(df.columns) > 2: rename_map[df.columns[2]] = 'Description'
            df.rename(columns=rename_map, inplace=True)
            logger.debug(_("强制重命名后的列名: {}").format(df.columns.tolist()))

            self.db_cache[db_key] = df
            return df
        else:
            logger.error(_("无法加载文件或文件为空: {}。").format(processed_csv_path))
            return None

    def annotate_genes(self, gene_ids: List[str], annotation_types: List[str]) -> pd.DataFrame:
        """
        为基因列表批量添加功能注释。
        """
        if not gene_ids:
            return pd.DataFrame()

        # 准备一个基础的DataFrame用于合并所有结果
        # 使用 set 去重以提高效率
        unique_gene_ids = sorted(list(set(gene_ids)))
        final_df = pd.DataFrame({'Gene_ID': unique_gene_ids})

        # 定义注释类型到文件关键字的映射
        key_map = {'go': 'GO', 'ipr': 'IPR', 'kegg_orthologs': 'KEGG_orthologs', 'kegg_pathways': 'KEGG_pathways'}

        with sqlite3.connect(self.db_path) as conn:
            for i, anno_type in enumerate(annotation_types):
                self.progress(int((i / len(annotation_types)) * 100) if annotation_types else 0,
                              _("正在处理 {} 注释...").format(anno_type))

                db_key = key_map.get(anno_type.lower())
                if not db_key:
                    logger.warning(_("不支持的注释类型: '{}'，已跳过。").format(anno_type))
                    continue

                # 1. 根据配置动态推断表名
                url = getattr(self.genome_info, f"{db_key}_url", None)
                if not url:
                    logger.warning(
                        _("基因组 '{}' 的配置中未找到 '{}' 的URL，无法推断表名。").format(self.genome_id, db_key))
                    continue
                table_name = _sanitize_table_name(os.path.basename(url), version_id=self.genome_id)

                try:
                    # 2. 从数据库查询
                    placeholders = ','.join('?' for _u in unique_gene_ids)
                    # 假设基因ID列被统一命名为 'Query'
                    query = f'SELECT * FROM "{table_name}" WHERE Query IN ({placeholders})'

                    logger.info(f"正在从表 '{table_name}' 中查询 {len(unique_gene_ids)} 个基因的 '{db_key}' 注释...")
                    anno_df = pd.read_sql_query(query, conn, params=unique_gene_ids)

                    if anno_df.empty:
                        continue

                    # 3. 数据聚合
                    # 将结果按基因ID分组，并将同一基因的多个注释条目合并为一行
                    anno_df = anno_df.rename(columns={'Query': 'Gene_ID'})

                    agg_dict = {}
                    if 'Match' in anno_df.columns:
                        agg_dict[f'{anno_type}_ID'] = pd.NamedAgg(column='Match', aggfunc=lambda s: "; ".join(
                            s.dropna().astype(str).unique()))
                    if 'Description' in anno_df.columns:
                        agg_dict[f'{anno_type}_Description'] = pd.NamedAgg(column='Description',
                                                                           aggfunc=lambda s: "; ".join(
                                                                               s.dropna().astype(str).unique()))

                    if not agg_dict:
                        continue

                    aggregated_annos = anno_df.groupby('Gene_ID').agg(**agg_dict).reset_index()

                    # 4. 合并到最终结果
                    final_df = pd.merge(final_df, aggregated_annos, on='Gene_ID', how='left')

                except (sqlite3.OperationalError, pd.io.sql.DatabaseError) as e:
                    if "no such table" in str(e):
                        logger.error(
                            _("错误: 数据库中未找到表 '{}'。请确保对应的原始文件已通过预处理脚本正确转换。").format(
                                table_name))
                    else:
                        logger.error(_("查询表 '{}' 时发生数据库错误: {}").format(table_name, e))

        final_df.fillna("N/A", inplace=True)
        self.progress(100, _("所有注释处理完成。"))
        return final_df