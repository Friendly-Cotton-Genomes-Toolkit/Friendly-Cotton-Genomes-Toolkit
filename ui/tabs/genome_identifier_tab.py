# 文件路径: ui/tabs/genome_identifier_tab.py

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import TYPE_CHECKING

from .base_tab import BaseTab
from ..utils.gui_helpers import identify_genome_from_gene_ids

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class GenomeIdentifierTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, app)
        if self.action_button:
            self.action_button.configure(text=_("开始鉴定"), command=self.start_identification_task)

            # 获取按钮所在的、现在是透明的父容器
            action_frame = self.action_button.master
            action_frame.grid_columnconfigure(0, weight=1)
            action_frame.grid_columnconfigure(1, weight=0)

            # 使用StringVar来动态更新标签文本
            self.result_var = tk.StringVar(value=_("鉴定结果将显示在这里。"))

            # 创建结果标签，并使用 "secondary" bootstyle 来获得柔和的文字颜色
            self.result_label = ttkb.Label(action_frame,
                                           textvariable=self.result_var,
                                           anchor="w",
                                           font=self.app.app_font_italic,
                                           bootstyle="secondary"
                                           )
            self.result_label.grid(row=0, column=0, sticky="ew", padx=(10, 10))

            # 将按钮放在右侧
            self.action_button.grid(row=0, column=1, sticky="e")

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(1, weight=1)

        ttkb.Label(parent_frame, text=_("基因组类别鉴定工具"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        input_card = ttkb.LabelFrame(parent_frame, text=_("输入基因列表"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        input_card.grid_columnconfigure(0, weight=1)
        input_card.grid_rowconfigure(1, weight=1)

        ttkb.Label(input_card, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"), wraplength=650,
                   justify='left').grid(row=0, column=0, sticky='w', padx=10, pady=(10, 5))

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.gene_list_textbox = tk.Text(input_card, height=15, wrap="word", relief="flat", background=text_bg,
                                         foreground=text_fg, insertbackground=text_fg, font=self.app.app_font_mono)
        self.gene_list_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))

    def update_from_config(self):
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def start_identification_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return
        if not self.app.genome_sources_data:
            self.app.ui_manager.show_error_message(_("错误"), _("基因组源数据未加载，无法进行鉴定。"))
            return

        gene_ids_text = self.gene_list_textbox.get("1.0", tk.END).strip()
        if not gene_ids_text:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入至少一个基因ID进行鉴定。"))
            return

        gene_ids = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if g.strip()]

        # 更新结果标签的状态
        self.result_var.set(_("正在鉴定中..."))
        self.result_label.configure(bootstyle="info", font=self.app.app_font_italic)

        identified_assembly = identify_genome_from_gene_ids(gene_ids, self.app.genome_sources_data,
                                                            lambda msg, level: self.app._log_to_viewer(msg, level))

        if identified_assembly:
            result_text = f"{_('鉴定结果')}: {identified_assembly}"
            self.result_var.set(result_text)
            self.result_label.configure(bootstyle="success", font=self.app.app_font_bold)
        else:
            self.result_var.set(_("未能识别到匹配的基因组。"))
            self.result_label.configure(bootstyle="warning", font=self.app.app_font_italic)