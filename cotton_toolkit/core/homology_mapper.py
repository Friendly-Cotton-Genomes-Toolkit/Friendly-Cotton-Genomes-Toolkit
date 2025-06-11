# cotton_toolkit/core/homology_mapper.py

import logging
from typing import List, Dict, Any, Union, Tuple, Optional, Callable

import numpy as np
import pandas as pd

# --- 国际化和日志设置 ---
try:
    import builtins
    _ = builtins._ # type: ignore # 期望从主程序获取 _
except (AttributeError, ImportError):
    def _(text: str) -> str: return text # 备用方案1：定义一个透传函数
    print("Warning (homology_mapper.py): builtins._ not found for i18n. Using pass-through.")
# 或者更简单地:
# _ = gettext.gettext # 备用方案2：如果 gettext 未被正确初始化，这也会是透传



logger = logging.getLogger("cotton_toolkit.homology_mapper")


# --- 新增：函数来处理 homology_id_slicer ---
def _apply_id_slicer(gene_id: str, slicer_rule: Optional[str]) -> str:
    """
    根据 slicer_rule 对基因 ID 进行切片处理。
    例如：slicer_rule='.', 则 'Ghir.A01G123400.1' 变为 'Ghir.A01G123400'
    slicer_rule='_' 则 'Ghir_A01G123400' 变为 'Ghir_A01G123400' (如果需要处理到第一个 _)
    这里我们假设 slicer_rule 是一个分隔符，我们需要它之前的部分。
    更复杂的切片逻辑可能需要正则表达。
    """
    if slicer_rule and slicer_rule in gene_id:
        return gene_id.split(slicer_rule)[0]
    return gene_id

