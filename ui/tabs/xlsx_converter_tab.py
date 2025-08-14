# 文件路径: ui/tabs/xlsx_converter_tab.py

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
import os
from typing import TYPE_CHECKING, Callable

from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class XlsxConverterTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            # self._ 属性在 super().__init__ 后才可用
            self.action_button.configure(text=self._("开始转换"), command=self.start_xlsx_to_csv_conversion)
        self.update_from_config()

    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        【修改】将所有需要翻译的元件都储存为 self 的属性。
        """
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 储存 UI 元件 ---
        self.title_label = ttkb.Label(parent_frame, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="n")

        self.description_label = ttkb.Label(parent_frame, text=_(
            "此工具会将一个Excel文件中的所有工作表内容合并到一个CSV文件中。\n适用于所有工作表表头一致的情况。"),
                                            wraplength=700, justify="center")  # <--- 【优化】移除了 bootstyle="secondary"

        self.description_label.grid(row=1, column=0, padx=10, pady=(0, 20))

        self.main_card = ttkb.LabelFrame(parent_frame, text=_("文件路径"), bootstyle="secondary")
        self.main_card.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.main_card.grid_columnconfigure(1, weight=1)

        self.input_label = ttk.Label(self.main_card, text=_("输入Excel文件:"), font=self.app.app_font_bold)
        # 顺便修复之前文字歪的问题
        self.input_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="sw")

        self.xlsx_input_entry = ttk.Entry(self.main_card)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        self.input_browse_button = ttkb.Button(self.main_card, text=_("浏览..."), width=12, bootstyle="info-outline",
                                               command=lambda: self.app.event_handler._browse_file(
                                                   self.xlsx_input_entry, [("Excel files", "*.xlsx")]))
        self.input_browse_button.grid(row=0, column=2, padx=(5, 10), pady=10)

        self.output_label = ttk.Label(self.main_card, text=_("输出CSV文件:"), font=self.app.app_font_bold)
        # 顺便修复之前文字歪的问题
        self.output_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="sw")

        self.csv_output_entry = ttk.Entry(self.main_card)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        self.output_browse_button = ttkb.Button(self.main_card, text=_("另存为..."), width=12, bootstyle="info-outline",
                                                command=lambda: self.app.event_handler._browse_save_file(
                                                    self.csv_output_entry, [("CSV files", "*.csv")]))
        self.output_browse_button.grid(row=1, column=2, padx=(5, 10), pady=10)


    def retranslate_ui(self, translator: Callable[[str], str]):
        """
        【新增】当语言切换时，此方法被 UIManager 调用以更新 UI 文本。
        """
        self.title_label.configure(text=translator("Excel (.xlsx) 转 CSV 工具"))
        self.description_label.configure(text=translator(
            "此工具会将一个Excel文件中的所有工作表内容合并到一个CSV文件中。\n适用于所有工作表表头一致的情况。"))
        self.main_card.configure(text=translator("文件路径"))
        self.input_label.configure(text=translator("输入Excel文件:"))
        self.output_label.configure(text=translator("输出CSV文件:"))
        self.input_browse_button.configure(text=translator("浏览..."))
        self.output_browse_button.configure(text=translator("另存为..."))

        if self.action_button:
            self.action_button.configure(text=translator("开始转换"))

    def update_button_state(self, is_task_running: bool, has_config: bool):
        # 这个工具不依赖配置文件，所以 has_config 固定为 True
        super().update_button_state(is_task_running, True)

    def start_xlsx_to_csv_conversion(self):
        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()
        if not input_path or not os.path.exists(input_path):
            self.app.ui_manager.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"));
            return
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.delete(0, tk.END)
            self.csv_output_entry.insert(0, output_path)
            self.app._log_to_viewer('ui.xlsx_tab',f"{_('自动生成输出路径:')} {output_path}", "INFO")
        try:
            self.app.event_handler._start_task(
                task_name=_("XLSX转CSV"),
                target_func=convert_excel_to_standard_csv,
                kwargs={"excel_path": input_path, "output_csv_path": output_path}
            )
        except Exception as e:
            self.app.ui_manager.show_error_message(_("转换失败"), f"{_('一个未预料的错误发生:')}\n{e}")

    def update_from_config(self):
        # 此分页不依赖于主配置文件，但仍需更新按钮状态
        self.update_button_state(self.app.active_task_name is not None, True)