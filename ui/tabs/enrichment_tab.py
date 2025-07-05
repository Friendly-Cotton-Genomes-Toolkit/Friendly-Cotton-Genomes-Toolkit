# 文件路径: ui/tabs/enrichment_tab.py

import os
import re
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_enrichment_pipeline
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class EnrichmentTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_enrichment_assembly = tk.StringVar()
        self.has_header_var = tk.BooleanVar(value=False)
        self.has_log2fc_var = tk.BooleanVar(value=False)
        self.analysis_type_var = tk.StringVar(value="go")  # 默认小写
        self.bubble_plot_var = tk.BooleanVar(value=True)
        self.bar_plot_var = tk.BooleanVar(value=True)
        self.upset_plot_var = tk.BooleanVar(value=False)
        self.cnet_plot_var = tk.BooleanVar(value=False)

        # 绘图参数的GUI变量
        self.top_n_var = tk.IntVar(value=20)
        self.sort_by_var = tk.StringVar(value="FDR")
        self.show_title_var = tk.BooleanVar(value=True)
        self.width_var = tk.DoubleVar(value=10.0)
        self.height_var = tk.DoubleVar(value=8.0)
        self.file_format_var = tk.StringVar(value="png")
        self.collapse_transcripts_var = tk.BooleanVar(value=False)

        super().__init__(parent, app)

        # 【核心修改】利用 BaseTab 提供的 action_button
        if self.action_button:
            self.action_button.configure(text=_("开始富集分析"), command=self.start_enrichment_task,
                                         bootstyle="success")

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame  # 确保所有UI元素都放在可滚动区域
        parent_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(parent_frame, text=_("富集分析与绘图"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        # 输入数据卡片
        input_card = ttkb.LabelFrame(parent_frame, text=_("输入数据"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        input_card.grid_columnconfigure(1, weight=1)

        ttk.Label(input_card, text=_("基因组版本:"), font=self.app.app_font_bold).grid(row=0, column=0, sticky="w",
                                                                                       padx=(10, 5), pady=10)
        self.assembly_dropdown = ttkb.OptionMenu(input_card, self.selected_enrichment_assembly, _("加载中..."),
                                                 bootstyle="info")
        self.assembly_dropdown.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

        ttk.Label(input_card, text=_("基因ID列表 (或基因ID,Log2FC):"), font=self.app.app_font_bold).grid(row=1,
                                                                                                         column=0,
                                                                                                         sticky="nw",
                                                                                                         padx=(10, 5),
                                                                                                         pady=10)
        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.enrichment_genes_textbox = tk.Text(input_card, height=10, font=self.app.app_font_mono, wrap="word",
                                                relief="flat", background=text_bg, foreground=text_fg,
                                                insertbackground=text_fg)
        self.enrichment_genes_textbox.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.app.ui_manager.add_placeholder(self.enrichment_genes_textbox, "enrichment_genes_input")
        self.enrichment_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                       self.enrichment_genes_textbox,
                                                                                                       "enrichment_genes_input"))
        self.enrichment_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                         self.enrichment_genes_textbox,
                                                                                                         "enrichment_genes_input"))
        self.enrichment_genes_textbox.bind("<KeyRelease>", self._on_gene_input_change)

        # 输入格式与分析类型卡片
        format_card = ttkb.LabelFrame(parent_frame, text=_("输入格式与分析类型"), bootstyle="secondary")
        format_card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        format_card.grid_columnconfigure(1, weight=1)

        ttk.Label(format_card, text=_("输入格式:"), font=self.app.app_font_bold).grid(row=0, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        input_format_frame = ttk.Frame(format_card)
        input_format_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        input_format_frame.grid_columnconfigure(0, weight=1)
        ttkb.Checkbutton(input_format_frame, text=_("包含表头"), variable=self.has_header_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(input_format_frame, text=_("包含Log2FC"), variable=self.has_log2fc_var,
                         bootstyle="round-toggle").pack(side="left")

        ttk.Label(format_card, text=_("分析类型:"), font=self.app.app_font_bold).grid(row=1, column=0, padx=15, pady=5,
                                                                                      sticky="w")
        radio_frame = ttk.Frame(format_card)
        radio_frame.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        radio_frame.grid_columnconfigure(0, weight=1)
        ttkb.Radiobutton(radio_frame, text="GO", variable=self.analysis_type_var, value="go",
                         bootstyle="toolbutton-success").pack(side="left", padx=5)
        ttkb.Radiobutton(radio_frame, text="KEGG", variable=self.analysis_type_var, value="kegg",
                         bootstyle="toolbutton-success").pack(side="left", padx=5)

        # 合并转录本到基因开关
        ttkb.Checkbutton(format_card, text=_("合并转录本到基因"), variable=self.collapse_transcripts_var,
                         bootstyle="round-toggle").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=15, pady=5)
        # 添加注释 Label
        ttkb.Label(format_card, text=_(
            "开启后，将忽略基因ID后的mRNA编号 (如 .1, .2)，统一视为基因ID。例如: Ghir_D02G021470.1 / Ghir_D02G021470.2 将统一视为 Ghir_D02G021470。"),
                   font=self.app.app_comment_font, bootstyle="info").grid(row=3, column=0, columnspan=2, sticky="w",
                                                                          padx=15, pady=(0, 5))

        # 绘图设置卡片
        plot_config_card = ttkb.LabelFrame(parent_frame, text=_("绘图设置"), bootstyle="secondary")
        plot_config_card.grid(row=4, column=0, sticky="ew", padx=10, pady=5)  # 调整row值
        plot_config_card.grid_columnconfigure(1, weight=1)

        ttk.Label(plot_config_card, text=_("绘图类型:"), font=self.app.app_font_bold).grid(row=0, column=0, padx=15,
                                                                                           pady=5, sticky="w")
        plot_type_frame = ttk.Frame(plot_config_card)
        plot_type_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        plot_type_frame.grid_columnconfigure(0, weight=1)
        ttkb.Checkbutton(plot_type_frame, text=_("气泡图"), variable=self.bubble_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("条形图"), variable=self.bar_plot_var, bootstyle="round-toggle").pack(
            side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("Upset图"), variable=self.upset_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        ttkb.Checkbutton(plot_type_frame, text=_("网络图(Cnet)"), variable=self.cnet_plot_var,
                         bootstyle="round-toggle").pack(side="left")

        # Top N
        ttk.Label(plot_config_card, text=_("显示前N项:"), font=self.app.app_font_bold).grid(row=1, column=0, padx=15,
                                                                                            pady=5, sticky="w")
        self.top_n_entry = ttk.Entry(plot_config_card, textvariable=self.top_n_var, width=10)
        self.top_n_entry.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # Sort By
        ttk.Label(plot_config_card, text=_("排序依据:"), font=self.app.app_font_bold).grid(row=2, column=0, padx=15,
                                                                                           pady=5, sticky="w")
        self.sort_by_dropdown = ttkb.OptionMenu(plot_config_card, self.sort_by_var, "FDR", "FDR", "PValue",
                                                "FoldEnrichment", bootstyle="info")
        self.sort_by_dropdown.grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        # Show Title
        ttkb.Checkbutton(plot_config_card, text=_("显示图表标题"), variable=self.show_title_var,
                         bootstyle="round-toggle").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=15, pady=5)

        # Width
        ttk.Label(plot_config_card, text=_("图表宽度 (英寸):"), font=self.app.app_font_bold).grid(row=4, column=0,
                                                                                                  padx=15, pady=5,
                                                                                                  sticky="w")
        self.width_entry = ttk.Entry(plot_config_card, textvariable=self.width_var, width=10)
        self.width_entry.grid(row=4, column=1, sticky="w", padx=10, pady=5)

        # Height
        ttk.Label(plot_config_card, text=_("图表高度 (英寸):"), font=self.app.app_font_bold).grid(row=5, column=0,
                                                                                                  padx=15, pady=5,
                                                                                                  sticky="w")
        self.height_entry = ttk.Entry(plot_config_card, textvariable=self.height_var, width=10)
        self.height_entry.grid(row=5, column=1, sticky="w", padx=10, pady=5)

        # File Format
        ttk.Label(plot_config_card, text=_("文件格式:"), font=self.app.app_font_bold).grid(row=6, column=0, padx=15,
                                                                                           pady=5, sticky="w")
        self.file_format_dropdown = ttkb.OptionMenu(plot_config_card, self.file_format_var, "png", "png", "svg", "pdf",
                                                    "jpeg", bootstyle="info")
        self.file_format_dropdown.grid(row=6, column=1, sticky="ew", padx=10, pady=5)

        # 输出设置卡片 (用于输出目录)
        output_dir_card = ttkb.LabelFrame(parent_frame, text=_("输出设置"), bootstyle="secondary")
        output_dir_card.grid(row=5, column=0, sticky="ew", padx=10, pady=5)  # 调整row值
        output_dir_card.grid_columnconfigure(1, weight=1)

        ttk.Label(output_dir_card, text=_("输出目录:"), font=self.app.app_font_bold).grid(row=0, column=0, padx=15,
                                                                                          pady=5, sticky="w")
        self.enrichment_output_dir_entry = ttk.Entry(output_dir_card)
        self.enrichment_output_dir_entry.grid(row=0, column=1, sticky="ew", padx=(10, 5), pady=5)
        ttkb.Button(output_dir_card, text=_("浏览..."), width=12,
                    command=lambda: self.app.event_handler._browse_directory(self.enrichment_output_dir_entry),
                    bootstyle="info-outline").grid(row=0, column=2, padx=(0, 10), pady=5)

    def update_assembly_dropdowns(self, assembly_ids: list):
        self.app.ui_manager.update_option_menu(self.assembly_dropdown, self.selected_enrichment_assembly, assembly_ids)

    def update_from_config(self):
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])
        # 设置富集分析的默认输出目录
        default_dir = os.path.join(os.getcwd(), "enrichment_results")
        self.enrichment_output_dir_entry.delete(0, tk.END)
        self.enrichment_output_dir_entry.insert(0, default_dir)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _on_gene_input_change(self, event=None):
        self.app.event_handler._auto_identify_genome_version(self.enrichment_genes_textbox,
                                                             self.selected_enrichment_assembly)

    def start_enrichment_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"));
            return

        gene_ids_text = self.enrichment_genes_textbox.get("1.0", tk.END).strip()
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("enrichment_genes_input", "")))
        lines = gene_ids_text.splitlines()

        assembly_id = self.selected_enrichment_assembly.get()
        output_dir = self.enrichment_output_dir_entry.get().strip()
        analysis_type = self.analysis_type_var.get().lower()

        has_header = self.has_header_var.get()
        has_log2fc = self.has_log2fc_var.get()
        collapse_transcripts = self.collapse_transcripts_var.get()

        plot_types = [name for var, name in
                      [(self.bubble_plot_var, 'bubble'), (self.bar_plot_var, 'bar'), (self.upset_plot_var, 'upset'),
                       (self.cnet_plot_var, 'cnet')] if var.get()]

        top_n = self.top_n_var.get()
        sort_by = self.sort_by_var.get()
        show_title = self.show_title_var.get()
        width = self.width_var.get()
        height = self.height_var.get()
        file_format = self.file_format_var.get()

        if has_header and len(lines) > 0:
            lines = lines[1:]

        study_gene_ids = []
        gene_log2fc_map = {} if has_log2fc else None

        try:
            if has_log2fc:
                for i, line in enumerate(lines):
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    if len(parts) >= 2:
                        gene_id, log2fc_str = parts[0], parts[1]
                        try:
                            gene_log2fc_map[gene_id] = float(log2fc_str)
                        except ValueError:
                            raise ValueError(f"{_('第 {i + 1} 行Log2FC值无效:')} '{log2fc_str}'")
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

        if not study_gene_ids:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要分析的基因ID。"));
            return
        if not assembly_id or assembly_id in [_("加载中..."), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"));
            return
        if not plot_types:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请至少选择一种图表类型。"));
            return
        if not output_dir:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择图表的输出目录。"));
            return

        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'study_gene_ids': study_gene_ids,
            'analysis_type': analysis_type,
            'plot_types': plot_types,
            'output_dir': output_dir,
            'gene_log2fc_map': gene_log2fc_map,
            'top_n': top_n,
            'sort_by': sort_by,
            'show_title': show_title,
            'width': width,
            'height': height,
            'file_format': file_format,
            'collapse_transcripts': collapse_transcripts
        }
        self.app.event_handler._start_task(task_name=f"{analysis_type.upper()} {_('富集分析')}",
                                           target_func=run_enrichment_pipeline, kwargs=task_kwargs)
