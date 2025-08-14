# cotton_toolkit/pipelines.py

import gzip
import io
import logging
import os
import re
import subprocess
import threading
import time
import traceback
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import asdict
from typing import List, Dict, Any, Optional, Callable, Tuple

import numpy as np
import pandas as pd

from .config.loader import get_genome_data_sources, get_local_downloaded_file_path
from .config.models import (
    MainConfig, HomologySelectionCriteria, GenomeSourceItem
)
from .core.ai_wrapper import AIWrapper
from .core.convertXlsx2csv import convert_excel_to_standard_csv
from .core.downloader import download_genome_data
from .core.file_normalizer import normalize_to_csv
from .core.gff_parser import get_genes_in_region, extract_gene_details, create_gff_database, get_gene_info_by_ids, \
    _apply_regex_to_id
from .core.homology_mapper import map_genes_via_bridge
from .tools.annotator import Annotator
from .tools.batch_ai_processor import process_single_csv_file
from .tools.enrichment_analyzer import run_go_enrichment, run_kegg_enrichment
from .tools.visualizer import plot_enrichment_bubble, plot_enrichment_bar, plot_enrichment_upset, plot_enrichment_cnet
from .utils.gene_utils import map_transcripts_to_genes

import tempfile
from Bio import SeqIO
from Bio.Blast.Applications import (NcbiblastnCommandline, NcbiblastpCommandline,
                                    NcbiblastxCommandline, NcbitblastnCommandline)
from Bio.SearchIO import parse as blast_parse

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines")


def _find_header_row(sheet_df: pd.DataFrame, keywords: List[str]) -> Optional[int]:
    for i in range(min(3, len(sheet_df))):
        row_values_str = ' '.join([str(v).lower() for v in sheet_df.iloc[i].values])
        if any(keyword.lower() in row_values_str for keyword in keywords):
            return i
    return None


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
                f.write(f"# 源基因组的位点（即用户输入的位点）: {source_locus_str}\n")
                f.write(f"# 目标基因组的位点（即转换后的大体的位点）: {target_assembly_id}\n")
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


def create_homology_df(file_path: str, progress_callback: Optional[Callable] = None,
                       cancel_event: Optional[threading.Event] = None) -> pd.DataFrame:
    progress = progress_callback if progress_callback else lambda p, m: None
    if not os.path.exists(file_path):
        raise FileNotFoundError(_("同源文件未找到: {}").format(file_path))

    lowered_path = file_path.lower()
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']

    progress(0, _("正在打开文件: {}...").format(os.path.basename(file_path)))
    with open(file_path, 'rb') as f_raw:
        is_gz = lowered_path.endswith('.gz')
        file_obj = gzip.open(f_raw, 'rb') if is_gz else f_raw
        try:
            if cancel_event and cancel_event.is_set(): return pd.DataFrame()
            progress(20, _("正在解析文件结构..."))
            if lowered_path.endswith(('.xlsx', '.xlsx.gz', '.xls', '.xls.gz')):
                xls = pd.ExcelFile(file_obj)
                all_sheets_data = []
                num_sheets = len(xls.sheet_names)
                for i, sheet_name in enumerate(xls.sheet_names):
                    if cancel_event and cancel_event.is_set():
                        logger.info("Cancellation requested during Excel sheet processing.")
                        return pd.DataFrame()
                    progress(20 + int(60 * (i / num_sheets)), _("正在处理工作表: {}...").format(sheet_name))
                    preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
                    header_row_index = _find_header_row(preview_df, header_keywords)
                    if header_row_index is not None:
                        sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                        sheet_df.dropna(how='all', inplace=True)
                        all_sheets_data.append(sheet_df)
                if not all_sheets_data:
                    raise ValueError(_("在Excel文件的任何工作表中都未能找到有效的表头或数据。"))
                if cancel_event and cancel_event.is_set(): return pd.DataFrame()
                progress(80, _("正在合并所有工作表..."))
                return pd.concat(all_sheets_data, ignore_index=True)
            else:
                if cancel_event and cancel_event.is_set(): return pd.DataFrame()
                progress(50, _("正在读取文本数据..."))
                return pd.read_csv(file_obj, sep=r'\s+', engine='python', comment='#')
        except Exception as e:
            logger.error(_("读取同源文件 '{}' 时出错: {}").format(file_path, e))
            raise
        finally:
            progress(100, _("文件加载完成。"))
            if is_gz:
                file_obj.close()


def _update_config_from_overrides(config_obj: Any, overrides: Optional[Dict[str, Any]]):
    if not overrides:
        return
    for key, value in overrides.items():
        if value is not None:
            if hasattr(config_obj, key):
                setattr(config_obj, key, value)
            else:
                logger.warning(_("配置覆盖警告：在对象 {} 中找不到键 '{}'。").format(type(config_obj).__name__, key))


