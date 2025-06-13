# cotton_toolkit/pipelines.py

import logging
import os
import re
import threading
import time
from dataclasses import asdict
from typing import List, Dict, Any, Optional, Callable, Tuple
import gzip
import pandas as pd

from .config.loader import get_genome_data_sources, get_local_downloaded_file_path
# 核心模块导入
from .config.models import (
    MainConfig, HomologySelectionCriteria, GenomeSourceItem
)
from .core.ai_wrapper import AIWrapper
from .core.downloader import download_genome_data
from .core.gff_parser import get_genes_in_region, extract_gene_details, create_gff_database, get_gene_info_by_ids
from .core.homology_mapper import map_genes_via_bridge
from .tools.batch_ai_processor import process_single_csv_file
from .tools.annotator import Annotator

# --- 国际化和日志设置 ---
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines")

bridge_id_regex = r'(AT[1-5MC]G\d{5})'

# --- 配置更新辅助函数 ---

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


# --- 核心流程函数 ---

def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Callable = print,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
):
    """执行数据下载流程。"""
    downloader_cfg = config.downloader
    cli_overrides = cli_overrides or {}

    _update_config_from_overrides(downloader_cfg, cli_overrides)
    if cli_overrides.get('http_proxy') or cli_overrides.get('https_proxy'):
        downloader_cfg.proxies.http = cli_overrides.get('http_proxy')
        downloader_cfg.proxies.https = cli_overrides.get('https_proxy')

    status_callback(_("下载流程开始..."))

    download_genome_data(
        config=config,
        genome_versions_to_download_override=cli_overrides.get("versions"),
        status_callback=status_callback,
        progress_callback=progress_callback,
        cancel_event=cancel_event
    )
    status_callback(_("下载流程结束。"))


