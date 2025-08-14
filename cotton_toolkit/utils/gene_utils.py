# cotton_toolkit/utils/gene_utils.py

import re
import threading
import logging
import pandas as pd
from typing import List, Union, Optional, Tuple, Any

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
        logger.debug(_(f"初步识别结果为 '{jgi_genome_id}'，正在二次校验是否也匹配 '{utx_genome_id}'..."))
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
                    logger.warning(_(f"二次校验成功：基因同样匹配 '{utx_genome_id}'。将优先选择 UTX。"))
                    best_match_id = utx_genome_id
                    ambiguity_warning = _(
                        "检测到基因ID同时匹配 'UTX_v2.1' 和 'JGI_v1.1'。\n\n"
                        "程序已自动优先选择 'UTX_v2.1'。\n\n"
                        "请您注意甄别，如果需要使用 JGI 版本，请手动从下拉菜单中选择。"
                    )
            except re.error as e:
                logger.warning(_(f"用于二次校验的 '{utx_genome_id}' 正则表达式无效: {e}"))

    if highest_score > 50:
        logger.info(_("最终自动识别基因为 '{}'，置信度: {:.2f}%.").format(best_match_id, highest_score))
        return (best_match_id, ambiguity_warning, highest_score)
    else:
        logger.info(_("无法根据输入的基因ID可靠地自动识别基因组 (最高匹配度未超过50%阈值)。"))
        return None