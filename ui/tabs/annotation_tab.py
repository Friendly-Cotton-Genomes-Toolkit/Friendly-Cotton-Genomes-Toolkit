# 文件路径: ui/tabs/annotation_tab.py

import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, List

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_functional_annotation
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class AnnotationTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.selected_annotation_assembly = tk.StringVar()
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=True)
        self.kegg_path_anno_var = tk.BooleanVar(value=True)
        # 2. 将 translator 传递给父类的构造函数
        super().__init__(parent, app, translator=translator)
        if self.action_button:
            # 【可选优化】这里的 _ 应该使用父类中保存的 self._，不过它在 super().__init__ 后已经可用
            self.action_button.configure(text=_("开始功能注释"), command=self.start_annotation_task)
        self.update_from_config()


    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        self.title_label = ttk.Label(parent_frame, text=_("功能注释"), font=self.app.app_title_font,
                                     bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")
        self.input_card = ttkb.LabelFrame(parent_frame, text=_("输入数据"), bootstyle="secondary")
        self.input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.input_card.grid_columnconfigure(1, weight=1)
        self.genome_version_label = ttk.Label(self.input_card, text=_("基因组版本:"), font=self.app.app_font_bold)
        self.genome_version_label.grid(row=0, column=0, sticky="w", padx=(10, 5), pady=10)
        self.assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_annotation_assembly, _("加载中..."),
                                                 bootstyle="info")
        self.assembly_dropdown.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        self.gene_id_label = ttk.Label(self.input_card, text=_("基因ID列表:"), font=self.app.app_font_bold)
        self.gene_id_label.grid(row=1, column=0, sticky="nw", padx=(10, 5), pady=10)
        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.annotation_genes_textbox = tk.Text(self.input_card, height=10, font=self.app.app_font_mono, wrap="word",
                                                relief="flat", background=text_bg, foreground=text_fg,
                                                insertbackground=text_fg)
        self.annotation_genes_textbox.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))

        initial_placeholder_text = self.app.placeholders.get("genes_input", "...")
        self.annotation_genes_textbox.after(10, lambda: self.app.ui_manager.add_placeholder(
            self.annotation_genes_textbox, initial_placeholder_text))

        self.annotation_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                       self.annotation_genes_textbox,
                                                                                                       "genes_input"))
        self.annotation_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                         self.annotation_genes_textbox,
                                                                                                         "genes_input"))
        self.annotation_genes_textbox.bind("<KeyRelease>", self._on_gene_input_change)

        self.anno_card = ttkb.LabelFrame(parent_frame, text=_("注释类型"), bootstyle="secondary")
        self.anno_card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.anno_card.grid_columnconfigure(1, weight=1)
        checkbox_frame = ttk.Frame(self.anno_card)
        checkbox_frame.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.go_check = ttkb.Checkbutton(checkbox_frame, text="GO", variable=self.go_anno_var, bootstyle="round-toggle")
        self.go_check.pack(side="left", padx=5)
        self.ipr_check = ttkb.Checkbutton(checkbox_frame, text="InterPro", variable=self.ipr_anno_var,
                                          bootstyle="round-toggle")
        self.ipr_check.pack(side="left", padx=5)
        self.kegg_ortho_check = ttkb.Checkbutton(checkbox_frame, text="KEGG Orthologs",
                                                 variable=self.kegg_ortho_anno_var, bootstyle="round-toggle")
        self.kegg_ortho_check.pack(side="left", padx=5)
        self.kegg_path_check = ttkb.Checkbutton(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                                                bootstyle="round-toggle")
        self.kegg_path_check.pack(side="left", padx=5)
        self.output_label = ttk.Label(self.anno_card, text=_("输出文件 (可选):"), font=self.app.app_font_bold)
        self.output_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.annotation_output_csv_entry = ttk.Entry(self.anno_card)
        self.annotation_output_csv_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=(5, 10))
        self.browse_button = ttkb.Button(self.anno_card, text=_("浏览..."), width=12,
                                         command=lambda: self.app.event_handler._browse_save_file(
                                             self.annotation_output_csv_entry,
                                             [("CSV files", "*.csv"), ("All files", "*.*")]), bootstyle="info-outline")
        self.browse_button.grid(row=1, column=2, padx=(0, 10), pady=5)


    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        self.app.ui_manager.update_option_menu(self.assembly_dropdown, self.selected_annotation_assembly, assembly_ids)

    def update_from_config(self):
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])
        self.annotation_output_csv_entry.delete(0, tk.END)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _on_gene_input_change(self, event=None):
        self.app.event_handler._auto_identify_genome_version(self.annotation_genes_textbox,
                                                             self.selected_annotation_assembly)

    def start_annotation_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = ""
        # 检查占位符状态
        if getattr(self.annotation_genes_textbox, 'is_placeholder', False):
            gene_ids_text = ""
        else:
            gene_ids_text = self.annotation_genes_textbox.get("1.0", tk.END).strip()

        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]

        assembly_id = self.selected_annotation_assembly.get()
        anno_types = [name for var, name in [(self.go_anno_var, 'go'), (self.ipr_anno_var, 'ipr'),
                                             (self.kegg_ortho_anno_var, 'kegg_orthologs'),
                                             (self.kegg_path_anno_var, 'kegg_pathways')] if var.get()]
        output_path = self.annotation_output_csv_entry.get().strip()
        if not output_path:
            output_path = os.path.join(os.getcwd(), "annotation_results", f"annotation_result_{assembly_id}.csv")

        if not gene_ids:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要注释的基因ID。"))
            return
        if not assembly_id or assembly_id in [_("加载中..."), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return
        if not anno_types:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。"))
            return

        task_kwargs = {
            'config': self.app.current_config,
            'gene_ids': gene_ids,
            'source_genome': assembly_id,
            'target_genome': assembly_id,
            'bridge_species': assembly_id,
            'annotation_types': anno_types,
            'output_path': output_path,
            'output_dir': os.path.dirname(output_path)
        }
        self.app.event_handler._start_task(task_name=_("功能注释"), target_func=run_functional_annotation,
                                           kwargs=task_kwargs)