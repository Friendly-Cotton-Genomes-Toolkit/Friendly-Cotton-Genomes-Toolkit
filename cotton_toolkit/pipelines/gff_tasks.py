import logging
import os
import threading
import time
from typing import Optional, List, Tuple, Callable

import pandas as pd

from cotton_toolkit import GFF3_DB_DIR
from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.gff_parser import get_gene_info_by_ids, get_genes_in_region
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.utils.gene_utils import resolve_gene_ids, _to_gene_id

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.gff_tasks")


@pipeline_task(_("GFF检索"))
def run_gff_lookup(
        config: MainConfig,
        assembly_id: str,
        gene_ids: Optional[List[str]] = None,
        region: Optional[Tuple[str, int, int]] = None,
        output_csv_path: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> bool:
    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']



    if not gene_ids and not region:
        raise ValueError(_("错误: 必须提供基因ID列表或染色体区域进行查询。"))


    progress(0, "流程开始，正在初始化配置...")
    if check_cancel(): return False
    logger.info("开始GFF基因查询流程...")

    # --- 以下是核心修改 ---
    try:
        # 1. 定位 GFF 文件和预期的数据库存储目录
        project_root = os.path.dirname(config.config_file_abs_path_)
        genome_sources = get_genome_data_sources(config)
        selected_genome_info = genome_sources.get(assembly_id)
        if not selected_genome_info:
            raise ValueError(f"错误: 基因组 '{assembly_id}' 未在基因组源列表中找到。")


        gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')
        if not gff_file_path or not os.path.exists(gff_file_path):
            raise FileNotFoundError(f"错误: 未找到基因组 '{assembly_id}' 的GFF文件。请先下载数据。")


        gff_db_dir = os.path.join(project_root, GFF3_DB_DIR)
        expected_db_path = os.path.join(gff_db_dir, f"{assembly_id}_genes.db")

        # 2. 检查预处理的数据库是否存在，不存在则报错
        if not os.path.exists(expected_db_path):
            error_message = (
                f"错误: 未找到预处理的GFF数据库 '{os.path.basename(expected_db_path)}'。\n\n"
                "请先前往“数据下载”选项卡，找到对应的基因组，并点击“预处理”按钮来创建数据库，以加速查询。"
            )
            raise FileNotFoundError(error_message)

        force_creation = False

    except Exception as e:
        logger.error(f"在准备GFF查询时发生错误: {e}")
        raise e

    results_df = pd.DataFrame()
    progress(40, _("正在数据库中查询..."))
    if check_cancel(): return False
    if gene_ids:
        try:
            logger.info(_("正在对输入的基因ID进行智能解析..."))
            resolved_ids = resolve_gene_ids(config, assembly_id, gene_ids,'id','gff')
            # GFF查询通常使用基础基因ID，所以我们在这里统一为基础ID
            final_ids_to_query = list(set(_to_gene_id(gid) for gid in resolved_ids))
            logger.info(_("按基因ID查询 {} 个基因... (已完成智能解析)").format(len(final_ids_to_query)))

            results_df = get_gene_info_by_ids(
                assembly_id=assembly_id, gff_filepath=gff_file_path,
                gene_ids=final_ids_to_query,
                force_db_creation=force_creation,
                progress_callback=lambda p, m: progress(40 + int(p * 0.4), _("查询基因ID: {}").format(m))
            )
        except (ValueError, FileNotFoundError) as e:
            raise e


    elif region:
        chrom, start, end = region
        logger.info(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end))
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
