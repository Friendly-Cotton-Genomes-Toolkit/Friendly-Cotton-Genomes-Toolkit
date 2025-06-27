# ui/tabs/gff_query_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

# 导入后台任务函数
from cotton_toolkit.pipelines import run_gff_lookup

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class GFFQueryTab(ctk.CTkFrame):
    """ “基因位点查询”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)
        self.selected_gff_query_assembly = tk.StringVar()
        self._create_widgets()
        self.update_from_config()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text=_("基因/区域位点查询"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(10, 5), padx=20, sticky="n")

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_frame.grid_columnconfigure((0, 1), weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text=_("输入基因ID (多行或逗号分隔):"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")
        self.gff_query_genes_textbox = ctk.CTkTextbox(input_frame, font=self.app.app_font, wrap="word")
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox, "gff_genes")
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda e: self.app.ui_manager._clear_placeholder(self.gff_query_genes_textbox,
                                                                                           "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda e: self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox,
                                                                                         "gff_genes"))
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)

        ctk.CTkLabel(input_frame, text=_("或 输入染色体区域:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        self.gff_query_region_entry = ctk.CTkEntry(input_frame, font=self.app.app_font,
                                                   placeholder_text=self.app.placeholders.get("gff_region", ""))
        self.gff_query_region_entry.grid(row=3, column=0, sticky="ew")

        config_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        config_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        config_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(config_frame, text=_("选择基因组版本:"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(
            config_frame, variable=self.selected_gff_query_assembly, values=[_("加载中...")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.gff_query_assembly_dropdown.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ctk.CTkLabel(config_frame, text=_("结果输出CSV文件:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        self.gff_query_output_csv_entry = ctk.CTkEntry(config_frame, font=self.app.app_font,
                                                       placeholder_text=_("不填则自动命名"))
        self.gff_query_output_csv_entry.grid(row=3, column=0, sticky="ew")
        ctk.CTkButton(config_frame, text=_("浏览..."), width=100, font=self.app.app_font,
                      command=lambda: self.app._browse_directory(self.gff_query_output_csv_entry)).grid(
            row=4, column=0, pady=10, sticky="w")

        self.start_button = ctk.CTkButton(
            self, text=_("开始基因查询"), font=self.app.app_font_bold, height=40,
            command=self.start_gff_query_task
        )
        self.start_button.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew")


    def _setup_placeholders(self):
        """设置输入框的占位符。"""
        # 调用主应用的通用占位符方法
        self.app._add_placeholder(self.gff_query_genes_textbox, "gff_genes")
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda e: self.app._clear_placeholder(self.gff_query_genes_textbox,
                                                                                "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda e: self.app._add_placeholder(self.gff_query_genes_textbox,
                                                                              "gff_genes"))


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))


    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        current_assembly = self.selected_gff_query_assembly.get()
        if not assembly_ids: assembly_ids = [_("加载中...")]
        if current_assembly not in assembly_ids:
            self.selected_gff_query_assembly.set(assembly_ids[0])
        self.gff_query_assembly_dropdown.configure(values=assembly_ids)


    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.start_button.configure(state=state)


    def _on_gff_query_gene_input_change(self, event=None):
        """GFF查询输入框基因ID变化时触发基因组自动识别。"""
        self.app.event_handler._auto_identify_genome_version(self.gff_query_genes_textbox,
                                                             self.selected_gff_query_assembly)  # 委托给 EventHandler


    def start_gff_query_task(self):
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        assembly_id = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_textbox.get("1.0", tk.END).strip()
        region_str = self.gff_query_region_entry.get().strip()
        output_path = self.gff_query_output_csv_entry.get().strip() or None

        is_placeholder = (gene_ids_text == _(self.app.placeholders.get("gff_genes", "")))
        has_genes = bool(gene_ids_text and not is_placeholder)
        has_region = bool(region_str)

        if not has_genes and not has_region:
            self.app.show_error_message(_("输入缺失"), _("必须输入基因ID列表或染色体区域之一。"))
            return
        if has_genes and has_region:
            self.app.show_warning_message(_("输入冲突"), _("请只使用基因ID列表或区域查询之一，将优先使用基因ID列表。"))
            region_str = ""

        gene_ids_list = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if
                         g.strip()] if has_genes else None
        region_tuple = None
        if has_region:
            try:
                chrom, pos_range = region_str.split(':')
                start, end = map(int, pos_range.split('-'))
                region_tuple = (chrom.strip(), start, end)
            except ValueError:
                self.app.show_error_message(_("输入错误"), _("区域格式不正确。请使用 'Chr:Start-End' 格式。"))
                return

        if not assembly_id or assembly_id in [_("加载中...")]:
            self.app.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return

        # 假设后端函数叫 run_gff_lookup
        from cotton_toolkit.pipelines import run_gff_lookup
        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids_list,
            'region': region_tuple,
            'output_csv_path': output_path
        }
        self.app.event_handler._start_task(  # 委托给 EventHandler
            task_name=_("GFF基因查询"),
            target_func=run_gff_lookup,
            kwargs=task_kwargs
        )
