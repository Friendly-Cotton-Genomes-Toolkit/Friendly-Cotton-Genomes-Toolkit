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

try:
    from builtins import _
except ImportError:
    _ = lambda text: str(text)


def _perform_hypergeometric_test(
        study_gene_ids: List[str],
        background_df: pd.DataFrame,
        status_callback: Callable,
        output_dir: str,
        gene_id_regex: Optional[str] = None,
        alpha: float = 0.05,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Optional[pd.DataFrame]:
    """
    一个通用的、执行超几何检验的核心函数，并支持进度报告。

    :param study_gene_ids: 用户输入的研究基因列表。
    :param background_df: 一个包含 ['GeneID', 'TermID', 'Description'] 列的DataFrame，代表全基因组的注释背景。
    :param status_callback: 用于记录日志的回调函数。
    :param alpha: 显著性水平阈值。
    :param progress_callback: 用于报告进度的回调函数。
    :return: 包含富集结果的DataFrame。
    """
    log = status_callback
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(5, _("正在准备富集分析背景数据..."))
    log("INFO: 正在准备富集分析背景数据...")

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

    progress(15, _("正在生成基因匹配报告..."))
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

        log(f"INFO: 详细注释报告已保存至: {os.path.basename(report_path)}")
    except Exception as e:
        log(f"WARNING: 创建基因匹配报告时发生错误: {e}")

    if N == 0:
        log("WARNING: 经过标准化和背景过滤后，没有有效的基因用于富集分析。")
        progress(100, _("任务终止：无有效基因。"))
        return None

    results = []
    term_counts = background_df.groupby('TermID')[background_gene_id_col].nunique()
    term_id_to_name = background_df.drop_duplicates(subset=['TermID']).set_index('TermID')['Description']

    total_terms = len(term_counts)
    progress(20, _("开始超几何检验..."))

    for i, (term_id, n) in enumerate(term_counts.items()):
        # 在循环中更新进度 (从20%到80%)
        if i % 50 == 0 or i == total_terms - 1:
            progress(20 + int(((i + 1) / total_terms) * 60), f"{_('正在计算富集项')} {i + 1}/{total_terms}")

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
        log("WARNING: 分析未产生任何结果。")
        progress(100, _("任务完成：无结果。"))
        return None

    results_df = pd.DataFrame(results)

    progress(85, _("正在进行多重检验校正..."))
    p_values = results_df['p_value'].dropna()
    if p_values.empty:
        log("WARNING: 所有Term的p-value计算失败。")
        progress(100, _("任务终止：p-value计算失败。"))
        return None

    reject, pvals_corrected, _d, _c = multipletests(p_values, alpha=alpha, method='fdr_bh')
    results_df['FDR'] = pvals_corrected

    progress(95, _("正在保存完整结果..."))
    try:
        full_results_path = os.path.join(output_dir, "enrichment_results_all.csv")
        results_df.sort_values(by='p_value').to_csv(full_results_path, index=False, encoding='utf-8-sig')
        log(f"INFO: 完整的富集结果清单已保存至: {os.path.basename(full_results_path)}")
    except Exception as e:
        log(f"WARNING: 保存完整富集结果时出错: {e}")

    if results_df.empty:
        log("WARNING: 富集分析未发现任何结果。")
        progress(100, _("任务完成：无结果。"))
        return None

    log(f"SUCCESS: 富集分析完成，共计算出 {len(results_df)} 个Term的结果。")
    progress(100, _("富集分析完成。"))
    return results_df.sort_values(by='FDR')


def run_go_enrichment(
        study_gene_ids: List[str],
        go_annotation_path: str,
        status_callback: Callable,
        output_dir: str,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Optional[pd.DataFrame]:
    """
    执行GO富集分析，并传递进度回调。
    """
    log = status_callback
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("准备GO富集分析..."))
    cache_dir = os.path.join(output_dir, '.cache')
    prepared_go_path = prepare_input_file(go_annotation_path, status_callback, cache_dir)

    if not prepared_go_path:
        log("GO注释文件准备失败，富集分析终止。", "ERROR")
        progress(100, _("任务终止：GO文件准备失败。"))
        return None

    progress(10, _("加载GO背景数据..."))
    log("正在加载处理后的GO注释背景数据...", "INFO")
    try:
        background_df = pd.read_csv(prepared_go_path)
        if not background_df.empty:
            rename_map = {}
            if len(background_df.columns) > 0: rename_map[background_df.columns[0]] = 'GeneID'
            if len(background_df.columns) > 1: rename_map[background_df.columns[1]] = 'TermID'
            if len(background_df.columns) > 2: rename_map[background_df.columns[2]] = 'Description'
            if len(background_df.columns) > 3: rename_map[background_df.columns[3]] = 'Namespace'
            background_df.rename(columns=rename_map, inplace=True)
            if 'Namespace' not in background_df.columns:
                background_df['Namespace'] = 'GO'
    except Exception as e:
        log(f"读取或重命名GO背景文件失败: {e}", "ERROR")
        progress(100, _("任务终止：读取GO背景失败。"))
        return None

    return _perform_hypergeometric_test(
        study_gene_ids,
        background_df,
        status_callback,
        output_dir,
        gene_id_regex=gene_id_regex,
        progress_callback=progress  # 将回调函数传递下去
    )


def run_kegg_enrichment(
        study_gene_ids: List[str],
        kegg_pathways_path: str,
        output_dir: str,
        status_callback: Optional[Callable] = print,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        **kwargs
) -> Optional[pd.DataFrame]:
    """
    执行KEGG富集分析, 与GO分析流程统一，并传递进度回调。
    """
    log = status_callback
    progress = progress_callback if progress_callback else lambda p, m: None

    try:
        progress(0, _("准备KEGG富集分析..."))
        cache_dir = os.path.join(output_dir, '.cache')
        prepared_kegg_path = prepare_input_file(kegg_pathways_path, log, cache_dir)

        if not prepared_kegg_path:
            raise ValueError("KEGG注释文件准备失败。")

        progress(10, _("加载KEGG背景数据..."))
        background_df = pd.read_csv(prepared_kegg_path)
        if background_df is None or background_df.empty:
            raise ValueError("加载的KEGG注释文件为空或格式不正确。")

        rename_map = {}
        if len(background_df.columns) > 0: rename_map[background_df.columns[0]] = 'GeneID'
        if len(background_df.columns) > 1: rename_map[background_df.columns[1]] = 'TermID'
        if len(background_df.columns) > 2: rename_map[background_df.columns[2]] = 'Description'
        background_df.rename(columns=rename_map, inplace=True)

        if 'Namespace' not in background_df.columns:
            background_df['Namespace'] = 'KEGG'

    except Exception as e:
        log(f"ERROR: 准备KEGG背景文件时出错: {e}")
        progress(100, _("任务终止：准备KEGG背景失败。"))
        return None

    return _perform_hypergeometric_test(
        study_gene_ids,
        background_df,
        log,
        output_dir,
        gene_id_regex=gene_id_regex,
        progress_callback=progress  # 将回调函数传递下去
    )