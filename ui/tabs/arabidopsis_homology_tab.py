# 文件路径: ui/tabs/homology_conversion_tab.py
# 版本：最终优化版，已修复Bug并添加ID格式自动识别功能

import tkinter as tk
import re  # 导入正则表达式模块
from tkinter import ttk
from typing import TYPE_CHECKING, List, Callable, Any

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines.homology import run_homology_conversion
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class HomologyConversionTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.app = app
        self.selected_cotton_assembly = tk.StringVar()
        self.conversion_direction_var = tk.StringVar()
        # --- 新增：用于匹配拟南芥ID的正则表达式 ---
        self.ath_pattern = re.compile(r"^(AT[1-5MC]G\d{5}(?:\.\d+)?)$", re.IGNORECASE)

        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.action_button.configure(text=self._("开始转换"), command=self.start_conversion_task)

        self._update_direction_options()
        self.update_from_config()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        ttkb.Label(parent, text=_("棉花-拟南芥同源基因转换"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="n")
        ttkb.Label(parent, text=_("基于预处理数据库中的同源注释表，快速进行ID批量转换。"), wraplength=700,
                   justify="center").grid(
            row=1, column=0, padx=10, pady=(0, 15))

        input_card = ttkb.LabelFrame(parent, text=_("输入参数"), bootstyle="secondary")
        input_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        input_card.grid_columnconfigure(1, weight=1)
        input_card.grid_rowconfigure(3, weight=1)

        ttkb.Label(input_card, text=_("转换方向:"), font=self.app.app_font_bold).grid(
            row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.direction_dropdown = ttkb.OptionMenu(input_card, self.conversion_direction_var, bootstyle="info")
        self.direction_dropdown.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")

        ttkb.Label(input_card, text=_("棉花基因组版本:"), font=self.app.app_font_bold).grid(
            row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.cotton_assembly_dropdown = ttkb.OptionMenu(input_card, self.selected_cotton_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.cotton_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        ttkb.Label(input_card, text=_("基因ID列表:"), font=self.app.app_font_bold).grid(
            row=2, column=0, padx=(10, 5), pady=10, sticky="nw")

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.gene_input_textbox = tk.Text(input_card, height=15, font=self.app.app_font_mono, wrap="word",
                                          relief="flat", background=text_bg, foreground=text_fg,
                                          insertbackground=text_fg)
        self.gene_input_textbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

        output_card = ttkb.LabelFrame(parent, text=_("输出文件"), bootstyle="secondary")
        output_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        output_card.grid_columnconfigure(1, weight=1)

        ttkb.Label(output_card, text=_("输出路径:"), font=self.app.app_font_bold).grid(
            row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.output_file_entry = ttkb.Entry(output_card, font=self.app.app_font_mono)
        self.output_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")
        ttkb.Button(output_card, text=_("浏览..."), width=12,
                    command=self._browse_output_file, bootstyle="info-outline").grid(
            row=0, column=2, padx=(5, 10), pady=10)

        # --- 核心修改：绑定键盘事件 ---
        self.gene_input_textbox.bind("<FocusIn>",
                                     lambda e: self.app.ui_manager._handle_focus_in(e, self.gene_input_textbox,
                                                                                    "homology_genes"))
        self.gene_input_textbox.bind("<FocusOut>",
                                     lambda e: self.app.ui_manager._handle_focus_out(e, self.gene_input_textbox,
                                                                                     "homology_genes"))
        self.gene_input_textbox.bind("<KeyRelease>", self._on_input_change)

    def _on_input_change(self, event=None):
        """
        【新增】当输入框内容改变时，自动识别ID类型并相应调整UI。
        """
        gene_ids_text = self.gene_input_textbox.get("1.0", "end-1c").strip()
        if not gene_ids_text or getattr(self.gene_input_textbox, 'is_placeholder', False):
            return

        # 1. 自动识别转换方向
        lines = gene_ids_text.splitlines()
        sample_lines = [line.strip() for line in lines[:10] if line.strip()]
        if not sample_lines: return

        ath_match_count = sum(1 for line in sample_lines if self.ath_pattern.match(line))

        # 如果超过80%的样本匹配拟南芥格式，则自动切换方向
        if (ath_match_count / len(sample_lines)) > 0.8:
            self.conversion_direction_var.set(_("拟南芥 -> 棉花"))
            # 如果是拟南芥ID，则不需要进行棉花基因组的自动识别，直接返回
            return

        # 2. 如果不是拟南芥ID，则假定为棉花ID，并触发棉花基因组的自动识别
        self.app.event_handler._auto_identify_genome_version(
            gene_input_textbox=self.gene_input_textbox,
            target_assembly_var=self.selected_cotton_assembly
        )

    # 其他方法保持不变
    def _update_direction_options(self):
        directions = {_("棉花 -> 拟南芥"): "cotton_to_ath", _("拟南芥 -> 棉花"): "ath_to_cotton"}
        self.app.ui_manager.update_option_menu(self.direction_dropdown, self.conversion_direction_var,
                                               list(directions.keys()))
        self.conversion_direction_var.set(_("棉花 -> 拟南芥"))

    def _browse_output_file(self):
        self.app.event_handler._browse_save_file(self.output_file_entry,
                                                 [(_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")])

    def start_conversion_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"),
                                                                               _("请先加载配置文件。")); return
        gene_ids_text = self.gene_input_textbox.get("1.0", tk.END).strip()
        if not gene_ids_text or getattr(self.gene_input_textbox, 'is_placeholder',
                                        False): self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                       _("请输入要转换的基因ID。")); return
        gene_ids = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if g.strip()]
        cotton_assembly_id = self.selected_cotton_assembly.get()
        if not cotton_assembly_id or _("加载中...") in cotton_assembly_id or _(
            "无可用棉花基因组") in cotton_assembly_id: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                              _("请选择一个有效的棉花基因组版本。")); return
        output_path = self.output_file_entry.get().strip()
        if not output_path: self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定输出文件路径。")); return
        direction_map = {_("棉花 -> 拟南芥"): "cotton_to_ath", _("拟南芥 -> 棉花"): "ath_to_cotton"}
        direction_key = direction_map.get(self.conversion_direction_var.get())
        if not direction_key: self.app.ui_manager.show_error_message(_("错误"), _("无效的转换方向。")); return
        task_kwargs = {'config': self.app.current_config, 'assembly_id': cotton_assembly_id, 'gene_ids': gene_ids,
                       'conversion_direction': direction_key, 'output_path': output_path}
        self.app.event_handler._start_task(task_name=_("同源基因转换"), target_func=run_homology_conversion,
                                           kwargs=task_kwargs)

    def update_from_config(self):
        if self.app.genome_sources_data:
            cotton_genomes = [asm_id for asm_id, info in self.app.genome_sources_data.items() if info.is_cotton()]
            self.app.ui_manager.update_option_menu(self.cotton_assembly_dropdown, self.selected_cotton_assembly,
                                                   cotton_genomes, _("无可用棉花基因组"))
        if not self.output_file_entry.get(): self.output_file_entry.insert(0, "homology_conversion_results.csv")
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)