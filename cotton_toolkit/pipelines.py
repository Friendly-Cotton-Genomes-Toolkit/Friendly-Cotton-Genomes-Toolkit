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
                log(f"在区域 {region} 中未找到任何基因。", "WARNING");
                return None
            source_gene_ids = [gene['gene_id'] for gene in genes_in_region_list]

        if not source_gene_ids:
            log(_("错误: 输入的基因列表为空。"), "ERROR");
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
            selection_criteria_s_to_b = type(selection_criteria_s_to_b)(**s2b_dict)
            selection_criteria_b_to_t = type(selection_criteria_b_to_t)(**b2t_dict)
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
    【已修改】通过调用核心同源映射流程，执行基于区域的位点转换。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")
    try:
        log("位点转换任务正在调用核心同源映射流程...", "INFO")
        run_homology_mapping(
            config=config,
            source_assembly_id=source_assembly_id,
            target_assembly_id=target_assembly_id,
            gene_ids=None,
            region=region,
            output_csv_path=output_path,
            criteria_overrides=criteria_overrides,
            status_callback=status_callback,
            calculate_target_locus=True,  # <<< 核心修改：强制开启位点计算
            progress_callback=kwargs.get('progress_callback'),
            cancel_event=kwargs.get('cancel_event')
        )
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
        gene_list_path: str,
        source_genome: str,
        target_genome: str,
        bridge_species: str,
        annotation_db_path: str,
        output_dir: str,
        status_callback: Callable[[str, str], None],
        progress_callback: Optional[Callable] = None,
        # 其他您可能需要的参数...
):
    """
    执行功能注释流水线，按需进行同源转换并解决参数问题。
    """
    log = lambda msg, level="INFO": status_callback(f"[{level}] {msg}")

    # --- 步骤 1: 准备输入基因列表 ---
    try:
        study_genes_df = pd.read_csv(gene_list_path)
        source_gene_ids = study_genes_df.iloc[:, 0].dropna().unique().tolist()
        if not source_gene_ids:
            log("输入的基因列表为空。", "ERROR")
            return
    except Exception as e:
        log(f"读取基因列表时出错: {e}", "ERROR")
        return

    genes_to_annotate = source_gene_ids
    original_to_target_map_df = None

    # --- 步骤 2: 按需进行同源转换 (参数准备) ---
    if source_genome != target_genome:
        log(f"源基因组 ({source_genome}) 与目标基因组 ({target_genome}) 不同，准备进行同源转换。", "INFO")

        # 2.1 获取所有基因组的配置信息
        genome_sources = get_genome_data_sources(config, logger_func=log)
        source_genome_info = genome_sources.get(source_genome)
        target_genome_info = genome_sources.get(target_genome)
        bridge_genome_info = genome_sources.get(bridge_species)

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            log("一个或多个基因组名称无效，无法找到配置信息。", "ERROR")
            return

        # 2.2 获取必要的同源文件路径
        s_to_b_homology_file = get_local_downloaded_file_path(config.data_dir,
                                                              source_genome_info.get_homology_file(bridge_species))
        b_to_t_homology_file = get_local_downloaded_file_path(config.data_dir,
                                                              target_genome_info.get_homology_file(bridge_species))

        if not s_to_b_homology_file or not b_to_t_homology_file:
            log("缺少必要的同源文件，无法进行转换。", "ERROR")
            return

        # 2.3 加载同源文件为DataFrame
        source_to_bridge_homology_df = create_homology_df(s_to_b_homology_file)
        bridge_to_target_homology_df = create_homology_df(b_to_t_homology_file)

        # 2.4 准备其他参数
        selection_criteria_s_to_b = config.get_selection_criteria(source_genome)
        selection_criteria_b_to_t = config.get_selection_criteria(target_genome)
        homology_columns = config.get_homology_columns_config()

        # 2.5 调用核心映射函数
        log("正在通过桥梁物种进行基因映射...", "INFO")
        mapped_df, _ = map_genes_via_bridge(
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
            bridge_genome_info=bridge_genome_info,  # 传递桥梁物种信息
            status_callback=status_callback
        )

        if mapped_df is None or mapped_df.empty:
            log("同源转换未能映射到任何基因，流程终止。", "WARNING")
            return

        # 更新待注释的基因列表为转换后的目标基因ID
        genes_to_annotate = mapped_df['Target_Gene_ID'].dropna().unique().tolist()
        original_to_target_map_df = mapped_df[['Source_Gene_ID', 'Target_Gene_ID']]

    # --- 步骤 3: 初始化 Annotator 并执行注释 ---
    log("正在初始化注释器...", "INFO")
    cache_dir = os.path.join(output_dir, '.cache')  # 定义缓存目录

    # 使用正确的参数初始化 Annotator
    annotator = Annotator(
        annotation_db_path=annotation_db_path,
        target_genome_id=target_genome,  # 明确目标基因组
        status_callback=status_callback,
        cache_dir=cache_dir
    )

    log(f"正在为 {len(genes_to_annotate)} 个基因执行功能注释...", "INFO")
    result_df = annotator.annotate_gene_list(genes_to_annotate)  # 传入待注释的基因列表

    # --- 步骤 4: 处理并保存结果 ---
    if result_df is not None and not result_df.empty:
        # 如果进行了同源转换，将注释结果与原始基因ID关联起来
        if original_to_target_map_df is not None:
            # result_df 的第一列是目标基因ID，我们将其重命名以便合并
            result_df.rename(columns={result_df.columns[0]: 'Target_Gene_ID'}, inplace=True)
            final_df = pd.merge(original_to_target_map_df, result_df, on='Target_Gene_ID', how='left')
        else:
            final_df = result_df

        output_file = os.path.join(output_dir, f"{os.path.basename(gene_list_path)}_annotated.csv")
        final_df.to_csv(output_file, index=False)
        log(f"注释成功！结果已保存至: {output_file}", "SUCCESS")
    else:
        log("注释完成，但没有生成任何结果。", "WARNING")




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
