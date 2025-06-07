import pandas as pd
import numpy as np
from typing import List, Dict, Any
import os

# 定义将要添加到Excel表中的新列的名称
OUTPUT_COLUMN_NAMES = [
    'is_overlapping',
    'num_overlaps',
    'overlap_partner_indices',
    'max_overlap_length_with_partner',
    'fine_mapping_potential'
]
# 内部使用的临时索引列名
TEMP_ORIGINAL_INDEX_NAME = 'original_index_temp_col_for_processing'


# --- find_overlapping_regions ---
# (此函数与之前版本相同，它内部记录的 regionX_original_index 仍然是0-based的原始行号)
def find_overlapping_regions(df: pd.DataFrame) -> List[Dict]:
    required_cols = ['chr', 'region.start', 'region.end']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame 中缺少必需的列: {col}")
    try:
        df['region.start'] = pd.to_numeric(df['region.start'])
        df['region.end'] = pd.to_numeric(df['region.end'])
    except ValueError as e:
        raise ValueError(f"列 'region.start' 或 'region.end' 无法转换为数值类型: {e}")
    df_copy = df.copy()
    if 'original_index' not in df_copy.columns:
        df_copy['original_index'] = df_copy.index
    overlapping_regions_info = []
    for chromosome, group in df_copy.groupby('chr'):
        sorted_group = group.sort_values(by='region.start').reset_index(drop=True)
        if len(sorted_group) < 2:
            continue
        for i in range(len(sorted_group)):
            for j in range(i + 1, len(sorted_group)):
                region1 = sorted_group.iloc[i]
                region2 = sorted_group.iloc[j]
                if region1['region.start'] < region2['region.end'] and \
                        region1['region.end'] > region2['region.start']:
                    overlap_start = max(region1['region.start'], region2['region.start'])
                    overlap_end = min(region1['region.end'], region2['region.end'])
                    overlap_length = overlap_end - overlap_start
                    if overlap_length > 0:
                        overlap_detail = {
                            'chr': chromosome,
                            'region1_original_index': region1['original_index'],  # 0-based
                            'region1_info': region1.to_dict(),
                            'region2_original_index': region2['original_index'],  # 0-based
                            'region2_info': region2.to_dict(),
                            'overlap_start': overlap_start,
                            'overlap_end': overlap_end,
                            'overlap_length': overlap_length
                        }
                        overlapping_regions_info.append(overlap_detail)
    return overlapping_regions_info


# --- annotate_dataframe_with_overlap_details ---
# (修改此函数以存储1-based的伙伴索引)
def annotate_dataframe_with_overlap_details(df: pd.DataFrame, overlaps: List[Dict]) -> pd.DataFrame:
    df_annotated = df.copy()
    df_annotated['is_overlapping'] = False
    df_annotated['num_overlaps'] = 0
    partner_indices_lists = [[] for _ in range(len(df_annotated))]
    df_annotated['max_overlap_length_with_partner'] = 0.0

    for overlap_info in overlaps:
        idx1_0based = overlap_info['region1_original_index']  # 这是0-based的原始索引
        idx2_0based = overlap_info['region2_original_index']  # 这是0-based的原始索引
        overlap_len = overlap_info['overlap_length']

        if idx1_0based in df_annotated.index and idx2_0based in df_annotated.index:
            df_annotated.loc[idx1_0based, 'is_overlapping'] = True
            df_annotated.loc[idx1_0based, 'num_overlaps'] += 1
            loc_idx1 = df_annotated.index.get_loc(idx1_0based)
            partner_indices_lists[loc_idx1].append(str(idx2_0based + 1))  # <--- 存储1-based索引
            df_annotated.loc[idx1_0based, 'max_overlap_length_with_partner'] = \
                max(df_annotated.loc[idx1_0based, 'max_overlap_length_with_partner'], overlap_len)

            df_annotated.loc[idx2_0based, 'is_overlapping'] = True
            df_annotated.loc[idx2_0based, 'num_overlaps'] += 1
            loc_idx2 = df_annotated.index.get_loc(idx2_0based)
            partner_indices_lists[loc_idx2].append(str(idx1_0based + 1))  # <--- 存储1-based索引
            df_annotated.loc[idx2_0based, 'max_overlap_length_with_partner'] = \
                max(df_annotated.loc[idx2_0based, 'max_overlap_length_with_partner'], overlap_len)
        else:
            print(f"警告: 0-based 索引 {idx1_0based} 或 {idx2_0based} 在重叠注释时未在DataFrame的索引中找到。")

    df_annotated['overlap_partner_indices'] = [','.join(sorted(list(set(lst)))) for lst in partner_indices_lists]
    return df_annotated


