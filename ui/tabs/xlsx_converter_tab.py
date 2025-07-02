# 文件路径: ui/tabs/xlsx_converter_tab.py

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import os
from typing import TYPE_CHECKING

from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class XlsxConverterTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, app)
        if self.action_button:
            self.action_button.configure(text=_("开始转换"), command=self.start_xlsx_to_csv_conversion)
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        ttkb.Label(parent_frame, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app.app_title_font, bootstyle="primary").grid(row=0, column=0, padx=10, pady=(10, 5), sticky="n")
        ttkb.Label(parent_frame, text=_("此工具会将一个Excel文件中的所有工作表内容合并到一个CSV文件中。\n适用于所有工作表表头一致的情况。"), wraplength=700, justify="center", bootstyle="secondary").grid(row=1, column=0, padx=10, pady=(0, 20), sticky="ew")
        main_card = ttkb.LabelFrame(parent_frame, text=_("文件路径"), bootstyle="secondary")
        main_card.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        main_card.grid_columnconfigure(1, weight=1)
        ttk.Label(main_card, text=_("输入Excel文件:")).grid(row=0, column=0, padx=(10,5), pady=10, sticky="w")
        self.xlsx_input_entry = ttk.Entry(main_card)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        ttkb.Button(main_card, text=_("浏览..."), width=12, bootstyle="info-outline", command=lambda: self.app.event_handler._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(row=0, column=2, padx=(5, 10), pady=10)
        ttk.Label(main_card, text=_("输出CSV文件:")).grid(row=1, column=0, padx=(10,5), pady=10, sticky="w")
        self.csv_output_entry = ttk.Entry(main_card)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ttkb.Button(main_card, text=_("另存为..."), width=12, bootstyle="info-outline", command=lambda: self.app.event_handler._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(row=1, column=2, padx=(5, 10), pady=10)

    def update_button_state(self, is_task_running: bool, has_config: bool):
        super().update_button_state(is_task_running, True)

    def start_xlsx_to_csv_conversion(self):
        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()
        if not input_path or not os.path.exists(input_path): self.app.ui_manager.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。")); return
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.delete(0, tk.END); self.csv_output_entry.insert(0, output_path)
            self.app._log_to_viewer(f"{_('自动生成输出路径:')} {output_path}", "INFO")
        try:
            self.app.event_handler._start_task(task_name=_("XLSX转CSV"), target_func=convert_excel_to_standard_csv, kwargs={"excel_path": input_path, "output_csv_path": output_path})
        except Exception as e:
            self.app.ui_manager.show_error_message(_("转换失败"), f"{_('一个未预料的错误发生:')}\n{e}")