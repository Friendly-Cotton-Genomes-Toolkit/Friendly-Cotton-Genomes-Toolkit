# cotton_toolkit/pipelines.py

import gzip
import io
import logging
import os
import re
import threading
import time
import traceback
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import asdict
from typing import List, Dict, Any, Optional, Callable, Tuple

import pandas as pd

from .config.loader import get_genome_data_sources, get_local_downloaded_file_path
from .config.models import (
    MainConfig, HomologySelectionCriteria, GenomeSourceItem
)
from .core.ai_wrapper import AIWrapper
from .core.convertXlsx2csv import convert_excel_to_standard_csv
from .core.downloader import download_genome_data
from .core.gff_parser import get_genes_in_region, extract_gene_details, create_gff_database, get_gene_info_by_ids
from .core.homology_mapper import map_genes_via_bridge
from .tools.annotator import Annotator
from .tools.batch_ai_processor import process_single_csv_file
from .tools.enrichment_analyzer import run_go_enrichment, run_kegg_enrichment
from .tools.visualizer import plot_enrichment_bubble, plot_enrichment_bar, plot_enrichment_upset, plot_enrichment_cnet
from .utils.gene_utils import map_transcripts_to_genes

# 【核心修改】使用更健壮的方式来设置翻译函数
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



def create_homology_df(file_path: str, progress_callback: Optional[Callable] = None) -> pd.DataFrame:
    progress = progress_callback if progress_callback else lambda p, m: None
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"同源文件未找到: {file_path}")

    lowered_path = file_path.lower()
    header_keywords = ['Query', 'Match', 'Score', 'Exp', 'PID', 'evalue', 'identity']

    progress(0, f"正在打开文件: {os.path.basename(file_path)}...")
    with open(file_path, 'rb') as f_raw:
        is_gz = lowered_path.endswith('.gz')
        file_obj = gzip.open(f_raw, 'rb') if is_gz else f_raw
        try:
            progress(20, _("正在解析文件结构..."))
            if lowered_path.endswith(('.xlsx', '.xlsx.gz', '.xls', '.xls.gz')):
                xls = pd.ExcelFile(file_obj)
                all_sheets_data = []
                num_sheets = len(xls.sheet_names)
                for i, sheet_name in enumerate(xls.sheet_names):
                    progress(20 + int(60 * (i / num_sheets)), f"正在处理工作表: {sheet_name}...")
                    preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=5)
                    header_row_index = _find_header_row(preview_df, header_keywords)
                    if header_row_index is not None:
                        sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
                        sheet_df.dropna(how='all', inplace=True)
                        all_sheets_data.append(sheet_df)
                if not all_sheets_data:
                    raise ValueError("在Excel文件的任何工作表中都未能找到有效的表头或数据。")
                progress(80, _("正在合并所有工作表..."))
                return pd.concat(all_sheets_data, ignore_index=True)
            else:
                progress(50, _("正在读取文本数据..."))
                return pd.read_csv(file_obj, sep=r'\s+', engine='python', comment='#')
        except Exception as e:
            logger.error(f"读取同源文件 '{file_path}' 时出错: {e}")
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
                logger.warning(f"配置覆盖警告：在对象 {type(config_obj).__name__} 中找不到键 '{key}'。")



