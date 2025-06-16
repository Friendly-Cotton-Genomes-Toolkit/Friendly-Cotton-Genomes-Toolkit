import logging
import pandas as pd
from typing import List

# 获取logger实例
logger = logging.getLogger("cotton_toolkit.core.convertXlsx2csv")


def convert_all_sheets_to_csv(input_path: str, output_path: str) -> bool:
    """
    将 .xlsx 文件中的所有sheet合并并转换为一个 .csv 文件。

    - 跳过每个sheet的前两行，使用第三行作为唯一的表头。
    - 合并所有sheet的数据。
    - 最终的CSV文件只在第一行包含一个表头，内部无多余表头或空行。

    Args:
        input_path (str): 输入的 .xlsx 文件路径。
        output_path (str): 输出的 .csv 文件路径。

    Returns:
        bool: 转换成功返回True，否则返回False。
    """
    try:
        with pd.ExcelFile(input_path, engine='openpyxl') as excel_file:
            sheet_names = excel_file.sheet_names
            if not sheet_names:
                logger.error(f"无法在 '{input_path}' 中找到任何sheet。")
                return False

            all_dfs: List[pd.DataFrame] = []

            # 1. 遍历所有sheet，使用第3行作为表头，忽略前面的内容
            for sheet_name in sheet_names:
                try:
                    # header=2 是实现您需求的关键：跳过前2行，用第3行做表头
                    df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name, header=2)

                    if not df_sheet.empty:
                        all_dfs.append(df_sheet)
                        logger.info(f"成功读取 sheet: '{sheet_name}'，包含 {len(df_sheet)} 行数据。")
                    else:
                        logger.warning(f"Sheet '{sheet_name}' 为空，已跳过。")
                except Exception as e:
                    logger.warning(f"读取 sheet '{sheet_name}' 时出错，已跳过: {e}")

            if not all_dfs:
                logger.error(f"在 '{input_path}' 中未找到任何包含数据的有效sheet进行转换。")
                return False

            # 2. 合并所有读取到的DataFrame。因为表头一致，数据会正确对齐。
            # 合并后只有一个表头。
            final_df = pd.concat(all_dfs, ignore_index=True)

        # 3. 将最终的DataFrame写入CSV。
        # 默认行为就是将表头写在第一行，且只写一次。
        final_df.to_csv(output_path, index=False, encoding='utf-8-sig')

        logger.info(
            f"成功将 '{input_path}' 中的 {len(all_dfs)} 个sheet合并转换为 '{output_path}'，总计 {len(final_df)} 行。")
        return True
    except FileNotFoundError:
        logger.error(f"转换失败: 输入文件未找到 at '{input_path}'")
        return False
    except Exception as e:
        logger.exception(f"转换 '{input_path}' 时发生未知错误。")
        return False

# 使用示例
# convert_all_sheets_to_csv("your_input_file.xlsx", "your_output_file.csv")