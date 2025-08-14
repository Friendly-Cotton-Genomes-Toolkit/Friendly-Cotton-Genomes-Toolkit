# cotton_toolkit/tools/annotator.py

import logging
import os
import re
import pandas as pd
from typing import List, Dict, Optional, Callable

from ..config.models import MainConfig, GenomeSourceItem
from ..config.loader import get_local_downloaded_file_path
from ..utils.file_utils import smart_load_file

logger = logging.getLogger("cotton_toolkit.annotator")


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

    # __init__ 方法保持不变
    def __init__(
            self,
            main_config: MainConfig,
            genome_id: str,
            genome_info: GenomeSourceItem,
            status_callback: Optional[Callable[[str, str], None]] = None,
            progress_callback: Optional[Callable[[int, str], None]] = None,
            custom_db_dir: Optional[str] = None
    ):
        self.config = main_config
        self.genome_id = genome_id
        self.genome_info = genome_info
        self.log = status_callback if status_callback else lambda msg, level="INFO": logger.info(f"[{level}] {msg}")
        self.progress = progress_callback if progress_callback else lambda p, m: logger.info(f"[{p}%] {m}")
        self.db_cache: Dict[str, pd.DataFrame] = {}
        self.custom_db_dir = custom_db_dir
        if self.custom_db_dir:
            self.log(_("INFO: 将优先使用自定义注释数据库目录: {}").format(self.custom_db_dir))


    # --- 以下函数是本次修改的核心 ---
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

        # 准确地推断出预处理后的CSV文件路径
        if original_path.endswith('.xlsx.gz'):
            base_path = original_path.replace('.xlsx.gz', '')
        elif original_path.endswith('.txt.gz'):
            base_path = original_path.replace('.txt.gz', '')
        else:
            logger.error(_('未知的文件类型: {}').format(original_path))
            return None

        processed_csv_path = base_path + '.csv'

        # 只检查 .csv 文件是否存在
        if not os.path.exists(processed_csv_path):
            logger.error(_("未找到预处理好的注释文件 '{}'。").format(os.path.basename(processed_csv_path)))
            logger.error(_("请先运行 '数据下载' -> '预处理注释文件' 功能来生成它。"))
            return None

        logger.info(_("正在加载预处理的注释文件: {}").format(os.path.basename(processed_csv_path)))
        df = smart_load_file(processed_csv_path, logger_func=self.log)

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

    # annotate_genes 方法保持不变，因为它已经是最终形态
    def annotate_genes(self, gene_ids: List[str], annotation_types: List[str]) -> pd.DataFrame:
        """
        【最终专业版】使用正则表达式提取核心ID，进行精确匹配。
        """
        # ... (此函数的代码与上一轮回复中的完全相同，无需修改) ...
        if not gene_ids:
            return pd.DataFrame()

        regex = self.genome_info.gene_id_regex
        if not regex:
            logger.error(_("基因组 {} 未在配置中定义 'gene_id_regex'。").format(self.genome_id))
            return pd.DataFrame([{'Gene_ID': gid, 'Error': _('No regex defined for genome')} for gid in gene_ids])

        logger.info(_("使用正则表达式进行匹配: {}").format(regex))

        input_id_map = {}
        for original_id in gene_ids:
            match = re.search(regex, original_id, re.IGNORECASE)
            if match:
                core_id = match.group(0).lower()
                if core_id not in input_id_map:
                    input_id_map[core_id] = original_id
            else:
                logger.warning(
                    _("输入的基因ID '{}' 不符合基因组 {} 的格式，将被忽略。").format(original_id, self.genome_id))


        final_results = {original_id: {'Gene_ID': original_id} for original_id in gene_ids}

        for i, anno_type in enumerate(annotation_types):
            self.progress(int((i / len(annotation_types)) * 100) if annotation_types else 0,
                          _("正在处理 {} 注释...").format(anno_type))

            key_map = {'go': 'GO', 'ipr': 'IPR', 'kegg_orthologs': 'KEGG_orthologs', 'kegg_pathways': 'KEGG_pathways'}
            db_key = key_map.get(anno_type.lower())
            if not db_key: continue

            anno_df = self._load_annotation_db(db_key)
            if anno_df is None or anno_df.empty: continue

            anno_df['Core_ID'] = anno_df['Query'].astype(str).str.extract(regex, flags=re.IGNORECASE,
                                                                          expand=False).str.lower()

            matched_df = anno_df.dropna(subset=['Core_ID']).copy()
            matched_df = matched_df[matched_df['Core_ID'].isin(input_id_map.keys())]

            if matched_df.empty: continue

            def aggregate_annotations(series):
                return "; ".join(series.dropna().astype(str).unique())

            agg_functions = {}
            if 'Match' in matched_df.columns: agg_functions[f'{anno_type}_ID'] = ('Match', aggregate_annotations)
            if 'Description' in matched_df.columns: agg_functions[f'{anno_type}_Description'] = ('Description',
                                                                                                 aggregate_annotations)
            if not agg_functions: continue

            grouped_annos = matched_df.groupby('Core_ID').agg(**agg_functions)

            for core_id, original_id in input_id_map.items():
                if core_id in grouped_annos.index:
                    final_results[original_id].update(grouped_annos.loc[core_id].to_dict())

        final_df = pd.DataFrame(list(final_results.values()))
        final_df.fillna("N/A", inplace=True)

        self.progress(100, _("所有注释处理完成。"))
        return final_df