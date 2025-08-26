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
    一个用于处理基因功能注释的类。
    - 强制读取预处理后的CSV文件，不再回退读取原始Excel。
    - 使用基因组专属的正则表达式进行精确匹配。
    """

    def __init__(
            self,
            main_config: MainConfig,
            genome_id: str,
            genome_info: GenomeSourceItem,
            progress_callback: Optional[Callable[[int, str], None]] = None,
            **kwargs  # 接受额外参数以保持接口兼容
    ):
        """
        初始化Annotator。

        Args:
            main_config: 主配置对象。
            genome_id: 目标基因组的唯一ID (例如 'HAU_v1')。
            genome_info: 目标基因组的详细配置信息对象。
            progress_callback: 用于报告进度的回调函数。

        Raises:
            FileNotFoundError: 如果预处理数据库 (genomes.db) 不存在。
        """
        self.config = main_config
        self.genome_id = genome_id
        self.genome_info = genome_info
        self.progress = progress_callback if progress_callback else lambda p, m: logger.info(f"[{p}%] {m}")

        # 直接定位到预处理数据库的路径
        project_root = os.path.dirname(self.config.config_file_abs_path_)
        self.db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)

        # 在初始化时就检查数据库是否存在，提前失败
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(_("预处理数据库未找到: {}。请先运行数据预处理流程。").format(self.db_path))


    def annotate_genes(self, gene_ids: List[str], annotation_types: List[str]) -> pd.DataFrame:
        """
        为给定的基因ID列表批量添加功能注释。

        此方法直接从SQLite数据库中查询所有请求的注释类型，然后将结果
        聚合到每个基因ID上，并返回一个包含所有注释信息的DataFrame。

        Args:
            gene_ids: 需要查询注释的基因ID列表。
            annotation_types: 一个包含所需注释类型的列表 (例如 ['go', 'ipr', 'kegg_orthologs'])。

        Returns:
            一个Pandas DataFrame，索引为基因ID，列为所请求的各类注释信息。
        """
        if not gene_ids:
            return pd.DataFrame()

        # 使用 set 去重以提高查询效率
        unique_gene_ids = sorted(list(set(gene_ids)))
        final_df = pd.DataFrame({'Gene_ID': unique_gene_ids})

        # 定义注释类型到文件关键字的映射，用于推断数据库中的表名
        key_map = {
            'go': 'GO',
            'ipr': 'IPR',
            'kegg_orthologs': 'KEGG_orthologs',
            'kegg_pathways': 'KEGG_pathways'
        }

        # 使用只读模式连接数据库，更安全
        with sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True) as conn:
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
                    # 2. 从数据库批量查询基因的注释信息
                    placeholders = ','.join('?' for _V in unique_gene_ids)
                    # 假设预处理后的表中，基因ID列统一为 'Query'
                    query = f'SELECT * FROM "{table_name}" WHERE Query IN ({placeholders})'

                    logger.info(f"正在从表 '{table_name}' 中查询 {len(unique_gene_ids)} 个基因的 '{db_key}' 注释...")
                    anno_df = pd.read_sql_query(query, conn, params=unique_gene_ids)

                    if anno_df.empty:
                        logger.warning(_("在表 '{}' 中未找到任何匹配的注释信息。").format(table_name))
                        continue

                    # 3. 数据聚合：将同一基因的多个注释条目合并为一行
                    anno_df = anno_df.rename(columns={'Query': 'Gene_ID'})

                    agg_dict = {}
                    if 'Match' in anno_df.columns:
                        agg_dict[f'{anno_type}_ID'] = pd.NamedAgg(
                            column='Match',
                            aggfunc=lambda s: "; ".join(s.dropna().astype(str).unique())
                        )
                    if 'Description' in anno_df.columns:
                        agg_dict[f'{anno_type}_Description'] = pd.NamedAgg(
                            column='Description',
                            aggfunc=lambda s: "; ".join(s.dropna().astype(str).unique())
                        )

                    if not agg_dict:
                        continue

                    aggregated_annos = anno_df.groupby('Gene_ID').agg(**agg_dict).reset_index()

                    # 4. 将当前注释类型的结果合并到最终的DataFrame中
                    final_df = pd.merge(final_df, aggregated_annos, on='Gene_ID', how='left')

                except (sqlite3.OperationalError, pd.io.sql.DatabaseError) as e:
                    error_msg = ""
                    if "no such table" in str(e):
                        error_msg = _(
                            "错误: 数据库中未找到表 '{}'。请确保对应的原始文件已通过预处理脚本正确转换。").format(
                            table_name)
                    else:
                        error_msg = _("查询表 '{}' 时发生数据库错误: {}").format(table_name, e)

                    logger.error(error_msg)
                    raise sqlite3.Error(error_msg) from e

        # 使用 'N/A' 填充所有未找到注释的单元格
        final_df.fillna("N/A", inplace=True)
        self.progress(100, _("所有注释处理完成。"))
        return final_df