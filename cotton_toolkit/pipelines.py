# cotton_toolkit/pipelines.py

import gzip
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
# 核心模块导入
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

# --- 国际化和日志设置 ---
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines")

bridge_id_regex = r'(AT[1-5MC]G\d{5})'




def convert_all_xlsx_in_folder_to_csv(folder_path: str, log: Callable) -> None:
    """
    遍历指定文件夹中的所有 .xlsx 或 .xlsx.gz 文件，并转换为 .csv 文件。
    """
    log(f"INFO: 正在转换文件夹 '{folder_path}' 中的所有Excel文件到CSV。")
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith((".xlsx", ".xlsx.gz")):
                excel_path = os.path.join(root, file)
                # 定义CSV输出路径：在同目录下，文件名不变，后缀改为.csv
                if file.lower().endswith(".xlsx.gz"):
                    csv_filename = os.path.splitext(os.path.splitext(file)[0])[0] + ".csv"
                else:
                    csv_filename = os.path.splitext(file)[0] + ".csv"
                output_csv_path = os.path.join(root, csv_filename)

                if os.path.exists(output_csv_path):
                    log(f"INFO: 发现已转换的CSV文件，跳过: {csv_filename}")
                    continue

                log(f"INFO: 正在转换 {file} 到 {csv_filename}")
                success = convert_excel_to_standard_csv(excel_path, output_csv_path, log) #
                if not success:
                    log(f"WARNING: 转换文件 {file} 失败。", "WARNING")


