# ui/tabs/genome_identifier_tab.py

import tkinter as tk
from tkinter import ttk, font as tkfont # Import ttk and tkfont
import ttkbootstrap as ttkb # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants

from typing import TYPE_CHECKING

# 导入后台任务函数
from ui.utils.gui_helpers import identify_genome_from_gene_ids

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class GenomeIdentifierTab(ttk.Frame): # Changed from ctk.CTkFrame to ttk.Frame
    """ “基因组类别鉴定”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent)
        self.app = app
        self.pack(fill="both", expand=True)

        # 此模块没有需要管理的Tkinter变量

        self._create_widgets()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- 统一使用 self.app 来访问字体 ---
        ttk.Label(self, text=_("基因组类别鉴定工具"), font=self.app.app_title_font).grid(
            row=0, column=0, padx=20, pady=(10, 5), sticky="n")

        # Added bootstyle="secondary" for a card-like appearance
        main_card = ttkb.Frame(self, bootstyle="secondary")
        main_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_card.grid_columnconfigure(0, weight=1)
        main_card.grid_rowconfigure(1, weight=1)

        ttk.Label(main_card, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"), wraplength=500,
                     justify="left", font=self.app.app_font).grid(
            row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        # Use tk.Text for textbox
        # 修复：tk.Text 的背景色和前景色通过 style.lookup 获取
        self.identifier_genes_textbox = tk.Text(main_card, font=self.app.app_font,
                                                background=self.app.style.lookup('TText', 'background'),
                                                foreground=self.app.style.lookup('TText', 'foreground'),
                                                relief="flat")
        self.identifier_genes_textbox.grid(row=1, column=0, padx=15, pady=5, sticky="nsew")

        action_frame = ttk.Frame(main_card)
        action_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_button = ttkb.Button(action_frame, text=_("开始鉴定"), command=self._run_genome_identification,
                                          bootstyle="primary")
        self.start_button.grid(row=0, column=0, sticky="w")
        # 修复：ttk.Label 不支持 text_color 参数，应使用 foreground
        self.identifier_result_label = ttk.Label(action_frame, text=_("鉴定结果将显示在这里。"),
                                                    font=self.app.app_font)
        self.identifier_result_label.grid(row=0, column=1, padx=10, sticky="e")


    def _run_genome_identification(self):
        """执行基因组类别鉴定。"""
        # Set text color dynamically based on theme
        # 修复：Colors 对象没有 'foreground' 属性，应使用 get_foreground() 方法
        default_label_text_color = self.app.style.lookup('TLabel', 'foreground') # Use direct lookup for safety
        warning_color = self.app.style.colors.warning
        error_color = self.app.style.colors.danger

        self.identifier_result_label.configure(text=_("正在鉴定中..."), font=self.app.app_font, foreground=default_label_text_color)
        gene_ids_text = self.identifier_genes_textbox.get("1.0", tk.END).strip()

        if not gene_ids_text:
            self.identifier_result_label.configure(text=_("请输入基因ID。"), foreground=warning_color)
            return

        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids:
            self.identifier_result_label.configure(text=_("请输入有效的基因ID。"), foreground=warning_color)
            return

        if not self.app.genome_sources_data:
            self.app._log_to_viewer(_("警告: 基因组源数据未加载，无法进行鉴定。"), "WARNING")
            self.identifier_result_label.configure(text=_("错误：基因组源未加载。"), foreground=error_color)
            return

        # Directly call the imported helper function, which logs via gui_status_callback
        identified_assembly = identify_genome_from_gene_ids(
            gene_ids,
            self.app.genome_sources_data,
            self.app.event_handler.gui_status_callback
        )


        if identified_assembly:
            result_text = f"{_('鉴定结果')}: {identified_assembly}"
            self.identifier_result_label.configure(text=result_text, foreground=default_label_text_color)
        else:
            self.identifier_result_label.configure(text=_("未能识别到匹配的基因组。"), foreground=warning_color)


    def update_button_state(self, is_task_running: bool, has_config: bool):
        """更新本选项卡中的按钮状态。"""
        state = "disabled" if is_task_running or not has_config else "normal"
        self.start_button.configure(state=state)

    def update_from_config(self):
        """基因组鉴定Tab不直接使用配置值，因此此方法为空。"""
        pass

    def update_assembly_dropdowns(self, assembly_ids: list[str]):
        """基因组鉴定Tab不包含基因组下拉菜单，因此此方法为空。"""
        pass