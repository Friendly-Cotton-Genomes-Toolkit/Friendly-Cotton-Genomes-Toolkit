# cotton_toolkit/utils/gene_utils.py
import os
import re
import sqlite3
import threading
import logging
from random import sample

import pandas as pd
from typing import List, Optional, Tuple, Any

from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.pipelines.blast import _, logger
from cotton_toolkit.utils.file_utils import _sanitize_table_name

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.gene_utils")

def parse_gene_id(gene_id: str) -> Optional[Tuple[str, str]]:
    """
    【全新升级】从一个棉花基因ID中解析出亚组和染色体编号。
    """
    if not isinstance(gene_id, str):
        return None

    match = re.search(r'[_.\s]([AD])(\d{2})G', gene_id, re.IGNORECASE)

    if match:
        subgenome = match.group(1).upper()
        chromosome = match.group(2)
        return (subgenome, chromosome)

    match = re.search(r'^GH_([AD])(\d{2})G', gene_id, re.IGNORECASE)
    if match:
        subgenome = match.group(1).upper()
        chromosome = match.group(2)
        return (subgenome, chromosome)

    return None


def normalize_gene_ids(gene_ids: pd.Series, pattern: str) -> pd.Series:
    """
    【修正版】使用正则表达式从基因ID中提取标准部分。
    """
    try:
        return gene_ids.str.extract(f"({pattern})", expand=True).iloc[:, 0]
    except Exception as e:
        logger.warning(_("Warning: Failed to apply regex for gene ID normalization. Reason: {}").format(e))
        return gene_ids

def map_transcripts_to_genes(gene_ids: List[str]) -> List[str]:
    """
    将转录本ID列表合并为其父基因ID列表。
    """
    pattern = re.compile(r'[\._-][Tt]?\d+$')
    unique_genes = {pattern.sub('', gid) for gid in gene_ids}
    return sorted(list(unique_genes))


def parse_region_string(region_str: str) -> Optional[Tuple[str, int, int]]:
    """
    【新增工具函数】解析灵活格式的区域字符串。
    """
    if not isinstance(region_str, str):
        return None

    normalized_str = region_str.replace('..', '-')
    match = re.match(r'^\s*([^:]+?)\s*:\s*(\d+)\s*-\s*(\d+)\s*$', normalized_str)

    if match:
        chrom = match.group(1).strip()
        start = int(match.group(2))
        end = int(match.group(3))

        if start > end:
            start, end = end, start

        return chrom, start, end

    return None