def run_homology_mapping(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: Optional[List[str]],
        region: Optional[Tuple[str, int, int]],
        output_csv_path: Optional[str],
        criteria_overrides: Optional[Dict[str, Any]],
        calculate_target_locus: bool = False,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> Any:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            # 修改: 直接使用 logger
            logger.info(_("任务被取消。"))
            return True
        return False

    try:
        progress(5, _("步骤 1: 加载配置..."))
        if check_cancel(): return None
        # 修改: get_genome_data_sources 不再需要 logger_func 参数
        genome_sources = get_genome_data_sources(config)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)
        bridge_species_name = "Arabidopsis_thaliana"
        bridge_genome_info = genome_sources.get(bridge_species_name)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            # 修改: 直接使用 logger
            logger.error(_("错误: 基因组名称无效。"))
            return None if not output_csv_path else pd.DataFrame()

        source_gene_ids = gene_ids
        if region:
            progress(15, _("步骤 2: 从染色体区域提取基因ID..."))
            if check_cancel(): return None

            gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
            gff_db_cache_dir = os.path.join(os.path.dirname(config.config_file_abs_path_),
                                            config.locus_conversion.gff_db_storage_dir)
            # 修改: get_genes_in_region 不再需要 status_callback
            genes_in_region_list = get_genes_in_region(assembly_id=source_assembly_id, gff_filepath=gff_path,
                                                       db_storage_dir=gff_db_cache_dir, region=region,
                                                       force_db_creation=False)
            if not genes_in_region_list:
                # 修改: 直接使用 logger
                logger.warning(_("在区域 {} 中未找到任何基因。").format(region))
                return [] if not output_csv_path else pd.DataFrame()
            source_gene_ids = [gene['gene_id'] for gene in genes_in_region_list]

        if not source_gene_ids:
            # 修改: 直接使用 logger
            logger.error(_("错误: 基因列表为空。"))
            return [] if not output_csv_path else pd.DataFrame()

        is_map_to_bridge = (target_assembly_id == bridge_species_name)
        is_map_from_bridge = (source_assembly_id == bridge_species_name)
        mapped_df, failed_genes = None, []

        if is_map_to_bridge and not is_map_from_bridge:
            logger.info(_("[简易模式] 执行 源 -> 桥梁 直接查找..."))
            progress(30, _("正在加载同源文件..."))
            if check_cancel(): return None
            homology_file_path = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
            if not homology_file_path or not os.path.exists(homology_file_path):
                logger.error(_(f"错误: 未找到 {source_assembly_id} 的同源文件。"))
                return None

            homology_df = create_homology_df(homology_file_path, lambda p, m: progress(30 + int(p * 0.4), m),
                                             cancel_event)
            if check_cancel() or homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return None

            query_col_name = 'Query' if 'Query' in homology_df.columns else homology_df.columns[0]
            match_col_name = next((col for col in homology_df.columns if 'match' in col.lower()),
                                  homology_df.columns[1])
            logger.info(_(f"已自动识别表头: 查询列='{query_col_name}', 匹配列='{match_col_name}'"))

            progress(70, _("正在标准化ID并查找匹配..."))
            if check_cancel(): return None

            search_col = query_col_name
            search_regex = source_genome_info.gene_id_regex
            homology_df[search_col] = homology_df[search_col].astype(str).apply(
                lambda x: _apply_regex_to_id(x, search_regex))
            processed_source_ids = {_apply_regex_to_id(gid, search_regex) for gid in source_gene_ids}

            results_df = homology_df[homology_df[search_col].isin(processed_source_ids)].copy()

            criteria = HomologySelectionCriteria()
            _update_config_from_overrides(criteria, criteria_overrides)
            if criteria.evalue_threshold is not None and 'Exp' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['Exp'], errors='coerce') <= criteria.evalue_threshold]
            if criteria.pid_threshold is not None and 'PID' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['PID'], errors='coerce') >= criteria.pid_threshold]
            if criteria.score_threshold is not None and 'Score' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['Score'], errors='coerce') >= criteria.score_threshold]

            results_df = results_df.sort_values(by='Score', ascending=False)
            if criteria.top_n and criteria.top_n > 0: results_df = results_df.groupby(search_col).head(criteria.top_n)

            mapped_df = results_df.rename(columns={query_col_name: 'Source_Gene_ID', match_col_name: 'Target_Gene_ID'})
            found_genes = set(mapped_df['Source_Gene_ID'])
            failed_genes = [gid for gid in source_gene_ids if gid not in found_genes]

        elif is_map_from_bridge and not is_map_to_bridge:
            logger.info(_("[简易模式] 执行 桥梁 -> 目标 直接查找..."))
            progress(30, _("正在加载同源文件..."))
            if check_cancel(): return None

            homology_file_path = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')
            if not homology_file_path or not os.path.exists(homology_file_path):
                logger.error(_(f"错误: 未找到 {target_assembly_id} 的同源文件。"))
                return None

            homology_df = create_homology_df(homology_file_path, lambda p, m: progress(30 + int(p * 0.4), m),
                                             cancel_event)
            if check_cancel() or homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return None

            query_col_name = 'Query' if 'Query' in homology_df.columns else homology_df.columns[0]
            match_col_name = next((col for col in homology_df.columns if 'match' in col.lower()),
                                  homology_df.columns[1])
            logger.info(_(f"已自动识别表头: 查询列='{query_col_name}', 匹配列='{match_col_name}'"))

            progress(70, _("正在标准化ID并查找匹配..."))
            if check_cancel(): return None

            search_col = match_col_name
            search_regex = bridge_genome_info.gene_id_regex
            homology_df[search_col] = homology_df[search_col].astype(str).apply(
                lambda x: _apply_regex_to_id(x, search_regex))
            processed_source_ids = {_apply_regex_to_id(gid, search_regex) for gid in source_gene_ids}

            results_df = homology_df[homology_df[search_col].isin(processed_source_ids)].copy()

            criteria = HomologySelectionCriteria();
            _update_config_from_overrides(criteria, criteria_overrides)
            if criteria.evalue_threshold is not None and 'Exp' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['Exp'], errors='coerce') <= criteria.evalue_threshold]
            if criteria.pid_threshold is not None and 'PID' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['PID'], errors='coerce') >= criteria.pid_threshold]
            if criteria.score_threshold is not None and 'Score' in results_df.columns: results_df = results_df[
                pd.to_numeric(results_df['Score'], errors='coerce') >= criteria.score_threshold]

            results_df = results_df.sort_values(by='Score', ascending=False)
            if criteria.top_n and criteria.top_n > 0: results_df = results_df.groupby(search_col).head(criteria.top_n)

            mapped_df = results_df.rename(columns={match_col_name: 'Source_Gene_ID', query_col_name: 'Target_Gene_ID'})
            found_genes = set(mapped_df['Source_Gene_ID'])
            failed_genes = [gid for gid in source_gene_ids if gid not in found_genes]

        else:
            logger.info(_("[标准模式] 调用核心函数执行三步映射..."))
            if check_cancel(): return None
            s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
            b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

            source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                              lambda p, m: progress(30 + int(p * 0.3), m), cancel_event)
            if check_cancel() or source_to_bridge_homology_df.empty: logger.info(
                _("任务被取消或文件读取失败。")); return None

            bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                              lambda p, m: progress(60 + int(p * 0.2), m), cancel_event)
            if check_cancel() or bridge_to_target_homology_df.empty: logger.info(
                _("任务被取消或文件读取失败。")); return None

            s2b_criteria = HomologySelectionCriteria()
            _update_config_from_overrides(s2b_criteria, criteria_overrides)
            b2t_criteria = HomologySelectionCriteria()
            _update_config_from_overrides(b2t_criteria, criteria_overrides)

            if check_cancel(): logger.info(_("任务被取消。")); return None

            # 修改: map_genes_via_bridge 不再需要 status_callback
            mapped_df, failed_genes = map_genes_via_bridge(
                source_gene_ids=source_gene_ids, source_assembly_name=source_assembly_id,
                target_assembly_name=target_assembly_id,
                bridge_species_name=bridge_species_name, source_to_bridge_homology_df=source_to_bridge_homology_df,
                bridge_to_target_homology_df=bridge_to_target_homology_df,
                selection_criteria_s_to_b=s2b_criteria.model_dump(),
                selection_criteria_b_to_t=b2t_criteria.model_dump(),
                homology_columns={"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"},
                source_genome_info=source_genome_info, target_genome_info=target_genome_info,
                bridge_genome_info=bridge_genome_info,
                progress_callback=lambda p, m: progress(80 + int(p * 0.1), m),
                cancel_event=cancel_event
            )

        if check_cancel(): logger.info(_("任务被取消。")); return None

        if output_csv_path:
            logger.info(_("步骤 5: 保存映射结果..."))
            if check_cancel(): return None
            progress(95, _("正在保存映射结果..."))
            # 修改: save_mapping_results 不再需要 status_callback
            save_mapping_results(
                output_path=output_csv_path,
                mapped_df=mapped_df,
                failed_genes=failed_genes,
                source_assembly_id=source_assembly_id,
                target_assembly_id=target_assembly_id,
                source_gene_ids_count=len(source_gene_ids),
                region=region
            )
            return mapped_df
        else:
            logger.info(_("步骤 5: 提取目标基因ID..."))
            if check_cancel(): return None
            progress(95, _("正在提取目标基因ID..."))

            if mapped_df is not None and not mapped_df.empty and 'Target_Gene_ID' in mapped_df.columns:
                target_ids = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
                target_regex = target_genome_info.gene_id_regex
                if target_regex:
                    logger.debug(_("正在使用目标基因组的正则表达式 '{}' 清理ID...").format(target_regex))
                    cleaned_ids = [_apply_regex_to_id(gid, target_regex) for gid in target_ids]
                    final_ids = sorted(list(set(cleaned_ids)))
                else:
                    final_ids = sorted(target_ids)

                logger.info(_("成功提取到 {} 个唯一的同源目标基因。").format(len(final_ids)))
                return final_ids
            else:
                logger.info(_("未找到任何同源目标基因。"))
                return []

    except Exception as e:
        logger.exception(_("流水线执行过程中发生意外错误: {}").format(e))
        return None


