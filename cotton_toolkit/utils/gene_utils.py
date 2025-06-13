# cotton_toolkit/utils/gene_utils.py

import re
from typing import Optional, Tuple


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