# --- assess_and_add_fine_mapping_potential_no_pval ---
# (此函数与之前版本相同)
def assess_and_add_fine_mapping_potential_no_pval(
        df: pd.DataFrame,
        eff_snp_col: str = 'Effective SNP',
        region_len_col: str = 'region.length',
        gene_num_col: str = 'Gene Number',
        eff_snp_high_thresh: int = 10,
        eff_snp_medium_thresh: int = 3,
        region_len_ideal_max_thresh: int = 1000000,
        region_len_ideal_min_thresh: int = 10000,
        gene_num_ideal_max_thresh: int = 15
) -> pd.DataFrame:
    df_assessed = df.copy()
    potential_list = []
    required_cols_for_assessment = {
        eff_snp_col: 'int', region_len_col: 'int', gene_num_col: 'int'
    }
    for col, dtype in required_cols_for_assessment.items():
        if col not in df_assessed.columns:
            print(f"警告: 精细定位评估缺少列 '{col}'。该列评估将受影响。")
            df_assessed[col] = -1
        else:
            try:
                df_assessed[col] = pd.to_numeric(df_assessed[col], errors='coerce').fillna(-1).astype(int)
            except Exception as e:
                print(f"警告: 转换列 '{col}' 为数值类型失败: {e}。将使用-1替代。")
                df_assessed[col] = -1
    if 'is_overlapping' not in df_assessed.columns:
        print("警告: 'is_overlapping' 列缺失，精细定位潜力评估可能不完整。")
        df_assessed['is_overlapping'] = False
    for index, row in df_assessed.iterrows():
        potential = "一般关注"
        eff_snps = row.get(eff_snp_col, -1)
        length = row.get(region_len_col, -1)
        num_genes = row.get(gene_num_col, -1)
        is_overlapping = row.get('is_overlapping', False)
        if eff_snps == -1 or length == -1 or num_genes == -1:
            potential = "信息不全"
        else:
            is_eff_snp_high = eff_snps >= eff_snp_high_thresh
            is_eff_snp_medium = eff_snps >= eff_snp_medium_thresh
            is_len_ideal = (length <= region_len_ideal_max_thresh and length >= region_len_ideal_min_thresh)
            is_gene_num_ideal = num_genes <= gene_num_ideal_max_thresh and num_genes != -1
            if is_eff_snp_high and is_len_ideal and is_gene_num_ideal:
                potential = "优先关注 (高SNP, 合适大小)"
            elif is_eff_snp_high and (not is_len_ideal or not is_gene_num_ideal):
                potential = "值得关注 (高SNP, 大小或基因数欠佳)"
            elif is_eff_snp_medium and is_len_ideal and is_gene_num_ideal:
                potential = "值得关注 (中等SNP, 合适大小)"
            elif is_eff_snp_medium:
                potential = "一般关注 (中等SNP)"
            else:
                potential = "一般关注 (SNP较少或大小欠佳)"
            if is_overlapping and potential != "信息不全":
                potential += " (重叠区域)"
        potential_list.append(potential)
    df_assessed['fine_mapping_potential'] = potential_list
    return df_assessed


