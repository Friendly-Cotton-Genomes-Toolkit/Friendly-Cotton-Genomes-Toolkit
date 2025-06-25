# ui/tabs/xlsx_converter_tab.py

import tkinter as tk
import customtkinter as ctk
import os
from typing import TYPE_CHECKING

# 导入后台任务函数
from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class XlsxConverterTab(ctk.CTkFrame):
    """ “XLSX转CSV”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)
        self._create_widgets()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- 使用 self.app 来访问主应用中定义的字体 ---
        ctk.CTkLabel(self, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(10, 5), padx=20, sticky="n")

        ctk.CTkLabel(self, text=_("此工具会将一个Excel文件中的所有工作表内容合并到一个CSV文件中。\n适用于所有工作表表头一致的情况。"),
                     font=self.app.app_font, wraplength=600, justify="center", text_color=self.app.secondary_text_color).grid(
            row=1, column=0, pady=0, padx=30, sticky="ew")

        card = ctk.CTkFrame(self)
        card.grid(row=2, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=_("输入Excel文件:"), font=self.app.app_font).grid(row=0, column=0, padx=10, pady=(20, 10), sticky="w")
        self.xlsx_input_entry = ctk.CTkEntry(card, placeholder_text=_("选择要转换的 .xlsx 文件"), height=35, font=self.app.app_font)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        ctk.CTkButton(card, text=_("浏览..."), width=100, height=35, font=self.app.app_font,
                      command=lambda: self.app._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(
            row=0, column=2, padx=10, pady=(20, 10))

        ctk.CTkLabel(card, text=_("输出CSV文件:"), font=self.app.app_font).grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.csv_output_entry = ctk.CTkEntry(card, placeholder_text=_("选择保存位置和文件名 (不填则自动命名)"), height=35, font=self.app.app_font)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(card, text=_("另存为..."), width=100, height=35, font=self.app.app_font,
                      command=lambda: self.app._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        self.start_button = ctk.CTkButton(
            self, text=_("开始转换"), height=40,
            command=self.start_xlsx_to_csv_conversion, font=self.app.app_font_bold
        )
        self.start_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))

    def start_xlsx_to_csv_conversion(self):
        """
        启动XLSX到CSV的转换任务。
        这是一个属于 XlsxConverterTab 自身的方法。
        """
        # 1. 从UI输入框获取输入和输出文件路径
        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()

        # 2. 验证输入路径是否有效
        if not input_path or not os.path.exists(input_path):
            # 如果路径无效，通过主应用显示一个错误弹窗
            self.app.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
            return

        # 3. 如果输出路径为空，则自动生成一个
        if not output_path:
            # 获取输入文件的基础名（不含扩展名）
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            # 在输入文件的相同目录下，生成一个 "文件名_merged.csv" 的路径
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            # 将自动生成的路径更新回UI输入框，让用户看到
            self.csv_output_entry.delete(0, tk.END)
            self.csv_output_entry.insert(0, output_path)

        # 4. 在一个 try...except 块中调用后端转换函数，以捕获任何可能发生的错误
        try:
            # 通过主应用的日志功能，在UI上显示任务开始的信息
            self.app._log_to_viewer(_("正在转换XLSX到CSV..."))

            # 调用后端核心处理函数
            # 注意：这里我们直接从导入的模块调用，而不是通过self.app
            from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv

            # 将主应用的日志函数传递给后端，以便后端也能在UI上打印日志
            success = convert_excel_to_standard_csv(
                excel_path=input_path,
                output_csv_path=output_path,
                logger_func=self.app.gui_status_callback  # 使用 gui_status_callback 可以同时更新UI日志和状态栏
            )

            # 5. 根据后端返回的结果，给用户最终的反馈
            if not success:
                # 如果后端明确返回失败，显示一个通用错误。详细信息应已由后端通过logger_func打印。
                self.app.show_error_message(_("转换失败"), _("转换过程中发生错误，请检查操作日志获取详情。"))

            # 如果成功，后端应已通过logger_func打印成功信息，这里可以不必重复弹窗
            # 如果您希望每次成功都弹窗，可以取消下面的注释
            # else:
            #     self.app.show_info_message(_("转换成功"), f"{_('文件已成功保存到:')}\n{output_path}")

        except Exception as e:
            # 如果在调用过程中发生任何未预料的Python异常，也捕获并显示
            self.app.show_error_message(_("转换失败"), f"{_('一个未预料的错误发生:')}\n{e}")
