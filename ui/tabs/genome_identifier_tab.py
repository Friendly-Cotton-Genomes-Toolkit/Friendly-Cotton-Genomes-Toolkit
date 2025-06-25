# ui/tabs/genome_identifier_tab.py

import tkinter as tk
import customtkinter as ctk
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


class GenomeIdentifierTab(ctk.CTkFrame):
    """ “基因组类别鉴定”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 此模块没有需要管理的Tkinter变量

        self._create_widgets()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- 统一使用 self.app 来访问字体 ---
        ctk.CTkLabel(self, text=_("基因组类别鉴定工具"), font=self.app.app_title_font).grid(
            row=0, column=0, padx=20, pady=(10, 5), sticky="n")

        main_card = ctk.CTkFrame(self)
        main_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_card.grid_columnconfigure(0, weight=1)
        main_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(main_card, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"), wraplength=500,
                     justify="left", font=self.app.app_font).grid(
            row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.identifier_genes_textbox = ctk.CTkTextbox(main_card, font=self.app.app_font)
        self.identifier_genes_textbox.grid(row=1, column=0, padx=15, pady=5, sticky="nsew")

        action_frame = ctk.CTkFrame(main_card)
        action_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        self.start_button = ctk.CTkButton(action_frame, text=_("开始鉴定"), command=self._run_genome_identification,
                                          font=self.app.app_font)
        self.start_button.grid(row=0, column=0, sticky="w")
        self.identifier_result_label = ctk.CTkLabel(action_frame, text=_("鉴定结果将显示在这里。"),
                                                    font=self.app.app_font)
        self.identifier_result_label.grid(row=0, column=1, padx=10, sticky="e")


    def _run_genome_identification(self):
        """执行基因组类别鉴定。"""
        self.identifier_result_label.configure(text=_("正在鉴定中..."), font=self.app.app_font)
        gene_ids_text = self.identifier_genes_textbox.get("1.0", tk.END).strip()

        if not gene_ids_text:
            self.identifier_result_label.configure(text=_("请输入基因ID。"), text_color="orange", font=self.app.app_font)
            return

        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids:
            self.identifier_result_label.configure(text=_("请输入有效的基因ID。"), text_color="orange",
                                                   font=self.app.app_font)
            return

        if not self.app.genome_sources_data:
            self.app._log_to_viewer(_("警告: 基因组源数据未加载，无法进行鉴定。"), "WARNING")
            self.identifier_result_label.configure(text=_("错误：基因组源未加载。"), text_color="red",
                                                   font=self.app.app_font)
            return

        # 直接调用导入的辅助函数，而不是一个不存在的app方法
        identified_assembly = identify_genome_from_gene_ids(
            gene_ids,
            self.app.genome_sources_data,
            self.app.gui_status_callback
        )


        if identified_assembly:
            result_text = f"{_('鉴定结果')}: {identified_assembly}"
            self.identifier_result_label.configure(text=result_text, text_color=self.app.default_label_text_color)
        else:
            self.identifier_result_label.configure(text=_("未能识别到匹配的基因组。"), text_color="orange")