def run_homology_mapping(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: Optional[List[str]],
        region: Optional[Tuple[str, int, int]],
        output_csv_path: Optional[str],
        criteria_overrides: Optional[Dict[str, Any]],
        status_callback: Callable,
        calculate_target_locus: bool = False,
        progress_callback: Optional[Callable[[int, str], None]] = None, # 确保类型提示正确
        cancel_event: Optional[threading.Event] = None
) -> Optional[pd.DataFrame]:
    log = lambda msg, level="INFO": status_callback(msg, level)
    # 确保 progress_callback 是一个可调用的函数，即使没有提供也使用空函数
    progress = progress_callback if progress_callback else lambda p, m: None

    try:
        progress(5, _("步骤 1: 正在加载基因组源配置...")) # 更新进度
        log(_("步骤 1: 加载配置和同源数据..."), "INFO")
        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)
        bridge_species_name = "Arabidopsis_thaliana"  # 直接使用默认桥梁物种
        bridge_genome_info = genome_sources.get(bridge_species_name)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log(_("错误: 一个或多个指定的基因组名称无效。"), "ERROR")
            progress(100, _("任务终止：基因组配置错误。")) # 错误时也更新进度
            return None

        source_gene_ids = gene_ids
        if region:
            progress(15, _("步骤 2: 从染色体区域提取基因ID...")) # 更新进度
            gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
            # 从 locus_conversion 配置中获取路径
            gff_db_cache_dir = os.path.join(os.path.dirname(config.config_file_abs_path_),
                                            config.locus_conversion.gff_db_storage_dir)
            genes_in_region_list = get_genes_in_region(
                assembly_id=source_assembly_id, gff_filepath=gff_path, db_storage_dir=gff_db_cache_dir, region=region,
                force_db_creation=False, status_callback=log  # 使用安全的默认值
            )
            if not genes_in_region_list:
                log(f"在区域 {region} 中未找到任何基因。", "WARNING")
                progress(100, _("任务终止：区域内无基因。"))
                return None
            source_gene_ids = [gene['gene_id'] for gene in genes_in_region_list]

        if not source_gene_ids:
            log(_("错误: 输入的基因列表为空。"), "ERROR")
            progress(100, _("任务终止：基因列表为空。"))
            return None

        progress(30, _("步骤 3: 加载同源文件...")) # 更新进度
        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')
        # 调用 create_homology_df 时传递 progress_callback，并计算更细致的进度
        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(30 + int(p * 0.3), f"加载源到桥梁文件: {m}")) # 30%-60%
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(60 + int(p * 0.2), f"加载桥梁到目标文件: {m}")) # 60%-80%


        log(_("步骤 4: 通过桥梁物种执行基因映射..."), "INFO")
        s2b_criteria = HomologySelectionCriteria()
        b2t_criteria = HomologySelectionCriteria()
        homology_columns = {
            "query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"
        }

        # 应用来自UI的覆盖参数
        s2b_dict = s2b_criteria.model_dump()
        b2t_dict = b2t_criteria.model_dump()
        if criteria_overrides:
            for key, value in criteria_overrides.items():
                if value is not None:
                    if key in s2b_dict:
                        s2b_dict[key] = value
                    if key in b2t_dict:
                        b2t_dict[key] = value

        # map_genes_via_bridge 内部应该有自己的进度报告
        mapped_df, failed_genes = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=bridge_species_name,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=s2b_dict,
            selection_criteria_b_to_t=b2t_dict,
            homology_columns=homology_columns,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            status_callback=status_callback,
            progress_callback=lambda p, m: progress(80 + int(p * 0.1), f"基因映射: {m}"), # 80%-90%
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            log("INFO: 任务在基因映射阶段被用户取消。", "INFO")
            progress(100, _("任务已取消。"))
            return None

        log(_("步骤 5: 保存映射结果..."), "INFO") # 从步骤4改为5
        progress(95, _("正在保存映射结果...")) # 更新进度
        if output_csv_path:
            source_locus_str = f"{source_assembly_id} | {region[0]}:{region[1]}-{region[2]}" if region else f"{source_assembly_id} | {len(source_gene_ids)} genes"
            header_line1 = f"# 源基因组的位点（即用户输入的位点）: {source_locus_str}\n"

            target_locus_summary = ""
            if calculate_target_locus:
                log("正在计算目标概要位点...", "INFO")
                # get_gene_info_by_ids 内部需要支持 progress_callback
                # 为了保持简洁，这里只报告总体进度，不再深入到 get_gene_info_by_ids 内部
                # 如果 get_gene_info_by_ids 没有 progress_callback，则需要修改它
                if mapped_df is not None and not mapped_df.empty:
                    target_gene_ids_list = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
                    if target_gene_ids_list:
                        target_gff_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')
                        gff_db_cache_dir = os.path.join(os.path.dirname(config.config_file_abs_path_),
                                                        config.locus_conversion.gff_db_storage_dir) # 这里的 config.integration_pipeline 应该改为 config.locus_conversion
                        target_genes_details_df = get_gene_info_by_ids(
                            assembly_id=target_assembly_id, gff_filepath=target_gff_path,
                            db_storage_dir=gff_db_cache_dir, gene_ids=target_gene_ids_list, status_callback=log
                            # progress_callback 可以在这里传递，如果 get_gene_info_by_ids 支持
                        )

                        if target_genes_details_df is not None and not target_genes_details_df.empty:
                            locus_bounds = target_genes_details_df.groupby('chrom').agg(min_start=('start', 'min'),
                                                                                        max_end=('end',
                                                                                                 'max')).reset_index()
                            summary_parts = [f"{row['chrom']}:{row['min_start']}-{row['max_end']}" for _V, row in
                                             locus_bounds.iterrows()]
                            target_locus_summary = " | " + (
                                ", ".join(summary_parts) if summary_parts else "无具体位点信息")
                else:
                    target_locus_summary = " | 无映射结果"

            header_line2 = f"# 目标基因组的位点（即转换后的大体的位点）: {target_assembly_id}{target_locus_summary}\n"

            with open(output_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(header_line1)
                f.write(header_line2)
                f.write("#\n")

                if mapped_df is not None and not mapped_df.empty:
                    mapped_df.to_csv(f, index=False, lineterminator='\n')
                else:
                    f.write("# 未找到任何成功的同源匹配。\n")

                if failed_genes:
                    f.write("\n\n")
                    f.write("# --- 匹配失败的源基因 ---\n")
                    failed_df = pd.DataFrame({
                        'Failed_Source_Gene_ID': failed_genes,
                        'Reason': "未能在目标基因组中找到满足所有筛选条件（如E-value, PID, 严格模式等）的同源基因。"
                    })
                    failed_df.to_csv(f, index=False, lineterminator='\n')

            log(f"结果已成功保存到: {output_csv_path}", "INFO")
        else:
            log("未提供输出路径，跳过保存文件。", "INFO")

        progress(100, _("同源映射流程完成。")) # 结束时更新进度
        return mapped_df

    except Exception as e:
        log(f"流水线执行过程中发生意外错误: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        progress(100, _("任务因错误而终止。")) # 错误时也更新进度
        return None


def run_locus_conversion(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        region: Tuple[str, int, int],
        output_path: str,
        status_callback: Callable,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        criteria_overrides: Optional[Dict[str, Any]] = None,
        **kwargs
) -> Optional[str]:
    log = lambda msg, level="INFO": status_callback(msg, level)
    progress = progress_callback if progress_callback else lambda p, m: None

    try:
        progress(5, _("流程开始，正在加载基因组配置..."))
        log("步骤1: 加载配置...", "INFO")
        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)

        bridge_species_name = "Arabidopsis thaliana"
        bridge_genome_info = genome_sources.get(bridge_species_name)
        if not bridge_genome_info:
            bridge_genome_info = genome_sources.get(bridge_species_name.replace(' ', '_'))

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log(f"错误: 无法为 {source_assembly_id}, {target_assembly_id} 或 {bridge_species_name} 找到配置。", "ERROR")
            progress(100, _("任务终止：基因组配置错误。"))
            return None

        progress(15, _("正在从GFF文件中提取基因..."))
        gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        gff_db_cache_dir = config.locus_conversion.gff_db_storage_dir
        os.makedirs(gff_db_cache_dir, exist_ok=True)

        source_gene_list = get_genes_in_region(
            assembly_id=source_assembly_id, gff_filepath=gff_path,
            db_storage_dir=gff_db_cache_dir, region=region,
            status_callback=log,
            gene_id_regex=source_genome_info.gene_id_regex,
            progress_callback=lambda p, m: progress(15 + int(p * 0.1), f"提取基因: {m}") # 15%-25%
        )
        if not source_gene_list:
            log(f"在区域 {region} 中未找到任何基因。", "WARNING")
            progress(100, _("任务终止：区域内无基因。"))
            return "在指定区域未找到任何基因。"
        source_gene_ids = [gene['gene_id'] for gene in source_gene_list]

        progress(30, _("正在加载同源文件..."))
        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not s_to_b_homology_file or not os.path.exists(
                s_to_b_homology_file) or not b_to_t_homology_file or not os.path.exists(b_to_t_homology_file):
            log(f"错误: 缺少必要的同源文件。请先为相关基因组下载数据。", "ERROR")
            progress(100, _("任务终止：缺少同源文件。"))
            return None

        progress(40, _("正在解析源到桥梁的同源文件..."))
        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(40 + int(p * 0.2), f"解析同源文件 (S->B): {m}")) # 40%-60%
        progress(60, _("正在解析桥梁到目标的同源文件..."))
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(60 + int(p * 0.1), f"解析同源文件 (B->T): {m}")) # 60%-70%

        homology_columns = {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"}
        if homology_columns['query'] not in source_to_bridge_homology_df.columns:
            raise ValueError(
                f"配置错误: 在同源文件中找不到查询列 '{homology_columns['query']}'。可用列: {source_to_bridge_homology_df.columns.tolist()}")

        selection_criteria_s_to_b = {"top_n": 1, "evalue_threshold": 1e-10}
        selection_criteria_b_to_t = {"top_n": 1, "evalue_threshold": 1e-10}

        progress(75, _("正在执行核心同源映射..."))
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
            status_callback=status_callback,
            progress_callback=lambda p, m: progress(75 + int(p * 0.15), f"基因映射: {m}"), # 75%-90%
            cancel_event=kwargs.get('cancel_event')
        )

        if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
            log("任务在同源映射阶段被用户取消。", "INFO")
            progress(100, _("任务已取消。"))
            return None

        progress(95, _("映射完成，正在整理并保存结果..."))
        output_dir = os.path.dirname(output_path)
        if output_dir: os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(f"# Source Locus: {source_assembly_id} | {region[0]}:{region[1]}-{region[2]}\n")
            f.write(f"# Target Assembly: {target_assembly_id}\n")
            f.write(
                f"# Failed to map {len(failed_genes)} genes: {','.join(failed_genes) if failed_genes else 'None'}\n")
            f.write("#\n# --- Detailed Mapping Results ---\n")
            if mapped_df is not None and not mapped_df.empty:
                mapped_df.to_csv(f, index=False, lineterminator='\n')
            else:
                f.write("# No successful homologous matches found.\n")

        progress(100, _("全部完成！"))
        success_message = f"位点转换结果已成功保存到:\n{os.path.abspath(output_path)}"
        log(success_message, "INFO")
        return success_message

    except Exception as e:
        log(f"位点转换流程出错: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
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
        status_callback: Callable,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        output_file: Optional[str] = None
):
    batch_cfg = config.batch_ai_processor
    _update_config_from_overrides(batch_cfg, cli_overrides)
    progress = progress_callback if progress_callback else lambda p, m: None
    log = lambda msg, level="INFO": status_callback(msg, level)

    progress(0, _("AI任务流程开始..."))
    log(_("AI任务流程开始..."), "INFO")

    progress(5, _("初始化AI客户端..."))
    ai_cfg = config.ai_services
    provider_name = ai_cfg.default_provider
    provider_cfg_obj = ai_cfg.providers.get(provider_name)
    if not provider_cfg_obj:
        log(f"错误: 在配置中未找到默认AI服务商 '{provider_name}' 的设置。", "ERROR")
        progress(100, _("任务终止：AI服务配置错误。"))
        return
    api_key = provider_cfg_obj.api_key
    model = provider_cfg_obj.model
    base_url = provider_cfg_obj.base_url
    if not api_key or "YOUR_API_KEY" in api_key:
        log(f"错误: 请在配置文件中为服务商 '{provider_name}' 设置一个有效的API Key。", "ERROR")
        progress(100, _("任务终止：API Key 未设置。"))
        return

    proxies_to_use = None
    if ai_cfg.use_proxy_for_ai:
        if config.proxies and (config.proxies.http or config.proxies.https):
            proxies_to_use = config.proxies.model_dump(exclude_none=True)
            log(f"INFO: AI服务将使用代理: {proxies_to_use}")
        else:
            log("WARNING: AI代理开关已打开，但配置文件中未设置代理地址。")

    progress(10, _("正在初始化AI客户端..."))
    log(_("正在初始化AI客户端... 服务商: {}, 模型: {}").format(provider_name, model))
    ai_client = AIWrapper(
        provider=provider_name,
        api_key=api_key,
        model=model,
        base_url=base_url,
        proxies=proxies_to_use,
        max_workers=config.batch_ai_processor.max_workers
    )
    project_root = os.path.dirname(config.config_file_abs_path_) if hasattr(config, 'config_file_abs_path_') and config.config_file_abs_path_ else '.'
    output_dir_name = getattr(config.batch_ai_processor, 'output_dir_name', 'ai_results')
    output_dir = os.path.join(project_root, output_dir_name)
    os.makedirs(output_dir, exist_ok=True)
    prompt_to_use = custom_prompt_template
    if not prompt_to_use:
        prompt_to_use = config.ai_prompts.translation_prompt if task_type == 'translate' else config.ai_prompts.analysis_prompt

    progress(15, _("正在处理CSV文件并调用AI服务..."))
    # process_single_csv_file 内部应有自己的进度更新
    process_single_csv_file(
        client=ai_client,
        input_csv_path=input_file,
        output_csv_directory=output_dir,
        source_column_name=source_column,
        new_column_name=new_column,
        user_prompt_template=prompt_to_use,
        task_identifier=f"{os.path.basename(input_file)}_{task_type}",
        max_row_workers=batch_cfg.max_workers,
        status_callback=status_callback,
        # 将 progress_callback 传递给子函数，并调整其百分比范围
        progress_callback=lambda p, m: progress(15 + int(p * 0.8), f"AI处理: {m}"), # 15%-95%
        cancel_event=cancel_event,
        output_csv_path=output_file
    )

    if cancel_event and cancel_event.is_set():
        log("INFO: 任务已被用户取消。", "INFO")
        progress(100, _("任务已取消。"))
        return

    progress(100, _("任务完成。"))
    log(_("AI任务流程成功完成。"), "INFO")