# 模拟 create_homology_df 函数
def create_homology_df(file_path: str) -> pd.DataFrame:
    """
    从 CSV 或 Excel 文件加载同源数据到 DataFrame。
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


def _load_data_file(file_path: str, log: Callable) -> Optional[pd.DataFrame]:
    """
    【最终增强版】智能加载数据文件的辅助函数。
    它能处理 .gz 压缩，在多种格式间自动尝试，并强力净化列名。
    """
    if not file_path or not os.path.exists(file_path):
        log(f"错误: 文件不存在 -> {file_path}", "ERROR")
        return None

    open_func = gzip.open if file_path.endswith('.gz') else open
    file_name = os.path.basename(file_path)
    df = None

    # 尝试1: 作为Excel文件读取
    try:
        with open_func(file_path, 'rb') as f:
            log(f"正在尝试作为 Excel (.xlsx) 文件读取: {file_name}", "DEBUG")
            df = pd.read_excel(f, engine='openpyxl')
    except Exception as excel_error:
        log(f"作为Excel读取失败 ({excel_error})，继续尝试其他格式...", "WARNING")

    # 尝试2: 作为逗号分隔的CSV文件读取 (如果Excel失败)
    if df is None:
        try:
            with open_func(file_path, 'rt', encoding='utf-8') as f:
                log(f"正在尝试作为逗号分隔 (CSV) 文件读取: {file_name}", "DEBUG")
                temp_df = pd.read_csv(f, sep=',', engine='python')
                # 检查是否成功解析出多于一列
                if len(temp_df.columns) > 1:
                    df = temp_df
                else:
                    log(f"作为CSV读取后仅发现一列，可能分隔符不正确。", "WARNING")
        except Exception as csv_error:
            log(f"作为CSV读取失败 ({csv_error})，继续尝试其他格式...", "WARNING")

    # 尝试3: 作为制表符分隔的TSV文件读取 (如果CSV失败或不适用)
    if df is None:
        try:
            with open_func(file_path, 'rt', encoding='utf-8') as f:
                log(f"正在尝试作为制表符分隔 (TSV) 文件读取: {file_name}", "DEBUG")
                df = pd.read_csv(f, sep='\t', engine='python')
        except Exception as tsv_error:
            log(f"作为TSV也读取失败 ({tsv_error})。无法加载文件: {file_name}", "ERROR")
            return None

    # --- 强力净化列名 ---
    if df is not None:
        # 移除所有非字母、数字、下划线、点、连字符或空格的字符，然后去除首尾空格
        cleaned_columns = [re.sub(r'[^\w\s\.-]', '', str(col)).strip() for col in df.columns]
        df.columns = cleaned_columns
        log(f"文件加载成功，净化后的列名为: {list(df.columns)}", "DEBUG")
        return df

    log(f"所有尝试均失败，无法加载文件: {file_name}", "ERROR")
    return None


def _update_config_from_overrides(config_obj: Any, overrides: Optional[Dict[str, Any]]):
    """使用CLI/GUI的重写值递归更新配置对象。"""
    if not overrides:
        return
    for key, value in overrides.items():
        if value is not None:
            if hasattr(config_obj, key):
                setattr(config_obj, key, value)
            else:
                logger.warning(f"配置覆盖警告：在对象 {type(config_obj).__name__} 中找不到键 '{key}'。")


def _update_criteria_from_cli(base_criteria: HomologySelectionCriteria,
                              cli_overrides: Optional[Dict[str, Any]]) -> HomologySelectionCriteria:
    """使用CLI/GUI参数安全地更新HomologySelectionCriteria实例。"""
    if not cli_overrides:
        return base_criteria

    updated_criteria_dict = asdict(base_criteria)
    for key, value in cli_overrides.items():
        if value is not None and key in updated_criteria_dict:
            if key == 'prioritize_subgenome' and isinstance(value, bool):
                updated_criteria_dict[key] = value
            elif value:
                updated_criteria_dict[key] = value
    return HomologySelectionCriteria(**updated_criteria_dict)


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
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
) -> Optional[pd.DataFrame]:
    """
    【最终版】执行同源基因映射。根据 calculate_target_locus 参数决定是否计算目标概要位点。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")

    try:
        # 步骤 1 & 2: 加载配置和数据 (此部分逻辑不变)
        log(_("步骤 1&2: 加载配置和同源数据..."), "INFO")
        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)
        bridge_species_name = config.integration_pipeline.bridge_species_name
        bridge_genome_info = genome_sources.get(bridge_species_name)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log(_("错误: 一个或多个指定的基因组名称无效。"), "ERROR")
            return None

        source_gene_ids = gene_ids
        if region:
            gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
            gff_db_cache_dir = os.path.join(os.path.dirname(config._config_file_abs_path_),
                                            config.integration_pipeline.gff_db_storage_dir)
            genes_in_region_list = get_genes_in_region(
                assembly_id=source_assembly_id, gff_filepath=gff_path, db_storage_dir=gff_db_cache_dir, region=region,
                force_db_creation=config.integration_pipeline.force_gff_db_creation, status_callback=log
            )
            if not genes_in_region_list:
                log(f"在区域 {region} 中未找到任何基因。", "WARNING")
                return None
            source_gene_ids = [gene['gene_id'] for gene in genes_in_region_list]

        if not source_gene_ids:
            log(_("错误: 输入的基因列表为空。"), "ERROR")
            return None

        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')
        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file)
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file)

        # 步骤 3: 执行映射 (此部分逻辑不变)
        log(_("步骤 3: 通过桥梁物种执行基因映射..."), "INFO")
        selection_criteria_s_to_b = config.integration_pipeline.selection_criteria_source_to_bridge
        selection_criteria_b_to_t = config.integration_pipeline.selection_criteria_bridge_to_target
        if criteria_overrides:
            s2b_dict = selection_criteria_s_to_b.to_dict()
            b2t_dict = selection_criteria_b_to_t.to_dict()
            for key, value in criteria_overrides.items():
                if value is not None:
                    if key in s2b_dict: s2b_dict[key] = value
                    if key in b2t_dict: b2t_dict[key] = value
            selection_criteria_s_to_b = type(selection_criteria_s_to_b)
            selection_criteria_b_to_t = type(selection_criteria_b_to_t)
        homology_columns = config.integration_pipeline.homology_columns


        mapped_df, failed_genes = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=bridge_species_name,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b.to_dict(),
            selection_criteria_b_to_t=selection_criteria_b_to_t.to_dict(),
            homology_columns=homology_columns,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            status_callback=status_callback,
            cancel_event=cancel_event
        )

        log(_("步骤 4: 保存映射结果..."), "INFO")
        if output_csv_path:
            # 准备自定义头部
            source_locus_str = f"{source_assembly_id} | {region[0]}:{region[1]}-{region[2]}" if region else f"{source_assembly_id} | {len(source_gene_ids)} genes"
            header_line1 = f"# 源基因组的位点（即用户输入的位点）: {source_locus_str}\n"

            target_locus_summary = ""
            if calculate_target_locus:
                log("正在计算目标概要位点...", "INFO")
                if mapped_df is not None and not mapped_df.empty:
                    target_gene_ids_list = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
                    if target_gene_ids_list:
                        target_gff_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')
                        gff_db_cache_dir = os.path.join(os.path.dirname(config._config_file_abs_path_),
                                                        config.integration_pipeline.gff_db_storage_dir)
                        target_genes_details_df = get_gene_info_by_ids(
                            assembly_id=target_assembly_id, gff_filepath=target_gff_path,
                            db_storage_dir=gff_db_cache_dir, gene_ids=target_gene_ids_list, status_callback=log
                        )

                        # --- 核心修正点 1：修复 KeyError ---
                        if target_genes_details_df is not None and not target_genes_details_df.empty:
                            locus_bounds = target_genes_details_df.groupby('chrom').agg(min_start=('start', 'min'),
                                                                                        max_end=('end',
                                                                                                 'max')).reset_index()
                            summary_parts = [f"{row['chrom']}:{row['min_start']}-{row['max_end']}" for _, row in
                                             locus_bounds.iterrows()]
                            target_locus_summary = " | " + (
                                ", ".join(summary_parts) if summary_parts else "无具体位点信息")
                        # 如果找不到坐标信息，则概要留空
                else:
                    target_locus_summary = " | 无映射结果"

            header_line2 = f"# 目标基因组的位点（即转换后的大体的位点）: {target_assembly_id}{target_locus_summary}\n"

            # --- 核心修正点 2：改进失败基因报告 ---
            with open(output_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                # 写入头部信息
                f.write(header_line1)
                f.write(header_line2)
                f.write("#\n")  # 写入一个空注释行作为分隔

                # 写入成功匹配的结果表格
                if mapped_df is not None and not mapped_df.empty:
                    mapped_df.to_csv(f, index=False, lineterminator='\n')
                else:
                    f.write("# 未找到任何成功的同源匹配。\n")

                # 如果有匹配失败的基因，在表格下方追加一个新部分
                if failed_genes:
                    f.write("\n\n")  # 写入两个换行符作为间隔
                    f.write("# --- 匹配失败的源基因 ---\n")
                    failed_df = pd.DataFrame({
                        'Failed_Source_Gene_ID': failed_genes,
                        'Reason': "未能在目标基因组中找到满足所有筛选条件（如E-value, PID, 严格模式等）的同源基因。"
                    })
                    failed_df.to_csv(f, index=False, lineterminator='\n')

            log(f"结果已成功保存到: {output_csv_path}", "SUCCESS")
        else:
            log("未提供输出路径，跳过保存文件。", "INFO")

        return mapped_df

    except Exception as e:
        log(f"流水线执行过程中发生意外错误: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None


def run_locus_conversion(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        region: Tuple[str, int, int],
        output_path: str,
        status_callback: Callable,
        criteria_overrides: Optional[Dict[str, Any]] = None,
        **kwargs
) -> None:
    """
    通过调用核心同源映射流程，执行带概要位点计算的位点转换。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")

    try:
        log("步骤1: 加载配置...", "INFO")
        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)
        bridge_species_name = config.integration_pipeline.bridge_species_name
        bridge_genome_info = genome_sources.get(bridge_species_name)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log(f"错误: 无法为 {source_assembly_id}, {target_assembly_id} 或 {bridge_species_name} 找到配置。", "ERROR")
            return

        # 步骤1.1: 从GFF中获取源基因ID
        gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        gff_db_cache_dir = os.path.join(os.path.dirname(config._config_file_abs_path_),
                                        config.integration_pipeline.gff_db_storage_dir)
        source_gene_list = get_genes_in_region(
            assembly_id=source_assembly_id, gff_filepath=gff_path,
            db_storage_dir=gff_db_cache_dir, region=region,
            force_db_creation=config.integration_pipeline.force_gff_db_creation,
            status_callback=log,
            gene_id_regex=source_genome_info.gene_id_regex
        )
        if not source_gene_list:
            log(f"在区域 {region} 中未找到任何基因。", "WARNING")
            return
        source_gene_ids = [gene['gene_id'] for gene in source_gene_list]

        # 步骤1.2: 准备调用 map_genes_via_bridge 所需的所有参数
        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        # --- 健壮性检查 ---
        if not s_to_b_homology_file or not b_to_t_homology_file:
            log(f"错误: 缺少必要的同源文件。源文件路径: '{s_to_b_homology_file}', 目标文件路径: '{b_to_t_homology_file}'。请先运行下载流程。", "ERROR")
            return

        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file)
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file)

        selection_criteria_s_to_b = config.integration_pipeline.selection_criteria_source_to_bridge
        selection_criteria_b_to_t = config.integration_pipeline.selection_criteria_bridge_to_target
        if criteria_overrides:
            s2b_dict = selection_criteria_s_to_b.to_dict()
            b2t_dict = selection_criteria_b_to_t.to_dict()
            for key, value in criteria_overrides.items():
                if value is not None:
                    if key in s2b_dict: s2b_dict[key] = value
                    if key in b2t_dict: b2t_dict[key] = value
            selection_criteria_s_to_b = type(selection_criteria_s_to_b)
            selection_criteria_b_to_t = type(selection_criteria_b_to_t)
        homology_columns = config.integration_pipeline.homology_columns

        # 步骤 2: 调用核心映射逻辑
        log("正在执行核心同源映射...", "INFO")
        mapped_df, failed_genes = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=bridge_species_name,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=selection_criteria_s_to_b.to_dict(),
            selection_criteria_b_to_t=selection_criteria_b_to_t.to_dict(),
            homology_columns=homology_columns,
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            status_callback=status_callback,
            cancel_event=kwargs.get('cancel_event')
        )

        # 步骤 3: 计算目标概要位点
        target_locus_summary = "无具体位点信息"
        if mapped_df is not None and not mapped_df.empty:
            target_gene_ids_list = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
            if target_gene_ids_list:
                target_gff_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')
                target_genes_details_df = get_gene_info_by_ids(
                    assembly_id=target_assembly_id,
                    gff_filepath=target_gff_path,
                    db_storage_dir=gff_db_cache_dir,
                    gene_ids=target_gene_ids_list,
                    status_callback=log,
                    gene_id_regex=target_genome_info.gene_id_regex  # 传递目标正则
                )
                if not target_genes_details_df.empty:
                    locus_bounds = target_genes_details_df.groupby('chrom').agg(min_start=('start', 'min'),
                                                                                max_end=('end', 'max')).reset_index()
                    summary_parts = [f"{row['chrom']}:{row['min_start']}-{row['max_end']}" for _, row in
                                     locus_bounds.iterrows()]
                    target_locus_summary = ", ".join(summary_parts)

        # 步骤 4: 写入最终的CSV文件
        header_line1 = f"# 源基因组的位点（即用户输入的位点）: {source_assembly_id} | {region[0]}:{region[1]}-{region[2]}\n"
        header_line2 = f"# 目标基因组的位点（即转换后的大体的位点）: {target_assembly_id} | {target_locus_summary}\n"
        failed_genes_str = ",".join(failed_genes) if failed_genes else "无"
        header_line3 = f"# 匹配失败的源基因 ({len(failed_genes)}): {failed_genes_str}\n"

        output_dir = os.path.dirname(output_path)
        if output_dir: os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(header_line1)
            f.write(header_line2)
            f.write(header_line3)
            if mapped_df is not None and not mapped_df.empty:
                mapped_df.to_csv(f, index=False, lineterminator='\n')
            else:
                f.write("# 未找到任何成功的同源匹配。\n")

        log(f"位点转换结果已成功保存到: {output_path}", "SUCCESS")

    except Exception as e:
        log(f"位点转换流程出错: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")


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
    """【已修正】执行AI任务流程，增加对 progress_callback 的支持以兼容GUI。"""
    batch_cfg = config.batch_ai_processor
    _update_config_from_overrides(batch_cfg, cli_overrides)

    # 如果提供了进度回调，就使用它，否则使用一个不做任何事的占位函数
    progress = progress_callback if progress_callback else lambda p, m: None

    status_callback(_("AI任务流程开始..."), "INFO")
    progress(0, _("初始化AI客户端..."))

    ai_cfg = config.ai_services
    provider_name = ai_cfg.default_provider
    provider_cfg_obj = ai_cfg.providers.get(provider_name)
    if not provider_cfg_obj:
        status_callback(f"错误: 在配置中未找到默认AI服务商 '{provider_name}' 的设置。", "ERROR")
        return

    api_key = provider_cfg_obj.api_key
    model = provider_cfg_obj.model
    base_url = provider_cfg_obj.base_url
    if not api_key or "YOUR_API_KEY" in api_key:
        status_callback(f"错误: 请在配置文件中为服务商 '{provider_name}' 设置一个有效的API Key。", "ERROR")
        return

    status_callback(_("正在初始化AI客户端... 服务商: {}, 模型: {}").format(provider_name, model))
    ai_client = AIWrapper(provider=provider_name, api_key=api_key, model=model, base_url=base_url)

    project_root = os.path.dirname(config._config_file_abs_path_) if config._config_file_abs_path_ else '.'
    output_dir_name = getattr(batch_cfg, 'output_dir_name', 'ai_results')  # 安全访问
    output_dir = os.path.join(project_root, output_dir_name)
    os.makedirs(output_dir, exist_ok=True)  # 确保输出目录存在

    prompt_to_use = custom_prompt_template
    if not prompt_to_use:
        prompt_to_use = config.ai_prompts.translation_prompt if task_type == 'translate' else config.ai_prompts.analysis_prompt

    progress(10, _("正在处理CSV文件..."))

    # 将回调函数传递给核心处理模块
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
        progress_callback=progress,
        cancel_event=cancel_event,
        output_csv_path=output_file
    )

    progress(100, _("任务完成。"))
    status_callback(_("AI任务流程成功完成。"), "SUCCESS")


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
    """
    【完整且最终修正版】执行功能注释流水线。

    此函数功能完备，支持:
    - 通过基因ID列表或文件路径输入。
    - 在源和目标基因组不同时，自动执行同源映射。
    - 支持任务取消。
    - 支持手动指定一个包含所有注释文件的数据库目录 (custom_db_dir)。
    - 支持手动指定一个完整的输出文件路径 (output_path)，否则在输出目录 (output_dir) 中自动生成。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: log(f"[{p}%] {m}")

    # --- 步骤 1: 准备输入基因列表 ---
    progress(0, _("准备输入基因列表..."))
    source_gene_ids = []
    if gene_ids:
        source_gene_ids = list(set(gene_ids))
        log(f"INFO: 从参数直接获取了 {len(source_gene_ids)} 个唯一基因ID。")
    elif gene_list_path and os.path.exists(gene_list_path):
        try:
            log(f"INFO: 正在从文件 '{os.path.basename(gene_list_path)}' 中读取基因列表...")
            study_genes_df = pd.read_csv(gene_list_path)
            source_gene_ids = study_genes_df.iloc[:, 0].dropna().unique().tolist()
            log(f"INFO: 从文件中读取了 {len(source_gene_ids)} 个唯一基因ID。")
        except Exception as e:
            log(f"读取基因列表文件时出错: {e}", "ERROR")
            return
    else:
        log("错误: 必须提供 'gene_ids' 或有效的 'gene_list_path' 参数之一。", "ERROR")
        return

    if not source_gene_ids:
        log("输入的基因列表为空，流程终止。", "ERROR")
        return

    genes_to_annotate = source_gene_ids
    original_to_target_map_df = pd.DataFrame({'Source_Gene_ID': source_gene_ids})

    # --- 步骤 2: 按需进行同源转换 ---
    progress(20, _("检查是否需要同源映射..."))
    if source_genome != target_genome:
        log(f"源基因组 ({source_genome}) 与目标基因组 ({target_genome}) 不同，准备进行同源转换。", "INFO")

        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_genome)
        target_genome_info = genome_sources.get(target_genome)
        bridge_genome_info = genome_sources.get(bridge_species)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log("一个或多个基因组名称无效，无法找到配置信息。", "ERROR")
            return

        progress(30, _("加载同源数据文件..."))
        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not all([s_to_b_homology_file, b_to_t_homology_file, os.path.exists(s_to_b_homology_file),
                    os.path.exists(b_to_t_homology_file)]):
            log("缺少必要的同源文件，无法进行转换。请先下载数据。", "ERROR")
            return

        source_to_bridge_homology_df = pd.read_excel(s_to_b_homology_file)
        bridge_to_target_homology_df = pd.read_excel(b_to_t_homology_file)

        selection_criteria_s_to_b = config.integration_pipeline.selection_criteria_source_to_bridge.to_dict()
        selection_criteria_b_to_t = config.integration_pipeline.selection_criteria_bridge_to_target.to_dict()
        homology_columns = config.integration_pipeline.homology_columns

        progress(40, _("正在通过桥梁物种进行基因映射..."))
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
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            log("任务在同源映射阶段被用户取消。", "INFO")
            return

        if mapped_df is None or mapped_df.empty:
            log("同源转换未能映射到任何基因，流程终止。", "WARNING")
            return

        genes_to_annotate = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
        original_to_target_map_df = mapped_df[['Source_Gene_ID', 'Target_Gene_ID']]

    # --- 步骤 3: 初始化 Annotator ---
    progress(60, _("初始化注释器..."))
    genome_sources = get_genome_data_sources(config, logger_func=log)
    target_genome_info = genome_sources.get(target_genome)
    if not target_genome_info:
        log(f"错误：无法为目标基因组 {target_genome} 找到配置信息。", "ERROR")
        return

    annotator = Annotator(
        main_config=config,
        genome_id=target_genome,
        genome_info=target_genome_info,
        status_callback=status_callback,
        progress_callback=progress_callback,
        custom_db_dir=custom_db_dir
    )

    # --- 步骤 4: 执行注释 ---
    progress(70, _("正在为 {len(genes_to_annotate)} 个基因执行功能注释..."))
    result_df = annotator.annotate_genes(genes_to_annotate, annotation_types)

    if cancel_event and cancel_event.is_set():
        log("任务在注释阶段被用户取消。", "INFO")
        return

    # --- 步骤 5: 处理并保存结果 ---
    progress(90, _("整理并保存结果..."))
    if result_df is not None and not result_df.empty:
        # 如果进行了同源转换，将注释结果与原始基因ID关联起来
        if 'Target_Gene_ID' in original_to_target_map_df.columns:
            final_df = pd.merge(original_to_target_map_df, result_df, on='Target_Gene_ID', how='left')
        else:
            final_df = result_df

        # --- 决定最终输出路径 ---
        final_output_path = ""
        if output_path:
            final_output_path = output_path
            # 确保其父目录存在
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
            return

        try:
            final_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
            log(f"注释成功！结果已保存至: {final_output_path}", "SUCCESS")
        except Exception as e:
            log(f"保存结果到 {final_output_path} 时发生错误: {e}", "ERROR")

    else:
        log("注释完成，但没有生成任何结果。", "WARNING")

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
    """
    【重构版】执行GFF基因位点查询流程。
    可以根据基因ID列表或染色体区域进行查询。
    """
    log = status_callback if status_callback else lambda msg, level="INFO": print(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: print(f"[{p}%] {m}")

    if not gene_ids and not region:
        log(_("错误: 必须提供基因ID列表或染色体区域进行查询。"), "ERROR")
        return False

    log(_("开始GFF基因查询流程..."), "INFO")
    progress(0, _("初始化配置..."))

    pipeline_cfg = config.integration_pipeline
    downloader_cfg = config.downloader
    project_root = os.path.dirname(config._config_file_abs_path_) if config._config_file_abs_path_ else '.'

    genome_sources = get_genome_data_sources(config, logger_func=log)
    selected_genome_info = genome_sources.get(assembly_id)
    if not selected_genome_info:
        log(_("错误: 基因组 '{}' 未在基因组源列表中找到。").format(assembly_id), "ERROR")
        return False

    gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')
    if not gff_file_path or not os.path.exists(gff_file_path):
        log(_("错误: 未找到基因组 '{}' 的GFF文件。请先下载数据。").format(assembly_id), "ERROR")
        return False

    progress(20, _("正在加载GFF数据库..."))
    gff_db_dir = os.path.join(project_root, pipeline_cfg.gff_db_storage_dir)
    force_creation = pipeline_cfg.force_gff_db_creation

    results_df = pd.DataFrame()
    if gene_ids:
        log(_("按基因ID查询 {} 个基因...").format(len(gene_ids)), "INFO")
        results_df = get_gene_info_by_ids(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, gene_ids=gene_ids,
            force_db_creation=force_creation, status_callback=log
        )
    elif region:
        chrom, start, end = region
        log(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end), "INFO")
        genes_in_region_list = get_genes_in_region(
            assembly_id=assembly_id, gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir, region=region,
            force_db_creation=force_creation, status_callback=log
        )
        if genes_in_region_list:
            results_df = pd.DataFrame(genes_in_region_list)

    progress(90, _("查询完成，正在整理结果..."))
    if results_df.empty:
        log(_("未找到任何符合条件的基因。"), "WARNING")
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
            log(_("GFF基因查询结果已保存到: {}").format(final_output_path), "SUCCESS")
        except Exception as e:
            log(_("保存结果时出错: {}").format(e), "ERROR")
            return False

    progress(100, _("GFF查询流程结束。"))
    return True


# GO KEGG 富集分析
def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
):
    """
    执行数据下载流程。
    """
    # ... (函数前半部分，包括日志设置、参数解析、构建all_download_tasks列表的代码都保持不变) ...
    log = status_callback if status_callback else print
    progress = progress_callback if progress_callback else lambda p, m: log(f"进度 {p}%: {m}")
    log("INFO: 下载流程开始...")
    downloader_cfg = config.downloader
    genome_sources = get_genome_data_sources(config, logger_func=log)
    if cli_overrides is None: cli_overrides = {}
    versions_to_download = cli_overrides.get("versions")
    if versions_to_download is None:
        versions_to_download = list(genome_sources.keys())
    force_download = cli_overrides.get("force", downloader_cfg.force_download)
    proxies = cli_overrides.get("proxies")
    max_workers = downloader_cfg.max_workers
    log(f"INFO: 将尝试下载的基因组版本: {', '.join(versions_to_download)}")

    all_download_tasks = []
    ALL_FILE_KEYS = ['gff3', 'GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']
    for version_id in versions_to_download:
        genome_info = genome_sources.get(version_id)
        if not genome_info:
            log(f"WARNING: 在基因组源中未找到版本 '{version_id}'，已跳过。")
            continue
        for file_key in ALL_FILE_KEYS:
            url = getattr(genome_info, f"{file_key}_url", None)
            if url:
                all_download_tasks.append({
                    "version_id": version_id,  # <-- 将version_id也加入任务信息中
                    "genome_info": genome_info,
                    "file_key": file_key,
                    "url": url
                })

    if not all_download_tasks:
        log("WARNING: 没有找到任何有效的URL可供下载。")
        return

    log(f"INFO: 准备下载 {len(all_download_tasks)} 个文件...")

    successful_downloads = 0
    failed_downloads = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            # 【核心修正】在提交任务时，将 task["version_id"] 作为新参数传递
            executor.submit(
                download_genome_data,
                downloader_config=config.downloader,
                version_id=task["version_id"],  # <-- 新增传递的参数
                genome_info=task["genome_info"],
                file_key=task["file_key"],
                url=task["url"],
                force=force_download,
                proxies=proxies,
                status_callback=log
            ): task for task in all_download_tasks
        }

        # ... (后续的循环、进度更新、日志总结部分代码保持不变) ...
        for i, future in enumerate(as_completed(future_to_task)):
            if cancel_event and cancel_event.is_set():
                log("INFO: 下载任务已被用户取消。")
                break
            task_info = future_to_task[future]
            try:
                if future.result():
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as exc:
                # 使用 version_id 而不是不存在的 genome_info.id
                log(f"ERROR: 下载 {task_info['version_id']} 的 {task_info['file_key']} 文件时发生严重错误: {exc}")
                failed_downloads += 1
            progress((i + 1) * 100 // len(all_download_tasks),
                     f"{_('总体下载进度')} ({i + 1}/{len(all_download_tasks)})")

    log(f"INFO: 所有指定的下载任务已完成。成功: {successful_downloads}, 失败: {failed_downloads}。")