# --- analyze_bsa_data_and_update_excel ---
# (确保 'Index' 列生成为1-based，之前的版本已是如此)
def analyze_bsa_data_and_update_excel(
        input_file_path: str,
        sheet_name: str,
        output_file_path: str,
        fine_map_eff_snp_high: int = 10,
        fine_map_eff_snp_medium: int = 3,
        fine_map_region_len_max: int = 1000000,
        fine_map_region_len_min: int = 10000,
        fine_map_gene_num_max: int = 15
) -> None:
    """
    对BSA（Bulk Segregant Analysis）数据进行分析，并将处理后的目标工作表保存到新的Excel文件中。
    输出文件会在最前面添加一个从1开始的'Index'列。
    'overlap_partner_indices' 列中的索引也将是1-based，与'Index'列对应。
    (其他文档字符串内容与之前版本类似)
    ...
    """
    print(f"开始处理输入文件: {input_file_path}, 工作表: {sheet_name}")
    print(f"分析结果将保存到新文件: {output_file_path}\n")

    try:
        bsa_df_original = pd.read_excel(input_file_path, sheet_name=sheet_name, engine='openpyxl')
        bsa_df_original[TEMP_ORIGINAL_INDEX_NAME] = range(len(bsa_df_original))  # 0-based
        bsa_df_original.set_index(TEMP_ORIGINAL_INDEX_NAME, inplace=True)

    except FileNotFoundError:
        print(f"错误: 输入文件 '{input_file_path}' 未找到。")
        return
    except ValueError:
        print(f"错误: 工作表 '{sheet_name}' 在文件 '{input_file_path}' 中未找到，或者文件为空/格式错误。")
        return
    except Exception as e:
        print(f"加载Excel文件 '{input_file_path}' 时发生错误: {e}")
        return

    print("数据加载成功。")
    current_bsa_df = bsa_df_original.copy()

    found_existing_output_cols = [col for col in OUTPUT_COLUMN_NAMES if col in current_bsa_df.columns]
    if found_existing_output_cols:
        error_message = (
            f"\n错误处理终止: 工作表 '{sheet_name}' 在文件 '{input_file_path}' 中似乎已被分析过。\n"
            f"检测到以下已存在的分析列: {found_existing_output_cols}\n"
            "为避免重复分析，本次处理已停止。"
        )
        print(error_message)
        return

    print("未检测到已分析列，开始新的分析...")

    try:
        print("\n开始查找和注释重叠区域...")
        df_for_overlap = current_bsa_df.reset_index().rename(columns={TEMP_ORIGINAL_INDEX_NAME: 'original_index'})
        overlaps = find_overlapping_regions(df_for_overlap)
        current_bsa_df = annotate_dataframe_with_overlap_details(current_bsa_df, overlaps)  # 此处会生成1-based的伙伴索引
        print("重叠区域注释完成。")
    except ValueError as e:
        print(f"\n分析重叠区域时出错: {e}")
        return
    except Exception as e:
        print(f"\n分析重叠区域时发生未知错误: {e}")
        return

    try:
        print("\n开始评估精细定位潜力 (不依赖P-value)...")
        current_bsa_df = assess_and_add_fine_mapping_potential_no_pval(
            current_bsa_df,
            eff_snp_col='Effective SNP',  # 确保这个列名与您的输入文件匹配
            region_len_col='region.length',
            gene_num_col='Gene Number',  # 确保这个列名与您的输入文件匹配
            eff_snp_high_thresh=fine_map_eff_snp_high,
            eff_snp_medium_thresh=fine_map_eff_snp_medium,
            region_len_ideal_max_thresh=fine_map_region_len_max,
            region_len_ideal_min_thresh=fine_map_region_len_min,
            gene_num_ideal_max_thresh=fine_map_gene_num_max
        )
        print("精细定位潜力评估完成。")
        if not current_bsa_df.empty:
            print("\n处理后 DataFrame (前5行含新列):")
            preview_df = current_bsa_df.reset_index(drop=True)
            cols_to_show = [col for col in bsa_df_original.columns if col != TEMP_ORIGINAL_INDEX_NAME][:3] + \
                           [col for col in OUTPUT_COLUMN_NAMES if col in preview_df.columns]
            valid_cols_to_show = [col for col in cols_to_show if col in preview_df.columns]
            if valid_cols_to_show:
                print(preview_df[valid_cols_to_show].head())
            else:
                print("无法显示预览，相关列可能未完全生成。")
        else:
            print("处理后的DataFrame为空。")
    except Exception as e:
        print(f"\n评估精细定位潜力时发生错误: {e}")
        return

    try:
        print("\n准备将结果保存到新的Excel文件...")
        df_to_save = current_bsa_df.copy()
        df_to_save.reset_index(drop=True, inplace=True)
        df_to_save.insert(0, 'Index', range(1, len(df_to_save) + 1))  # 生成1-based的 'Index' 列

        output_dir = os.path.dirname(output_file_path)
        if output_dir and not os.path.exists(output_dir):  # 检查目录是否为空字符串（当路径只有文件名时）
            os.makedirs(output_dir)
            print(f"已创建输出目录: {output_dir}")

        df_to_save.to_excel(output_file_path, sheet_name=sheet_name, index=False)
        print(f"\n分析结果已成功保存到新文件: '{output_file_path}' (工作表: '{sheet_name}')。")
        print(
            f"输出文件包含一个从1开始的 'Index' 列，'overlap_partner_indices'中的索引也为1-based。原始输入文件未被修改。")

    except Exception as e:
        print(f"\n将结果保存到新 Excel 文件时发生错误: {e}")
        print("请确保输出路径有效，文件名合法，并且你有写入权限。")

    print("\n分析结束。")


# --- 如何使用 ---
if __name__ == "__main__":
    source_excel_file = "你的BSA数据文件名.xlsx"
    source_sheet_name = "Sheet1"
    output_excel_file = "分析结果输出_1based_index.xlsx"

    if source_excel_file == "你的BSA数据文件名.xlsx" or \
            output_excel_file == "分析结果输出_1based_index.xlsx":
        print("警告: 请在代码中修改 `source_excel_file`, `source_sheet_name`, 和 `output_excel_file`。")
        # exit()

    analyze_bsa_data_and_update_excel(
        input_file_path=source_excel_file,
        sheet_name=source_sheet_name,
        output_file_path=output_excel_file,
        fine_map_eff_snp_high=15,
        fine_map_eff_snp_medium=5,
        fine_map_region_len_max=1500000,
        fine_map_region_len_min=5000,
        fine_map_gene_num_max=20
    )