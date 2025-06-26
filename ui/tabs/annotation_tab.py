# cotton_tool/ui/tabs/annotation_tab.py

import os
import re
import tkinter as tk
import customtkinter as ctk
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


class AnnotationTab(BaseTab): # 继承自 BaseTab
    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, app)

    def _create_widgets(self):
        parent_frame = self.scrollable_frame

        # 在顶部添加一个标题
        ctk.CTkLabel(parent_frame, text=_("功能注释与富集分析"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(5, 15), padx=10, sticky="n")

        # 后续卡片的 row 从 1 开始
        input_card = ctk.CTkFrame(parent_frame, border_width=0)
        input_card.grid(row=1, column=0, sticky="ew", padx=5, pady=(5, 10))
        input_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(input_card, text=_("输入数据"), font=self.app.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                       sticky="w", padx=10,
                                                                                       pady=(10, 15))
        ctk.CTkLabel(input_card, text=_("基因组版本:"), font=self.app.app_font).grid(row=1, column=0, sticky="w",
                                                                                     padx=(15, 5), pady=10)
        self.selected_annotation_assembly = tk.StringVar()
        self.assembly_dropdown = ctk.CTkOptionMenu(
            input_card, variable=self.selected_annotation_assembly, values=[_("加载中...")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(input_card, text=_("基因ID列表:"), font=self.app.app_font).grid(row=2, column=0, sticky="nw",
                                                                                     padx=(15, 5), pady=10)
        self.annotation_genes_textbox = ctk.CTkTextbox(input_card, height=180, font=self.app.app_font_mono, wrap="word")
        self.annotation_genes_textbox.grid(row=2, column=1, sticky="ew", padx=10, pady=(5, 10))
        self.app._add_placeholder(self.annotation_genes_textbox, "genes_input")

        anno_card = ctk.CTkFrame(parent_frame, border_width=0)
        anno_card.grid(row=2, column=0, sticky="ew", padx=5, pady=10)
        anno_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(anno_card, text=_("功能注释"), font=self.app.app_font_bold).grid(row=0, column=0, sticky="w",
                                                                                      padx=10, pady=(10, 15))
        checkbox_frame = ctk.CTkFrame(anno_card, fg_color="transparent")
        checkbox_frame.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.go_anno_var = tk.BooleanVar(value=True);
        self.ipr_anno_var = tk.BooleanVar(value=True);
        self.kegg_ortho_anno_var = tk.BooleanVar(value=True);
        self.kegg_path_anno_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(checkbox_frame, text="GO", variable=self.go_anno_var, font=self.app.app_font).pack(side="left",
                                                                                                           padx=5)
        ctk.CTkCheckBox(checkbox_frame, text="InterPro", variable=self.ipr_anno_var, font=self.app.app_font).pack(
            side="left", padx=5)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                        font=self.app.app_font).pack(side="left", padx=5)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                        font=self.app.app_font).pack(side="left", padx=5)
        self.annotation_output_csv_entry = ctk.CTkEntry(anno_card,
                                                        placeholder_text=_("输出注释结果路径 (可选, .csv/.xlsx)"))
        self.annotation_output_csv_entry.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.start_annotation_button = ctk.CTkButton(anno_card, text=_("开始功能注释"),
                                                     command=self.start_annotation_task)
        self.start_annotation_button.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 15))

        enrich_card = ctk.CTkFrame(parent_frame, border_width=0)
        enrich_card.grid(row=3, column=0, sticky="ew", padx=5, pady=10)
        enrich_card.grid_columnconfigure(1, weight=3);
        enrich_card.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(enrich_card, text=_("富集分析与绘图"), font=self.app.app_font_bold).grid(row=0, column=0,
                                                                                              columnspan=4, sticky="w",
                                                                                              padx=10, pady=(10, 15))
        ctk.CTkLabel(enrich_card, text=_("输入格式:"), font=self.app.app_font).grid(row=1, column=0, padx=15, pady=5,
                                                                                    sticky="w")
        input_format_frame = ctk.CTkFrame(enrich_card, fg_color="transparent")
        input_format_frame.grid(row=1, column=1, columnspan=3, padx=10, pady=5, sticky="w")
        self.has_header_var = tk.BooleanVar(value=False);
        self.has_log2fc_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(input_format_frame, text=_("包含表头"), variable=self.has_header_var,
                        font=self.app.app_font).pack(side="left", padx=(0, 15))
        ctk.CTkCheckBox(input_format_frame, text=_("包含Log2FC"), variable=self.has_log2fc_var,
                        font=self.app.app_font).pack(side="left")
        ctk.CTkLabel(enrich_card, text=_("分析类型:"), font=self.app.app_font).grid(row=2, column=0, padx=15, pady=5,
                                                                                    sticky="w")
        self.analysis_type_var = tk.StringVar(value="GO")
        ctk.CTkSegmentedButton(enrich_card, values=["GO", "KEGG"], variable=self.analysis_type_var).grid(row=2,
                                                                                                         column=1,
                                                                                                         padx=10,
                                                                                                         pady=5,
                                                                                                         sticky="w")
        ctk.CTkLabel(enrich_card, text=_("绘图类型:"), font=self.app.app_font).grid(row=3, column=0, padx=15, pady=5,
                                                                                    sticky="w")
        plot_type_frame = ctk.CTkFrame(enrich_card, fg_color="transparent")
        plot_type_frame.grid(row=3, column=1, columnspan=3, padx=10, pady=5, sticky="w")

        # 定义所有绘图类型的变量
        self.bubble_plot_var = tk.BooleanVar(value=True)
        self.bar_plot_var = tk.BooleanVar(value=True)
        self.upset_plot_var = tk.BooleanVar(value=False)  # Upset图默认为不勾选
        self.cnet_plot_var = tk.BooleanVar(value=False)  # Cnet图默认为不勾选

        # 创建所有复选框
        ctk.CTkCheckBox(plot_type_frame, text=_("气泡图"), variable=self.bubble_plot_var, font=self.app.app_font).pack(
            side="left", padx=(0, 15))
        ctk.CTkCheckBox(plot_type_frame, text=_("条形图"), variable=self.bar_plot_var, font=self.app.app_font).pack(
            side="left", padx=(0, 15))
        # 新增的复选框
        ctk.CTkCheckBox(plot_type_frame, text=_("Upset图"), variable=self.upset_plot_var, font=self.app.app_font).pack(
            side="left", padx=(0, 15))
        ctk.CTkCheckBox(plot_type_frame, text=_("网络图(Cnet)"), variable=self.cnet_plot_var,
                        font=self.app.app_font).pack(
            side="left")

        ctk.CTkLabel(enrich_card, text=_("输出目录:"), font=self.app.app_font).grid(row=4, column=0, padx=15, pady=5,
                                                                                    sticky="w")
        self.enrichment_output_dir_entry = ctk.CTkEntry(enrich_card)
        self.enrichment_output_dir_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 5), pady=5)
        ctk.CTkButton(enrich_card, text=_("浏览..."), width=100,
                      command=lambda: self.app._browse_directory(self.enrichment_output_dir_entry)).grid(row=4,
                                                                                                         column=3,
                                                                                                         padx=(0, 10),
                                                                                                         pady=5)
        self.start_enrichment_button = ctk.CTkButton(enrich_card, text=_("开始富集分析"),
                                                     command=self.start_enrichment_task)
        self.start_enrichment_button.grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(15, 15))


    def update_assembly_dropdowns(self, assembly_ids: list):
        if not assembly_ids: assembly_ids = [_("加载中...")]
        self.assembly_dropdown.configure(values=assembly_ids)
        if assembly_ids: self.selected_annotation_assembly.set(assembly_ids[0])


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        if self.app.current_config:
            default_dir = os.path.join(os.getcwd(), "enrichment_results")
            self.enrichment_output_dir_entry.insert(0, default_dir)


    def _on_gene_input_change(self, event=None):
        """【新增】基因输入框内容变化时，调用主App的自动识别功能。"""
        self.app._auto_identify_genome_version(self.genes_textbox, self.selected_annotation_assembly)



    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.start_annotation_button.configure(state=state)
        self.start_enrichment_button.configure(state=state)

    def start_annotation_task(self):
        """【新增】启动功能注释任务。此逻辑从gui_app.py移入。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.genes_textbox.get("1.0", tk.END).strip()
        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        assembly_id = self.selected_annotation_assembly.get()

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        output_path = self.annotation_output_csv_entry.get().strip() or None

        if not gene_ids: self.app.show_error_message(_("输入缺失"), _("请输入要注释的基因ID。")); return
        if not assembly_id or assembly_id == _("加载中..."): self.app.show_error_message(_("输入缺失"),
                                                                                         _("请选择一个基因组版本。")); return
        if not anno_types: self.app.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。")); return

        task_kwargs = {
            'config': self.app.current_config, 'gene_ids': gene_ids, 'source_genome': assembly_id,
            'target_genome': assembly_id,
            'bridge_species': self.app.current_config.integration_pipeline.bridge_species_name,
            'annotation_types': anno_types, 'output_path': output_path,
            'output_dir': os.path.join(os.getcwd(), "annotation_results")
        }

        self.app._start_task(
            task_name=_("功能注释"),
            target_func=run_functional_annotation,
            kwargs=task_kwargs
        )

    def start_enrichment_task(self):
        """启动富集分析与绘图任务。此逻辑从gui_app.py移入，实现内聚。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"));
            return

        gene_ids_text = self.genes_textbox.get("1.0", tk.END).strip()
        assembly_id = self.selected_annotation_assembly.get()
        output_dir = self.enrichment_output_dir_entry.get().strip()
        analysis_type = self.analysis_type_var.get().lower()
        has_header = self.has_header_var.get()
        has_log2fc = self.has_log2fc_var.get()

        # 假设配置文件中有这些参数，或者在这里使用固定值/从UI获取
        # 为了简化，我们使用一些合理的默认值
        plot_config = self.app.current_config.enrichment_plot

        plot_types = []
        if self.bubble_plot_var.get(): plot_types.append('bubble')
        if self.bar_plot_var.get(): plot_types.append('bar')
        if self.upset_plot_var.get(): plot_types.append('upset')
        if self.cnet_plot_var.get(): plot_types.append('cnet')

        # 解析基因列表
        lines = gene_ids_text.splitlines()
        if has_header and len(lines) > 1:
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
            self.app.show_error_message(_("输入格式错误"), str(e));
            return

        study_gene_ids = sorted(list(set(study_gene_ids)))

        if not study_gene_ids: self.app.show_error_message(_("输入缺失"), _("请输入要分析的基因ID。")); return
        if not assembly_id or assembly_id == _("加载中..."): self.app.show_error_message(_("输入缺失"),
                                                                                         _("请选择一个基因组版本。")); return
        if not plot_types: self.app.show_error_message(_("输入缺失"), _("请至少选择一种图表类型。")); return
        if not output_dir: self.app.show_error_message(_("输入缺失"), _("请选择图表的输出目录。")); return

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

        self.app._start_task(
            task_name=f"{analysis_type.upper()} {_('富集分析')}",
            target_func=run_enrichment_pipeline,
            kwargs=task_kwargs
        )