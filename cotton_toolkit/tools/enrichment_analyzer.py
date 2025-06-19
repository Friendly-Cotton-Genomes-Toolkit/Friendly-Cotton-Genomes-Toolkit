# cotton_toolkit/tools/enrichment_analyzer.py
import os
import pandas as pd
from scipy.stats import hypergeom
from statsmodels.stats.multitest import multipletests
from typing import List, Optional, Callable

from .data_loader import load_annotation_data
from ..core.convertXlsx2csv import convert_excel_to_standard_csv
from ..utils.file_utils import prepare_input_file
from ..utils.gene_utils import normalize_gene_ids


def _perform_hypergeometric_test(
    study_gene_ids: List[str],
    background_df: pd.DataFrame,
    status_callback: Callable,
    output_dir: str,
    gene_id_regex: Optional[str] = None,
    alpha: float = 0.05
) -> Optional[pd.DataFrame]:
    """
    一个通用的、执行超几何检验的核心函数。
    适用于GO和KEGG。

    :param study_gene_ids: 用户输入的研究基因列表。
    :param background_df: 一个包含 ['GeneID', 'TermID', 'Description'] 列的DataFrame，代表全基因组的注释背景。
    :param status_callback: 用于记录日志的回调函数。
    :param alpha: 显著性水平阈值。
    :return: 包含富集结果的DataFrame。
    """
    status_callback("INFO: 正在准备富集分析背景数据...")

    original_input_set = set(study_gene_ids)
    background_gene_id_col = 'GeneID'
    study_ids_normalized = pd.Series(study_gene_ids, name="norm")
    if gene_id_regex:
        background_df['GeneID_norm'] = normalize_gene_ids(background_df['GeneID'], gene_id_regex)
        study_ids_series = pd.Series(study_gene_ids, name="orig")
        study_ids_normalized = normalize_gene_ids(study_ids_series, gene_id_regex)
        background_df.dropna(subset=['GeneID_norm'], inplace=True)
        background_gene_id_col = 'GeneID_norm'

    study_gene_ids_set = set(study_ids_normalized.dropna())
    background_genes_set = set(background_df[background_gene_id_col].unique())

    study_genes_in_pop = study_gene_ids_set.intersection(background_genes_set)
    M = len(background_genes_set)
    N = len(study_genes_in_pop)

    try:
        background_df['Description'] = background_df['Description'].astype(str)
        gene_to_terms_map = background_df.groupby(background_gene_id_col).apply(
            lambda df_group: '; '.join(df_group['TermID'] + ' (' + df_group['Description'] + ')')
        ).to_dict()

        report_data = []
        norm_to_orig_df = pd.DataFrame(
            {'Original_ID': study_gene_ids, 'Normalized_ID': study_ids_normalized}).drop_duplicates()
        all_normalized_genes = norm_to_orig_df['Normalized_ID'].dropna().unique()

        for norm_gene in all_normalized_genes:
            orig_ids = ";".join(norm_to_orig_df[norm_to_orig_df['Normalized_ID'] == norm_gene]['Original_ID'])
            annotations = "N/A"
            if norm_gene in study_genes_in_pop:
                status, reason = "匹配成功 (Matched)", "在背景中找到，已用于分析"
                annotations = gene_to_terms_map.get(norm_gene, "在背景中但无注释条目")
            else:
                status, reason = "匹配失败 (Failed)", "基因ID不在背景注释中"
            report_data.append({'Original_ID': orig_ids, 'Normalized_ID': norm_gene, 'Status': status, 'Reason': reason,
                                'Annotations': annotations})

        failed_norm_ids = norm_to_orig_df[norm_to_orig_df['Normalized_ID'].isnull()]['Original_ID']
        for failed_id in failed_norm_ids:
            report_data.append({'Original_ID': failed_id, 'Normalized_ID': 'N/A', 'Status': '匹配失败 (Failed)',
                                'Reason': '基因ID标准化失败', 'Annotations': 'N/A'})

        report_df = pd.DataFrame(report_data)
        report_path = os.path.join(output_dir, "gene_matching_report.csv")
        report_df.to_csv(report_path, index=False, encoding='utf-8-sig')

        status_callback(f"INFO: 详细注释报告已保存至: {os.path.basename(report_path)}")
    except Exception as e:
        status_callback(f"WARNING: 创建基因匹配报告时发生错误: {e}")

    if N == 0:
        return None

    results = []
    term_counts = background_df.groupby('TermID')[background_gene_id_col].nunique()
    term_id_to_name = background_df.drop_duplicates(subset=['TermID']).set_index('TermID')['Description']

    for term_id, n in term_counts.items():
        genes_in_term = set(background_df[background_df['TermID'] == term_id][background_gene_id_col])
        k_genes_norm = study_genes_in_pop.intersection(genes_in_term)
        k = len(k_genes_norm)

        if k > 0:
            p_value = hypergeom.sf(k - 1, M, n, N)
            rich_factor = k / n if n > 0 else 0
            results.append({'TermID': term_id, 'Description': term_id_to_name.get(term_id, ''),
                            'Namespace': background_df.loc[background_df['TermID'] == term_id, 'Namespace'].iloc[0],
                            'p_value': p_value, 'GeneRatio': f"{k}/{N}", 'BgRatio': f"{n}/{M}",
                            'Genes': ";".join(sorted(list(k_genes_norm))), 'GeneNumber': k, 'RichFactor': rich_factor})

    if not results:
        status_callback("WARNING: 分析未产生任何结果。")
        return None

    results_df = pd.DataFrame(results)

    # 5. 多重检验校正
    p_values = results_df['p_value'].dropna()
    if p_values.empty:
        status_callback("WARNING: 所有Term的p-value计算失败。")
        return None

    reject, pvals_corrected, _, _ = multipletests(p_values, alpha=alpha, method='fdr_bh')
    results_df['FDR'] = pvals_corrected

    # --- 【核心修改】---
    # 不再使用FDR < 0.05进行预过滤，而是返回所有结果
    # 之前被删除的代码: final_results_df = results_df[results_df['FDR'] <= alpha].copy()

    # 保存完整的、未经筛选的结果清单（这个功能保持不变，依然很有用）
    try:
        full_results_path = os.path.join(output_dir, "enrichment_results_all.csv")
        results_df.sort_values(by='p_value').to_csv(full_results_path, index=False, encoding='utf-8-sig')
        status_callback(f"INFO: 完整的富集结果清单已保存至: {os.path.basename(full_results_path)}")
    except Exception as e:
        status_callback(f"WARNING: 保存完整富集结果时出错: {e}")

    if results_df.empty:
        status_callback("WARNING: 富集分析未发现任何结果。")
        return None

    status_callback(f"SUCCESS: 富集分析完成，共计算出 {len(results_df)} 个Term的结果。")
    # 直接返回按FDR排好序的完整结果，交由绘图函数去取Top N
    return results_df.sort_values(by='FDR')


