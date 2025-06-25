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
        """创建“XLSX转CSV”页面的UI"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold
        secondary_text_color = self.app.secondary_text_color

        ctk.CTkLabel(self, text=_("Excel (.xlsx) 转 CSV 工具"), font=app_font_bold, wraplength=500).grid(row=0,
                                                                                                         column=0,
                                                                                                         pady=(20, 10),
                                                                                                         padx=20,
                                                                                                         sticky="n")

        info_label = ctk.CTkLabel(self, text=_(
            "此工具会将一个Excel文件中的所有工作表(Sheet)内容合并到一个CSV文件中。\n适用于所有Sheet表头格式一致的情况。"),
                                  font=app_font, wraplength=600, justify="center", text_color=secondary_text_color)
        info_label.grid(row=1, column=0, pady=(0, 20), padx=30, sticky="ew")

        card = ctk.CTkFrame(self)
        card.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=_("输入Excel文件:"), font=app_font).grid(row=0, column=0, padx=10, pady=(20, 10),
                                                                         sticky="w")
        self.xlsx_input_entry = ctk.CTkEntry(card, placeholder_text=_("选择要转换的 .xlsx 文件"), height=35,
                                             font=app_font)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        ctk.CTkButton(card, text=_("浏览..."), width=100, height=35, font=app_font,
                      command=lambda: self.app._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(
            row=0, column=2, padx=10, pady=(20, 10))

        ctk.CTkLabel(card, text=_("输出CSV文件:"), font=app_font).grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.csv_output_entry = ctk.CTkEntry(card, placeholder_text=_("选择保存位置和文件名 (不填则自动命名)"),
                                             height=35, font=app_font)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(card, text=_("另存为..."), width=100, height=35, font=app_font,
                      command=lambda: self.app._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        ctk.CTkButton(self, text=_("开始转换"), height=40, command=self.start_xlsx_to_csv_conversion,
                      font=app_font_bold).grid(row=3, column=0, sticky="ew", padx=20, pady=20)

    def start_xlsx_to_csv_conversion(self):
        """启动XLSX到CSV的转换任务"""
        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()

        if not input_path or not os.path.exists(input_path):
            self.app.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
            return

        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.delete(0, tk.END)  # 清空以防用户输入了空格
            self.csv_output_entry.insert(0, output_path)

        # 这里我们直接调用核心函数，因为它非常快，不需要放入后台任务队列
        try:
            self.app._log_to_viewer(_("正在转换XLSX到CSV..."))
            success = convert_excel_to_standard_csv(input_path, output_path)
            if success:
                self.app.show_info_message(_("转换成功"), f"{_('文件已成功保存到:')}\n{output_path}")
                self.app._log_to_viewer(f"{_('XLSX到CSV转换成功，文件已保存到:')} {output_path}")
            else:
                # convert_excel_to_standard_csv 内部应有日志记录错误
                self.app.show_error_message(_("转换失败"), _("转换过程中发生错误，请检查日志获取详情。"))
        except Exception as e:
            self.app.show_error_message(_("转换失败"), f"{_('一个未预料的错误发生:')} {e}")
            self.app._log_to_viewer(f"ERROR: {e}", "ERROR")