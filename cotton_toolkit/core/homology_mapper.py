import logging
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Callable
import threading

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
        progress: Callable,
        cancel_event: Optional[threading.Event] = None
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """
    执行完整的 源基因 -> 桥梁基因 -> 目标基因 的三步映射逻辑。

    该函数现在支持通过 `cancel_event` 进行任务中断。
    """

    def check_cancel():
        """辅助函数，用于检查是否收到了取消信号。"""
        if cancel_event and cancel_event.is_set():
            logger.info(_("映射任务已被用户取消。"))
            return True
        return False

    # Top N 参数现在用于筛选最优的 N 个【桥梁基因】
    user_top_n_s2b = selection_criteria_s_to_b.get('top_n', 1)

    # 步骤1: 先应用除top_n外的所有筛选条件，找出所有可能的 源->桥梁 路径
    temp_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 0}
    progress(50, _("正在映射: 源 -> 桥梁..."))
    # 注意：假设 load_and_map_homology 内部也支持 cancel_event
    s2b_map = load_and_map_homology(source_to_bridge_homology_df, homology_columns, temp_s2b_criteria, source_gene_ids,
                                    source_genome_info.gene_id_regex, bridge_genome_info.gene_id_regex)

    if check_cancel(): return pd.DataFrame(), source_gene_ids
    if not s2b_map: return pd.DataFrame(), source_gene_ids

    all_s2b_hits_df = pd.DataFrame([match for matches in s2b_map.values() for match in matches])
    if all_s2b_hits_df.empty: return pd.DataFrame(), source_gene_ids

    # 步骤2: 对所有可能的桥梁基因按分数排序，并选出Top N个
    score_col_name = homology_columns.get('score', 'Score')
    if score_col_name in all_s2b_hits_df.columns:
        all_s2b_hits_df = all_s2b_hits_df.sort_values(by=score_col_name, ascending=False)

    if user_top_n_s2b is not None and user_top_n_s2b > 0:
        s2b_hits_df = all_s2b_hits_df.groupby(homology_columns.get('query')).head(user_top_n_s2b)
    else:
        s2b_hits_df = all_s2b_hits_df

    bridge_gene_ids = s2b_hits_df[homology_columns.get('match')].unique().tolist()
    if not bridge_gene_ids:
        return pd.DataFrame(), source_gene_ids

    if check_cancel(): return pd.DataFrame(), source_gene_ids

    # 步骤3: 从这Top N个桥梁基因出发，找出【所有】对应的目标基因（不再使用top_n限制）
    progress(65, _("正在映射: 桥梁 -> 目标..."))
    temp_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 0}
    b2t_homology_cols = {'query': homology_columns.get('match'), 'match': homology_columns.get('query'),
                         **{k: v for k, v in homology_columns.items() if k not in ['query', 'match']}}
    b2t_map = load_and_map_homology(bridge_to_target_homology_df, b2t_homology_cols, temp_b2t_criteria, bridge_gene_ids,
                                    bridge_genome_info.gene_id_regex, target_genome_info.gene_id_regex)

    if check_cancel(): return pd.DataFrame(), source_gene_ids
    if not b2t_map: return pd.DataFrame(), source_gene_ids

    b2t_hits_df = pd.DataFrame([match for matches in b2t_map.values() for match in matches])

    if check_cancel(): return pd.DataFrame(), source_gene_ids

    progress(75, _("正在合并映射结果..."))
    df1 = s2b_hits_df.rename(
        columns={homology_columns.get('query'): "Source_Gene_ID", homology_columns.get('match'): "Bridge_Gene_ID"})
    df2 = b2t_hits_df.rename(
        columns={b2t_homology_cols.get('query'): "Bridge_Gene_ID", b2t_homology_cols.get('match'): "Target_Gene_ID"})
    merged_df = pd.merge(df1, df2, on="Bridge_Gene_ID", how="inner", suffixes=('_s2b', '_b2t'))
    if merged_df.empty: return pd.DataFrame(), source_gene_ids

    # 计算并添加一对多关系的指示列
    merged_df['Num_Bridge_Homologs'] = merged_df.groupby('Source_Gene_ID')['Bridge_Gene_ID'].transform('nunique')
    merged_df['Num_Target_Homologs_From_Bridge'] = merged_df.groupby('Bridge_Gene_ID')['Target_Gene_ID'].transform(
        'nunique')

    progress(85, _("正在根据模式筛选和排序..."))
    is_cotton_to_cotton = source_genome_info.is_cotton() and target_genome_info.is_cotton()
    strict_mode = selection_criteria_s_to_b.get('strict_subgenome_priority', True)
    score_s2b_col, score_b2t_col = f"{score_col_name}_s2b", f"{score_col_name}_b2t"
    if score_s2b_col not in merged_df.columns: merged_df[score_s2b_col] = 0
    if score_b2t_col not in merged_df.columns: merged_df[score_b2t_col] = 0
    secondary_sort_cols, ascending_flags = [score_s2b_col, score_b2t_col], [False, False]

    if strict_mode and is_cotton_to_cotton:
        logger.info(_("已启用严格模式：仅保留同亚组、同染色体编号的匹配。"))
        merged_df['Source_Parsed'] = merged_df['Source_Gene_ID'].apply(parse_gene_id)
        merged_df['Target_Parsed'] = merged_df['Target_Gene_ID'].apply(parse_gene_id)
        condition = ((merged_df['Source_Parsed'].notna()) & (merged_df['Target_Parsed'].notna()) &
                     (merged_df['Source_Parsed'].str[0] == merged_df['Target_Parsed'].str[0]) &
                     (merged_df['Source_Parsed'].str[1] == merged_df['Target_Parsed'].str[1]))
        sorted_df = merged_df[condition].sort_values(by=secondary_sort_cols, ascending=ascending_flags)
    else:
        logger.info(_("严格模式已关闭，使用常规双分数排序规则。"))
        sorted_df = merged_df.sort_values(by=secondary_sort_cols, ascending=ascending_flags)

    if check_cancel(): return pd.DataFrame(), source_gene_ids

    progress(90, _("正在整理最终结果..."))
    final_df = sorted_df.drop_duplicates(subset=['Source_Gene_ID', 'Bridge_Gene_ID', 'Target_Gene_ID'])

    successfully_mapped_genes = set(final_df['Source_Gene_ID'].unique())
    failed_genes = [gid for gid in source_gene_ids if gid not in successfully_mapped_genes]
    if failed_genes:
        logger.info(_("信息: {} 个源基因未能找到符合条件的同源匹配。").format(len(failed_genes)))

    final_df = final_df.drop(columns=['Source_Parsed', 'Target_Parsed'], errors='ignore').reset_index(drop=True)

    if not final_df.empty:
        core_cols = ['Source_Gene_ID', 'Bridge_Gene_ID', 'Target_Gene_ID', 'Num_Bridge_Homologs',
                     'Num_Target_Homologs_From_Bridge']
        existing_core_cols = [c for c in core_cols if c in final_df.columns]
        other_cols = [c for c in final_df.columns if c not in existing_core_cols]
        final_df = final_df[existing_core_cols + other_cols]

    return final_df, failed_genes

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
        progress_callback: Optional[Callable] = None,
        **kwargs
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    # 修改：不再使用 log 回调，直接使用 logger
    progress = progress_callback if progress_callback else lambda p, m: None
    bridge_genome_info = kwargs.get('bridge_genome_info')
    if not bridge_genome_info: raise ValueError("Bridge genome info is required.")

    is_map_to_bridge = (target_assembly_name == bridge_species_name)
    is_map_from_bridge = (source_assembly_name == bridge_species_name)

    if is_map_to_bridge and not is_map_from_bridge:
        # 修改：使用标准logger
        logger.info(_("智能映射: 检测到 [源 -> 桥梁] 模式，构建虚拟流程..."))
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

        relaxed_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 1, 'evalue_threshold': None,
                                'pid_threshold': None, 'score_threshold': None}

        final_df, failed_genes = _execute_full_mapping_logic(
            source_gene_ids=source_gene_ids,
            source_genome_info=source_genome_info,
            target_genome_info=bridge_genome_info,
            bridge_genome_info=bridge_genome_info,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=dummy_b2t_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b,
            selection_criteria_b_to_t=relaxed_b2t_criteria,
            homology_columns=homology_columns,
            progress=progress
        )
        if 'Target_Gene_ID' in final_df.columns and 'Bridge_Gene_ID' in final_df.columns:
            bridge_ids = final_df['Bridge_Gene_ID'].dropna()
            target_ids = final_df['Target_Gene_ID'].dropna()
            if len(bridge_ids) == len(target_ids) and all(bridge_ids == target_ids):
                final_df = final_df.drop(columns=['Target_Gene_ID'])

        return final_df, failed_genes

    elif is_map_from_bridge and not is_map_to_bridge:
        # 修改：使用标准logger
        logger.info(_("智能映射: 检测到 [桥梁 -> 目标] 模式，构建虚拟流程..."))
        query_col = homology_columns.get("query", "Query")
        match_col = homology_columns.get("match", "Match")
        dummy_s2b_df = pd.DataFrame({
            query_col: source_gene_ids,
            match_col: source_gene_ids,
            homology_columns.get("score", "Score"): [9999] * len(source_gene_ids),
            homology_columns.get("evalue", "Exp"): [0] * len(source_gene_ids),
            homology_columns.get("pid", "PID"): [100.0] * len(source_gene_ids),
        })
        relaxed_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 1, 'evalue_threshold': None,
                                'pid_threshold': None, 'score_threshold': None}

        final_df, failed_genes = _execute_full_mapping_logic(
            source_gene_ids=source_gene_ids,
            source_genome_info=bridge_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            source_to_bridge_homology_df=dummy_s2b_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=relaxed_s2b_criteria,
            selection_criteria_b_to_t=selection_criteria_b_to_t,
            homology_columns=homology_columns,
            progress=progress
        )
        return final_df, failed_genes

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
            progress=progress
        )


