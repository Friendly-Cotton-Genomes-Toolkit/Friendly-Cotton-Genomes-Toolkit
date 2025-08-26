import os
import re
import threading
import traceback
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Optional, Tuple, Dict, Any, Callable
import logging
import pandas as pd

from cotton_toolkit import GFF3_DB_DIR
from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig, HomologySelectionCriteria
from cotton_toolkit.core.gff_parser import get_genes_in_region, _apply_regex_to_id, get_gene_info_by_ids
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.pipelines.blast import run_blast_pipeline
from cotton_toolkit.utils.config_overrides_utils import _update_config_from_overrides
from cotton_toolkit.utils.gene_utils import resolve_gene_ids, parse_gene_id, _to_transcript_id, _to_gene_id
from cotton_toolkit.core.data_access import get_sequences_for_gene_ids, get_homology_by_gene_ids, \
    resolve_arabidopsis_ids_from_homology_db

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.homology")


def _homology_blast_worker(
        gene_ids_chunk: List[str],
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        criteria: HomologySelectionCriteria,
        cancel_event: Optional[threading.Event]
) -> Optional[pd.DataFrame]:
    """
    每个线程执行的工作单元：为一小批基因提取序列，然后执行BLAST。
    此函数在开始和关键步骤检查中断信号。
    """
    # 检查1: 任务开始时
    if cancel_event and cancel_event.is_set():
        return None

    # 步骤 A: 获取序列
    query_fasta_str, _ = get_sequences_for_gene_ids(config, source_assembly_id, gene_ids_chunk)
    if not query_fasta_str:
        return pd.DataFrame()  # 如果这个区块没有序列，返回空DataFrame以示完成

    # 检查2: 获取序列后，执行BLAST前
    if cancel_event and cancel_event.is_set():
        return None

    # 步骤 B: 执行BLAST
    # run_blast_pipeline 内部也包含了多步中断检查
    return run_blast_pipeline(
        config=config,
        blast_type='blastn',
        target_assembly_id=target_assembly_id,
        query_file_path=None,
        query_text=query_fasta_str,
        output_path=None,  # 在工作线程中不保存文件，只返回DataFrame
        evalue=criteria.evalue_threshold,
        word_size=11,
        max_target_seqs=criteria.top_n,
        cancel_event=cancel_event
    )


@pipeline_task(_("拟南芥基因转换"))
def run_arabidopsis_homology_conversion(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str],
        conversion_direction: str,
        output_path: str,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[Any]:
    """
    智能解析输入ID，并直接输出数据库中所有匹配的原始同源关系，
    确保输出结果的格式与数据库中的记录完全一致。
    """
    progress = kwargs.get('progress_callback', lambda p, m: None)
    check_cancel = kwargs.get('check_cancel', lambda: False)

    progress(0, _("正在准备同源转换..."))
    if check_cancel(): return None

    # 步骤 1: 智能解析输入ID，得到用于查询的、唯一的、标准化的ID列表
    query_ids = []
    if conversion_direction == 'cotton_to_ath':
        try:
            progress(5, _("正在智能解析棉花基因ID..."))
            unique_gene_ids = sorted(list(set(gene_ids)))
            query_ids = resolve_gene_ids(config, assembly_id, unique_gene_ids)
        except (ValueError, FileNotFoundError) as e:
            raise e

    else:  # ath_to_cotton
        try:
            progress(5, _("正在智能解析拟南芥基因ID..."))
            query_ids, _c = resolve_arabidopsis_ids_from_homology_db(config, assembly_id, gene_ids)
        except (ValueError, FileNotFoundError) as e:
            raise e

    if not query_ids:
        raise ValueError(_("解析后输入基因列表为空。"))


    progress(20, _("正在从数据库获取同源关系..."))
    if check_cancel(): return None

    # 步骤 2: 调用数据访问函数，获取所有匹配的原始数据
    result_df = get_homology_by_gene_ids(
        config=config,
        assembly_id=assembly_id,
        gene_ids=query_ids,
        direction=conversion_direction
    )

    if check_cancel(): return None

    # 步骤 3: 直接整理查询结果
    progress(80, _("正在整理转换结果..."))

    if result_df.empty:
        logger.warning(_("在数据库中未找到任何同源基因匹配。"))
        # 根据方向创建带正确表头的空文件
        if conversion_direction == 'cotton_to_ath':
            result_df = pd.DataFrame(columns=['Cotton_ID', 'Arabidopsis_ID', 'Description'])
        else:
            result_df = pd.DataFrame(columns=['Arabidopsis_ID', 'Cotton_ID', 'Description'])
    else:
        logger.info(_("成功从数据库中查询到 {} 条同源匹配项。").format(len(result_df)))
        # 仅重命名列，完全保留数据库的原始数据
        if conversion_direction == 'cotton_to_ath':
            result_df.rename(columns={
                'Query': 'Cotton_ID',
                'Match': 'Arabidopsis_ID',
                'Description': 'Description'
            }, inplace=True)
        else:  # ath_to_cotton
            result_df.rename(columns={
                'Match': 'Arabidopsis_ID',
                'Query': 'Cotton_ID',
                'Description': 'Description'
            }, inplace=True)

    # 步骤 4: 保存到文件或直接输出结果
    if output_path:
        progress(95, _("正在保存结果文件..."))
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            final_message = _("同源基因转换成功！结果已保存至: {}").format(output_path)
            logger.info(final_message)
            progress(100, _("转换完成。"))
            return final_message
        except Exception as e:
            raise IOError(_("保存结果文件时出错: {}").format(e))

    else:
        # 如果没有输出路径，直接返回DataFrame
        progress(100, _("查询完成。"))
        return result_df


