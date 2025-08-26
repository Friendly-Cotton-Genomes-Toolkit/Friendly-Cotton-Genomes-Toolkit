import os
import threading
from typing import List, Optional, Callable, Any, Dict
import logging
import pandas as pd
import tempfile

from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.pipelines.blast import run_blast_pipeline
from cotton_toolkit.core.data_access import get_sequences_for_gene_ids
from cotton_toolkit.pipelines.decorators import pipeline_task

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipelines.mapping")

@pipeline_task(_("同源转换"))
def run_homology_mapping(
        config: MainConfig,
        source_assembly_id: str,
        target_assembly_id: str,
        gene_ids: List[str],
        output_csv_path: Optional[str],
        criteria_overrides: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs  # 捕获其他可能的旧参数
) -> Optional[pd.DataFrame]:
    """
    【新版】通过动态BLAST执行同源基因映射。
    """

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']

    # 1. 获取源基因序列
    progress(10, _("正在从数据库提取源基因序列..."))
    logger.info(_("步骤 1/3: 正在为 {} 个基因提取序列...").format(len(gene_ids)))
    query_fasta_str, not_found_genes = get_sequences_for_gene_ids(config, source_assembly_id, gene_ids)

    if not query_fasta_str:
        error_message = _("未能获取任何查询序列，任务终止。")
        if not_found_genes:
            error_message += "\n" + _("未找到序列的基因列表: {}").format(", ".join(not_found_genes))
        raise ValueError(error_message)

    logger.debug(_("--- BLAST Query Sequence (first 1000 chars) ---\n{}\n-------------------------------------------------").format(query_fasta_str[:1000]))
    if not_found_genes:
        logger.warning(
            _("以下 {} 个基因未找到序列，将被忽略: {}").format(len(not_found_genes), ", ".join(not_found_genes)))

    # 2. 准备并执行BLAST
    progress(30, _("正在准备并执行BLASTN搜索..."))
    logger.info(_("步骤 2/3: 正在对目标基因组 '{}' 执行BLASTN...").format(target_assembly_id))

    # 从 criteria_overrides 中提取BLAST参数
    evalue = criteria_overrides.get('evalue_threshold', 1e-10)
    # top_n 对应 max_target_seqs
    max_target_seqs = criteria_overrides.get('top_n', 1)

    # 创建一个临时文件来保存BLAST结果，因为我们需要后处理
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".xlsx") as tmp_output:
        temp_output_path = tmp_output.name

    blast_result_msg = run_blast_pipeline(
        config=config,
        blast_type='blastn',  # 直接使用blastn进行核酸到核酸的比对
        target_assembly_id=target_assembly_id,
        query_file_path=None,
        query_text=query_fasta_str,
        output_path=temp_output_path,
        evalue=evalue,
        word_size=11,  # blastn 默认值
        max_target_seqs=max_target_seqs,
        progress_callback=lambda p, m: progress(30 + int(p * 0.6), m),  # 将BLAST进度映射到30%-90%
        cancel_event=cancel_event
    )

    if not blast_result_msg or "完成" not in blast_result_msg:
        logger.error(_("BLAST步骤执行失败。"))
        if os.path.exists(temp_output_path): os.remove(temp_output_path)
        return None

    # 3. 后处理与保存
    progress(90, _("正在应用后处理筛选并保存结果..."))
    logger.info(_("步骤 3/3: 正在后处理BLAST结果..."))

    results_df = pd.read_excel(temp_output_path)

    # 应用额外的筛选条件 (PID, Score等)
    pid_threshold = criteria_overrides.get('pid_threshold', 0)
    if pid_threshold > 0 and 'Identity (%)' in results_df.columns:
        results_df = results_df[results_df['Identity (%)'] >= pid_threshold]

    score_threshold = criteria_overrides.get('score_threshold', 0)
    if score_threshold > 0 and 'Bit_Score' in results_df.columns:
        results_df = results_df[results_df['Bit_Score'] >= score_threshold]

    # (可选) 应用严格模式
    # 此处可以添加严格模式的筛选逻辑，类似于旧版 homology_mapper 中的代码

    # 保存最终结果到用户指定路径
    try:
        if output_csv_path:
            logger.info(_("正在将最终结果保存到: {}").format(output_csv_path))
            if output_csv_path.lower().endswith('.csv'):
                results_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            else:
                results_df.to_excel(output_csv_path, index=False, engine='openpyxl')
    except Exception as e:
        raise IOError(_("保存结果文件时发生错误: {}").format(e))

    if os.path.exists(temp_output_path):
        os.remove(temp_output_path)

    progress(100, _("同源转换完成。"))
    return results_df