def run_functional_annotation(
        config: MainConfig,
        source_genome: str,
        target_genome: str,
        bridge_species: str,
        annotation_types: List[str],
        status_callback: Callable[[str, str], None],
        output_dir: Optional[str] = None,
        output_path: Optional[str] = None,
        gene_list_path: Optional[str] = None,
        gene_ids: Optional[List[str]] = None,
        custom_db_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> None:
    log = lambda msg, level="INFO": status_callback(msg, level)
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("准备输入基因列表..."))
    source_gene_ids = []
    if gene_ids:
        source_gene_ids = list(set(gene_ids))
        log(f"INFO: 从参数直接获取了 {len(source_gene_ids)} 个唯一基因ID。")
    elif gene_list_path and os.path.exists(gene_list_path):
        try:
            progress(5, _("正在从文件读取基因列表..."))
            log(f"INFO: 正在从文件 '{os.path.basename(gene_list_path)}' 中读取基因列表...")
            study_genes_df = pd.read_csv(gene_list_path)
            source_gene_ids = study_genes_df.iloc[:, 0].dropna().unique().tolist()
            log(f"INFO: 从文件中读取了 {len(source_gene_ids)} 个唯一基因ID。")
        except Exception as e:
            log(f"读取基因列表文件时出错: {e}", "ERROR")
            progress(100, _("任务终止：读取基因列表失败。"))
            return
    else:
        log("错误: 必须提供 'gene_ids' 或有效的 'gene_list_path' 参数之一。", "ERROR")
        progress(100, _("任务终止：缺少基因输入。"))
        return

    if not source_gene_ids:
        log("输入的基因列表为空，流程终止。", "ERROR")
        progress(100, _("任务终止：基因列表为空。"))
        return

    genes_to_annotate = source_gene_ids
    original_to_target_map_df = pd.DataFrame({'Source_Gene_ID': source_gene_ids})

    progress(10, _("检查是否需要同源映射..."))
    if source_genome != target_genome:
        log(f"源基因组 ({source_genome}) 与目标基因组 ({target_genome}) 不同，准备进行同源转换。", "INFO")

        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_genome)
        target_genome_info = genome_sources.get(target_genome)
        bridge_genome_info = genome_sources.get(bridge_species)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log("一个或多个基因组名称无效，无法找到配置信息。", "ERROR")
            progress(100, _("任务终止：基因组配置错误。"))
            return

        progress(20, _("加载同源数据文件..."))
        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not all([s_to_b_homology_file, b_to_t_homology_file, os.path.exists(s_to_b_homology_file),
                    os.path.exists(b_to_t_homology_file)]):
            log("缺少必要的同源文件，无法进行转换。请先下载数据。", "ERROR")
            progress(100, _("任务终止：缺少同源文件。"))
            return

        progress(25, _("正在解析源到桥梁的同源文件..."))
        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(25 + int(p * 0.1),
                                                                                                  f"加载同源数据: {m}"))  # 25%-35%
        progress(35, _("正在解析桥梁到目标的同源文件..."))
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(35 + int(p * 0.1),
                                                                                                  f"加载同源数据: {m}"))  # 35%-45%

        selection_criteria_s_to_b = HomologySelectionCriteria().model_dump()
        selection_criteria_b_to_t = HomologySelectionCriteria().model_dump()
        homology_columns = {
            "query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"
        }

        progress(50, _("正在通过桥梁物种进行基因映射..."))
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
            status_callback=status_callback,
            progress_callback=lambda p, m: progress(50 + int(p * 0.2), f"基因映射: {m}"),  # 50%-70%
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            log("任务在同源映射阶段被用户取消。", "INFO")
            progress(100, _("任务已取消。"))
            return

        if mapped_df is None or mapped_df.empty:
            log("同源转换未能映射到任何基因，流程终止。", "WARNING")
            progress(100, _("任务终止：同源映射失败。"))
            return

        genes_to_annotate = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
        original_to_target_map_df = mapped_df[['Source_Gene_ID', 'Target_Gene_ID']]

    progress(75, _("初始化注释器..."))
    genome_sources = get_genome_data_sources(config, logger_func=log)
    target_genome_info = genome_sources.get(target_genome)
    if not target_genome_info:
        log(f"错误：无法为目标基因组 {target_genome} 找到配置信息。", "ERROR")
        progress(100, _("任务终止：目标基因组配置错误。"))
        return

    # Annotator 内部应该也使用 progress_callback
    annotator = Annotator(
        main_config=config,
        genome_id=target_genome,
        genome_info=target_genome_info,
        status_callback=status_callback,
        progress_callback=lambda p, m: progress(75 + int(p * 0.15), f"执行注释: {m}"),  # 75%-90%
        custom_db_dir=custom_db_dir
    )

    progress(90, _("正在执行功能注释..."))
    result_df = annotator.annotate_genes(genes_to_annotate, annotation_types)

    if cancel_event and cancel_event.is_set():
        log("任务在注释阶段被用户取消。", "INFO")
        progress(100, _("任务已取消。"))
        return

    progress(95, _("整理并保存结果..."))
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
            log("错误: 必须提供 output_dir 或 output_path 参数之一用于保存结果。", "ERROR")
            progress(100, _("任务终止：未提供输出路径。"))
            return

        try:
            final_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
            log(f"注释成功！结果已保存至: {final_output_path}", "INFO")
        except Exception as e:
            log(f"保存结果到 {final_output_path} 时发生错误: {e}", "ERROR")
            progress(100, _("任务终止：保存结果失败。"))
            return

    else:
        log("注释完成，但没有生成任何结果。", "WARNING")
        progress(100, _("任务完成：无结果。"))

    progress(100, _("功能注释流程结束。"))


