# 文件路径: core/homology_mapper.py

import logging
import os
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Callable

# 确保导入了正确的模块
from ..config.models import GenomeSourceItem
from ..utils.gene_utils import parse_gene_id

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.homology_mapper")


# 保持不变的辅助函数
def select_best_homologs(homology_df: pd.DataFrame, query_gene_id_col: str, match_gene_id_col: str,
                         criteria: Dict[str, Any]) -> pd.DataFrame:
    if homology_df.empty: return pd.DataFrame(columns=homology_df.columns)
    filtered_df = homology_df.copy()
    evalue_col, pid_col, score_col = criteria.get('evalue', 'Exp'), criteria.get('pid', 'PID'), criteria.get('score',
                                                                                                             'Score')
    if "evalue_threshold" in criteria and evalue_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[evalue_col], errors='coerce').fillna(1.0) <= criteria["evalue_threshold"]]
    if "pid_threshold" in criteria and pid_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[pid_col], errors='coerce').fillna(0) >= criteria["pid_threshold"]]
    if "score_threshold" in criteria and score_col in filtered_df.columns:
        filtered_df = filtered_df[
            pd.to_numeric(filtered_df[score_col], errors='coerce').fillna(0) >= criteria["score_threshold"]]
    if filtered_df.empty: return pd.DataFrame(columns=homology_df.columns)
    sort_by_metrics, ascending_flags = criteria.get("sort_by", ["Score"]), criteria.get("ascending", [False])
    sort_by_cols = [criteria.get(col.lower(), col) for col in sort_by_metrics]
    sorted_df = filtered_df.sort_values(by=sort_by_cols, ascending=ascending_flags)
    top_n_val = criteria.get("top_n")
    if top_n_val is not None and top_n_val > 0:
        return sorted_df.groupby(query_gene_id_col).head(top_n_val).reset_index(drop=True)
    return sorted_df.reset_index(drop=True)


# 保持不变的辅助函数
def load_and_map_homology(homology_df: pd.DataFrame, homology_columns: Dict[str, str],
                          selection_criteria: Dict[str, Any], query_gene_ids: Optional[List[str]] = None,
                          query_id_regex: Optional[str] = None, match_id_regex: Optional[str] = None) -> Dict[
    str, List[Dict[str, Any]]]:
    from .gff_parser import _apply_regex_to_id
    query_col, match_col = homology_columns.get('query'), homology_columns.get('match')
    if query_col not in homology_df.columns: raise ValueError(f"配置错误: 在同源文件中找不到查询列 '{query_col}'。")
    if match_col not in homology_df.columns: raise ValueError(f"配置错误: 在同源文件中找不到匹配列 '{match_col}'。")
    df_copy = homology_df.copy()
    df_copy[query_col] = df_copy[query_col].astype(str).apply(lambda x: _apply_regex_to_id(x, query_id_regex))
    df_copy[match_col] = df_copy[match_col].astype(str).apply(lambda x: _apply_regex_to_id(x, match_id_regex))
    filtered_df = df_copy
    if query_gene_ids:
        processed_query_ids = {_apply_regex_to_id(gid, query_id_regex) for gid in query_gene_ids}
        filtered_df = df_copy[df_copy[query_col].isin(processed_query_ids)]
    if filtered_df.empty: return {}
    criteria = {**selection_criteria, **homology_columns}
    best_hits_df = select_best_homologs(filtered_df, query_col, match_col, criteria)
    homology_map: Dict[str, List[Dict[str, Any]]] = {}
    for _, row in best_hits_df.iterrows():
        query_id = row[query_col]
        homology_map.setdefault(query_id, []).append(row.to_dict())
    return homology_map


