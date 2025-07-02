# ui/tabs/gff_query_tab.py

import tkinter as tk
from tkinter import font as tkfont
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import TYPE_CHECKING, List

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

    def __init__(self, parent, app: "CottonToolkitApp"):
        self.style = app.style
        self.selected_gff_query_assembly = tk.StringVar()
        super().__init__(parent, app)
        self._create_base_widgets()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ttkb.Label(parent, text=_("基因/区域位点查询"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, pady=(10, 15), padx=10, sticky="n")

        main_card = ttkb.Frame(parent, bootstyle="secondary")
        main_card.grid(row=1, column=0, sticky="nsew", padx=0, pady=10)
        main_card.grid_columnconfigure((0, 1), weight=1)
        main_card.grid_rowconfigure(0, weight=1)

        # --- 输入面板 ---
        input_frame = ttkb.Frame(main_card)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)

        ttkb.Label(input_frame, text=_("输入基因ID (多行或逗号分隔):"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")

        text_bg = self.style.lookup('TFrame', 'background')
        text_fg = self.style.lookup('TLabel', 'foreground')
        self.gff_query_genes_textbox = tk.Text(input_frame, wrap="word", font=self.app.app_font_mono,
                                               background=text_bg, foreground=text_fg, relief="flat",
                                               insertbackground=text_fg)
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox, "gff_genes")
        self.gff_query_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_textbox_focus_in(e,
                                                                                                              self.gff_query_genes_textbox,
                                                                                                              "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_textbox_focus_out(e,
                                                                                                                self.gff_query_genes_textbox,
                                                                                                                "gff_genes"))
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)

        ttkb.Label(input_frame, text=_("或 输入染色体区域:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        self.gff_query_region_entry = ttkb.Entry(input_frame)
        self.gff_query_region_entry.grid(row=3, column=0, sticky="ew")
        self.app.ui_manager._add_placeholder(self.gff_query_region_entry, "gff_region")
        self.gff_query_region_entry.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_textbox_focus_in(e,
                                                                                                             self.gff_query_region_entry,
                                                                                                             "gff_region"))
        self.gff_query_region_entry.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_textbox_focus_out(e,
                                                                                                               self.gff_query_region_entry,
                                                                                                               "gff_region"))

        # --- 配置面板 ---
        config_frame = ttkb.Frame(main_card)
        config_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        config_frame.grid_columnconfigure(0, weight=1)

        ttkb.Label(config_frame, text=_("选择基因组版本:"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")
        self.gff_query_assembly_dropdown = ttkb.OptionMenu(config_frame, self.selected_gff_query_assembly,
                                                           _("加载中..."), bootstyle="info")
        self.gff_query_assembly_dropdown.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        ttkb.Label(config_frame, text=_("结果输出CSV文件:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        self.gff_query_output_csv_entry = ttkb.Entry(config_frame)
        self.gff_query_output_csv_entry.grid(row=3, column=0, sticky="ew")

        ttkb.Button(config_frame, text=_("浏览..."), width=12, bootstyle="outline",
                    command=lambda: self.app.event_handler._browse_save_file(self.gff_query_output_csv_entry,
                                                                             [(_("CSV 文件"), "*.csv")])).grid(
            row=4, column=0, pady=10, sticky="w")

        # --- 开始按钮 ---
        self.start_button = ttkb.Button(parent, text=_("开始基因查询"), command=self.start_gff_query_task,
                                        bootstyle="success")
        self.start_button.grid(row=2, column=0, padx=0, pady=(10, 20), sticky="ew")

    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """健壮地更新下拉菜单的值，避免销毁和重建控件。"""
        valid_ids = assembly_ids or [_("无可用基因组")]

        dropdown = self.gff_query_assembly_dropdown
        string_var = self.selected_gff_query_assembly

        if not (dropdown and dropdown.winfo_exists()):
            self.app.logger.warning("尝试更新GFF查询的下拉菜单，但它不存在。")
            return

        menu = dropdown['menu']
        menu.delete(0, 'end')

        for value in valid_ids:
            menu.add_command(label=value, command=lambda v=value, sv=string_var: sv.set(v))

        if string_var.get() not in valid_ids:
            string_var.set(valid_ids[0])

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'):
            self.start_button.configure(state=state)

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

        is_region_placeholder = (region_str == self.app.placeholders.get("gff_region", ""))
        is_genes_placeholder = (gene_ids_text == _(self.app.placeholders.get("gff_genes", "")))
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
        if has_region and not has_genes:  # Only process region if no genes are given
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

        # 修复 NameError: name 'output_path' is not defined
        output_path = self.gff_query_output_csv_entry.get().strip() or None

        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids_list,
            'region': region_tuple,
            'output_csv_path': output_path
        }
        self.app.event_handler._start_task(
            task_name=_("GFF基因查询"),
            target_func=run_gff_lookup,
            kwargs=task_kwargs
        )