def run_gff_lookup(
        config: MainConfig,
        assembly_id: str,
        gene_ids: Optional[List[str]] = None,
        region: Optional[Tuple[str, int, int]] = None,
        output_csv_path: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    log = status_callback if status_callback else lambda msg, level="INFO": print(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: None

    if not gene_ids and not region:
        log(_("错误: 必须提供基因ID列表或染色体区域进行查询。"), "ERROR")
        progress(100, _("任务终止：缺少查询参数。"))
        return False

    progress(0, _("流程开始，正在初始化配置..."))
    log(_("开始GFF基因查询流程..."), "INFO")

    project_root = '.'
    if hasattr(config, 'config_file_abs_path_') and config.config_file_abs_path_:
        project_root = os.path.dirname(config.config_file_abs_path_)

    genome_sources = get_genome_data_sources(config, logger_func=log)
    selected_genome_info = genome_sources.get(assembly_id)
    if not selected_genome_info:
        log(_("错误: 基因组 '{}' 未在基因组源列表中找到。").format(assembly_id), "ERROR")
        progress(100, _("任务终止：基因组配置错误。"))
        return False

    gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')
    if not gff_file_path or not os.path.exists(gff_file_path):
        log(_("错误: 未找到基因组 '{}' 的GFF文件。请先下载数据。").format(assembly_id), "ERROR")
        progress(100, _("任务终止：GFF文件缺失。"))
        return False

    progress(20, _("正在准备GFF数据库..."))
    gff_db_dir = config.locus_conversion.gff_db_storage_dir
    os.makedirs(gff_db_dir, exist_ok=True)

    force_creation = False # 保持为False，除非有UI选项控制

    results_df = pd.DataFrame()
    progress(40, _("正在数据库中查询..."))
    if gene_ids:
        log(_("按基因ID查询 {} 个基因...").format(len(gene_ids)), "INFO")
        results_df = get_gene_info_by_ids(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, gene_ids=gene_ids,
            force_db_creation=force_creation, status_callback=log,
            progress_callback=lambda p, m: progress(40 + int(p * 0.4), f"查询基因ID: {m}") # 40%-80%
        )
    elif region:
        chrom, start, end = region
        log(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end), "INFO")
        genes_in_region_list = get_genes_in_region(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, region=region,
            force_db_creation=force_creation, status_callback=log,
            progress_callback=lambda p, m: progress(40 + int(p * 0.4), f"查询区域基因: {m}") # 40%-80%
        )
        if genes_in_region_list:
            results_df = pd.DataFrame(genes_in_region_list)

    if cancel_event and cancel_event.is_set():
        log("INFO: 任务已被用户取消。", "INFO")
        progress(100, _("任务已取消。"))
        return False

    progress(90, _("查询完成，正在整理结果..."))
    if results_df.empty:
        log(_("未找到任何符合条件的基因。"), "WARNING")
        progress(100, _("任务完成：未找到结果。"))
    else:
        log(_("查询完成，找到 {} 个基因记录。").format(len(results_df)), "INFO")

        final_output_path = output_csv_path
        if not final_output_path:
            output_dir = os.path.join(project_root, "gff_query_results")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            query_type = "genes" if gene_ids else f"region_{region[0]}_{region[1]}_{region[2]}"
            final_output_path = os.path.join(output_dir, f"gff_query_{assembly_id}_{query_type}_{timestamp}.csv")

        try:
            results_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
            log(_("GFF基因查询结果已保存到: {}").format(final_output_path), "INFO")
        except Exception as e:
            log(_("保存结果时出错: {}").format(e), "ERROR")
            progress(100, _("任务终止：保存结果失败。"))
            return False

    progress(100, _("GFF查询流程结束。"))
    return True


def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
):
    log = lambda msg, level="INFO": status_callback(msg, level)
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("下载流程开始..."))
    log("INFO: 下载流程开始...")

    downloader_cfg = config.downloader
    genome_sources = get_genome_data_sources(config, logger_func=log)
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
            log(f"INFO: 本次下载将使用代理: {proxies_to_use}")
        else:
            log("WARNING: 下载代理开关已打开，但配置文件中未设置代理地址。")

    progress(5, _("正在准备下载任务列表..."))
    log(f"INFO: 将尝试下载的基因组版本: {', '.join(versions_to_download)}")

    all_download_tasks = []
    if not file_keys_to_process:
        all_possible_keys = [f.name.replace('_url', '') for f in GenomeSourceItem.model_fields.values() if
                             f.name.endswith('_url')]
        log(f"DEBUG: 未从UI指定文件类型，将尝试检查所有可能的类型: {all_possible_keys}")
    else:
        all_possible_keys = file_keys_to_process
        log(f"DEBUG: 将根据UI的选择，精确下载以下文件类型: {all_possible_keys}")

    for version_id in versions_to_download:
        genome_info = genome_sources.get(version_id)
        if not genome_info:
            log(f"WARNING: 在基因组源中未找到版本 '{version_id}'，已跳过。")
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

    if not all_download_tasks:
        log("WARNING: 根据您的选择，没有找到任何有效的URL可供下载。")
        progress(100, _("任务完成：无文件可下载。"))
        return

    progress(10, f"找到 {len(all_download_tasks)} 个文件需要下载。")
    log(f"INFO: 准备下载 {len(all_download_tasks)} 个文件...")

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
                status_callback=log,
                cancel_event=cancel_event,
            ): task for task in all_download_tasks
        }

        total_tasks = len(future_to_task)
        current_completed_tasks = 0
        for future in as_completed(future_to_task):
            if cancel_event and cancel_event.is_set():
                log("INFO: 下载任务已被用户取消。")
                progress(100, _("任务已取消。"))
                break

            task_info = future_to_task[future]
            try:
                if future.result():
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as exc:
                log(f"ERROR: 下载 {task_info['version_id']} 的 {task_info['file_key']} 文件时发生严重错误: {exc}",
                    "ERROR")
                failed_downloads += 1
            finally:
                current_completed_tasks += 1
                # 将进度映射到 10% 到 95% 之间
                progress_percentage = 10 + int((current_completed_tasks / total_tasks) * 85)
                progress(progress_percentage,
                         f"{_('总体下载进度')} ({current_completed_tasks}/{total_tasks}) - {task_info['version_id']} {task_info['file_key']}")

    log(f"INFO: 所有指定的下载任务已完成。成功: {successful_downloads}, 失败: {failed_downloads}。")
    progress(100, _("下载流程完成。"))