# --- 核心同源映射函数 load_and_map_homology ---
def load_and_map_homology(
        homology_file_path: str,
        homology_columns: Dict[str, str],
        selection_criteria: Dict[str, Any],
        query_gene_ids: Optional[List[str]] = None,
        homology_id_slicer: Optional[str] = None, # 引入 slicer 参数
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    加载同源数据，并根据筛选标准和查询基因ID进行映射。
    返回一个字典，键为查询基因ID，值为其所有符合条件的同源基因列表。
    """
    log = status_callback if status_callback else logger.info
    log(f"INFO: {_('加载同源文件:')} {homology_file_path}")

    homology_df = None
    try:
        # 支持 CSV 和 XLSX
        if homology_file_path.lower().endswith('.csv'):
            homology_df = pd.read_csv(homology_file_path)
        elif homology_file_path.lower().endswith(('.xlsx', '.xls')):
            homology_df = pd.read_excel(homology_file_path)
        else:
            log(_("错误: 不支持的同源文件格式。支持 .csv, .xlsx, .xls。"), level="ERROR")
            return {}
    except FileNotFoundError:
        log(_("错误: 同源文件未找到: {}").format(homology_file_path), level="ERROR")
        return {}
    except Exception as e:
        log(_("错误: 读取同源文件 {} 失败: {}").format(homology_file_path, e), level="ERROR")
        return {}

    # 重命名列以方便访问
    df_cols = homology_df.columns
    query_col = homology_columns.get('query')
    match_col = homology_columns.get('match')
    evalue_col = homology_columns.get('evalue')
    score_col = homology_columns.get('score')
    pid_col = homology_columns.get('pid')

    required_cols = [query_col, match_col, evalue_col, score_col, pid_col]
    if not all(col in df_cols for col in required_cols):
        log(_("错误: 同源文件中缺少必要的列。需要: {}").format(", ".join(required_cols)), level="ERROR")
        return {}

    # 应用 ID 切片器
    if homology_id_slicer:
        homology_df[query_col] = homology_df[query_col].apply(lambda x: _apply_id_slicer(str(x), homology_id_slicer))
        homology_df[match_col] = homology_df[match_col].apply(lambda x: _apply_id_slicer(str(x), homology_id_slicer))

    # 筛选同源数据
    filtered_df = homology_df.copy()

    if selection_criteria:
        if 'evalue_threshold' in selection_criteria and evalue_col:
            filtered_df = filtered_df[filtered_df[evalue_col] <= selection_criteria['evalue_threshold']]
        if 'pid_threshold' in selection_criteria and pid_col:
            filtered_df = filtered_df[filtered_df[pid_col] >= selection_criteria['pid_threshold']]
        if 'score_threshold' in selection_criteria and score_col:
            filtered_df = filtered_df[filtered_df[score_col] >= selection_criteria['score_threshold']]

    # 排序并取 Top N
    if 'sort_by' in selection_criteria and selection_criteria['sort_by'] and \
       'ascending' in selection_criteria and selection_criteria['ascending']:
        try:
            sort_cols = [homology_columns.get(c, c) for c in selection_criteria['sort_by']] # 确保用实际列名排序
            filtered_df = filtered_df.sort_values(by=sort_cols, ascending=selection_criteria['ascending'])
        except KeyError as e:
            log(_("警告: 排序依据列 {} 不存在，跳过排序。").format(e), level="WARNING")

    top_n = selection_criteria.get('top_n')
    if top_n is not None and top_n > 0:
        # 对每个查询基因，只保留 Top N
        filtered_df = filtered_df.groupby(query_col).head(top_n).reset_index(drop=True)

    # 过滤出 query_gene_ids 中的基因
    if query_gene_ids:
        # 应用 slicer 到查询 ID 列表，以确保一致性
        query_gene_ids_processed = [_apply_id_slicer(gid, homology_id_slicer) for gid in query_gene_ids]
        filtered_df = filtered_df[filtered_df[query_col].isin(query_gene_ids_processed)]
        # 确保原始 query_gene_ids 在结果中被映射，如果它们在 homology_df 中有映射的话

    # 构建最终的映射字典
    homology_map: Dict[str, List[Dict[str, Any]]] = {}
    for _c, row in filtered_df.iterrows():
        query_id = row[query_col]
        match_info = {col: row[col] for col in required_cols} # 包含所有关键同源信息
        homology_map.setdefault(query_id, []).append(match_info)

    log(_("同源映射完成。找到 {} 个查询基因的映射。").format(len(homology_map)))
    return homology_map


def select_best_homologs(
        homology_df: pd.DataFrame,
        query_gene_id_col: str,
        match_gene_id_col: str,
        criteria: Dict[str, Any],
        evalue_col_in_df: str = "Exp",
        score_col_in_df: str = "Score",
        pid_col_in_df: str = "PID"
) -> pd.DataFrame:
    """
    根据指定的筛选标准从同源关系DataFrame中为一个或多个查询基因选择最佳同源匹配。

    Args:
        homology_df (pd.DataFrame): 包含同源关系数据的DataFrame。
        query_gene_id_col (str): homology_df 中“查询基因ID”列的名称。
        match_gene_id_col (str): homology_df 中“匹配基因ID”列的名称。
        criteria (Dict[str, Any]): 筛选标准的字典，例如:
            {
                "sort_by": ["Score", "Exp", "PID"], # 通用度量名 ('Score', 'Exp', 'PID')
                "ascending": [False, True, False],  # 对应的排序方式列表
                "top_n": 1,                         # 每个查询基因选择的最佳匹配数量 (None则全选)
                "evalue_threshold": 1e-5,           # E-value 必须 <= 此值
                "pid_threshold": 0.0,               # PID 必须 >= 此值
                "score_threshold": 0.0              # Score 必须 >= 此值
            }
        evalue_col_in_df (str): homology_df 中实际的 E-value 列名。
        score_col_in_df (str): homology_df 中实际的 Score 列名。
        pid_col_in_df (str): homology_df 中实际的 PID 列名。

    Returns:
        pd.DataFrame: 包含每个查询基因的最佳同源匹配的DataFrame (可能为空)。
    """

    if homology_df.empty:
        logger.debug(_("select_best_homologs: 输入的homology_df为空，返回空DataFrame。"))
        return pd.DataFrame(columns=homology_df.columns)

    # 列名映射，将通用标准名映射到DataFrame中的实际列名
    metric_to_df_col = {
        "Exp": evalue_col_in_df,
        "Score": score_col_in_df,
        "PID": pid_col_in_df
    }
    # 确保查询和匹配列也包含在metric_to_df_col中，以防它们也用于排序（虽然不常见）
    if query_gene_id_col not in metric_to_df_col.values(): metric_to_df_col[query_gene_id_col] = query_gene_id_col
    if match_gene_id_col not in metric_to_df_col.values(): metric_to_df_col[match_gene_id_col] = match_gene_id_col

    filtered_df = homology_df.copy()

    # 1. 应用阈值过滤
    # 确保在过滤前列存在且为数值类型
    evalue_actual_col = metric_to_df_col.get("Exp")
    if "evalue_threshold" in criteria and evalue_actual_col and evalue_actual_col in filtered_df.columns:
        try:
            filtered_df[evalue_actual_col] = pd.to_numeric(filtered_df[evalue_actual_col], errors='coerce')
            filtered_df.dropna(subset=[evalue_actual_col], inplace=True)  # 移除无法转换的
            filtered_df = filtered_df[filtered_df[evalue_actual_col] <= criteria["evalue_threshold"]]
        except Exception as e:
            logger.warning(_("E-value过滤时出错 (列 '{}'): {}").format(evalue_actual_col, e))

    pid_actual_col = metric_to_df_col.get("PID")
    if "pid_threshold" in criteria and pid_actual_col and pid_actual_col in filtered_df.columns:
        try:
            filtered_df[pid_actual_col] = pd.to_numeric(filtered_df[pid_actual_col], errors='coerce')
            filtered_df.dropna(subset=[pid_actual_col], inplace=True)
            filtered_df = filtered_df[filtered_df[pid_actual_col] >= criteria["pid_threshold"]]
        except Exception as e:
            logger.warning(_("PID过滤时出错 (列 '{}'): {}").format(pid_actual_col, e))

    score_actual_col = metric_to_df_col.get("Score")
    if "score_threshold" in criteria and score_actual_col and score_actual_col in filtered_df.columns:
        try:
            filtered_df[score_actual_col] = pd.to_numeric(filtered_df[score_actual_col], errors='coerce')
            filtered_df.dropna(subset=[score_actual_col], inplace=True)
            filtered_df = filtered_df[filtered_df[score_actual_col] >= criteria["score_threshold"]]
        except Exception as e:
            logger.warning(_("Score过滤时出错 (列 '{}'): {}").format(score_actual_col, e))

    if filtered_df.empty:
        logger.debug(_("select_best_homologs: 应用阈值过滤后，DataFrame为空。"))
        return pd.DataFrame(columns=homology_df.columns)

    # 2. 排序和选择top_n
    sort_by_metrics = criteria.get("sort_by", [])
    sort_by_actual_cols = [metric_to_df_col[metric] for metric in sort_by_metrics
                           if metric in metric_to_df_col and metric_to_df_col[metric] in filtered_df.columns]

    top_n_val = criteria.get("top_n")

    if not sort_by_actual_cols:
        if top_n_val is not None and top_n_val > 0:  # top_n 有限且 > 0
            logger.warning(_("select_best_homologs: 定义了 top_n 但没有有效的排序列，将返回所有通过阈值的同源基因。"))
        return filtered_df

        # 确保用于排序的列是数值类型 (再次确保，因为copy和过滤可能改变类型)
    for col in sort_by_actual_cols:
        try:
            filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce')
        except Exception as e:
            logger.warning(_("将排序列 '{}' 转换为数值时出错: {}").format(col, e))
    filtered_df.dropna(subset=sort_by_actual_cols, inplace=True)  # 移除排序键为NaN的行

    if filtered_df.empty:
        logger.debug(_("select_best_homologs: 排序前移除NaN值后，DataFrame为空。"))
        return pd.DataFrame(columns=homology_df.columns)

    ascending_flags_raw = criteria.get("ascending", [])
    ascending_flags = [ascending_flags_raw[i] for i, metric in enumerate(sort_by_metrics)
                       if metric in metric_to_df_col and metric_to_df_col[metric] in filtered_df.columns]

    if query_gene_id_col not in filtered_df.columns:
        logger.warning(_("select_best_homologs: 查询基因ID列 '{}' 不在DataFrame中。将对整个表应用排序和top_n。").format(
            query_gene_id_col))
        sorted_df = filtered_df.sort_values(by=sort_by_actual_cols, ascending=ascending_flags)
        return sorted_df.head(top_n_val) if top_n_val is not None else sorted_df

    selected_groups = []
    for _a, group in filtered_df.groupby(query_gene_id_col):
        sorted_group = group.sort_values(by=sort_by_actual_cols, ascending=ascending_flags)
        selected_groups.append(sorted_group.head(top_n_val) if top_n_val is not None else sorted_group)

    if not selected_groups:
        logger.debug(_("select_best_homologs: 分组并应用top_n后，没有选中任何数据。"))
        return pd.DataFrame(columns=homology_df.columns)

    result_df = pd.concat(selected_groups).reset_index(drop=True)
    logger.debug(_("select_best_homologs: 选择了 {} 条最佳匹配。").format(len(result_df)))
    return result_df


def map_genes_via_bridge(
        source_gene_ids: Union[str, List[str]],
        source_assembly_name: str,
        target_assembly_name: str,
        source_to_bridge_homology_df: pd.DataFrame,
        bridge_to_target_homology_df: pd.DataFrame,
        s_to_b_query_col: str,
        s_to_b_match_col: str,
        b_to_t_query_col: str,
        b_to_t_match_col: str,
        selection_criteria_s_to_b: Dict[str, Any],
        selection_criteria_b_to_t: Dict[str, Any],
        source_id_slicer: Optional[str] = None,
        bridge_id_slicer: Optional[str] = None,
        evalue_col: str = "Exp",
        score_col: str = "Score",
        pid_col: str = "PID",
        bridge_species_name: str = "Arabidopsis_thaliana"
) -> Tuple[pd.DataFrame, int]:
    """
    Maps source genes to target genes via a bridge, handling ID slicing, fuzzy matching, and one-to-many relationships.

    Args:
        source_gene_ids (Union[str, List[str]]): A single gene ID or a list of gene IDs to map.
        source_assembly_name (str): The name of the source assembly.
        target_assembly_name (str): The name of the target assembly.
        source_to_bridge_homology_df (pd.DataFrame): DataFrame for source-to-bridge homology.
        bridge_to_target_homology_df (pd.DataFrame): DataFrame for bridge-to-target homology.
        s_to_b_query_col (str): Query ID column name in the source-to-bridge DataFrame.
        s_to_b_match_col (str): Match ID column name in the source-to-bridge DataFrame.
        b_to_t_query_col (str): Query ID column name in the bridge-to-target DataFrame.
        b_to_t_match_col (str): Match ID column name in the bridge-to-target DataFrame.
        selection_criteria_s_to_b (Dict[str, Any]): Filtering criteria for the source-to-bridge step.
        selection_criteria_b_to_t (Dict[str, Any]): Filtering criteria for the bridge-to-target step.
        source_id_slicer (Optional[str]): Character to slice source query IDs by (e.g., '_').
        bridge_id_slicer (Optional[str]): Character to slice bridge IDs by.
        evalue_col (str): The name of the E-value column.
        score_col (str): The name of the Score column.
        pid_col (str): The name of the PID column.
        bridge_species_name (str): The name of the bridge species.

    Returns:
        Tuple[pd.DataFrame, int]: A tuple containing the results DataFrame and the count of fuzzy matches performed.
    """
    if isinstance(source_gene_ids, str):
        source_gene_ids = [source_gene_ids]
    if not source_gene_ids:
        logger.warning(_("map_genes_via_bridge: 输入的源基因ID列表为空。"))
        return pd.DataFrame(), 0

    logger.info(_("开始通过 {} 将 {} 个源基因从 {} 映射到 {}...").format(
        bridge_species_name, len(set(source_gene_ids)), source_assembly_name, target_assembly_name))

    # --- Apply ID Slicing ---
    s_to_b_df = source_to_bridge_homology_df.copy()
    b_to_t_df = bridge_to_target_homology_df.copy()

    if source_id_slicer:
        logger.info(f"Applying slicer '{source_id_slicer}' to source homology query IDs.")
        s_to_b_df[s_to_b_query_col] = s_to_b_df[s_to_b_query_col].astype(str).str.split(source_id_slicer).str[0]

    if bridge_id_slicer:
        logger.info(f"Applying slicer '{bridge_id_slicer}' to bridge homology query/match IDs.")
        s_to_b_df[s_to_b_match_col] = s_to_b_df[s_to_b_match_col].astype(str).str.split(bridge_id_slicer).str[0]
        b_to_t_df[b_to_t_query_col] = b_to_t_df[b_to_t_query_col].astype(str).str.split(bridge_id_slicer).str[0]

    # --- Fuzzy Matching Logic ---
    fuzzy_match_count = 0
    expanded_source_ids = []
    source_id_notes = {}  # Maps the matched source ID back to a note about how it was found

    available_source_ids = set(s_to_b_df[s_to_b_query_col].unique())

    for input_id in set(source_gene_ids):
        if input_id in available_source_ids:
            expanded_source_ids.append(input_id)
            source_id_notes[input_id] = _("直接匹配")
        else:
            fuzzy_matches = [sid for sid in available_source_ids if str(sid).startswith(input_id)]
            if fuzzy_matches:
                fuzzy_match_count += 1
                expanded_source_ids.extend(fuzzy_matches)
                for match in fuzzy_matches:
                    source_id_notes[match] = _("模糊匹配 on '{}'").format(input_id)

    if not expanded_source_ids:
        logger.warning(_("在源->桥梁同源数据中未找到任何与输入源基因匹配的记录 (包括模糊匹配)。"))
        return pd.DataFrame(), fuzzy_match_count

    # 1. Source -> Bridge
    source_homologs_to_bridge_all = s_to_b_df[s_to_b_df[s_to_b_query_col].isin(expanded_source_ids)]
    best_bridge_hits_df = select_best_homologs(
        homology_df=source_homologs_to_bridge_all,
        query_gene_id_col=s_to_b_query_col,
        match_gene_id_col=s_to_b_match_col,
        criteria=selection_criteria_s_to_b,
        evalue_col_in_df=evalue_col, score_col_in_df=score_col, pid_col_in_df=pid_col
    )
    if best_bridge_hits_df.empty:
        logger.info(_("步骤1 (源->桥梁): 应用选择标准后，没有找到合适的桥梁物种同源基因。"))
        return pd.DataFrame(), fuzzy_match_count

    # 2. Bridge -> Target
    unique_bridge_gene_ids = best_bridge_hits_df[s_to_b_match_col].unique().tolist()
    target_homologs_from_bridge_all = b_to_t_df[b_to_t_df[b_to_t_query_col].isin(unique_bridge_gene_ids)]
    best_target_hits_df = select_best_homologs(
        homology_df=target_homologs_from_bridge_all,
        query_gene_id_col=b_to_t_query_col,
        match_gene_id_col=b_to_t_match_col,
        criteria=selection_criteria_b_to_t,
        evalue_col_in_df=evalue_col, score_col_in_df=score_col, pid_col_in_df=pid_col
    )
    if best_target_hits_df.empty:
        logger.info(_("步骤2 (桥梁->目标): 应用选择标准后，没有找到合适的目标棉花同源基因。"))
        return pd.DataFrame(), fuzzy_match_count

    # --- 3. Merge Results ---
    df1 = best_bridge_hits_df.rename(
        columns={s_to_b_query_col: "Source_Gene_ID_A", s_to_b_match_col: "Bridge_Gene_ID_Ath"})
    df2 = best_target_hits_df.rename(
        columns={b_to_t_query_col: "Bridge_Gene_ID_Ath", b_to_t_match_col: "Target_Gene_ID_B"})

    # The merge naturally handles one-to-many relationships
    merged_df = pd.merge(df1, df2, on="Bridge_Gene_ID_Ath", how="inner")
    if merged_df.empty:
        logger.info(_("通过桥梁基因未能将源基因与目标基因连接起来 (合并后为空)。"))
        return pd.DataFrame(), fuzzy_match_count

    # Add the fuzzy match note column
    merged_df['Match_Note'] = merged_df['Source_Gene_ID_A'].map(source_id_notes)

    # Clean up and reorder columns
    final_df = merged_df.drop_duplicates().reset_index(drop=True)
    logger.info(_("映射完成，找到 {} 条完整的 源基因->桥梁->目标基因 映射路径。").format(len(final_df)))

    return final_df, fuzzy_match_count


# --- 用于独立测试 homology_mapper.py 的示例代码 ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info(_("--- 开始独立测试 homology_mapper.py ---"))

    # --- 1. 准备示例同源数据 ---
    data_sourceA_to_At = {
        "Query_CottonA": ["CottonA_G001", "CottonA_G001", "CottonA_G002", "CottonA_G003", "CottonA_G001"],
        "Match_Ath": ["At_G100", "At_G101", "At_G100", "At_G102", "At_G103_low_score"],
        "Exp_val": [1e-50, 1e-45, 1e-60, 1e-30, 1e-15],
        "Score_val": [500, 450, 600, 300, 80],
        "PID_val": [80.0, 75.0, 85.0, 70.0, 55.0]
    }
    source_to_at_df = pd.DataFrame(data_sourceA_to_At)

    data_At_to_targetB = {
        "Query_Ath": ["At_G100", "At_G100", "At_G101", "At_G102", "At_G103_low_score"],
        "Match_CottonB": ["CottonB_g201", "CottonB_g202", "CottonB_g203", "CottonB_g204", "CottonB_g205_low_pid"],
        "Exp_val": [1e-70, 1e-65, 1e-50, 1e-40, 1e-25],
        "Score_val": [700, 650, 500, 400, 200],
        "PID_val": [90.0, 88.0, 80.0, 75.0, 30.0]  # CottonB_g205_low_pid 的PID较低
    }
    at_to_target_df = pd.DataFrame(data_At_to_targetB)

    # --- 2. 定义裁剪/选择标准 ---
    # 注意：'sort_by' 中的值 ('Score', 'Exp', 'PID') 是通用名称，
    # select_best_homologs 函数内部会通过 evalue/score/pid_col_in_df 参数映射到实际列名。
    criteria_s_to_b_example = {
        "sort_by": ["Score", "Exp"],
        "ascending": [False, True],
        "top_n": 1,
        "evalue_threshold": 1e-10,
        "pid_threshold": 60.0,  # CottonA_G001 -> At_G103_low_score (PID 55) 会被过滤
        "score_threshold": 100.0
    }
    criteria_b_to_t_example = {
        "sort_by": ["Score", "PID"],
        "ascending": [False, False],
        "top_n": 1,
        "evalue_threshold": 1e-20,
        "pid_threshold": 70.0,  # CottonB_g205_low_pid (PID 30) 会被过滤
        "score_threshold": 150.0
    }

    # --- 3. 指定要映射的源基因ID ---
    source_genes_to_map_example = ["CottonA_G001", "CottonA_G002", "CottonA_G003", "CottonA_G004_NoHit"]

    # --- 4. 执行映射 ---
    logger.info("\n--- 调用 map_genes_via_bridge ---")
    mapped_results_df = map_genes_via_bridge(
        source_gene_ids=source_genes_to_map_example,
        source_assembly_name="CottonA_Demo",
        target_assembly_name="CottonB_Demo",
        bridge_species_name="Arabidopsis_thaliana",
        source_to_bridge_homology_df=source_to_at_df,
        bridge_to_target_homology_df=at_to_target_df,
        s_to_b_query_col="Query_CottonA",
        s_to_b_match_col="Match_Ath",
        b_to_t_query_col="Query_Ath",
        b_to_t_match_col="Match_CottonB",
        evalue_col="Exp_val",  # DataFrame中实际的Evalue列名
        score_col="Score_val",  # DataFrame中实际的Score列名
        pid_col="PID_val",  # DataFrame中实际的PID列名
        selection_criteria_s_to_b=criteria_s_to_b_example,
        selection_criteria_b_to_t=criteria_b_to_t_example
    )

    if not mapped_results_df.empty:
        print("\n--- 映射结果 (独立测试) ---")
        print(mapped_results_df.to_string())
        # 预期:
        # CottonA_G001 -> At_G100 (score 500) -> CottonB_g201 (score 700, pid 90)
        # CottonA_G002 -> At_G100 (score 600) -> CottonB_g201 (score 700, pid 90)
        # CottonA_G003 -> At_G102 (score 300) -> CottonB_g204 (score 400, pid 75)
        # CottonA_G001 -> At_G101 (score 450) -> CottonB_g203 (score 500, pid 80)
        # 上面是如果 top_n=1 应用于每一步后，再合并。
        # 由于 CottonA_G001 有多个 At 同源，如果 top_n=1 仅选择 At_G100 (基于Score)，则只有一条路径。
        # 如果 select_best_homologs 返回多个最佳（例如 top_n=None 或 top_n=2 且有多个满足），则路径会更多。
        # 当前的 select_best_homologs 按 query_gene_id 分组取 top_n，所以
        # CottonA_G001 -> At_G100 (score 500, pid 80)
        # CottonA_G002 -> At_G100 (score 600, pid 85)
        # CottonA_G003 -> At_G102 (score 300, pid 70)
        # 然后 At_G100 -> CottonB_g201 (score 700, pid 90)
        # At_G102 -> CottonB_g204 (score 400, pid 75)
        # 所以最终结果应有3条路径：
        # G001 -> At_G100 -> CottonB_g201
        # G002 -> At_G100 -> CottonB_g201
        # G003 -> At_G102 -> CottonB_g204

        assert len(mapped_results_df) == 3, "映射结果行数不符合预期"
        assert "CottonB_g201" in mapped_results_df["Target_Gene_ID_B"].values
        assert "CottonB_g204" in mapped_results_df["Target_Gene_ID_B"].values

    else:
        print("\n--- 未找到任何映射结果 (独立测试) ---")

    logger.info(_("--- homology_mapper.py 测试结束 ---"))
