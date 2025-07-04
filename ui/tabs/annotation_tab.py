# 文件路径: ui/tabs/annotation_tab.py

import os
import re
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_functional_annotation, run_enrichment_pipeline
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class AnnotationTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_annotation_assembly = tk.StringVar()
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=True)
        self.kegg_path_anno_var = tk.BooleanVar(value=True)
        self.has_header_var = tk.BooleanVar(value=False)
        self.has_log2fc_var = tk.BooleanVar(value=False)
        self.analysis_type_var = tk.StringVar(value="GO")
        self.bubble_plot_var = tk.BooleanVar(value=True)
        self.bar_plot_var = tk.BooleanVar(value=True)
        self.upset_plot_var = tk.BooleanVar(value=False)
        self.cnet_plot_var = tk.BooleanVar(value=False)

        super().__init__(parent, app)

        if self.action_button:
            self.action_button.configure(text=_("开始功能注释"), command=self.start_annotation_task)

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(parent_frame, text=_("功能注释与富集分析"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        input_card = ttkb.LabelFrame(parent_frame, text=_("输入数据"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        input_card.grid_columnconfigure(1, weight=1)
        ttk.Label(input_card, text=_("基因组版本:"), font=self.app.app_font_bold).grid(row=0, column=0, sticky="w",
                                                                                       padx=(10, 5), pady=10)
        self.assembly_dropdown = ttkb.OptionMenu(input_card, self.selected_annotation_assembly, _("加载中..."),
                                                 bootstyle="info")
        self.assembly_dropdown.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        ttk.Label(input_card, text=_("基因ID列表:"), font=self.app.app_font_bold).grid(row=1, column=0, sticky="nw",
                                                                                       padx=(10, 5), pady=10)
        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.annotation_genes_textbox = tk.Text(input_card, height=10, font=self.app.app_font_mono, wrap="word",
                                                relief="flat", background=text_bg, foreground=text_fg,
                                                insertbackground=text_fg)
        self.annotation_genes_textbox.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.app.ui_manager.add_placeholder(self.annotation_genes_textbox, "genes_input")
        self.annotation_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                       self.annotation_genes_textbox,
                                                                                                       "genes_input"))
        self.annotation_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                         self.annotation_genes_textbox,
                                                                                                         "genes_input"))
        self.annotation_genes_textbox.bind("<KeyRelease>", self._on_gene_input_change)

        anno_card = ttkb.LabelFrame(parent_frame, text=_("功能注释"), bootstyle="secondary")
        anno_card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        anno_card.grid_columnconfigure(1, weight=1)
        checkbox_frame = ttk.Frame(anno_card)
        checkbox_frame.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        ttkb.Checkbutton(checkbox_frame, text="GO", variable=self.go_anno_var, bootstyle="round-toggle").pack(
            side="left", padx=5)
        ttkb.Checkbutton(checkbox_frame, text="InterPro", variable=self.ipr_anno_var, bootstyle="round-toggle").pack(
            side="left", padx=5)
        ttkb.Checkbutton(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)
        ttkb.Checkbutton(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)
        ttk.Label(anno_card, text=_("输出文件 (可选):"), font=self.app.app_font_bold).grid(row=1, column=0, sticky="w",
                                                                                           padx=10, pady=5)
        self.annotation_output_csv_entry = ttk.Entry(anno_card)
        self.annotation_output_csv_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=(5, 10))

        enrich_card = ttkb.LabelFrame(parent_frame, text=_("富集分析与绘图"), bootstyle="secondary")
        enrich_card.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        enrich_card.grid_columnconfigure(1, weight=1)
        ttk.Label(enrich_card, text=_("输入格式:"), font=self.app.app_font_bold).grid(row=1, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        input_format_frame = ttk.Frame(enrich_card)
        input_format_frame.grid(row=1, column=1, columnspan=3, padx=10, pady=5, sticky="w")
        ttkb.Checkbutton(input_format_frame, text=_("包含表头"), variable=self.has_header_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(input_format_frame, text=_("包含Log2FC"), variable=self.has_log2fc_var,
                         bootstyle="round-toggle").pack(side="left")
        ttk.Label(enrich_card, text=_("分析类型:"), font=self.app.app_font_bold).grid(row=2, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        radio_frame = ttk.Frame(enrich_card)
        radio_frame.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        ttkb.Radiobutton(radio_frame, text="GO", variable=self.analysis_type_var, value="GO",
                         bootstyle="toolbutton-success").pack(side="left", padx=5)
        ttkb.Radiobutton(radio_frame, text="KEGG", variable=self.analysis_type_var, value="KEGG",
                         bootstyle="toolbutton-success").pack(side="left", padx=5)
        ttk.Label(enrich_card, text=_("绘图类型:"), font=self.app.app_font_bold).grid(row=3, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        plot_type_frame = ttk.Frame(enrich_card)
        plot_type_frame.grid(row=3, column=1, columnspan=3, padx=10, pady=5, sticky="w")
        ttkb.Checkbutton(plot_type_frame, text=_("气泡图"), variable=self.bubble_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("条形图"), variable=self.bar_plot_var, bootstyle="round-toggle").pack(
            side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("Upset图"), variable=self.upset_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("网络图(Cnet)"), variable=self.cnet_plot_var,
                         bootstyle="round-toggle").pack(side="left")
        ttk.Label(enrich_card, text=_("输出目录:"), font=self.app.app_font_bold).grid(row=4, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        self.enrichment_output_dir_entry = ttk.Entry(enrich_card)
        self.enrichment_output_dir_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 5), pady=5)
        ttkb.Button(enrich_card, text=_("浏览..."), width=12,
                    command=lambda: self.app.event_handler._browse_directory(self.enrichment_output_dir_entry),
                    bootstyle="info-outline").grid(row=4, column=3, padx=(0, 10), pady=5)
        self.start_enrichment_button = ttkb.Button(enrich_card, text=_("开始富集分析"),
                                                   command=self.start_enrichment_task, bootstyle="primary")
        self.start_enrichment_button.grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(15, 15))

    def update_assembly_dropdowns(self, assembly_ids: list):
        self.app.ui_manager.update_option_menu(self.assembly_dropdown, self.selected_annotation_assembly, assembly_ids)

    def update_from_config(self):
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])
        if self.app.current_config: default_dir = os.path.join(os.getcwd(),
                                                               "enrichment_results"); self.enrichment_output_dir_entry.delete(
            0, tk.END); self.enrichment_output_dir_entry.insert(0, default_dir)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _on_gene_input_change(self, event=None):
        self.app.event_handler._auto_identify_genome_version(self.annotation_genes_textbox,
                                                             self.selected_annotation_assembly)

    def update_button_state(self, is_running, has_config):
        super().update_button_state(is_running, has_config)
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_enrichment_button'): self.start_enrichment_button.configure(state=state)

    def start_annotation_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"),
                                                                               _("请先加载配置文件。")); return
        gene_ids_text = self.annotation_genes_textbox.get("1.0", tk.END).strip()
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("genes_input", "")))
        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if
                    gene.strip() and not is_placeholder]
        assembly_id = self.selected_annotation_assembly.get()
        anno_types = [name for var, name in [(self.go_anno_var, 'go'), (self.ipr_anno_var, 'ipr'),
                                             (self.kegg_ortho_anno_var, 'kegg_orthologs'),
                                             (self.kegg_path_anno_var, 'kegg_pathways')] if var.get()]
        output_path = self.annotation_output_csv_entry.get().strip() or None
        if not gene_ids: self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要注释的基因ID。")); return
        if not assembly_id or assembly_id in [_("加载中..."),
                                              _("无可用基因组")]: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                                         _("请选择一个基因组版本。")); return
        if not anno_types: self.app.ui_manager.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。")); return
        task_kwargs = {'config': self.app.current_config, 'gene_ids': gene_ids, 'source_genome': assembly_id,
                       'target_genome': assembly_id,
                       'bridge_species': self.app.current_config.integration_pipeline.bridge_species_name,
                       'annotation_types': anno_types, 'output_path': output_path,
                       'output_dir': os.path.join(os.getcwd(), "annotation_results")}
        self.app.event_handler._start_task(task_name=_("功能注释"), target_func=run_functional_annotation,
                                           kwargs=task_kwargs)

    def start_enrichment_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"),
                                                                               _("请先加载配置文件。")); return
        gene_ids_text = self.annotation_genes_textbox.get("1.Tcl.END").strip()
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("genes_input", "")))
        lines = gene_ids_text.splitlines()
        assembly_id = self.selected_annotation_assembly.get()
        output_dir = self.enrichment_output_dir_entry.get().strip()
        analysis_type = self.analysis_type_var.get().lower()
        has_header = self.has_header_var.get()
        has_log2fc = self.has_log2fc_var.get()
        plot_config = self.app.current_config.enrichment_plot
        plot_types = [name for var, name in
                      [(self.bubble_plot_var, 'bubble'), (self.bar_plot_var, 'bar'), (self.upset_plot_var, 'upset'),
                       (self.cnet_plot_var, 'cnet')] if var.get()]
        if has_header and len(lines) > 0: lines = lines[1:]
        study_gene_ids, gene_log2fc_map = [], {} if has_log2fc else None
        try:
            if has_log2fc:
                for i, line in enumerate(lines):
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    if len(parts) >= 2:
                        gene_id, log2fc_str = parts[0], parts[1]
                        gene_log2fc_map[gene_id] = float(
                            log2fc_str)
                        study_gene_ids.append(gene_id)
                    else:
                        raise ValueError(f"{_('第 {i + 1} 行格式错误，需要两列 (基因, Log2FC):')} '{line}'")
            else:
                for line in lines:
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    study_gene_ids.extend([p for p in parts if p])
        except ValueError as e:
            self.app.ui_manager.show_error_message(_("输入格式错误"), str(e));
            return
        study_gene_ids = sorted(list(set(study_gene_ids)))
        if not study_gene_ids: self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要分析的基因ID。")); return
        if not assembly_id or assembly_id in [_("加载中..."),
                                              _("无可用基因组")]: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                                         _("请选择一个基因组版本。")); return
        if not plot_types: self.app.ui_manager.show_error_message(_("输入缺失"), _("请至少选择一种图表类型。")); return
        if not output_dir: self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择图表的输出目录。")); return
        task_kwargs = {'config': self.app.current_config, 'assembly_id': assembly_id, 'study_gene_ids': study_gene_ids,
                       'analysis_type': analysis_type, 'plot_types': plot_types, 'output_dir': output_dir,
                       'gene_log2fc_map': gene_log2fc_map, 'top_n': plot_config.top_n, 'sort_by': plot_config.sort_by,
                       'show_title': plot_config.show_title, 'width': plot_config.width, 'height': plot_config.height,
                       'file_format': plot_config.file_format, 'collapse_transcripts': plot_config.collapse_transcripts}
        self.app.event_handler._start_task(task_name=f"{analysis_type.upper()} {_('富集分析')}",
                                           target_func=run_enrichment_pipeline, kwargs=task_kwargs)
