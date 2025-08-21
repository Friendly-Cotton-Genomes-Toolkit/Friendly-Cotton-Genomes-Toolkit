
import os
import threading
import traceback
from typing import Optional, List, Dict, Callable, Union

import pandas as pd
import logging

from .decorators import pipeline_task
from ..config.models import MainConfig
from ..core.data_access import get_sequences_for_gene_ids

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines.data_query")


@pipeline_task(_("CDS序列提取"))
def run_sequence_extraction(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str],
        output_path: Optional[str] = None,
        **kwargs
) -> Optional[Union[Dict[str, str], str]]:
    """
    从数据库中提取一个或多个基因/转录本的CDS序列。

    此函数通过调用 get_sequences_for_gene_ids 来复用与其他流程相同的核心数据提取逻辑。

    - 如果提供了 output_path (多基因模式)，则将结果保存为CSV文件。
    - 如果未提供 output_path (单基因模式)，则返回一个包含序列的字典。
    """

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    # 步骤 1: 调用可复用的核心函数获取序列
    # 这与 run_homology_mapping 的第一步完全相同
    progress(10, _("正在从数据库提取基因序列..."))
    fasta_str, not_found_genes = get_sequences_for_gene_ids(config, assembly_id, gene_ids)

    if check_cancel(): return None

    if not fasta_str:
        logger.error(_("未能获取任何查询序列，任务终止。"))
        return {} if not output_path else _("未能获取任何查询序列。")

    if not_found_genes:
        logger.warning(
            _("以下 {} 个基因未找到序列，将被忽略: {}").format(len(not_found_genes), ", ".join(not_found_genes)))

    progress(80, _("序列提取完成，正在整理输出..."))

    # --- 将FASTA字符串解析为字典 ---
    sequences_dict = {}
    if fasta_str:
        current_id = None
        for line in fasta_str.strip().split('\\n'):
            if line.startswith('>'):
                current_id = line[1:].strip()
                sequences_dict[current_id] = []
            elif current_id:
                sequences_dict[current_id].append(line.strip())

        for gene_id, seq_parts in sequences_dict.items():
            sequences_dict[gene_id] = "".join(seq_parts)

    # 步骤 2: 根据模式处理输出 (这是此函数独有的部分)
    if not output_path:
        # 单基因/GUI模式: 直接返回序列字典
        logger.info(_("成功为查询ID提取了 {} 条CDS序列。").format(len(sequences_dict)))
        return sequences_dict
    else:
        # 多基因/文件输出模式: 保存为CSV
        df = pd.DataFrame(list(sequences_dict.items()), columns=['ID', 'Sequence'])
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        success_msg = _("CDS序列已成功保存到: {}").format(output_path)
        logger.info(success_msg)
        return success_msg