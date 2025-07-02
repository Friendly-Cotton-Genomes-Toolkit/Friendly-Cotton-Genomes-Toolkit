# cotton_tool/ui/tabs/annotation_tab.py

import os
import re
import tkinter as tk
from tkinter import ttk, font as tkfont  # Import ttk and tkfont
import ttkbootstrap as ttkb  # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants

from typing import TYPE_CHECKING, List

# 导入后台任务函数
from cotton_toolkit.pipelines import run_functional_annotation, run_enrichment_pipeline
from ui.tabs.base_tab import BaseTab

if TYPE_CHECKING:
    from ui.gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class AnnotationTab(BaseTab):  # 继承自 BaseTab
    def __init__(self, parent, app: "CottonToolkitApp"):
        # Initialize selected_annotation_assembly here as it's used in _create_widgets
        self.selected_annotation_assembly = tk.StringVar()
        super().__init__(parent, app)
        self._create_base_widgets()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # Access fonts directly from self.app
        font_regular = self.app.app_font
        font_bold = self.app.app_font_bold
        font_title = self.app.app_title_font
        font_mono = self.app.app_font_mono
        # 修复：Colors 对象没有 'foreground' 属性，应使用 get_foreground('TLabel') 方法
        # safe_text_color is not directly used for colors here, but good practice.

        ttk.Label(parent_frame, text=_("功能注释与富集分析"), font=font_title,
                  foreground=self.app.style.colors.primary).grid(row=0, column=0, pady=(5, 15), padx=10,
                                                                 sticky="n")
        # Added bootstyle="secondary" for a card-like appearance
        input_card = ttkb.Frame(parent_frame, bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="ew", padx=5, pady=(5, 10))
        input_card.grid_columnconfigure(1, weight=1)
        ttk.Label(input_card, text=_("输入数据"), font=font_bold).grid(row=0, column=0, columnspan=2, sticky="w",
                                                                       padx=10, pady=(10, 15))
        ttk.Label(input_card, text=_("基因组版本:"), font=font_regular).grid(row=1, column=0, sticky="w", padx=(15, 5),
                                                                             pady=10)

        # Initialize the dropdown with a default variable value, before actual options are loaded
        initial_assembly_value = [_("加载中...")][0]
        self.selected_annotation_assembly.set(initial_assembly_value) # Ensure StringVar is set initially

        self.assembly_dropdown = ttkb.OptionMenu(input_card, self.selected_annotation_assembly,
                                                 initial_assembly_value,  # Default display value
                                                 *[initial_assembly_value],  # Initial options list
                                                 bootstyle="info")
        self.assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=10, pady=10)

        ttk.Label(input_card, text=_("基因ID列表:"), font=font_regular).grid(row=2, column=0, sticky="nw", padx=(15, 5),
                                                                             pady=10)
        # Use tk.Text for textbox
        # 修复：使用 style.lookup 获取 'TText' 的背景色和前景色
        self.annotation_genes_textbox = tk.Text(input_card, height=10, font=font_mono, wrap="word",
                                                background=self.app.style.lookup('TText', 'background'),
                                                foreground=self.app.style.lookup('TText', 'foreground'),
                                                relief="flat")
        self.annotation_genes_textbox.grid(row=2, column=1, sticky="ew", padx=10, pady=(5, 10))
        self.app.ui_manager._add_placeholder(self.annotation_genes_textbox, "genes_input")
        self.annotation_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._clear_placeholder(
            self.annotation_genes_textbox, "genes_input"))
        self.annotation_genes_textbox.bind("<FocusOut>",
                                           lambda e: self.app.ui_manager._add_placeholder(self.annotation_genes_textbox,
                                                                                          "genes_input"))
        self.annotation_genes_textbox.bind("<KeyRelease>", self._on_gene_input_change)

        # Added bootstyle="secondary" for a card-like appearance
        anno_card = ttkb.Frame(parent_frame, bootstyle="secondary")
        anno_card.grid(row=2, column=0, sticky="ew", padx=5, pady=10)
        anno_card.grid_columnconfigure(0, weight=1)
        ttk.Label(anno_card, text=_("功能注释"), font=font_bold).grid(row=0, column=0, sticky="w", padx=10,
                                                                      pady=(10, 15))

        checkbox_frame = ttk.Frame(anno_card)
        checkbox_frame.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=True)
        self.kegg_path_anno_var = tk.BooleanVar(value=True)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(checkbox_frame, text="GO", variable=self.go_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(checkbox_frame, text="InterPro", variable=self.ipr_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                         bootstyle="round-toggle").pack(side="left", padx=5)

        # 修复：ttk.Entry 不支持 placeholder_text 参数。移除此参数。
        self.annotation_output_csv_entry = ttk.Entry(anno_card, font=font_regular)
        self.annotation_output_csv_entry.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_annotation_button = ttkb.Button(anno_card, text=_("开始功能注释"),
                                                   command=self.start_annotation_task,
                                                   bootstyle="primary")
        self.start_annotation_button.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 15))

        # Added bootstyle="secondary" for a card-like appearance
        enrich_card = ttkb.Frame(parent_frame, bootstyle="secondary")
        enrich_card.grid(row=3, column=0, sticky="ew", padx=5, pady=10)
        enrich_card.grid_columnconfigure(1, weight=3)
        enrich_card.grid_columnconfigure(3, weight=1)
        ttk.Label(enrich_card, text=_("富集分析与绘图"), font=font_bold).grid(row=0, column=0, columnspan=4, sticky="w",
                                                                              padx=10, pady=(10, 15))
        ttk.Label(enrich_card, text=_("输入格式:"), font=font_regular).grid(row=1, column=0, padx=15, pady=5,
                                                                            sticky="w")

        input_format_frame = ttk.Frame(enrich_card)
        input_format_frame.grid(row=1, column=1, columnspan=3, padx=10, pady=5, sticky="w")
        self.has_header_var = tk.BooleanVar(value=False)
        self.has_log2fc_var = tk.BooleanVar(value=False)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(input_format_frame, text=_("包含表头"), variable=self.has_header_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(input_format_frame, text=_("包含Log2FC"), variable=self.has_log2fc_var,
                         bootstyle="round-toggle").pack(side="left")

        ttk.Label(enrich_card, text=_("分析类型:"), font=font_regular).grid(row=2, column=0, padx=15, pady=5,
                                                                            sticky="w")
        radio_frame = ttk.Frame(enrich_card)
        radio_frame.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        self.analysis_type_var = tk.StringVar(value="GO") # Moved definition here
        # 修复：ttkb.Radiobutton 不支持直接的 font 参数
        ttkb.Radiobutton(radio_frame, text="GO", variable=self.analysis_type_var, value="GO",
                         bootstyle="toolbutton").pack(side="left", padx=5)
        # 修复：ttkb.Radiobutton 不支持直接的 font 参数
        ttkb.Radiobutton(radio_frame, text="KEGG", variable=self.analysis_type_var, value="KEGG",
                         bootstyle="toolbutton").pack(side="left", padx=5)

        ttk.Label(enrich_card, text=_("绘图类型:"), font=font_regular).grid(row=3, column=0, padx=15, pady=5,
                                                                            sticky="w")
        plot_type_frame = ttk.Frame(enrich_card)
        plot_type_frame.grid(row=3, column=1, columnspan=3, padx=10, pady=5, sticky="w")
        self.bubble_plot_var = tk.BooleanVar(value=True)
        self.bar_plot_var = tk.BooleanVar(value=True)
        self.upset_plot_var = tk.BooleanVar(value=False)
        self.cnet_plot_var = tk.BooleanVar(value=False)
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(plot_type_frame, text=_("气泡图"), variable=self.bubble_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(plot_type_frame, text=_("条形图"), variable=self.bar_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(plot_type_frame, text=_("Upset图"), variable=self.upset_plot_var,
                         bootstyle="round-toggle").pack(side="left", padx=(0, 15))
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        ttkb.Checkbutton(plot_type_frame, text=_("网络图(Cnet)"), variable=self.cnet_plot_var,
                         bootstyle="round-toggle").pack(side="left")

        ttk.Label(enrich_card, text=_("输出目录:"), font=font_regular).grid(row=4, column=0, padx=15, pady=5,
                                                                            sticky="w")
        self.enrichment_output_dir_entry = ttk.Entry(enrich_card, font=font_regular)
        self.enrichment_output_dir_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 5), pady=5)
        # 修复：ttkb.Button 不支持直接的 font 参数
        ttkb.Button(enrich_card, text=_("浏览..."), width=12,
                    command=lambda: self.app.event_handler._browse_directory(self.enrichment_output_dir_entry),
                    bootstyle="outline").grid(row=4, column=3, padx=(0, 10), pady=5)
        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_enrichment_button = ttkb.Button(enrich_card, text=_("开始富集分析"),
                                                   command=self.start_enrichment_task,
                                                   bootstyle="primary")
        self.start_enrichment_button.grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(15, 15))


    def update_assembly_dropdowns(self, assembly_ids: list):
        # 修复：ttkb.OptionMenu 不支持通过 configure(values=...) 更新选项。
        # 必须销毁旧的并重新创建新的 OptionMenu。
        old_dropdown = self.assembly_dropdown
        parent_frame = old_dropdown.master # 获取父容器

        # --- 在销毁旧控件之前，安全地获取所有必需的属性 ---
        # 确保 old_dropdown 存在且是 ttkbootstrap.OptionMenu 实例
        variable = self.selected_annotation_assembly
        command = old_dropdown.cget('command') if old_dropdown and old_dropdown.winfo_exists() else None
        bootstyle = old_dropdown.cget('bootstyle') if old_dropdown and old_dropdown.winfo_exists() else "info"

        # 获取布局信息
        layout_info = {}
        manager_type = None
        if old_dropdown and old_dropdown.winfo_exists():
            if hasattr(old_dropdown, 'winfo_manager'):
                manager_type = old_dropdown.winfo_manager()
                if manager_type == "grid":
                    layout_info = old_dropdown.grid_info()
                elif manager_type == "pack":
                    layout_info = old_dropdown.pack_info()

        if old_dropdown and old_dropdown.winfo_exists():
            old_dropdown.destroy() # Destroy old OptionMenu

        # 确保有一个默认值来初始化新的 OptionMenu
        if not assembly_ids: assembly_ids = [_("无可用基因组")] # Changed from "加载中..." for clarity
        new_initial_value = variable.get()
        if new_initial_value not in assembly_ids and assembly_ids:
            new_initial_value = assembly_ids[0]
        elif not assembly_ids:
            new_initial_value = _("无可用基因组") # Ensure it's set to this if list is empty
        variable.set(new_initial_value) # Ensure StringVar is updated to the new initial value

        # Recreate OptionMenu
        self.assembly_dropdown = ttkb.OptionMenu(
            parent_frame,
            variable, # Pass StringVar object
            new_initial_value, # Default display value (must be one of the options)
            *assembly_ids, # New options list as positional argument
            command=command,
            bootstyle=bootstyle
        )

        # Reapply layout
        if layout_info:
            if manager_type == "grid":
                self.assembly_dropdown.grid(**{k:v for k,v in layout_info.items() if k != 'in'})
            elif manager_type == "pack":
                self.assembly_dropdown.pack(**{k:v for k,v in layout_info.items() if k != 'in'})
        else:
            # Fallback for initial creation if layout_info was empty (shouldn't happen with _create_widgets call)
            self.assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=10, pady=10)


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        if self.app.current_config:
            default_dir = os.path.join(os.getcwd(), "enrichment_results")
            self.enrichment_output_dir_entry.delete(0, tk.END)  # Clear before inserting
            self.enrichment_output_dir_entry.insert(0, default_dir)

    def _on_gene_input_change(self, event=None):
        """基因输入框内容变化时，调用主App的自动识别功能。"""
        self.app.event_handler._auto_identify_genome_version(self.annotation_genes_textbox,  # Corrected variable name
                                                             self.selected_annotation_assembly)  # 委托给 EventHandler

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.start_annotation_button.configure(state=state)
        self.start_enrichment_button.configure(state=state)

    def start_annotation_task(self):
        """启动功能注释任务。此逻辑从gui_app.py移入。"""
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.annotation_genes_textbox.get("1.0", tk.END).strip()
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("genes_input", "")))
        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if
                    gene.strip() and not is_placeholder]
        assembly_id = self.selected_annotation_assembly.get()

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        output_path = self.annotation_output_csv_entry.get().strip() or None

        if not gene_ids: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                _("请输入要注释的基因ID。")); return
        if not assembly_id or assembly_id == _("加载中...") or assembly_id == _("无可用基因组"): self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                                    _("请选择一个基因组版本。")); return
        if not anno_types: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                  _("请至少选择一种注释类型。")); return

        task_kwargs = {
            'config': self.app.current_config, 'gene_ids': gene_ids, 'source_genome': assembly_id,
            'target_genome': assembly_id,
            'bridge_species': self.app.current_config.integration_pipeline.bridge_species_name,
            'annotation_types': anno_types, 'output_path': output_path,
            'output_dir': os.path.join(os.getcwd(), "annotation_results")
            # This 'output_dir' might conflict with 'output_path' based on run_functional_annotation's signature. Review backend.
        }

        self.app.event_handler._start_task(
            task_name=_("功能注释"),
            target_func=run_functional_annotation,
            kwargs=task_kwargs
        )

    def start_enrichment_task(self):
        """启动富集分析与绘图任务。此逻辑从gui_app.py移入，实现内聚。"""
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"));
            return

        gene_ids_text = self.annotation_genes_textbox.get("1.0", tk.END).strip()
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("genes_input", "")))
        lines = gene_ids_text.splitlines()

        assembly_id = self.selected_annotation_assembly.get()
        output_dir = self.enrichment_output_dir_entry.get().strip()
        analysis_type = self.analysis_type_var.get().lower()
        has_header = self.has_header_var.get()
        has_log2fc = self.has_log2fc_var.get()

        # 假设配置文件中有这些参数，或者在这里使用固定值/从UI获取
        plot_config = self.app.current_config.enrichment_plot

        plot_types = []
        if self.bubble_plot_var.get(): plot_types.append('bubble')
        if self.bar_plot_var.get(): plot_types.append('bar')
        if self.upset_plot_var.get(): plot_types.append('upset')
        if self.cnet_plot_var.get(): plot_types.append('cnet')

        # 解析基因列表
        if has_header and len(lines) > 0:
            lines = lines[1:]  # Skip header line

        study_gene_ids = []
        gene_log2fc_map = {} if has_log2fc else None

        try:
            if has_log2fc:
                for i, line in enumerate(lines):
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    if len(parts) >= 2:
                        gene_id, log2fc_str = parts[0], parts[1]
                        gene_log2fc_map[gene_id] = float(log2fc_str)
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

        if not study_gene_ids: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                      _("请输入要分析的基因ID。")); return
        if not assembly_id or assembly_id == _("加载中...") or assembly_id == _("无可用基因组"): self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                                                    _("请选择一个基因组版本。")); return
        if not plot_types: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                  _("请至少选择一种图表类型。")); return
        if not output_dir: self.app.ui_manager.show_error_message(_("输入缺失"),
                                                                  _("请选择图表的输出目录。")); return
        # Current Japanese Standard Time (JST): Wednesday, July 2, 2025 3:05:18 AM
        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'study_gene_ids': study_gene_ids,
            'analysis_type': analysis_type,
            'plot_types': plot_types,
            'output_dir': output_dir,
            'gene_log2fc_map': gene_log2fc_map,
            'top_n': plot_config.top_n,
            'sort_by': plot_config.sort_by,
            'show_title': plot_config.show_title,
            'width': plot_config.width,
            'height': plot_config.height,
            'file_format': plot_config.file_format,
            'collapse_transcripts': plot_config.collapse_transcripts,
        }

        self.app.event_handler._start_task(
            task_name=f"{analysis_type.upper()} {_('富集分析')}",
            target_func=run_enrichment_pipeline,
            kwargs=task_kwargs
        )