# File: gui_helpers.py

import re
import threading
from typing import Any, Optional, Callable, Tuple

try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


def identify_genome_from_gene_ids(
        gene_ids: list[str],
        genome_sources: dict[str, Any],
        status_callback: Optional[Callable[[str, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[Tuple[str, Optional[str], float]]:
    """
    通过基因ID列表识别最可能的基因组版本。
    【已修改】: 返回值现在是一个包含(ID, 警告信息, 置信度分数)的元组。
    """
    # ... 函数前半部分代码保持不变 ...
    if not gene_ids or not genome_sources:
        return None
    log = status_callback if status_callback else (lambda msg, level="INFO": print(f"[{level}] {msg}"))
    gene_ids_to_check = [
        gid for gid in gene_ids
        if gid and not gid.lower().startswith(('scaffold', 'unknown', 'chr'))
    ]
    if not gene_ids_to_check:
        log(_("过滤后没有用于识别的有效基因ID。"), "DEBUG")
        return None
    scores = {}
    total_valid_ids = len(gene_ids_to_check)
    for assembly_id, source_info in genome_sources.items():
        if cancel_event and cancel_event.is_set():
            log(_("基因组自动识别任务被用户取消。"), "INFO")
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
            log(_(f"基因组 '{assembly_id}' 的正则表达式无效: {e}"), "WARNING")
            continue
    if not scores:
        log(_("无法根据输入的基因ID可靠地自动识别基因组 (没有任何基因组的正则表达式匹配到输入ID)。"), "INFO")
        return None

    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    log(_("基因组自动识别诊断分数:"), "DEBUG")
    for assembly_id, score in sorted_scores:
        log(_(f"  - {assembly_id}: {score:.2f}%"), "DEBUG")

    best_match_id, highest_score = sorted_scores[0]
    ambiguity_warning = None
    jgi_genome_id = 'JGI_v1.1'
    utx_genome_id = 'UTX_v2.1'

    if best_match_id == jgi_genome_id:
        log(_(f"初步识别结果为 '{jgi_genome_id}'，正在二次校验是否也匹配 '{utx_genome_id}'..."), "DEBUG")
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
                    log(_(f"二次校验成功：基因同样匹配 '{utx_genome_id}'。将优先选择 UTX。"), "WARNING")
                    best_match_id = utx_genome_id
                    ambiguity_warning = _(
                        "检测到基因ID同时匹配 'UTX_v2.1' 和 'JGI_v1.1'。\n\n"
                        "程序已自动优先选择 'UTX_v2.1'。\n\n"
                        "请您注意甄别，如果需要使用 JGI 版本，请手动从下拉菜单中选择。"
                    )
            except re.error as e:
                log(_(f"用于二次校验的 '{utx_genome_id}' 正则表达式无效: {e}"), "WARNING")

    if highest_score > 50:
        log(_(f"最终自动识别基因为 '{best_match_id}'，置信度: {highest_score:.2f}%."), "INFO")
        return (best_match_id, ambiguity_warning, highest_score)
    else:
        log(_("无法根据输入的基因ID可靠地自动识别基因组 (最高匹配度未超过50%阈值)。"), "INFO")
        return None
