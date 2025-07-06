# cotton_toolkit/utils/gene_utils.py

import re
import pandas as pd
from typing import List, Union, Optional, Tuple

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


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
        print(_("Warning: Failed to apply regex for gene ID normalization. Reason: {}").format(e))
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