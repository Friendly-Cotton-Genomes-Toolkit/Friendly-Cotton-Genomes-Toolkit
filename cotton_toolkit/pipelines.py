# cotton_toolkit/pipelines.py

import logging
import os
import re
import tempfile
import threading
import time
from concurrent.futures import as_completed, ThreadPoolExecutor
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
                hvg_gene_info = extract_gene_details(gff_B_db) if gff_B_db else {}
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
        bridge_species_name=pipeline_cfg.bridge_species_name,
        source_to_bridge_homology_df=s_to_b_df,
        bridge_to_target_homology_df=b_to_t_df,
        selection_criteria_s_to_b=asdict(s2b_criteria),
        selection_criteria_b_to_t=asdict(b2t_criteria),
        homology_columns=pipeline_cfg.homology_columns,
        source_genome_info=source_genome_info,
        target_genome_info=target_genome_info,
        status_callback=log,
        cancel_event=cancel_event,
        bridge_id_regex=bridge_id_regex
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


# (紧跟在 run_homology_mapping 函数之后添加)

def run_locus_conversion(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        region: Tuple[str, int, int],
        status_callback: Callable = print,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
) -> Optional[str]:
    """
    专用于位点转换。
    优先在目标基因组中寻找与源染色体同名的染色体。如果找不到，则回退到
    寻找包含最多同源基因的染色体策略。

    Args:
        config: 主配置对象。
        source_assembly_id: 源基因组的ID。
        target_assembly_id: 目标基因组的ID。
        region: 一个元组，表示源基因组中的区域 (chrom, start, end)。
        status_callback: 用于状态更新的回调函数。
        progress_callback: 用于进度更新的回调函数。
        cancel_event: 用于取消任务的线程事件。

    Returns:
        一个包含目标区域范围的字符串，或者在失败/无结果时返回 None。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: log(f"进度 {p}%: {m}")

    temp_output_path = None
    try:
        # 为了获取中间的同源映射结果，我们创建一个临时文件
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', encoding='utf-8-sig') as tmp_file:
            temp_output_path = tmp_file.name

        log(_("步骤 1/3: 正在执行核心同源映射..."))

        # 调用通用的、输出文件到CSV的 run_homology_mapping 函数
        # 它会处理从区域提取基因ID的逻辑
        run_homology_mapping(
            config=config,
            source_assembly_id=source_assembly_id,
            target_assembly_id=target_assembly_id,
            region=region,
            output_csv_path=temp_output_path,
            status_callback=status_callback,
            progress_callback=progress_callback,
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            log(_("任务已取消。"), "WARNING")
            return None

        # 检查映射是否成功生成了包含数据的文件
        if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) == 0:
            log(_("核心映射未产生任何结果，无法进行位点转换。"), "WARNING")
            return None

        # 从临时文件中读取目标基因ID
        result_df = pd.read_csv(temp_output_path)
        if result_df.empty or 'Target_Gene_ID' not in result_df.columns:
            log(_("映射结果为空或格式不正确。"), "WARNING")
            return None

        target_gene_ids = result_df['Target_Gene_ID'].dropna().unique().tolist()
        if not target_gene_ids:
            log(_("映射成功但未能提取任何有效的目标基因ID。"), "WARNING")
            return None

    finally:
        # 无论成功与否，都确保删除临时文件
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                os.remove(temp_output_path)
                log(_("已清理临时文件。"), "DEBUG")
            except OSError as e:
                log(f"{_('清理临时文件时出错')}: {e}", "WARNING")

    # --- 从这里开始的逻辑，用于计算坐标范围 ---

    log(_("步骤 2/3: 正在为 {} 个目标基因查询坐标...").format(len(target_gene_ids)))

    # 获取GFF文件路径
    try:
        genome_sources = get_genome_data_sources(config, logger_func=log)
        target_genome_info = genome_sources.get(target_assembly_id)
        target_gff_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')
        gff_db_dir = os.path.join(os.path.dirname(config._config_file_abs_path_),
                                  config.integration_pipeline.gff_db_storage_dir)
    except Exception as e:
        log(f"{_('获取目标GFF文件路径时出错')}: {e}", "ERROR")
        return None

    if not target_gff_path or not os.path.exists(target_gff_path):
        log(_("错误: 目标基因组 '{}' 的GFF文件未找到，无法计算坐标。").format(target_assembly_id), "ERROR")
        return None

    # 查询坐标
    target_coords_df = get_gene_info_by_ids(
        assembly_id=target_assembly_id,
        gff_filepath=target_gff_path,
        db_storage_dir=gff_db_dir,
        gene_ids=target_gene_ids,
        force_db_creation=config.integration_pipeline.force_gff_db_creation,
        status_callback=log
    )

    if target_coords_df.empty:
        log(_("未能查询到任何目标基因的坐标信息。"), "WARNING")
        return None

    log(_("步骤 3/3: 正在按指定规则筛选主要同源区域..."))

    source_chrom_name = region[0]
    final_coords_df = None
    best_target_chrom = None

    # 1. 优先策略：尝试寻找与源染色体完全同名的目标染色体
    direct_match_df = target_coords_df[target_coords_df['chrom'] == source_chrom_name]

    if not direct_match_df.empty:
        # 如果找到了同名染色体，并且上面有基因，就用它
        log(f"INFO: 已成功筛选出与源染色体同名的目标染色体 '{source_chrom_name}' 上的同源基因。", "INFO")
        final_coords_df = direct_match_df
        best_target_chrom = source_chrom_name
    else:
        # 2. 回退策略：如果找不到同名染色体，则使用“最多基因”策略
        log(f"WARNING: 在目标基因组中未找到名为 '{source_chrom_name}' 的同源染色体。将回退到查找包含最多同源基因的染色体。",
            "WARNING")

        chrom_hit_counts = target_coords_df['chrom'].value_counts()
        log(f"DEBUG: 各目标染色体上的同源基因数量: {chrom_hit_counts.to_dict()}", "DEBUG")

        if not chrom_hit_counts.empty:
            # 识别基因数量最多的染色体
            best_target_chrom_from_counts = chrom_hit_counts.index[0]
            log(f"INFO: 回退策略: 已选择包含最多同源基因的染色体 '{best_target_chrom_from_counts}' ({chrom_hit_counts.iloc[0]} 个基因) 作为输出。",
                "INFO")

            # 筛选出只属于这个“最多基因”染色体的坐标
            final_coords_df = target_coords_df[target_coords_df['chrom'] == best_target_chrom_from_counts]
            best_target_chrom = best_target_chrom_from_counts
        else:
            log("ERROR: 无法确定主要目标染色体。", "ERROR")
            return None

    # 确保我们最终有数据可以处理
    if final_coords_df is None or final_coords_df.empty:
        log("ERROR: 经过筛选后，没有可用于计算区间的坐标数据。", "ERROR")
        return None

    # 3. 在最终选定的数据集上计算外包围框
    min_start_val = final_coords_df['start'].min()
    max_end_val = final_coords_df['end'].max()

    # 4. 格式化最终的输出字符串
    final_output_string = f"{best_target_chrom}:{min_start_val}-{max_end_val}"

    log(_("成功转换为目标区域: {}").format(final_output_string), "SUCCESS")
    return final_output_string



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


# GO KEGG 富集分析
def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
):
    """
    【ID修正版】执行数据下载流程。
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
        enrichment_df = run_go_enrichment(study_gene_ids=study_gene_ids, gaf_path=gaf_path, output_dir=output_dir, status_callback=log, gene_id_regex=gene_id_regex)

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