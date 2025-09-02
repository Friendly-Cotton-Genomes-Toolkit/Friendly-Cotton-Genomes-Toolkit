import itertools
import pandas as pd
from typing import Dict, Optional, List
import logging
import collections
import math

from Bio.Seq import Seq
from Bio.Data import CodonTable
from Bio.SeqUtils import gc_fraction
from Bio.SeqUtils.ProtParam import ProteinAnalysis, ProtParamData

from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.tools.fa_loader import parse_fasta_text


logger = logging.getLogger("cotton_toolkit.pipelines.sequence_analysis")

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text

def _build_synonymous_codon_dict(table: CodonTable.CodonTable) -> dict:
    """
    构建同义密码子字典
    """
    synonymous_codons = collections.defaultdict(list)
    bases = ['T', 'C', 'A', 'G']
    all_codons = ["".join(p) for p in itertools.product(bases, repeat=3)]

    for codon in all_codons:
        try:
            aa = table.forward_table[codon]
            synonymous_codons[aa].append(codon)
        except (KeyError, CodonTable.TranslationError):
            if codon in table.stop_codons:
                synonymous_codons["*"].append(codon)
    return synonymous_codons


def _calculate_aliphatic_index(aa_percent: dict) -> float:
    """
    根据氨基酸组成百分比，手动计算脂肪族指数。
    公式来源: Ikai, A.J. (1980). J. Biochem. 88, 1895-1898.
    https://www.jstage.jst.go.jp/article/biochemistry1922/88/6/88_6_1895/_article
    AI = X(Ala) + a * X(Val) + b * (X(Ile) + X(Leu))
    """
    a = 2.9
    b = 3.9
    ala_percent = aa_percent.get('A', 0.0) * 100
    val_percent = aa_percent.get('V', 0.0) * 100
    ile_percent = aa_percent.get('I', 0.0) * 100
    leu_percent = aa_percent.get('L', 0.0) * 100

    aliphatic_index = ala_percent + a * val_percent + b * (ile_percent + leu_percent)
    return aliphatic_index


def _calculate_enc(sequence: Seq, codon_table_id: int) -> float:
    """根据指定的密码子表，计算有效密码子数 (ENC)。"""
    codon_counts = collections.Counter(sequence[i:i + 3] for i in range(0, len(sequence), 3))
    table = CodonTable.ambiguous_dna_by_id[codon_table_id]
    synonymous_codons = _build_synonymous_codon_dict(table)

    one_codon_aas = {aa for aa, codons in synonymous_codons.items() if len(codons) == 1}
    f = collections.defaultdict(float)
    for aa, codons in synonymous_codons.items():
        if aa in one_codon_aas: continue
        n = sum(codon_counts[c] for c in codons)
        if n == 0: continue
        p = sum((codon_counts[c] / n) ** 2 for c in codons)
        if n - 1 == 0:
            f[aa] = 1.0
        else:
            f[aa] = (n * p - 1) / (n - 1)

    deg_classes = collections.defaultdict(list)
    for aa, val in f.items():
        deg = len(synonymous_codons[aa])
        deg_classes[deg].append(val)
    avg_f = {deg: sum(vals) / len(vals) for deg, vals in deg_classes.items()}

    enc = 2.0
    if 2 in avg_f: enc += 9.0 / avg_f[2]
    if 3 in avg_f: enc += 1.0 / avg_f[3]
    if 4 in avg_f: enc += 5.0 / avg_f[4]
    if 6 in avg_f: enc += 3.0 / avg_f[6]
    return enc


def _calculate_cai(sequence: Seq, reference_weights: Dict[str, float], codon_table_id: int) -> float:
    """
    根据指定的参考权重和密码子表，计算密码子适应指数 (CAI)。
    """
    sequence = str(sequence).upper()
    table = CodonTable.ambiguous_dna_by_id[codon_table_id]
    synonymous_codons = _build_synonymous_codon_dict(table)

    max_weights = {}
    for aa, codons in synonymous_codons.items():
        weights = [reference_weights.get(c, 0.0) for c in codons]
        max_w = max(weights) if weights else 0.0
        max_weights[aa] = max_w if max_w > 0 else 1.0

    relative_adaptiveness = {}
    for aa, codons in synonymous_codons.items():
        for codon in codons:
            weight = reference_weights.get(codon, 0.0)
            relative_adaptiveness[codon] = weight / max_weights[aa]

    log_sum = 0.0
    num_codons = 0
    for i in range(0, len(sequence), 3):
        codon = sequence[i:i + 3]
        if len(codon) == 3:
            w = relative_adaptiveness.get(codon)
            if w is not None and w > 0:
                log_sum += math.log(w)
            num_codons += 1

    if num_codons == 0: return 0.0
    return math.exp(log_sum / num_codons)



