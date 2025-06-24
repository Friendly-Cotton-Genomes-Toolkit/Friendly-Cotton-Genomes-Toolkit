# cotton_toolkit/casestudies/bsa_hvg_integration.py

import logging
import os
import pandas as pd
import threading
from typing import Optional, Callable, Dict, Any

# --- 正确的导入 ---
from ..config.models import MainConfig, GenomeSourceItem
from ..config.loader import get_genome_data_sources, get_local_downloaded_file_path
from ..core.gff_parser import create_gff_database, get_genes_in_region, extract_gene_details
from ..core.homology_mapper import map_genes_via_bridge

# --- 正确的日志记录器设置 ---
logger = logging.getLogger(__name__)
try:
    from builtins import _
except ImportError:
    def _(s):
        return s



def run_integrate_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    """
    (高级案例) 整合BSA定位结果和HVG基因数据，进行候选基因筛选和优先级排序。
    """
    log = status_callback if status_callback else lambda msg, level: logger.info(f"[{level}] {msg}")
    progress = progress_callback if progress_callback else lambda p, m: logger.info(f"[{p}%] {m}")

    pipeline_cfg = config.integration_pipeline
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None and hasattr(pipeline_cfg, key):
                setattr(pipeline_cfg, key, value)

    log(_("开始整合分析流程..."), "INFO")
    progress(0, _("初始化配置..."))

    # --- 核心逻辑开始 ---
    try:
        # 1. 校验配置和获取基因组信息
        if not all([pipeline_cfg.input_excel_path, pipeline_cfg.bsa_sheet_name, pipeline_cfg.hvg_sheet_name,
                    pipeline_cfg.bsa_assembly_id, pipeline_cfg.hvg_assembly_id]):
            log(_("错误: 整合分析所需的配置不完整（如Excel路径、Sheet名或基因组ID）。"), "ERROR")
            return False

        genome_sources = get_genome_data_sources(config, logger_func=log)
        if not genome_sources:
            log(_("错误: 未能加载基因组源数据。"), "ERROR")
            return False

        bsa_genome_info: Optional[GenomeSourceItem] = genome_sources.get(pipeline_cfg.bsa_assembly_id)
        hvg_genome_info: Optional[GenomeSourceItem] = genome_sources.get(pipeline_cfg.hvg_assembly_id)

        if not bsa_genome_info or not hvg_genome_info:
            log(_("错误: BSA基因组 '{}' 或 HVG基因组 '{}' 未在基因组源列表中找到。").format(
                pipeline_cfg.bsa_assembly_id, pipeline_cfg.hvg_assembly_id), "ERROR")
            return False

        bridge_genome_info = genome_sources.get(pipeline_cfg.bridge_species_name)

        # 2. 加载数据文件
        progress(10, _("加载输入数据..."))
        all_sheets_data = pd.read_excel(pipeline_cfg.input_excel_path, sheet_name=None, engine='openpyxl')
        bsa_df = all_sheets_data[pipeline_cfg.bsa_sheet_name].copy()
        hvg_df = all_sheets_data[pipeline_cfg.hvg_sheet_name].copy()

        s_to_b_homology_df, b_to_t_homology_df = None, None
        versions_are_different = pipeline_cfg.bsa_assembly_id != pipeline_cfg.hvg_assembly_id
        if versions_are_different:
            s_to_b_path = get_local_downloaded_file_path(config, bsa_genome_info, 'homology_ath')
            b_to_t_path = get_local_downloaded_file_path(config, hvg_genome_info, 'homology_ath')
            s_to_b_homology_df = pd.read_csv(s_to_b_path)
            b_to_t_homology_df = pd.read_csv(b_to_t_path)

        # 3. 准备GFF数据库
        progress(25, _("准备GFF数据库..."))
        gff_db_dir = config.integration_pipeline.gff_db_storage_dir
        force_gff_db = config.integration_pipeline.force_gff_db_creation
        gff_file_bsa = get_local_downloaded_file_path(config, bsa_genome_info, 'gff3')

        db_path_bsa = os.path.join(gff_db_dir, f"{pipeline_cfg.bsa_assembly_id}_genes.db")
        create_gff_database(gff_file_bsa, db_path=db_path_bsa, force=force_gff_db, status_callback=log)

        if versions_are_different:
            gff_file_hvg = get_local_downloaded_file_path(config, hvg_genome_info, 'gff3')
            db_path_hvg = os.path.join(gff_db_dir, f"{pipeline_cfg.hvg_assembly_id}_genes.db")
            create_gff_database(gff_file_hvg, db_path=db_path_hvg, force=force_gff_db, status_callback=log)

        # 4. 从BSA区域提取基因
        progress(40, _("从BSA区域提取基因..."))
        bsa_cols = pipeline_cfg.bsa_columns
        source_genes_data = []
        for _b, bsa_row in bsa_df.iterrows():
            region = (bsa_row[bsa_cols['chr']], bsa_row[bsa_cols['start']], bsa_row[bsa_cols['end']])
            genes_in_region = get_genes_in_region(pipeline_cfg.bsa_assembly_id, gff_file_bsa, gff_db_dir, region,
                                                  force_gff_db, log)
            for gene in genes_in_region:
                gene_info = extract_gene_details(gene)
                source_genes_data.append({**bsa_row.to_dict(), **gene_info})

        source_genes_df = pd.DataFrame(source_genes_data)

        # 5. 同源映射 (如果需要)
        if versions_are_different:
            progress(50, _("执行跨版本同源映射..."))
            genes_to_map = source_genes_df['gene_id'].dropna().unique().tolist()
            if genes_to_map:
                mapped_df, _b = map_genes_via_bridge(
                    source_gene_ids=genes_to_map,
                    source_assembly_name=pipeline_cfg.bsa_assembly_id,
                    target_assembly_name=pipeline_cfg.hvg_assembly_id,
                    bridge_species_name=pipeline_cfg.bridge_species_name,
                    source_to_bridge_homology_df=s_to_b_homology_df,
                    bridge_to_target_homology_df=b_to_t_homology_df,
                    selection_criteria_s_to_b=pipeline_cfg.selection_criteria_source_to_bridge.to_dict(),
                    selection_criteria_b_to_t=pipeline_cfg.selection_criteria_bridge_to_target.to_dict(),
                    homology_columns=pipeline_cfg.homology_columns,
                    source_genome_info=bsa_genome_info,
                    target_genome_info=hvg_genome_info,
                    bridge_genome_info=bridge_genome_info,
                    status_callback=log
                )
                # 合并映射结果
                source_genes_df = source_genes_df.merge(mapped_df, left_on='gene_id', right_on='Source_Gene_ID',
                                                        how='left')
                source_genes_df.rename(columns={'gene_id': 'Source_Gene_ID_Original'}, inplace=True)  # 避免列名冲突
            else:
                source_genes_df['Target_Gene_ID'] = None  # 如果没有基因需要映射
        else:
            progress(50, _("基因组版本相同，跳过映射。"))
            source_genes_df['Target_Gene_ID'] = source_genes_df['gene_id']

        # 6. 合并HVG数据并筛选
        progress(70, _("合并HVG数据并筛选候选基因..."))
        hvg_cols = pipeline_cfg.hvg_columns
        # 合并HVG数据
        final_df = source_genes_df.merge(hvg_df, left_on='Target_Gene_ID', right_on=hvg_cols['gene_id'], how='inner')

        # 筛选逻辑 (示例)
        log2fc_thresh = pipeline_cfg.common_hvg_log2fc_threshold
        if hvg_cols.get('log2fc') in final_df.columns:
            final_df['Is_Candidate'] = final_df[hvg_cols['log2fc']].abs() >= log2fc_thresh

        # 7. 保存结果
        progress(90, _("正在保存结果到Excel..."))
        with pd.ExcelWriter(pipeline_cfg.input_excel_path, engine='openpyxl', mode='a',
                            if_sheet_exists='replace') as writer:
            final_df.to_excel(writer, sheet_name=pipeline_cfg.output_sheet_name, index=False)

        log(_("整合分析结果已成功写入到 '{}' 的 '{}' 工作表。").format(
            pipeline_cfg.input_excel_path, pipeline_cfg.output_sheet_name), "SUCCESS")

        progress(100, _("流程结束。"))
        return True

    except Exception as e:
        log(f"整合分析流程发生严重错误: {e}", "ERROR")
        logger.exception("完整错误堆栈:")
        return False