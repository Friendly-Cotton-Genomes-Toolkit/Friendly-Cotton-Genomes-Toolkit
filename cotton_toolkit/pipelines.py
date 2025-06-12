# cotton_toolkit/pipelines.py (Continuation from previous response)
import logging
import os
import time
from dataclasses import asdict
from typing import List, Dict, Any, Optional, Callable, Tuple
from urllib.parse import urlparse

import pandas as pd

from cotton_toolkit.config.models import MainConfig, DownloaderConfig
from .core.gff_parser import get_genes_in_region

# --- 国际化和日志设置 ---
# 假设 _ 函数已由主应用程序入口设置到 builtins
# 为了让静态检查工具识别 _，可以这样做：
try:
    import builtins  #

    _ = builtins._  # type: ignore #
except (AttributeError, ImportError):  # builtins._ 未设置或导入builtins失败 #
    # 如果在测试或独立运行此模块时，_ 可能未设置
    def _(text: str) -> str:  #
        return text  #

# --- 从实际的包核心模块导入功能 ---
try:
    # 导入 gff_parser 中的函数
    from cotton_toolkit.core.gff_parser import get_genes_in_region, get_gene_info_by_ids, \
        extract_gene_details  # <-- 确保这一行存在且正确
    # 导入 homology_mapper 中的函数
    from cotton_toolkit.core.homology_mapper import load_and_map_homology, select_best_homologs, map_genes_via_bridge
    # 导入 loader 中的函数，用于获取基因组源数据
    from cotton_toolkit.config.loader import get_genome_data_sources, \
        get_local_downloaded_file_path  # Ensure get_local_downloaded_file_path is imported
    # 导入 downloader 中的函数，用于下载 GFF 和同源文件
    from cotton_toolkit.core.downloader import download_file
    from cotton_toolkit.config.models import MainConfig, IntegrationPipelineConfig, LocusConversionConfig, \
        GenomeSourceItem  # 导入相关 Config 类

    CORE_MODULES_IMPORTED = True  #
    print("INFO (pipelines.py): Successfully imported core modules.")  #
except ImportError as e:
    CORE_MODULES_IMPORTED = False  #
    print(
        f"WARNING (pipelines.py): Could not import core modules: {e}. Using MOCK functions for integrate_bsa_with_hvg.")  #
    # --- MOCK 函数定义 (仅当真实导入失败时，用于独立测试此文件的流程) ---
    DB_SUFFIX = ".mock.gffutils.db"  #


    class MockGFFFeature:  #
        def __init__(self, id: str, chrom: str, start: int, end: int, strand: str,
                     attributes: Optional[Dict[str, Any]] = None):  #
            self.id = id  #
            self.chrom = chrom  #
            self.start = start  #
            self.end = end  #
            self.strand = strand  #
            self.attributes = attributes if attributes else {}  #


    class MockGFFDB:  #
        def __init__(self, db_path: str): self.db_path = db_path; self.genes: Dict[str, MockGFFFeature] = {}  #

        def add_gene(self, gene: MockGFFFeature): self.genes[gene.id] = gene  #

        def __getitem__(self, key: str) -> Optional[MockGFFFeature]: return self.genes.get(key)  #

        def region(self, seqid: str, start: int, end: int, featuretype: Optional[str] = None,
                   strand: Optional[str] = None) -> List[MockGFFFeature]:  #
            # print(f"MOCK_GFFDB: Querying region {seqid}:{start}-{end} for {featuretype}")
            return [g for g in self.genes.values() if
                    g.chrom == seqid and featuretype == 'gene' and max(start, g.start) < min(end, g.end)]  #


    def create_or_load_gff_db(gff_file_path: str, db_path: Optional[str] = None, force_create: bool = False,
                              verbose: bool = True, status_callback: Optional[Callable[[str], None]] = None) -> \
            Optional[MockGFFDB]:  # Add status_callback
        if verbose: print(f"MOCK: create_or_load_gff_db for GFF '{gff_file_path}' -> DB '{db_path}'")  #
        if not os.path.exists(gff_file_path):  #
            if verbose: print(f"MOCK Error: GFF file {gff_file_path} not found for DB creation.")  #
            return None  #
        actual_db_path = db_path if db_path else gff_file_path + DB_SUFFIX  #
        mock_db = MockGFFDB(actual_db_path)  # 重要的是返回一个有region方法的对象 #
        # 模拟从GFF文件读取内容 (简化版)
        try:
            with open(gff_file_path, 'r', encoding='utf-8') as f_gff:  #
                for line in f_gff:  #
                    if line.startswith("#") or line.strip() == "": continue  #
                    parts = line.strip().split('\t')  #
                    if len(parts) >= 9 and parts[2].lower() == 'gene':  #
                        attrs = {kv.split('=', 1)[0]: kv.split('=', 1)[1] for kv in parts[8].split(';') if '=' in kv}  #
                        if "ID" in attrs: mock_db.add_gene(  #
                            MockGFFFeature(attrs["ID"], parts[0], int(parts[3]), int(parts[4]), parts[6], attrs))  #
        except Exception as e_mock_gff:  #
            if verbose: print(f"MOCK GFF Read Error: {e_mock_gff}")  #
        return mock_db  #


    def get_features_in_region(db: MockGFFDB, chrom: str, start: int, end: int, feature_type: Optional[str] = None,
                               strand: Optional[str] = None) -> List[MockGFFFeature]:  #
        return db.region(seqid=chrom, start=start, end=end, featuretype=feature_type, strand=strand) if db else []  #

# --- 定义模块级常量 ---
REASONING_COL_NAME = 'Ms1_LoF_Support_Reasoning'  #
MATCH_NOTE_COL_NAME = 'Match_Note'
logger = logging.getLogger("cotton_toolkit.pipelines")


# 将百分比转换为字符串
def _format_progress_msg(percentage: int, message: str) -> str:
    return f"[{percentage}%] {message}"


