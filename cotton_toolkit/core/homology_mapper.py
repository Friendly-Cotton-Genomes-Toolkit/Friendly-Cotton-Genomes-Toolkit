import logging
import os

import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Callable

from .gff_parser import _apply_regex_to_id
from ..config.models import GenomeSourceItem  # 确保导入了 GenomeSourceItem
from ..utils.gene_utils import parse_gene_id  # 确保导入了 parse_gene_id

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.homology_mapper")


def select_best_homologs(
        homology_df: pd.DataFrame,
        query_gene_id_col: str,
        match_gene_id_col: str,
        criteria: Dict[str, Any]
) -> pd.DataFrame:
    if homology_df.empty:
        return pd.DataFrame(columns=homology_df.columns)

    filtered_df = homology_df.copy()

    evalue_col = criteria.get('evalue', 'Exp')
    pid_col = criteria.get('pid', 'PID')
    score_col = criteria.get('score', 'Score')

    if "evalue_threshold" in criteria and evalue_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[evalue_col], errors='coerce').fillna(1.0) <= criteria["evalue_threshold"]]
    if "pid_threshold" in criteria and pid_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[pid_col], errors='coerce').fillna(0) >= criteria["pid_threshold"]]
    if "score_threshold" in criteria and score_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[score_col], errors='coerce').fillna(0) >= criteria["score_threshold"]]

    if filtered_df.empty:
        return pd.DataFrame(columns=homology_df.columns)

    sort_by_metrics = criteria.get("sort_by", ["Score"])
    sort_by_cols = [criteria.get(col.lower(), col) for col in sort_by_metrics]
    ascending_flags = criteria.get("ascending", [False])

    sorted_df = filtered_df.sort_values(by=sort_by_cols, ascending=ascending_flags)

    top_n_val = criteria.get("top_n")
    if top_n_val is not None and top_n_val > 0:
        return sorted_df.groupby(query_gene_id_col).head(top_n_val).reset_index(drop=True)

    return sorted_df.reset_index(drop=True)


