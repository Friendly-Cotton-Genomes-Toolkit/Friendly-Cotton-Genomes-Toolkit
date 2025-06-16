import logging
from typing import List, Dict, Any, Tuple, Optional, Callable

import pandas as pd
from .gff_parser import _apply_regex_to_id
from ..config.models import GenomeSourceItem
from ..utils.gene_utils import parse_gene_id

_ = lambda text: text
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
        raise ValueError(f"配置错误: 在同源文件中找不到查询列 '{query_col}'。可用列: {list(homology_df.columns)}")
    if match_col not in homology_df.columns:
        raise ValueError(f"配置错误: 在同源文件中找不到匹配列 '{match_col}'。可用列: {list(homology_df.columns)}")

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
    for _, row in best_hits_df.iterrows():
        query_id = row[query_col]
        homology_map.setdefault(query_id, []).append(row.to_dict())

    return homology_map


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
        **kwargs
) -> Tuple[pd.DataFrame, Any]:
    """
    通过桥梁物种进行基因映射，并根据条件执行包含共线性权重的三级优先排序。

    Args:
        source_gene_ids (List[str]): 需要映射的源基因ID列表。
        source_assembly_name (str): 源基因组的名称。
        target_assembly_name (str): 目标基因组的名称。
        bridge_species_name (str): 桥梁物种的名称。
        source_to_bridge_homology_df (pd.DataFrame): 源到桥梁的同源数据。
        bridge_to_target_homology_df (pd.DataFrame): 桥梁到目标的同源数据。
        selection_criteria_s_to_b (Dict[str, Any]): 源到桥梁的筛选标准。
        selection_criteria_b_to_t (Dict[str, Any]): 桥梁到目标的筛选标准。
        homology_columns (Dict[str, str]): 同源文件中的列名映射。
        source_genome_info (GenomeSourceItem): 源基因组的详细信息对象。
        target_genome_info (GenomeSourceItem): 目标基因组的详细信息对象。
        status_callback (Optional[Callable[[str, str], None]]): 状态更新回调函数。
        **kwargs: 其他可选参数，如 bridge_id_regex, cancel_event。

    Returns:
        Tuple[pd.DataFrame, Any]: 一个包含最终映射结果的DataFrame和第二个保留返回值（当前为None）。
    """

    log = status_callback if status_callback else lambda msg, level="INFO": logger.info(f"[{level}] {msg}")

    # 获取桥梁物种的正则表达式
    bridge_id_regex =  r'AT[1-5]G\d{5}'

    # 1. 保存用户原始的top_n设置，并创建临时标准以获取所有同源关系
    user_top_n = selection_criteria_s_to_b.get('top_n', 1)
    temp_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 0}
    temp_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 0}
    bridge_id_regex = kwargs.get('bridge_id_regex')
    log("步骤1和2将获取所有可能的同源关系 (临时 top_n=0)", "DEBUG")

    # 步骤 1.1: 源 -> 桥梁
    s2b_map = load_and_map_homology(source_to_bridge_homology_df, homology_columns, temp_s2b_criteria, source_gene_ids,
                                    source_genome_info.gene_id_regex, bridge_id_regex)
    if not s2b_map:
        log("在源->桥梁同源数据中未找到任何匹配记录。", "WARNING")
        return pd.DataFrame(), None

    s2b_hits_df = pd.DataFrame([match for matches in s2b_map.values() for match in matches])
    bridge_gene_ids = s2b_hits_df[homology_columns.get('match')].unique().tolist()
    log(_("[步骤1: 源->桥梁] 完成，找到 {} 个桥梁同源物。").format(len(bridge_gene_ids)), "DEBUG")

    # 步骤 1.2: 桥梁 -> 目标
    b2t_homology_cols = {
        'query': homology_columns.get('match'),
        'match': homology_columns.get('query'),
        **{k: v for k, v in homology_columns.items() if k not in ['query', 'match']}
    }
    b2t_map = load_and_map_homology(bridge_to_target_homology_df, b2t_homology_cols, temp_b2t_criteria, bridge_gene_ids,
                                    bridge_id_regex, target_genome_info.gene_id_regex)
    if not b2t_map:
        log("在桥梁->目标同源数据中未找到任何匹配记录。", "WARNING")
        return pd.DataFrame(), None

    b2t_hits_df = pd.DataFrame([match for matches in b2t_map.values() for match in matches])
    log(_("[步骤2: 桥梁->目标] 完成。"), "DEBUG")

    # 步骤 2: 合并
    df1 = s2b_hits_df.rename(
        columns={homology_columns.get('query'): "Source_Gene_ID", homology_columns.get('match'): "Bridge_Gene_ID"})
    df2 = b2t_hits_df.rename(
        columns={b2t_homology_cols.get('query'): "Bridge_Gene_ID", b2t_homology_cols.get('match'): "Target_Gene_ID"})
    merged_df = pd.merge(df1, df2, on="Bridge_Gene_ID", how="inner", suffixes=('_s2b', '_b2t'))
    if merged_df.empty:
        log("通过桥梁基因未能连接源基因与目标基因。", "WARNING")
        return pd.DataFrame(), None

    # 步骤 3: 最终排序
    prioritize_subgenome = selection_criteria_s_to_b.get('prioritize_subgenome', False)
    # 【修正】使用新的 is_cotton() 方法
    is_cotton_to_cotton = source_genome_info.is_cotton() and target_genome_info.is_cotton()


    score_col_name = homology_columns.get('score', 'Score')
    secondary_sort_cols = [f"{score_col_name}_s2b", f"{score_col_name}_b2t"]
    ascending_flags = [False, False]

    if prioritize_subgenome and is_cotton_to_cotton:
        log("正在执行棉花-棉花三级优先排序...", "INFO")

        merged_df['Source_Parsed'] = merged_df['Source_Gene_ID'].apply(parse_gene_id)
        merged_df['Target_Parsed'] = merged_df['Target_Gene_ID'].apply(parse_gene_id)

        def calculate_priority_score(row):
            source_info = row['Source_Parsed']
            target_info = row['Target_Parsed']
            if not source_info or not target_info: return 0
            if source_info == target_info: return 2
            if source_info[0] == target_info[0]: return 1
            return 0

        merged_df['homology_priority_score'] = merged_df.apply(calculate_priority_score, axis=1)

        final_sort_cols = ['homology_priority_score'] + secondary_sort_cols
        final_ascending = [False] + ascending_flags

        log(f"多级排序依据: {final_sort_cols}, 排序顺序: {final_ascending}", "DEBUG")
        sorted_df = merged_df.sort_values(by=final_sort_cols, ascending=final_ascending)
    else:
        log("不执行亚组倾向性排序，使用常规双分数排序规则。", "INFO")
        sorted_df = merged_df.sort_values(by=secondary_sort_cols, ascending=ascending_flags)

    # 步骤 4: 应用Top N
    final_df = sorted_df
    if user_top_n is not None and user_top_n > 0:
        log(f"正在为每个源基因提取 top {user_top_n} 个最佳结果...", "INFO")
        # 使用 sort=False 来保留我们精心设计的排序结果
        final_df = sorted_df.groupby('Source_Gene_ID', sort=False).head(user_top_n)

    # 清理辅助列并返回
    final_df = final_df.drop(columns=['Source_Parsed', 'Target_Parsed', 'homology_priority_score'], errors='ignore')

    # --- 为结果文件添加版本备注 ---
    notes = []
    if source_genome_info.bridge_version and source_genome_info.bridge_version.lower() == 'tair10':
        notes.append(f"Source uses tair10.")
    if target_genome_info.bridge_version and target_genome_info.bridge_version.lower() == 'tair10':
        notes.append(f"Target uses tair10.")

    if notes:
        final_df['Mapping_Note'] = " ".join(notes)
    # --- 新增结束 ---

    final_df = final_df.reset_index(drop=True)
    log(_("映射完成，找到 {} 条最终映射路径。").format(len(final_df)), "INFO")

    return final_df, None