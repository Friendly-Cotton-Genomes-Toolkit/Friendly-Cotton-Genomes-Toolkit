import pandas as pd
import os
import re  # re is not strictly needed for this version but keeping it from original
import logging  # 用于日志记录

# 获取logger实例。主应用入口会配置根logger或包logger。
# 这里我们获取一个特定于本模块的logger。
logger = logging.getLogger("cotton_toolkit.convertXlsx2csv")



def convert_xlsx_to_single_csv(xlsx_filepath: str, output_csv_filepath: str) -> bool:
    """
    将XLSX文件的所有工作表合并内容到一个单一的CSV文件。

    参数:
    xlsx_filepath (str): 输入的XLSX文件的路径。
    output_csv_filepath (str): 输出的合并后CSV文件的完整路径。
    """
    try:
        # 读取Excel文件并获取所有工作表的名称
        logger.info(f'正在转换： {xlsx_filepath}')

        xls = pd.ExcelFile(xlsx_filepath)
        sheet_names = xls.sheet_names
        logger.info(f"找到工作表: {sheet_names}")

        if not sheet_names:
            logger.warning(f"警告: 文件 '{xlsx_filepath}' 中没有找到任何工作表。")
            return False

    except FileNotFoundError:
        logger.error(f"错误: 文件 '{xlsx_filepath}' 未找到。")
        return False
    except Exception as e:
        logger.error(f"读取Excel文件时发生错误: {e}")
        return False

    all_sheets_data = []  # 用于存储从每个工作表读取的DataFrame

    # 遍历每个工作表
    for sheet_name in sheet_names:
        logger.info(f"正在处理工作表: '{sheet_name}'...")
        try:
            # 读取当前工作表到pandas DataFrame
            df_sheet = xls.parse(sheet_name)

            # 可选: 如果希望在合并后的CSV中知道数据来自哪个原始工作表，
            # 可以添加一列来存储工作表名称。
            # df_sheet['original_sheet_name'] = sheet_name

            all_sheets_data.append(df_sheet)
            logger.info(f"工作表 '{sheet_name}' 读取成功。")

        except Exception as e:
            logger.error(f"处理工作表 '{sheet_name}' 时发生错误: {e}。将跳过此工作表。")

    if not all_sheets_data:
        logger.error("没有成功读取任何工作表的数据。无法创建合并的CSV文件。")
        return False

    # 合并所有工作表的DataFrame
    # ignore_index=True 会重新生成从0开始的连续索引
    # 如果不同工作表的列名不完全一致，pd.concat 会自动处理，
    # 缺失的列会用NaN填充。
    try:
        combined_df = pd.concat(all_sheets_data, ignore_index=True)
        logger.info("所有工作表数据已合并。")
    except Exception as e:
        logger.error(f"合并工作表数据时发生错误: {e}")
        return False

    # 创建输出目录 (如果CSV文件路径包含尚不存在的目录)
    output_dir = os.path.dirname(output_csv_filepath)
    if output_dir and not os.path.exists(output_dir):  # output_dir可能为空字符串，如果只指定文件名
        try:
            os.makedirs(output_dir)
            logger.info(f"创建输出目录: '{output_dir}'")

        except OSError as e:
            logger.error(f"错误: 无法创建输出目录 '{output_dir}': {e}")
            return False

    elif not output_dir and not os.path.exists(os.getcwd()):  # 确保当前工作目录存在，虽然这很少见
        logger.error(f"错误: 当前工作目录 '{os.getcwd()}' 不存在。")
        return False

    # 将合并后的DataFrame保存为CSV文件
    try:
        combined_df.to_csv(output_csv_filepath, index=False, encoding='utf-8')
        logger.info(f"所有工作表已合并并保存为 '{output_csv_filepath}'")
        return True
    except Exception as e:
        logger.error(f"保存合并后的CSV文件 '{output_csv_filepath}' 时发生错误: {e}")
        return False