@pipeline_task(_("同源基因映射"))
def run_homology_mapping(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: Optional[List[str]],
        region: Optional[Tuple[str, int, int]],
        output_csv_path: Optional[str],
        criteria_overrides: Optional[Dict[str, Any]],
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[pd.DataFrame]:
    """
    通过动态BLAST并行执行同源基因映射，并全程支持中断。
    """

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    try:
        source_gene_ids = gene_ids

        if gene_ids:
            try:
                progress(5, _("正在智能解析输入基因ID..."))
                source_gene_ids = resolve_gene_ids(config, source_assembly_id, gene_ids)
                progress(10, _("ID解析完成，准备执行BLAST。"))
            except (ValueError, FileNotFoundError) as e:
                raise e

        elif region:
            progress(10, _("正在从GFF数据库提取区域基因..."))
            if check_cancel(): return None

            genome_sources = get_genome_data_sources(config)
            source_genome_info = genome_sources.get(source_assembly_id)
            gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')

            gff_db_cache_dir = os.path.join(os.path.dirname(config.config_file_abs_path_), "genomes", "gff3")

            genes_in_region_list = get_genes_in_region(assembly_id=source_assembly_id, gff_filepath=gff_path,
                                                       db_storage_dir=gff_db_cache_dir, region=region)

            if not genes_in_region_list:
                logger.warning(_("在区域 {} 中未找到任何基因。").format(region))
                return pd.DataFrame()

            raw_gene_ids = [gene['id'] for gene in genes_in_region_list]
            logger.debug(_("从GFF区域提取到 {} 个原始基因ID。前5个示例: {}").format(len(raw_gene_ids), raw_gene_ids[:5]))

            logger.info(_("正在使用正则表达式规范化从GFF中提取的基因ID..."))
            id_regex = source_genome_info.gene_id_regex

            # 将规范化后的结果直接赋值给 source_gene_ids
            normalized_ids = [_apply_regex_to_id(gid, id_regex) for gid in raw_gene_ids]
            source_gene_ids = [gid for gid in normalized_ids if gid]

            logger.debug(
                _("规范化后得到 {} 个有效基因ID。前5个示例: {}").format(len(source_gene_ids), source_gene_ids[:5]))

        if not source_gene_ids:
            raise ValueError(_("错误: 基因列表为空。"))


        criteria = HomologySelectionCriteria()
        if criteria_overrides:
            _update_config_from_overrides(criteria, criteria_overrides)

        # --- 多线程执行 (后续代码保持不变) ---
        max_workers = config.downloader.max_workers
        chunk_size = max(1, (len(source_gene_ids) + max_workers - 1) // max_workers)
        gene_chunks = [source_gene_ids[i:i + chunk_size] for i in range(0, len(source_gene_ids), chunk_size)]

        all_results_df = []
        progress(20, _("正在并行启动BLAST任务 (共 {} 个子任务)...").format(len(gene_chunks)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(_homology_blast_worker, chunk, config, source_assembly_id, target_assembly_id, criteria,
                                cancel_event): i
                for i, chunk in enumerate(gene_chunks)
            }

            completed_chunks = 0
            for future in as_completed(future_to_chunk):
                if check_cancel():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return None

                result_df = future.result()
                if result_df is not None and not result_df.empty:
                    all_results_df.append(result_df)

                completed_chunks += 1
                progress(20 + int((completed_chunks / len(gene_chunks)) * 70),
                         _("已完成 {}/{} 个BLAST子任务...").format(completed_chunks, len(gene_chunks)))

        if check_cancel(): return None

        if not all_results_df:
            logger.warning(_("所有BLAST任务完成，但未找到任何匹配项。"))
            return pd.DataFrame()

        results_df = pd.concat(all_results_df, ignore_index=True)
        logger.debug(_("所有线程共返回 {} 条原始匹配。").format(len(results_df)))

        progress(90, _("正在应用筛选条件并整理结果..."))

        if criteria.pid_threshold is not None and 'Identity (%)' in results_df.columns:
            results_df = results_df[
                pd.to_numeric(results_df['Identity (%)'], errors='coerce') >= criteria.pid_threshold]

        if criteria.score_threshold is not None and 'Bit_Score' in results_df.columns:
            results_df = results_df[results_df['Bit_Score'] >= criteria.score_threshold]

        if criteria.strict_subgenome_priority:
            genome_sources = get_genome_data_sources(config)
            source_info = genome_sources.get(source_assembly_id)
            target_info = genome_sources.get(target_assembly_id)
            if source_info and target_info and source_info.is_cotton() and target_info.is_cotton():
                logger.info(_("已启用严格模式：筛选同亚组、同染色体编号的匹配。"))
                results_df['Source_Parsed'] = results_df['Query_ID'].apply(parse_gene_id)
                results_df['Target_Parsed'] = results_df['Hit_ID'].apply(parse_gene_id)
                condition = ((results_df['Source_Parsed'].notna()) & (results_df['Target_Parsed'].notna()) &
                             (results_df['Source_Parsed'].str[0] == results_df['Target_Parsed'].str[0]) &
                             (results_df['Source_Parsed'].str[1] == results_df['Target_Parsed'].str[1]))
                results_df = results_df[condition].drop(columns=['Source_Parsed', 'Target_Parsed'])

        if output_csv_path:
            progress(95, _("正在保存最终结果..."))
            logger.info(_("正在将最终BLAST结果保存到: {}").format(output_csv_path))
            if output_csv_path.lower().endswith('.csv'):
                results_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            else:
                results_df.to_excel(output_csv_path, index=False, engine='openpyxl')

        progress(100, _("同源映射完成。"))
        return results_df

    except Exception as e:
        logger.error(_("同源映射流水线发生意外错误: {}").format(e))
        raise e


@pipeline_task(_("位点转换"))
def run_locus_conversion(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        region: Tuple[str, int, int],
        output_path: str,
        criteria_overrides: Optional[Dict[str, Any]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[str]:
    """
    通过动态BLAST进行位点转换。
    """
    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    try:
        # 步骤 1: 调用新的同源映射流程来找到最佳匹配基因
        # 注意：我们将 output_csv_path 设为 None，以便直接获取DataFrame结果
        progress(0, _("正在通过BLAST进行同源基因映射..."))
        if check_cancel(): return None

        homology_results_df = run_homology_mapping(
            config=config,
            source_assembly_id=source_assembly_id,
            target_assembly_id=target_assembly_id,
            gene_ids=None,  # 明确告知函数从region提取基因
            region=region,
            output_csv_path=None,  # 直接返回DataFrame
            criteria_overrides=criteria_overrides,
            progress_callback=lambda p, m: progress(int(p * 0.8), m),  # 映射进度占80%
            cancel_event=cancel_event
        )

        if check_cancel(): return None
        if homology_results_df is None or homology_results_df.empty:
            logger.warning(_("未能找到任何同源基因，无法进行位点转换。"))
            progress(100, _("任务完成：无同源基因。"))
            # 创建一个空文件以表示任务已执行但无结果
            with open(output_path, 'w', encoding='utf-8-sig') as f:
                f.write(
                    _("# Source Locus: {} | {}:{}-{}\n").format(source_assembly_id, region[0], region[1], region[2]))
                f.write(_("# Target Assembly: {}\n").format(target_assembly_id))
                f.write(_("# No successful homologous matches found to convert locus.\n"))
            return _("在指定区域未找到可转换的同源基因。")

        # 步骤 2: 获取目标基因的坐标信息

        progress(82, _("正在查询源基因的坐标..."))
        if check_cancel(): return None

        source_ids_to_query = homology_results_df['Query_ID'].dropna().unique().tolist()
        logger.info(_("正在为 {} 个唯一的源基因ID查询GFF信息。").format(len(source_ids_to_query)))

        genome_sources = get_genome_data_sources(config)
        source_genome_info = genome_sources.get(source_assembly_id)
        source_gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        gff_db_dir = os.path.join(os.path.dirname(config.config_file_abs_path_), GFF3_DB_DIR)

        source_gene_info_df = get_gene_info_by_ids(
            assembly_id=source_assembly_id,
            gff_filepath=source_gff_path,
            gene_ids=source_ids_to_query
        )

        if not source_gene_info_df.empty:
            source_gene_info_df['Query_Loci'] = source_gene_info_df.apply(
                lambda row: f"{row['seqid']}:{row['start']}-{row['end']}", axis=1
            )
            homology_results_df = pd.merge(
                homology_results_df,
                source_gene_info_df[['id', 'Query_Loci']],
                left_on='Query_ID',
                right_on='id',
                how='left'
            ).drop(columns=['id'])

        progress(85, _("正在查询目标基因的坐标..."))
        if check_cancel(): return None

        homology_results_df['base_gene_id_for_lookup'] = homology_results_df['Hit_ID'].apply(
            lambda x: re.sub(r'\.\d+$', '', str(x))
        )
        base_gene_ids_to_query = homology_results_df['base_gene_id_for_lookup'].dropna().unique().tolist()
        logger.info(
            _("将 {} 个同源Hit_ID规范化为 {} 个唯一的基础基因ID进行GFF查询。").format(
                len(homology_results_df['Hit_ID'].unique()),
                len(base_gene_ids_to_query)))

        target_genome_info = genome_sources.get(target_assembly_id)
        gff_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')

        target_gene_info_df = get_gene_info_by_ids(
            assembly_id=target_assembly_id,
            gff_filepath=gff_path,
            gene_ids=base_gene_ids_to_query
        )

        if target_gene_info_df.empty:
            logger.warning(_("找到了同源基因ID，但无法在目标GFF中查询到它们的坐标信息。"))
            final_df = homology_results_df
        else:

            target_gene_info_df['Hit_Loci'] = target_gene_info_df.apply(
                lambda row: f"{row['seqid']}:{row['start']}-{row['end']}", axis=1
            )

            # 步骤 3: 合并BLAST结果和目标坐标信息
            progress(95, _("正在合并BLAST结果与坐标信息..."))
            target_gene_info_df = target_gene_info_df.rename(columns={'id': 'base_gene_id_for_lookup'})
            final_df = pd.merge(homology_results_df, target_gene_info_df, on='base_gene_id_for_lookup', how='left')
            final_df = final_df.drop(columns=['base_gene_id_for_lookup'])

        # 步骤 4: 保存最终结果
        cols = final_df.columns.tolist()
        if 'Query_Loci' in cols:
            cols.remove('Query_Loci')
            if 'Query_ID' in cols:
                query_id_index = cols.index('Query_ID')
                cols.insert(query_id_index + 1, 'Query_Loci')

        if 'Hit_Loci' in cols:
            cols.remove('Hit_Loci')
            if 'Hit_ID' in cols:
                hit_id_index = cols.index('Hit_ID')
                cols.insert(hit_id_index + 1, 'Hit_Loci')

        final_df = final_df[cols]

        # 步骤 5: 保存最终结果
        logger.info(_("正在将位点转换结果保存到: {}").format(output_path))
        final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        progress(100, _("位点转换完成！"))
        success_message = _("位点转换结果已成功保存到:\n{}").format(os.path.abspath(output_path))
        logger.info(success_message)
        return success_message

    except Exception as e:
        logger.error(_("位点转换流程出错: {}").format(e))
        logger.debug(traceback.format_exc())
        progress(100, _("任务因错误而终止。"))
        raise e
