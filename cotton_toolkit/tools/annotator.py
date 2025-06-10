import logging
import pandas as pd

logger = logging.getLogger("cotton_toolkit.tools.annotator")

def match_genes(xlsx_file_path: str, csv_file_path: str, output_csv_path: str, xlsx_gene_column: str,
                csv_query_column: str, csv_match_column: str,
                csv_description_column: str):
    try:
        # 1. 读取xlsx文件，获取“修正的基因名”列表
        df_xlsx = pd.read_excel(xlsx_file_path)
        # 确保列名正确，并获取唯一的基因名列表
        if xlsx_gene_column not in df_xlsx.columns:
            raise ValueError(f"错误: XLSX文件中未找到列 '{xlsx_gene_column}'")
        xlsx_gene_names = df_xlsx[xlsx_gene_column].dropna().unique().tolist()
        print(f"从XLSX文件加载了 {len(xlsx_gene_names)} 个唯一的基因名。")
        if not xlsx_gene_names:
            print("警告: XLSX文件中的基因名列表为空。")
            exit()

        # 2. 读取csv文件
        df_csv = pd.read_csv(csv_file_path)
        # 确保列名正确
        required_csv_cols = [csv_query_column, csv_match_column, csv_description_column]
        for col in required_csv_cols:
            if col not in df_csv.columns:
                raise ValueError(f"错误: CSV文件中未找到列 '{col}'")
        print(f"从CSV文件加载了 {len(df_csv)} 行数据。")

        # 3. 创建一个字典来存储每个xlsx基因名匹配到的所有信息
        # 键是 "修正的基因名"，值是一个字典，包含 Match, Description, Query 的集合 (set)
        # 使用集合可以自动处理重复项
        results_dict = {gene_name: {'Match': set(), 'Description': set(), 'Query': set()} for gene_name in xlsx_gene_names}

        # 4. 遍历CSV文件的每一行，进行匹配
        matched_csv_rows_count = 0
        for index, csv_row in df_csv.iterrows():
            query_val = str(csv_row[csv_query_column])  # 确保是字符串
            match_val = str(csv_row[csv_match_column])
            desc_val = str(csv_row[csv_description_column])

            for xlsx_gene in xlsx_gene_names:
                # 核心匹配逻辑：CSV的Query列是否以XLSX的基因名开头
                if query_val.startswith(xlsx_gene):
                    results_dict[xlsx_gene]['Match'].add(match_val)
                    results_dict[xlsx_gene]['Description'].add(desc_val)
                    results_dict[xlsx_gene]['Query'].add(query_val)
                    matched_csv_rows_count += 1
                    break  # 假设一个CSV Query只对应一个XLSX基因名前缀

        print(f"CSV中有 {matched_csv_rows_count} 行数据与XLSX中的基因名匹配。")

        # 5. 准备输出数据
        output_data = []
        for gene_name, data in results_dict.items():
            if data['Query']:  # 只输出那些在CSV中找到匹配的基因
                # 对集合中的元素排序后用分号连接，确保输出顺序一致性
                output_data.append({
                    '修正的基因名': gene_name,
                    'Match': '; '.join(sorted(list(data['Match']))),
                    'Description': '; '.join(sorted(list(data['Description']))),
                    'Querys(所有匹配到的query)': '; '.join(sorted(list(data['Query'])))
                })

        if not output_data:
            print("没有找到任何匹配项，不生成输出文件。")
        else:
            # 6. 创建输出DataFrame并保存到CSV
            output_df = pd.DataFrame(output_data)
            output_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')  # utf-8-sig 确保Excel能正确打开中文
            print(f"匹配结果已保存到: {output_csv_path}")
            print(f"共输出了 {len(output_df)} 条匹配的基因信息。")

    except FileNotFoundError:
        print(f"错误: 文件未找到。请检查 '{xlsx_file_path}' 和 '{csv_file_path}' 的路径是否正确。")
    except ValueError as ve:
        print(ve)
    except Exception as e:
        print(f"发生了一个意外错误: {e}")