# 【新增】核心逻辑执行函数
def _execute_full_mapping_logic(
        source_gene_ids: List[str],
        source_genome_info: GenomeSourceItem,
        target_genome_info: GenomeSourceItem,
        bridge_genome_info: GenomeSourceItem,
        source_to_bridge_homology_df: pd.DataFrame,
        bridge_to_target_homology_df: pd.DataFrame,
        selection_criteria_s_to_b: Dict[str, Any],
        selection_criteria_b_to_t: Dict[str, Any],
        homology_columns: Dict[str, str],
        log: Callable,
        progress: Callable
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    # 这部分包含了您文件中原有的、能够成功运行的完整A->B->C逻辑
    user_top_n = selection_criteria_s_to_b.get('top_n', 1)
    temp_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 0}
    temp_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 0}

    progress(50, _("正在映射: 源 -> 桥梁..."))
    s2b_map = load_and_map_homology(source_to_bridge_homology_df, homology_columns, temp_s2b_criteria, source_gene_ids,
                                    source_genome_info.gene_id_regex, bridge_genome_info.gene_id_regex)
    if not s2b_map: return pd.DataFrame(), source_gene_ids

    s2b_hits_df = pd.DataFrame([match for matches in s2b_map.values() for match in matches])
    bridge_gene_ids = s2b_hits_df[homology_columns.get('match')].unique().tolist()

    progress(65, _("正在映射: 桥梁 -> 目标..."))
    b2t_homology_cols = {'query': homology_columns.get('match'), 'match': homology_columns.get('query'),
                         **{k: v for k, v in homology_columns.items() if k not in ['query', 'match']}}
    b2t_map = load_and_map_homology(bridge_to_target_homology_df, b2t_homology_cols, temp_b2t_criteria, bridge_gene_ids,
                                    bridge_genome_info.gene_id_regex, target_genome_info.gene_id_regex)
    if not b2t_map: return pd.DataFrame(), source_gene_ids

    b2t_hits_df = pd.DataFrame([match for matches in b2t_map.values() for match in matches])

    progress(75, _("正在合并映射结果..."))
    df1 = s2b_hits_df.rename(
        columns={homology_columns.get('query'): "Source_Gene_ID", homology_columns.get('match'): "Bridge_Gene_ID"})
    df2 = b2t_hits_df.rename(
        columns={b2t_homology_cols.get('query'): "Bridge_Gene_ID", b2t_homology_cols.get('match'): "Target_Gene_ID"})
    merged_df = pd.merge(df1, df2, on="Bridge_Gene_ID", how="inner", suffixes=('_s2b', '_b2t'))
    if merged_df.empty: return pd.DataFrame(), source_gene_ids

    progress(85, _("正在根据模式筛选和排序..."))
    is_cotton_to_cotton = source_genome_info.is_cotton() and target_genome_info.is_cotton()
    strict_mode = selection_criteria_s_to_b.get('strict_subgenome_priority', True)
    score_col_name = homology_columns.get('score', 'Score')
    score_s2b_col, score_b2t_col = f"{score_col_name}_s2b", f"{score_col_name}_b2t"
    if score_s2b_col not in merged_df.columns: merged_df[score_s2b_col] = 0
    if score_b2t_col not in merged_df.columns: merged_df[score_b2t_col] = 0
    secondary_sort_cols, ascending_flags = [score_s2b_col, score_b2t_col], [False, False]

    if strict_mode and is_cotton_to_cotton:
        log(_("已启用严格模式：仅保留同亚组、同染色体编号的匹配。"), "INFO")
        merged_df['Source_Parsed'] = merged_df['Source_Gene_ID'].apply(parse_gene_id)
        merged_df['Target_Parsed'] = merged_df['Target_Gene_ID'].apply(parse_gene_id)
        condition = ((merged_df['Source_Parsed'].notna()) & (merged_df['Target_Parsed'].notna()) & (
                    merged_df['Source_Parsed'].str[0] == merged_df['Target_Parsed'].str[0]) & (
                                 merged_df['Source_Parsed'].str[1] == merged_df['Target_Parsed'].str[1]))
        sorted_df = merged_df[condition].sort_values(by=secondary_sort_cols, ascending=ascending_flags)
    else:
        log(_("严格模式已关闭，使用常规双分数排序规则。"), "INFO")
        sorted_df = merged_df.sort_values(by=secondary_sort_cols, ascending=ascending_flags)

    progress(90, _("正在筛选 Top N 结果..."))
    final_df = sorted_df
    if user_top_n is not None and user_top_n > 0: final_df = sorted_df.groupby('Source_Gene_ID', sort=False).head(
        user_top_n)

    successfully_mapped_genes = set(final_df['Source_Gene_ID'].unique())
    failed_genes = [gid for gid in source_gene_ids if gid not in successfully_mapped_genes]
    if failed_genes: log(_("信息: {} 个源基因未能找到符合条件的同源匹配。").format(len(failed_genes)), "INFO")

    final_df = final_df.drop(columns=['Source_Parsed', 'Target_Parsed'], errors='ignore').reset_index(drop=True)
    return final_df, failed_genes


