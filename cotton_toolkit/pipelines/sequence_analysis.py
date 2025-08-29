import itertools

import pandas as pd
from typing import Dict, Optional
import logging

from Bio.Seq import Seq
from Bio.Data import CodonTable
from Bio.SeqUtils import gc_fraction
from Bio.SeqUtils.ProtParam import ProteinAnalysis, ProtParamData

from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.tools.fa_loader import parse_fasta_text

# Setup logger
logger = logging.getLogger("cotton_toolkit.pipelines.sequence_analysis")


try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text



def _calculate_rscu(sequence: Seq, codon_table_id: int) -> Dict[str, float]:
    """
    Calculates the Relative Synonymous Codon Usage (RSCU) for a sequence.
    用更通用的方法构建同义密码子表，以兼容不同版本的BioPython。
    """
    table = CodonTable.ambiguous_dna_by_id[codon_table_id]

    codon_counts = {}
    for i in range(0, len(sequence) - 2, 3):
        codon = str(sequence[i:i + 3])
        if codon not in table.stop_codons:
            codon_counts[codon] = codon_counts.get(codon, 0) + 1

    if not codon_counts:
        return {}

    # 手动构建同义密码子字典，以避免版本兼容性问题
    synonymous_codons = {}
    bases = ['T', 'C', 'A', 'G']
    # 使用itertools生成所有64种密码子组合
    for p in itertools.product(bases, repeat=3):
        codon = "".join(p)
        # 查询密码子对应的氨基酸，如果不是终止密码子
        if codon in table.forward_table:
            aa = table.forward_table[codon]
            if aa not in synonymous_codons:
                synonymous_codons[aa] = []
            synonymous_codons[aa].append(codon)

    rscu_values = {}
    for aa, codons in synonymous_codons.items():
        total_synonymous_usage = sum(codon_counts.get(c, 0) for c in codons)
        if total_synonymous_usage > 0:
            num_synonymous_codons = len(codons)
            for codon in codons:
                observed_count = codon_counts.get(codon, 0)
                expected_count = total_synonymous_usage / num_synonymous_codons
                rscu_values[codon] = observed_count / expected_count if expected_count > 0 else 0.0

    return rscu_values


@pipeline_task(_("序列分析"))
def run_analyze_sequences(
        sequences_dict: Dict[str, str],
        organelle_type: str = 'nucleus',
        input_sequence_type: str = 'cds',
        **kwargs
) -> pd.DataFrame:
    """
    根据输入序列类型（CDS或蛋白质）执行不同的分析流程。
    """

    progress = kwargs.get('progress_callback', lambda p, m: None)
    check_cancel = kwargs.get('check_cancel', lambda: False)

    if check_cancel(): return None

    analysis_results = []
    total_sequences = len(sequences_dict)

    codon_table_map = {
        'nucleus': 1,
        'mitochondria': 1,
        'chloroplast': 11
    }
    codon_table_id = codon_table_map.get(organelle_type, 1)

    for i, (gene_id, seq_str) in enumerate(sequences_dict.items()):
        # 在每次循环开始时检查是否需要取消
        if check_cancel(): return None

        # 更新进度条
        progress_percent = int((i / total_sequences) * 100)
        progress(progress_percent, _("正在分析 {} ({}/{})").format(gene_id, i + 1, total_sequences))

        if not seq_str:
            logger.warning(_("Skipping analysis for '{}' due to empty sequence.").format(gene_id))
            continue

        result_row = {'GeneID': gene_id}
        seq_str_upper = seq_str.upper()

        try:
            # 根据输入类型执行不同分析
            if input_sequence_type == 'cds':
                cds_seq = Seq(seq_str_upper)

                # 1. GC含量分析 (仅限CDS)
                result_row['GC_Content(%)'] = round(gc_fraction(cds_seq) * 100, 2)

                # 2. 密码子使用偏好性 (仅限CDS)
                if len(cds_seq) % 3 == 0:
                    rscu = _calculate_rscu(cds_seq, codon_table_id)
                    result_row['RSCU_Values'] = str(rscu) if rscu else None
                else:
                    logger.warning(_("CDS for '{}' is not a multiple of 3; skipping RSCU analysis.").format(gene_id))

                # 3. 理化性质分析 (从CDS翻译)
                protein_seq = None
                if len(cds_seq) % 3 == 0:
                    try:
                        protein_seq = cds_seq.translate(table=codon_table_id, cds=True)
                    except CodonTable.TranslationError as e:
                        logger.warning(_("Could not translate CDS for '{}': {}").format(gene_id, e))

                if protein_seq:
                    protein_seq_str = str(protein_seq).rstrip('*')
                    if protein_seq_str:
                        pa = ProteinAnalysis(protein_seq_str)
                        result_row['Molecular_Weight(Da)'] = round(pa.molecular_weight(), 2)
                        result_row['Isoelectric_Point(pI)'] = round(pa.isoelectric_point(), 2)
                        result_row['Aromaticity'] = round(pa.aromaticity(), 4)
                        result_row['Instability_Index'] = round(pa.instability_index(), 2)
                        result_row['Gravy'] = round(pa.gravy(), 4)

            elif input_sequence_type == 'protein':
                # 直接进行理化性质分析
                pa = ProteinAnalysis(seq_str_upper)
                result_row['Molecular_Weight(Da)'] = round(pa.molecular_weight(), 2)
                result_row['Isoelectric_Point(pI)'] = round(pa.isoelectric_point(), 2)
                result_row['Aromaticity'] = round(pa.aromaticity(), 4)
                result_row['Instability_Index'] = round(pa.instability_index(), 2)
                result_row['Gravy'] = round(pa.gravy(), 4)

            analysis_results.append(result_row)

        except Exception as e:
            err_msg = _("分析基因 '{}' 时发生错误: {}").format(gene_id, e)
            logger.error(err_msg)
            raise type(e)(err_msg) from e


    if not analysis_results:
        return pd.DataFrame()

    return pd.DataFrame(analysis_results)