def _calculate_gc3(sequence: Seq) -> Optional[float]:
    """Calculates the GC content of the third codon position."""
    if len(sequence) % 3 != 0: return None
    third_positions = [sequence[i+2] for i in range(0, len(sequence), 3)]
    if not third_positions: return 0.0
    gc_count = third_positions.count('G') + third_positions.count('C')
    return (gc_count / len(third_positions)) * 100



def _calculate_rscu(sequence: Seq, codon_table_id: int) -> Dict[str, float]:
    """
    Calculates the Relative Synonymous Codon Usage (RSCU) for a sequence.
    """
    codon_counts = collections.Counter(sequence[i:i + 3] for i in range(0, len(sequence), 3))
    table = CodonTable.ambiguous_dna_by_id[codon_table_id]
    synonymous_codons = _build_synonymous_codon_dict(table)

    rscu_values = {}
    for aa, codons in synonymous_codons.items():
        total_synonymous_usage = sum(codon_counts.get(c, 0) for c in codons)
        if total_synonymous_usage > 0:
            num_synonymous_codons = len(codons)
            expected_count = total_synonymous_usage / num_synonymous_codons
            for codon in codons:
                observed_count = codon_counts.get(codon, 0)
                rscu_values[codon] = observed_count / expected_count if expected_count > 0 else 0.0
        else:
            for codon in codons:
                rscu_values[codon] = 0.0
    return rscu_values