# 【重构后】的智能函数
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
    log = status_callback if status_callback else lambda msg, level="INFO": logger.info(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: None
    bridge_genome_info = kwargs.get('bridge_genome_info')
    if not bridge_genome_info: raise ValueError("Bridge genome info is required.")

    is_map_to_bridge = (target_assembly_name == bridge_species_name)
    is_map_from_bridge = (source_assembly_name == bridge_species_name)

    # 模式1: 棉花 -> 拟南芥 (A -> B)
    if is_map_to_bridge and not is_map_from_bridge:
        log(_("智能映射: 检测到 [源 -> 桥梁] 模式，构建虚拟流程..."), "INFO")
        # 创建一个虚拟的 B->B 自身映射表
        bridge_col = homology_columns.get("match", "Match")
        query_col = homology_columns.get("query", "Query")
        possible_hits = source_to_bridge_homology_df[source_to_bridge_homology_df[query_col].isin(source_gene_ids)]
        bridge_genes = possible_hits[bridge_col].dropna().unique()
        dummy_b2t_df = pd.DataFrame({
            query_col: bridge_genes,
            bridge_col: bridge_genes,
            homology_columns.get("score", "Score"): [9999] * len(bridge_genes),
            homology_columns.get("evalue", "Exp"): [0] * len(bridge_genes),
            homology_columns.get("pid", "PID"): [100.0] * len(bridge_genes),
        })

        # 对虚拟步骤放宽筛选
        relaxed_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 1, 'evalue_threshold': None,
                                'pid_threshold': None, 'score_threshold': None}

        final_df, failed_genes = _execute_full_mapping_logic(
            source_gene_ids=source_gene_ids,
            source_genome_info=source_genome_info,
            target_genome_info=bridge_genome_info,  # 目标信息用桥梁的
            bridge_genome_info=bridge_genome_info,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=dummy_b2t_df,  # 使用虚拟数据
            selection_criteria_s_to_b=selection_criteria_s_to_b,
            selection_criteria_b_to_t=relaxed_b2t_criteria,
            homology_columns=homology_columns,
            log=log, progress=progress
        )
        # 清理虚拟步骤产生的冗余列
        if 'Target_Gene_ID' in final_df.columns and 'Bridge_Gene_ID' in final_df.columns:
            # 比较前先确保数据类型一致且无空值
            bridge_ids = final_df['Bridge_Gene_ID'].dropna()
            target_ids = final_df['Target_Gene_ID'].dropna()
            if len(bridge_ids) == len(target_ids) and all(bridge_ids == target_ids):
                final_df = final_df.drop(columns=['Target_Gene_ID'])

        return final_df, failed_genes

    # 模式2: 拟南芥 -> 棉花 (B -> C)
    elif is_map_from_bridge and not is_map_to_bridge:
        log(_("智能映射: 检测到 [桥梁 -> 目标] 模式，构建虚拟流程..."), "INFO")
        # 创建一个虚拟的 B->B 自身映射表
        query_col = homology_columns.get("query", "Query")
        match_col = homology_columns.get("match", "Match")
        dummy_s2b_df = pd.DataFrame({
            query_col: source_gene_ids,  # 源基因就是桥梁基因
            match_col: source_gene_ids,
            homology_columns.get("score", "Score"): [9999] * len(source_gene_ids),
            homology_columns.get("evalue", "Exp"): [0] * len(source_gene_ids),
            homology_columns.get("pid", "PID"): [100.0] * len(source_gene_ids),
        })
        # 对虚拟步骤放宽筛选
        relaxed_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 1, 'evalue_threshold': None,
                                'pid_threshold': None, 'score_threshold': None}

        final_df, failed_genes = _execute_full_mapping_logic(
            source_gene_ids=source_gene_ids,
            source_genome_info=bridge_genome_info,  # 源信息用桥梁的
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            source_to_bridge_homology_df=dummy_s2b_df,  # 使用虚拟数据
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=relaxed_s2b_criteria,
            selection_criteria_b_to_t=selection_criteria_b_to_t,
            homology_columns=homology_columns,
            log=log, progress=progress
        )
        return final_df, failed_genes

    # 模式3: 标准 A -> B -> C
    else:
        return _execute_full_mapping_logic(
            source_gene_ids=source_gene_ids,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b,
            selection_criteria_b_to_t=selection_criteria_b_to_t,
            homology_columns=homology_columns,
            log=log, progress=progress
        )