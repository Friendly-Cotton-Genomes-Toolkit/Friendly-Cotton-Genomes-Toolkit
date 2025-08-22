# 文件路径: ui/tabs/gff_query_tab.py

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, List, Callable

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_gff_lookup
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class GFFQueryTab(BaseTab):
    """ “基因/区域位点查询”选项卡 """

    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.selected_gff_query_assembly = tk.StringVar()
        self.output_path_var = tk.StringVar()

        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            # self._ 属性在 super().__init__ 后才可用
            self.action_button.configure(text=self._("开始基因查询"), command=self.start_gff_query_task)
        self.update_from_config()

    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        """
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        self.title_label = ttkb.Label(parent, text=_("基因/区域位点查询"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        main_frame = ttk.Frame(parent)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=0)
        main_frame.grid_columnconfigure((0, 1), weight=1, uniform="group1")
        main_frame.grid_rowconfigure(0, weight=1)

        self.input_frame = ttkb.LabelFrame(main_frame, text=_("输入参数"), bootstyle="secondary")
        self.input_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_rowconfigure(1, weight=1)

        self.gene_id_label = ttkb.Label(self.input_frame, text=_("输入基因ID (多行或逗号分隔):"),
                                        font=self.app.app_font_bold)
        self.gene_id_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        text_bg = self.app.style.lookup('TFrame', 'background')

        self.gff_query_genes_textbox = tk.Text(self.input_frame, wrap="word", height=10, font=self.app.app_font_mono,
                                               relief="flat", background=text_bg,
                                               insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.gff_query_genes_textbox.after(10, lambda: self.app.ui_manager.add_placeholder(
            self.gff_query_genes_textbox,
            self.app.placeholders.get("gff_genes", "...")
        ))
        self.gff_query_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                      self.gff_query_genes_textbox,
                                                                                                      "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                        self.gff_query_genes_textbox,
                                                                                                        "gff_genes"))
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)

        self.region_label = ttkb.Label(self.input_frame, text=_("或 输入染色体区域:"), font=self.app.app_font_bold)
        self.region_label.grid(row=2, column=0, sticky="w", padx=10, pady=(10, 0))

        self.gff_query_region_entry = tk.Text(self.input_frame, height=1, wrap="none", font=self.app.app_font_mono,
                                              relief="flat", background=text_bg,
                                              insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.gff_query_region_entry.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))

        self.gff_query_region_entry.after(10, lambda: self.app.ui_manager.add_placeholder(
            self.gff_query_region_entry,
            self.app.placeholders.get("gff_region", "...")
        ))
        self.gff_query_region_entry.bind("<FocusIn>",
                                         lambda e: self.app.ui_manager._handle_focus_in(e, self.gff_query_region_entry,
                                                                                        "gff_region"))
        self.gff_query_region_entry.bind("<FocusOut>",
                                         lambda e: self.app.ui_manager._handle_focus_out(e, self.gff_query_region_entry,
                                                                                         "gff_region"))

        # 阻止在单行模式的 Text 控件中按回车键换行
        self.gff_query_region_entry.bind("<Return>", lambda e: "break")

        self.config_frame = ttkb.LabelFrame(main_frame, text=_("配置与输出"), bootstyle="secondary")
        self.config_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=10)
        self.config_frame.grid_columnconfigure(0, weight=1)

        self.genome_version_label = ttkb.Label(self.config_frame, text=_("选择基因组版本:"),
                                               font=self.app.app_font_bold)
        self.genome_version_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.gff_query_assembly_dropdown = ttkb.OptionMenu(self.config_frame, self.selected_gff_query_assembly,
                                                           _("加载中..."), bootstyle="info")
        self.gff_query_assembly_dropdown.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.output_path_label = ttkb.Label(self.config_frame, text=_("结果输出CSV文件:"), font=self.app.app_font_bold)
        self.output_path_label.grid(row=2, column=0, sticky="w", padx=10, pady=(10, 0))
        # 【修复】移除了 foreground=text_fg
        self.gff_query_output_csv_entry = ttkb.Entry(self.config_frame, textvariable=self.output_path_var,
                                                     font=self.app.app_font_mono)
        self.gff_query_output_csv_entry.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        self.browse_button = ttkb.Button(self.config_frame, text=_("浏览..."), width=12, bootstyle="info-outline",
                                         command=lambda: self.app.event_handler._browse_save_file(
                                             self.gff_query_output_csv_entry, [(_("CSV 文件"), "*.csv")]))
        self.browse_button.grid(row=4, column=0, sticky='e', padx=10, pady=5)



    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        valid_ids = assembly_ids or [_("无可用基因组")]
        dropdown = self.gff_query_assembly_dropdown
        string_var = self.selected_gff_query_assembly
        if not (dropdown and dropdown.winfo_exists()): return
        menu = dropdown['menu']
        menu.delete(0, 'end')
        for value in valid_ids:
            menu.add_command(label=value, command=lambda v=value, sv=string_var: sv.set(v))
        if string_var.get() not in valid_ids:
            string_var.set(valid_ids[0])

    def _on_gff_query_gene_input_change(self, event=None):
        self.app.event_handler._auto_identify_genome_version(self.gff_query_genes_textbox,
                                                             self.selected_gff_query_assembly)

    def start_gff_query_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        assembly_id = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_textbox.get("1.0", tk.END).strip()
        region_str = self.gff_query_region_entry.get().strip()
        output_path = self.output_path_var.get().strip()
        if not output_path:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定结果文件的保存路径。"))
            return

        is_region_placeholder = (region_str == self.app.placeholders.get("gff_region", ""))
        is_genes_placeholder = (gene_ids_text == self.app.placeholders.get("gff_genes", ""))
        has_genes = bool(gene_ids_text and not is_genes_placeholder)
        has_region = bool(region_str and not is_region_placeholder)

        if not has_genes and not has_region:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("必须输入基因ID列表或染色体区域之一。"))
            return
        if has_genes and has_region:
            self.app.ui_manager.show_warning_message(_("输入冲突"), _("将优先使用基因ID列表进行查询。"))
            region_str = ""

        gene_ids_list = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if
                         g.strip()] if has_genes else None
        region_tuple = None

        if has_region and not has_genes:
            try:
                chrom, pos_range = region_str.split(':')
                start, end = map(int, pos_range.split('-'))
                region_tuple = (chrom.strip(), start, end)
            except ValueError:
                self.app.ui_manager.show_error_message(_("输入错误"), _("区域格式不正确。请使用 'Chr:Start-End' 格式。"))
                return

        if not assembly_id or assembly_id in [_("加载中..."), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return

        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids_list,
            'region': region_tuple,
            'output_csv_path': output_path
        }
        self.app.event_handler._start_task(task_name=_("GFF基因查询"), target_func=run_gff_lookup, kwargs=task_kwargs)