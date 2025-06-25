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

        # 1. 移动相关的 Tkinter 变量
        self.selected_gff_query_assembly = tk.StringVar()

        # 2. 调用UI创建和初始化方法
        self._create_widgets()
        self.update_from_config()
        self._setup_placeholders()

    def _create_widgets(self):
        """创建GFF基因查询选项卡的全部UI控件。"""
        self.grid_columnconfigure((0, 1), weight=1)

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold
        assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [_("无可用版本")]

        # Part 1: 输入区域
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_frame, text=_("输入基因ID (每行一个或逗号分隔，与区域查询二选一):"), font=app_font_bold).grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        self.gff_query_genes_textbox = ctk.CTkTextbox(input_frame, height=120, font=app_font, wrap="word")
        self.app._bind_mouse_wheel_to_scrollable(self.gff_query_genes_textbox)
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", rowspan=2, padx=(0, 10))

        # 绑定事件到本类的方法
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)

        ctk.CTkLabel(input_frame, text=_("输入染色体区域 (例如: Chr01:1000-2000，与基因ID查询二选一):"),
                     font=app_font_bold).grid(row=3, column=0, sticky="w", pady=(10, 5))
        self.gff_query_region_entry = ctk.CTkEntry(input_frame, font=app_font,
                                                   placeholder_text=_("例如: A03:1000-2000"))
        self.gff_query_region_entry.grid(row=4, column=0, sticky="ew", padx=(0, 10))

        # Part 2: 基因组选择与输出
        ctk.CTkLabel(input_frame, text=_("选择基因组版本:"), font=app_font_bold).grid(row=0, column=1, sticky="w",
                                                                                      pady=(0, 5), padx=(10, 0))
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame, variable=self.selected_gff_query_assembly, values=assembly_ids,
            font=app_font, dropdown_font=app_font
        )
        self.gff_query_assembly_dropdown.grid(row=1, column=1, sticky="new", padx=(10, 0))

        output_frame = ctk.CTkFrame(input_frame)
        output_frame.grid(row=2, column=1, rowspan=3, sticky="nsew", padx=(10, 0), pady=(10, 0))
        output_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                        sticky="w", pady=(0, 5))
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=app_font,
                                                       placeholder_text=_("不填则自动命名"))
        self.gff_query_output_csv_entry.grid(row=1, column=0, columnspan=2, sticky="ew")

        ctk.CTkButton(output_frame, text=_("浏览..."), width=100, font=app_font,
                      command=lambda: self.app._browse_directory(self.gff_query_output_csv_entry)).grid(row=2, column=0,
                                                                                                        columnspan=2,
                                                                                                        pady=10)

        # Part 3: 开始按钮
        ctk.CTkButton(self, text=_("开始基因查询"), font=app_font_bold, command=self.start_gff_query_task).grid(row=1,
                                                                                                                column=0,
                                                                                                                columnspan=2,
                                                                                                                padx=10,
                                                                                                                pady=15,
                                                                                                                sticky="e")

    def _setup_placeholders(self):
        """设置输入框的占位符。"""
        # 调用主应用的通用占位符方法
        self.app._add_placeholder(self.gff_query_genes_textbox, self.app.placeholder_key_gff_genes)
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda e: self.app._clear_placeholder(self.gff_query_genes_textbox,
                                                                                self.app.placeholder_key_gff_genes))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda e: self.app._add_placeholder(self.gff_query_genes_textbox,
                                                                              self.app.placeholder_key_gff_genes))

    def update_from_config(self):
        """由主应用调用，在配置加载时更新本页面。"""
        self.app._log_to_viewer("DEBUG: GFFQueryTab received update_from_config call.", "DEBUG")
        pass

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """由主应用调用，用于更新本选项卡内的基因组下拉菜单。"""
        current_assembly = self.selected_gff_query_assembly.get()
        if current_assembly not in assembly_ids:
            self.selected_gff_query_assembly.set(assembly_ids[0] if "无可用" not in assembly_ids[0] else "")
        self.gff_query_assembly_dropdown.configure(values=assembly_ids)

    def _on_gff_query_gene_input_change(self, event=None):
        """GFF查询输入框基因ID变化时触发基因组自动识别。"""
        # 调用主应用的通用识别方法，并传入本 Tab 的控件和变量
        self.app._auto_identify_genome_version(self.gff_query_genes_textbox, self.selected_gff_query_assembly)

    def start_gff_query_task(self):
        """启动GFF基因查询任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        assembly_id = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_textbox.get("1.0", tk.END).strip()
        region_str = self.gff_query_region_entry.get().strip()
        output_path = self.gff_query_output_csv_entry.get().strip() or None

        gene_ids_list = None
        region_tuple = None

        # 检查占位符
        is_placeholder = (gene_ids_text == _(self.app.placeholders.get(self.app.placeholder_key_gff_genes, "")))

        has_genes = bool(gene_ids_text and not is_placeholder)
        has_region = bool(region_str)

        if not has_genes and not has_region:
            self.app.show_error_message(_("输入缺失"), _("必须输入基因ID列表或染色体区域之一。"))
            return

        if has_genes and has_region:
            self.app.show_warning_message(_("输入冲突"), _("请只使用基因ID列表或区域查询之一，将优先使用基因ID列表。"))
            region_str = ""  # 优先使用基因ID

        if has_genes:
            gene_ids_list = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        elif has_region:
            try:
                chrom, pos_range = region_str.split(':')
                start, end = map(int, pos_range.split('-'))
                region_tuple = (chrom.strip(), start, end)
            except ValueError:
                self.app.show_error_message(_("输入错误"), _("区域格式不正确。请使用 'Chr:Start-End' 格式。"))
                return

        if not assembly_id or assembly_id == _("无可用版本"):
            self.app.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return

        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids_list,
            'region': region_tuple,
            'output_csv_path': output_path,
        }

        self.app._start_task(
            task_name=_("GFF基因查询"),
            target_func=run_gff_lookup,
            kwargs=task_kwargs
        )