def save_mapping_results(
        output_path: str,
        mapped_df: Optional[pd.DataFrame],
        failed_genes: List[str],
        source_assembly_id: str,
        target_assembly_id: str,
        source_gene_ids_count: int,
        region: Optional[Tuple[str, int, int]]
) -> bool:
    """
    将同源映射结果以智能格式保存到CSV或XLSX文件。

    Args:
        output_path (str): 目标输出文件路径 (.csv 或 .xlsx).
        mapped_df (Optional[pd.DataFrame]): 包含成功映射结果的数据框.
        failed_genes (List[str]): 映射失败的基因ID列表.
        source_assembly_id (str): 源基因组ID.
        target_assembly_id (str): 目标基因组ID.
        source_gene_ids_count (int): 输入的源基因总数.
        region (Optional[Tuple[str, int, int]]): 源染色体区域 (可选).

    Returns:
        bool: 保存是否成功.
    """
    output_path_lower = output_path.lower()

    if output_path_lower.endswith('.csv'):
        try:
            with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
                source_locus_str = f"{source_assembly_id} | {region[0]}:{region[1]}-{region[2]}" if region else f"{source_assembly_id} | {source_gene_ids_count} genes"
                f.write(_("# 源: {}\n").format(source_locus_str))
                f.write(_("# 目标: {}\n").format(target_assembly_id))
                # --- 新增代码块：在CSV文件头中添加新列的说明 ---
                f.write("#\n")
                f.write("# 列说明:\n")
                f.write(f"#   {_("Num_Bridge_Homologs: 指示一个'源基因'对应到了多少个不同的'桥梁基因' (拟南芥)")}\n")
                f.write(f"#   {_("Num_Target_Homologs_From_Bridge: 指示一个'桥梁基因'对应到了多少个不同的'目标基因'")}\n")
                f.write(f"#   {_("注意: 当这些列的值 > 1 时，表示存在一对多的映射关系，需要您特别关注")}\n")
                f.write("#\n")

                if mapped_df is not None and not mapped_df.empty:
                    mapped_df.to_csv(f, index=False, lineterminator='\n')
                else:
                    f.write(_("# 未找到任何成功的同源匹配。\n"))

                if failed_genes:
                    f.write("\n\n")
                    f.write(_("# --- 匹配失败的源基因 ---\n"))
                    reason = _("未能在目标基因组中找到满足所有筛选条件的同源基因。")
                    failed_df = pd.DataFrame({'Failed_Source_Gene_ID': failed_genes, 'Reason': reason})
                    failed_df.to_csv(f, index=False, lineterminator='\n')
            # 修改: 使用 logger
            logger.info(_(f"结果已成功保存到 CSV 文件: {output_path}"))
            return True
        except Exception as e:
            # 修改: 使用 logger
            logger.error(_(f"保存到 CSV 文件时出错: {e}"))
            return False

    elif output_path_lower.endswith('.xlsx'):
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                if mapped_df is not None and not mapped_df.empty:
                    mapped_df.to_excel(writer, sheet_name='Homology_Results', index=False)
                else:
                    pd.DataFrame([{'Status': _("未找到任何成功的同源匹配。")}]).to_excel(writer,
                                                                                        sheet_name='Homology_Results',
                                                                                        index=False)

                if failed_genes:
                    reason = _("未能在目标基因组中找到满足所有筛选条件的同源基因。")
                    failed_df = pd.DataFrame({'Failed_Source_Gene_ID': failed_genes, 'Reason': reason})
                    failed_df.to_excel(writer, sheet_name='Failed_Genes', index=False)
            # 修改: 使用 logger
            logger.info(_(f"结果已成功保存到 XLSX 文件: {output_path}"))
            return True
        except Exception as e:
            # 修改: 使用 logger
            logger.error(_(f"保存到 XLSX 文件时出错: {e}"))
            return False

    else:
        # 修改: 使用 logger
        logger.error(_(f"错误: 不支持的输出文件格式: {output_path}。请使用 .csv 或 .xlsx。"))
        return False
