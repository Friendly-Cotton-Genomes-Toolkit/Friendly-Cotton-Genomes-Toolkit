import logging
import os

import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Callable

from .gff_parser import _apply_regex_to_id
from ..config.models import GenomeSourceItem  # 确保导入了 GenomeSourceItem
from ..utils.gene_utils import parse_gene_id  # 确保导入了 parse_gene_id

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


# 新增 create_homology_df 函数，以匹配 pipelines.py 中的调用
def create_homology_df(file_path: str) -> pd.DataFrame:
    """
    从 CSV 或 Excel 文件加载同源数据到 DataFrame。
    这个函数是为了满足 pipelines.py 中对 create_homology_df 的调用而添加的。
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"同源文件未找到: {file_path}")

    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path)
    elif file_path.lower().endswith((".xlsx", ".xls")):
        # 如果是Excel，用pandas读取
        return pd.read_excel(file_path, engine='openpyxl')
    else:
        raise ValueError(f"不支持的同源文件格式: {os.path.basename(file_path)}")


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

    # 获取桥梁物种的正则表达式 (这里保持pipelines.py中定义的值)
    # 如果 kwargs 中有 bridge_id_regex，则优先使用；否则从 GenomeSourceItem 获取
    # 确保 bridge_genome_info 存在并且有 gene_id_regex 属性
    # 这里从 kwargs 中获取 bridge_genome_info，因为在 pipelines.py 中会传入
    bridge_genome_info = kwargs.get('bridge_genome_info')
    bridge_id_regex = kwargs.get('bridge_id_regex')
    if not bridge_id_regex and bridge_genome_info and hasattr(bridge_genome_info,
                                                              'gene_id_regex') and bridge_genome_info.gene_id_regex:
        bridge_id_regex = bridge_genome_info.gene_id_regex
    # 默认值，以防万一
    if not bridge_id_regex:
        bridge_id_regex = r'(AT[1-5MC]G\d{5})'

    # 1. 保存用户原始的top_n设置，并创建临时标准以获取所有同源关系
    user_top_n = selection_criteria_s_to_b.get('top_n', 1)
    temp_s2b_criteria = {**selection_criteria_s_to_b, 'top_n': 0}
    temp_b2t_criteria = {**selection_criteria_b_to_t, 'top_n': 0}

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
    # 确保这些列在 merged_df 中存在，否则进行防护
    score_s2b_col = f"{score_col_name}_s2b"
    score_b2t_col = f"{score_col_name}_b2t"

    # 检查列是否存在，如果不存在则使用默认值或跳过
    if score_s2b_col not in merged_df.columns:
        logger.warning(f"警告: 列 '{score_s2b_col}' 不存在，可能影响排序。将填充默认值0。")
        merged_df[score_s2b_col] = 0  # 填充0，避免报错
    if score_b2t_col not in merged_df.columns:
        logger.warning(f"警告: 列 '{score_b2t_col}' 不存在，可能影响排序。将填充默认值0。")
        merged_df[score_b2t_col] = 0  # 填充0，避免报错

    secondary_sort_cols = [score_s2b_col, score_b2t_col]
    ascending_flags = [False, False]  # 默认分数降序排列

    if prioritize_subgenome and is_cotton_to_cotton:
        # 新增日志：明确指示优先级开关状态
        log(f"优先级开关 prioritize_subgenome 已开启: {prioritize_subgenome}", "INFO")

        # 使用 errors='ignore' 以防解析失败，parse_gene_id 已经处理了 None 的情况
        merged_df['Source_Parsed'] = merged_df['Source_Gene_ID'].apply(parse_gene_id)
        merged_df['Target_Parsed'] = merged_df['Target_Gene_ID'].apply(parse_gene_id)

        # 新增调试日志：打印解析后的基因信息
        logger.info("部分合并DF的基因ID解析结果和原始ID (前10行):")  # 改为INFO级别
        for idx, row in merged_df.head(10).iterrows():  # 打印前10行
            logger.info(f"  Source_ID='{row['Source_Gene_ID']}' -> Parsed='{row['Source_Parsed']}'")
            logger.info(f"  Target_ID='{row['Target_Gene_ID']}' -> Parsed='{row['Target_Parsed']}'")

        def calculate_priority_keys(row) -> Tuple[int, int]:
            """
            计算优先级键，返回一个整数元组，用于强制排序。
            元组的第一个元素是亚组匹配的优先级 (2 > 1 > 0)，
            第二个元素是染色体编号匹配的优先级 (1 > 0)。
            最高优先级: (2, 1) -> 亚组相同, 染色体编号相同
            次高优先级: (2, 0) -> 亚组相同, 染色体编号不同
            最低优先级: (0, 0) -> 亚组不同 或 无法解析
            """
            source_info = row['Source_Parsed']  # (亚组, 染色体号)
            target_info = row['Target_Parsed']  # (亚组, 染色体号)

            # 如果无法解析基因ID（例如，Target_GeneID 是 GhiUnG...），则优先级最低
            # 同时，对于像 GhiUnG... 这种无亚组信息的基因，也应视为无法解析，获得最低优先级
            if not source_info or not target_info:
                # 检查target_info是否是"GhiUnG..."这种格式
                if isinstance(row['Target_Gene_ID'], str) and 'UnG' in row['Target_Gene_ID']:
                    logger.debug(f"Target_ID '{row['Target_Gene_ID']}' 包含 'UnG'，视为无法解析，优先级 (0,0).")
                else:
                    logger.debug(
                        f"Source_Info or Target_Info is None for '{row['Source_Gene_ID']}' -> '{row['Target_Gene_ID']}', Priority (0,0).")
                return (0, 0)  # 最低优先级

            source_subgenome = source_info[0]
            target_subgenome = target_info[0]
            source_chr_num = source_info[1]
            target_chr_num = target_info[1]

            # 1. 检查亚组是否相同
            subgenome_match_priority = 0
            if source_subgenome == target_subgenome:
                subgenome_match_priority = 2  # 亚组相同是最高层级的匹配 (A-A 或 D-D)

            # 2. 检查染色体编号是否相同 (仅在亚组相同的前提下有意义)
            chr_num_match_priority = 0
            # 只有当亚组匹配优先级为2时，才考虑染色体编号
            if subgenome_match_priority == 2 and source_chr_num == target_chr_num:
                chr_num_match_priority = 1  # 染色体编号相同是次层级的匹配

            return (subgenome_match_priority, chr_num_match_priority)

        merged_df['homology_priority_keys'] = merged_df.apply(calculate_priority_keys, axis=1)

        # 新增调试日志：打印计算出的优先级键
        logger.info("部分合并DF的优先级键和匹配信息 (前10行):")  # 改为INFO级别
        for idx, row in merged_df.head(10).iterrows():  # 打印前10行
            logger.info(
                f"  Source_ID='{row['Source_Gene_ID']}', Target_ID='{row['Target_Gene_ID']}', Priority_Keys='{row['homology_priority_keys']}'")

        # 排序键：先按 'homology_priority_keys' 降序（最高优先级元组在前），然后按分数降序
        # ['homology_priority_keys'] 是一个元组列，pandas 会按元组的元素逐个排序
        # [False, False] 表示 (2,1) 优于 (2,0) 优于 (0,0)
        final_sort_cols = ['homology_priority_keys'] + secondary_sort_cols
        final_ascending = [False] + ascending_flags

        log(f"多级排序依据: {final_sort_cols}, 排序顺序: {final_ascending}", "DEBUG")
        sorted_df = merged_df.sort_values(by=final_sort_cols, ascending=final_ascending)
    else:
        # 修正日志：明确指示开关未开启
        log(f"未开启亚组倾向性排序 (prioritize_subgenome 为 False)，使用常规双分数排序规则。", "INFO")
        sorted_df = merged_df.sort_values(by=secondary_sort_cols, ascending=ascending_flags)

    # 步骤 4: 应用Top N
    final_df = sorted_df
    if user_top_n is not None and user_top_n > 0:
        log(f"正在为每个源基因提取 top {user_top_n} 个最佳结果...", "INFO")
        # 使用 sort=False 来保留我们精心设计的排序结果
        final_df = sorted_df.groupby('Source_Gene_ID', sort=False).head(user_top_n)

    # 清理辅助列并返回
    final_df = final_df.drop(columns=['Source_Parsed', 'Target_Parsed', 'homology_priority_keys'], errors='ignore')

    # --- 为结果文件添加版本备注 ---
    notes = []
    # 这里的 bridge_version 属性应该在 GenomeSourceItem 中定义，检查是否存在
    if hasattr(source_genome_info,
               'bridge_version') and source_genome_info.bridge_version and source_genome_info.bridge_version.lower() == 'tair10':
        notes.append(f"Source uses tair10.")
    if hasattr(target_genome_info,
               'bridge_version') and target_genome_info.bridge_version and target_genome_info.bridge_version.lower() == 'tair10':
        notes.append(f"Target uses tair10.")

    if notes:
        final_df['Mapping_Note'] = " ".join(notes)
    # --- 新增结束 ---

    final_df = final_df.reset_index(drop=True)
    log(_("映射完成，找到 {} 条最终映射路径。").format(len(final_df)), "INFO")

    return final_df, None