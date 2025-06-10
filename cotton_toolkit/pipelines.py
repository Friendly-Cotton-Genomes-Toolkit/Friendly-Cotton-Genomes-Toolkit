# cotton_toolkit/pipelines.py
import gzip
import os
import time
from typing import List, Dict, Any, Optional, Callable, Tuple
from urllib.parse import urlparse
import pandas as pd

from cotton_toolkit.config.loader import get_genome_data_sources

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
    from .core.gff_parser import create_or_load_gff_db, get_features_in_region, DB_SUFFIX, \
    extract_gene_details  # extract_gene_details 如果需要 #
    from .core.homology_mapper import map_genes_via_bridge, select_best_homologs  #

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
            self.id = id;  #
            self.chrom = chrom;  #
            self.start = start;  #
            self.end = end;  #
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
                              verbose: bool = True) -> Optional[MockGFFDB]:  #
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


# 独立同源映射功能
def run_homology_mapping_standalone(
        config: Dict[str, Any],
        source_gene_ids_override: Optional[List[str]] = None,
        source_assembly_id_override: Optional[str] = None,
        target_assembly_id_override: Optional[str] = None,
        s_to_b_homology_file_override: Optional[str] = None,
        b_to_t_homology_file_override: Optional[str] = None,
        output_csv_path: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> bool:
    """
    独立运行基因组同源映射流程。
    支持 棉花 -> 拟南芥 (一步) 和 棉花 -> 拟南芥 -> 棉花 (两步) 两种模式。
    """

    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(f"[{level}] {msg}")
        elif level == "ERROR":
            print(f"ERROR: {msg}")
        else:
            print(f"INFO: {msg}")

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            print(f"PROGRESS [{percent}%]: {msg}")

    # --- 新增：定义一个特殊的标识符来代表拟南芥 ---
    ARABIDOPSIS_TARGET_ID = "arabidopsis_auto_select"

    pipeline_cfg = config.get('integration_pipeline', {})
    downloader_cfg = config.get('downloader', {})

    source_assembly_id = source_assembly_id_override or pipeline_cfg.get('bsa_assembly_id')
    target_assembly_id = target_assembly_id_override or pipeline_cfg.get('hvg_assembly_id')

    if not all([source_assembly_id, target_assembly_id]):
        _log_status(_("错误: 必须指定源基因组ID和目标基因组ID。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    source_gene_ids = source_gene_ids_override
    if not source_gene_ids:
        _log_status(_("错误: 必须提供需要映射的源基因ID列表。"), "ERROR")
        if task_done_callback: task_done_callback(False)
        return False

    # 确定默认输出路径
    final_output_path = output_csv_path
    if not final_output_path:
        final_output_dir = os.path.join(downloader_cfg.get('download_output_base_dir', "downloaded_cotton_data"),
                                        "homology_map_results")
        os.makedirs(final_output_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_output_path = os.path.join(final_output_dir,
                                         f"homology_map_{source_assembly_id}_to_{target_assembly_id}_{timestamp}.csv")

    # --- 新增：根据目标ID选择不同的执行路径 ---
    if target_assembly_id == ARABIDOPSIS_TARGET_ID:
        # --- 执行新的一步映射：棉花 -> 拟南芥 ---
        _log_status(_("执行一步映射模式: 棉花 -> 拟南芥..."))
        _log_progress(10, _("加载源到拟南芥的同源文件..."))

        # 获取源-桥梁同源文件
        s_to_b_homology_file = s_to_b_homology_file_override or pipeline_cfg.get('homology_files', {}).get(
            'bsa_to_bridge_csv')
        if not s_to_b_homology_file or not os.path.exists(s_to_b_homology_file):
            _log_status(_("错误: 源到拟南芥的同源文件未找到或未配置: {}").format(s_to_b_homology_file), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False

        try:
            s_to_b_df = pd.read_csv(s_to_b_homology_file)
            _log_progress(30, _("同源文件加载完毕。"))

            # 从配置中获取筛选标准和列名
            homology_cols = pipeline_cfg.get('homology_columns', {})
            sel_criteria = pipeline_cfg.get('selection_criteria_source_to_bridge', {})

            _log_status(_("开始筛选最佳拟南芥同源基因..."))
            _log_progress(50, _("筛选中..."))

            # 筛选出与输入基因相关的行
            source_query_col = homology_cols.get('query', "Query")
            related_homology_df = s_to_b_df[s_to_b_df[source_query_col].isin(source_gene_ids)]

            # 调用 select_best_homologs
            best_hits_df = select_best_homologs(
                homology_df=related_homology_df,
                query_gene_id_col=source_query_col,
                match_gene_id_col=homology_cols.get('match', "Match"),
                criteria=sel_criteria,
                evalue_col_in_df=homology_cols.get('evalue', "Exp"),
                score_col_in_df=homology_cols.get('score', "Score"),
                pid_col_in_df=homology_cols.get('pid', "PID")
            )

            _log_progress(80, _("筛选完成。"))
            if best_hits_df.empty:
                _log_status(_("未找到任何符合条件的拟南芥同源基因。"), "WARNING")

            best_hits_df.to_csv(final_output_path, index=False)
            _log_status(_("一步映射结果已保存到: {}").format(final_output_path))
            _log_progress(100, _("流程结束。"))
            if task_done_callback: task_done_callback(True)
            return True

        except Exception as e:
            _log_status(_("执行一步映射时发生错误: {}").format(e), "ERROR")
            if task_done_callback: task_done_callback(False)
            return False

    else:
        # --- 执行旧的两步映射：棉花 -> 拟南芥 -> 棉花 ---
        _log_status(_("执行两步映射模式: 棉花 -> 桥梁 -> 棉花..."))
        _log_progress(10, _("加载同源文件..."))

        s_to_b_homology_file = s_to_b_homology_file_override or pipeline_cfg.get('homology_files', {}).get(
            'bsa_to_bridge_csv')
        b_to_t_homology_file = b_to_t_homology_file_override or pipeline_cfg.get('homology_files', {}).get(
            'bridge_to_hvg_csv')

        if not CORE_MODULES_IMPORTED:
            _log_status(_("错误: 核心模块未加载，无法执行同源映射。"), "ERROR");
            return False

        pipeline_cfg = config.get('integration_pipeline', {})
        downloader_cfg = config.get('downloader', {})

        # 获取基因组源信息，用于 slicer
        genome_sources = {}
        if 'genome_sources_file' in downloader_cfg:
            from .config.loader import get_genome_data_sources as get_gs_func # 动态导入，避免循环依赖
            genome_sources = get_gs_func(config) or {}

        source_assembly_id = source_assembly_id_override if source_assembly_id_override else pipeline_cfg.get('bsa_assembly_id')
        target_assembly_id = target_assembly_id_override if target_assembly_id_override else pipeline_cfg.get('hvg_assembly_id')

        if not all([source_assembly_id, target_assembly_id]):
            _log_status(_("错误: 必须指定源基因组ID和目标基因组ID。"), "ERROR");
            return False
        if source_assembly_id == target_assembly_id:
            _log_status(_("源基因组和目标基因组相同，无需执行同源映射。"), "INFO")
            return True # 认为成功

        s_to_b_homology_file = s_to_b_homology_file_override
        b_to_t_homology_file = b_to_t_homology_file_override

        # 尝试从配置中获取同源文件路径
        homology_files_cfg = pipeline_cfg.get('homology_files', {})
        if not s_to_b_homology_file:
            s_to_b_homology_file = homology_files_cfg.get('bsa_to_bridge_csv')
        if not b_to_t_homology_file:
            b_to_t_homology_file = homology_files_cfg.get('bridge_to_hvg_csv')

        if not all([s_to_b_homology_file, b_to_t_homology_file]):
            _log_status(_("错误: 必须提供源到桥梁和桥梁到目标的同源文件路径。"), "ERROR");
            return False
        if not os.path.exists(s_to_b_homology_file):
            _log_status(_("错误: 源到桥梁同源文件 '{}' 未找到。").format(s_to_b_homology_file), "ERROR");
            return False
        if not os.path.exists(b_to_t_homology_file):
            _log_status(_("错误: 桥梁到目标同源文件 '{}' 未找到。").format(b_to_t_homology_file), "ERROR");
            return False

        try:
            s_to_b_homology_df = pd.read_csv(s_to_b_homology_file)
            b_to_t_homology_df = pd.read_csv(b_to_t_homology_file)
            _log_progress(20, _("同源文件加载完毕。"))

        except Exception as e:
            _log_status(_("加载同源文件时出错: {}").format(e), "ERROR");
            return False
        _log_progress(20, _("同源文件加载完毕。"))

        source_gene_ids = source_gene_ids_override
        if not source_gene_ids:
            _log_status(_("错误: 必须提供需要映射的源基因ID列表。"), "ERROR");
            return False

        homology_cols = pipeline_cfg.get('homology_columns', {})
        sel_criteria_s_to_b = pipeline_cfg.get('selection_criteria_source_to_bridge', {})
        sel_criteria_b_to_t = pipeline_cfg.get('selection_criteria_bridge_to_target', {})
        bridge_species_name = pipeline_cfg.get('bridge_species_name', "Arabidopsis_thaliana")

        source_id_slicer = genome_sources.get(source_assembly_id, {}).get('homology_id_slicer')
        bridge_id_slicer = genome_sources.get(target_assembly_id, {}).get('homology_id_slicer') # Assuming target assembly's slicer for bridge to target

        _log_status(_("开始执行同源映射算法..."))
        _log_progress(40, _("执行映射..."))
        try:
            mapped_df, fuzzy_count = map_genes_via_bridge(
                source_gene_ids=source_gene_ids,
                source_assembly_name=source_assembly_id,
                target_assembly_name=target_assembly_id,
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
                bridge_id_slicer=bridge_id_slicer
            )
            if fuzzy_count > 0:
                _log_status(_("注意: 在同源映射中执行了 {} 次模糊匹配。").format(fuzzy_count), "WARNING")

            if mapped_df.empty:
                _log_status(_("未找到任何有效同源映射结果。"), "WARNING")
                overall_success = True # 流程本身没出错，只是没找到结果
            else:
                _log_status(_("同源映射完成，找到 {} 条映射结果。").format(len(mapped_df)))
                _log_progress(80, _("映射完成，正在写入结果。"))

                final_output_path = output_csv_path
                if not final_output_path:
                    # 默认输出到下载目录或临时目录
                    final_output_dir = os.path.join(downloader_cfg.get('download_output_base_dir', "downloaded_cotton_data"), "homology_map_results")
                    os.makedirs(final_output_dir, exist_ok=True)
                    final_output_path = os.path.join(final_output_dir, f"homology_map_{source_assembly_id}_to_{target_assembly_id}.csv")

                mapped_df.to_csv(final_output_path, index=False)
                _log_status(_("同源映射结果已保存到: {}").format(final_output_path))
                overall_success = True

        except Exception as e:
            _log_status(_("执行同源映射时发生错误: {}").format(e), "ERROR")
            overall_success = False
        finally:
            if task_done_callback: task_done_callback(overall_success)
        return overall_success

# 新增：独立GFF基因查询功能
def run_gff_gene_lookup_standalone(
        config: Dict[str, Any],
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

    pipeline_cfg = config.get('integration_pipeline', {})
    downloader_cfg = config.get('downloader', {})

    assembly_id = assembly_id_override
    if not assembly_id:
        assembly_id = pipeline_cfg.get('bsa_assembly_id')
        if not assembly_id: assembly_id = pipeline_cfg.get('hvg_assembly_id')

    if not assembly_id:
        _log_status(_("错误: 必须指定基因组版本ID用于GFF查询。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False

    gff_files_cfg = pipeline_cfg.get('gff_files', {})
    gff_file_path = gff_files_cfg.get(assembly_id)

    if not gff_file_path:
        genome_sources = {}
        if 'genome_sources_file' in downloader_cfg:
            from .config.loader import get_genome_data_sources as get_gs_func
            genome_sources = get_gs_func(config) or {}

        genome_info = genome_sources.get(assembly_id)
        if genome_info and genome_info.get("gff3_url"):
            safe_dir_name = genome_info.get("species_name", assembly_id).replace(" ", "_").replace(".", "_").replace(
                "(", "").replace(")", "").replace("'", "")
            version_output_dir = os.path.join(downloader_cfg.get('download_output_base_dir', "downloaded_cotton_data"),
                                              safe_dir_name)
            # Correctly parse URL for filename, even if it's a local path in mock
            try:
                parsed_url = urlparse(genome_info["gff3_url"])
                filename = os.path.basename(
                    parsed_url.path) if parsed_url.path else f"{assembly_id}_annotations.gff3.gz"
            except:  # Fallback for non-URL like paths in mock or error cases
                filename = f"{assembly_id}_annotations.gff3.gz"
            gff_file_path = os.path.join(version_output_dir, filename)

    if not gff_file_path or not os.path.exists(gff_file_path):
        _log_status(
            _("错误: 未找到基因组 '{}' 的GFF文件 '{}'。请检查配置文件或下载。").format(assembly_id, gff_file_path),
            "ERROR");
        if task_done_callback: task_done_callback(False)
        return False

    gff_db_dir = pipeline_cfg.get('gff_db_storage_dir', "gff_databases_cache")
    force_gff_db_creation = pipeline_cfg.get('force_gff_db_creation', False)

    _log_progress(20, _("加载GFF数据库..."))
    db_path_to_create = os.path.join(gff_db_dir, os.path.basename(gff_file_path) + DB_SUFFIX) if gff_db_dir else None
    gff_db = create_or_load_gff_db(gff_file_path, db_path=db_path_to_create, force_create=force_gff_db_creation,
                                   verbose=False)
    if not gff_db:
        _log_status(_("错误: 无法加载或创建GFF数据库。"), "ERROR");
        if task_done_callback: task_done_callback(False)
        return False
    _log_progress(40, _("GFF数据库加载完毕。"))

    results_data = []
    if gene_ids_override:
        _log_status(_("按基因ID查询 {} 个基因...").format(len(gene_ids_override)))
        for i, gene_id in enumerate(gene_ids_override):
            gene_details = extract_gene_details(gff_db, gene_id)
            if gene_details:
                results_data.append(gene_details)
            else:
                _log_status(_("警告: 未找到基因ID '{}' 的详细信息。").format(gene_id), "WARNING")
            _log_progress(40 + int((i + 1) / len(gene_ids_override) * 40), _("查询基因ID..."))
    elif region_override:
        chrom, start, end = region_override
        _log_status(_("按区域 {}:{}-{} 查询基因...").format(chrom, start, end))
        # Convert to list to get a count for progress, or iterate directly if memory is a concern
        genes_in_region_list = list(get_features_in_region(gff_db, chrom, start, end, feature_type='gene'))
        total_genes_in_region = len(genes_in_region_list)
        for i, gene_feature in enumerate(genes_in_region_list):
            gene_details = extract_gene_details(gff_db, gene_feature.id)
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
            final_output_dir = os.path.join(downloader_cfg.get('download_output_base_dir', "downloaded_cotton_data"),
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
        config: Dict[str, Any],
        source_assembly: str,
        gene_ids: List[str],
        status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[Dict[str, str], str]:
    """
    将棉花基因ID列表转换为拟南芥同源基因ID。

    Args:
        config (Dict[str, Any]): 主配置字典。
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
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        raise ValueError("无法加载基因组来源信息。")

    source_info = genome_sources.get(source_assembly)
    if not source_info:
        raise ValueError(f"在基因组来源文件中未找到 '{source_assembly}' 的配置。")

    homology_type = source_info.get('homology_type', _('未知版本'))
    homology_url = source_info.get('homology_ath_url')
    if not homology_url:
        raise ValueError(f"基因组 '{source_assembly}' 未配置 'homology_ath_url'。")

    # 2. 确定本地同源文件的路径 (假设已被下载和转换)
    # downloader 会将 .xlsx.gz 或 .txt.gz 转换为 .csv
    base_dir = config.get('downloader', {}).get('download_output_base_dir', 'downloaded_cotton_data')
    safe_dir_name = source_info.get("species_name", source_assembly).replace(" ", "_").replace(".", "_").replace("(",
                                                                                                                 "").replace(
        ")", "").replace("'", "")
    version_output_dir = os.path.join(base_dir, safe_dir_name)

    # 尝试找到对应的CSV文件，这是下载和转换后的最终产物
    # 从URL推断原始文件名
    parsed_url = urlparse(homology_url)
    original_filename = os.path.basename(parsed_url.path)
    # 将 .xlsx.gz 或 .txt.gz 等后缀替换为 .csv
    base_name_no_ext = os.path.splitext(os.path.splitext(original_filename)[0])[0]
    homology_csv_path = os.path.join(version_output_dir, f"{base_name_no_ext}.csv")

    if not os.path.exists(homology_csv_path):
        raise FileNotFoundError(f"同源文件不存在: {homology_csv_path}。请先通过'数据下载'功能下载并转换该文件。")

    _log(f"使用同源文件: {os.path.basename(homology_csv_path)}")

    # 3. 读取同源文件并进行查找
    homology_df = pd.read_csv(homology_csv_path)
    homology_cols = config.get('integration_pipeline', {}).get('homology_columns', {})

    # 获取用于筛选的最佳匹配标准
    sel_criteria = config.get('integration_pipeline', {}).get('selection_criteria_source_to_bridge', {})

    all_matches = homology_df[homology_df[homology_cols.get('query')].isin(gene_ids)]

    # 使用 select_best_homologs 函数来找到最佳匹配
    best_hits_df = select_best_homologs(
        homology_df=all_matches,
        query_gene_id_col=homology_cols.get('query'),
        match_gene_id_col=homology_cols.get('match'),
        criteria=sel_criteria,
        evalue_col_in_df=homology_cols.get('evalue'),
        score_col_in_df=homology_cols.get('score'),
        pid_col_in_df=homology_cols.get('pid')
    )

    results = {}
    if not best_hits_df.empty:
        # 将结果转换为字典
        results = pd.Series(
            best_hits_df[homology_cols.get('match')].values,
            index=best_hits_df[homology_cols.get('query')]
        ).to_dict()

    # 为未找到匹配的基因添加标记
    for gene_id in gene_ids:
        if gene_id not in results:
            results[gene_id] = "Not Found"

    _log(f"转换完成，处理了 {len(gene_ids)} 个基因ID。")

    return results, homology_type



# --- 主整合函数 ---
def integrate_bsa_with_hvg(
        config: Dict[str, Any],
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
        config (Dict[str, Any]): 包含所有流程所需参数的配置字典。
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

    pipeline_cfg = config.get('integration_pipeline')
    if not pipeline_cfg:
        _log_status(_("错误: 配置中未找到 'integration_pipeline' 部分。"), "ERROR");
        return False

    # --- 参数提取与验证 (补充完整) ---
    input_excel = input_excel_path_override if input_excel_path_override else pipeline_cfg.get('input_excel_path')  #
    bsa_sheet_name = pipeline_cfg.get('bsa_sheet_name')  #
    hvg_sheet_name = pipeline_cfg.get('hvg_sheet_name')  #
    output_sheet_name = output_sheet_name_override if output_sheet_name_override else pipeline_cfg.get(
        'output_sheet_name')  #

    if not all([input_excel, bsa_sheet_name, hvg_sheet_name, output_sheet_name]):  #
        _log_status(_("错误: 输入/输出Excel或Sheet名称配置不完整。"), "ERROR");  #
        return False  #

    _log_status(f"  Input Excel: {input_excel}")  #
    _log_status(f"  BSA Sheet: {bsa_sheet_name}, HVG Sheet: {hvg_sheet_name}, Output Sheet: {output_sheet_name}")  #

    bsa_assembly_id = pipeline_cfg.get('bsa_assembly_id')  #
    hvg_assembly_id = pipeline_cfg.get('hvg_assembly_id')  #
    if not all([bsa_assembly_id, hvg_assembly_id]):  #
        _log_status(_("错误: 必须在配置中指定 'bsa_assembly_id' 和 'hvg_assembly_id'。"), "ERROR");  #
        return False  #
    _log_status(f"  BSA Assembly: {bsa_assembly_id}, HVG Assembly: {hvg_assembly_id}")  #

    gff_files_cfg = pipeline_cfg.get('gff_files', {})  #
    gff_file_path_bsa_assembly = gff_files_cfg.get(bsa_assembly_id)  #
    gff_file_path_hvg_assembly = gff_files_cfg.get(hvg_assembly_id)  #
    if not gff_file_path_bsa_assembly or (bsa_assembly_id != hvg_assembly_id and not gff_file_path_hvg_assembly):  #
        _log_status(_("错误: GFF文件路径配置不完整。"), "ERROR");  #
        return False  #

    gff_db_dir = pipeline_cfg.get('gff_db_storage_dir')  #
    force_gff_db_creation = pipeline_cfg.get('force_gff_db_creation', False)  #
    bsa_cols = pipeline_cfg.get('bsa_columns', {})  #
    hvg_cols = pipeline_cfg.get('hvg_columns', {})  #
    homology_cols = pipeline_cfg.get('homology_columns', {})  #
    sel_criteria_s_to_b = pipeline_cfg.get('selection_criteria_source_to_bridge', {})  #
    sel_criteria_b_to_t = pipeline_cfg.get('selection_criteria_bridge_to_target', {})  #
    common_hvg_log2fc_thresh = pipeline_cfg.get('common_hvg_log2fc_threshold', 1.0)  #
    bridge_species_name = pipeline_cfg.get('bridge_species_name', "Arabidopsis_thaliana")  #

    # --- 1. 加载Excel数据和同源数据 ---
    _log_status(_("步骤1: 加载表格数据..."), "INFO")  #
    try:
        # 检查输出sheet是否已存在
        try:
            excel_reader_check = pd.ExcelFile(input_excel, engine='openpyxl')  #
            if output_sheet_name in excel_reader_check.sheet_names:  #
                _log_status(_("错误: 输出工作表 '{}' 已存在于 '{}'。为避免覆盖，处理终止。").format(output_sheet_name,  #
                                                                                                 input_excel),
                            "ERROR");  #
                return False  #
        except FileNotFoundError:  #
            _log_status(_("错误: 输入Excel文件 '{}' 未找到。").format(input_excel), "ERROR");  #
            return False  #
        except Exception:  #
            pass  # 其他错误，让下面的 read_excel 捕获 #

        all_sheets_data = pd.read_excel(input_excel, sheet_name=None, engine='openpyxl')  #
        if bsa_sheet_name not in all_sheets_data: _log_status(  #
            _("错误: BSA工作表 '{}' 未在 '{}' 中找到。").format(bsa_sheet_name, input_excel), "ERROR"); return False  #
        bsa_df = all_sheets_data[bsa_sheet_name].copy()  #
        if hvg_sheet_name not in all_sheets_data: _log_status(  #
            _("错误: HVG工作表 '{}' 未在 '{}' 中找到。").format(hvg_sheet_name, input_excel), "ERROR"); return False  #
        hvg_df = all_sheets_data[hvg_sheet_name].copy()  #

        s_to_b_homology_df, b_to_t_homology_df = None, None  #
        if bsa_assembly_id != hvg_assembly_id:  #
            homology_files_cfg = pipeline_cfg.get('homology_files', {})  #
            homology_bsa_to_bridge_csv_path = homology_files_cfg.get('bsa_to_bridge_csv')  #
            homology_bridge_to_hvg_csv_path = homology_files_cfg.get('bridge_to_hvg_csv')  #
            if not all([homology_bsa_to_bridge_csv_path, homology_bridge_to_hvg_csv_path]):  #
                _log_status(_("错误: 版本不同但同源文件路径配置不完整。"), "ERROR");  #
                return False  #
            if not os.path.exists(homology_bsa_to_bridge_csv_path): _log_status(  #
                _("错误: 源->桥梁同源文件 '{}' 不存在。").format(homology_bsa_to_bridge_csv_path),
                "ERROR"); return False  #
            if not os.path.exists(homology_bridge_to_hvg_csv_path): _log_status(  #
                _("错误: 桥梁->目标同源文件 '{}' 不存在。").format(homology_bridge_to_hvg_csv_path),  #
                "ERROR"); return False  #
            s_to_b_homology_df = pd.read_csv(homology_bsa_to_bridge_csv_path)  #
            b_to_t_homology_df = pd.read_csv(homology_bridge_to_hvg_csv_path)  #
            _log_status(_("同源数据CSV加载成功。"))  #
    except Exception as e:  #
        _log_status(_("加载数据时发生错误: {}").format(e), "ERROR");  #
        return False  #
    _log_progress(10, _("输入数据加载完毕。"))  #

    # --- 2. 准备GFF数据库 ---
    _log_status(_("步骤2: 准备GFF数据库..."), "INFO")  #
    if gff_db_dir and not os.path.exists(gff_db_dir):  #
        try:
            os.makedirs(gff_db_dir);  #
            _log_status(f"Created GFF DB directory: {gff_db_dir}")  #
        except OSError as e:  #
            _log_status(f"Error creating GFF DB directory {gff_db_dir}: {e}", "ERROR");  #
            return False  #

    if not os.path.exists(gff_file_path_bsa_assembly): _log_status(  #
        _("错误: 源GFF文件 '{}' 未找到。").format(gff_file_path_bsa_assembly), "ERROR"); return False  #
    db_A_path = os.path.join(gff_db_dir,  #
                             os.path.basename(gff_file_path_bsa_assembly) + DB_SUFFIX) if gff_db_dir else None  #
    gff_A_db = create_or_load_gff_db(gff_file_path_bsa_assembly, db_path=db_A_path, force_create=force_gff_db_creation,
                                     #
                                     verbose=False)  # verbose=False让它少打印 #
    if not gff_A_db: _log_status(_("错误: 创建/加载源基因组 {} 的GFF数据库失败。").format(bsa_assembly_id),  #
                                 "ERROR"); return False  #

    gff_B_db = gff_A_db  #
    if bsa_assembly_id != hvg_assembly_id:  #
        if not os.path.exists(gff_file_path_hvg_assembly): _log_status(  #
            _("错误: 目标GFF文件 '{}' 未找到。").format(gff_file_path_hvg_assembly), "ERROR"); return False  #
        db_B_path = os.path.join(gff_db_dir,  #
                                 os.path.basename(gff_file_path_hvg_assembly) + DB_SUFFIX) if gff_db_dir else None  #
        gff_B_db = create_or_load_gff_db(gff_file_path_hvg_assembly, db_path=db_B_path,  #
                                         force_create=force_gff_db_creation, verbose=False)  #
        if not gff_B_db: _log_status(_("错误: 创建/加载目标基因组 {} 的GFF数据库失败。").format(hvg_assembly_id),  #
                                     "ERROR"); return False  #
    _log_status(_("GFF数据库准备完毕。"));  #
    _log_progress(25, _("GFF数据库就绪。"))  #

    # --- 3. 从BSA区域中提取源基因 ---
    _log_status(_("步骤3: 从BSA区域中提取源基因 (基于 {}) ...").format(bsa_assembly_id))  #
    source_genes_in_bsa_regions_data = []  #
    for bsa_idx, bsa_row in bsa_df.iterrows():  #
        try:
            # 从配置中获取列名
            chrom_val = str(bsa_row[bsa_cols.get('chr', 'chr')])  #
            start_val = int(bsa_row[bsa_cols.get('start', 'region.start')])  #
            end_val = int(bsa_row[bsa_cols.get('end', 'region.end')])  #

            bsa_row_dict_prefix = {f"bsa_{k}": v for k, v in bsa_row.items()}  #
            bsa_row_dict_prefix["bsa_original_row_index (0-based)"] = bsa_idx  #

            genes_found_this_region = 0  #
            for gene_feature_A in get_features_in_region(gff_A_db, chrom_val, start_val, end_val,
                                                         feature_type='gene'):  #
                gene_data = {"Source_Gene_ID_A": gene_feature_A.id, **bsa_row_dict_prefix}  #
                source_genes_in_bsa_regions_data.append(gene_data)  #
                genes_found_this_region += 1  #
            if genes_found_this_region == 0:  #
                source_genes_in_bsa_regions_data.append({"Source_Gene_ID_A": pd.NA, **bsa_row_dict_prefix})  #
        except Exception as e:  #
            _log_status(_("警告: 处理BSA区域 (行索引 {}) 时出错: {}").format(bsa_idx, e), "WARNING");  #
            continue  #

    source_genes_df = pd.DataFrame(source_genes_in_bsa_regions_data)  #
    if source_genes_df.empty: _log_status(_("BSA区域未提取到或关联任何基因条目。"));  # 可能仍需继续以生成空输出 #
    _log_status(_("从BSA区域共提取/关联 {} 个源基因条目。").format(len(source_genes_df)))  #
    _log_progress(40, _("源基因提取完成。"))  #

    # --- 4. 基因同源映射 ---
    genes_on_hvg_assembly_df = source_genes_df.copy()  #
    # 新增: 获取 genome_sources 以便后续获取 slicer
    genome_sources = {}
    if 'downloader' in config and 'genome_sources_file' in config['downloader']:
        # This import is here to avoid circular dependency if config.loader imports pipelines
        from cotton_toolkit.config.loader import get_genome_data_sources as get_gs_func
        genome_sources = get_gs_func(config) or {}

    bsa_source_config = genome_sources.get(bsa_assembly_id, {})
    bsa_homology_id_slicer = bsa_source_config.get('homology_id_slicer')
    # For bridge to target, assuming target (HVG) assembly might also have a slicer defined
    hvg_source_config = genome_sources.get(hvg_assembly_id, {})
    bridge_to_hvg_slicer = hvg_source_config.get('homology_id_slicer')

    if bsa_assembly_id != hvg_assembly_id:  #
        _log_status(_("\n步骤4: 执行基因同源映射 ({} -> {} -> {})...").format(bsa_assembly_id, bridge_species_name,  #
                                                                              hvg_assembly_id))  #
        valid_source_for_map_df = source_genes_df.dropna(subset=["Source_Gene_ID_A"])  #
        if not valid_source_for_map_df.empty and s_to_b_homology_df is not None and b_to_t_homology_df is not None:  #
            unique_source_gene_ids_A = valid_source_for_map_df["Source_Gene_ID_A"].unique().tolist()  #

            # ----------- 调用更新后的映射函数 (假设 map_genes_via_bridge 已更新) ------------
            mapped_df, fuzzy_count = map_genes_via_bridge(  #
                source_gene_ids=unique_source_gene_ids_A, source_assembly_name=bsa_assembly_id,  #
                target_assembly_name=hvg_assembly_id,  #
                bridge_species_name=bridge_species_name, source_to_bridge_homology_df=s_to_b_homology_df,  #
                bridge_to_target_homology_df=b_to_t_homology_df,  #
                s_to_b_query_col=homology_cols.get('query', "Query"),  #
                s_to_b_match_col=homology_cols.get('match', "Match"),  #
                b_to_t_query_col=homology_cols.get('query', "Query"),  #
                b_to_t_match_col=homology_cols.get('match', "Match"),  #
                evalue_col=homology_cols.get('evalue', "Exp"), score_col=homology_cols.get('score', "Score"),  #
                pid_col=homology_cols.get('pid', "PID"),  #
                selection_criteria_s_to_b=sel_criteria_s_to_b, selection_criteria_b_to_t=sel_criteria_b_to_t,  #
                source_id_slicer=bsa_homology_id_slicer,  # 传递slicer
                bridge_id_slicer=bridge_to_hvg_slicer  # Slicer for bridge IDs if they also need truncation
            )
            # ----------------------------------------------

            if fuzzy_count > 0:
                _log_status(_("注意: 在同源映射中执行了 {} 次模糊匹配。详情请见输出文件的 '{}' 列。").format(fuzzy_count,
                                                                                                           MATCH_NOTE_COL_NAME),
                            "WARNING")

            if not mapped_df.empty:  #
                genes_on_hvg_assembly_df = pd.merge(source_genes_df, mapped_df, on="Source_Gene_ID_A", how="left")  #
                genes_on_hvg_assembly_df.rename(columns={"Target_Gene_ID_B": "gene_id_on_hvg_assembly"},
                                                inplace=True)  #
            else:  #
                genes_on_hvg_assembly_df["gene_id_on_hvg_assembly"] = pd.NA  #
                genes_on_hvg_assembly_df[MATCH_NOTE_COL_NAME] = _("无有效同源映射")  # Default note for no map
        else:  #
            genes_on_hvg_assembly_df["gene_id_on_hvg_assembly"] = pd.NA  #
            genes_on_hvg_assembly_df[MATCH_NOTE_COL_NAME] = _("无有效同源映射或数据不足")  # Default note

    else:  #
        _log_status(_("\n步骤4: BSA和HVG基因组版本相同 ('{}')，跳过映射。").format(bsa_assembly_id))  #
        genes_on_hvg_assembly_df.rename(columns={"Source_Gene_ID_A": "gene_id_on_hvg_assembly"}, inplace=True)  #
        genes_on_hvg_assembly_df[MATCH_NOTE_COL_NAME] = _("无需映射 (版本相同)")  # Default note for same assembly

    if "gene_id_on_hvg_assembly" not in genes_on_hvg_assembly_df.columns: genes_on_hvg_assembly_df[  #
        "gene_id_on_hvg_assembly"] = pd.NA  #

    if bsa_assembly_id == hvg_assembly_id:  # 添加空列 #
        homology_info_cols = ["Bridge_Gene_ID_Ath", "Bridge_Species", "Target_Assembly",  #
                              f"S_to_B_{homology_cols.get('score', 'Score')}",  #
                              f"S_to_B_{homology_cols.get('evalue', 'Exp')}",  #
                              f"S_to_B_{homology_cols.get('pid', 'PID')}",  #
                              f"B_to_T_{homology_cols.get('score', 'Score')}",  #
                              f"B_to_T_{homology_cols.get('evalue', 'Exp')}",  #
                              f"B_to_T_{homology_cols.get('pid', 'PID')}"]  #
        for col in homology_info_cols:  #
            if col not in genes_on_hvg_assembly_df.columns: genes_on_hvg_assembly_df[col] = pd.NA  #
        genes_on_hvg_assembly_df["Target_Assembly"] = hvg_assembly_id  # 即使相同也标记 #

    _log_status(_("获得 {} 个与BSA关联基因条目(映射后/无需映射)。").format(len(genes_on_hvg_assembly_df)))  #
    _log_progress(60, _("基因映射完成。"))  #

    # --- 5. 与HVG列表交集 ---
    _log_status(_("\n步骤5: 与HVG列表进行交集..."))  #
    hvg_df[hvg_cols.get('gene_id', 'gene_id')] = hvg_df[hvg_cols.get('gene_id', 'gene_id')].astype(str)  #
    genes_on_hvg_assembly_df["gene_id_on_hvg_assembly"] = genes_on_hvg_assembly_df["gene_id_on_hvg_assembly"].astype(  #
        object).where(  #
        genes_on_hvg_assembly_df["gene_id_on_hvg_assembly"].notna(), pd.NA).astype(str).replace('<NA>', pd.NA)  #

    mergable_df = genes_on_hvg_assembly_df.dropna(subset=["gene_id_on_hvg_assembly"])  #
    if not mergable_df.empty:  #
        # 如果 gene_id_on_hvg_assembly 可能有重复 (因为一个BSA区域可能映射到多个同源基因，而这些同源基因是同一个)
        # 在合并前去重，或者确保合并的键是唯一的组合
        intersected_df = pd.merge(mergable_df, hvg_df, left_on="gene_id_on_hvg_assembly",  #
                                  right_on=hvg_cols.get('gene_id', 'gene_id'), how="inner")  #
    else:  #
        intersected_df = pd.DataFrame()  #

    if intersected_df.empty:  #
        _log_status(_("与HVG列表取交集后，未找到任何候选基因。"))  #
        output_df_final = genes_on_hvg_assembly_df  #
        if REASONING_COL_NAME not in output_df_final.columns: output_df_final[REASONING_COL_NAME] = _(  #
            "无HVG交集或映射失败")  #
        # 为HVG表的列名添加空列，以保持输出结构一致性
        for hvg_col_key in hvg_cols.values():  # 使用配置中的HVG列名 #
            if hvg_col_key not in output_df_final.columns: output_df_final[hvg_col_key] = pd.NA  #
    else:  #
        _log_status(_("与HVG列表交集后，初步筛选出 {} 个候选基因条目。").format(len(intersected_df)))  #
        # 合并回所有BSA/映射条目，没有HVG匹配的行，其HVG列和推理列将为NA/特定值
        # 确保合并键能唯一识别行，避免行数爆炸
        # 使用 genes_on_hvg_assembly_df 的所有列作为左键的基础，避免重复
        merge_cols = list(genes_on_hvg_assembly_df.columns)
        if 'gene_id' in intersected_df.columns and 'gene_id' not in merge_cols:  # hvg_cols.get('gene_id') may be 'gene_id'
            intersected_df_for_merge = intersected_df.drop(columns=['gene_id'])
        else:
            intersected_df_for_merge = intersected_df

        output_df_final = pd.merge(genes_on_hvg_assembly_df, intersected_df_for_merge,  #
                                   on=list(
                                       genes_on_hvg_assembly_df.columns.intersection(intersected_df_for_merge.columns)),
                                   #
                                   how="left", suffixes=('', '_DROP_HVG'))  #
        cols_to_drop = [col for col in output_df_final.columns if '_DROP_HVG' in col]  #
        output_df_final.drop(columns=cols_to_drop, inplace=True)  #

        # --- 6. 应用“Ms1功能缺失”推理 ---
        _log_status(_("\n步骤6: 应用“Ms1功能缺失”推理逻辑..."))  #
        reasoning_list = []  #
        hvg_cat_col_name = hvg_cols.get('category', 'hvg_category')  #
        hvg_lfc_col_name = hvg_cols.get('log2fc', 'log2fc_WT_vs_Ms1')  #
        for _, row in output_df_final.iterrows():  #
            reasoning = _("无HVG匹配或数据不足")  #
            if pd.notna(row.get(hvg_cat_col_name)) and pd.notna(row.get(hvg_lfc_col_name)):  #
                category = row[hvg_cat_col_name];  #
                log2fc = row[hvg_lfc_col_name];  #
                reasoning = _("不确定")  #
                if category == "WT特有TopHVG":  #
                    if log2fc > 0:  #
                        reasoning = _("高优先级 (WT高表达/高变异，Ms1中显著下降/均一)")  #
                    else:  #
                        reasoning = _("中低优先级 (WT高变异，Ms1中表达未降或上升/均一)")  #
                elif category == "Ms1特有TopHVG":  #
                    if log2fc < 0:  #
                        reasoning = _("中高优先级 (Ms1高表达/高变异，WT中低表达/均一，或失控)")  #
                    else:  #
                        reasoning = _("中低优先级 (Ms1高变异，但WT中表达未显著更低)")  #
                elif category == "共同TopHVG":  #
                    if abs(log2fc) > common_hvg_log2fc_thresh:  #
                        if log2fc > 0:  #
                            reasoning = _("高优先级 (共同高变异，Ms1中平均表达显著更低)")  #
                        else:  #
                            reasoning = _("中高优先级 (共同高变异，Ms1中平均表达显著更高，或失抑制)")  #
                    else:  #
                        reasoning = _("一般关注 (共同高变异，但平均表达差异不大)")  #
            reasoning_list.append(reasoning)  #
        output_df_final[REASONING_COL_NAME] = reasoning_list  #
    _log_progress(75, _("与HVG列表交集及推理完成。"))  #

    # --- 7. (可选的GFF详细信息提取，如果需要，从gff_B_db提取) ---
    # ... (此部分逻辑保持不变) ...

    # --- 8. 整理并输出结果到Excel新Sheet ---
    _log_status(_("\n步骤7: 准备并写入最终结果..."))  # 注意步骤号可能因可选步骤而变 #
    if not output_df_final.empty:  #
        # 整理列顺序
        final_cols_order = [  #
            'Result_Index (1-based)',
            'gene_id_on_hvg_assembly',
            REASONING_COL_NAME,  #
            MATCH_NOTE_COL_NAME,  # 确保备注列在前面
            hvg_cols.get('category', 'hvg_category'),  #
            hvg_cols.get('log2fc', 'log2fc_WT_vs_Ms1')  #
        ]
        # 添加BSA原始列 (以'bsa_'为前缀的列)
        final_cols_order.extend(sorted([col for col in output_df_final.columns if col.startswith('bsa_')]))  #
        # 添加源基因A的信息
        final_cols_order.extend(sorted(  #
            [col for col in output_df_final.columns if
             col.startswith('Source_Gene_') and col not in final_cols_order]))  #
        # 添加桥梁和目标映射的信息
        final_cols_order.extend(sorted([col for col in output_df_final.columns if col.startswith(  #
            ('Bridge_', 'Target_', 'S_to_B_', 'B_to_T_')) and col not in final_cols_order]))  #
        # 添加HVG表中的其他列 (除了已在key_cols_front中的)
        other_hvg_cols_to_add = [col for col in hvg_df.columns if  #
                                 col in output_df_final.columns and col not in final_cols_order and col != hvg_cols.get(
                                     #
                                     'gene_id', 'gene_id')]  #
        final_cols_order.extend(sorted(other_hvg_cols_to_add))  #

        # 确保所有期望的列都存在于 output_df_final 中才进行重排
        existing_final_cols = [col for col in final_cols_order if col in output_df_final.columns]  #
        # 添加所有剩余的列，确保没有遗漏
        existing_final_cols.extend(sorted([col for col in output_df_final.columns if col not in existing_final_cols]))

        output_df_final = output_df_final[existing_final_cols]  #
        output_df_final.insert(0, 'Result_Index (1-based)', range(1, len(output_df_final) + 1))  #

    all_sheets_data[output_sheet_name] = output_df_final  #

    try:
        with pd.ExcelWriter(input_excel, engine='openpyxl') as writer:  # input_excel from params #
            for sheetname, df_data_loop_write in all_sheets_data.items():  #
                df_data_loop_write.to_excel(writer, sheet_name=sheetname, index=False)  #
        _log_status(_("整合分析结果已成功写入文件 '{}' 的新工作表 '{}'。").format(input_excel, output_sheet_name))  #
        _log_status(_("原始文件中的其他sheet内容保持不变。"))  #
        _log_progress(100, _("流程成功结束!"))  #

        result_from_your_function = True  # 替换为您的函数实际的返回值 #
        overall_success = result_from_your_function  #

    except Exception as e_final_write:  #
        _log_status(_("将最终结果写回Excel文件时发生错误: {}").format(e_final_write), "ERROR")  #
        overall_success = False  #

    finally:
        if task_done_callback:  #
            task_done_callback(overall_success)  #

    return overall_success  #


# --- `if __name__ == '__main__':` 测试模块 (与之前回复中用于测试的示例类似) ---
# --- 它将创建模拟文件，并使用上面定义的（可能仍然是MOCK的）核心函数来测试 integrate_bsa_with_hvg ---
if __name__ == '__main__':  #
    import builtins  # type: ignore #

    if not hasattr(builtins, '_'):  # type: ignore #
        def _(text): return text  #


        builtins._ = _  # type: ignore #
    import shutil  # 确保导入 #

    # 设置测试语言 (如果您的i18n已配置好)
    # setup_pipeline_i18n(language_code='zh_CN')
    # setup_pipeline_i18n(language_code='en') # 在函数内定义了，这里不需要重复

    print(_("--- 开始运行整合流程测试 (使用真实函数签名，若导入失败则用MOCK) ---"))  #

    test_dir = "pipeline_integration_test_data_v2"  # 改名以防冲突 #
    if os.path.exists(test_dir): shutil.rmtree(test_dir)  #
    os.makedirs(test_dir, exist_ok=True)  #

    test_excel_file = os.path.join(test_dir, "integration_input_v2.xlsx")  #
    bsa_sheet = "BSA_棉花A_v2"  #
    hvg_sheet = "HVG_棉花B_v2"  #
    output_sheet = "Combined_Analysis_Output_v2"  #
    if os.path.exists(test_excel_file): os.remove(test_excel_file)  #

    gff_A_path = os.path.join(test_dir, "cottonA_test_v2.gff3")  #
    gff_B_path = os.path.join(test_dir, "cottonB_test_v2.gff3.gz")  #
    homology_A_to_At_csv = os.path.join(test_dir, "hom_A_At_test_v2.csv")  #
    homology_At_to_B_csv = os.path.join(test_dir, "hom_At_B_test_v2.csv")  #
    gff_db_test_dir = os.path.join(test_dir, "gff_databases_test_v2")  #
    os.makedirs(gff_db_test_dir, exist_ok=True)  #

    bsa_test_data = pd.DataFrame({  #
        'chr': ["Scaffold_A1", "Scaffold_A1"], 'region.start': [100, 6000],  #
        'region.end': [2500, 8500], 'bsa_score': [0.9, 0.7], 'some_other_bsa_info': ['info1', 'info2']  #
    })
    hvg_test_data = pd.DataFrame({  #
        'gene_id': ["GeneB_mapped1", "GeneB_mapped2", "GeneB_unrelated"],
        # 对应 map_genes_via_bridge 的 Target_Gene_ID_B #
        'hvg_category': ["WT特有TopHVG", "共同TopHVG", "Ms1特有TopHVG"],  #
        'log2fc_WT_vs_Ms1': [2.1, 0.5, -3.0],  #
        'hvg_extra_info': ['hvg_info1', 'hvg_info2', 'hvg_info3']  #
    })
    homology_A_to_At_data = pd.DataFrame({  #
        "Query": ["CottonA_G1", "CottonA_G1", "CottonA_G2", "CottonA_G3_NoAtMatch"],  #
        "Match": ["At_bridge1", "At_H2_no_B_match", "At_bridge1", "At_H_dummy"],  #
        "Exp": [1e-50, 1e-20, 1e-60, 1e-2], "Score": [500, 200, 600, 50], "PID": [80, 60, 85, 40]  #
    })
    homology_At_to_B_data = pd.DataFrame({  #
        "Query": ["At_bridge1", "At_bridge1", "At_H2_no_B_match"],  #
        "Match": ["GeneB_mapped1", "CottonB_Gene00X_NotHVG", "GeneB_mapped2"],  # GeneB_mapped2 会被映射 #
        "Exp": [1e-70, 1e-30, 1e-55], "Score": [700, 300, 550], "PID": [90, 70, 85]  #
    })
    with open(gff_A_path, 'w', encoding='utf-8') as f:  #
        f.write("##gff-version 3\n")  #
        f.write("Scaffold_A1\t.\tgene\t1000\t2000\t.\t+\t.\tID=CottonA_G1;Name=GeneA1_Name\n")  #
        f.write("Scaffold_A1\t.\tgene\t7000\t8000\t.\t-\t.\tID=CottonA_G3_NoAtMatch\n")  # 这个在第二个BSA区域 #
    gff_b_content = "##gff-version 3\n" + \
                    "Contig_B1\t.\tgene\t100\t1000\t.\t+\t.\tID=GeneB_mapped1;Description=MappedGene1_Desc\n" + \
                    "Contig_B1\t.\tgene\t2000\t3000\t.\t-\t.\tID=GeneB_mapped2;Description=MappedGene2_Desc\n" + \
                    "Contig_B2\t.\tgene\t500\t600\t.\t+\t.\tID=CottonB_Gene00X_NotHVG\n"  #
    with gzip.open(gff_B_path, 'wt', encoding='utf-8') as f_gz:  #
        f_gz.write(gff_b_content)  #

    with pd.ExcelWriter(test_excel_file, engine='openpyxl') as writer_excel:  #
        bsa_test_data.to_excel(writer_excel, sheet_name=bsa_sheet, index=False)  #
        hvg_test_data.to_excel(writer_excel, sheet_name=hvg_sheet, index=False)  #
    homology_A_to_At_data.to_csv(homology_A_to_At_csv, index=False)  #
    homology_At_to_B_data.to_csv(homology_At_to_B_csv, index=False)  #

    selection_criteria = {"sort_by": ["Score", "Exp", "PID"], "ascending": [False, True, False], "top_n": 1,  #
                          "evalue_threshold": 1e-10, "pid_threshold": 50.0, "score_threshold": 100.0}  #

    # 准备config字典，模拟从YAML加载
    test_config = {  #
        "integration_pipeline": {  #
            "input_excel_path": test_excel_file,  # 会被下面的override覆盖 #
            "bsa_sheet_name": bsa_sheet,  #
            "hvg_sheet_name": hvg_sheet,  #
            "output_sheet_name": output_sheet,  # 会被下面的override覆盖 #
            "bsa_assembly_id": "CottonA_Test_v2",  #
            "hvg_assembly_id": "CottonB_Test_v2",  #
            "gff_files": {  #
                "CottonA_Test_v2": gff_A_path,  #
                "CottonB_Test_v2": gff_B_path  #
            },
            "homology_files": {  #
                "bsa_to_bridge_csv": homology_A_to_At_csv,  #
                "bridge_to_hvg_csv": homology_At_to_B_csv  #
            },
            "bridge_species_name": "Arabidopsis_thaliana",  #
            "gff_db_storage_dir": gff_db_test_dir,  #
            "force_gff_db_creation": True,  #
            "bsa_columns": {'chr': 'chr', 'start': 'region.start', 'end': 'region.end'},  #
            "hvg_columns": {'gene_id': 'gene_id', 'category': 'hvg_category', 'log2fc': 'log2fc_WT_vs_Ms1'},  #
            "homology_columns": {'query': "Query", 'match': "Match", 'evalue': "Exp", 'score': "Score", 'pid': "PID"},
            #
            "selection_criteria_source_to_bridge": selection_criteria,  #
            "selection_criteria_bridge_to_target": selection_criteria,  #
            "common_hvg_significant_log2fc_threshold": 1.0  #
        },
        "downloader": {  # 为 get_genome_data_sources 准备一些东西 #
            "download_output_base_dir": "dummy_download_dir_pipeline_test",  #
            # 新增: 模拟 genome_sources_file 以便测试 slicer 读取
            "genome_sources_file": "dummy_genome_sources.yml"
        },
        # 新增: 模拟主配置文件中的 _config_file_abs_path_
        "_config_file_abs_path_": os.path.abspath(os.path.join(test_dir, "dummy_config.yml"))
    }
    # 创建一个虚拟的 genome_sources.yml 以测试 slicer 的读取
    dummy_gs_path = os.path.join(test_dir, "dummy_genome_sources.yml")
    with open(dummy_gs_path, 'w') as f_gs:
        f_gs.write("""
genome_sources:
  CottonA_Test_v2:
    species_name: "Cotton A Test v2"
    homology_id_slicer: "_" 
  CottonB_Test_v2:
    species_name: "Cotton B Test v2"
    homology_id_slicer: "_"
""")
    # 创建一个虚拟的 config.yml 文件的绝对路径，用于 get_gs_func
    with open(os.path.join(test_dir, "dummy_config.yml"), 'w') as f_dummy_cfg:
        f_dummy_cfg.write("downloader:\n  genome_sources_file: dummy_genome_sources.yml")

    print("\n--- 调用 integrate_bsa_with_hvg (使用真实函数签名) ---")  #
    success = integrate_bsa_with_hvg(  #
        config=test_config,  # 传递整个config对象 #
        # input_excel_path_override=test_excel_file, # 这些现在从config中获取，除非CLI覆盖
        # output_sheet_name_override=output_sheet
    )

    if success:  #
        print(f"\n--- 测试流程成功完成。结果已写入 '{test_excel_file}' 的 '{output_sheet}' 工作表。---")  #
        try:
            results_check_df = pd.read_excel(test_excel_file, sheet_name=output_sheet, engine='openpyxl')  #
            print("输出结果预览 (来自Excel):")  #
            print(results_check_df.to_string())  #
            assert not results_check_df.empty, "结果不应为空"  #
            assert "GeneB_mapped1" in results_check_df["gene_id_on_hvg_assembly"].values  #
            assert "GeneB_mapped2" in results_check_df["gene_id_on_hvg_assembly"].values  #
            # 检查 CottonB_Gene001 的推理
            reasoning_g1 = \
                results_check_df[results_check_df["gene_id_on_hvg_assembly"] == "GeneB_mapped1"][  #
                    REASONING_COL_NAME].iloc[0]  #
            assert reasoning_g1 == _("高优先级 (WT高表达/高变异，Ms1中显著下降/均一)"), f"推理不匹配: {reasoning_g1}"  #
            # 检查 CottonB_Gene002 的推理 (log2fc=0.5，不显著)
            reasoning_g2 = \
                results_check_df[results_check_df["gene_id_on_hvg_assembly"] == "GeneB_mapped2"][  #
                    REASONING_COL_NAME].iloc[0]  #
            assert reasoning_g2 == _("一般关注 (共同高变异，但平均表达差异不大)"), f"推理不匹配: {reasoning_g2}"  #
            print("基本断言通过。")  #
        except Exception as e_check:  #
            print(f"检查输出Excel时出错: {e_check}")  #
    else:  #
        print("\n--- 测试流程中发生错误或未产生预期的输出。---")  #

    # 清理
    # if os.path.exists(test_dir): shutil.rmtree(test_dir)
    # print(f"\n测试目录 {test_dir} 已保留。")