def identify_genome_from_gene_ids(
        gene_ids: list[str],
        genome_sources: dict[str, Any],
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[Tuple[str, Optional[str], float]]:
    """
    通过基因ID列表识别最可能的基因组版本。
    """
    if not gene_ids or not genome_sources:
        return None
    gene_ids_to_check = [
        gid for gid in gene_ids
        if gid and not gid.lower().startswith(('scaffold', 'unknown', 'chr'))
    ]
    if not gene_ids_to_check:
        logger.debug(_("过滤后没有用于识别的有效基因ID。"))
        return None
    scores = {}
    total_valid_ids = len(gene_ids_to_check)
    for assembly_id, source_info in genome_sources.items():
        if cancel_event and cancel_event.is_set():
            logger.info(_("基因组自动识别任务被用户取消。"))
            return None
        if isinstance(source_info, dict):
            regex_pattern = source_info.get('gene_id_regex')
        else:
            regex_pattern = getattr(source_info, 'gene_id_regex', None)
        if not regex_pattern:
            continue
        try:
            regex = re.compile(regex_pattern)
            match_count = sum(1 for gene_id in gene_ids_to_check if regex.match(gene_id))
            if match_count > 0:
                score = (match_count / total_valid_ids) * 100
                scores[assembly_id] = score
        except re.error as e:
            logger.warning(_(f"基因组 '{assembly_id}' 的正则表达式无效: {e}"))
            continue
    if not scores:
        logger.info(_("无法根据输入的基因ID可靠地自动识别基因组 (没有任何基因组的正则表达式匹配到输入ID)。"))
        return None

    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    logger.debug(_("基因组自动识别诊断分数:"))
    for assembly_id, score in sorted_scores:
        logger.debug(_(f"  - {assembly_id}: {score:.2f}%"))

    best_match_id, highest_score = sorted_scores[0]
    ambiguity_warning = None
    jgi_genome_id = 'JGI_v1.1'
    utx_genome_id = 'UTX_v2.1'

    if best_match_id == jgi_genome_id:
        logger.debug(_(f"初步识别结果为 '{jgi_genome_id}'，正在二次校验是否也匹配 '{utx_genome_id}(_v3.1)'..."))
        utx_genome_info = genome_sources.get(utx_genome_id)
        utx_regex_pattern = None
        if utx_genome_info:
            if isinstance(utx_genome_info, dict):
                utx_regex_pattern = utx_genome_info.get('gene_id_regex')
            else:
                utx_regex_pattern = getattr(utx_genome_info, 'gene_id_regex', None)
        if utx_regex_pattern:
            try:
                utx_regex = re.compile(utx_regex_pattern)
                if any(utx_regex.match(gid) for gid in gene_ids_to_check):
                    logger.warning(_(f"二次校验成功：基因同样匹配 '{utx_genome_id}(_v3.1)'。将优先选择 UTX_v2.1。"))
                    best_match_id = utx_genome_id
                    ambiguity_warning = _(
                        "检测到基因ID同时匹配 'UTX_v2.1(v3.1)' 和 'JGI_v1.1'。\n\n"
                        "程序已自动优先选择 'UTX_v2.1'。\n\n"
                        "请您注意甄别，如果需要使用 JGI 或 UTX_v3.1 版本，请手动判断或选择。"
                    )
            except re.error as e:
                logger.warning(_(f"用于二次校验的 '{utx_genome_id}(_v3.1)' 正则表达式无效: {e}"))

    if highest_score > 50:
        logger.info(_("最终自动识别基因为 '{}'，置信度: {:.2f}%.").format(best_match_id, highest_score))
        return (best_match_id, ambiguity_warning, highest_score)
    else:
        logger.info(_("无法根据输入的基因ID可靠地自动识别基因组 (最高匹配度未超过50%阈值)。"))
        return None


def _to_gene_id(an_id: str) -> str:
    """移除转录本后缀 (如 .1, .2) 返回基础基因ID"""
    return re.sub(r'\.\d+$', '', str(an_id))


def _to_transcript_id(an_id: str, suffix: str = ".1") -> str:
    """确保ID以转录本后缀结尾，默认为 .1"""
    if re.search(r'\.\d+$', str(an_id)):
        return str(an_id)  # 如果已经是转录本格式，直接返回
    return f"{an_id}{suffix}"


def _check_id_exists(cursor: sqlite3.Cursor, table_name: str, gene_id: str) -> bool:
    """在数据库表中快速检查单个ID是否存在"""
    query = f'SELECT 1 FROM "{table_name}" WHERE Gene = ? LIMIT 1'
    cursor.execute(query, (gene_id,))
    return cursor.fetchone() is not None


def resolve_gene_ids(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str]
) -> List[str]:
    """
    智能解析基因ID列表。
    自动检测用户提供的是基因还是转录本ID，并根据数据库进行校正。
    """
    if not gene_ids:
        return []

    # --- 数据库和表名准备 (与 get_sequences_for_gene_ids 类似) ---
    project_root = os.path.dirname(config.config_file_abs_path_)
    db_path = os.path.join(project_root, "genomes", "genomes.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(_("错误: 预处理数据库 'genomes.db' 未找到。"))

    genome_sources = get_genome_data_sources(config)
    genome_info = genome_sources.get(assembly_id)
    if not genome_info:
        raise ValueError(_("错误: 找不到基因组 '{}' 的配置。").format(assembly_id))

    cds_file_path = get_local_downloaded_file_path(config, genome_info, 'predicted_cds')
    table_name = _sanitize_table_name(os.path.basename(cds_file_path), version_id=genome_info.version_id)

    processing_mode = None  # 'gene' 或 'transcript'

    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if cursor.fetchone() is None:
            raise ValueError(_("错误: 在数据库中找不到表 '{}'。请先对CDS文件进行预处理。").format(table_name))

        # --- 根据ID数量选择不同逻辑 ---
        if len(gene_ids) >= 2:
            # 随机取两个样本进行探测
            samples = sample(gene_ids, 2)
            logger.debug(_("智能解析：抽取了两个样本进行探测: {}").format(samples))
            for sample_id in samples:
                # 优先尝试转录本格式
                if _check_id_exists(cursor, table_name, _to_transcript_id(sample_id)):
                    processing_mode = 'transcript'
                    logger.info(_("智能解析：探测到数据库匹配转录本ID (例如: {})。").format(_to_transcript_id(sample_id)))
                    break
                # 如果转录本失败，尝试基础基因格式
                elif _check_id_exists(cursor, table_name, _to_gene_id(sample_id)):
                    processing_mode = 'gene'
                    logger.info(_("智能解析：探测到数据库匹配基础基因ID (例如: {})。").format(_to_gene_id(sample_id)))
                    break

            if processing_mode is None:
                raise ValueError(_("错误：无法在数据库中匹配提供的基因ID样本。请检查基因组版本和ID格式是否正确。"))

        elif len(gene_ids) == 1:
            sample_id = gene_ids[0]
            logger.debug(_("智能解析：正在探测单个ID: {}").format(sample_id))
            if _check_id_exists(cursor, table_name, _to_transcript_id(sample_id)):
                processing_mode = 'transcript'
            elif _check_id_exists(cursor, table_name, _to_gene_id(sample_id)):
                processing_mode = 'gene'
            else:
                raise ValueError(_("错误：无法在数据库中匹配提供的基因ID '{}'。").format(sample_id))

    # --- 根据探测到的模式，统一处理整个列表 ---
    if processing_mode == 'transcript':
        logger.debug(_("应用 '转录本' 模式处理整个列表。"))
        return list(dict.fromkeys([_to_transcript_id(gid) for gid in gene_ids]))  # dict.fromkeys去重并保持顺序
    elif processing_mode == 'gene':
        logger.debug(_("应用 '基因' 模式处理整个列表。"))
        return list(dict.fromkeys([_to_gene_id(gid) for gid in gene_ids]))

    return gene_ids  # 如果只有一个ID且模式未定，返回原始ID