def run_enrichment_pipeline(
        config: MainConfig,
        assembly_id: str,
        study_gene_ids: List[str],
        analysis_type: str,
        plot_types: List[str],
        output_dir: str,
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
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
    """
    【全功能修正版】执行富集分析与可视化的完整流程。
    """
    log = status_callback if status_callback else print
    progress = progress_callback if progress_callback else lambda p, m: log(f"进度 {p}%: {m}")

    log(f"INFO: {analysis_type.upper()} 富集与可视化流程启动。")

    if collapse_transcripts:
        original_count = len(study_gene_ids)
        log("INFO: 正在将RNA合并到基因...")
        study_gene_ids = map_transcripts_to_genes(study_gene_ids)
        log(f"INFO: 基因列表已从 {original_count} 个RNA合并为 {len(study_gene_ids)} 个唯一基因。")

    try:
        genome_sources = get_genome_data_sources(config, logger_func=log)
        genome_info = genome_sources.get(assembly_id)
        if not genome_info:
            log(f"ERROR: 无法在配置中找到基因组 '{assembly_id}'。")
            return None
        gene_id_regex = genome_info.gene_id_regex if hasattr(genome_info, 'gene_id_regex') else None
    except Exception as e:
        log(f"ERROR: 获取基因组源数据时失败: {e}")
        return None

    os.makedirs(output_dir, exist_ok=True)
    enrichment_df = None

    # --- 步骤 1: 执行核心富集分析 ---
    if analysis_type == 'go':
        progress(20, _("正在执行GO富集分析..."))
        gaf_path = get_local_downloaded_file_path(config, genome_info, 'GO')
        if not gaf_path or not os.path.exists(gaf_path):
            log(f"ERROR: 未找到 '{assembly_id}' 的GO注释关联文件 (GAF)。请先下载数据。")
            return None
        enrichment_df = run_go_enrichment(study_gene_ids=study_gene_ids, go_annotation_path=gaf_path, output_dir=output_dir, status_callback=log, gene_id_regex=gene_id_regex)

    elif analysis_type == 'kegg':
        progress(20, _("正在执行KEGG富集分析..."))
        pathways_path = get_local_downloaded_file_path(config, genome_info, 'KEGG_pathways')
        if not pathways_path or not os.path.exists(pathways_path):
            log(f"ERROR: 未找到 '{assembly_id}' 的KEGG通路文件。请先下载数据。")
            return None
        enrichment_df = run_kegg_enrichment(study_gene_ids=study_gene_ids, kegg_pathways_path=pathways_path, output_dir=output_dir, status_callback=log, gene_id_regex=gene_id_regex)


    else:
        log(f"ERROR: 未知的分析类型 '{analysis_type}'。")
        return None

    if cancel_event and cancel_event.is_set():
        log("INFO: 任务在分析后被取消。")
        return None

    if enrichment_df is None or enrichment_df.empty:
        log("WARNING: 富集分析未发现任何显著结果，流程终止。")
        return []  # 返回空列表表示成功但无结果

    progress(70, _("富集分析完成，正在生成图表..."))

    # --- 步骤 2: 遍历并生成所有请求的图表 ---
    generated_plots = []

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
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_bubble.{file_format}")
                plot_path = plot_enrichment_bubble(enrichment_df=df_sub, output_path=output_path, title=title_ns,
                                                   **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            if 'bar' in plot_types:
                # !!!!!!!!!!!!!!! 这是修改点 !!!!!!!!!!!!!!!
                # 将 has_log2fc=... 替换为 gene_log2fc_map=...
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_bar.{file_format}")
                plot_path = plot_enrichment_bar(enrichment_df=df_sub, output_path=output_path, title=title_ns,
                                                gene_log2fc_map=gene_log2fc_map, **plot_kwargs_common)
                if plot_path: generated_plots.append(plot_path)

            if 'upset' in plot_types:
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_upset.{file_format}")
                plot_path = plot_enrichment_upset(enrichment_df=df_sub, output_path=output_path, top_n=top_n)
                if plot_path: generated_plots.append(plot_path)

            if 'cnet' in plot_types:
                output_path = os.path.join(output_dir, f"{file_prefix_ns}_cnet.{file_format}")
                plot_path = plot_enrichment_cnet(enrichment_df=df_sub, output_path=output_path, top_n=top_n,
                                                 gene_log2fc_map=gene_log2fc_map)
                if plot_path: generated_plots.append(plot_path)
    else:
        title = f"{analysis_type.upper()} Enrichment"
        file_prefix = f"{analysis_type}_enrichment"

        if 'bubble' in plot_types:
            output_path = os.path.join(output_dir, f"{file_prefix}_bubble.{file_format}")
            plot_path = plot_enrichment_bubble(enrichment_df=enrichment_df, output_path=output_path, title=title,
                                               **plot_kwargs_common)
            if plot_path: generated_plots.append(plot_path)

        if 'bar' in plot_types:
            # !!!!!!!!!!!!!!! 这是另一个修改点 !!!!!!!!!!!!!!!
            # 同样，替换参数
            output_path = os.path.join(output_dir, f"{file_prefix}_bar.{file_format}")
            plot_path = plot_enrichment_bar(enrichment_df=enrichment_df, output_path=output_path, title=title,
                                            gene_log2fc_map=gene_log2fc_map, **plot_kwargs_common)
            if plot_path: generated_plots.append(plot_path)

        if 'upset' in plot_types:
            output_path = os.path.join(output_dir, f"{file_prefix}_upset.{file_format}")
            plot_path = plot_enrichment_upset(enrichment_df=enrichment_df, output_path=output_path, top_n=top_n)
            if plot_path: generated_plots.append(plot_path)

        if 'cnet' in plot_types:
            output_path = os.path.join(output_dir, f"{file_prefix}_cnet.{file_format}")
            plot_path = plot_enrichment_cnet(enrichment_df=enrichment_df, output_path=output_path, top_n=top_n,
                                             gene_log2fc_map=gene_log2fc_map)
            if plot_path: generated_plots.append(plot_path)

    progress(100, _("所有图表已生成。"))
    log(f"SUCCESS: 流程完成。在 '{output_dir}' 中成功生成 {len(generated_plots)} 个图表。", "SUCCESS")

    return generated_plots


def _preprocess_single_annotation_excel(excel_path: str, output_csv_path: str, log: Callable) -> bool:
    """
    【新增的专用函数】专门用于读取多Sheet的Excel注释文件，合并并添加标准表头。
    """
    try:
        all_sheets_dict = pd.read_excel(excel_path, sheet_name=None, header=None, engine='openpyxl')
        all_dfs = [df for df in all_sheets_dict.values() if not df.empty and df.dropna(how='all').shape[0] > 0]

        if not all_dfs:
            log(f"WARNING: 文件 {os.path.basename(excel_path)} 中没有找到有效数据。", "WARNING")
            return False

        concatenated_df = pd.concat(all_dfs, ignore_index=True)

        # 强制设置我们需要的标准列名
        num_cols = len(concatenated_df.columns)
        new_columns = []
        if num_cols > 0: new_columns.append('Query')
        if num_cols > 1: new_columns.append('Match')
        if num_cols > 2: new_columns.append('Description')
        if num_cols > 3:
            for i in range(3, num_cols): new_columns.append(f'Extra_Col_{i + 1}')
        concatenated_df.columns = new_columns

        concatenated_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        log(f"ERROR: 预处理注释文件 {os.path.basename(excel_path)} 时发生错误: {e}", "ERROR")
        return False


def run_preprocess_annotation_files(
        config: MainConfig,
        status_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    """
    【已恢复】调用公用的 convert_excel_to_standard_csv 函数，
    预处理所有已下载的Excel注释文件。
    """
    log = status_callback if status_callback else print
    progress = progress_callback if progress_callback else lambda p, m: log(f"[{p}%] {m}")

    log("INFO: 开始预处理注释文件（转换为CSV）...")
    progress(0, "初始化...")

    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        log("ERROR: 未能加载基因组源数据。", "ERROR")
        return False

    tasks_to_run = []
    ALL_ANNO_KEYS = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs']
    for genome_info in genome_sources.values():
        for key in ALL_ANNO_KEYS:
            source_path = get_local_downloaded_file_path(config, genome_info, key)
            # 只处理存在的、且是Excel格式的文件
            if source_path and os.path.exists(source_path) and source_path.lower().endswith(('.xlsx', '.xlsx.gz')):
                # 智能推断输出路径
                base_path = source_path.replace('.xlsx.gz', '').replace('.xlsx', '')
                output_path = base_path + '.csv'
                # 如果CSV文件不存在，或者源文件比它更新，则需要处理
                if not os.path.exists(output_path) or os.path.getmtime(source_path) > os.path.getmtime(output_path):
                    tasks_to_run.append((source_path, output_path))

    if not tasks_to_run:
        log("INFO: 所有注释文件均已是最新状态，无需预处理。", "INFO")
        progress(100, "无需处理。")
        return True

    total_tasks = len(tasks_to_run)
    log(f"INFO: 找到 {total_tasks} 个文件需要进行预处理。")
    success_count = 0

    for i, (source, output) in enumerate(tasks_to_run):
        if cancel_event and cancel_event.is_set():
            log("INFO: 任务被用户取消。", "INFO")
            return False

        progress((i + 1) * 100 // total_tasks, f"正在转换: {os.path.basename(source)}")

        # 调用您公用的转换函数
        if convert_excel_to_standard_csv(source, output, log):
            success_count += 1

    log(f"SUCCESS: 预处理完成。成功转换 {success_count}/{total_tasks} 个文件。", "SUCCESS")
    progress(100, "全部完成。")
    return True