# ui/tabs/xlsx_converter_tab.py

import tkinter as tk
from tkinter import ttk # Import ttk module
import ttkbootstrap as ttkb # Import ttkbootstrap
import os
from typing import TYPE_CHECKING

# 导入后台任务函数
from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv
from ui.tabs.base_tab import BaseTab # Import BaseTab

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class XlsxConverterTab(BaseTab): # Changed from ctk.CTkFrame to ttk.Frame
    """ “XLSX转CSV”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, app)
        self._create_base_widgets()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(2, weight=1) # Adjusted row config for scrollable_frame

        # --- 使用 self.app 来访问主应用中定义的字体 ---
        ttk.Label(parent_frame, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(10, 5), padx=20, sticky="n")

        # 修复：ttk.Label 不支持 text_color 参数，应使用 foreground
        ttk.Label(parent_frame, text=_( # Changed from self to parent_frame
            "此工具会将一个Excel文件中的所有工作表内容合并到一个CSV文件中。\n适用于所有工作表表头一致的情况。"),
                     font=self.app.app_font, wraplength=600, justify="center",
                     foreground=self.app.secondary_text_color).grid(
            row=1, column=0, pady=0, padx=30, sticky="ew")

        card = ttk.Frame(parent_frame) # Changed from self to parent_frame
        card.grid(row=2, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_columnconfigure(1, weight=1)

        ttk.Label(card, text=_("输入Excel文件:"), font=self.app.app_font).grid(row=0, column=0, padx=10,
                                                                                  pady=(20, 10), sticky="w")
        # 修复：ttk.Entry 不支持 placeholder_text 参数。移除此参数。
        self.xlsx_input_entry = ttk.Entry(card, font=self.app.app_font) # Corrected line
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        # 修复：ttkb.Button 不支持直接的 font 参数
        ttkb.Button(card, text=_("浏览..."), width=12,
                      bootstyle="outline",
                      command=lambda: self.app.event_handler._browse_file(self.xlsx_input_entry,
                                                                          [("Excel files", "*.xlsx")])).grid(
            row=0, column=2, padx=10, pady=(20, 10))

        ttk.Label(card, text=_("输出CSV文件:"), font=self.app.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                sticky="w")
        # 修复：ttk.Entry 不支持 placeholder_text 参数。移除此参数。
        self.csv_output_entry = ttk.Entry(card, font=self.app.app_font) # Corrected line
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        # 修复：ttkb.Button 不支持直接的 font 参数
        ttkb.Button(card, text=_("另存为..."), width=12,
                      bootstyle="outline",
                      command=lambda: self.app.event_handler._browse_save_file(self.csv_output_entry,
                                                                               [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_button = ttkb.Button(
            parent_frame, text=_("开始转换"), # Changed from self to parent_frame
            command=self.start_xlsx_to_csv_conversion, bootstyle="success"
        )
        self.start_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))

    def update_button_state(self, is_task_running: bool, has_config: bool):
        """更新本选项卡中的按钮状态。"""
        state = "disabled" if is_task_running or not has_config else "normal"
        self.start_button.configure(state=state)


    def update_from_config(self):
        """XLSX Converter Tab 不直接使用配置值，所以此方法为空。"""
        pass


    def update_assembly_dropdowns(self, assembly_ids: list[str]):
        """XLSX Converter Tab 不包含基因组下拉菜单，此方法为空。"""
        pass


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
                self.app.ui_manager.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
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

                # Use _start_task to manage the backend function execution and UI updates
                self.app.event_handler._start_task(
                    task_name=_("XLSX转CSV"),
                    target_func=convert_excel_to_standard_csv,
                    kwargs={
                        "excel_path": input_path,
                        "output_csv_path": output_path
                        # status_callback and progress_callback will be added by _start_task
                    }
                )

            except Exception as e:
                # 如果在调用过程中发生任何未预料的Python异常，也捕获并显示
                self.app.ui_manager.show_error_message(_("转换失败"), f"{_('一个未预料的错误发生:')}\n{e}")