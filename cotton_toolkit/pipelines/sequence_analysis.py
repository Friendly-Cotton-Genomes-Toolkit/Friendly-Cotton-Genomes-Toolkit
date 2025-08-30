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


def _analyze_sequences(
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
        if check_cancel(): return None

        progress_percent = int((i / total_sequences) * 100)
        progress(progress_percent, _("正在分析 {} ({}/{})").format(gene_id, i + 1, total_sequences))

        if not seq_str:
            logger.warning(_("Skipping analysis for '{}' due to empty sequence.").format(gene_id))
            continue

        result_row = {'GeneID': gene_id}
        seq_str_upper = seq_str.upper()
        protein_seq_for_analysis = None  # 用于后续蛋白质分析的序列

        try:
            if input_sequence_type == 'cds':
                cds_seq = Seq(seq_str_upper)
                result_row['GC_Content(%)'] = round(gc_fraction(cds_seq) * 100, 2)

                if len(cds_seq) % 3 == 0:
                    rscu = _calculate_rscu(cds_seq, codon_table_id)
                    result_row['RSCU_Values'] = str(rscu) if rscu else None
                    try:
                        # 尝试翻译成蛋白质序列
                        translated_protein = cds_seq.translate(table=codon_table_id, cds=True)
                        protein_seq_for_analysis = str(translated_protein).rstrip('*')
                    except CodonTable.TranslationError as e:
                        logger.warning(_("Could not translate CDS for '{}': {}").format(gene_id, e))
                else:
                    logger.warning(_("CDS for '{}' is not a multiple of 3; skipping RSCU and translation.").format(gene_id))

            elif input_sequence_type == 'protein':
                # 如果输入直接是蛋白质，则直接使用
                protein_seq_for_analysis = seq_str_upper

            # --- 对有效蛋白质序列执行理化性质分析 ---
            if protein_seq_for_analysis:
                # 检查序列是否包含非标准氨基酸字符，防止ProteinAnalysis报错
                valid_protein_chars = set(ProtParamData.kd.keys())
                if all(char in valid_protein_chars for char in protein_seq_for_analysis):
                    pa = ProteinAnalysis(protein_seq_for_analysis)
                    result_row['Molecular_Weight(Da)'] = round(pa.molecular_weight(), 2)
                    result_row['Isoelectric_Point(pI)'] = round(pa.isoelectric_point(), 2)
                    result_row['Aromaticity'] = round(pa.aromaticity(), 4)
                    result_row['Instability_Index'] = round(pa.instability_index(), 2)
                    result_row['Gravy'] = round(pa.gravy(), 4)
                else:
                    logger.warning(
                        _("Protein sequence for '{}' contains non-standard amino acids; skipping protein analysis.").format(
                            gene_id))
            analysis_results.append(result_row)

        except Exception as e:
            err_msg = _("分析基因 '{}' 时发生错误: {}").format(gene_id, e)
            logger.error(err_msg)
            # 在循环中不向上抛出异常，而是记录错误并继续，以处理FASTA文件中的其他序列
            analysis_results.append({'GeneID': gene_id, 'Error': str(e)})


    if not analysis_results:
        return pd.DataFrame()

    return pd.DataFrame(analysis_results)


@pipeline_task(_("序列分析"))
def run_seq_analysis(
        config: 'MainConfig',
        sequence_type: str,
        organelle_type: str,
        output_path: str,
        perform_analysis: bool,
        fasta_text: Optional[str] = None,
        fasta_file_path: Optional[str] = None,
        **kwargs
) -> Optional[str]:
    """
    直接分析FASTA格式的文本或文件，执行序列分析，
    并将不含原始序列的分析结果输出为一个“宽格式”矩阵视图Excel文件。
    """
    progress = kwargs.get('progress_callback', lambda p, m: None)
    check_cancel = kwargs.get('check_cancel', lambda: False)

    # --- 函数前半部分的输入处理和序列分析逻辑保持不变 ---
    progress(5, _("正在准备输入序列..."))
    if fasta_file_path:
        try:
            progress(8, _("正在读取文件..."))
            with open(fasta_file_path, 'r', encoding='utf-8') as f:
                fasta_text = f.read()
            progress(10, _("文件读取完毕，正在解析序列..."))
        except Exception as e:
            raise IOError(_("无法读取输入的FASTA文件: {}").format(e))
    if not fasta_text:
        raise ValueError(_("输入序列为空，请粘贴序列或选择有效的文件。"))
    if check_cancel(): return None
    if not fasta_file_path:
        progress(10, _("正在解析粘贴的序列..."))
    sequences_dict = parse_fasta_text(fasta_text)
    if not sequences_dict:
        raise ValueError(_("未能从输入中解析出任何有效的FASTA序列。"))
    if check_cancel(): return None
    source_df = pd.DataFrame(sequences_dict.items(), columns=['Header', 'Sequence'])
    final_df = source_df
    if perform_analysis:
        analysis_df = _analyze_sequences(
            sequences_dict=sequences_dict,
            organelle_type=organelle_type,
            input_sequence_type=sequence_type,
            **kwargs
        )
        if check_cancel(): return None
        if analysis_df is not None and not analysis_df.empty:
            final_df = pd.merge(source_df, analysis_df, left_on='Header', right_on='GeneID', how='left')
            if 'GeneID' in final_df.columns:
                final_df = final_df.drop(columns=['GeneID'])

    # --- 文件保存逻辑 ---
    try:
        progress(95, _("正在生成Excel报告..."))
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 使用 errors='ignore' 可以避免在列不存在时报错
            main_df = final_df.drop(columns=['Sequence', 'RSCU_Values'], errors='ignore')

            main_df.to_excel(writer, sheet_name='综合分析结果', index=False)

            # 2. 收集所有RSCU数据到“长格式”列表中
            all_rscu_data = []
            if perform_analysis and 'RSCU_Values' in final_df.columns:
                for index, row in final_df.iterrows():
                    gene_id = row['Header']
                    rscu_str = row['RSCU_Values']
                    if pd.notna(rscu_str):
                        try:
                            rscu_dict = eval(rscu_str)
                            if not rscu_dict: continue
                            for codon, value in rscu_dict.items():
                                all_rscu_data.append({
                                    'GeneID': gene_id,
                                    '密码子(Codon)': codon,
                                    'RSCU值(Value)': value
                                })
                        except Exception as e:
                            logger.warning(f"无法为基因'{gene_id}'处理RSCU数据: {e}")

            # 3. 将“长格式”数据重塑为“宽格式”矩阵并写入
            if all_rscu_data:
                long_rscu_df = pd.DataFrame(all_rscu_data)

                wide_rscu_df = long_rscu_df.pivot(
                    index='GeneID',
                    columns='密码子(Codon)',
                    values='RSCU值(Value)'
                ).reset_index().fillna(0)

                wide_rscu_df.to_excel(writer, sheet_name='RSCU矩阵视图', index=False)

            # 4. 自动调整列宽
            workbook = writer.book
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for column_cells in sheet.columns:
                    is_rscu_matrix = sheet_name == 'RSCU矩阵视图' and column_cells[0].column_letter != 'A'
                    if is_rscu_matrix:
                        length = max(len(str(cell.value)) for cell in column_cells)
                        sheet.column_dimensions[column_cells[0].column_letter].width = max(8, length + 2)
                    else:
                        length = max(len(str(cell.value)) for cell in column_cells)
                        sheet.column_dimensions[column_cells[0].column_letter].width = (length + 2) * 1.2

    except Exception as e:
        raise IOError(_("无法写入Excel输出文件: {}").format(e))

    progress(100, _("分析完成！"))

    if perform_analysis:
        return _("序列及分析结果已成功保存到: {}").format(output_path)
    else:
        # 如果不执行分析，只输出Header
        final_df.drop(columns=['Sequence']).to_csv(output_path, index=False, encoding='utf-8-sig')
        return _("序列已成功解析并保存到: {}").format(output_path)