# --- 新增：位点转换流程函数 ---
def run_locus_conversion_standalone(
        config: MainConfig,  # 传入 MainConfig 对象
        source_assembly_id_override: Optional[str] = None,
        target_assembly_id_override: Optional[str] = None,
        region_override: Optional[Tuple[str, int, int]] = None,  # (chrom, start, end)
        output_csv_path: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(msg)
        else:
            if level.upper() == "ERROR":
                logger.error(msg)
            elif level.upper() == "WARNING":
                logger.warning(msg)
            else:
                logger.info(msg)

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            logger.info(f"[{percent}%] {msg}")

    _log_status(_("开始位点（区域）基因组转换流程..."))
    _log_progress(0, _("准备转换参数..."))

    locus_cfg: LocusConversionConfig = config.locus_conversion
    downloader_cfg: DownloaderConfig = config.downloader  # 获取 DownloaderConfig 实例
    integration_pipeline_cfg = config.integration_pipeline  # 复用同源筛选标准

    # 获取参数，优先使用 override，其次是配置
    source_assembly_id = source_assembly_id_override
    target_assembly_id = target_assembly_id_override
    region = region_override
    final_output_csv_path = output_csv_path

    if not all([source_assembly_id, target_assembly_id, region]):
        _log_status(_("错误: 缺少必要的输入参数（源基因组ID、目标基因组ID、区域）。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # 获取基因组源数据
    genome_sources = get_genome_data_sources(config, logger=_log_status)
    if not genome_sources:
        _log_status(_("错误: 未能加载基因组源数据。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    source_genome_info: GenomeSourceItem = genome_sources.get(source_assembly_id)
    target_genome_info: GenomeSourceItem = genome_sources.get(target_assembly_id)

    if not source_genome_info:
        _log_status(_("错误: 源基因组 '{}' 未在基因组源列表中找到。").format(source_assembly_id), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False
    if not target_genome_info:
        _log_status(_("错误: 目标基因组 '{}' 未在基因组源列表中找到。").format(target_assembly_id), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # 确定位点转换任务的输出目录 (用于保存最终的 CSV 结果)
    locus_conversion_results_dir = locus_cfg.output_dir_name
    os.makedirs(locus_conversion_results_dir, exist_ok=True)

    # GFF 数据库缓存目录
    gff_db_storage_dir = locus_cfg.gff_db_storage_dir
    os.makedirs(gff_db_storage_dir, exist_ok=True)
    force_gff_db_creation = locus_cfg.force_gff_db_creation

    _log_progress(10, _("参数校验与文件路径确定。"))

    # --- 步骤 1: 获取源基因组 GFF 文件并查找区域内的基因 ---
    _log_status(_("正在获取源基因组 '{}' 的 GFF 文件...").format(source_assembly_id))

    # 首先尝试从主下载目录查找 GFF 文件
    source_gff_local_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')

    # 如果文件不存在于主下载目录，则下载它
    if not source_gff_local_path or not os.path.exists(source_gff_local_path):
        _log_status(f"INFO: {_('源基因组 GFF 文件未在预期位置找到，将尝试下载。')}")
        source_gff_url = source_genome_info.gff3_url
        # 下载到主下载目录，确保后续可重用
        expected_download_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
        if not expected_download_path:  # Fallback if path couldn't be determined for some reason
            expected_download_path = os.path.join(locus_conversion_results_dir,
                                                  os.path.basename(urlparse(source_gff_url).path).split('?')[0])

        if not download_file(source_gff_url, expected_download_path, downloader_cfg.force_download,
                             task_desc=f"{source_assembly_id} GFF", proxies=downloader_cfg.proxies.to_dict()):
            _log_status(_("错误: 无法下载源基因组 '{}' 的 GFF 文件。").format(source_assembly_id), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False
        source_gff_local_path = expected_download_path  # 更新为实际下载的路径
    else:
        _log_status(f"INFO: {_('源基因组 GFF 文件已存在于:')} {source_gff_local_path} {_('将直接使用。')}")

    _log_progress(20, _("源基因组 GFF 文件准备完成。"))

    _log_status(_("正在源基因组 '{}' 的区域 '{}:{}-{}' 中查找基因...").format(source_assembly_id, region[0], region[1],
                                                                              region[2]))
    source_genes_in_region = get_genes_in_region(
        assembly_id=source_assembly_id,
        gff_filepath=source_gff_local_path,
        db_storage_dir=gff_db_storage_dir,
        region=region,
        force_db_creation=force_gff_db_creation,
        status_callback=_log_status
    )
    if not source_genes_in_region:
        _log_status(_("警告: 在源基因组 '{}' 的指定区域中未找到基因。").format(source_assembly_id), "WARNING")
        if task_done_callback: task_done_callback(True)
        return True

    _log_status(_("在源区域找到 {} 个基因。").format(len(source_genes_in_region)))
    source_gene_ids = [g['gene_id'] for g in source_genes_in_region]
    _log_progress(40, _("源区域基因查找完成。"))

    # --- 步骤 2: 获取同源映射文件并进行同源映射 ---
    _log_status(
        _("正在获取源基因组 '{}' 到目标基因组 '{}' 的同源映射文件...").format(source_assembly_id, target_assembly_id))

    # 尝试从主下载目录查找 S2B 同源文件
    # 获取源基因组的信息（用于 homology_ath_url 和 slicer）
    source_genome_info_for_homology: GenomeSourceItem = genome_sources.get(source_assembly_id)
    if not source_genome_info_for_homology:
        _log_status(_("错误: 无法获取源基因组 '{}' 的详细信息，无法确定同源文件URL。").format(source_assembly_id),
                    "ERROR")
        if task_done_callback: task_done_callback(False)
        return False
    homology_s2b_url = source_genome_info_for_homology.homology_ath_url

    homology_s2b_local_path = get_local_downloaded_file_path(config, source_genome_info_for_homology, 'homology_ath')

    if not homology_s2b_local_path or not os.path.exists(homology_s2b_local_path):
        _log_status(f"INFO: {_('源到桥梁物种同源映射文件未在预期位置找到，将尝试下载。')}")
        expected_download_path = get_local_downloaded_file_path(config, source_genome_info_for_homology, 'homology_ath')
        if not expected_download_path:
            expected_download_path = os.path.join(locus_conversion_results_dir,
                                                  os.path.basename(urlparse(homology_s2b_url).path).split('?')[0])

        if not download_file(homology_s2b_url, expected_download_path, downloader_cfg.force_download,
                             task_desc=f"{source_assembly_id}-Ath Homology", proxies=downloader_cfg.proxies.to_dict()):
            _log_status(_("错误: 无法下载源到桥梁物种的同源映射文件。"), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False
        homology_s2b_local_path = expected_download_path
    else:
        _log_status(f"INFO: {_('源到桥梁物种同源映射文件已存在于:')} {homology_s2b_local_path} {_('将直接使用。')}")

    _log_progress(50, _("同源映射文件准备完成。"))

    s2b_criteria = integration_pipeline_cfg.selection_criteria_source_to_bridge
    b2t_criteria = integration_pipeline_cfg.selection_criteria_bridge_to_target
    homology_cols = integration_pipeline_cfg.homology_columns

    _log_status(_("正在从源基因组 '{}' 映射基因到桥梁物种（拟南芥）...").format(source_assembly_id))
    slicer_rule_source = source_genome_info_for_homology.homology_id_slicer

    source_to_bridge_homology_map = load_and_map_homology(
        homology_file_path=homology_s2b_local_path,
        homology_columns=homology_cols,
        selection_criteria=asdict(s2b_criteria),
        query_gene_ids=source_gene_ids,
        homology_id_slicer=slicer_rule_source,
        status_callback=_log_status
    )
    if not source_to_bridge_homology_map:
        _log_status(_("警告: 未能找到源基因组到桥梁物种的同源映射。"), "WARNING")
        if task_done_callback: task_done_callback(True)
        return True

    _log_progress(60, _("源基因组到桥梁物种映射完成。"))

    # 获取桥梁物种到目标基因组的同源映射文件 URL
    # 获取目标基因组的信息（用于 homology_ath_url 和 slicer）
    target_genome_info_for_homology: GenomeSourceItem = genome_sources.get(target_assembly_id)
    if not target_genome_info_for_homology:
        _log_status(_("错误: 无法获取目标基因组 '{}' 的详细信息，无法确定同源文件URL。").format(target_assembly_id),
                    "ERROR")
        if task_done_callback: task_done_callback(False)
        return False
    homology_b2t_url = target_genome_info_for_homology.homology_ath_url

    # 尝试从主下载目录查找 B2T 同源文件
    homology_b2t_local_path = get_local_downloaded_file_path(config, target_genome_info_for_homology, 'homology_ath')

    if not homology_b2t_local_path or not os.path.exists(homology_b2t_local_path):
        _log_status(f"INFO: {_('桥梁物种到目标基因组同源映射文件未在预期位置找到，将尝试下载。')}")
        expected_download_path = get_local_downloaded_file_path(config, target_genome_info_for_homology, 'homology_ath')
        if not expected_download_path:
            expected_download_path = os.path.join(locus_conversion_results_dir,
                                                  os.path.basename(urlparse(homology_b2t_url).path).split('?')[0])

        if not download_file(homology_b2t_url, expected_download_path, downloader_cfg.force_download,
                             task_desc=f"Ath-{target_assembly_id} Homology", proxies=downloader_cfg.proxies.to_dict()):
            _log_status(_("错误: 无法下载桥梁物种到目标基因组的同源映射文件。"), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False
    else:
        _log_status(
            f"INFO: {_('桥梁物种到目标基因组同源映射文件已存在于:')} {homology_b2t_local_path} {_('将直接使用。')}")

    _log_progress(70, _("桥梁物种到目标基因组同源映射文件准备完成。"))

    bridge_gene_ids = set()
    for s_id, matches in source_to_bridge_homology_map.items():
        for match in matches:
            bridge_gene_ids.add(match[homology_cols['match']])

    _log_status(_("正在从桥梁物种映射基因到目标基因组 '{}'...").format(target_assembly_id))
    slicer_rule_target = target_genome_info_for_homology.homology_id_slicer

    bridge_to_target_homology_map = load_and_map_homology(
        homology_file_path=homology_b2t_local_path,
        homology_columns=homology_cols,
        selection_criteria=asdict(b2t_criteria),
        query_gene_ids=list(bridge_gene_ids),
        homology_id_slicer=slicer_rule_target,
        status_callback=_log_status
    )
    if not bridge_to_target_homology_map:
        _log_status(_("警告: 未能找到桥梁物种到目标基因组的同源映射。"), "WARNING")
        if task_done_callback: task_done_callback(True)
        return True
    _log_progress(80, _("桥梁物种到目标基因组映射完成。"))

    # --- 步骤 3: 获取目标基因在目标基因组中的位置 ---
    _log_status(_("正在获取目标基因组 '{}' 的 GFF 文件...").format(target_assembly_id))

    # 尝试从主下载目录查找目标 GFF 文件
    target_gff_local_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')

    if not target_gff_local_path or not os.path.exists(target_gff_local_path):
        _log_status(f"INFO: {_('目标基因组 GFF 文件未在预期位置找到，将尝试下载。')}")
        target_gff_url = target_genome_info.gff3_url
        expected_download_path = get_local_downloaded_file_path(config, target_genome_info, 'gff3')
        if not expected_download_path:
            expected_download_path = os.path.join(locus_conversion_results_dir,
                                                  os.path.basename(urlparse(target_gff_url).path).split('?')[0])

        if not download_file(target_gff_url, expected_download_path, downloader_cfg.force_download,
                             task_desc=f"{target_assembly_id} GFF", proxies=downloader_cfg.proxies.to_dict()):
            _log_status(_("错误: 无法下载目标基因组 '{}' 的 GFF 文件。").format(target_assembly_id), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False
    else:
        _log_status(f"INFO: {_('目标基因组 GFF 文件已存在于:')} {target_gff_local_path} {_('将直接使用。')}")

    _log_progress(90, _("目标基因组 GFF 文件准备完成。"))

    all_target_gene_ids = set()
    for b_id, b_matches in bridge_to_target_homology_map.items():
        for b_match in b_matches:
            all_target_gene_ids.add(b_match[homology_cols['match']])

    _log_status(_("正在目标基因组 '{}' 中查询映射到的基因位置信息...").format(target_assembly_id))
    target_gene_info_map = get_gene_info_by_ids(
        assembly_id=target_assembly_id,
        gff_filepath=target_gff_local_path,
        db_storage_dir=gff_db_storage_dir,
        gene_ids=list(all_target_gene_ids),
        force_db_creation=force_gff_db_creation,
        status_callback=_log_status
    )
    if not target_gene_info_map:
        _log_status(_("警告: 未能在目标基因组中找到任何映射到的基因的位置信息。"), "WARNING")
        if task_done_callback: task_done_callback(True)
        return True
    _log_progress(95, _("目标基因位置查询完成。"))

    # --- 步骤 4: 整合所有信息并生成最终输出 (与 integrate_bsa_with_hvg 类似，但更简单) ---
    _log_status(_("整合转换结果..."))
    final_results = []
    for source_gene_id in source_gene_ids:
        # 获取源基因在源区域的信息
        source_gene_details_in_region = next((g for g in source_genes_in_region if g['gene_id'] == source_gene_id),
                                             None)

        # 从源到桥梁的映射
        s_to_b_matches = source_to_bridge_homology_map.get(source_gene_id, [])

        if not s_to_b_matches:
            final_results.append({
                "Source_Gene_ID": source_gene_id,
                "Source_Assembly": source_assembly_id,
                "Source_Chr": source_gene_details_in_region['seqid'] if source_gene_details_in_region else None,
                "Source_Start": source_gene_details_in_region['start'] if source_gene_details_in_region else None,
                "Source_End": source_gene_details_in_region['end'] if source_gene_details_in_region else None,
                "Target_Gene_ID": None,
                "Target_Assembly": target_assembly_id,
                "Target_Chr": None,
                "Target_Start": None,
                "Target_End": None,
                "Bridge_Gene_ID": None,
                "Match_Note": _("无源到桥梁映射")
            })
            continue

        for s_to_b_match in s_to_b_matches:
            bridge_gene_id = s_to_b_match[homology_cols['match']]
            s_to_b_evalue = s_to_b_match[homology_cols['evalue']]
            s_to_b_score = s_to_b_match[homology_cols['score']]
            s_to_b_pid = s_to_b_match[homology_cols['pid']]

            # 从桥梁到目标的映射
            b_to_t_matches = bridge_to_target_homology_map.get(bridge_gene_id, [])

            if not b_to_t_matches:
                final_results.append({
                    "Source_Gene_ID": source_gene_id,
                    "Source_Assembly": source_assembly_id,
                    "Source_Chr": source_gene_details_in_region['seqid'] if source_gene_details_in_region else None,
                    "Source_Start": source_gene_details_in_region['start'] if source_gene_details_in_region else None,
                    "Source_End": source_gene_details_in_region['end'] if source_gene_details_in_region else None,
                    "Target_Gene_ID": None,
                    "Target_Assembly": target_assembly_id,
                    "Target_Chr": None,
                    "Target_Start": None,
                    "Target_End": None,
                    "Bridge_Gene_ID": bridge_gene_id,
                    f"S_to_B_{homology_cols['score']}": s_to_b_score,
                    f"S_to_B_{homology_cols['evalue']}": s_to_b_evalue,
                    f"S_to_B_{homology_cols['pid']}": s_to_b_pid,
                    "Match_Note": _("无桥梁到目标映射")
                })
                continue

            for b_to_t_match in b_to_t_matches:
                target_gene_id = b_to_t_match[homology_cols['match']]
                b_to_t_evalue = b_to_t_match[homology_cols['evalue']]
                b_to_t_score = b_to_t_match[homology_cols['score']]
                b_to_t_pid = b_to_t_match[homology_cols['pid']]

                # 获取目标基因的GFF信息
                target_gene_details = target_gene_info_map.get(target_gene_id)

                row_data = {
                    "Source_Gene_ID": source_gene_id,
                    "Source_Assembly": source_assembly_id,
                    "Source_Chr": source_gene_details_in_region['seqid'] if source_gene_details_in_region else None,
                    "Source_Start": source_gene_details_in_region['start'] if source_gene_details_in_region else None,
                    "Source_End": source_gene_details_in_region['end'] if source_gene_details_in_region else None,
                    "Target_Gene_ID": target_gene_id,
                    "Target_Assembly": target_assembly_id,
                    "Target_Chr": target_gene_details['seqid'] if target_gene_details else None,
                    "Target_Start": target_gene_details['start'] if target_gene_details else None,
                    "Target_End": target_gene_details['end'] if target_gene_details else None,
                    "Bridge_Gene_ID": bridge_gene_id,
                    f"S_to_B_{homology_cols['score']}": s_to_b_score,
                    f"S_to_B_{homology_cols['evalue']}": s_to_b_evalue,
                    f"S_to_B_{homology_cols['pid']}": s_to_b_pid,
                    f"B_to_T_{homology_cols['score']}": b_to_t_score,
                    f"B_to_T_{homology_cols['evalue']}": b_to_t_evalue,
                    f"B_to_T_{homology_cols['pid']}": b_to_t_pid,
                    "Match_Note": _("成功映射")
                }
                final_results.append(row_data)

    if not final_results:
        _log_status(_("没有找到任何位点转换的有效结果。"), "WARNING")
        output_df = pd.DataFrame(columns=[
            "Source_Gene_ID", "Source_Assembly", "Source_Chr", "Source_Start", "Source_End",
            "Target_Gene_ID", "Target_Assembly", "Target_Chr", "Target_Start", "Target_End",
            "Bridge_Gene_ID", f"S_to_B_{homology_cols['score']}", f"S_to_B_{homology_cols['evalue']}",
            f"S_to_B_{homology_cols['pid']}", f"B_to_T_{homology_cols['score']}",
            f"B_to_T_{homology_cols['evalue']}", f"B_to_T_{homology_cols['pid']}",
            "Match_Note"
        ])
        overall_success = True
    else:
        output_df = pd.DataFrame(final_results)
        # Add a 1-based index
        output_df.insert(0, 'Result_Index (1-based)', range(1, len(output_df) + 1))
        overall_success = True

    if not final_output_csv_path:
        # Default output path
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_output_csv_path = os.path.join(locus_conversion_results_dir,
                                             f"locus_conversion_result_{source_assembly_id}_to_{target_assembly_id}_{timestamp}.csv")

    try:
        output_df.to_csv(final_output_csv_path, index=False, encoding='utf-8-sig')
        _log_status(_("位点转换结果已保存到: {}").format(final_output_csv_path))
    except Exception as e:
        _log_status(_("错误: 保存位点转换结果时发生错误: {}").format(e), "ERROR")
        overall_success = False

    _log_progress(100, _("位点转换流程结束。"))
    if task_done_callback: task_done_callback(overall_success)
    return overall_success


# 独立同源映射功能
def run_homology_map_standalone(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: Optional[List[str]] = None,
        region: Optional[Tuple[str, int, int]] = None,
        output_csv_path: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = print,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    """
    【统一后端函数】执行同源映射或位点转换。
    如果提供了 gene_ids，则对基因列表进行映射。
    如果提供了 region，则先从区域提取基因，再进行映射。
    """
    runner_log = status_callback
    runner_progress = progress_callback
    pipeline_cfg = config.integration_pipeline
    downloader_cfg = config.downloader
    was_successful = False  # 用于记录任务最终是否成功

    runner_log("开始执行映射/转换流程...")
    runner_progress(0, "初始化...")

    # --- 1. 确定源基因列表 ---
    genes_to_map = []
    if gene_ids:
        genes_to_map = gene_ids
        runner_log(f"接收到 {len(genes_to_map)} 个基因ID进行处理。")
    elif region:
        try:
            runner_log(f"根据区域 {region} 查找源基因...")
            genome_sources = get_genome_data_sources(config, logger=runner_log)
            source_genome_info = genome_sources.get(source_assembly_id)
            if not source_genome_info:
                raise FileNotFoundError(f"未在基因组源列表中找到源基因组 '{source_assembly_id}'。")

            gff_path = get_local_downloaded_file_path(config, source_genome_info, 'gff3')
            if not gff_path or not os.path.exists(gff_path):
                raise FileNotFoundError(f"源基因组 '{source_assembly_id}' 的GFF文件未找到或未下载。")

            runner_progress(10, "正在从GFF区域提取基因...")
            genes_in_region_list = get_genes_in_region(
                assembly_id=source_assembly_id,
                gff_filepath=gff_path,
                db_storage_dir=pipeline_cfg.gff_db_storage_dir,
                region=region,
                force_db_creation=pipeline_cfg.force_gff_db_creation,
                status_callback=runner_log
            )
            if not genes_in_region_list:
                runner_log(f"警告: 在区域 {region} 中未找到任何基因，流程正常结束。", "WARNING")
                was_successful = True
                if output_csv_path:
                    pd.DataFrame().to_csv(output_csv_path, index=False)
                return True

            genes_to_map = [g['gene_id'] for g in genes_in_region_list]
            runner_log(f"从区域中提取到 {len(genes_to_map)} 个基因。")

        except Exception as e:
            runner_log(f"从区域提取基因时发生错误: {e}", "ERROR")
            return False
    else:
        runner_log("错误: 必须提供基因ID列表或基因组区域之一。", "ERROR")
        return False

    runner_progress(30, "源基因列表准备完毕。")

    # --- 2. 执行同源映射 ---
    try:
        runner_log("正在执行同源映射...")
        genome_sources = get_genome_data_sources(config, logger=runner_log)
        source_genome_info = genome_sources.get(source_assembly_id)
        target_genome_info = genome_sources.get(target_assembly_id)

        s_to_b_homology_file = get_local_downloaded_file_path(config, source_genome_info, 'homology_ath')
        b_to_t_homology_file = get_local_downloaded_file_path(config, target_genome_info, 'homology_ath')

        if not all([s_to_b_homology_file, b_to_t_homology_file, os.path.exists(s_to_b_homology_file),
                    os.path.exists(b_to_t_homology_file)]):
            raise FileNotFoundError("缺少必要的同源文件，请先在'数据下载'页面下载。")

        s_to_b_df = pd.read_csv(s_to_b_homology_file)
        b_to_t_df = pd.read_csv(b_to_t_homology_file)

        runner_progress(50, "同源文件加载完毕，开始映射...")

        mapped_df, fuzzy_count = map_genes_via_bridge(
            source_gene_ids=genes_to_map,
            source_assembly_name=source_assembly_id,
            target_assembly_name=target_assembly_id,
            bridge_species_name=pipeline_cfg.bridge_species_name,
            source_to_bridge_homology_df=s_to_b_df,
            bridge_to_target_homology_df=b_to_t_df,
            s_to_b_query_col=pipeline_cfg.homology_columns.query,
            s_to_b_match_col=pipeline_cfg.homology_columns.match,
            b_to_t_query_col=pipeline_cfg.homology_columns.query,
            b_to_t_match_col=pipeline_cfg.homology_columns.match,
            evalue_col=pipeline_cfg.homology_columns.evalue,
            score_col=pipeline_cfg.homology_columns.score,
            pid_col=pipeline_cfg.homology_columns.pid,
            selection_criteria_s_to_b=asdict(pipeline_cfg.selection_criteria_source_to_bridge),
            selection_criteria_b_to_t=asdict(pipeline_cfg.selection_criteria_bridge_to_target),
        )
        if fuzzy_count > 0:
            runner_log(f"注意: 在同源映射中执行了 {fuzzy_count} 次模糊匹配。", "WARNING")

        runner_progress(90, "映射完成，正在保存结果...")

        # --- 3. 保存结果 ---
        final_output_path = output_csv_path
        if not final_output_path:
            output_dir = os.path.join(downloader_cfg.download_output_base_dir, "homology_map_results")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            final_output_path = os.path.join(output_dir,
                                             f"map_result_{source_assembly_id}_to_{target_assembly_id}_{timestamp}.csv")

        mapped_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
        runner_log(f"流程成功完成，结果已保存至: {final_output_path}")
        was_successful = True

    except Exception as e:
        runner_log(f"执行映射/转换时发生严重错误: {e}", "ERROR")
        logger.exception("完整错误堆栈:")
        was_successful = False

    finally:
        if task_done_callback:
            task_done_callback(was_successful)

    return was_successful


# 新增：独立GFF基因查询功能
def run_gff_gene_lookup_standalone(
        config: MainConfig,  # Changed to MainConfig type hint
        assembly_id_override: Optional[str] = None,
        gene_ids_override: Optional[List[str]] = None,
        region_override: Optional[Tuple[str, int, int]] = None,  # (chrom, start, end)
        output_csv_path: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    """
    独立运行GFF基因位点查询流程。
    可以根据基因ID列表或染色体区域进行查询。
    """

    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(f"[{level}] {msg}")
        elif level == "ERROR":
            print(f"ERROR: {msg}")
        elif level == "WARNING":
            print(f"WARNING: {msg}")
        else:
            print(f"INFO: {msg}")

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            print(f"PROGRESS [{percent}%]: {msg}")

    overall_success = False  # This will now be set at the end of successful operations
    _log_status(_("开始独立GFF基因查询流程..."))
    _log_progress(0, _("初始化配置..."))

    if not CORE_MODULES_IMPORTED:
        _log_status(_("错误: 核心模块未加载，无法执行GFF查询。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False

    pipeline_cfg: IntegrationPipelineConfig = config.integration_pipeline
    downloader_cfg: DownloaderConfig = config.downloader

    assembly_id = assembly_id_override
    # Removed fallback to bsa_assembly_id or hvg_assembly_id from config
    # as GUI/CLI should provide the explicit assembly_id.

    if not assembly_id:
        _log_status(_("错误: 必须指定基因组版本ID用于GFF查询。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False

    genome_sources = get_genome_data_sources(config, logger=_log_status)
    if not genome_sources:
        _log_status(_("错误: 未能加载基因组源数据。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    selected_genome_info: Optional[GenomeSourceItem] = genome_sources.get(assembly_id)
    if not selected_genome_info:
        _log_status(_("错误: 基因组 '{}' 未在基因组源列表中找到，无法查询GFF。").format(assembly_id), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Determine GFF file path (prefer explicit config, then downloaded path)
    gff_file_path = pipeline_cfg.gff_files.get(assembly_id)
    if not gff_file_path:
        gff_file_path = get_local_downloaded_file_path(config, selected_genome_info, 'gff3')

    if not gff_file_path or not os.path.exists(gff_file_path):
        _log_status(
            _("错误: 未找到基因组 '{}' 的GFF文件 '{}'。请检查配置文件或下载。").format(assembly_id,
                                                                                     gff_file_path or "N/A"),
            "ERROR");
        if task_done_callback: task_done_cb(False)
        return False

    gff_db_dir = pipeline_cfg.gff_db_storage_dir
    force_gff_db_creation = pipeline_cfg.force_gff_db_creation

    _log_progress(20, _("加载GFF数据库..."))
    # Use the gff_file_path as part of the DB name to ensure uniqueness
    db_name = os.path.basename(gff_file_path).replace('.gff3.gz', '').replace('.gff3', '') + "_gff.db"
    db_path_to_create = os.path.join(gff_db_dir, db_name)

    gff_db = create_or_load_gff_db(gff_file_path, db_path=db_path_to_create, force_create=force_gff_db_creation,
                                   verbose=True,
                                   status_callback=_log_status)  # Set verbose to True for more gffutils logs
    if not gff_db:
        _log_status(_("错误: 无法加载或创建GFF数据库。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False
    _log_progress(40, _("GFF数据库加载完毕。"))

    results_data = []
    if gene_ids_override:
        _log_status(_("按基因ID查询 {} 个基因...").format(len(gene_ids_override)))
        gene_info_map = get_gene_info_by_ids(
            assembly_id=assembly_id,
            gff_filepath=gff_file_path,  # Not strictly needed if db is loaded, but kept for consistency
            db_storage_dir=gff_db_dir,
            gene_ids=gene_ids_override,
            force_db_creation=force_gff_db_creation,
            status_callback=_log_status  # Pass status callback
        )
        for i, gene_id in enumerate(gene_ids_override):
            gene_details = gene_info_map.get(gene_id)  # Get from the map
            if gene_details:
                results_data.append(gene_details)
            else:
                _log_status(_("警告: 未找到基因ID '{}' 的详细信息。").format(gene_id), "WARNING")
            _log_progress(40 + int((i + 1) / len(gene_ids_override) * 40), _("查询基因ID..."))
    elif region_override:
        chrom, start, end = region_override
        _log_status(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end))

        # Use get_genes_in_region which handles db creation/loading internally based on parameters
        genes_in_region_list = get_genes_in_region(
            assembly_id=assembly_id,
            gff_filepath=gff_file_path,
            db_storage_dir=gff_db_dir,
            region=region_override,
            force_db_creation=force_gff_db_creation,
            status_callback=_log_status  # Pass status callback
        )
        total_genes_in_region = len(genes_in_region_list)
        for i, gene_feature_dict in enumerate(genes_in_region_list):
            # For region query, extract_gene_details from the passed db object
            gene_details = extract_gene_details(gff_db, gene_feature_dict['gene_id'])
            if gene_details:
                results_data.append(gene_details)
            if total_genes_in_region > 0:
                _log_progress(40 + int((i + 1) / total_genes_in_region * 40), _("查询区域基因..."))
            else:
                _log_progress(80, _("查询区域基因..."))  # If no genes, jump to 80% for this step
    else:
        _log_status(_("错误: 必须提供基因ID列表或染色体区域进行查询。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False

    if not results_data:
        _log_status(_("未找到任何符合条件的基因。"), "INFO")
        overall_success = True
    else:
        _log_status(_("查询完成，找到 {} 个基因。").format(len(results_data)))
        _log_progress(90, _("查询完成，正在写入结果。"))

        flat_results = []
        for gene_info in results_data:
            gene_id_val = gene_info.get('gene_id')  # Renamed to avoid conflict
            base_info = {k: v for k, v in gene_info.items() if k != 'transcripts' and k != 'attributes'}
            if 'attributes' in gene_info and isinstance(gene_info['attributes'], dict):
                for attr_k, attr_v in gene_info['attributes'].items():
                    base_info[f"attr_{attr_k}"] = attr_v

            if gene_info.get('transcripts'):
                for transcript in gene_info['transcripts']:
                    trans_info = {f"transcript_{k}": v for k, v in transcript.items() if
                                  k not in ['exons', 'cds', 'attributes']}
                    if 'attributes' in transcript and isinstance(transcript['attributes'], dict):
                        for attr_k, attr_v in transcript['attributes'].items():
                            trans_info[f"transcript_attr_{attr_k}"] = attr_v

                    if transcript.get('exons'):
                        trans_info['exons_coords'] = "; ".join(
                            [f"({e['start']}-{e['end']})" for e in transcript['exons']])
                    if transcript.get('cds'):
                        trans_info['cds_coords'] = "; ".join([f"({c['start']}-{c['end']})" for c in transcript['cds']])
                    flat_results.append({**base_info, **trans_info})
            else:
                flat_results.append(base_info)

        output_df = pd.DataFrame(flat_results)
        cols_order = ['gene_id', 'chr', 'start', 'end', 'strand', 'transcript_id', 'transcript_type', 'exons_coords',
                      'cds_coords']
        existing_cols_order = [col for col in cols_order if col in output_df.columns]
        other_cols = [col for col in output_df.columns if col not in existing_cols_order]
        # Ensure gene_id column from base_info is used if transcript_id is not present (for genes without transcripts in GFF)
        if 'gene_id' not in existing_cols_order and 'gene_id' in output_df.columns:
            existing_cols_order.insert(0, 'gene_id')

        output_df = output_df[existing_cols_order + sorted(other_cols)]

        final_output_path = output_csv_path
        if not final_output_path:
            final_output_dir = os.path.join(downloader_cfg.download_output_base_dir,
                                            "gff_query_results")
            os.makedirs(final_output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if gene_ids_override:
                final_output_path = os.path.join(final_output_dir, f"gff_query_genes_{assembly_id}_{timestamp}.csv")
            elif region_override:
                final_output_path = os.path.join(final_output_dir,
                                                 f"gff_query_region_{assembly_id}_{chrom}_{start}_{end}_{timestamp}.csv")
            else:
                final_output_path = os.path.join(final_output_dir, f"gff_query_results_{assembly_id}_{timestamp}.csv")

        output_df.to_csv(final_output_path, index=False)
        _log_status(_("GFF基因查询结果已保存到: {}").format(final_output_path))
        overall_success = True

    _log_progress(100, _("GFF查询流程结束。"))
    if task_done_callback: task_done_callback(overall_success)
    return overall_success


def run_cotton_to_ath_conversion(
        config: MainConfig,  # Changed to MainConfig type hint
        source_assembly: str,
        gene_ids: List[str],
        status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[Dict[str, str], str]:
    """
    将棉花基因ID列表转换为拟南芥同源基因ID。

    Args:
        config (MainConfig): 主配置对象。
        source_assembly (str): 源棉花基因组的ID (例如, 'NBI_v1.1')。
        gene_ids (List[str]): 需要转换的棉花基因ID列表。
        status_callback (Optional[Callable[[str], None]]): 用于报告状态更新的回调函数。

    Returns:
        Tuple[Dict[str, str], str]: 一个元组，包含 (结果字典, 拟南芥基因组类型字符串)。
    """

    def _log(msg: str):
        if status_callback:
            status_callback(msg)
        else:
            print(msg)

    _log(f"开始从 {source_assembly} 到拟南芥的基因转换...")

    # 1. 从配置中获取基因组来源信息
    genome_sources: Dict[str, GenomeSourceItem] = get_genome_data_sources(config)  # Get as GenomeSourceItem
    if not genome_sources:
        raise ValueError("无法加载基因组来源信息。")

    source_info = genome_sources.get(source_assembly)
    if not source_info:
        raise ValueError(f"在基因组来源文件中未找到 '{source_assembly}' 的配置。")

    homology_type = source_info.homology_type
    homology_url = source_info.homology_ath_url
    if not homology_url:
        raise ValueError(f"基因组 '{source_assembly}' 未配置 'homology_ath_url'。")

    # 2. 确定本地同源文件的路径 (假设已被下载和转换)
    homology_csv_path = get_local_downloaded_file_path(config, source_info, 'homology_ath')

    if not homology_csv_path or not os.path.exists(homology_csv_path):
        raise FileNotFoundError(f"同源文件不存在: {homology_csv_path}。请先通过'数据下载'功能下载并转换该文件。")

    _log(f"使用同源文件: {os.path.basename(homology_csv_path)}")

    # 3. 读取同源文件并进行查找
    homology_df = pd.read_csv(homology_csv_path)
    homology_cols = config.integration_pipeline.homology_columns  # Access as property

    # 获取用于筛选的最佳匹配标准
    sel_criteria = asdict(config.integration_pipeline.selection_criteria_source_to_bridge)  # Convert dataclass to dict

    all_matches = homology_df[homology_df[homology_cols.query].isin(gene_ids)]

    # 使用 select_best_homologs 函数来找到最佳匹配
    best_hits_df = select_best_homologs(
        homology_df=all_matches,
        query_gene_id_col=homology_cols.query,
        match_gene_id_col=homology_cols.match,
        criteria=sel_criteria,
        evalue_col_in_df=homology_cols.evalue,
        score_col_in_df=homology_cols.score,
        pid_col_in_df=homology_cols.pid
    )

    results = {}
    if not best_hits_df.empty:
        # 将结果转换为字典
        results = pd.Series(
            best_hits_df[homology_cols.match].values,
            index=best_hits_df[homology_cols.query]
        ).to_dict()

    # 为未找到匹配的基因添加标记
    for gene_id in gene_ids:
        if gene_id not in results:
            results[gene_id] = "Not Found"

    _log(f"转换完成，处理了 {len(gene_ids)} 个基因ID。")

    return results, homology_type


# --- 主整合函数 ---
def integrate_bsa_with_hvg(
        config: MainConfig,  # Changed to MainConfig type hint
        input_excel_path_override: Optional[str] = None,
        output_sheet_name_override: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    """
    整合BSA定位结果和HVG基因数据，进行候选基因筛选和优先级排序。
    能够处理BSA和HVG数据基于不同或相同基因组版本的情况。
    结果将输出到指定的输入Excel文件的一个新工作表中。

    Args:
        config (MainConfig): 包含所有流程所需参数的配置对象。
            期望结构包含 'integration_pipeline' 和 'downloader' (用于推断路径) 等顶级键。
        input_excel_path_override (Optional[str]): 覆盖配置文件中指定的输入Excel路径。
        output_sheet_name_override (Optional[str]): 覆盖配置文件中指定的输出Sheet名称。
        status_callback (Optional[Callable[[str], None]]): 用于报告状态更新的回调函数。
        progress_callback (Optional[Callable[[int, str], None]]): 用于报告进度的回调函数 (百分比, 消息)。
        task_done_callback (Optional[Callable[[bool], None]]): 任务完成后的回调。

    Returns:
        bool: 如果成功完成并写入结果则返回True，否则返回False。
    """
    global _

    # --- 日志/状态辅助函数 ---
    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(f"[{level}] {msg}")
        elif level == "ERROR":
            print(f"ERROR: {msg}")
        elif level == "WARNING":
            print(f"WARNING: {msg}")
        else:
            print(f"INFO: {msg}")

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            print(f"PROGRESS [{percent}%]: {msg}")

    overall_success = False

    _log_status(_("开始整合分析流程..."))

    _log_progress(0, _("初始化配置..."))

    pipeline_cfg: IntegrationPipelineConfig = config.integration_pipeline
    if not pipeline_cfg:  # Should not happen with MainConfig as type hint
        _log_status(_("错误: 配置中未找到 'integration_pipeline' 部分。"), "ERROR");
        return False

    # --- 参数提取与验证 (补充完整) ---
    input_excel = input_excel_path_override if input_excel_path_override else pipeline_cfg.input_excel_path  # Access as property
    bsa_sheet_name = pipeline_cfg.bsa_sheet_name
    hvg_sheet_name = pipeline_cfg.hvg_sheet_name
    output_sheet_name = output_sheet_name_override if output_sheet_name_override else pipeline_cfg.output_sheet_name

    if not all([input_excel, bsa_sheet_name, hvg_sheet_name, output_sheet_name]):
        _log_status(_("错误: 输入/输出Excel或Sheet名称配置不完整。"), "ERROR");
        return False

    _log_status(f"  Input Excel: {input_excel}")
    _log_status(f"  BSA Sheet: {bsa_sheet_name}, HVG Sheet: {hvg_sheet_name}, Output Sheet: {output_sheet_name}")

    bsa_assembly_id = pipeline_cfg.bsa_assembly_id
    hvg_assembly_id = pipeline_cfg.hvg_assembly_id
    if not all([bsa_assembly_id, hvg_assembly_id]):
        _log_status(_("错误: 必须在配置中指定 'bsa_assembly_id' 和 'hvg_assembly_id'。"), "ERROR");
        return False
    _log_status(f"  BSA Assembly: {bsa_assembly_id}, HVG Assembly: {hvg_assembly_id}")

    # 获取基因组源数据
    genome_sources: Dict[str, GenomeSourceItem] = get_genome_data_sources(config, logger=_log_status)
    if not genome_sources:
        _log_status(_("错误: 未能加载基因组源数据。"), "ERROR")
        return False

    bsa_genome_info: Optional[GenomeSourceItem] = genome_sources.get(bsa_assembly_id)
    hvg_genome_info: Optional[GenomeSourceItem] = genome_sources.get(hvg_assembly_id)

    if not bsa_genome_info:
        _log_status(_("错误: BSA基因组 '{}' 未在基因组源列表中找到。").format(bsa_assembly_id), "ERROR")
        return False
    if not hvg_genome_info:
        _log_status(_("错误: HVG基因组 '{}' 未在基因组源列表中找到。").format(hvg_assembly_id), "ERROR")
        return False

    # Determine GFF file paths (prefer explicit config, then downloaded path)
    gff_file_path_bsa_assembly = pipeline_cfg.gff_files.get(bsa_assembly_id)
    if not gff_file_path_bsa_assembly:
        gff_file_path_bsa_assembly = get_local_downloaded_file_path(config, bsa_genome_info, 'gff3')

    gff_file_path_hvg_assembly = pipeline_cfg.gff_files.get(hvg_assembly_id)
    if not gff_file_path_hvg_assembly:
        gff_file_path_hvg_assembly = get_local_downloaded_file_path(config, hvg_genome_info, 'gff3')

    if not gff_file_path_bsa_assembly:
        _log_status(_("错误: BSA基因组 '{}' 的GFF文件未找到或未下载。").format(bsa_assembly_id), "ERROR");
        return False
    if bsa_assembly_id != hvg_assembly_id and not gff_file_path_hvg_assembly:
        _log_status(_("错误: HVG基因组 '{}' 的GFF文件未找到或未下载。").format(hvg_assembly_id), "ERROR");
        return False

    gff_db_dir = pipeline_cfg.gff_db_storage_dir
    force_gff_db_creation = pipeline_cfg.force_gff_db_creation
    bsa_cols = pipeline_cfg.bsa_columns
    hvg_cols = pipeline_cfg.hvg_columns
    homology_cols = pipeline_cfg.homology_columns
    sel_criteria_s_to_b = asdict(pipeline_cfg.selection_criteria_source_to_bridge)  # Convert dataclass to dict
    sel_criteria_b_to_t = asdict(pipeline_cfg.selection_criteria_bridge_to_target)  # Convert dataclass to dict
    common_hvg_log2fc_thresh = pipeline_cfg.common_hvg_log2fc_threshold
    bridge_species_name = pipeline_cfg.bridge_species_name

    # --- 1. 加载Excel数据和同源数据 ---
    _log_status(_("步骤1: 加载表格数据..."), "INFO")
    try:
        # 检查输出sheet是否已存在
        try:
            excel_reader_check = pd.ExcelFile(input_excel, engine='openpyxl')
            if output_sheet_name in excel_reader_check.sheet_names:
                _log_status(_("错误: 输出工作表 '{}' 已存在于 '{}'。为避免覆盖，处理终止。").format(output_sheet_name,
                                                                                                 input_excel),
                            "ERROR");
                return False
        except FileNotFoundError:
            _log_status(_("错误: 输入Excel文件 '{}' 未找到。").format(input_excel), "ERROR");
            return False
        except Exception as e_check:  # Catch other potential issues before full read
            _log_status(_("警告: 检查Excel文件 '{}' 时发生错误: {}").format(input_excel, e_check), "WARNING")
            pass  # Continue to full read, which will likely fail if it's a real problem

        all_sheets_data = pd.read_excel(input_excel, sheet_name=None, engine='openpyxl')
        if bsa_sheet_name not in all_sheets_data: _log_status(
            _("错误: BSA工作表 '{}' 未在 '{}' 中找到。").format(bsa_sheet_name, input_excel), "ERROR"); return False
        bsa_df = all_sheets_data[bsa_sheet_name].copy()
        if hvg_sheet_name not in all_sheets_data: _log_status(
            _("错误: HVG工作表 '{}' 未在 '{}' 中找到。").format(hvg_sheet_name, input_excel), "ERROR"); return False
        hvg_df = all_sheets_data[hvg_sheet_name].copy()

        s_to_b_homology_df, b_to_t_homology_df = None, None
        if bsa_assembly_id != hvg_assembly_id:
            # Automatic homology file path detection
            homology_bsa_to_bridge_csv_path = get_local_downloaded_file_path(config, bsa_genome_info, 'homology_ath')
            homology_bridge_to_hvg_csv_path = get_local_downloaded_file_path(config, hvg_genome_info, 'homology_ath')

            if not homology_bsa_to_bridge_csv_path or not os.path.exists(homology_bsa_to_bridge_csv_path):
                _log_status(_("错误: 源基因组 '{}' 到桥梁物种的同源文件未找到或未下载: '{}'。请先下载。").format(
                    bsa_assembly_id, homology_bsa_to_bridge_csv_path or "N/A"), "ERROR");
                return False
            if not homology_bridge_to_hvg_csv_path or not os.path.exists(homology_bridge_to_hvg_csv_path):
                _log_status(_("错误: 桥梁物种到目标基因组 '{}' 的同源文件未找到或未下载: '{}'。请先下载。").format(
                    hvg_assembly_id, homology_bridge_to_hvg_csv_path or "N/A"), "ERROR");
                return False

            s_to_b_homology_df = pd.read_csv(homology_bsa_to_bridge_csv_path)
            b_to_t_homology_df = pd.read_csv(homology_bridge_to_hvg_csv_path)
            _log_status(_("同源数据CSV加载成功。"))
    except Exception as e:
        _log_status(_("加载数据时发生错误: {}").format(e), "ERROR");
        return False
    _log_progress(10, _("输入数据加载完毕。"))

    # --- 2. 准备GFF数据库 ---
    _log_status(_("步骤2: 准备GFF数据库..."), "INFO")
    if gff_db_dir and not os.path.exists(gff_db_dir):
        try:
            os.makedirs(gff_db_dir);
            _log_status(f"Created GFF DB directory: {gff_db_dir}")
        except OSError as e:
            _log_status(f"Error creating GFF DB directory {gff_db_dir}: {e}", "ERROR");
            return False

    # Use the gff_file_path_bsa_assembly resolved earlier
    db_A_name = os.path.basename(gff_file_path_bsa_assembly).replace('.gff3.gz', '').replace('.gff3', '') + "_gff.db"
    db_A_path = os.path.join(gff_db_dir, db_A_name)
    gff_A_db = create_or_load_gff_db(gff_file_path_bsa_assembly, db_path=db_A_path, force_create=force_gff_db_creation,
                                     verbose=True, status_callback=_log_status)  # Pass status_callback
    if not gff_A_db: _log_status(_("错误: 创建/加载源基因组 {} 的GFF数据库失败。").format(bsa_assembly_id),
                                 "ERROR"); return False

    gff_B_db = gff_A_db
    if bsa_assembly_id != hvg_assembly_id:
        # Use the gff_file_path_hvg_assembly resolved earlier
        db_B_name = os.path.basename(gff_file_path_hvg_assembly).replace('.gff3.gz', '').replace('.gff3',
                                                                                                 '') + "_gff.db"
        db_B_path = os.path.join(gff_db_dir, db_B_name)
        gff_B_db = create_or_load_gff_db(gff_file_path_hvg_assembly, db_path=db_B_path,
                                         force_create=force_gff_db_creation, verbose=True,
                                         status_callback=_log_status)  # Pass status_callback
        if not gff_B_db: _log_status(_("错误: 创建/加载目标基因组 {} 的GFF数据库失败。").format(hvg_assembly_id),
                                     "ERROR"); return False
    _log_status(_("GFF数据库准备完毕。"));
    _log_progress(25, _("GFF数据库就绪。"))

    # --- 3. 从BSA区域中提取源基因 ---
    _log_status(_("步骤3: 从BSA区域中提取源基因 (基于 {}) ...").format(bsa_assembly_id))
    source_genes_in_bsa_regions_data = []
    for bsa_idx, bsa_row in bsa_df.iterrows():
        try:
            # 从配置中获取列名
            chrom_val = str(bsa_row[bsa_cols.chr])  # Access as property
            start_val = int(bsa_row[bsa_cols.start])  # Access as property
            end_val = int(bsa_row[bsa_cols.end])  # Access as property

            bsa_row_dict_prefix = {f"bsa_{k}": v for k, v in bsa_row.items()}
            bsa_row_dict_prefix["bsa_original_row_index (0-based)"] = bsa_idx

            genes_found_this_region = 0
            # Use get_genes_in_region directly with the assembled GFF DB and callbacks
            genes_in_region_gff_db = get_genes_in_region(
                assembly_id=bsa_assembly_id,  # Pass assembly_id
                gff_filepath=gff_file_path_bsa_assembly,  # Use the determined path
                db_storage_dir=gff_db_dir,
                region=(chrom_val, start_val, end_val),
                force_db_creation=force_gff_db_creation,
                status_callback=_log_status
            )

            if not genes_in_region_gff_db:
                _log_status(_("警告: 在BSA区域 {}:{}-{} ({}) 中未找到基因。").format(
                    chrom_val, start_val, end_val, bsa_assembly_id), "WARNING")
                # Append a row indicating no genes found in this region
                source_genes_in_bsa_regions_data.append({
                    "BSA_Original_Index": bsa_idx,
                    "BSA_Chr": chrom_val,
                    "BSA_Start": start_val,
                    "BSA_End": end_val,
                    "Source_Gene_ID": None,
                    "Source_Chr": None,
                    "Source_Start": None,
                    "Source_End": None,
                    "Source_Strand": None,
                    "Match_Note": _("BSA区域无基因")
                })
                continue

            for gene_feature_dict in genes_in_region_gff_db:
                # 获取基因的详细信息
                gene_details = extract_gene_details(gff_A_db, gene_feature_dict['gene_id'])
                if gene_details:
                    # 合并BSA行信息和基因信息
                    row_data = {
                        **bsa_row_dict_prefix,
                        "Source_Gene_ID": gene_details['gene_id'],
                        "Source_Chr": gene_details['chr'],
                        "Source_Start": gene_details['start'],
                        "Source_End": gene_details['end'],
                        "Source_Strand": gene_details['strand'],
                        "Match_Note": _("BSA区域内基因")
                    }
                    source_genes_in_bsa_regions_data.append(row_data)
                    genes_found_this_region += 1
                else:
                    _log_status(_("警告: 未能在GFF数据库中找到基因 '{}' 的详细信息，跳过。").format(
                        gene_feature_dict['gene_id']), "WARNING")

            _log_status(_("在BSA区域 {}:{}-{} 中找到 {} 个基因。").format(
                chrom_val, start_val, end_val, genes_found_this_region))

        except KeyError as ke:
            _log_status(_("错误: BSA工作表中缺少关键列。请检查配置中的BSA列名是否正确。缺少: {}").format(ke), "ERROR");
            return False
        except ValueError as ve:
            _log_status(_("错误: BSA工作表中的区域坐标值无效。请确保是整数。错误: {}").format(ve), "ERROR");
            return False
        except Exception as e:
            _log_status(_("处理BSA区域时发生未知错误: {}").format(e), "ERROR");
            return False

    bsa_genes_df = pd.DataFrame(source_genes_in_bsa_regions_data)
    if bsa_genes_df.empty:
        _log_status(_("未从BSA区域中提取到任何基因。"), "WARNING")
        overall_success = True
        if task_done_callback: task_done_callback(overall_success)
        return True  # Continue with empty dataframe, it will propagate

    _log_progress(40, _("BSA区域基因提取完毕。"))

    # --- 4. 同源映射 (如果基因组不同) ---
    mapped_hvg_gene_ids = {}
    if bsa_assembly_id != hvg_assembly_id:
        _log_status(_("步骤4: 执行同源映射 (从 {} 到 {}) ...").format(bsa_assembly_id, hvg_assembly_id))
        _log_progress(50, _("开始同源映射..."))

        # 获取源基因组和目标基因组的 homology_id_slicer
        source_id_slicer = bsa_genome_info.homology_id_slicer
        hvg_id_slicer = hvg_genome_info.homology_id_slicer

        try:
            # 假设 bsa_genes_df 的 'Source_Gene_ID' 列包含了所有需要映射的基因ID
            # 确保传递给 map_genes_via_bridge 的基因ID是唯一的列表
            genes_to_map = bsa_genes_df['Source_Gene_ID'].dropna().unique().tolist()
            if not genes_to_map:
                _log_status(_("BSA基因列表中没有需要映射的基因，跳过同源映射。"), "WARNING")
                mapped_hvg_gene_ids = {gene_id: [] for gene_id in bsa_genes_df['Source_Gene_ID'].dropna().unique()}
            else:
                mapped_df, fuzzy_count = map_genes_via_bridge(
                    source_gene_ids=genes_to_map,
                    source_assembly_name=bsa_assembly_id,
                    target_assembly_name=hvg_assembly_id,
                    bridge_species_name=bridge_species_name,
                    source_to_bridge_homology_df=s_to_b_homology_df,
                    bridge_to_target_homology_df=b_to_t_homology_df,
                    s_to_b_query_col=homology_cols.get('query', "Query"),
                    s_to_b_match_col=homology_cols.get('match', "Match"),
                    b_to_t_query_col=homology_cols.get('query', "Query"),
                    b_to_t_match_col=homology_cols.get('match', "Match"),
                    evalue_col=homology_cols.get('evalue', "Exp"),
                    score_col=homology_cols.get('score', "Score"),
                    pid_col=homology_cols.get('pid', "PID"),
                    selection_criteria_s_to_b=sel_criteria_s_to_b,
                    selection_criteria_b_to_t=sel_criteria_b_to_t,
                    source_id_slicer=source_id_slicer,
                    bridge_id_slicer=hvg_id_slicer,  # Changed to hvg_id_slicer
                    status_callback=_log_status
                )
                if fuzzy_count > 0:
                    _log_status(_("注意: 同源映射中执行了 {} 次模糊匹配。").format(fuzzy_count), "WARNING")

                # 将映射结果转换为 {原始基因ID: [映射基因ID1, 映射基因ID2], ...} 的字典形式
                # 确保映射结果能处理一对多，且只包含 HVG 基因组中的 ID
                mapped_hvg_gene_ids = {}
                for idx, row in mapped_df.iterrows():
                    original_id = row['Source_Gene_ID']
                    mapped_id = row['Target_Gene_ID']
                    if original_id not in mapped_hvg_gene_ids:
                        mapped_hvg_gene_ids[original_id] = []
                    mapped_hvg_gene_ids[original_id].append(mapped_id)

                # 为那些没有找到映射的基因也添加空列表条目，以便后续合并时有对应
                for gene_id in genes_to_map:
                    if gene_id not in mapped_hvg_gene_ids:
                        mapped_hvg_gene_ids[gene_id] = []

        except Exception as e:
            _log_status(_("执行同源映射时发生错误: {}").format(e), "ERROR");
            return False
        _log_progress(70, _("同源映射完成。"))
    else:
        _log_status(_("源基因组和HVG基因组相同 ({})，跳过同源映射。").format(bsa_assembly_id))
        # 如果基因组相同，则直接将源基因ID作为映射后的HVG基因ID
        mapped_hvg_gene_ids = {gene_id: [gene_id] for gene_id in bsa_genes_df['Source_Gene_ID'].dropna().unique()}
        _log_progress(70, _("同源映射跳过。"))

    # --- 5. 合并HVG数据和GFF信息 ---
    _log_status(_("步骤5: 合并HVG数据和GFF信息..."), "INFO")

    # 确保 HVG 列名存在于 hvg_df
    required_hvg_cols = [hvg_cols.gene_id, hvg_cols.category, hvg_cols.log2fc]
    for col in required_hvg_cols:
        if col not in hvg_df.columns:
            _log_status(_("错误: HVG工作表中缺少关键列 '{}'。请检查配置。").format(col), "ERROR")
            return False

    # 准备一个 HVG 基因信息字典，方便查询
    hvg_info_map = hvg_df.set_index(hvg_cols.gene_id).to_dict(orient='index')

    final_integrated_data = []
    # 遍历 BSA 区域提取出的基因
    for bsa_gene_idx, bsa_gene_row in bsa_genes_df.iterrows():
        source_gene_id = bsa_gene_row['Source_Gene_ID']
        if pd.isna(source_gene_id):
            # 如果BSA区域内没有基因，则直接将原始BSA行数据加入，并标记
            final_integrated_data.append(
                {**bsa_gene_row.to_dict(), "HVG_Category": None, "HVG_log2FC": None, "Mapped_HVG_Gene_IDs": None,
                 "Match_Note": _("BSA区域无基因")})
            continue

        # 获取映射后的 HVG 基因 ID 列表
        hvg_mapped_ids = mapped_hvg_gene_ids.get(source_gene_id, [])

        if not hvg_mapped_ids:
            # 如果没有映射到 HVG 基因
            row_data = bsa_gene_row.to_dict()
            row_data.update({
                "HVG_Category": None,
                "HVG_log2FC": None,
                "Mapped_HVG_Gene_IDs": _("无映射"),
                "Match_Note": _("无映射HVG")
            })
            final_integrated_data.append(row_data)
            continue

        # 为每个映射到的 HVG 基因，获取其 HVG 信息和 GFF 信息
        # 如果一个 Source_Gene_ID 映射到多个 HVG_Gene_ID，则为每个映射创建一个行
        # 如果一个 HVG_Gene_ID 在 HVG 数据中多次出现（例如，不同条件），这里只取第一次遇到的

        found_hvg_match = False
        for mapped_id in hvg_mapped_ids:
            hvg_data = hvg_info_map.get(mapped_id)
            if hvg_data:
                hvg_category = hvg_data[hvg_cols.category]
                hvg_log2fc = hvg_data[hvg_cols.log2fc]

                # 获取 HVG 基因的 GFF 信息
                hvg_gene_details = extract_gene_details(gff_B_db, mapped_id)
                if not hvg_gene_details:
                    _log_status(_("警告: HVG基因 '{}' 未能在GFF数据库中找到详细信息。").format(mapped_id), "WARNING")
                    hvg_gene_details = {'chr': None, 'start': None, 'end': None, 'strand': None}  # Placeholder

                # 整合所有信息
                row_data = bsa_gene_row.to_dict()
                row_data.update({
                    "Mapped_HVG_Gene_IDs": mapped_id,
                    "HVG_Category": hvg_category,
                    "HVG_log2FC": hvg_log2fc,
                    "HVG_Chr": hvg_gene_details.get('chr'),
                    "HVG_Start": hvg_gene_details.get('start'),
                    "HVG_End": hvg_gene_details.get('end'),
                    "HVG_Strand": hvg_gene_details.get('strand'),
                    "Match_Note": _("HVG匹配")
                })
                final_integrated_data.append(row_data)
                found_hvg_match = True
            else:
                # 映射到了，但该基因不在 HVG 列表中
                row_data = bsa_gene_row.to_dict()
                row_data.update({
                    "Mapped_HVG_Gene_IDs": mapped_id,
                    "HVG_Category": None,
                    "HVG_log2FC": None,
                    "HVG_Chr": None,
                    "HVG_Start": None,
                    "HVG_End": None,
                    "HVG_Strand": None,
                    "Match_Note": _("映射到但不在HVG列表")
                })
                final_integrated_data.append(row_data)
                found_hvg_match = True  # Still considered a "match" for mapping purposes

        if not found_hvg_match and hvg_mapped_ids:  # Should ideally not happen if loop ran, but as a safeguard
            _log_status(_("警告: 基因 '{}' 映射到HVG基因 ({})，但未能从HVG数据中检索信息。").format(source_gene_id,
                                                                                                  ", ".join(
                                                                                                      hvg_mapped_ids)),
                        "WARNING")

    if not final_integrated_data:
        _log_status(_("未生成任何整合结果。"), "WARNING")
        overall_success = True
        if task_done_callback: task_done_callback(overall_success)
        return True

    integrated_df = pd.DataFrame(final_integrated_data)

    _log_progress(80, _("HVG数据和GFF信息合并完成。"))

    # --- 6. 筛选和标记候选基因 ---
    _log_status(_("步骤6: 筛选和标记候选基因..."), "INFO")

    # 定义“候选基因”的条件
    # 必须在BSA区域内 (由之前的逻辑确保，即 Source_Gene_ID 非空)
    # 必须有映射到的HVG基因 (Mapped_HVG_Gene_IDs 非空且非“无映射”)
    # 必须在HVG列表中 (HVG_Category 和 HVG_log2FC 非空)
    # HVG_Category 必须是 'TopHVG' 或 'CommonTopHVG'
    # 如果是 'CommonTopHVG'，则其 log2FC 绝对值必须大于等于 common_hvg_log2fc_threshold

    integrated_df['Is_Candidate'] = False

    # Ensure columns exist before using them
    if 'HVG_Category' in integrated_df.columns and 'HVG_log2FC' in integrated_df.columns:
        # Condition 1: Mapped to an HVG gene and present in HVG list
        cond_hvg_mapped_and_present = integrated_df['Mapped_HVG_Gene_IDs'].notna() & \
                                      (integrated_df['Mapped_HVG_Gene_IDs'] != _("无映射")) & \
                                      integrated_df['HVG_Category'].notna()

        # Condition 2: HVG Category is 'TopHVG'
        cond_tophvg = integrated_df['HVG_Category'] == 'TopHVG'

        # Condition 3: HVG Category is 'CommonTopHVG' AND log2FC meets threshold
        # Safely convert to numeric, coercing errors to NaN
        integrated_df['HVG_log2FC_Numeric'] = pd.to_numeric(integrated_df['HVG_log2FC'], errors='coerce')

        cond_common_tophvg_threshold = (integrated_df['HVG_Category'] == 'CommonTopHVG') & \
                                       (integrated_df['HVG_log2FC_Numeric'].abs() >= common_hvg_log2fc_thresh)

        # Combine conditions for Is_Candidate
        integrated_df['Is_Candidate'] = cond_hvg_mapped_and_present & (cond_tophvg | cond_common_tophvg_threshold)
    else:
        _log_status(_("警告: 缺少 'HVG_Category' 或 'HVG_log2FC' 列，无法正确标记候选基因。"), "WARNING")

    # 7. 添加优先级排序 (示例：根据 log2FC 绝对值降序)
    # 首先对候选基因进行排序，然后是非候选基因
    if 'HVG_log2FC_Numeric' in integrated_df.columns:
        integrated_df['Sorting_Priority'] = integrated_df['HVG_log2FC_Numeric'].abs()
        integrated_df['Sorting_Priority'] = integrated_df['Sorting_Priority'].fillna(
            -1)  # For non-numeric or non-candidates

        # Sort candidates by abs(log2FC) descending, then non-candidates
        integrated_df = integrated_df.sort_values(
            by=['Is_Candidate', 'Sorting_Priority'],
            ascending=[False, False]
        ).drop(columns=['Sorting_Priority', 'HVG_log2FC_Numeric'])  # Drop temp columns
    else:
        _log_status(_("警告: 缺少 'HVG_log2FC' 列，无法进行优先级排序。"), "WARNING")

    _log_progress(90, _("候选基因筛选和排序完成。"))

    # --- 8. 写入结果到Excel ---
    _log_status(_("步骤8: 写入结果到Excel文件..."), "INFO")
    try:
        # 读取现有工作簿，然后添加新工作表
        with pd.ExcelWriter(input_excel, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            # 检查输出sheet是否存在并决定行为
            # 由于上面已经检查过且 if_sheet_exists='replace'，这里直接写即可
            integrated_df.to_excel(writer, sheet_name=output_sheet_name, index=False)

        _log_status(_("整合分析结果已成功写入到 '{}' 中的工作表 '{}'。").format(input_excel, output_sheet_name))
        overall_success = True
    except Exception as e:
        _log_status(_("错误: 写入结果到Excel时发生错误: {}").format(e), "ERROR");
        return False

    _log_progress(100, _("整合分析流程结束。"))
    if task_done_callback: task_done_callback(overall_success)
    return overall_success


# 新增：功能注释流程函数
def run_functional_annotation(
        config: MainConfig,
        input_gene_ids: List[str],
        assembly_id_override: Optional[str] = None,  # New parameter for assembly selection
        output_csv_path: Optional[str] = None,
        go_anno: bool = True,
        ipr_anno: bool = True,
        kegg_ortho_anno: bool = False,
        kegg_path_anno: bool = False,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    """
    执行功能注释流程。
    """

    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(f"[{level}] {msg}")
        elif level == "ERROR":
            print(f"ERROR: {msg}")
        elif level == "WARNING":
            print(f"WARNING: {msg}")
        else:
            print(f"INFO: {msg}")

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            print(f"PROGRESS [{percent}%]: {msg}")

    overall_success = False
    _log_status(_("开始功能注释流程..."))
    _log_progress(0, _("初始化配置..."))

    if not CORE_MODULES_IMPORTED:
        _log_status(_("错误: 核心模块未加载，无法执行功能注释。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    anno_cfg = config.annotation_tool
    downloader_cfg = config.downloader

    if not input_gene_ids:
        _log_status(_("错误: 没有提供基因ID进行注释。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Get genome sources
    genome_sources = get_genome_data_sources(config, logger=_log_status)
    if not genome_sources:
        _log_status(_("错误: 未能加载基因组源数据。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Determine assembly_id
    assembly_id = assembly_id_override
    if not assembly_id:
        _log_status(_("错误: 必须指定基因组版本ID用于功能注释。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    selected_genome_info: Optional[GenomeSourceItem] = genome_sources.get(assembly_id)
    if not selected_genome_info:
        _log_status(_("错误: 基因组 '{}' 未在基因组源列表中找到，无法进行注释。").format(assembly_id), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Initialize Annotator
    try:
        from cotton_toolkit.tools.annotator import Annotator
        annotator = Annotator(
            database_root_dir=anno_cfg.database_root_dir,
            genome_info=selected_genome_info,  # Pass the selected genome info
            main_config=config,  # Pass the whole config to Annotator for downloader access
            status_callback=_log_status,
            progress_callback=_log_progress
        )
        _log_progress(10, _("注释器初始化完成。"))
    except Exception as e:
        _log_status(_("错误: 初始化注释器失败: {}").format(e), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Prepare output path
    if not output_csv_path:
        annotation_results_dir = anno_cfg.output_dir_name
        os.makedirs(annotation_results_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_csv_path = os.path.join(annotation_results_dir, f"functional_annotation_{assembly_id}_{timestamp}.csv")

    annotation_types = []
    if go_anno: annotation_types.append('go')
    if ipr_anno: annotation_types.append('ipr')
    if kegg_ortho_anno: annotation_types.append('kegg_orthologs')
    if kegg_path_anno: annotation_types.append('kegg_pathways')

    if not annotation_types:
        _log_status(_("警告: 未选择任何注释类型。"), "WARNING")
        # Still create an empty file with gene IDs if no annotations are selected
        empty_df = pd.DataFrame(input_gene_ids, columns=["Gene_ID"])
        try:
            empty_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            _log_status(_("已生成空注释结果文件: {}").format(output_csv_path))
            overall_success = True
        except Exception as e:
            _log_status(_("错误: 保存空注释结果文件失败: {}").format(e), "ERROR")
            overall_success = False
        if task_done_callback: task_done_callback(overall_success)
        return overall_success

    # Perform annotation
    _log_status(_("开始获取和处理注释数据..."))
    try:
        final_results_df = annotator.annotate_genes(
            gene_ids=input_gene_ids,
            annotation_types=annotation_types
        )
        _log_progress(90, _("注释完成。"))
    except Exception as e:
        _log_status(_("错误: 执行基因注释失败: {}").format(e), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # Save results
    _log_status(_("保存注释结果..."))
    try:
        final_results_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        _log_status(_("功能注释结果已保存到: {}").format(output_csv_path))
        overall_success = True
    except Exception as e:
        _log_status(_("错误: 保存功能注释结果时发生错误: {}").format(e), "ERROR")
        overall_success = False

    _log_progress(100, _("功能注释流程结束。"))
    if task_done_callback: task_done_callback(overall_success)
    return overall_success
