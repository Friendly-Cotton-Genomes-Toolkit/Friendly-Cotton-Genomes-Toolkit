import os
import re
import threading
import time
from typing import List, Optional, Callable, Dict
import logging
import pandas as pd

from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig, HomologySelectionCriteria
from cotton_toolkit.core.homology_mapper import map_genes_via_bridge
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.tools.annotator import Annotator
from cotton_toolkit.core.data_access import create_homology_df
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
        source_genome: str,
        target_genome: str,
        bridge_species: str,
        annotation_types: List[str],
        output_dir: Optional[str] = None,
        output_path: Optional[str] = None,
        gene_list_path: Optional[str] = None,
        gene_ids: Optional[List[str]] = None,
        custom_db_dir: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> None:
    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    progress(0, _("准备输入基因列表..."))
    if check_cancel(): return

    source_gene_ids = []
    if gene_ids:
        try:
            progress(2, _("正在智能解析输入基因ID..."))
            source_gene_ids = resolve_gene_ids(config, source_genome, gene_ids)
            logger.info(_("从参数智能解析了 {} 个唯一基因ID。").format(len(source_gene_ids)))
        except (ValueError, FileNotFoundError) as e:
            logger.error(e)
            progress(100, _("任务终止：基因ID解析失败。"))
            return

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
    final_df_base = pd.DataFrame({'Source_Gene_ID': source_gene_ids})

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

        source_to_bridge_homology_df = create_homology_df(config, s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(25 + int(p * 0.1),
                                                                                                  _("加载同源数据: {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or source_to_bridge_homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return

        progress(35, _("正在解析桥梁到目标的同源文件..."))
        if check_cancel(): return

        bridge_to_target_homology_df = create_homology_df(config, b_to_t_homology_file,
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

        # 1. 创建包含基础基因ID的临时列
        mapped_df['base_gene_id'] = mapped_df['Target_Gene_ID'].apply(lambda x: re.sub(r'\.\d+$', '', str(x)))
        # 2. 使用这个基础ID列表进行注释
        genes_to_annotate = mapped_df['base_gene_id'].dropna().unique().tolist()
        # 3. 更新用于最终合并的基础DataFrame
        final_df_base = mapped_df

    progress(75, _("初始化注释器..."))
    if check_cancel(): return

    genome_sources = get_genome_data_sources(config)
    target_genome_info = genome_sources.get(target_genome)
    if not target_genome_info:
        logger.error(_("错误：无法为目标基因组 {} 找到配置信息。").format(target_genome))
        progress(100, _("任务终止：目标基因组配置错误。"))
        return

    annotator = Annotator(
        main_config=config,
        genome_id=target_genome,
        genome_info=target_genome_info,
        progress_callback=lambda p, m: progress(75 + int(p * 0.15), _("执行注释: {}").format(m)),
        custom_db_dir=custom_db_dir
    )

    progress(90, _("正在执行功能注释..."))
    if check_cancel(): return

    # annotator现在接收基础基因ID列表
    result_df = annotator.annotate_genes(genes_to_annotate, annotation_types)

    if cancel_event and cancel_event.is_set():
        progress(100, _("任务已取消。"))
        return

    progress(95, _("整理并保存结果..."))
    if check_cancel(): return

    if result_df is not None and not result_df.empty:
        if 'base_gene_id' in final_df_base.columns:
            # 1. 在注释结果中，将主键列重命名以匹配我们的临时列
            result_df = result_df.rename(columns={'Gene_ID': 'base_gene_id'})
            # 2. 使用共有的基础ID列进行安全合并
            final_df = pd.merge(final_df_base, result_df, on='base_gene_id', how='left')
            # 3. 移除辅助列
            final_df = final_df.drop(columns=['base_gene_id'])
        else:  # 如果没有进行同源映射，则直接使用注释结果
            final_df = pd.merge(final_df_base, result_df, left_on='Source_Gene_ID', right_on='Gene_ID', how='left')
            if 'Gene_ID' in final_df.columns:
                final_df = final_df.drop(columns=['Gene_ID'])

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
    # 修改: 移除 status_callback 参数

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
            logger.error(_("无法在配置中找到基因组 '{}'。").format(assembly_id))
            progress(100, _("任务终止：基因组配置错误。"))
            return None
        gene_id_regex = genome_info.gene_id_regex if hasattr(genome_info, 'gene_id_regex') else None
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
