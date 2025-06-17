import re
from typing import Any, Optional, Callable


def identify_genome_from_gene_ids(
        gene_ids: list[str],
        genome_sources: dict[str, Any],
        status_callback: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    通过基因ID列表识别最可能的基因组版本。
    【已增强】增加详细的匹配分数日志，并能检测和警告混合基因组输入。
    """
    if not gene_ids or not genome_sources:
        return None

    log = status_callback if status_callback else print

    gene_ids_to_check = [
        gid for gid in gene_ids
        if gid and not gid.lower().startswith(('scaffold', 'unknown', 'chr'))
    ]

    if not gene_ids_to_check:
        log("DEBUG: 过滤后没有用于识别的有效基因ID。", "DEBUG")
        return None

    scores = {}
    total_valid_ids = len(gene_ids_to_check)

    # 1. 计算每个基因组的匹配分数
    for assembly_id, source_info in genome_sources.items():
        # 兼容处理字典和对象
        if isinstance(source_info, dict):
            regex_pattern = source_info.get('gene_id_regex')
        else:
            regex_pattern = getattr(source_info, 'gene_id_regex', None)

        if not regex_pattern:
            continue

        try:
            # 使用 re.IGNORECASE 使匹配不区分大小写，增加灵活性
            regex = re.compile(regex_pattern, re.IGNORECASE)
            match_count = sum(1 for gene_id in gene_ids_to_check if regex.match(gene_id))

            if match_count > 0:
                score = (match_count / total_valid_ids) * 100
                scores[assembly_id] = score
        except re.error as e:
            log(f"警告: 基因组 '{assembly_id}' 的正则表达式无效: {e}", "WARNING")
            continue

    if not scores:
        log("INFO: 无法根据输入的基因ID可靠地自动识别基因组 (没有任何基因组的正则表达式匹配到输入ID)。")
        return None

    # 2. 对分数进行排序和分析
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    # 【新功能】打印详细的诊断日志
    log("DEBUG: 基因组自动识别诊断分数:", "DEBUG")
    for assembly_id, score in sorted_scores:
        log(f"  - {assembly_id}: {score:.2f}%", "DEBUG")

    best_match_id, highest_score = sorted_scores[0]

    # 3. 【新功能】检查是否存在混合输入
    # 找出所有匹配度超过10%的“显著匹配”项
    significant_matches = [s for s in sorted_scores if s[1] > 10.0]
    if len(significant_matches) > 1:
        # 如果存在多于一个显著匹配项，则发出警告
        top_matches_str = ", ".join([f"{asm_id} ({score:.1f}%)" for asm_id, score in significant_matches[:3]])
        log(f"警告: 检测到混合的基因组ID输入。可能性较高的基因组包括: {top_matches_str}", "WARNING")

    # 4. 判断最终结果 (降低识别阈值至50%)
    if highest_score > 50:
        log(f"INFO: 自动识别基因为 '{best_match_id}'，置信度: {highest_score:.2f}%.")
        return best_match_id
    else:
        log("INFO: 无法根据输入的基因ID可靠地自动识别基因组 (最高匹配度未超过50%阈值)。")
        return None
