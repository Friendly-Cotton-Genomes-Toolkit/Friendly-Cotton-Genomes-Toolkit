# cotton_toolkit/tools/enrichment_analyzer.py
import os
import pandas as pd
from scipy.stats import hypergeom
from statsmodels.stats.multitest import multipletests
from typing import List, Optional, Callable
import logging
import  sqlite3

from .. import PREPROCESSED_DB_NAME
from ..config.models import MainConfig, GenomeSourceItem
from ..utils.file_utils import _sanitize_table_name
from ..utils.gene_utils import normalize_gene_ids, resolve_gene_ids

try:
    from builtins import _
except ImportError:
    _ = lambda text: str(text)

logger = logging.getLogger("cotton_toolkit.tools.enrichment_analyzer")


def _perform_hypergeometric_test(
        study_gene_ids: List[str],
        background_df: pd.DataFrame,
        output_dir: str,
        gene_id_regex: Optional[str] = None,
        alpha: float = 0.05,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Optional[pd.DataFrame]:
    """
    一个通用的、执行超几何检验的核心函数，并支持进度报告。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(5, _("正在准备富集分析背景数据..."))
    # 修改: 直接使用 logger
    logger.info(_("正在准备富集分析背景数据..."))

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
                status, reason = _("匹配成功 (Matched)"), _("在背景中找到，已用于分析")
                annotations = gene_to_terms_map.get(norm_gene, _("在背景中但无注释条目"))
            else:
                status, reason = _("匹配失败 (Failed)"), _("基因ID不在背景注释中")
            report_data.append({'Original_ID': orig_ids, 'Normalized_ID': norm_gene, 'Status': status, 'Reason': reason,
                                'Annotations': annotations})

        failed_norm_ids = norm_to_orig_df[norm_to_orig_df['Normalized_ID'].isnull()]['Original_ID']
        for failed_id in failed_norm_ids:
            report_data.append({'Original_ID': failed_id, 'Normalized_ID': 'N/A', 'Status': '匹配失败 (Failed)',
                                'Reason': '基因ID标准化失败', 'Annotations': 'N/A'})

        report_df = pd.DataFrame(report_data)
        report_path = os.path.join(output_dir, "gene_matching_report.csv")
        report_df.to_csv(report_path, index=False, encoding='utf-8-sig')

        # 修改: 直接使用 logger
        logger.info(_("详细注释报告已保存至: {}").format(os.path.basename(report_path)))
    except Exception as e:
        # 修改: 直接使用 logger
        logger.warning(_("创建基因匹配报告时发生错误: {}").format(e))

    if N == 0:
        # 修改: 直接使用 logger
        logger.warning(_("经过标准化和背景过滤后，没有有效的基因用于富集分析。"))
        progress(100, _("任务终止：无有效基因。"))
        return None

    results = []
    term_counts = background_df.groupby('TermID')[background_gene_id_col].nunique()
    term_id_to_name = background_df.drop_duplicates(subset=['TermID']).set_index('TermID')['Description']

    total_terms = len(term_counts)
    progress(20, _("开始超几何检验..."))

    for i, (term_id, n) in enumerate(term_counts.items()):
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
        # 修改: 直接使用 logger
        logger.warning(_("分析未产生任何结果。"))
        progress(100, _("任务完成：无结果。"))
        return None

    results_df = pd.DataFrame(results)

    progress(85, _("正在进行多重检验校正..."))
    p_values = results_df['p_value'].dropna()
    if p_values.empty:
        # 修改: 直接使用 logger
        logger.warning(_("所有Term的p-value计算失败。"))
        progress(100, _("任务终止：p-value计算失败。"))
        return None

    reject, pvals_corrected, _d, _c = multipletests(p_values, alpha=alpha, method='fdr_bh')
    results_df['FDR'] = pvals_corrected

    progress(95, _("正在保存完整结果..."))
    try:
        full_results_path = os.path.join(output_dir, "enrichment_results_all.csv")
        results_df.sort_values(by='p_value').to_csv(full_results_path, index=False, encoding='utf-8-sig')
        # 修改: 直接使用 logger
        logger.info(_("完整的富集结果清单已保存至: {}").format(os.path.basename(full_results_path)))
    except Exception as e:
        # 修改: 直接使用 logger
        logger.warning(_("保存完整富集结果时出错: {}").format(e))

    if results_df.empty:
        # 修改: 直接使用 logger
        logger.warning(_("富集分析未发现任何结果。"))
        progress(100, _("任务完成：无结果。"))
        return None

    # 修改: 直接使用 logger
    logger.info(_("富集分析完成，共计算出 {} 个Term的结果。").format(len(results_df)))
    progress(100, _("富集分析完成。"))
    return results_df.sort_values(by='FDR')


def run_go_enrichment(
        main_config: MainConfig,
        genome_info: GenomeSourceItem,
        study_gene_ids: List[str],
        output_dir: str,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Optional[pd.DataFrame]:
    """
    【最终数据库版】执行GO富集分析，直接从SQLite数据库读取背景数据。
    """

    progress = progress_callback if progress_callback else lambda p, m: None

    try:
        progress(5, _("正在智能解析输入基因ID..."))
        resolved_gene_ids = resolve_gene_ids(main_config, genome_info.version_id, study_gene_ids)
        logger.info(_("ID智能解析完成，得到 {} 个标准化的ID用于富集分析。").format(len(resolved_gene_ids)))
    except (ValueError, FileNotFoundError) as e:
        logger.error(e)
        progress(100, _("任务终止：基因ID解析失败。"))
        raise e

    progress(10, _("正在从数据库加载GO背景数据..."))

    try:
        project_root = os.path.dirname(main_config.config_file_abs_path_)
        db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)

        # 1. 推断表名
        go_url = getattr(genome_info, "GO_url", None)
        if not go_url:
            raise ValueError(_("基因组 '{}' 配置中缺少 GO_url").format(genome_info.version_id))
        table_name = _sanitize_table_name(os.path.basename(go_url), version_id=genome_info.version_id)

        # 2. 从数据库加载背景数据
        logger.info(_("正在从数据库表 '{}' 加载GO背景注释...").format(table_name))
        with sqlite3.connect(db_path) as conn:
            background_df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)

        # 3. 重命名列以匹配核心统计函数的要求
        rename_map = {}
        if len(background_df.columns) > 0: rename_map[background_df.columns[0]] = 'GeneID'
        if len(background_df.columns) > 1: rename_map[background_df.columns[1]] = 'TermID'
        if len(background_df.columns) > 2: rename_map[background_df.columns[2]] = 'Description'
        if len(background_df.columns) > 3: rename_map[background_df.columns[3]] = 'Namespace'
        background_df.rename(columns=rename_map, inplace=True)

        if 'Namespace' not in background_df.columns:
            logger.warning(_("GO背景文件中未找到 'Namespace' 列，将使用默认值 'GO'。"))
            background_df['Namespace'] = 'GO'

    except (ValueError, sqlite3.OperationalError, pd.io.sql.DatabaseError) as e:
        error_msg = _("加载GO背景数据失败: {}").format(e)
        logger.error(error_msg)
        logger.error(
            _("请确认预处理脚本已成功运行，并且表 '{}' 已在 '{}' 中正确创建。").format(locals().get('table_name', 'N/A'),
                                                                                     PREPROCESSED_DB_NAME))
        progress(100, _("任务终止：加载GO背景数据失败。"))
        raise IOError(error_msg) from e


    # 4. 调用核心统计函数
    return _perform_hypergeometric_test(
        resolved_gene_ids,
        background_df,
        output_dir,
        gene_id_regex=gene_id_regex,
        progress_callback=progress
    )


def run_kegg_enrichment(
        main_config: MainConfig,
        genome_info: GenomeSourceItem,
        study_gene_ids: List[str],
        output_dir: str,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> Optional[pd.DataFrame]:
    """
    执行KEGG富集分析，直接从预处理的SQLite数据库高效加载背景数据。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    try:
        progress(5, _("正在智能解析输入基因ID..."))
        resolved_gene_ids = resolve_gene_ids(main_config, genome_info.version_id, study_gene_ids)
        logger.info(_("ID智能解析完成，得到 {} 个标准化的ID用于富集分析。").format(len(resolved_gene_ids)))
    except (ValueError, FileNotFoundError) as e:
        logger.error(e)
        progress(100, _("任务终止：基因ID解析失败。"))
        raise e

    progress(10, _("正在从数据库加载KEGG背景数据..."))

    try:
        project_root = os.path.dirname(main_config.config_file_abs_path_)
        db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)

        # 1. 根据配置信息推断出数据库中的表名
        #    注意：这里使用的是 'KEGG_pathways_url'
        kegg_url = getattr(genome_info, "KEGG_pathways_url", None)
        if not kegg_url:
            raise ValueError(_("基因组 '{}' 配置中缺少 'KEGG_pathways_url'。").format(genome_info.version_id))

        table_name = _sanitize_table_name(os.path.basename(kegg_url), version_id=genome_info.version_id)

        # 2. 从数据库加载背景数据
        logger.info(_("正在从数据库表 '{}' 加载KEGG背景注释...").format(table_name))
        with sqlite3.connect(db_path) as conn:
            background_df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)

        # 3. 重命名列以匹配核心统计函数的要求
        rename_map = {}
        if len(background_df.columns) > 0: rename_map[background_df.columns[0]] = 'GeneID'
        if len(background_df.columns) > 1: rename_map[background_df.columns[1]] = 'TermID'
        if len(background_df.columns) > 2: rename_map[background_df.columns[2]] = 'Description'
        background_df.rename(columns=rename_map, inplace=True)

        # 为KEGG数据添加默认的Namespace列
        if 'Namespace' not in background_df.columns:
            background_df['Namespace'] = 'KEGG'

    except (ValueError, sqlite3.OperationalError, pd.io.sql.DatabaseError) as e:
        error_msg = _("加载KEGG背景数据失败: {}").format(e)
        logger.error(error_msg)
        logger.error(
            _("请确认预处理脚本已成功运行，并且表 '{}' 已在 '{}' 中正确创建。").format(locals().get('table_name', 'N/A'),
                                                                                     PREPROCESSED_DB_NAME))
        progress(100, _("任务终止：加载KEGG背景数据失败。"))
        raise IOError(error_msg) from e

    # 4. 调用通用的核心统计函数
    return _perform_hypergeometric_test(
        resolved_gene_ids,
        background_df,
        output_dir,
        gene_id_regex=gene_id_regex,
        progress_callback=progress
    )
