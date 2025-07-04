# 文件路径: ui/tabs/homology_tab.py

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import TYPE_CHECKING, List

from cotton_toolkit.pipelines import run_homology_mapping
from .base_tab import BaseTab

# 这个 TYPE_CHECKING 块是解决循环导入的关键
# 它确保下面的 import 只在类型检查时执行，运行时会被跳过
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class HomologyTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.homology_strict_priority_var = tk.BooleanVar(value=True)
        super().__init__(parent, app)
        if self.action_button:
            self.action_button.configure(text=_("开始转换"), command=self._start_homology_task)
        self.update_from_config()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        ttkb.Label(parent, text=_("基因同源转换"), font=self.app.app_title_font, bootstyle="primary").grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        card1 = ttkb.LabelFrame(parent, text=_("输入"), bootstyle="secondary")
        card1.grid(row=1, column=0, sticky="new", padx=10, pady=5)
        card1.grid_columnconfigure(1, weight=1)
        card1.grid_rowconfigure(3, weight=1)
        ttkb.Label(card1, text=_("源基因组:"), font=self.app.app_font_bold).grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.source_assembly_dropdown = ttkb.OptionMenu(card1, self.selected_homology_source_assembly, _("加载中..."), bootstyle="info")
        self.source_assembly_dropdown.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")
        ttkb.Label(card1, text=_("目标基因组:"), font=self.app.app_font_bold).grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.target_assembly_dropdown = ttkb.OptionMenu(card1, self.selected_homology_target_assembly, _("加载中..."), bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ttkb.Label(card1, text=_("基因ID列表:"), font=self.app.app_font_bold).grid(row=2, column=0, padx=(10, 5), pady=10, sticky="nw")
        text_bg = self.app.style.lookup('TFrame', 'background'); text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.homology_map_genes_textbox = tk.Text(card1, height=10, font=self.app.app_font_mono, wrap="word", relief="flat", background=text_bg, foreground=text_fg, insertbackground=text_fg)
        self.homology_map_genes_textbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")
        self.app.ui_manager.add_placeholder(self.homology_map_genes_textbox, "homology_genes")
        self.homology_map_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)

        card2 = ttkb.LabelFrame(parent, text=_("参数设置"), bootstyle="secondary")
        card2.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        card2.grid_columnconfigure((1, 3), weight=1)
        self.strict_switch = ttkb.Checkbutton(card2, text=_("严格匹配模式 (同源亚组内优先)"), variable=self.homology_strict_priority_var, bootstyle="round-toggle")
        self.strict_switch.grid(row=0, column=0, columnspan=4, padx=10, pady=10, sticky="w")
        def create_param_entry(p, label, default_val, r, c):
            ttkb.Label(p, text=label, font=self.app.app_font_bold).grid(row=r, column=c * 2, padx=(10, 5), pady=5, sticky="w")
            entry = ttkb.Entry(p, width=15); entry.insert(0, default_val)
            entry.grid(row=r, column=c * 2 + 1, padx=(0, 10), pady=5, sticky="ew"); return entry
        self.homology_top_n_entry = create_param_entry(card2, _("Top N:"), "1", 1, 0)
        self.homology_evalue_entry = create_param_entry(card2, _("E-value:"), "1e-10", 1, 1)
        self.homology_pid_entry = create_param_entry(card2, _("PID (%):"), "30.0", 2, 0)
        self.homology_score_entry = create_param_entry(card2, _("Score:"), "50.0", 2, 1)

        card3 = ttkb.LabelFrame(parent, text=_("输出文件 (可选)"), bootstyle="secondary")
        card3.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        card3.grid_columnconfigure(1, weight=1)
        ttkb.Label(card3, text=_("输出路径:"), font=self.app.app_font_bold).grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_output_file_entry = ttkb.Entry(card3)
        self.homology_output_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")
        self.browse_button = ttkb.Button(card3, text=_("浏览..."), width=12, command=self._browse_output_file, bootstyle="info-outline")
        self.browse_button.grid(row=0, column=2, padx=(5, 10), pady=10)

    def _browse_output_file(self): self.app.event_handler._browse_save_file(self.homology_output_file_entry,[(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")])
    def _start_homology_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。")); return
        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip(); is_placeholder = (gene_ids_text == _(self.app.placeholders.get("homology_genes", "")))
        if not gene_ids_text or is_placeholder: self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。")); return
        gene_ids = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if g.strip()]; source_assembly = self.selected_homology_source_assembly.get(); target_assembly = self.selected_homology_target_assembly.get()
        if not all([source_assembly, target_assembly]) or _("加载中...") in [source_assembly, target_assembly] or _("无可用基因组") in [source_assembly, target_assembly]: self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择有效的源和目标基因组。")); return
        try:
            criteria = {"top_n": int(self.homology_top_n_entry.get()),
                        "evalue_threshold": float(self.homology_evalue_entry.get()),
                        "pid_threshold": float(self.homology_pid_entry.get()),
                        "score_threshold": float(self.homology_score_entry.get()),
                        "strict_subgenome_priority": self.homology_strict_priority_var.get()}
        except (ValueError, TypeError):
            self.app.ui_manager.show_error_message(_("输入错误"), _("参数设置中的阈值必须是有效的数字。")); return
        self.app.event_handler._start_task(
            task_name=_("基因同源转换"),
            target_func=run_homology_mapping,
            kwargs={
                'config': self.app.current_config,
                'source_assembly_id': source_assembly,
                'target_assembly_id': target_assembly,
                'gene_ids': gene_ids,
                'region': None,  # <--- 在这里添加这一行
                'output_csv_path': self.homology_output_file_entry.get().strip() or None,
                'criteria_overrides': criteria
            }
        )


    def update_from_config(self):
        if self.app.current_config: self.homology_output_file_entry.delete(0, tk.END); self.homology_output_file_entry.insert(0, "homology_results.xlsx")
        self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)
    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        valid_ids = assembly_ids or [_("无可用基因组")]
        def update_menu(dropdown, string_var):
            if not (dropdown and dropdown.winfo_exists()): return
            menu = dropdown['menu']; menu.delete(0, 'end')
            for value in valid_ids: menu.add_command(label=value, command=lambda v=value, sv=string_var: sv.set(v))
            if string_var.get() not in valid_ids: string_var.set(valid_ids[0])
        update_menu(self.source_assembly_dropdown, self.selected_homology_source_assembly); update_menu(self.target_assembly_dropdown, self.selected_homology_target_assembly)
    def _on_homology_gene_input_change(self, event=None): self.app.event_handler._auto_identify_genome_version(self.homology_map_genes_textbox, self.selected_homology_source_assembly)