@pipeline_task(_("直接序列分析"))
def run_seq_direct_analysis(
        config: MainConfig,
        sequence_type: str,
        organelle_type: str,
        output_path: str,
        perform_analysis: bool,
        fasta_text: Optional[str] = None,
        fasta_file_path: Optional[str] = None,
        **kwargs
) -> Optional[str]:
    """
    直接分析FASTA格式的文本，并根据模式返回结果。
    """
    progress = kwargs.get('progress_callback', lambda p, m: None)
    check_cancel = kwargs.get('check_cancel', lambda: False)

    progress(5, _("正在准备输入序列..."))

    if fasta_file_path:
        try:
            progress(8, _("正在读取文件，大文件可能需要一些时间..."))
            with open(fasta_file_path, 'r', encoding='utf-8') as f:
                fasta_text = f.read()
            progress(10, _("文件读取完毕，正在解析序列..."))
        except Exception as e:
            raise IOError(_("无法读取输入的FASTA文件: {}").format(e))

    if not fasta_text:
        raise ValueError(_("输入序列为空，请粘贴序列或选择有效的文件。"))

    if check_cancel(): return None

    # 如果是粘贴文本，也更新一下进度
    if not fasta_file_path:
        progress(10, _("正在解析粘贴的序列..."))

    sequences_dict = parse_fasta_text(fasta_text)
    if not sequences_dict:
        raise ValueError(_("未能从输入中解析出任何有效的FASTA序列。"))

    if check_cancel(): return None

    # 调用核心分析模块
    analysis_df = run_analyze_sequences(
        sequences_dict=sequences_dict,
        organelle_type=organelle_type,
        input_sequence_type=sequence_type,
        **kwargs
    )

    if check_cancel(): return None

    # 准备原始数据
    source_df = pd.DataFrame(sequences_dict.items(), columns=['Header', 'Sequence'])

    # 合并分析结果
    if analysis_df is not None and not analysis_df.empty:
        final_df = pd.merge(source_df, analysis_df, left_on='Header', right_on='GeneID', how='left')
        if 'GeneID' in final_df.columns:
            final_df = final_df.drop(columns=['GeneID'])
    else:
        final_df = source_df

    # 保存文件
    final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return _("序列及分析结果已成功保存到: {}").format(output_path)