def load_and_map_homology(
        homology_df: pd.DataFrame,
        homology_columns: Dict[str, str],
        selection_criteria: Dict[str, Any],
        query_gene_ids: Optional[List[str]] = None,
        query_id_regex: Optional[str] = None,
        match_id_regex: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    query_col = homology_columns.get('query')
    match_col = homology_columns.get('match')

    if query_col not in homology_df.columns:
        raise ValueError(
            _("配置错误: 在同源文件中找不到查询列 '{}'。可用列: {}").format(query_col, list(homology_df.columns)))
    if match_col not in homology_df.columns:
        raise ValueError(
            _("配置错误: 在同源文件中找不到匹配列 '{}'。可用列: {}").format(match_col, list(homology_df.columns)))

    df_copy = homology_df.copy()
    df_copy[query_col] = df_copy[query_col].astype(str).apply(lambda x: _apply_regex_to_id(x, query_id_regex))
    df_copy[match_col] = df_copy[match_col].astype(str).apply(lambda x: _apply_regex_to_id(x, match_id_regex))

    filtered_df = df_copy
    if query_gene_ids:
        processed_query_ids = {_apply_regex_to_id(gid, query_id_regex) for gid in query_gene_ids}
        filtered_df = df_copy[df_copy[query_col].isin(processed_query_ids)]

    if filtered_df.empty:
        return {}

    criteria = {**selection_criteria, **homology_columns}
    best_hits_df = select_best_homologs(filtered_df, query_col, match_col, criteria)

    homology_map: Dict[str, List[Dict[str, Any]]] = {}
    for _A, row in best_hits_df.iterrows():
        query_id = row[query_col]
        homology_map.setdefault(query_id, []).append(row.to_dict())

    return homology_map


# 新增 create_homology_df 函数，以匹配 pipelines.py 中的调用
def create_homology_df(file_path: str) -> pd.DataFrame:
    """
    从 CSV 或 Excel 文件加载同源数据到 DataFrame。
    这个函数是为了满足 pipelines.py 中对 create_homology_df 的调用而添加的。
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(_("同源文件未找到: {}").format(file_path))

    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path)
    elif file_path.lower().endswith((".xlsx", ".xls")):
        # 如果是Excel，用pandas读取
        return pd.read_excel(file_path, engine='openpyxl')
    else:
        raise ValueError(_("不支持的同源文件格式: {}").format(os.path.basename(file_path)))


def map_genes_via_bridge(
        source_gene_ids: List[str],
        source_assembly_name: str,
        target_assembly_name: str,
        bridge_species_name: str,
        source_to_bridge_homology_df: pd.DataFrame,
        bridge_to_target_homology_df: pd.DataFrame,
        selection_criteria_s_to_b: Dict[str, Any],
        selection_criteria_b_to_t: Dict[str, Any],
        homology_columns: Dict[str, str],
        source_genome_info: GenomeSourceItem,
        target_genome_info: GenomeSourceItem,
        status_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable] = None,
        **kwargs
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """
    通过桥梁物种进行同源基因映射，并根据 strict_subgenome_priority 开关执行筛选。
    返回一个包含(DataFrame, failed_genes_list)的元组。
    """
    log = status_callback if status_callback else lambda msg, level="INFO": logger.info(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: None
    base_progress = 50  # 这个函数内的进度从50%开始
    progress_range = 45  # 这个函数内的进度范围为45% (从50%到95%)

    bridge_genome_info = kwargs.get('bridge_genome_info')
    bridge_id_regex = kwargs.get('bridge_id_regex')
    if not bridge_id_regex and bridge_genome_info and hasattr(bridge_genome_info,
                                                              'gene_id_regex') and bridge_genome_info.gene_id_regex:
        bridge_id_regex = bridge_genome_info.gene_id_regex
    if not bridge_id_regex:
        bridge_id_regex = r'(AT[1-5MC]G\d{5})'

    user_top_n = selection_criteria_s_to_b.get('top_n', 1)

    # 获取所有可能的同源关系 (top_n=0)
    temp_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 0}
    temp_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 0}

    progress(base_progress + 5, _("正在映射: 源 -> 桥梁..."))
    s2b_map = load_and_map_homology(source_to_bridge_homology_df, homology_columns, temp_s2b_criteria, source_gene_ids,
                                    source_genome_info.gene_id_regex, bridge_id_regex)
    if not s2b_map:
        return pd.DataFrame(), source_gene_ids

    s2b_hits_df = pd.DataFrame([match for matches in s2b_map.values() for match in matches])
    bridge_gene_ids = s2b_hits_df[homology_columns.get('match')].unique().tolist()

    progress(base_progress + 15, _("正在映射: 桥梁 -> 目标..."))
    b2t_homology_cols = {'query': homology_columns.get('match'), 'match': homology_columns.get('query'),
                         **{k: v for k, v in homology_columns.items() if k not in ['query', 'match']}}
    b2t_map = load_and_map_homology(bridge_to_target_homology_df, b2t_homology_cols, temp_b2t_criteria, bridge_gene_ids,
                                    bridge_id_regex, target_genome_info.gene_id_regex)
    if not b2t_map:
        return pd.DataFrame(), source_gene_ids

    b2t_hits_df = pd.DataFrame([match for matches in b2t_map.values() for match in matches])

    progress(base_progress + 25, _("正在合并映射结果..."))
    df1 = s2b_hits_df.rename(
        columns={homology_columns.get('query'): "Source_Gene_ID", homology_columns.get('match'): "Bridge_Gene_ID"})
    df2 = b2t_hits_df.rename(
        columns={b2t_homology_cols.get('query'): "Bridge_Gene_ID", b2t_homology_cols.get('match'): "Target_Gene_ID"})
    merged_df = pd.merge(df1, df2, on="Bridge_Gene_ID", how="inner", suffixes=('_s2b', '_b2t'))
    if merged_df.empty:
        return pd.DataFrame(), source_gene_ids

    # --- 步骤 3: 根据模式进行筛选和排序 ---
    progress(base_progress + 35, _("正在根据模式筛选和排序..."))
    is_cotton_to_cotton = source_genome_info.is_cotton() and target_genome_info.is_cotton()
    # 使用新的开关，并默认开启
    strict_mode = selection_criteria_s_to_b.get('strict_subgenome_priority', True)

    score_col_name = homology_columns.get('score', 'Score')
    score_s2b_col = f"{score_col_name}_s2b"
    score_b2t_col = f"{score_col_name}_b2t"
    if score_s2b_col not in merged_df.columns: merged_df[score_s2b_col] = 0
    if score_b2t_col not in merged_df.columns: merged_df[score_b2t_col] = 0

    secondary_sort_cols = [score_s2b_col, score_b2t_col]
    ascending_flags = [False, False]

    if strict_mode and is_cotton_to_cotton:
        log(_("已启用严格模式：仅保留同亚组、同染色体编号的匹配。"), "INFO")

        merged_df['Source_Parsed'] = merged_df['Source_Gene_ID'].apply(parse_gene_id)
        merged_df['Target_Parsed'] = merged_df['Target_Gene_ID'].apply(parse_gene_id)

        # 定义严格匹配条件
        condition = (
                (merged_df['Source_Parsed'].notna()) &
                (merged_df['Target_Parsed'].notna()) &
                (merged_df['Source_Parsed'].str[0] == merged_df['Target_Parsed'].str[0]) &  # 亚组相同
                (merged_df['Source_Parsed'].str[1] == merged_df['Target_Parsed'].str[1])  # 染色体编号相同
        )
        # 直接用此条件筛选DataFrame
        sorted_df = merged_df[condition].sort_values(by=secondary_sort_cols, ascending=ascending_flags)
    else:
        # 关闭严格模式时，执行常规的、基于分数的排序
        log(_("严格模式已关闭，使用常规双分数排序规则。"), "INFO")
        sorted_df = merged_df.sort_values(by=secondary_sort_cols, ascending=ascending_flags)

    # --- 步骤 4: 应用Top N并找出匹配失败的基因 ---
    progress(base_progress + 40, _("正在筛选 Top N 结果..."))
    final_df = sorted_df
    if user_top_n is not None and user_top_n > 0:
        final_df = sorted_df.groupby('Source_Gene_ID', sort=False).head(user_top_n)

    successfully_mapped_genes = set(final_df['Source_Gene_ID'].unique())
    failed_genes = [gid for gid in source_gene_ids if gid not in successfully_mapped_genes]
    if failed_genes:
        log(_("信息: {} 个源基因未能找到符合条件的同源匹配。").format(len(failed_genes)), "INFO")

    # 清理辅助列并返回
    final_df = final_df.drop(columns=['Source_Parsed', 'Target_Parsed'], errors='ignore')
    final_df = final_df.reset_index(drop=True)

    return final_df, failed_genes