def run_enrichment_pipeline(
        config: MainConfig,
        assembly_id: str,
        study_gene_ids: List[str],
        analysis_type: str,
        plot_types: List[str],
        output_dir: str,
        status_callback: Optional[Callable] = None,
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
) -> Optional[List[str]]:
    log = lambda msg, level="INFO": status_callback(msg, level)
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("富集分析与可视化流程启动。"))
    log(f"INFO: {analysis_type.upper()} 富集与可视化流程启动。")

    if collapse_transcripts:
        original_count = len(study_gene_ids)
        progress(5, _("正在将RNA合并到基因..."))
        log("INFO: 正在将RNA合并到基因...")
        study_gene_ids = map_transcripts_to_genes(study_gene_ids)
        log(f"INFO: 基因列表已从 {original_count} 个RNA合并为 {len(study_gene_ids)} 个唯一基因。")

    try:
        progress(10, _("正在获取基因组信息..."))
        genome_sources = get_genome_data_sources(config, logger_func=log)
        genome_info = genome_sources.get(assembly_id)
        if not genome_info:
            log(f"ERROR: 无法在配置中找到基因组 '{assembly_id}'。")
            progress(100, _("任务终止：基因组配置错误。"))
            return None
        gene_id_regex = genome_info.gene_id_regex if hasattr(genome_info, 'gene_id_regex') else None
    except Exception as e:
        log(f"ERROR: 获取基因组源数据时失败: {e}")
        progress(100, _("任务终止：获取基因组信息失败。"))
        return None

    os.makedirs(output_dir, exist_ok=True)
    enrichment_df = None

    if analysis_type == 'go':
        progress(20, _("正在执行GO富集分析..."))
        gaf_path = get_local_downloaded_file_path(config, genome_info, 'GO')
        if not gaf_path or not os.path.exists(gaf_path):
            log(f"ERROR: 未找到 '{assembly_id}' 的GO注释关联文件 (GAF)。请先下载数据。")
            progress(100, _("任务终止：缺少GO注释文件。"))
            return None
        # Assuming run_go_enrichment can take progress_callback
        enrichment_df = run_go_enrichment(study_gene_ids=study_gene_ids, go_annotation_path=gaf_path,
                                          output_dir=output_dir, status_callback=log, gene_id_regex=gene_id_regex,
                                          progress_callback=lambda p, m: progress(20 + int(p * 0.4), f"GO富集: {m}")) # 20%-60%

    elif analysis_type == 'kegg':
        progress(20, _("正在执行KEGG富集分析..."))
        pathways_path = get_local_downloaded_file_path(config, genome_info, 'KEGG_pathways')
        if not pathways_path or not os.path.exists(pathways_path):
            log(f"ERROR: 未找到 '{assembly_id}' 的KEGG通路文件。请先下载数据。")
            progress(100, _("任务终止：缺少KEGG通路文件。"))
            return None
        # Assuming run_kegg_enrichment can take progress_callback
        enrichment_df = run_kegg_enrichment(study_gene_ids=study_gene_ids, kegg_pathways_path=pathways_path,
                                            output_dir=output_dir, status_callback=log, gene_id_regex=gene_id_regex,
                                            progress_callback=lambda p, m: progress(20 + int(p * 0.4), f"KEGG富集: {m}")) # 20%-60%


    else:
        log(f"ERROR: 未知的分析类型 '{analysis_type}'。")
        progress(100, _("任务终止：分析类型未知。"))
        return None

    if cancel_event and cancel_event.is_set():
        log("INFO: 任务在分析后被取消。")
        progress(100, _("任务已取消。"))
        return None

    if enrichment_df is None or enrichment_df.empty:
        log("WARNING: 富集分析未发现任何显著结果，流程终止。")
        progress(100, _("任务完成：无显著结果。"))
        return []

    progress(60, _("富集分析完成，正在生成图表..."))

    generated_plots = []
    total_plot_types = len(plot_types)
    current_plot_index = 0

    plot_kwargs_common = {
        'top_n': top_n, 'sort_by': sort_by, 'show_title': show_title, 'width': width, 'height': height
    }

    if analysis_type == 'go' and 'Namespace' in enrichment_df.columns:
        namespaces = enrichment_df['Namespace'].unique()
        for ns in namespaces:
            df_sub = enrichment_df[enrichment_df['Namespace'] == ns]
            if df_sub.empty: continue

            title_ns = f"GO Enrichment - {ns}"
            file_prefix_ns = f"go_enrichment_{ns}"

            if 'bubble' in plot_types:
                progress_each_plot = (40 / total_plot_types) / len(namespaces) if total_plot_types > 0 else 0
                current_plot_index += 1
                progress(60 + int(progress_each_plot * (current_plot_index-1)), f"生成气泡图 ({ns})...")
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_bubble.{file_format}")
                plot_path = plot_enrichment_bubble(enrichment_df=df_sub, output_path=output_path, title=title_ns,
                                                   **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            if 'bar' in plot_types:
                progress_each_plot = (40 / total_plot_types) / len(namespaces) if total_plot_types > 0 else 0
                current_plot_index += 1
                progress(60 + int(progress_each_plot * (current_plot_index-1)), f"生成条形图 ({ns})...")
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_bar.{file_format}")
                plot_path = plot_enrichment_bar(enrichment_df=df_sub, output_path=output_path, title=title_ns,
                                                gene_log2fc_map=gene_log2fc_map, **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            if 'upset' in plot_types:
                progress_each_plot = (40 / total_plot_types) / len(namespaces) if total_plot_types > 0 else 0
                current_plot_index += 1
                progress(60 + int(progress_each_plot * (current_plot_index-1)), f"生成Upset图 ({ns})...")
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_upset.{file_format}")
                plot_path = plot_enrichment_upset(enrichment_df=df_sub, output_path=output_path, top_n=top_n)
                if plot_path: generated_plots.append(plot_path)

            if 'cnet' in plot_types:
                progress_each_plot = (40 / total_plot_types) / len(namespaces) if total_plot_types > 0 else 0
                current_plot_index += 1
                progress(60 + int(progress_each_plot * (current_plot_index-1)), f"生成网络图(Cnet) ({ns})...")
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_cnet.{file_format}")
                plot_path = plot_enrichment_cnet(enrichment_df=df_sub, output_path=output_path, top_n=top_n,
                                                 gene_log2fc_map=gene_log2fc_map)
                if plot_path: generated_plots.append(plot_path)
    else: # 非GO分析，不分命名空间
        for plot_type in plot_types:
            progress_each_plot = (40 / total_plot_types) if total_plot_types > 0 else 0
            current_plot_index += 1
            current_progress_val = 60 + int(progress_each_plot * (current_plot_index-1))

            title = f"{analysis_type.upper()} Enrichment"
            file_prefix = f"{analysis_type}_enrichment"

            if plot_type == 'bubble':
                progress(current_progress_val, _("生成气泡图..."))
                output_path = os.path.join(output_dir, f"{file_prefix}_bubble.{file_format}")
                plot_path = plot_enrichment_bubble(enrichment_df=enrichment_df, output_path=output_path, title=title,
                                                   **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            elif plot_type == 'bar':
                progress(current_progress_val, _("生成条形图..."))
                output_path = os.path.join(output_dir, f"{file_prefix}_bar.{file_format}")
                plot_path = plot_enrichment_bar(enrichment_df=enrichment_df, output_path=output_path, title=title,
                                                gene_log2fc_map=gene_log2fc_map, **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            elif plot_type == 'upset':
                progress(current_progress_val, _("生成Upset图..."))
                output_path = os.path.join(output_dir, f"{file_prefix}_upset.{file_format}")
                plot_path = plot_enrichment_upset(enrichment_df=enrichment_df, output_path=output_path, top_n=top_n)
                if plot_path: generated_plots.append(plot_path)

            elif plot_type == 'cnet':
                progress(current_progress_val, _("生成网络图(Cnet)..."))
                output_path = os.path.join(output_dir, f"{file_prefix}_cnet.{file_format}")
                plot_path = plot_enrichment_cnet(enrichment_df=enrichment_df, output_path=output_path, top_n=top_n,
                                                 gene_log2fc_map=gene_log2fc_map)
                if plot_path: generated_plots.append(plot_path)

    progress(100, _("所有图表已生成。"))
    log(f"流程完成。在 '{output_dir}' 中成功生成 {len(generated_plots)} 个图表。", "INFO")

    return generated_plots




def run_preprocess_annotation_files(
        config: MainConfig,
        status_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: None

    progress(0, _("开始预处理注释文件（转换为CSV）..."))
    log("开始预处理注释文件（转换为CSV）...", "INFO")

    progress(5, _("正在加载基因组源数据..."))
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        log("未能加载基因组源数据。", "ERROR")
        progress(100, _("任务终止：未能加载基因组源。"))
        return False

    tasks_to_run = []
    ALL_ANNO_KEYS = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs']
    progress(10, _("正在检查需要预处理的文件..."))
    for genome_info in genome_sources.values():
        for key in ALL_ANNO_KEYS:
            source_path = get_local_downloaded_file_path(config, genome_info, key)
            if source_path and os.path.exists(source_path) and source_path.lower().endswith(('.xlsx', '.xlsx.gz')):
                base_path = source_path.replace('.xlsx.gz', '').replace('.xlsx', '')
                output_path = base_path + '.csv'
                # 检查CSV是否存在或Excel是否比CSV新
                if not os.path.exists(output_path) or os.path.getmtime(source_path) > os.path.getmtime(output_path):
                    tasks_to_run.append((source_path, output_path))

    if not tasks_to_run:
        log("所有注释文件均已是最新状态，无需预处理。", "INFO")
        progress(100, _("无需处理，所有文件已是最新。"))
        return True

    total_tasks = len(tasks_to_run)
    progress(20, f"找到 {total_tasks} 个文件需要进行预处理。")
    log(f"找到 {total_tasks} 个文件需要进行预处理。", "INFO")
    success_count = 0

    for i, (source, output) in enumerate(tasks_to_run):
        if cancel_event and cancel_event.is_set():
            log("任务被用户取消。", "INFO")
            progress(100, _("任务已取消。"))
            return False

        # 将进度映射到 20% 到 95% 之间
        progress_percentage = 20 + int(((i + 1) / total_tasks) * 75)
        progress(progress_percentage, f"正在转换: {os.path.basename(source)} ({i+1}/{total_tasks})")

        # convert_excel_to_standard_csv 内部也应该有自己的进度回调，这里不再嵌套
        if convert_excel_to_standard_csv(source, output, log):
            success_count += 1

    log(f"预处理完成。成功转换 {success_count}/{total_tasks} 个文件。", "INFO")
    progress(100, _("预处理完成。"))
    return True


def run_xlsx_to_csv(
        excel_path: str,
        output_csv_path: str,
        status_callback: Optional[Callable[[str, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs) -> bool:
    """
    流水线函数：将一个Excel文件转换为标准的CSV文件。
    """
    log = status_callback if status_callback else lambda msg, level="INFO": print(f"[{level}] {msg}")
    try:
        log(f"开始将 '{os.path.basename(excel_path)}' 转换为CSV...", "INFO")
        success = convert_excel_to_standard_csv(
            excel_path=excel_path,
            output_csv_path=output_csv_path,
            status_callback=log,
            cancel_event=cancel_event
        )
        if success:
            log(f"成功将文件转换为CSV格式: {output_csv_path}", "INFO")
        else:
            log(f"转换文件时失败。", "ERROR")
        return success
    except Exception as e:
        log(f"执行Excel到CSV转换流水线时发生错误: {e}", "ERROR")
        return False