def run_locus_conversion(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        region: Tuple[str, int, int],
        output_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        criteria_overrides: Optional[Dict[str, Any]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[str]:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已取消。"))
            return True
        return False

    try:
        progress(5, _("流程开始，正在加载基因组配置..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        logger.info(_("步骤1: 加载配置..."))
        # 修改: get_genome_data_sources 不再需要 logger_func
        genome_sources = get_genome_data_sources(config)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)

        bridge_species_name = "Arabidopsis thaliana"
        bridge_genome_info = genome_sources.get(bridge_species_name)
        if not bridge_genome_info:
            bridge_genome_info = genome_sources.get(bridge_species_name.replace(' ', '_'))

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            logger.error(_("错误: 无法为 {}, {} 或 {} 找到配置。").format(source_assembly_id, target_assembly_id,
                                                                         bridge_species_name))
            progress(100, _("任务终止：基因组配置错误。"))
            return None

        progress(15, _("正在从GFF文件中提取基因..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        gff_db_cache_dir = config.locus_conversion.gff_db_storage_dir
        os.makedirs(gff_db_cache_dir, exist_ok=True)

        source_gene_list = get_genes_in_region(
            assembly_id=source_assembly_id, gff_filepath=gff_path,
            db_storage_dir=gff_db_cache_dir, region=region,
            gene_id_regex=source_genome_info.gene_id_regex,
            progress_callback=lambda p, m: progress(15 + int(p * 0.1), _("提取基因: {}").format(m))
        )
        if not source_gene_list:
            logger.warning(_("在区域 {} 中未找到任何基因。").format(region))
            progress(100, _("任务终止：区域内无基因。"))
            return _("在指定区域未找到任何基因。")
        source_gene_ids = [gene['gene_id'] for gene in source_gene_list]

        progress(30, _("正在加载同源文件..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not all([s_to_b_homology_file, b_to_t_homology_file, os.path.exists(s_to_b_homology_file),
                    os.path.exists(b_to_t_homology_file)]):
            logger.error(_("错误: 缺少必要的同源文件。请先为相关基因组下载数据。"))
            progress(100, _("任务终止：缺少同源文件。"))
            return None

        progress(40, _("正在解析源到桥梁的同源文件..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(40 + int(p * 0.2),
                                                                                                  _("解析同源文件 (S->B): {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or source_to_bridge_homology_df.empty: logger.info(
            _("任务被取消或文件读取失败。")); return None

        progress(60, _("正在解析桥梁到目标的同源文件..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(60 + int(p * 0.1),
                                                                                                  _("解析同源文件 (B->T): {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or bridge_to_target_homology_df.empty: logger.info(
            _("任务被取消或文件读取失败。")); return None

        homology_columns = {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"}
        if homology_columns['query'] not in source_to_bridge_homology_df.columns:
            raise ValueError(_("配置错误: 在同源文件中找不到查询列 '{}'。可用列: {}").format(homology_columns['query'],
                                                                                            source_to_bridge_homology_df.columns.tolist()))

        selection_criteria_s_to_b = {"top_n": 1, "evalue_threshold": 1e-10}
        selection_criteria_b_to_t = {"top_n": 1, "evalue_threshold": 1e-10}

        progress(75, _("正在执行核心同源映射..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        # 修改: map_genes_via_bridge 不再需要 status_callback
        mapped_df, failed_genes = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=bridge_species_name,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b,
            selection_criteria_b_to_t=selection_criteria_b_to_t,
            homology_columns=homology_columns,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            progress_callback=lambda p, m: progress(75 + int(p * 0.15), _("基因映射: {}").format(m)),
            cancel_event=kwargs.get('cancel_event')
        )

        if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
            logger.info(_("任务在同源映射阶段被用户取消。"))
            progress(100, _("任务已取消。"))
            return None

        progress(95, _("映射完成，正在整理并保存结果..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        output_dir = os.path.dirname(output_path)
        if output_dir: os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(_("# Source Locus: {} | {}:{}-{}\n").format(source_assembly_id, region[0], region[1], region[2]))
            f.write(_("# Target Assembly: {}\n").format(target_assembly_id))
            f.write(_("# Failed to map {} genes: {}\n").format(len(failed_genes),
                                                               ','.join(failed_genes) if failed_genes else 'None'))
            f.write(_("#\n# --- Detailed Mapping Results ---\n"))
            if mapped_df is not None and not mapped_df.empty:
                mapped_df.to_csv(f, index=False, lineterminator='\n')
            else:
                f.write(_("# No successful homologous matches found.\n"))

        progress(100, _("全部完成！"))
        success_message = _("位点转换结果已成功保存到:\n{}").format(os.path.abspath(output_path))
        logger.info(success_message)
        return success_message

    except Exception as e:
        logger.error(_("位点转换流程出错: {}").format(e))
        logger.debug(traceback.format_exc())
        progress(100, _("任务因错误而终止。"))
        return None


def run_ai_task(
        config: MainConfig,
        input_file: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str],
        cli_overrides: Optional[Dict[str, Any]],
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        output_file: Optional[str] = None
):
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已被用户取消。"));
            return True
        return False

    progress(0, _("AI任务流程开始..."))
    logger.info(_("AI任务流程开始..."))
    if check_cancel(): return

    progress(5, _("正在解析AI服务配置..."))
    if check_cancel(): return

    ai_cfg = config.ai_services
    provider_name = cli_overrides.get('ai_provider') if cli_overrides else ai_cfg.default_provider
    model_name = cli_overrides.get('ai_model') if cli_overrides else None
    provider_cfg_obj = ai_cfg.providers.get(provider_name)
    if not provider_cfg_obj:
        logger.error(_("错误: 在配置中未找到AI服务商 '{}' 的设置。").format(provider_name));
        return
    if not model_name: model_name = provider_cfg_obj.model
    api_key = provider_cfg_obj.api_key
    base_url = provider_cfg_obj.base_url
    if not api_key or "YOUR_API_KEY" in api_key:
        logger.error(_("错误: 请在配置文件中为服务商 '{}' 设置一个有效的API Key。").format(provider_name));
        return

    proxies_to_use = config.proxies.model_dump(
        exclude_none=True) if ai_cfg.use_proxy_for_ai and config.proxies else None

    progress(10, _("正在初始化AI客户端..."))
    if check_cancel(): return

    logger.info(_("正在初始化AI客户端... 服务商: {}, 模型: {}").format(provider_name, model_name))
    ai_client = AIWrapper(provider=provider_name, api_key=api_key, model=model_name, base_url=base_url,
                          proxies=proxies_to_use, max_workers=config.batch_ai_processor.max_workers)

    prompt_to_use = custom_prompt_template or (
        config.ai_prompts.translation_prompt if task_type == 'translate' else config.ai_prompts.analysis_prompt)

    final_output_path = None
    if output_file is not None:
        output_directory = os.path.dirname(output_file)
        final_output_path = output_file
        logger.info(_("将在原文件上修改: {}").format(output_file))
    else:
        output_directory = os.path.dirname(input_file)
        logger.info(_("将创建新文件并保存于源文件目录: {}").format(output_directory))

    os.makedirs(output_directory, exist_ok=True)

    progress(15, _("正在处理CSV文件并调用AI服务..."))
    if check_cancel(): return

    # 修改: process_single_csv_file 不再需要 status_callback
    process_single_csv_file(
        client=ai_client,
        input_csv_path=input_file,
        output_csv_directory=output_directory,
        source_column_name=source_column,
        new_column_name=new_column,
        user_prompt_template=prompt_to_use,
        task_identifier=f"{os.path.basename(input_file)}_{task_type}",
        max_row_workers=config.batch_ai_processor.max_workers,
        progress_callback=lambda p, m: progress(15 + int(p * 0.8), _("AI处理: {}").format(m)),
        cancel_event=cancel_event,
        output_csv_path=final_output_path
    )

    if cancel_event and cancel_event.is_set():
        return

    progress(100, _("任务完成。"))
    logger.info(_("AI任务流程成功完成。"))


def run_functional_annotation(
        config: MainConfig,
        source_genome: str,
        target_genome: str,
        bridge_species: str,
        annotation_types: List[str],
        output_dir: Optional[str] = None,
        output_path: Optional[str] = None,
        gene_list_path: Optional[str] = None,
        gene_ids: Optional[List[str]] = None,
        custom_db_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> None:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务被取消。"))
            return True
        return False

    progress(0, _("准备输入基因列表..."))
    if check_cancel(): return

    source_gene_ids = []
    if gene_ids:
        source_gene_ids = list(set(gene_ids))
        logger.info(_("从参数直接获取了 {} 个唯一基因ID。").format(len(source_gene_ids)))
    elif gene_list_path and os.path.exists(gene_list_path):
        try:
            progress(5, _("正在从文件读取基因列表..."))
            if check_cancel(): return
            logger.info(_("正在从文件 '{}' 中读取基因列表...").format(os.path.basename(gene_list_path)))
            study_genes_df = pd.read_csv(gene_list_path)
            source_gene_ids = study_genes_df.iloc[:, 0].dropna().unique().tolist()
            logger.info(_("从文件中读取了 {} 个唯一基因ID。").format(len(source_gene_ids)))
        except Exception as e:
            logger.error(_("读取基因列表文件时出错: {}").format(e))
            progress(100, _("任务终止：读取基因列表失败。"))
            return
    else:
        logger.error(_("错误: 必须提供 'gene_ids' 或有效的 'gene_list_path' 参数之一。"))
        progress(100, _("任务终止：缺少基因输入。"))
        return

    if not source_gene_ids:
        logger.error(_("输入的基因列表为空，流程终止。"))
        progress(100, _("任务终止：基因列表为空。"))
        return

    genes_to_annotate = source_gene_ids
    original_to_target_map_df = pd.DataFrame({'Source_Gene_ID': source_gene_ids})

    progress(10, _("检查是否需要同源映射..."))
    if check_cancel(): return

    if source_genome != target_genome:
        logger.info(_("源基因组 ({}) 与目标基因组 ({}) 不同，准备进行同源转换。").format(source_genome, target_genome))

        genome_sources = get_genome_data_sources(config)
        source_genome_info = genome_sources.get(source_genome)
        target_genome_info = genome_sources.get(target_genome)
        bridge_genome_info = genome_sources.get(bridge_species)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            logger.error(_("一个或多个基因组名称无效，无法找到配置信息。"))
            progress(100, _("任务终止：基因组配置错误。"))
            return

        progress(20, _("加载同源数据文件..."))
        if check_cancel(): return

        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not all([s_to_b_homology_file, b_to_t_homology_file, os.path.exists(s_to_b_homology_file),
                    os.path.exists(b_to_t_homology_file)]):
            logger.error(_("缺少必要的同源文件，无法进行转换。请先下载数据。"))
            progress(100, _("任务终止：缺少同源文件。"))
            return

        progress(25, _("正在解析源到桥梁的同源文件..."))
        if check_cancel(): return

        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(25 + int(p * 0.1),
                                                                                                  _("加载同源数据: {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or source_to_bridge_homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return

        progress(35, _("正在解析桥梁到目标的同源文件..."))
        if check_cancel(): return

        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(35 + int(p * 0.1),
                                                                                                  _("加载同源数据: {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or bridge_to_target_homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return

        selection_criteria_s_to_b = HomologySelectionCriteria().model_dump()
        selection_criteria_b_to_t = HomologySelectionCriteria().model_dump()
        homology_columns = {
            "query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"
        }

        progress(50, _("正在通过桥梁物种进行基因映射..."))
        if check_cancel(): return

        mapped_df, _c = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_genome,
            target_assembly_name=target_genome,
            bridge_species_name=bridge_species,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b,
            selection_criteria_b_to_t=selection_criteria_b_to_t,
            homology_columns=homology_columns,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            progress_callback=lambda p, m: progress(50 + int(p * 0.2), _("基因映射: {}").format(m)),
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            progress(100, _("任务已取消。"))
            return

        if mapped_df is None or mapped_df.empty:
            logger.warning(_("同源转换未能映射到任何基因，流程终止。"))
            progress(100, _("任务终止：同源映射失败。"))
            return

        genes_to_annotate = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
        original_to_target_map_df = mapped_df[['Source_Gene_ID', 'Target_Gene_ID']]

    progress(75, _("初始化注释器..."))
    if check_cancel(): return

    genome_sources = get_genome_data_sources(config)
    target_genome_info = genome_sources.get(target_genome)
    if not target_genome_info:
        logger.error(_("错误：无法为目标基因组 {} 找到配置信息。").format(target_genome))
        progress(100, _("任务终止：目标基因组配置错误。"))
        return

    # 修改: Annotator 不再需要 status_callback
    annotator = Annotator(
        main_config=config,
        genome_id=target_genome,
        genome_info=target_genome_info,
        progress_callback=lambda p, m: progress(75 + int(p * 0.15), _("执行注释: {}").format(m)),
        custom_db_dir=custom_db_dir
    )

    progress(90, _("正在执行功能注释..."))
    if check_cancel(): return

    result_df = annotator.annotate_genes(genes_to_annotate, annotation_types)

    if cancel_event and cancel_event.is_set():
        progress(100, _("任务已取消。"))
        return

    progress(95, _("整理并保存结果..."))
    if check_cancel(): return

    if result_df is not None and not result_df.empty:
        if 'Target_Gene_ID' in original_to_target_map_df.columns:
            final_df = pd.merge(original_to_target_map_df, result_df, on='Target_Gene_ID', how='left')
        else:
            final_df = result_df

        final_output_path = ""
        if output_path:
            final_output_path = output_path
            os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
        elif output_dir:
            os.makedirs(output_dir, exist_ok=True)
            base_name = "annotation_result"
            if gene_list_path:
                base_name = os.path.splitext(os.path.basename(gene_list_path))[0]
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            final_output_path = os.path.join(output_dir, f"{base_name}_{timestamp}.csv")
        else:
            logger.error(_("错误: 必须提供 output_dir 或 output_path 参数之一用于保存结果。"))
            progress(100, _("任务终止：未提供输出路径。"))
            return

        try:
            final_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
            logger.info(_("注释成功！结果已保存至: {}").format(final_output_path))
        except Exception as e:
            logger.error(_("保存结果到 {} 时发生错误: {}").format(final_output_path, e))
            progress(100, _("任务终止：保存结果失败。"))
            return

    else:
        logger.warning(_("注释完成，但没有生成任何结果。"))
        progress(100, _("任务完成：无结果。"))

    progress(100, _("功能注释流程结束。"))


def run_gff_lookup(
        config: MainConfig,
        assembly_id: str,
        gene_ids: Optional[List[str]] = None,
        region: Optional[Tuple[str, int, int]] = None,
        output_csv_path: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已被用户取消。"))
            progress(100, _("任务已取消。"))
            return True
        return False

    if not gene_ids and not region:
        logger.error(_("错误: 必须提供基因ID列表或染色体区域进行查询。"))
        progress(100, _("任务终止：缺少查询参数。"))
        return False

    progress(0, _("流程开始，正在初始化配置..."))
    if check_cancel(): return False
    logger.info(_("开始GFF基因查询流程..."))

    project_root = '.'
    if hasattr(config, 'config_file_abs_path_') and config.config_file_abs_path_:
        project_root = os.path.dirname(config.config_file_abs_path_)

    # 修改: get_genome_data_sources 不再需要 logger_func
    genome_sources = get_genome_data_sources(config)
    selected_genome_info = genome_sources.get(assembly_id)
    if not selected_genome_info:
        logger.error(_("错误: 基因组 '{}' 未在基因组源列表中找到。").format(assembly_id))
        progress(100, _("任务终止：基因组配置错误。"))
        return False

    gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')
    if not gff_file_path or not os.path.exists(gff_file_path):
        logger.error(_("错误: 未找到基因组 '{}' 的GFF文件。请先下载数据。").format(assembly_id))
        progress(100, _("任务终止：GFF文件缺失。"))
        return False

    progress(20, _("正在准备GFF数据库..."))
    if check_cancel(): return False
    gff_db_dir = config.locus_conversion.gff_db_storage_dir
    os.makedirs(gff_db_dir, exist_ok=True)

    force_creation = False

    results_df = pd.DataFrame()
    progress(40, _("正在数据库中查询..."))
    if check_cancel(): return False
    if gene_ids:
        logger.info(_("按基因ID查询 {} 个基因...").format(len(gene_ids)))
        # 修改: get_gene_info_by_ids 不再需要 status_callback
        results_df = get_gene_info_by_ids(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, gene_ids=gene_ids,
            force_db_creation=force_creation,
            progress_callback=lambda p, m: progress(40 + int(p * 0.4), _("查询基因ID: {}").format(m))
        )
    elif region:
        chrom, start, end = region
        logger.info(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end))
        # 修改: get_genes_in_region 不再需要 status_callback
        genes_in_region_list = get_genes_in_region(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, region=region,
            force_db_creation=force_creation,
            progress_callback=lambda p, m: progress(40 + int(p * 0.4), _("查询区域基因: {}").format(m))
        )
        if genes_in_region_list:
            results_df = pd.DataFrame(genes_in_region_list)

    if check_cancel(): return False

    progress(90, _("查询完成，正在整理结果..."))
    if check_cancel(): return False

    if results_df.empty:
        logger.warning(_("未找到任何符合条件的基因。"))
        progress(100, _("任务完成：未找到结果。"))
    else:
        logger.info(_("查询完成，找到 {} 个基因记录。").format(len(results_df)))

        final_output_path = output_csv_path
        if not final_output_path:
            output_dir = os.path.join(project_root, "gff_query_results")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            query_type = "genes" if gene_ids else f"region_{region[0]}_{region[1]}_{region[2]}"
            final_output_path = os.path.join(output_dir, f"gff_query_{assembly_id}_{query_type}_{timestamp}.csv")

        try:
            results_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
            logger.info(_("GFF基因查询结果已保存到: {}").format(final_output_path))
        except Exception as e:
            logger.error(_("保存结果时出错: {}").format(e))
            progress(100, _("任务终止：保存结果失败。"))
            return False

    progress(100, _("GFF查询流程结束。"))
    return True


def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
):
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("下载流程开始..."))
    if cancel_event and cancel_event.is_set(): logger.info(_("任务在启动时被取消。")); return
    logger.info(_("下载流程开始..."))

    downloader_cfg = config.downloader
    # 修改: get_genome_data_sources 不再需要 logger_func
    genome_sources = get_genome_data_sources(config)
    if cli_overrides is None: cli_overrides = {}

    versions_to_download = cli_overrides.get("versions") or list(genome_sources.keys())
    force_download = cli_overrides.get("force", downloader_cfg.force_download)
    max_workers = downloader_cfg.max_workers
    use_proxy_for_this_run = cli_overrides.get("use_proxy_for_download", downloader_cfg.use_proxy_for_download)

    file_keys_to_process = cli_overrides.get("file_types")

    proxies_to_use = None
    if use_proxy_for_this_run:
        if config.proxies and (config.proxies.http or config.proxies.https):
            proxies_to_use = config.proxies.model_dump(exclude_none=True)
            logger.info(_("本次下载将使用代理: {}").format(proxies_to_use))
        else:
            logger.warning(_("下载代理开关已打开，但配置文件中未设置代理地址。"))

    progress(5, _("正在准备下载任务列表..."))
    if cancel_event and cancel_event.is_set(): logger.info(_("任务被取消。")); return

    logger.info(_("将尝试下载的基因组版本: {}").format(', '.join(versions_to_download)))

    all_download_tasks = []
    if not file_keys_to_process:
        all_possible_keys = [f.name.replace('_url', '') for f in GenomeSourceItem.model_fields.values() if
                             f.name.endswith('_url')]
        logger.debug(_("未从UI指定文件类型，将尝试检查所有可能的类型: {}").format(all_possible_keys))
    else:
        all_possible_keys = file_keys_to_process
        logger.debug(_("将根据UI的选择，精确下载以下文件类型: {}").format(all_possible_keys))

    for version_id in versions_to_download:
        if cancel_event and cancel_event.is_set(): break
        genome_info = genome_sources.get(version_id)
        if not genome_info:
            logger.warning(_("在基因组源中未找到版本 '{}'，已跳过。").format(version_id))
            continue

        for file_key in all_possible_keys:
            url_attr = f"{file_key}_url"
            if hasattr(genome_info, url_attr):
                url = getattr(genome_info, url_attr)
                if url:
                    all_download_tasks.append({
                        "version_id": version_id,
                        "genome_info": genome_info,
                        "file_key": file_key,
                        "url": url
                    })

    if cancel_event and cancel_event.is_set(): logger.info(_("任务在任务列表创建期间被取消。")); return

    if not all_download_tasks:
        logger.warning(_("根据您的选择，没有找到任何有效的URL可供下载。"))
        progress(100, _("任务完成：无文件可下载。"))
        return

    progress(10, _("找到 {} 个文件需要下载。").format(len(all_download_tasks)))
    if cancel_event and cancel_event.is_set(): logger.info(_("任务被取消。")); return
    logger.info(_("准备下载 {} 个文件...").format(len(all_download_tasks)))

    successful_downloads, failed_downloads = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(
                download_genome_data,
                downloader_config=config.downloader,
                version_id=task["version_id"],
                genome_info=task["genome_info"],
                file_key=task["file_key"],
                url=task["url"],
                force=force_download,
                proxies=proxies_to_use,
                cancel_event=cancel_event,
            ): task for task in all_download_tasks
        }

        total_tasks = len(future_to_task)
        current_completed_tasks = 0
        for future in as_completed(future_to_task):
            if cancel_event and cancel_event.is_set():
                logger.info(_("下载任务已被用户取消。"))
                progress(100, _("任务已取消。"))
                for f in future_to_task:
                    f.cancel()
                break

            task_info = future_to_task[future]
            try:
                if future.result():
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as exc:
                if not isinstance(exc, threading.CancelledError):
                    logger.error(_("下载 {} 的 {} 文件时发生严重错误: {}").format(task_info['version_id'],
                                                                                  task_info['file_key'], exc))
                failed_downloads += 1
            finally:
                current_completed_tasks += 1
                progress_percentage = 10 + int((current_completed_tasks / total_tasks) * 85)
                progress(progress_percentage,
                         f"{_('总体下载进度')} ({current_completed_tasks}/{total_tasks}) - {task_info['version_id']} {task_info['file_key']}")

    logger.info(_("所有指定的下载任务已完成。成功: {}, 失败: {}。").format(successful_downloads, failed_downloads))
    progress(100, _("下载流程完成。"))


def _generate_r_script_and_data(
        enrichment_df: pd.DataFrame,
        r_output_dir: str,
        file_prefix: str,
        plot_type: str,
        plot_kwargs: Dict[str, Any],
        analysis_title: str,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[List[str]]:
    # 修改: 移除 log 参数
    try:
        if not os.path.exists(r_output_dir):
            os.makedirs(r_output_dir)

        top_n = plot_kwargs.get('top_n', 20)
        sort_by = plot_kwargs.get('sort_by', 'FDR').lower()

        df_plot = enrichment_df.copy()
        sort_col = 'FDR'
        if sort_by == 'pvalue':
            sort_col = 'PValue'
        elif sort_by == 'foldenrichment':
            sort_col = 'RichFactor'

        ascending = sort_by in ['fdr', 'pvalue']
        current_top_n = plot_kwargs.get('top_n', 10) if plot_type == 'upset' else top_n
        df_plot = df_plot.sort_values(by=sort_col, ascending=ascending).head(current_top_n)

        if df_plot.empty:
            logger.warning(f"DataFrame is empty for plot type '{plot_type}'. Cannot generate R script.")
            return None

        if 'FDR' in df_plot.columns:
            fdr_numeric = pd.to_numeric(df_plot['FDR'], errors='coerce').replace(0, np.finfo(float).tiny)
            df_plot['log10FDR'] = -np.log10(fdr_numeric)

        if plot_type != 'upset':
            df_plot = df_plot.iloc[::-1].copy()

        data_path = os.path.join(r_output_dir, f"{file_prefix}_{plot_type}_data.csv")
        script_path = os.path.join(r_output_dir, f"{file_prefix}_{plot_type}_script.R")
        r_script_content = ""
        log2fc_data_path = None
        df_plot.to_csv(data_path, index=False, encoding='utf-8-sig')

        if plot_type == 'bubble':
            r_script_content = f"""
# R Script: Bubble Plot for Enrichment Analysis

# 1. Load required packages
# install.packages(c("ggplot2", "dplyr", "stringr"))
library(ggplot2)
library(dplyr)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for plotting
# Convert 'Description' to a factor to preserve the sorting order from Python.
enrich_data$Description <- factor(enrich_data$Description, levels = unique(enrich_data$Description))
# Wrap long labels to prevent overlap.
levels(enrich_data$Description) <- str_wrap(levels(enrich_data$Description), width = 50)

# 4. Create the bubble plot
bubble_plot <- ggplot(enrich_data, aes(x = RichFactor, y = Description, size = GeneNumber, color = {sort_col})) +
  geom_point(alpha = 0.8, shape = 16) +
  scale_color_viridis_c(direction = -1, name = "{sort_col}") +
  scale_size_continuous(name = "Gene Count", range = c(3, 10)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Top {current_top_n} Enriched Terms by {sort_by.upper()}",
    x = "Rich Factor",
    y = "Term Description"
  ) +
  theme_minimal(base_size = 14) +
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold", size = 16),
    plot.subtitle = element_text(hjust = 0.5),
    axis.text = element_text(colour = "black"),
    panel.grid.minor = element_blank()
  )

# 5. Save the plot
ggsave(
  "{file_prefix}_bubble_plot_from_R.png",
  plot = bubble_plot,
  width = {plot_kwargs.get('width', 10)},
  height = {plot_kwargs.get('height', 8)},
  dpi = 300,
  bg = "white"
)
"""
        elif plot_type == 'bar':
            use_log2fc = False
            if gene_log2fc_map and 'Genes' in df_plot.columns:
                use_log2fc = True
                avg_fc_list = [np.mean(
                    [gene_log2fc_map.get(g) for g in re.sub(r'\.\d+$', '', str(gene_str)).split(';') if
                     g and gene_log2fc_map.get(g) is not None] or [0]) for gene_str in df_plot['Genes']]
                df_with_fc = df_plot.copy();
                df_with_fc['avg_log2FC'] = avg_fc_list
                df_with_fc.to_csv(data_path, index=False, encoding='utf-8-sig')
            r_script_content = f"""
# R Script: Bar Plot for Enrichment Analysis

# 1. Load required packages
library(ggplot2)
library(dplyr)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for plotting
enrich_data$Description <- factor(enrich_data$Description, levels = unique(enrich_data$Description))
levels(enrich_data$Description) <- str_wrap(levels(enrich_data$Description), width = 40)

# 4. Create the bar plot
use_log2fc_color <- {'TRUE' if use_log2fc else 'FALSE'}
bar_plot <- ggplot(enrich_data, aes(x = log10FDR, y = Description)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Top {current_top_n} Enriched Terms by {sort_by.upper()}",
    x = "-log10(FDR)",
    y = "Term Description"
  ) +
  theme_minimal(base_size = 14) +
  theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size=16),
      plot.subtitle = element_text(hjust = 0.5),
      axis.text = element_text(colour = "black"),
      panel.grid.minor.y = element_blank(),
      panel.grid.major.y = element_blank()
  )

# 5. Set fill color based on log2FC availability
if (use_log2fc_color) {{
  # Calculate the mean of the log2FC values to create a relative, high-contrast color scale.
  midpoint_val <- mean(enrich_data$avg_log2FC, na.rm = TRUE)

  final_plot <- bar_plot +
    geom_col(aes(fill = avg_log2FC)) +
    # Use the calculated midpoint to ensure a diverging scale (blue to red), similar to Python's.
    scale_fill_gradient2(
      low = "blue",
      mid = "white",
      high = "red",
      midpoint = midpoint_val,
      name = "Average log2FC"
    )
}} else {{
  final_plot <- bar_plot + geom_col(fill = "skyblue")
}}

# 6. Save the plot
ggsave(
  "{file_prefix}_bar_plot_from_R.png",
  plot = final_plot,
  width = {plot_kwargs.get('width', 10)},
  height = {plot_kwargs.get('height', 8)},
  dpi = 300,
  bg = "white"
)
"""
        elif plot_type == 'cnet':
            cnet_top_n = plot_kwargs.get('top_n', 5)
            if gene_log2fc_map:
                log2fc_data_path = os.path.join(r_output_dir, f"{file_prefix}_cnet_log2fc_data.csv")
                cleaned_fc_data = []
                processed_keys = set()
                for k, v in gene_log2fc_map.items():
                    if not isinstance(k, str): continue
                    cleaned_key = re.sub(r'\.\d+$', '', k)
                    if cleaned_key not in processed_keys:
                        cleaned_fc_data.append({'GeneID': cleaned_key, 'log2FC': v})
                        processed_keys.add(cleaned_key)
                if cleaned_fc_data:
                    pd.DataFrame(cleaned_fc_data).to_csv(log2fc_data_path, index=False, encoding='utf-8-sig')

            r_script_content = f"""
# R Script: Gene-Concept Network (cnet) Plot (Manual Version)

# 1. Load required packages
library(ggplot2)
library(dplyr)
library(ggraph)
library(igraph)
library(tidyr)

# 2. Load data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)
gene_log2fc <- NULL
log2fc_file <- "{os.path.basename(log2fc_data_path) if log2fc_data_path else 'NULL'}"
if (!is.null(log2fc_file) && file.exists(log2fc_file)) {{
  log2fc_data <- read.csv(log2fc_file)
  gene_log2fc <- setNames(log2fc_data$log2FC, log2fc_data$GeneID)
}}

# 3. Prepare data for network graphing
edge_list <- enrich_data %>%
  select(Description, Genes) %>%
  rename(from = Description, to = Genes) %>%
  separate_rows(to, sep = ";")
graph_obj <- graph_from_data_frame(edge_list, directed = FALSE)

# 4. Prepare node attributes
V(graph_obj)$type <- ifelse(V(graph_obj)$name %in% enrich_data$Description, "Term", "Gene")

if (!is.null(gene_log2fc)) {{
  # Map log2FC values to each node. Terms will have NA.
  V(graph_obj)$logFC <- gene_log2fc[V(graph_obj)$name]
}} else {{
  V(graph_obj)$logFC <- as.numeric(NA)
}}

# Set node size based on degree
node_degrees <- degree(graph_obj, V(graph_obj))
V(graph_obj)$size <- ifelse(V(graph_obj)$type == "Term", node_degrees, 3)

# 5. Create the plot using ggraph
set.seed(123)
cnet_plot <- ggraph(graph_obj, layout = 'fr') +
  geom_edge_link(alpha = 0.4, colour = 'grey50') +
  # Map color aesthetic directly to the numeric logFC attribute
  geom_node_point(aes(color = logFC, size = size), alpha = 0.8) +
  geom_node_text(aes(label = name), repel = TRUE, size = 3) +

  # Add the color scale, which will create the legend and color the nodes.
  # 'na.value' sets the color for Term nodes (where logFC is NA).
  scale_color_gradient2(
    name = "log2FC",
    low = "blue",
    mid = "white",
    high = "red",
    midpoint = 0,
    na.value = "skyblue"
  ) +

  scale_size_continuous(name = "Gene Count", range = c(3, 15)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Gene-Concept Network"
  ) +
  theme_graph() +
  theme(
    plot.title = element_text(hjust = 0.5, face="bold"),
    legend.position = "right"
  ) +
  guides(size = guide_legend(order=1), color = guide_colorbar(order=2))

if (!is.null(gene_log2fc)) {{
  valid_fc_values <- na.omit(V(graph_obj)$logFC[V(graph_obj)$type == 'Gene'])
  if(length(valid_fc_values) > 0) {{
    midpoint_val <- mean(valid_fc_values, na.rm = TRUE)
    cnet_plot <- cnet_plot +
      scale_color_gradient2(
        name = "log2FC",
        low = "blue",
        mid = "white",
        high = "red",
        midpoint = midpoint_val,
        na.value = "skyblue"
      )
  }}
}} else {{
    # If there is no logFC data, ensure terms are still colored
    cnet_plot <- cnet_plot + scale_color_continuous(na.value = "skyblue")
}}

# 6. Save the plot
ggsave(
  "{file_prefix}_cnet_plot_from_R.png",
  plot = cnet_plot,
  width = 12, height = 12, dpi = 300, bg = "white"
)
"""

        elif plot_type == 'upset':
            r_script_content = f"""
# R Script: Upset Plot for Gene Set Intersections

# 1. Load required packages
# install.packages(c("UpSetR", "stringr"))
library(UpSetR)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for UpSetR
# Wrap long set names to prevent overlap
enrich_data$Description <- str_wrap(enrich_data$Description, width = 40)

# Create a named list where names are terms and values are gene vectors.
gene_list <- strsplit(enrich_data$Genes, ";")
names(gene_list) <- enrich_data$Description

# 4. Create and save the Upset plot
png("{file_prefix}_upset_plot_from_R.png", width = 1200, height = 700, res = 100)
upset(
  fromList(gene_list),
  sets = enrich_data$Description,
  nsets = nrow(enrich_data),
  nintersects = 40,
  order.by = "freq",

  # mb.ratio controls the height ratio of the main bar plot to the matrix.
  # c(0.4, 0.6) gives 40% height to the bar plot and 60% to the matrix.
  mb.ratio = c(0.4, 0.6),
  text.scale = 1.3,
  mainbar.y.label = "Intersection Size",
  sets.x.label = "Set Size"
)
dev.off() # Close the PNG device
"""

        if r_script_content:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(r_script_content)
            generated_files = [data_path, script_path]
            if log2fc_data_path: generated_files.append(log2fc_data_path)
            # 修改: 使用 logger
            logger.info(f"Successfully generated R script and data for '{plot_type}' plot.")
            return generated_files
        return None
    except Exception as e:
        # 修改: 使用 logger
        logger.error(f"An error occurred while generating the R script for plot type '{plot_type}': {e}")
        logger.debug(traceback.format_exc())
        return None


def run_enrichment_pipeline(
        config: MainConfig,
        assembly_id: str,
        study_gene_ids: List[str],
        analysis_type: str,
        plot_types: List[str],
        output_dir: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        gene_log2fc_map: Optional[Dict[str, float]] = None,
        collapse_transcripts: bool = False,
        top_n: int = 20,
        sort_by: str = 'FDR',
        show_title: bool = True,
        width: float = 10,
        height: float = 8,
        file_format: str = 'png'
) -> Optional[str]:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已被用户取消。"));
            progress(100, _("任务已取消."));
            return True
        return False

    progress(0, _("富集分析与可视化流程启动。"))
    if check_cancel(): return None
    logger.info(_("{} 富集与可视化流程启动。").format(analysis_type.upper()))

    if collapse_transcripts:
        original_count = len(study_gene_ids)
        study_gene_ids = map_transcripts_to_genes(study_gene_ids)
        logger.info(_("基因列表已从 {} 个RNA合并为 {} 个唯一基因。").format(original_count, len(study_gene_ids)))

    try:
        progress(10, _("正在获取基因组信息..."))
        if check_cancel(): return None
        # 修改: get_genome_data_sources 不再需要 logger_func
        genome_sources = get_genome_data_sources(config)
        genome_info = genome_sources.get(assembly_id)
        if not genome_info:
            logger.error(_("无法在配置中找到基因组 '{}'。").format(assembly_id));
            progress(100, _("任务终止：基因组配置错误。"));
            return None
        gene_id_regex = genome_info.gene_id_regex if hasattr(genome_info, 'gene_id_regex') else None
    except Exception as e:
        logger.error(_("获取基因组源数据时失败: {}").format(e));
        progress(100, _("任务终止：获取基因组信息失败。"));
        return None

    os.makedirs(output_dir, exist_ok=True)
    r_output_dir = os.path.join(output_dir, "R_scripts_and_data")
    enrichment_df = None

    if analysis_type == 'go':
        progress(20, _("正在执行GO富集分析..."))
        if check_cancel(): return None
        gaf_path = get_local_downloaded_file_path(config, genome_info, 'GO')
        if not gaf_path or not os.path.exists(gaf_path):
            logger.error(_("未找到 '{}' 的GO注释关联文件 (GAF)。请先下载数据。").format(assembly_id));
            progress(100, _("任务终止：缺少GO注释文件。"));
            return None
        # 修改: run_go_enrichment 不再需要 status_callback
        enrichment_df = run_go_enrichment(study_gene_ids=study_gene_ids, go_annotation_path=gaf_path,
                                          output_dir=output_dir, gene_id_regex=gene_id_regex,
                                          progress_callback=lambda p, m: progress(20 + int(p * 0.4),
                                                                                  _("GO富集: {}").format(m)))
    elif analysis_type == 'kegg':
        progress(20, _("正在执行KEGG富集分析..."))
        if check_cancel(): return None
        pathways_path = get_local_downloaded_file_path(config, genome_info, 'KEGG_pathways')
        if not pathways_path or not os.path.exists(pathways_path):
            logger.error(_("未找到 '{}' 的KEGG通路文件。请先下载数据。").format(assembly_id));
            progress(100, _("任务终止：缺少KEGG通路文件。"));
            return None
        # 修改: run_kegg_enrichment 不再需要 status_callback
        enrichment_df = run_kegg_enrichment(study_gene_ids=study_gene_ids, kegg_pathways_path=pathways_path,
                                            output_dir=output_dir, gene_id_regex=gene_id_regex,
                                            progress_callback=lambda p, m: progress(20 + int(p * 0.4),
                                                                                    _("KEGG富集: {}").format(m)))

    if check_cancel(): return None
    if enrichment_df is None or enrichment_df.empty:
        logger.warning(_("富集分析未发现任何显著结果，流程终止。"));
        progress(100, _("任务完成：无显著结果。"));
        return "Enrichment analysis completed with no significant results."

    progress(60, _("富集分析完成，正在生成图表..."))

    generated_plots = []
    plot_kwargs_common = {'top_n': top_n, 'show_title': show_title, 'width': width, 'height': height,
                          'sort_by': sort_by}

    def process_python_plots(df_sub, title_prefix, file_prefix_ns):
        """Helper function to run all selected python plotting functions."""
        if 'bubble' in plot_types:
            plot_path = plot_enrichment_bubble(df_sub,
                                               os.path.join(output_dir, f"{file_prefix_ns}_bubble.{file_format}"),
                                               title=f"{title_prefix} Bubble Plot", **plot_kwargs_common)
            if plot_path: generated_plots.append(plot_path)

        if 'bar' in plot_types:
            plot_path = plot_enrichment_bar(df_sub, os.path.join(output_dir, f"{file_prefix_ns}_bar.{file_format}"),
                                            title=f"{title_prefix} Bar Plot", gene_log2fc_map=gene_log2fc_map,
                                            **plot_kwargs_common)
            if plot_path: generated_plots.append(plot_path)

        if 'upset' in plot_types:
            plot_path = plot_enrichment_upset(df_sub, os.path.join(output_dir, f"{file_prefix_ns}_upset.{file_format}"),
                                              top_n=plot_kwargs_common.get('top_n', 10))
            if plot_path: generated_plots.append(plot_path)

        if 'cnet' in plot_types:
            plot_path = plot_enrichment_cnet(df_sub, os.path.join(output_dir, f"{file_prefix_ns}_cnet.{file_format}"),
                                             top_n=plot_kwargs_common.get('top_n', 5), gene_log2fc_map=gene_log2fc_map)
            if plot_path: generated_plots.append(plot_path)

    if analysis_type == 'go' and 'Namespace' in enrichment_df.columns:
        for ns in enrichment_df['Namespace'].unique():
            if check_cancel(): break
            df_sub = enrichment_df[enrichment_df['Namespace'] == ns]
            if df_sub.empty: continue
            process_python_plots(df_sub, f"GO Enrichment - {ns}", f"go_enrichment_{ns}")
    else:
        process_python_plots(enrichment_df, f"{analysis_type.upper()} Enrichment",
                             f"{analysis_type.lower()}_enrichment")

    progress(95, _("正在生成 R 脚本和数据..."))
    if check_cancel(): return None
    logger.info(_("正在为绘图生成 R 脚本和配套数据..."))

    generated_files = generated_plots
    r_plot_types = plot_types

    if r_plot_types:
        try:
            os.makedirs(r_output_dir, exist_ok=True)
            readme_path = os.path.join(r_output_dir, "readme.md")
            readme_content = "Due to inconsistencies in some of the libraries or algorithms used by R and Python, the generated plots may not be completely identical."
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            generated_files.append(readme_path)
        except Exception as e:
            logger.warning(f"Could not write readme.md file. Reason: {e}")

    def generate_r_scripts(df_sub, title_prefix, file_prefix_ns):
        for plot_type in r_plot_types:
            if check_cancel(): break
            # 修改: _generate_r_script_and_data 不再需要 log
            r_files = _generate_r_script_and_data(
                enrichment_df=df_sub, r_output_dir=r_output_dir, file_prefix=file_prefix_ns,
                plot_type=plot_type, plot_kwargs=plot_kwargs_common, analysis_title=title_prefix,
                gene_log2fc_map=gene_log2fc_map
            )
            if r_files: generated_files.extend(r_files)

    if analysis_type == 'go' and 'Namespace' in enrichment_df.columns:
        for ns in enrichment_df['Namespace'].unique():
            if check_cancel(): break
            df_sub = enrichment_df[enrichment_df['Namespace'] == ns]
            if df_sub.empty: continue
            generate_r_scripts(df_sub, f"GO Enrichment - {ns}", f"go_enrichment_{ns}")
    else:
        generate_r_scripts(enrichment_df, f"{analysis_type.upper()} Enrichment", f"{analysis_type.lower()}_enrichment")

    progress(100, _("所有图表和脚本已生成。"))
    final_message = _("富集分析成功！\n\n在输出目录 '{}' 中共生成 {} 个文件。\n").format(os.path.abspath(output_dir),
                                                                                       len(generated_files))
    if any(f.endswith('_script.R') for f in generated_files):
        final_message += _(
            "\n✨ 提示：我们已为您额外生成了配套的 .R 脚本和 .csv 数据文件，并统一存放在 '{}' 子文件夹中。").format(
            os.path.basename(r_output_dir))
    logger.info(final_message)
    return final_message


def run_preprocess_annotation_files(
        config: MainConfig,
        selected_assembly_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已被用户取消。"))
            progress(100, _("任务已取消。"))
            return True
        return False

    progress(0, _("开始预处理注释文件（转换为CSV）..."))
    if check_cancel(): return False
    logger.info(_("开始预处理注释文件（转换为CSV）..."))

    progress(5, _("正在加载基因组源数据..."))
    if check_cancel(): return False
    # 修改: get_genome_data_sources 不再需要回调函数
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        logger.error(_("未能加载基因组源数据。"))
        progress(100, _("任务终止：未能加载基因组源。"))
        return False

    genomes_to_process = [genome_sources[
                              selected_assembly_id]] if selected_assembly_id and selected_assembly_id in genome_sources else genome_sources.values()

    tasks_to_run = []
    ALL_ANNO_KEYS = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']
    progress(10, _("正在检查需要预处理的文件..."))
    if check_cancel(): return False

    for genome_info in genomes_to_process:
        if check_cancel(): break
        for key in ALL_ANNO_KEYS:
            source_path = get_local_downloaded_file_path(config, genome_info, key)

            if source_path and os.path.exists(source_path) and source_path.lower().endswith(
                    ('.xlsx', '.xlsx.gz', '.txt', '.txt.gz')):

                if source_path.lower().endswith('.gz'):
                    base_path = source_path.rsplit('.', 2)[0]
                else:
                    base_path = source_path.rsplit('.', 1)[0]
                output_path = base_path + '.csv'

                if not os.path.exists(output_path) or os.path.getmtime(source_path) > os.path.getmtime(output_path):
                    tasks_to_run.append((source_path, output_path))

    if check_cancel(): return False

    if not tasks_to_run:
        logger.info(_("所有注释文件均已是最新状态，无需预处理。"))
        progress(100, _("无需处理，所有文件已是最新。"))
        return True

    total_tasks = len(tasks_to_run)
    progress(20, _("找到 {} 个文件需要进行预处理。").format(total_tasks))
    logger.info(_("找到 {} 个文件需要进行预处理。").format(total_tasks))
    success_count = 0

    for i, (source, output) in enumerate(tasks_to_run):
        if check_cancel(): return False

        progress_percentage = 20 + int(((i + 1) / total_tasks) * 75)
        progress(progress_percentage, _("正在转换: {} ({}/{})").format(os.path.basename(source), i + 1, total_tasks))

        logger.info(_("Starting intelligent conversion for: {}").format(os.path.basename(source)))
        # 修改: normalize_to_csv 不再需要回调函数
        if normalize_to_csv(source, output):
            success_count += 1
        else:
            logger.error(_("Conversion failed for: {}").format(os.path.basename(source)))

    logger.info(_("预处理完成。成功转换 {}/{} 个文件。").format(success_count, total_tasks))
    progress(100, _("预处理完成。"))
    return success_count == total_tasks


def run_xlsx_to_csv(
        excel_path: str,
        output_csv_path: str,
        cancel_event: Optional[threading.Event] = None,
        **kwargs) -> bool:
    # 修改: 移除 status_callback 参数
    try:
        logger.info(_("开始将 '{}' 转换为CSV...").format(os.path.basename(excel_path)))
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务在开始前被取消。"))
            return False
        # 修改: convert_excel_to_standard_csv 不再需要 status_callback
        success = convert_excel_to_standard_csv(
            excel_path=excel_path,
            output_csv_path=output_csv_path,
            cancel_event=cancel_event
        )
        if success:
            logger.info(_("成功将文件转换为CSV格式: {}").format(output_csv_path))
        else:
            if not (cancel_event and cancel_event.is_set()):
                logger.error(_("转换文件时失败。"))
        return success
    except Exception as e:
        logger.error(_("执行Excel到CSV转换流水线时发生错误: {}").format(e))
        return False


def run_blast_pipeline(
        config: MainConfig,
        blast_type: str,
        target_assembly_id: str,
        query_file_path: Optional[str],
        query_text: Optional[str],
        output_path: str,
        evalue: float,
        word_size: int,
        max_target_seqs: int,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> Optional[str]:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel(message: str = "任务已取消。"):
        if cancel_event and cancel_event.is_set():
            logger.info(message)
            return True
        return False

    tmp_query_file_to_clean = None
    try:
        progress(0, _("BLAST 流程启动..."))
        if check_cancel(): return _("任务已取消。")

        progress(5, _("正在验证目标基因组数据库..."))
        logger.info(_("步骤 1: 准备目标数据库 '{}'...").format(target_assembly_id))

        # 修改: get_genome_data_sources 不再需要 logger_func
        genome_sources = get_genome_data_sources(config)
        target_genome_info = genome_sources.get(target_assembly_id)
        if not target_genome_info:
            logger.error(_("错误: 无法找到目标基因组 '{}' 的配置。").format(target_assembly_id))
            return None

        db_type = 'prot' if blast_type in ['blastp', 'blastx'] else 'nucl'
        seq_file_key = 'predicted_protein' if db_type == 'prot' else 'predicted_cds'

        logger.info(_("为 {} 需要 {} 类型的数据库，将使用 '{}' 文件。").format(blast_type, db_type, seq_file_key))

        compressed_seq_file = get_local_downloaded_file_path(config, target_genome_info, seq_file_key)
        if not compressed_seq_file or not os.path.exists(compressed_seq_file):
            logger.error(_("错误: 未找到目标基因组的 '{}' 序列文件。请先下载数据。").format(seq_file_key))
            return None

        db_fasta_path = compressed_seq_file
        if compressed_seq_file.endswith('.gz'):
            decompressed_path = compressed_seq_file.removesuffix('.gz')
            db_fasta_path = decompressed_path
            if not os.path.exists(decompressed_path) or os.path.getmtime(compressed_seq_file) > os.path.getmtime(
                    decompressed_path):
                progress(8, _("文件为gz压缩格式，正在解压..."))
                logger.info(_("正在解压 {} 到 {}...").format(os.path.basename(compressed_seq_file),
                                                             os.path.basename(decompressed_path)))
                try:
                    with gzip.open(compressed_seq_file, 'rb') as f_in, open(decompressed_path, 'wb') as f_out:
                        while True:
                            if check_cancel(_("解压过程被取消。")): return None
                            chunk = f_in.read(1024 * 1024)
                            if not chunk:
                                break
                            f_out.write(chunk)
                    logger.info(_("解压成功。"))
                except Exception as e:
                    logger.error(_("解压文件时出错: {}").format(e))
                    return None

        if check_cancel(): return _("任务已取消。")

        db_check_ext = '.phr' if db_type == 'prot' else '.nhr'
        if not os.path.exists(db_fasta_path + db_check_ext):
            progress(10, _("正在创建BLAST数据库... (可能需要一些时间)"))
            logger.info(
                _("未找到现有的BLAST数据库，正在为 '{}' 创建一个新的 {} 库...").format(os.path.basename(db_fasta_path),
                                                                                      db_type))

            makeblastdb_cmd = ["makeblastdb", "-in", db_fasta_path, "-dbtype", db_type, "-out", db_fasta_path, "-title",
                               f"{target_assembly_id} {db_type} DB"]
            try:
                if check_cancel(_("数据库创建过程在开始前被取消。")): return None
                result = subprocess.run(makeblastdb_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
                logger.info(_("BLAST数据库创建成功。"))
            except FileNotFoundError:
                logger.error(_(
                    "错误: 'makeblastdb' 命令未找到。请确保 BLAST+ 已被正确安装并添加到了系统的 PATH 环境变量中。\n\n官方下载地址:\nhttps://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"))
                return False
            except subprocess.CalledProcessError as e:
                logger.error(_("创建BLAST数据库失败: {} \nStderror: {}").format(e.stdout, e.stderr))
                return None

        if check_cancel(): return _("任务已取消。")

        progress(25, _("正在准备查询序列..."))
        tmp_query_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".fasta")
        tmp_query_file_to_clean = tmp_query_file.name
        with tmp_query_file:
            query_fasta_path = tmp_query_file.name
            if query_file_path:
                if check_cancel(): return _("任务已取消。")
                logger.info(_("正在处理输入文件: {}").format(query_file_path))
                file_format = "fasta"
                try:
                    with open(query_file_path, "r") as f:
                        if f.read(1) == '@': file_format = "fastq"
                except:
                    pass
                if file_format == "fastq":
                    logger.info(_("检测到FASTQ格式，正在转换为FASTA..."))
                    SeqIO.convert(query_file_path, "fastq", query_fasta_path, "fasta")
                else:
                    logger.info(_("将输入文件作为FASTA格式处理..."))
                    with open(query_file_path, 'r') as infile:
                        tmp_query_file.write(infile.read())
            elif query_text:
                if check_cancel(): return _("任务已取消。")
                logger.info(_("正在处理文本输入..."))
                tmp_query_file.write(query_text)

        if check_cancel(): return _("任务已取消。")

        progress(40, _("正在执行 {} ...").format(blast_type))
        logger.info(_("步骤 2: 执行 {} ...").format(blast_type.upper()))

        output_xml_path = query_fasta_path + ".xml"

        blast_map = {'blastn': NcbiblastnCommandline, 'blastp': NcbiblastpCommandline, 'blastx': NcbiblastxCommandline,
                     'tblastn': NcbitblastnCommandline}
        blast_cline = blast_map[blast_type](query=query_fasta_path, db=db_fasta_path, out=output_xml_path, outfmt=5,
                                            evalue=evalue, word_size=word_size, max_target_seqs=max_target_seqs,
                                            num_threads=config.downloader.max_workers)

        logger.info(_("BLAST命令: {}").format(str(blast_cline)))
        if check_cancel(_("BLAST在执行前被取消。")): return None
        stdout, stderr = blast_cline()
        if stderr:
            logger.error(_("BLAST运行时发生错误: {}").format(stderr))
            return None

        if check_cancel(): return _("任务已取消。")

        progress(80, _("正在解析BLAST结果..."))
        logger.info(_("步骤 3: 解析结果并保存到 {} ...").format(output_path))

        all_hits = []
        if not os.path.exists(output_xml_path) or os.path.getsize(output_xml_path) == 0:
            logger.warning(_("BLAST运行完毕，但未产生任何结果。"))
        else:
            blast_results = blast_parse(output_xml_path, "blast-xml")
            for query_result in blast_results:
                if check_cancel(_("BLAST结果解析过程被取消。")): break
                for hit in query_result:
                    for hsp in hit:
                        hit_data = {
                            "Query_ID": query_result.id, "Query_Length": query_result.seq_len,
                            "Hit_ID": hit.id, "Hit_Description": hit.description, "Hit_Length": hit.seq_len,
                            "E-value": hsp.evalue, "Bit_Score": hsp.bitscore,
                            "Identity (%)": (hsp.ident_num / hsp.aln_span) * 100 if hsp.aln_span > 0 else 0,
                            "Positives (%)": (hsp.pos_num / hsp.aln_span) * 100 if hsp.aln_span > 0 else 0,
                            "Gaps": hsp.gap_num, "Alignment_Length": hsp.aln_span,
                            "Query_Start": hsp.query_start, "Query_End": hsp.query_end,
                            "Hit_Start": hsp.hit_start, "Hit_End": hsp.hit_end,
                            "Query_Strand": hsp.query_strand, "Hit_Strand": hsp.hit_strand,
                            "Query_Sequence": str(hsp.query.seq), "Hit_Sequence": str(hsp.hit.seq),
                            "Alignment_Midline": hsp.aln_annotation.get('homology', '')
                        }
                        all_hits.append(hit_data)

        if check_cancel(): return _("任务已取消。")

        if not all_hits:
            logger.info(_("未找到任何显著的BLAST匹配项。"))
        else:
            results_df = pd.DataFrame(all_hits)
            results_df['Identity (%)'] = results_df['Identity (%)'].map('{:.2f}'.format)
            results_df['Positives (%)'] = results_df['Positives (%)'].map('{:.2f}'.format)

            progress(95, _("正在保存到文件..."))
            if output_path.lower().endswith('.csv'):
                results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            elif output_path.lower().endswith('.xlsx'):
                results_df.to_excel(output_path, index=False, engine='openpyxl')

            logger.info(_("成功找到 {} 条匹配记录。").format(len(results_df)))

        progress(100, _("BLAST流程完成。"))
        return _("BLAST 任务完成！结果已保存到 {}").format(output_path)

    except Exception as e:
        logger.error(_("BLAST流水线执行过程中发生意外错误: {}").format(e))
        logger.debug(traceback.format_exc())
        return None
    finally:
        if tmp_query_file_to_clean and os.path.exists(tmp_query_file_to_clean):
            os.remove(tmp_query_file_to_clean)
            output_xml_path = tmp_query_file_to_clean + ".xml"
            if os.path.exists(output_xml_path):
                os.remove(output_xml_path)


def run_build_blast_db_pipeline(
        config: MainConfig,
        selected_assembly_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    # 修改: 移除 status_callback
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已被用户取消。"))
            return True
        return False

    progress(0, _("开始预处理BLAST数据库..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False
    logger.info(_("开始批量创建BLAST数据库..."))

    progress(5, _("正在加载基因组源数据..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False
    # 修改: get_genome_data_sources 不再需要回调函数
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        logger.error(_("未能加载基因组源数据。"))
        progress(100, _("任务终止：未能加载基因组源。"))
        return False

    genomes_to_process = [genome_sources[
                              selected_assembly_id]] if selected_assembly_id and selected_assembly_id in genome_sources else genome_sources.values()

    tasks_to_run = []
    BLAST_FILE_KEYS = ['predicted_cds', 'predicted_protein']
    progress(10, _("正在检查需要预处理的文件..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False

    for genome_info in genomes_to_process:
        if check_cancel(): break
        for key in BLAST_FILE_KEYS:
            url_attr = f"{key}_url"
            if not hasattr(genome_info, url_attr) or not getattr(genome_info, url_attr):
                continue

            compressed_file = get_local_downloaded_file_path(config, genome_info, key)
            if not compressed_file or not os.path.exists(compressed_file):
                continue

            db_fasta_path = compressed_file.removesuffix('.gz')
            db_type = 'prot' if key == 'predicted_protein' else 'nucl'
            db_check_ext = '.phr' if db_type == 'prot' else '.nhr'

            if not os.path.exists(db_fasta_path + db_check_ext):
                tasks_to_run.append((compressed_file, db_fasta_path, db_type))

    if check_cancel(): logger.info(_("任务在文件检查后被取消。")); return False

    if not tasks_to_run:
        logger.info(_("所有BLAST数据库均已是最新状态，无需预处理。"))
        progress(100, _("无需处理，所有文件已是最新。"))
        return True

    total_tasks = len(tasks_to_run)
    progress(20, _("找到 {} 个BLAST数据库需要创建。").format(total_tasks))
    logger.info(_("找到 {} 个BLAST数据库需要创建。").format(total_tasks))
    success_count = 0

    for i, (compressed_file, db_fasta_path, db_type) in enumerate(tasks_to_run):
        if check_cancel():
            logger.info(_("任务被用户取消。"));
            progress(100, _("任务已取消。"));
            return False

        task_progress = 20 + int(((i + 1) / total_tasks) * 75)
        progress(task_progress, _("正在处理: {} ({}/{})").format(os.path.basename(compressed_file), i + 1, total_tasks))

        try:
            if compressed_file.endswith('.gz'):
                if not os.path.exists(db_fasta_path) or os.path.getmtime(compressed_file) > os.path.getmtime(
                        db_fasta_path):
                    logger.info(_("正在解压 {}...").format(os.path.basename(compressed_file)))
                    with gzip.open(compressed_file, 'rb') as f_in, open(db_fasta_path, 'wb') as f_out:
                        while True:
                            if check_cancel(): raise InterruptedError("Decompression cancelled")
                            chunk = f_in.read(1024 * 1024)
                            if not chunk: break
                            f_out.write(chunk)

            if check_cancel(): continue

            logger.info(_("正在为 {} 创建 {} 数据库...").format(os.path.basename(db_fasta_path), db_type))
            makeblastdb_cmd = ["makeblastdb", "-in", db_fasta_path, "-dbtype", db_type, "-out", db_fasta_path]

            result = subprocess.run(makeblastdb_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            logger.info(_("数据库 {} 创建成功。").format(os.path.basename(db_fasta_path)))
            success_count += 1

        except InterruptedError:
            logger.info(_("任务在解压时被取消: {}").format(os.path.basename(compressed_file)))
            return False
        except FileNotFoundError:
            logger.error(_(
                "错误: 'makeblastdb' 命令未找到。请确保 BLAST+ 已被正确安装并添加到了系统的 PATH 环境变量中。\n\n官方下载地址:\nhttps://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"))
            return False
        except subprocess.CalledProcessError as e:
            logger.error(_("创建数据库 {} 失败: {}").format(os.path.basename(db_fasta_path), e.stderr))
        except Exception as e:
            logger.error(_("处理文件 {} 时发生未知错误: {}").format(os.path.basename(compressed_file), e))

    logger.info(_("BLAST数据库预处理完成。成功创建 {}/{} 个数据库。").format(success_count, total_tasks))
    progress(100, _("预处理完成。"))
    return True