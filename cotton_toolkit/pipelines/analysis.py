import os
import threading
import time
import traceback
from typing import Optional, List, Tuple, Dict, Any, Callable

import pandas as pd
import logging
from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig, HomologySelectionCriteria
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv
from cotton_toolkit.core.gff_parser import get_genes_in_region, _apply_regex_to_id, get_gene_info_by_ids
from cotton_toolkit.core.homology_mapper import map_genes_via_bridge, save_mapping_results
from cotton_toolkit.tools.annotator import Annotator
from cotton_toolkit.tools.batch_ai_processor import process_single_csv_file
from cotton_toolkit.tools.data_loader import create_homology_df
from cotton_toolkit.tools.enrichment_analyzer import run_go_enrichment, run_kegg_enrichment
from cotton_toolkit.tools.visualizer import plot_enrichment_bubble, plot_enrichment_bar, plot_enrichment_upset, \
    plot_enrichment_cnet, _generate_r_script_and_data
from cotton_toolkit.utils.config_overrides_utils import _update_config_from_overrides
from cotton_toolkit.utils.gene_utils import map_transcripts_to_genes


# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipeline.analysis")


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

            source_to_bridge_homology_df = create_homology_df(config=config,file_path=s_to_b_homology_file,
                                                              progress_callback=lambda p, m: progress(30 + int(p * 0.3), m),  cancel_event=cancel_event)
            if check_cancel() or source_to_bridge_homology_df.empty: logger.info(
                _("任务被取消或文件读取失败。")); return None

            bridge_to_target_homology_df = create_homology_df(config=config,file_path=b_to_t_homology_file,
                                                              progress_callback=lambda p, m: progress(60 + int(p * 0.2), m),  cancel_event=cancel_event)
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
    """
    执行物种间的基因组位点转换。

    该流程首先从源基因组的指定区域查找基因，然后通过桥梁物种（如拟南芥）
    的同源基因信息，将这些基因映射到目标基因组上，并最终输出映射结果。

    此函数依赖于预处理好的GFF数据库和同源数据库以保证最佳性能。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            logger.info(_("任务已取消。"))
            return True
        return False

    try:
        progress(5, _("流程开始，正在加载基因组配置..."))
        if check_cancel(): return None

        # --- 步骤 1: 加载所有必需的基因组配置 ---
        logger.info(_("步骤1: 加载配置..."))
        genome_sources = get_genome_data_sources(config)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)
        bridge_species_name = "Arabidopsis thaliana"  # 假设桥梁物种固定
        bridge_genome_info = genome_sources.get(bridge_species_name)
        if not bridge_genome_info:
            bridge_genome_info = genome_sources.get(bridge_species_name.replace(' ', '_'))

        if not all([source_genome_info, target_genome_info, bridge_genome_info]):
            error_msg = _("错误: 无法为 {}, {} 或 {} 找到配置。").format(source_assembly_id, target_assembly_id,
                                                                        bridge_species_name)
            logger.error(error_msg)
            progress(100, _("任务终止：基因组配置错误。"))
            return None

        # --- 步骤 2: 从GFF数据库中提取源基因 ---
        progress(15, _("正在从GFF数据库中提取基因..."))
        if check_cancel(): return None

        gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        gff_db_cache_dir = config.locus_conversion.gff_db_storage_dir

        # 直接调用 get_genes_in_region，不再手动检查DB文件是否存在
        # gff_parser 会在找不到预处理DB时抛出 FileNotFoundError
        source_gene_list = get_genes_in_region(
            assembly_id=source_assembly_id,
            gff_filepath=gff_path,
            db_storage_dir=gff_db_cache_dir,
            region=region,
            gene_id_regex=source_genome_info.gene_id_regex,
            force_db_creation=False,  # 关键：设置为False，强制使用预处理数据库
            progress_callback=lambda p, m: progress(15 + int(p * 0.1), _("提取基因: {}").format(m))
        )

        if not source_gene_list:
            message = _("在指定区域 {} 未找到任何基因。").format(region)
            logger.warning(message)
            progress(100, _("任务终止：区域内无基因。"))
            return message
        source_gene_ids = [gene['gene_id'] for gene in source_gene_list]

        logger.debug(f"从GFF区域提取到 {len(source_gene_ids)} 个基因。")
        logger.debug(f"GFF提取并标准化后的前5个基因ID: {source_gene_ids[:5]}")

        # --- 步骤 3: 加载同源数据 (已优化为优先使用SQLite) ---
        progress(30, _("正在加载同源文件..."))
        if check_cancel(): return None

        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        source_to_bridge_homology_df = create_homology_df(config,s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(40 + int(p * 0.2),
                                                                                                  _("解析同源文件 (S->B): {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)

        bridge_to_target_homology_df = create_homology_df(config,b_to_t_homology_file,
                                                          progress_callback=lambda p, m: progress(60 + int(p * 0.1),
                                                                                                  _("解析同源文件 (B->T): {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)

        if source_to_bridge_homology_df.empty or bridge_to_target_homology_df.empty:
            logger.error(_("错误: 必要的同源数据未能加载。"))
            return None

        logger.debug(f"加载了 '源->桥梁' 同源数据，共 {len(source_to_bridge_homology_df)} 行。")
        logger.debug(f"S2B同源文件'Query'列的前5个原始ID: {source_to_bridge_homology_df['Query'].head().tolist()}")
        logger.debug(f"加载了 '桥梁->目标' 同源数据，共 {len(bridge_to_target_homology_df)} 行。")

        # --- 步骤 4: 执行核心同源映射 ---
        progress(75, _("正在执行核心同源映射..."))
        if check_cancel(): return None

        # 这里的参数可以根据需要从config或criteria_overrides中获取
        s2b_criteria = HomologySelectionCriteria()
        b2t_criteria = HomologySelectionCriteria()
        if criteria_overrides:
            _update_config_from_overrides(s2b_criteria, criteria_overrides)
            _update_config_from_overrides(b2t_criteria, criteria_overrides)

        logger.debug(f"将使用以下筛选标准 (S->B): {s2b_criteria.model_dump()}")
        logger.debug(f"将使用以下筛选标准 (B->T): {b2t_criteria.model_dump()}")

        homology_columns = {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"}


        progress(75, _("正在执行核心同源映射..."))
        if check_cancel(): logger.info(_("任务已取消。")); return None

        mapped_df, failed_genes = map_genes_via_bridge(
            source_gene_ids=source_gene_ids,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=bridge_species_name,
            homology_columns=homology_columns,
            source_to_bridge_homology_df=source_to_bridge_homology_df,
            bridge_to_target_homology_df=bridge_to_target_homology_df,
            selection_criteria_s_to_b=s2b_criteria.model_dump(),  # 使用修复后的标准
            selection_criteria_b_to_t=b2t_criteria.model_dump(),  # 使用修复后的标准
            source_genome_info=source_genome_info,
            target_genome_info=target_genome_info,
            bridge_genome_info=bridge_genome_info,
            progress_callback=lambda p, m: progress(75 + int(p * 0.15), _("基因映射: {}").format(m)),
            cancel_event=cancel_event
        )

        if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
            logger.info(_("任务在同源映射阶段被用户取消。"))
            progress(100, _("任务已取消。"))
            return None

        progress(95, _("映射完成，正在整理并保存结果..."))
        if check_cancel(): return None

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

    except FileNotFoundError as e:
        logger.error(str(e))
        progress(100, _("任务终止：缺少必要的预处理数据库。"))
        return None

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
            logger.error(f"错误: 基因组 '{assembly_id}' 未在基因组源列表中找到。")
            progress(100, "任务终止：基因组配置错误。")
            return False

        gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')
        if not gff_file_path or not os.path.exists(gff_file_path):
            logger.error(f"错误: 未找到基因组 '{assembly_id}' 的GFF文件。请先下载数据。")
            progress(100, "任务终止：GFF文件缺失。")
            return False

        gff_db_dir = os.path.join(project_root, config.locus_conversion.gff_db_storage_dir)
        expected_db_path = os.path.join(gff_db_dir, os.path.basename(gff_file_path) + ".db")

        # 2. 检查预处理的数据库是否存在，不存在则报错
        if not os.path.exists(expected_db_path):
            logger.error(f"错误: 未找到预处理的GFF数据库 '{expected_db_path}'。")
            logger.error("请先运行GFF预处理流程来创建数据库，以加速查询。")
            progress(100, "任务终止：GFF数据库缺失。")
            return False

        # 3. 确认不再强制创建数据库 (force_creation = False)
        force_creation = False

    except Exception as e:
        logger.error(f"在准备GFF查询时发生错误: {e}")
        return False

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

        source_to_bridge_homology_df = create_homology_df(config,s_to_b_homology_file,
                                                          progress_callback=lambda p, m: progress(25 + int(p * 0.1),
                                                                                                  _("加载同源数据: {}").format(
                                                                                                      m)),
                                                          cancel_event=cancel_event)
        if check_cancel() or source_to_bridge_homology_df.empty: logger.info(_("任务被取消或文件读取失败。")); return

        progress(35, _("正在解析桥梁到目标的同源文件..."))
        if check_cancel(): return

        bridge_to_target_homology_df = create_homology_df(config,b_to_t_homology_file,
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
            logger.error(_("无法在配置中找到基因组 '{}'。").format(assembly_id))
            progress(100, _("任务终止：基因组配置错误。"));
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
