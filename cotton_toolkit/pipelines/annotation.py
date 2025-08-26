import os
import re
import threading
import time
from typing import List, Optional, Callable, Dict
import logging
import pandas as pd

from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig, HomologySelectionCriteria
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.tools.annotator import Annotator
from cotton_toolkit.tools.enrichment_analyzer import run_go_enrichment, run_kegg_enrichment
from cotton_toolkit.tools.visualizer import plot_enrichment_bubble, plot_enrichment_bar, plot_enrichment_upset, \
    plot_enrichment_cnet, _generate_r_script_and_data
from cotton_toolkit.utils.gene_utils import resolve_gene_ids, map_transcripts_to_genes


try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.annotation")


@pipeline_task(_("功能注释"))
def run_functional_annotation(
        config: MainConfig,
        assembly_id: str,
        annotation_types: List[str],
        output_path: str,
        gene_ids: Optional[List[str]] = None,
        gene_list_path: Optional[str] = None,
        custom_db_dir: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> None:

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    progress(0, _("准备输入基因列表..."))
    if check_cancel(): return

    # 步骤 1: 准备和解析输入的基因ID列表
    resolved_gene_ids = []
    if gene_ids:
        try:
            progress(5, _("正在智能解析输入基因ID..."))
            resolved_gene_ids = resolve_gene_ids(config, assembly_id, gene_ids)
            logger.info(_("从参数智能解析了 {} 个唯一基因ID。").format(len(resolved_gene_ids)))
        except (ValueError, FileNotFoundError) as e:
            raise e

    elif gene_list_path and os.path.exists(gene_list_path):
        try:
            progress(5, _("正在从文件读取基因列表..."))
            study_genes_df = pd.read_csv(gene_list_path)
            raw_gene_ids = study_genes_df.iloc[:, 0].dropna().unique().tolist()
            resolved_gene_ids = resolve_gene_ids(config, assembly_id, raw_gene_ids)
            logger.info(_("从文件中读取并解析了 {} 个唯一基因ID。").format(len(resolved_gene_ids)))
        except Exception as e:
            raise IOError(_("读取或解析基因列表文件时出错: {}").format(e))

    else:
        raise ValueError(_("错误: 必须提供 'gene_ids' 或有效的 'gene_list_path' 参数之一。"))

    if not resolved_gene_ids:
        raise ValueError(_("输入的基因列表为空或无法解析，流程终止。"))

    # 创建一个基础DataFrame，用于最后合并结果
    final_df_base = pd.DataFrame({'Gene_ID': resolved_gene_ids})

    progress(20, _("初始化注释器..."))
    if check_cancel(): return

    # 步骤 2: 初始化注释器 (Annotator)
    genome_sources = get_genome_data_sources(config)
    genome_info = genome_sources.get(assembly_id)
    if not genome_info:
        raise ValueError(_("错误：无法为目标基因组 {} 找到配置信息。").format(assembly_id))

    annotator = Annotator(
        main_config=config,
        genome_id=assembly_id,
        genome_info=genome_info,
        progress_callback=lambda p, m: progress(30 + int(p * 0.6), _("执行注释: {}").format(m)),
        custom_db_dir=custom_db_dir
    )

    progress(90, _("正在执行功能注释..."))
    if check_cancel(): return

    # 步骤 3: 直接使用解析后的基因ID列表进行注释
    result_df = annotator.annotate_genes(resolved_gene_ids, annotation_types)

    if cancel_event and cancel_event.is_set():
        return

    progress(95, _("整理并保存结果..."))
    if check_cancel(): return

    # 步骤 4: 整理并保存结果
    if result_df is not None and not result_df.empty:
        # 直接将注释结果与原始基因列表进行合并
        final_df = pd.merge(final_df_base, result_df, on='Gene_ID', how='left')

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            logger.info(_("注释成功！结果已保存至: {}").format(output_path))
        except Exception as e:
            raise IOError(_("保存结果到 {} 时发生错误: {}").format(output_path, e))

    else:
        logger.warning(_("注释完成，但没有生成任何结果。"))

    progress(100, _("功能注释流程结束。"))


@pipeline_task(_("富集分析"))
def run_enrichment_pipeline(
        config: MainConfig,
        assembly_id: str,
        study_gene_ids: List[str],
        analysis_type: str,
        plot_types: List[str],
        output_dir: str,
        gene_log2fc_map: Optional[Dict[str, float]] = None,
        collapse_transcripts: bool = False,
        top_n: int = 20,
        sort_by: str = 'FDR',
        show_title: bool = True,
        width: float = 10,
        height: float = 8,
        file_format: str = 'png',
        **kwargs
) -> Optional[str]:

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    progress(0, _("富集分析与可视化流程启动。"))
    if check_cancel(): return None
    logger.info(_("{} 富集与可视化流程启动。").format(analysis_type.upper()))

    progress(2, _("正在智能解析研究基因ID..."))
    resolved_study_ids = resolve_gene_ids(config, assembly_id, study_gene_ids)
    logger.info(_("ID智能解析完成，得到 {} 个标准化的ID。").format(len(resolved_study_ids)))

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
            raise ValueError(_("无法在配置中找到基因组 '{}'。").format(assembly_id))

    except Exception as e:
        logger.error(_("获取基因组源数据时失败: {}").format(e))
        progress(100, _("任务终止：获取基因组信息失败。"))
        return None

    os.makedirs(output_dir, exist_ok=True)
    r_output_dir = os.path.join(output_dir, "R_scripts_and_data")
    enrichment_df = None

    if analysis_type == 'go':
        progress(20, _("正在执行GO富集分析..."))
        if check_cancel(): return None
        enrichment_df = run_go_enrichment(
            main_config=config,
            genome_info=genome_info,
            study_gene_ids=study_gene_ids,
            output_dir=output_dir,
            gene_id_regex=getattr(genome_info, 'gene_id_regex', None),
            progress_callback=lambda p, m: progress(20 + int(p * 0.4), f"GO富集: {m}")
        )
    elif analysis_type == 'kegg':
        progress(20, _("正在执行KEGG富集分析..."))
        if check_cancel(): return None
        enrichment_df = run_kegg_enrichment(
            main_config=config,
            genome_info=genome_info,
            study_gene_ids=study_gene_ids,
            output_dir=output_dir,
            gene_id_regex=getattr(genome_info, 'gene_id_regex', None),
            progress_callback=lambda p, m: progress(20 + int(p * 0.4), f"KEGG富集: {m}")
        )

    if check_cancel(): return None
    if enrichment_df is None or enrichment_df.empty:
        logger.warning(_("富集分析未发现任何显著结果，流程终止。"))
        progress(100, _("任务完成：无显著结果。"))
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
