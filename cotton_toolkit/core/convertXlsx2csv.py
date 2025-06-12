# cotton_toolkit/core/convertXlsx2csv.py

import logging
import pandas as pd
from typing import Union

# 获取logger实例
logger = logging.getLogger("cotton_toolkit.convertXlsx2csv")


def find_first_sheet_with_content(excel_file: pd.ExcelFile) -> Union[str, None]:
    """
    查找Excel文件中第一个包含非空内容的sheet。
    """
    for sheet_name in excel_file.sheet_names:
        try:
            # 只读取前几行进行检查，提高效率
            df_preview = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, nrows=5)
            if not df_preview.empty and df_preview.dropna(how='all').shape[0] > 0:
                logger.debug(f"找到有内容的sheet: '{sheet_name}'")
                return sheet_name
        except Exception as e:
            logger.warning(f"检查sheet '{sheet_name}' 时出错: {e}")
            continue
    logger.warning("在Excel文件中未找到任何包含内容的sheet。")
    return None


def convert(input_path: str, output_path: str) -> bool:
    """
    将 .xlsx 文件转换为 .csv 文件。

    【已修复】使用 'with' 语句确保Excel文件句柄在使用后被立即释放，解决[WinError 32]问题。
    同时，跳过Excel文件的前两行，将第三行作为表头。

    Args:
        input_path (str): 输入的 .xlsx 文件路径。
        output_path (str): 输出的 .csv 文件路径。

    Returns:
        bool: 转换成功返回True，否则返回False。
    """
    try:
        # --- 【核心修复点】 ---
        # 使用 'with' 语句来管理 pd.ExcelFile 对象的生命周期。
        # 当 'with' 代码块结束时，excel_file 会被自动关闭，从而释放对源文件的锁定。
        with pd.ExcelFile(input_path, engine='openpyxl') as excel_file:
            target_sheet = find_first_sheet_with_content(excel_file)

            if target_sheet is None:
                logger.error(f"无法在 '{input_path}' 中找到任何有数据的sheet进行转换。")
                return False

            # 从已打开的、受管的excel_file对象中读取数据
            # header=2 告知Pandas跳过前2行，使用第3行（0-indexed）作为表头。
            df = pd.read_excel(excel_file, sheet_name=target_sheet, header=2)

        # 'with' 块已退出，此时 input_path 对应的文件应该已经解锁。

        # 将读取到的数据保存为CSV，不包含索引列
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        logger.info(f"成功将 '{input_path}' (sheet: '{target_sheet}') 转换为 '{output_path}'")
        return True
    except FileNotFoundError:
        logger.error(f"转换失败: 输入文件未找到 at '{input_path}'")
        return False
    except ValueError as e:
        logger.error(f"转换 '{input_path}' 时发生值错误 (文件可能为空或格式不正确): {e}")
        return False
    except Exception as e:
        logger.exception(f"转换 '{input_path}' 时发生未知错误。")
        return False


# 为了保持与旧版本downloader的兼容性，保留此别名
convert_xlsx_to_single_csv = convert