def run_go_enrichment(
        study_gene_ids: List[str],
        go_annotation_path: str,  # 这是用户传入的原始文件路径 (可以是xlsx, txt, csv)
        status_callback: Callable,
        output_dir: str,
        gene_id_regex: Optional[str] = None
) -> Optional[pd.DataFrame]:
    # --- 核心修改点 ---
    # 1. 定义一个用于存放转换后文件的缓存目录
    cache_dir = os.path.join(output_dir, '.cache')

    # 2. 调用通用的文件准备函数
    prepared_go_path = prepare_input_file(go_annotation_path, status_callback, cache_dir)

    if not prepared_go_path:
        status_callback("GO注释文件准备失败，富集分析终止。", "ERROR")
        return None
    # --- 修改结束 ---

    # 后续代码现在可以安全地假设 prepared_go_path 是一个标准格式的CSV文件
    status_callback("正在加载处理后的GO注释背景数据...", "INFO")
    try:
        # 直接读取已标准化的CSV文件
        background_df = pd.read_csv(prepared_go_path)
    except Exception as e:
        status_callback(f"读取标准化注释文件失败: {e}", "ERROR")
        return None

    # 调用时参数保持不变，因为现在定义和调用已经匹配
    return _perform_hypergeometric_test(study_gene_ids, background_df, status_callback, output_dir, gene_id_regex=gene_id_regex)


def run_kegg_enrichment(study_gene_ids: List[str], kegg_pathways_path: str, output_dir: str, status_callback: Optional[Callable] = print, gene_id_regex: Optional[str] = None, **kwargs) -> Optional[pd.DataFrame]:
    try:
        annotation_file_to_load = _prepare_annotation_file(kegg_pathways_path, status_callback)
        background_df = load_annotation_data(annotation_file_to_load, status_callback)
        if background_df is None or background_df.empty:
            raise ValueError("加载的KEGG注释文件为空或格式不正确。")
    except Exception as e:
        status_callback(f"ERROR: 准备KEGG背景文件时出错: {e}")
        return None
    # 调用时参数保持不变，因为现在定义和调用已经匹配
    return _perform_hypergeometric_test(study_gene_ids, background_df, status_callback, output_dir, gene_id_regex=gene_id_regex)
def _prepare_annotation_file(
        original_path: str,
        status_callback: Callable
) -> str:
    """
    【智能缓存版】一个通用的注释文件预处理和缓存函数。
    """
    if not str(original_path).lower().endswith(('.xlsx', '.xlsx.gz')):
        return original_path

    source_dir = os.path.dirname(original_path)
    base_name = os.path.basename(original_path)
    if base_name.lower().endswith('.xlsx.gz'):
        cache_base_name = base_name[:-8]
    else:  # .xlsx
        cache_base_name = base_name[:-5]

    cached_csv_path = os.path.join(source_dir, f"{cache_base_name}_standardized.csv")

    try:
        if os.path.exists(cached_csv_path):
            original_mtime = os.path.getmtime(original_path)
            cached_mtime = os.path.getmtime(cached_csv_path)
            if cached_mtime >= original_mtime:
                status_callback(f"INFO: 发现有效的缓存文件，将直接使用: {os.path.basename(cached_csv_path)}")
                return cached_csv_path
            else:
                status_callback(f"INFO: 缓存文件已过期，将重新生成...")
    except OSError as e:
        status_callback(f"WARNING: 检查缓存时出错: {e}")

    success = convert_excel_to_standard_csv(original_path, cached_csv_path, status_callback)
    if success:
        return cached_csv_path
    else:
        raise IOError(f"Failed to convert Excel file: {original_path}")


