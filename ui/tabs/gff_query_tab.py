# ui/tabs/gff_query_tab.py

import tkinter as tk
from tkinter import ttk, font as tkfont # Import ttk and tkfont
import ttkbootstrap as ttkb # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants

from typing import TYPE_CHECKING, List

# 导入后台任务函数
from cotton_toolkit.pipelines import run_gff_lookup
from ui.tabs.base_tab import BaseTab # Import BaseTab

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class GFFQueryTab(BaseTab): # Changed from ctk.CTkFrame to ttk.Frame
    """ “基因位点查询”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_gff_query_assembly = tk.StringVar()
        super().__init__(parent, app)
        self._create_base_widgets()
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(1, weight=1) # Adjusted row configuration for scrollable_frame

        ttk.Label(parent_frame, text=_("基因/区域位点查询"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(10, 5), padx=20, sticky="n")

        main_frame = ttk.Frame(parent_frame) # Changed from self to parent_frame
        main_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_frame.grid_columnconfigure((0, 1), weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)
        ttk.Label(input_frame, text=_("输入基因ID (多行或逗号分隔):"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")
        # Use tk.Text for textbox
        # 修复：tk.Text 的背景色和前景色通过 style.lookup 获取
        self.gff_query_genes_textbox = tk.Text(input_frame, font=self.app.app_font, wrap="word",
                                               background=self.app.style.lookup('TText', 'background'),
                                               foreground=self.app.style.lookup('TText', 'foreground'),
                                               relief="flat")
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox, "gff_genes")
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda e: self.app.ui_manager._clear_placeholder(self.gff_query_genes_textbox,
                                                                                           "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda e: self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox,
                                                                                         "gff_genes"))
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)

        ttk.Label(input_frame, text=_("或 输入染色体区域:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        self.gff_query_region_entry = ttk.Entry(input_frame, font=self.app.app_font)
        self.gff_query_region_entry.grid(row=3, column=0, sticky="ew")
        # For placeholder in Entry, you need to implement focusin/focusout events manually as done for Textbox
        self.gff_query_region_entry.insert(0, self.app.placeholders.get("gff_region", ""))
        self.gff_query_region_entry.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_textbox_focus_in(e, self.gff_query_region_entry, "gff_region"))
        self.gff_query_region_entry.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_textbox_focus_out(e, self.gff_query_region_entry, "gff_region"))


        config_frame = ttk.Frame(main_frame)
        config_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        config_frame.grid_columnconfigure(0, weight=1)
        ttk.Label(config_frame, text=_("选择基因组版本:"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w")
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        self.gff_query_assembly_dropdown = ttkb.OptionMenu(
            config_frame, self.selected_gff_query_assembly,
            _("加载中..."),  # 默认值
            *[_("加载中...")],  # 选项列表
            bootstyle="info"
        )
        self.gff_query_assembly_dropdown.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(config_frame, text=_("结果输出CSV文件:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="w", pady=(15, 5))
        # ttk.Entry 并不直接支持 placeholder_text，需要自定义逻辑
        self.gff_query_output_csv_entry = ttk.Entry(config_frame, font=self.app.app_font)
        self.gff_query_output_csv_entry.grid(row=3, column=0, sticky="ew")
        # 修复：ttkb.Button 不支持直接的 font 参数
        ttkb.Button(config_frame, text=_("浏览..."), width=12, bootstyle="outline",
                      command=lambda: self.app._browse_directory(self.gff_query_output_csv_entry)).grid(
            row=4, column=0, pady=10, sticky="w")

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_button = ttkb.Button(
            parent_frame, text=_("开始基因查询"), # Changed from self to parent_frame
            command=self.start_gff_query_task, bootstyle="success"
        )
        self.start_button.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew") # Adjusted row for parent_frame


    def _setup_placeholders(self):
        """设置输入框的占位符。(Deprecated, moved to ui_manager)"""
        # This function should ideally be removed as placeholder management is in UIManager
        # For compatibility if still called, it will just re-call UIManager's methods.
        self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox, "gff_genes")
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda e: self.app.ui_manager._clear_placeholder(self.gff_query_genes_textbox,
                                                                                "gff_genes"))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda e: self.app.ui_manager._add_placeholder(self.gff_query_genes_textbox,
                                                                              "gff_genes"))


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        old_dropdown = self.gff_query_assembly_dropdown
        parent_frame = old_dropdown.master
        grid_info = {}
        pack_info = {}
        manager_type = None

        if old_dropdown and old_dropdown.winfo_exists():
            if hasattr(old_dropdown, 'winfo_manager'):
                manager_type = old_dropdown.winfo_manager()
                if manager_type == "grid":
                    grid_info = old_dropdown.grid_info()
                elif manager_type == "pack":
                    pack_info = old_dropdown.pack_info()
        else:
            # If the dropdown hasn't been created yet or was destroyed,
            # we need to ensure the _create_widgets runs first or handle initial creation.
            # This path handles initial creation implicitly by using fixed grid coordinates.
            pass

        variable = self.selected_gff_query_assembly
        command = old_dropdown.cget('command') if 'command' in old_dropdown.configure() else None
        bootstyle = old_dropdown.cget('bootstyle') if old_dropdown and old_dropdown.winfo_exists() else "info"

        if old_dropdown and old_dropdown.winfo_exists():
            old_dropdown.destroy()  # 销毁旧的下拉菜单

        if not assembly_ids:
            new_values = [_("加载中...")]
        else:
            new_values = assembly_ids

        if variable.get() not in new_values:
            variable.set(new_values[0] if new_values else "")

        # 重新创建 ttkb.OptionMenu
        self.gff_query_assembly_dropdown = ttkb.OptionMenu(
            parent_frame,
            variable,
            variable.get(),  # 默认显示值
            *new_values,  # 新的选项列表
            command=command,
            bootstyle=bootstyle
        )

        # 重新应用布局
        if grid_info:
            self.gff_query_assembly_dropdown.grid(**{k: v for k, v in grid_info.items() if k != 'in'})
        elif pack_info:
            self.gff_query_assembly_dropdown.pack(**{k: v for k, v in pack_info.items() if k != 'in'})
        else:
            # Fallback grid position for initial creation
            # This should match where it's initially gridded in _create_widgets
            self.gff_query_assembly_dropdown.grid(row=1, column=0, sticky="ew", pady=(5, 0)) # Assuming it's in config_frame


    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.start_button.configure(state=state)


    def _on_gff_query_gene_input_change(self, event=None):
        """GFF查询输入框基因ID变化时触发基因组自动识别。"""
        self.app.event_handler._auto_identify_genome_version(self.gff_query_genes_textbox,
                                                             self.selected_gff_query_assembly)  # 委托给 EventHandler


    def start_gff_query_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        assembly_id = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_textbox.get("1.0", tk.END).strip()
        region_str = self.gff_query_region_entry.get().strip()

        # Check if region_str is still the placeholder text
        is_region_placeholder = (region_str == self.app.placeholders.get("gff_region", ""))

        is_genes_placeholder = (gene_ids_text == _(self.app.placeholders.get("gff_genes", "")))
        has_genes = bool(gene_ids_text and not is_genes_placeholder)
        has_region = bool(region_str and not is_region_placeholder)

        if not has_genes and not has_region:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("必须输入基因ID列表或染色体区域之一。"))
            return
        if has_genes and has_region:
            self.app.ui_manager.show_warning_message(_("输入冲突"), _("请只使用基因ID列表或区域查询之一，将优先使用基因ID列表。"))
            region_str = "" # Prioritize genes, clear region if both are present

        gene_ids_list = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if
                         g.strip()] if has_genes else None
        region_tuple = None
        if has_region:
            try:
                chrom, pos_range = region_str.split(':')
                start, end = map(int, pos_range.split('-'))
                region_tuple = (chrom.strip(), start, end)
            except ValueError:
                self.app.ui_manager.show_error_message(_("输入错误"), _("区域格式不正确。请使用 'Chr:Start-End' 格式。"))
                return

        if not assembly_id or assembly_id in [_("加载中...")]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return

        # 假设后端函数叫 run_gff_lookup
        # from cotton_toolkit.pipelines import run_gff_lookup # 已经在文件顶部导入
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