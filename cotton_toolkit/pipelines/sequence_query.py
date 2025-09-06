import os
import threading
import traceback
from typing import Optional, List, Dict, Callable, Union, Any

import logging

from .decorators import pipeline_task
from ..config.models import MainConfig
from ..core.data_access import get_sequences_for_gene_ids
from ..utils.gene_utils import resolve_gene_ids

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines.sequence_query")


@pipeline_task(_("序列提取"))
def run_sequence_extraction(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str],
        sequence_type: str = 'cds',
        output_path: Optional[str] = None,
        **kwargs
) -> Optional[Union[Dict[str, str], str]]:
    """
    从数据库中提取一个或多个基因/转录本的CDS或蛋白质序列。

    - 如果提供了 output_path (多基因模式)，则将结果保存为FASTA文件。
    - 如果未提供 output_path (单基因模式)，则返回一个包含序列的字典。
    """

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    progress(5, _("正在解析基因/转录本ID..."))
    try:
        resolved_gene_ids = resolve_gene_ids(config, assembly_id, gene_ids,'Gene','predicted_cds')
        if not resolved_gene_ids:
            raise ValueError(_("输入错误: 解析后未发现任何有效的基因ID。请检查您的输入。"))

        logger.info(_("基因ID解析完成，共 {} 个有效ID。").format(len(resolved_gene_ids)))
    except (ValueError, FileNotFoundError) as e:
        logger.error(_("基因ID解析失败: {}").format(e))
        raise e

    if check_cancel(): return None

    progress(10, _("正在从数据库提取基因序列..."))
    fasta_str, not_found_genes = get_sequences_for_gene_ids(
        config, assembly_id, resolved_gene_ids, sequence_type=sequence_type
    )

    if check_cancel(): return None

    if not fasta_str:
        error_message = _("未能获取任何查询序列，任务终止。")
        if not_found_genes:
            error_message += "\n" + _("未找到序列的基因列表: {}").format(", ".join(not_found_genes))
        raise FileNotFoundError(error_message)

    if not_found_genes:
        logger.warning(
            _("以下 {} 个基因未找到序列，将被忽略: {}").format(len(not_found_genes), ", ".join(not_found_genes)))

    progress(80, _("序列提取完成，正在整理输出..."))

    # --- 将FASTA字符串解析为字典 ---
    sequences_dict = {}
    if fasta_str:
        current_id = None
        for line in fasta_str.strip().split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith('>'):
                current_id = line[1:]
                sequences_dict[current_id] = []
            elif current_id:
                sequences_dict[current_id].append(line)

        for gene_id, seq_parts in sequences_dict.items():
            sequences_dict[gene_id] = "".join(seq_parts)

    if not output_path:
        # 单基因/GUI模式:
        logger.info(_("成功为查询ID提取了 {} 条序列。").format(len(sequences_dict)))
        return sequences_dict
    else:
        # 多基因/文件输出模式:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for gene_id, sequence in sequences_dict.items():
                    f.write(f">{gene_id}\n")
                    # 按80个字符换行
                    for i in range(0, len(sequence), 80):
                        f.write(sequence[i:i + 80] + "\n")

            success_msg = _("序列已成功保存到: {}").format(output_path)
            logger.info(success_msg)
            return success_msg
        except Exception as e:
            err_msg = _("保存FASTA文件失败: {}").format(e)
            logger.error(err_msg)
            raise IOError(err_msg)