# 组织表达量数据来自cottonMD（https://yanglab.hzau.edu.cn/CottonMD）
# 仅摘取了TM1的数据，且去除了所有关于开花后时间（DPA）及胁迫处理的材料
# 之后，计算表达量的平均值与变异系数（使用样本标准偏差计算）
# 再取表达量top 10%、且变异系数最小的100个基因，用来计算CAI
COTTON_TM1_INDEX = {
    "AAA": 0.8469,    "AAC": 0.8495,    "AAG": 1.1531,    "AAT": 1.1505,
    "ACA": 1.1236,    "ACC": 0.9404,    "ACG": 0.3354,    "ACT": 1.6007,
    "AGA": 1.3414,    "AGC": 0.7477,    "AGG": 1.4200,    "AGT": 0.8803,
    "ATA": 0.6406,    "ATC": 1.0214,    "ATG": 1.0000,    "ATT": 1.3380,
    "CAA": 1.0153,    "CAC": 0.7263,    "CAG": 0.9847,    "CAT": 1.2737,
    "CCA": 1.3062,    "CCC": 0.5775,    "CCG": 0.4147,    "CCT": 1.7016,
    "CGA": 0.8363,    "CGC": 0.7353,    "CGG": 0.5164,    "CGT": 1.1506,
    "CTA": 0.5246,    "CTC": 0.8870,    "CTG": 0.7797,    "CTT": 1.6435,
    "GAA": 1.0060,    "GAC": 0.5971,    "GAG": 0.9940,    "GAT": 1.4029,
    "GCA": 1.1841,    "GCC": 0.8423,    "GCG": 0.2848,    "GCT": 1.6887,
    "GGA": 1.1608,    "GGC": 0.7663,    "GGG": 0.7111,    "GGT": 1.3618,
    "GTA": 0.5255,    "GTC": 0.7474,    "GTG": 1.0077,    "GTT": 1.7194,
    "TAA": 1.0500,    "TAC": 0.8492,    "TAG": 0.9000,    "TAT": 1.1508,
    "TCA": 1.1786,    "TCC": 0.9797,    "TCG": 0.5672,    "TCT": 1.6464,
    "TGA": 1.0500,    "TGC": 1.0025,    "TGG": 1.0000,    "TGT": 0.9975,
    "TTA": 0.6174,    "TTC": 0.9652,    "TTG": 1.5478,    "TTT": 1.0348,
}


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
        protein_seq_for_analysis = None

        try:
            if input_sequence_type == 'cds':
                cds_seq = Seq(seq_str_upper)
                result_row['GC_Content(%)'] = round(gc_fraction(cds_seq) * 100, 2)

                gc3_val = _calculate_gc3(cds_seq)
                if gc3_val is not None:
                    result_row['GC3_Content(%)'] = round(gc3_val, 2)

                if len(cds_seq) > 0 and len(cds_seq) % 3 == 0:
                    try:
                        result_row['ENC'] = round(_calculate_enc(cds_seq, codon_table_id), 2)
                    except Exception as e:
                        logger.warning(f"Could not calculate ENC for '{gene_id}': {e}")
                    try:
                        result_row['CAI'] = round(_calculate_cai(cds_seq, COTTON_TM1_INDEX, codon_table_id), 4)
                    except Exception as e:
                        logger.warning(f"Could not calculate CAI for '{gene_id}': {e}")

                if len(cds_seq) % 3 == 0:
                    rscu = _calculate_rscu(cds_seq, codon_table_id)
                    result_row['RSCU_Values'] = str(rscu) if rscu else None
                    try:
                        translated_protein = cds_seq.translate(table=codon_table_id, cds=True)
                        protein_seq_for_analysis = str(translated_protein).rstrip('*')
                    except CodonTable.TranslationError as e:
                        logger.warning(_("Could not translate CDS for '{}': {}").format(gene_id, e))
                else:
                    logger.warning(
                        _("CDS for '{}' is not a multiple of 3; skipping RSCU and translation.").format(gene_id))

            elif input_sequence_type == 'protein':
                protein_seq_for_analysis = seq_str_upper

            if protein_seq_for_analysis:

                problematic_genes_to_debug = ["Gh_D03G0025", "Gh_D03G0034"]
                if gene_id in problematic_genes_to_debug:
                    print(f"\n--- DEBUGGING GENE: {gene_id} ---")
                    print(f"Protein sequence passed to ProteinAnalysis (length {len(protein_seq_for_analysis)}):")
                    print(protein_seq_for_analysis)

                    try:
                        pa_debug = ProteinAnalysis(protein_seq_for_analysis)
                        aa_percent_debug = pa_debug.get_amino_acids_percent()
                        sum_of_percents = sum(aa_percent_debug.values()) * 100
                        print(f"Sum of calculated AA percentages by ProteinAnalysis: {sum_of_percents:.4f}%")
                    except Exception as e:
                        print(f"Error during ProteinAnalysis debugging: {e}")
                    print(f"-------------------------------------\n")


                valid_protein_chars = set(ProtParamData.kd.keys())
                if all(char in valid_protein_chars for char in protein_seq_for_analysis):
                    pa = ProteinAnalysis(protein_seq_for_analysis)
                    aa_percent = pa.get_amino_acids_percent() # 获取氨基酸组成

                    result_row['Molecular_Weight(Da)'] = round(pa.molecular_weight(), 2)
                    result_row['Isoelectric_Point(pI)'] = round(pa.isoelectric_point(), 2)
                    result_row['Aromaticity'] = round(pa.aromaticity(), 4)
                    result_row['Instability_Index'] = round(pa.instability_index(), 2)
                    result_row['Gravy'] = round(pa.gravy(), 4)
                    aliphatic_index_val = _calculate_aliphatic_index(aa_percent)
                    result_row['Aliphatic_Index'] = round(aliphatic_index_val, 2)
                    sec_struc = pa.secondary_structure_fraction()
                    result_row['Helix_Fraction(%)'] = round(sec_struc[0] * 100, 2)
                    result_row['Turn_Fraction(%)'] = round(sec_struc[1] * 100, 2)
                    result_row['Sheet_Fraction(%)'] = round(sec_struc[2] * 100, 2)

                    aa_percent = pa.get_amino_acids_percent()
                    for aa, percent in aa_percent.items():
                        result_row[f'AA_{aa}_(%)'] = round(percent * 100, 2)
                else:
                    logger.warning(
                        _("Protein sequence for '{}' contains non-standard amino acids; skipping protein analysis.").format(
                            gene_id))
            analysis_results.append(result_row)

        except Exception as e:
            err_msg = _("分析基因 '{}' 时发生错误: {}").format(gene_id, e)
            logger.error(err_msg)
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

    try:
        progress(95, _("正在生成Excel报告..."))
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            main_df = final_df.drop(columns=['Sequence', 'RSCU_Values'], errors='ignore')
            main_df.to_excel(writer, sheet_name=_('综合分析结果'), index=False)

            all_rscu_data = []
            if perform_analysis and 'RSCU_Values' in final_df.columns:
                # 1. 创建一个密码子到氨基酸的映射字典
                table = CodonTable.ambiguous_dna_by_id[1]
                codon_to_aa_map = {}
                bases = ['T', 'C', 'A', 'G']
                all_codons = ["".join(p) for p in itertools.product(bases, repeat=3)]
                for codon in all_codons:
                    try:
                        aa = table.forward_table[codon]
                        codon_to_aa_map[codon] = aa
                    except (KeyError, CodonTable.TranslationError):
                        if codon in table.stop_codons:
                            codon_to_aa_map[codon] = 'Stop'
                        else:
                            codon_to_aa_map[codon] = '?'

                # 2. 收集RSCU数据
                for index, row in final_df.iterrows():
                    gene_id = row['Header']
                    rscu_str = row['RSCU_Values']
                    if pd.notna(rscu_str):
                        try:
                            rscu_dict = eval(rscu_str)
                            if not rscu_dict: continue
                            for codon, value in rscu_dict.items():
                                aa = codon_to_aa_map.get(codon, '?')
                                new_column_name = f"{codon} ({aa})"
                                all_rscu_data.append({
                                    'GeneID': gene_id,
                                    'Codon_AA': new_column_name,
                                    'RSCU_Value': value
                                })
                        except Exception as e:
                            logger.warning(_("无法为基因'{gene_id}'处理RSCU数据: {e}").format(gene_id=gene_id, e=e))

            # 3. 使用新的列名进行数据透视
            if all_rscu_data:
                long_rscu_df = pd.DataFrame(all_rscu_data)
                wide_rscu_df = long_rscu_df.pivot(
                    index='GeneID',
                    columns='Codon_AA',  # 使用包含氨基酸信息的新列作为矩阵的列
                    values='RSCU_Value'
                ).reset_index().fillna(0)

                # 自动排序RSCU列，使其按字母顺序排列
                gene_id_col = wide_rscu_df[['GeneID']]
                rscu_cols = wide_rscu_df.drop(columns=['GeneID'])
                sorted_rscu_cols = rscu_cols.reindex(sorted(rscu_cols.columns), axis=1)
                final_wide_df = pd.concat([gene_id_col, sorted_rscu_cols], axis=1)

                final_wide_df.to_excel(writer, sheet_name=_('RSCU矩阵视图'), index=False)

            workbook = writer.book
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for column_cells in sheet.columns:
                    is_rscu_matrix = sheet_name ==_('RSCU矩阵视图') and column_cells[0].column_letter != 'A'
                    if is_rscu_matrix:
                        length = max(len(str(cell.value)) for cell in column_cells)
                        sheet.column_dimensions[column_cells[0].column_letter].width = max(8, length + 2)
                    else:
                        length = max(len(str(cell.value)) for cell in column_cells)
                        header_length = len(str(column_cells[0].value))
                        max_len = max(length, header_length)
                        sheet.column_dimensions[column_cells[0].column_letter].width = max_len + 2
    except Exception as e:
        raise IOError(_("无法写入Excel输出文件: {}").format(e))

    progress(100, _("分析完成！"))
    if perform_analysis:
        return _("序列及分析结果已成功保存到: {}").format(output_path)
    else:
        final_df.drop(columns=['Sequence']).to_csv(output_path, index=False, encoding='utf-8-sig')
        return _("序列已成功解析并保存到: {}").format(output_path)