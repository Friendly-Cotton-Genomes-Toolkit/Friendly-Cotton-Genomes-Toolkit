# cotton_toolkit/utils/gene_utils.py

import re
import threading
import logging
import pandas as pd
from typing import List, Union, Optional, Tuple, Any, Callable

from ui.utils.gui_helpers import _

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

    Args:
        gene_id (str): 基因ID字符串。

    Returns:
        Optional[Tuple[str, str]]: 一个包含(亚组, 染色体号)的元组，
                                   例如 ('D', '13')。如果找不到则返回 None。
    """
    if not isinstance(gene_id, str):
        return None

    # 一个更通用的正则表达式，能捕获多种格式 (Ghir_A01G..., Gh_D13G..., Gohir.A05...)
    # 它捕获:
    #   - 分组1 ([AD]): 亚组字母 'A' 或 'D'
    #   - 分组2 (\d{2}): 两位数的染色体编号
    match = re.search(r'[_.\s]([AD])(\d{2})G', gene_id, re.IGNORECASE)

    if match:
        subgenome = match.group(1).upper()
        chromosome = match.group(2)
        return (subgenome, chromosome)

    # 为 ZJU 的格式 GH_A01G... 做一个备用匹配
    match = re.search(r'^GH_([AD])(\d{2})G', gene_id, re.IGNORECASE)
    if match:
        subgenome = match.group(1).upper()
        chromosome = match.group(2)
        return (subgenome, chromosome)

    return None


def normalize_gene_ids(gene_ids: pd.Series, pattern: str) -> pd.Series:
    """
    【修正版】使用正则表达式从基因ID中提取标准部分。
    此版本经过加固，即使正则表达式包含多个捕获组，也能稳定地只返回第一列结果。
    """
    try:
        # --- 这是核心修改 ---
        # 1. expand=True 确保 str.extract 的返回结果永远是一个DataFrame。
        # 2. .iloc[:, 0] 明确选取这个DataFrame的第一列。
        # 这样，无论用户在YAML中定义的pattern有多少个括号，函数都能稳定返回一个Series。
        return gene_ids.str.extract(f"({pattern})", expand=True).iloc[:, 0]
        # --- 修改结束 ---
    except Exception as e:
        # 如果模式无效或出现其他错误，打印警告并返回原始数据
        logger.warning(_("Warning: Failed to apply regex for gene ID normalization. Reason: {}").format(e))
        return gene_ids

def map_transcripts_to_genes(gene_ids: List[str]) -> List[str]:
    """
    将转录本ID列表合并为其父基因ID列表。
    例如：['GENE.1', 'GENE.2', 'OTHERGENE'] -> ['GENE', 'OTHERGENE']
    规则：去除点、破折号或下划线后面的 't' 或 'T' 及数字后缀。
    """
    # 正则表达式：匹配. or - or _，可选的't'或'T'，以及结尾的一个或多个数字
    pattern = re.compile(r'[\._-][Tt]?\d+$')
    # 使用集合来自动处理合并后的重复基因ID
    unique_genes = {pattern.sub('', gid) for gid in gene_ids}
    return sorted(list(unique_genes))


def parse_region_string(region_str: str) -> Optional[Tuple[str, int, int]]:
    """
    【新增工具函数】解析灵活格式的区域字符串。
    支持 'Chr:Start-End' 或 'Chr:Start..End' 格式。

    :param region_str: 用户输入的区域字符串。
    :return: 一个包含 (染色体, 开始位置, 结束位置) 的元组，如果格式不正确则返回 None。
    """
    if not isinstance(region_str, str):
        return None

    # 将 '..' 替换为 '-' 以统一格式
    normalized_str = region_str.replace('..', '-')

    # 使用正则表达式匹配 "染色体:开始-结束"
    match = re.match(r'^\s*([^:]+?)\s*:\s*(\d+)\s*-\s*(\d+)\s*$', normalized_str)

    if match:
        chrom = match.group(1).strip()
        start = int(match.group(2))
        end = int(match.group(3))

        # 保证 start <= end
        if start > end:
            start, end = end, start

        return chrom, start, end

    return None


def identify_genome_from_gene_ids(
        gene_ids: list[str],
        genome_sources: dict[str, Any],
        status_callback: Optional[Callable[[str, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[Tuple[str, Optional[str], float]]:
    """
    通过基因ID列表识别最可能的基因组版本。
    返回值现在是一个包含(ID, 警告信息, 置信度分数)的元组。
    """
    # ... 函数前半部分代码保持不变 ...
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
