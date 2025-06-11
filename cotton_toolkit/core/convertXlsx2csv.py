# cotton_toolkit/core/convertXlsx2csv.py

import pandas as pd
import os
import logging
from typing import Optional, Callable  # 确保导入 Optional 和 Callable

# --- 国际化和日志设置 ---
# 假设 _ 函数已由主应用程序入口设置到 builtins
try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


    if 'builtins' not in locals() or not hasattr(builtins, '_'):
        print("Warning (convertXlsx2csv.py): builtins._ not found for i18n. Using pass-through.")

logger = logging.getLogger("cotton_toolkit.converter")


def convert_xlsx_to_single_csv(
        xlsx_filepath: str,
        output_csv_filepath: Optional[str] = None,
        header_row_index: int = 0,  # 新增参数：指定标题行索引，默认为0 (第一行)
        status_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    将一个Excel文件中的所有工作表内容合并到一个CSV文件中。
    适用于所有工作表表头格式一致的情况。

    Args:
        xlsx_filepath (str): 输入的Excel文件路径。
        output_csv_filepath (Optional[str]): 输出的CSV文件路径。如果为None，将自动生成。
        header_row_index (int): 包含列名的行索引（从0开始计数）。默认为0 (第一行)。
        status_callback (Optional[Callable[[str], None]]): 用于报告状态更新的回调函数。

    Returns:
        bool: 转换成功返回True，否则返回False。
    """
    log = status_callback if status_callback else logger.info

    if not os.path.exists(xlsx_filepath):
        log(_("错误: 输入Excel文件未找到: {}").format(xlsx_filepath), level="ERROR")
        return False

    if not output_csv_filepath:
        base_name = os.path.splitext(os.path.basename(xlsx_filepath))[0]
        output_csv_filepath = os.path.join(os.path.dirname(xlsx_filepath), f"{base_name}_merged.csv")

    try:
        xls = pd.ExcelFile(xlsx_filepath)
        all_sheets_df = []

        log(_("正在处理Excel文件: {}").format(xlsx_filepath))
        for sheet_name in xls.sheet_names:
            log(_("读取工作表: {}").format(sheet_name))

            # --- 核心修改：添加 header 参数 ---
            # 告诉 pandas 从 header_row_index 这一行开始读取列名
            df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row_index)
            # --- 修改结束 ---

            all_sheets_df.append(df)

        if not all_sheets_df:
            log(_("错误: Excel文件中没有找到任何工作表。"), level="ERROR")
            return False

        # 合并所有工作表
        merged_df = pd.concat(all_sheets_df, ignore_index=True)

        # 保存为CSV
        merged_df.to_csv(output_csv_filepath, index=False, encoding='utf-8')
        log(_("所有工作表已成功合并并保存到CSV: {}").format(output_csv_filepath))
        return True

    except FileNotFoundError:
        log(_("错误: 文件未找到，请检查路径: {}").format(xlsx_filepath), level="ERROR")
        return False
    except Exception as e:
        log(_("错误: 转换Excel文件到CSV时发生错误: {}").format(e), level="ERROR")
        logger.exception("详细错误信息:")  # 打印完整的堆栈跟踪
        return False


# --- 用于独立测试 convertXlsx2csv.py 的示例代码 ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 创建一个模拟的Excel文件用于测试
    test_xlsx_path = "test_data.xlsx"
    test_csv_path = "merged_output.csv"

    # 包含描述性行和真正标题行的Excel数据
    data_sheet1 = {
        "Column A": [1, 2],
        "Column B": ["x", "y"]
    }
    data_sheet2 = {
        "Column A": [3, 4],
        "Column B": ["z", "w"]
    }

    # 写入Excel文件，模拟一个首行是描述文字的情况
    with pd.ExcelWriter(test_xlsx_path) as writer:
        # Sheet1: 模拟第一行是描述，第二行是真实标题
        df1_raw = pd.DataFrame({
            "It may contain multiple worksheets": ["Column A", "Column B"],
            "Unnamed: 1": ["x", "y"]  # 模拟 Unnamed 列
        })
        # 实际内容，不写入
        # df1_actual_data = pd.DataFrame(data_sheet1)
        # df1_raw.to_excel(writer, sheet_name='Sheet1', index=False, header=False, startrow=0)
        # pd.DataFrame(data_sheet1).to_excel(writer, sheet_name='Sheet1', index=False, header=True, startrow=1)

        # 最简单的模拟，直接把描述行作为 DataFrame 的第一行
        df_desc = pd.DataFrame([
            ["It may contain multiple worksheets", "Unnamed: 1", "Unnamed: 2"],
            ["真实列名1", "真实列名2", "真实列名3"],
            ["数据1a", "数据1b", "数据1c"],
            ["数据2a", "数据2b", "数据2c"]
        ])
        df_desc.to_excel(writer, sheet_name='Sheet1', index=False, header=False)

        df2 = pd.DataFrame(data_sheet2)
        df2.to_excel(writer, sheet_name='Sheet2', index=False)

    print(f"已创建模拟Excel文件: {test_xlsx_path}")

    print("\n--- 尝试转换 (header_row_index=0, 默认行为) ---")
    convert_xlsx_to_single_csv(test_xlsx_path, "output_default_header.csv")

    print("\n--- 尝试转换 (header_row_index=1, 跳过第一行描述) ---")
    success = convert_xlsx_to_single_csv(test_xlsx_path, test_csv_path, header_row_index=1)

    if success:
        print(f"\n成功转换到: {test_csv_path}")
        with open(test_csv_path, 'r', encoding='utf-8') as f:
            print("--- CSV 内容 (前5行) ---")
            for i, line in enumerate(f):
                print(line.strip())
                if i >= 4: break
            print("------------------------")
    else:
        print("\n转换失败。")

    # 清理
    if os.path.exists(test_xlsx_path):
        os.remove(test_xlsx_path)
    if os.path.exists(test_csv_path):
        os.remove(test_csv_path)
    if os.path.exists("output_default_header.csv"):
        os.remove("output_default_header.csv")