def run_integrate_pipeline(
    config: MainConfig,
    cli_overrides: Optional[Dict[str, Any]] = None,
    status_callback: Optional[Callable[[str, str], None]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> bool:
    """
    【最终版】整合BSA定位结果和HVG基因数据，进行候选基因筛选和优先级排序。
    此函数作为新的流程入口，取代了旧的 integrate_bsa_with_hvg。
    """

    # --- 1. 初始化和应用覆盖参数 ---
    # 使用标准化的回调函数
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: print(f"[{p}%] {m}")

    pipeline_cfg = config.integration_pipeline
    _update_config_from_overrides(pipeline_cfg, cli_overrides)

    log(_("开始整合分析流程..."), "INFO")
    progress(0, _("初始化配置..."))

    # --- 2. 核心业务逻辑 (源自原 integrate_bsa_with_hvg) ---

    overall_success = False

    # 从更新后的配置中提取变量
    input_excel = pipeline_cfg.input_excel_path
    bsa_sheet_name = pipeline_cfg.bsa_sheet_name
    hvg_sheet_name = pipeline_cfg.hvg_sheet_name
    output_sheet_name = pipeline_cfg.output_sheet_name
    bsa_assembly_id = pipeline_cfg.bsa_assembly_id
    hvg_assembly_id = pipeline_cfg.hvg_assembly_id

    # 校验配置
    if not all([input_excel, bsa_sheet_name, hvg_sheet_name, output_sheet_name, bsa_assembly_id, hvg_assembly_id]):
        log(_("错误: 整合分析所需的配置不完整（如Excel路径、Sheet名或基因组ID）。"), "ERROR")
        return False

    genome_sources = get_genome_data_sources(config, logger_func=log)
    if not genome_sources:
        log(_("错误: 未能加载基因组源数据。"), "ERROR")
        return False

    bsa_genome_info: Optional[GenomeSourceItem] = genome_sources.get(bsa_assembly_id)
    hvg_genome_info: Optional[GenomeSourceItem] = genome_sources.get(hvg_assembly_id)

    if not bsa_genome_info or not hvg_genome_info:
        log(_("错误: BSA基因组 '{}' 或 HVG基因组 '{}' 未在基因组源列表中找到。").format(bsa_assembly_id, hvg_assembly_id), "ERROR")
        return False

    # 加载数据文件
    progress(10, _("加载输入数据..."))
    try:
        all_sheets_data = pd.read_excel(input_excel, sheet_name=None, engine='openpyxl')
        bsa_df = all_sheets_data[bsa_sheet_name].copy()
        hvg_df = all_sheets_data[hvg_sheet_name].copy()

        s_to_b_homology_df, b_to_t_homology_df = None, None
        if bsa_assembly_id != hvg_assembly_id:
            homology_bsa_to_bridge_path = get_local_downloaded_file_path(config, bsa_genome_info, 'homology_ath')
            homology_bridge_to_hvg_path = get_local_downloaded_file_path(config, hvg_genome_info, 'homology_ath')
            s_to_b_homology_df = pd.read_excel(homology_bsa_to_bridge_path)
            b_to_t_homology_df = pd.read_excel(homology_bridge_to_hvg_path)
    except Exception as e:
        log(_("加载Excel或同源文件时发生错误: {}").format(e), "ERROR")
        return False

    # 准备GFF数据库
    progress(25, _("准备GFF数据库..."))
    gff_db_dir = pipeline_cfg.gff_db_storage_dir
    force_gff_db_creation = pipeline_cfg.force_gff_db_creation
    gff_file_path_bsa_assembly = get_local_downloaded_file_path(config, bsa_genome_info, 'gff3')
    db_A_path = os.path.join(gff_db_dir, f"{bsa_assembly_id}_genes.db")
    gff_A_db = create_gff_database(gff_file_path_bsa_assembly, db_path=db_A_path, force=force_gff_db_creation, status_callback=log)
    if not gff_A_db:
        log(_("错误: 创建/加载源基因组 {} 的GFF数据库失败。").format(bsa_assembly_id), "ERROR"); return False

    gff_B_db = gff_A_db
    if bsa_assembly_id != hvg_assembly_id:
        gff_file_path_hvg_assembly = get_local_downloaded_file_path(config, hvg_genome_info, 'gff3')
        db_B_path = os.path.join(gff_db_dir, f"{hvg_assembly_id}_genes.db")
        gff_B_db = create_gff_database(gff_file_path_hvg_assembly, db_path=db_B_path, force=force_gff_db_creation, status_callback=log)
        if not gff_B_db:
            log(_("错误: 创建/加载目标基因组 {} 的GFF数据库失败。").format(hvg_assembly_id), "ERROR"); return False

    # 从BSA区域提取基因
    progress(40, _("从BSA区域提取基因..."))
    source_genes_in_bsa_regions_data = []

    bsa_cols = pipeline_cfg.bsa_columns

    for bsa_idx, bsa_row in bsa_df.iterrows():
        try:
            chrom, start, end = str(bsa_row[bsa_cols['chr']]), int(bsa_row[bsa_cols['start']]), int(bsa_row[bsa_cols['end']])
            genes_in_region = get_genes_in_region(assembly_id=bsa_assembly_id, gff_filepath=gff_file_path_bsa_assembly, db_storage_dir=gff_db_dir, region=(chrom, start, end), force_db_creation=force_gff_db_creation, status_callback=log)
            if not genes_in_region:
                source_genes_in_bsa_regions_data.append({"bsa_original_row_index": bsa_idx, "Match_Note": _("BSA区域无基因"), **bsa_row.to_dict()})
                continue
            for gene in genes_in_region:
                source_genes_in_bsa_regions_data.append({"bsa_original_row_index": bsa_idx, "Source_Gene_ID": gene['gene_id'], "Source_Chr": gene['chrom'], "Source_Start": gene['start'], "Source_End": gene['end'], **bsa_row.to_dict()})
        except Exception as e:
            log(_("处理BSA行 {} 时发生错误: {}").format(bsa_idx, e), "ERROR"); return False
    bsa_genes_df = pd.DataFrame(source_genes_in_bsa_regions_data)

    # 同源映射 (如果需要)
    mapped_hvg_gene_ids = {}
    if bsa_assembly_id != hvg_assembly_id:
        progress(50, _("执行跨版本同源映射..."))
        genes_to_map = bsa_genes_df['Source_Gene_ID'].dropna().unique().tolist()
        if genes_to_map:
            homology_cols = pipeline_cfg.homology_columns
            sel_criteria_s_to_b = asdict(pipeline_cfg.selection_criteria_source_to_bridge)
            sel_criteria_b_to_t = asdict(pipeline_cfg.selection_criteria_bridge_to_target)


            mapped_df, _c = map_genes_via_bridge(
                source_gene_ids=genes_to_map, source_assembly_name=bsa_assembly_id, target_assembly_name=hvg_assembly_id,
                source_to_bridge_homology_df=s_to_b_homology_df, bridge_to_target_homology_df=b_to_t_homology_df,
                s_to_b_query_col=homology_cols['query'], s_to_b_match_col=homology_cols['match'],
                b_to_t_query_col=homology_cols['query'], b_to_t_match_col=homology_cols['match'],
                selection_criteria_s_to_b=sel_criteria_s_to_b, selection_criteria_b_to_t=sel_criteria_b_to_t,
                source_id_regex=bsa_genome_info.gene_id_regex, bridge_id_regex=bridge_id_regex, target_id_regex=hvg_genome_info.gene_id_regex,
                status_callback=lambda msg, level="INFO": log(f"[Homology] {msg}", level), cancel_event=cancel_event
            )
            for _b, row in mapped_df.iterrows():
                mapped_hvg_gene_ids.setdefault(row['Source_Gene_ID'], []).append(row['Target_Gene_ID'])
    else:
        progress(50, _("基因组版本相同，跳过映射。"))
        mapped_hvg_gene_ids = {gid: [gid] for gid in bsa_genes_df['Source_Gene_ID'].dropna().unique()}

    # 合并与筛选
    progress(70, _("合并HVG数据并筛选候选基因..."))
    hvg_cols = pipeline_cfg.hvg_columns
    hvg_info_map = hvg_df.set_index(hvg_cols['gene_id']).to_dict(orient='index')
    final_data = []
    for _n, bsa_gene_row in bsa_genes_df.iterrows():
        source_gene_id = bsa_gene_row.get('Source_Gene_ID')
        hvg_ids = mapped_hvg_gene_ids.get(source_gene_id, []) if pd.notna(source_gene_id) else []
        if hvg_ids:
            for hvg_id in hvg_ids:
                hvg_data = hvg_info_map.get(hvg_id, {})
                hvg_gene_info = extract_gene_details(gff_B_db, hvg_id) if gff_B_db else {}
                row = {**bsa_gene_row, "Mapped_HVG_Gene_ID": hvg_id, "HVG_Chr": hvg_gene_info.get('chrom'), **hvg_data}
                final_data.append(row)
        else:
            final_data.append(bsa_gene_row.to_dict())

    integrated_df = pd.DataFrame(final_data)
    log2fc_thresh = pipeline_cfg.common_hvg_log2fc_threshold
    if hvg_cols.get('category') in integrated_df.columns and hvg_cols.get('log2fc') in integrated_df.columns:
        cond_tophvg = integrated_df[hvg_cols['category']] == 'TopHVG'
        cond_common = (integrated_df[hvg_cols['category']] == 'CommonTopHVG') & (pd.to_numeric(integrated_df[hvg_cols['log2fc']], errors='coerce').abs() >= log2fc_thresh)
        integrated_df['Is_Candidate'] = cond_tophvg | cond_common
    else:
        integrated_df['Is_Candidate'] = False

    # 保存结果
    progress(90, _("正在保存结果到Excel..."))
    try:
        with pd.ExcelWriter(input_excel, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            integrated_df.to_excel(writer, sheet_name=output_sheet_name, index=False)
        log(_("整合分析结果已成功写入到 '{}' 的 '{}' 工作表。").format(input_excel, output_sheet_name), "SUCCESS")
        overall_success = True
    except Exception as e:
        log(_("错误: 写入结果到Excel时发生错误: {}").format(e), "ERROR")
        overall_success = False

    progress(100, _("流程结束。"))
    return overall_success


def run_homology_mapping(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: Optional[List[str]] = None,
        region: Optional[Tuple[str, int, int]] = None,
        output_csv_path: Optional[str] = None,
        criteria_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Callable = print,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
):
    """执行同源映射的核心函数，可处理基因列表或区域输入。"""
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: log(f"进度 {p}%: {m}")

    if not gene_ids and not region:
        log(_("错误：必须提供基因ID列表或基因组区域之一。"), "ERROR");
        return

    pipeline_cfg = config.integration_pipeline
    project_root = os.path.dirname(config._config_file_abs_path_) if config._config_file_abs_path_ else '.'
    gff_db_dir = os.path.join(project_root, pipeline_cfg.gff_db_storage_dir);
    os.makedirs(gff_db_dir, exist_ok=True)

    s2b_criteria = _update_criteria_from_cli(pipeline_cfg.selection_criteria_source_to_bridge, criteria_overrides)
    b2t_criteria = _update_criteria_from_cli(pipeline_cfg.selection_criteria_bridge_to_target, criteria_overrides)
    log(_("使用的筛选标准: {}").format(asdict(s2b_criteria)), "DEBUG")

    genome_sources = get_genome_data_sources(config, logger_func=log)
    source_genome_info = genome_sources.get(source_assembly_id)
    target_genome_info = genome_sources.get(target_assembly_id)
    if not source_genome_info or not target_genome_info:
        log(_("错误: 未能在基因组源列表中找到源或目标基因组信息。"), "ERROR");
        return

    # --- 检查并记录同源库版本 ---
    if source_genome_info.bridge_version and source_genome_info.bridge_version.lower() == 'tair10':
        log(f"注意: 源基因组 '{source_assembly_id}' 使用的是较旧的 tair10 拟南芥同源数据库。", "WARNING")
    if target_genome_info.bridge_version and target_genome_info.bridge_version.lower() == 'tair10':
        log(f"注意: 目标基因组 '{target_assembly_id}' 使用的是较旧的 tair10 拟南芥同源数据库。", "WARNING")
    # ...

    genes_to_map = gene_ids
    if region:
        progress(10, _("正在从指定区域提取基因..."))
        source_gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        if not source_gff_path or not os.path.exists(source_gff_path):
            log(_("错误: 源基因组 '{}' 的GFF文件未找到。").format(source_assembly_id), "ERROR");
            return
        genes_to_map = [g['gene_id'] for g in
                        get_genes_in_region(assembly_id=source_assembly_id, gff_filepath=source_gff_path,
                                            db_storage_dir=gff_db_dir, region=region,
                                            force_db_creation=pipeline_cfg.force_gff_db_creation, status_callback=log)]
        if not genes_to_map:
            log(_("警告: 在指定区域 {} 中未找到任何基因。").format(region), "WARNING");
            return
        log(_("从区域中找到 {} 个基因进行映射。").format(len(genes_to_map)))

    progress(30, _("正在加载同源文件..."))
    s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
    b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')
    if not s_to_b_homology_file or not os.path.exists(
            s_to_b_homology_file) or not b_to_t_homology_file or not os.path.exists(b_to_t_homology_file):
        log(_("错误: 找不到一个或多个同源映射文件。请先下载数据。"), "ERROR");
        return

    s_to_b_df = _load_data_file(s_to_b_homology_file, log)
    b_to_t_df = _load_data_file(b_to_t_homology_file, log)

    progress(50, _("开始通过桥梁物种进行映射..."))
    homology_cols = pipeline_cfg.homology_columns

    result_df, a_ = map_genes_via_bridge(
        source_gene_ids=genes_to_map,
        source_assembly_name=source_assembly_id,
        target_assembly_name=target_assembly_id,
        bridge_species_name=pipeline_cfg.bridge_species_name,  # <--- 补上
        source_to_bridge_homology_df=s_to_b_df,
        bridge_to_target_homology_df=b_to_t_df,
        selection_criteria_s_to_b=asdict(s2b_criteria),
        selection_criteria_b_to_t=asdict(b2t_criteria),
        homology_columns=pipeline_cfg.homology_columns, # <--- 补上
        source_genome_info=source_genome_info,         # <--- 补上
        target_genome_info=target_genome_info,         # <--- 补上
        status_callback=log,
        cancel_event=cancel_event,
        bridge_id_regex=bridge_id_regex # 通过kwargs传递
    )

    if result_df.empty: log(_("映射完成，但未找到任何有效的同源关系。"), "WARNING"); return
    progress(90, _("映射完成，正在整理并保存结果..."))

    final_output_path = output_csv_path
    if not final_output_path:
        output_dir = os.path.join(project_root, "homology_results")
        os.makedirs(output_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_output_path = os.path.join(output_dir,
                                         f"map_{source_assembly_id}_to_{target_assembly_id}_{timestamp}.csv")

    result_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
    log(_("同源映射流程成功完成，结果已保存至: {}").format(final_output_path), "SUCCESS")


def run_ai_task(
        config: MainConfig,
        input_file: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str],
        cli_overrides: Optional[Dict[str, Any]],
        status_callback: Callable,
        cancel_event: Optional[threading.Event] = None
):
    """【修正】执行AI任务流程，正确创建AI客户端。"""
    batch_cfg = config.batch_ai_processor
    _update_config_from_overrides(batch_cfg, cli_overrides)

    status_callback(_("AI任务流程开始..."))

    # --- 【核心修正】创建AI客户端实例 ---
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
    # --- 修正结束 ---

    project_root = os.path.dirname(config._config_file_abs_path_) if config._config_file_abs_path_ else '.'
    output_dir = os.path.join(project_root, batch_cfg.output_dir_name)

    prompt_to_use = custom_prompt_template
    if not prompt_to_use:
        prompt_to_use = config.ai_prompts.translation_prompt if task_type == 'translate' else config.ai_prompts.analysis_prompt

    process_single_csv_file(
        client=ai_client,  # 传递已创建的客户端
        input_csv_path=input_file,
        output_csv_directory=output_dir,
        source_column_name=source_column,
        new_column_name=new_column,
        system_prompt=_("你是一个专业的生物信息学分析助手。"),
        user_prompt_template=prompt_to_use,
        task_identifier=f"{os.path.basename(input_file)}_{task_type}",
        max_row_workers=batch_cfg.max_workers
    )

    status_callback(_("AI任务流程成功完成。"))


def run_functional_annotation(
        config: MainConfig,
        gene_ids: List[str],
        assembly_id: str,
        annotation_types: List[str],
        output_csv_path: Optional[str] = None,
        status_callback: Callable = print,
        progress_callback: Optional[Callable] = None,
        **kwargs
):
    """执行功能注释流程。"""
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: log(f"进度 {p}%: {m}")

    log(_("功能注释流程开始..."))

    genome_sources = get_genome_data_sources(config, logger_func=log)
    genome_info = genome_sources.get(assembly_id)
    if not genome_info:
        log(f"错误: 未在配置中找到基因组 '{assembly_id}' 的信息。", "ERROR")
        return

    try:
        annotator = Annotator(
            main_config=config,
            genome_info=genome_info,
            status_callback=log,
            progress_callback=progress
        )
        result_df = annotator.annotate_genes(gene_ids, annotation_types)

        if result_df.empty:
            log("警告: 未找到任何注释信息。", "WARNING")
            return

        final_output_path = output_csv_path
        if not final_output_path:
            project_root = os.path.dirname(config._config_file_abs_path_) if config._config_file_abs_path_ else '.'
            output_dir = os.path.join(project_root, config.annotation_tool.output_dir_name)
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            final_output_path = os.path.join(output_dir, f"annotation_{assembly_id}_{timestamp}.csv")

        result_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
        log(_("功能注释结果已保存到: {}").format(final_output_path), "SUCCESS")

    except Exception as e:
        log(f"执行功能注释时发生错误: {e}", "ERROR")
        logger.exception("完整错误堆栈:")


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