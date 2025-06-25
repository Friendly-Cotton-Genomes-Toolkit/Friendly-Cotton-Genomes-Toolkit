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
        """创建基因组类别鉴定选项卡的全部UI控件。"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold
        app_title_font = self.app.app_title_font
        app_comment_font = self.app.app_comment_font

        # --- 标题和描述 ---
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(info_frame, text=_("基因组类别鉴定工具"), font=app_title_font).grid(row=0, column=0, padx=10,
                                                                                         pady=(5, 2), sticky="w")
        ctk.CTkLabel(info_frame, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"), wraplength=400,
                     justify="left", font=app_font).grid(row=1, column=0, padx=10, pady=(2, 5), sticky="w")
        ctk.CTkLabel(info_frame, text=_("注意：以 'scaffold'、'Unknown' 开头的ID无法用于检查。"), font=app_comment_font,
                     text_color="orange", wraplength=400, justify="left").grid(row=2, column=0, padx=10, pady=(0, 5),
                                                                               sticky="w")

        # --- 基因输入文本框 ---
        self.identifier_genes_textbox = ctk.CTkTextbox(self, height=200, font=app_font)
        self.app._bind_mouse_wheel_to_scrollable(self.identifier_genes_textbox)
        self.identifier_genes_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # --- 操作区域 ---
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(action_frame, text=_("开始鉴定"), command=self._run_genome_identification, font=app_font).grid(
            row=0, column=0, padx=10, pady=5, sticky="w")
        self.identifier_result_label = ctk.CTkLabel(action_frame, text=_("鉴定结果将显示在这里。"), font=app_font)
        self.identifier_result_label.grid(row=0, column=1, padx=10, pady=5, sticky="e")

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

        identified_assembly = identify_genome_from_gene_ids(gene_ids, self.app.genome_sources_data,
                                                            self.app._log_to_viewer)

        if identified_assembly:
            result_text = f"{_('鉴定结果')}: {identified_assembly}"
            self.identifier_result_label.configure(text=result_text, text_color=self.app.default_label_text_color)
        else:
            self.identifier_result_label.configure(text=_("未能识别到匹配的基因组。"), text_color="orange")