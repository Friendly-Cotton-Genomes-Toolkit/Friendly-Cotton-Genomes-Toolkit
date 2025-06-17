# cotton_tool/ui/tabs/annotation_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING
import os

# 使用 TYPE_CHECKING 可以在不引起循环导入的情况下，为IDE提供类型提示，
# 这对于代码补全和静态分析非常有帮助。
if TYPE_CHECKING:
    from gui_app import CottonToolkitApp

# 尝试从Python的内建模块导入全局翻译函数 `_`。
# 如果失败（例如在非GUI环境或测试中），则定义一个不做任何操作的占位函数。
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AnnotationTab(ctk.CTkFrame):
    """
    功能注释与富集分析”选项卡的主界面类。
    这个类负责创建该选项卡内的所有UI控件，并将其逻辑连接到主App实例。
    """

    def __init__(self, parent, app: "CottonToolkitApp"):
        """
        AnnotationTab的构造函数。

        Args:
            parent: 父级控件，即放置此选项卡的 CTkTabview。
            app (CottonToolkitApp): 主应用程序的实例，用于访问共享变量、方法和配置。
        """
        # 调用父类的构造函数，设置此Frame为透明背景
        super().__init__(parent, fg_color="transparent")
        # 保存主应用实例的引用，以便后续调用
        self.app = app
        # 让此Frame填充整个父容器
        self.pack(fill="both", expand=True)
        # 调用方法来创建所有UI控件
        self._create_widgets()

    def _create_widgets(self):
        """
        【全功能版】创建“功能注释与富集分析”选项卡的完整UI。
        此方法负责布局和初始化此选项卡内的所有控件。
        """
        # 配置网格布局，使第一列（也是唯一一列）可以随窗口大小缩放
        self.grid_columnconfigure(0, weight=1)

        # --- 从主App实例获取共享资源 ---
        # 获取已加载的基因组版本列表，如果未加载则显示提示信息
        assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [_("无可用版本")]
        # 获取在主App中定义的全局字体
        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold

        # --- Part 1: 公共输入区 (基因ID和基因组选择) ---
        # 创建一个Frame来容纳顶部的所有输入控件
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        top_frame.grid_columnconfigure(0, weight=1)  # 让输入框可以横向填充

        # 基因ID输入的标签
        ctk.CTkLabel(top_frame, text=_("输入基因ID (每行一个或逗号分隔):"), font=app_font_bold).grid(row=0, column=0,
                                                                                                     sticky="w",
                                                                                                     pady=(0, 5))

        # 基因ID输入文本框，这是所有注释和富集功能的数据源头
        genes_textbox = ctk.CTkTextbox(top_frame, height=180, font=app_font, wrap="word")
        genes_textbox.grid(row=1, column=0, sticky="nsew")
        # 将此文本框的引用保存到主App实例的属性中，以便其他方法（如任务启动函数）可以访问它
        self.app.annotation_genes_textbox = genes_textbox

        # 为输入框添加占位符和事件绑定
        self.app._add_placeholder(genes_textbox, self.app.placeholder_key_homology)
        genes_textbox.bind("<FocusIn>",
                           lambda e: self.app._clear_placeholder(genes_textbox, self.app.placeholder_key_homology))
        genes_textbox.bind("<FocusOut>",
                           lambda e: self.app._add_placeholder(genes_textbox, self.app.placeholder_key_homology))
        genes_textbox.bind("<KeyRelease>", self.app._on_annotation_gene_input_change)  # 每次键盘输入后尝试自动识别基因组版本

        # 创建一个Frame来容纳输入框下方的两个开关选项
        input_options_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        input_options_frame.grid(row=2, column=0, sticky="w", padx=0, pady=(10, 0))

        ctk.CTkSwitch(input_options_frame, text=_("输入包含表头 (将跳过首行)"),
                      variable=self.app.has_header_var).pack(side="left")

        ctk.CTkSwitch(input_options_frame, text=_("包含Log2FC (格式: 基因ID,Log2FC)"),
                      variable=self.app.has_log2fc_var).pack(side="left", padx=15)

        # --- 【新增】合并转录本的开关 ---
        ctk.CTkSwitch(input_options_frame, text=_("将RNA合并到基因"),
                      variable=self.app.collapse_transcripts_var).pack(side="left", padx=15)

        # 基因组版本选择的标签
        ctk.CTkLabel(top_frame, text=_("选择基因组版本:"), font=app_font_bold).grid(row=3, column=0, sticky="w",
                                                                                    pady=(10, 5))
        # 基因组版本下拉菜单
        self.app.annotation_assembly_dropdown = ctk.CTkOptionMenu(
            top_frame, variable=self.app.selected_annotation_assembly, values=assembly_ids,
            font=app_font, dropdown_font=app_font
        )
        self.app.annotation_assembly_dropdown.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        # --- Part 2: 功能区选项卡 ---
        # 创建一个Tabview来区分“仅注释”和“富集分析”两个主要功能
        action_tabview = ctk.CTkTabview(self, corner_radius=8)
        action_tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=15)

        # -- Tab 1: 简单注释 --
        anno_tab = action_tabview.add(_("仅注释"))
        anno_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(anno_tab, text=_("选择要查询的注释类型:"), font=app_font_bold).grid(row=0, column=0, padx=10,
                                                                                         pady=10, sticky="w")
        # GO注释复选框
        self.app.go_anno_checkbox = ctk.CTkCheckBox(anno_tab, text=_("GO 功能注释"), variable=self.app.go_anno_var,
                                                    font=app_font)
        self.app.go_anno_checkbox.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        # InterPro注释复选框
        self.app.ipr_anno_checkbox = ctk.CTkCheckBox(anno_tab, text=_("InterPro Domain 注释"),
                                                     variable=self.app.ipr_anno_var, font=app_font)
        self.app.ipr_anno_checkbox.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        # KEGG Orthologs注释复选框
        self.app.kegg_ortho_checkbox = ctk.CTkCheckBox(anno_tab, text=_("KEGG Orthologs 注释"),
                                                       variable=self.app.kegg_ortho_anno_var, font=app_font)
        self.app.kegg_ortho_checkbox.grid(row=3, column=0, padx=10, pady=5, sticky="w")
        # KEGG Pathways注释复选框
        self.app.kegg_path_checkbox = ctk.CTkCheckBox(anno_tab, text=_("KEGG Pathways 注释"),
                                                      variable=self.app.kegg_path_anno_var, font=app_font)
        self.app.kegg_path_checkbox.grid(row=4, column=0, padx=10, pady=5, sticky="w")

        # 输出文件路径设置
        ctk.CTkLabel(anno_tab, text=_("结果输出CSV文件:"), font=app_font_bold).grid(row=5, column=0, padx=10,
                                                                                    pady=(15, 5), sticky="w")
        self.app.annotation_output_csv_entry = ctk.CTkEntry(anno_tab, font=app_font,
                                                            placeholder_text=_("不填则自动命名并保存"))
        self.app.annotation_output_csv_entry.grid(row=6, column=0, sticky="ew", padx=10)
        # 任务启动按钮
        ctk.CTkButton(anno_tab, text=_("开始注释"), font=app_font_bold, command=self.app.start_annotation_task).grid(
            row=7, column=0, padx=10, pady=15, sticky="e")

        # -- Tab 2: 富集分析与绘图 --
        enrich_tab = action_tabview.add(_("富集与绘图"))
        enrich_tab.grid_columnconfigure((1, 3), weight=1)  # 让第2和第4列可以缩放

        # 分析类型选择器 (GO 或 KEGG)
        ctk.CTkLabel(enrich_tab, text=_("分析类型:"), font=app_font_bold).grid(row=0, column=0, columnspan=1, padx=10,
                                                                               pady=10, sticky="w")
        self.app.analysis_type_var = tk.StringVar(value="GO")
        ctk.CTkSegmentedButton(enrich_tab, variable=self.app.analysis_type_var, values=["GO", "KEGG"]).grid(row=0,
                                                                                                            column=1,
                                                                                                            columnspan=3,
                                                                                                            padx=10,
                                                                                                            pady=10,
                                                                                                            sticky="ew")

        # 绘图参数区域的标题
        ctk.CTkLabel(enrich_tab, text=_("绘图参数:"), font=app_font_bold).grid(row=1, column=0, columnspan=4, padx=10,
                                                                               pady=10, sticky="w")

        # 参数行1: Top N 和 排序依据
        ctk.CTkLabel(enrich_tab, text=_("Top N 通路:")).grid(row=2, column=0, padx=(10, 5), pady=5, sticky="w")
        ctk.CTkEntry(enrich_tab, textvariable=self.app.enrich_top_n_var).grid(row=2, column=1, padx=5, pady=5,
                                                                              sticky="ew")
        ctk.CTkLabel(enrich_tab, text=_("排序/颜色依据:")).grid(row=2, column=2, padx=(10, 5), pady=5, sticky="w")
        ctk.CTkOptionMenu(enrich_tab, variable=self.app.enrich_sort_by_var, values=["FDR", "p_value"]).grid(row=2,
                                                                                                            column=3,
                                                                                                            padx=5,
                                                                                                            pady=5,
                                                                                                            sticky="ew")

        # 参数行2: 图片格式 和 是否显示标题
        ctk.CTkLabel(enrich_tab, text=_("图形格式:")).grid(row=3, column=0, padx=(10, 5), pady=5, sticky="w")
        ctk.CTkOptionMenu(enrich_tab, variable=self.app.enrich_format_var, values=["png", "pdf", "svg"]).grid(row=3,
                                                                                                              column=1,
                                                                                                              padx=5,
                                                                                                              pady=5,
                                                                                                              sticky="ew")
        ctk.CTkSwitch(enrich_tab, text=_("显示标题"), variable=self.app.enrich_show_title_var).grid(row=3, column=2,
                                                                                                    columnspan=2,
                                                                                                    padx=10, pady=5,
                                                                                                    sticky="w")

        # 参数行3: 图片尺寸
        ctk.CTkLabel(enrich_tab, text=_("图形宽度 (英寸):")).grid(row=4, column=0, padx=(10, 5), pady=5, sticky="w")
        ctk.CTkEntry(enrich_tab, textvariable=self.app.enrich_width_var).grid(row=4, column=1, padx=5, pady=5,
                                                                              sticky="ew")
        ctk.CTkLabel(enrich_tab, text=_("图形高度 (英寸):")).grid(row=4, column=2, padx=(10, 5), pady=5, sticky="w")
        ctk.CTkEntry(enrich_tab, textvariable=self.app.enrich_height_var).grid(row=4, column=3, padx=5, pady=5,
                                                                               sticky="ew")

        # 参数行4: 选择要生成的图表类型
        ctk.CTkLabel(enrich_tab, text=_("选择图表类型:"), font=app_font_bold).grid(row=5, column=0, columnspan=4,
                                                                                   padx=10, pady=(15, 5), sticky="w")
        plot_type_frame = ctk.CTkFrame(enrich_tab, fg_color="transparent")
        plot_type_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=10, pady=5)
        # 气泡图
        ctk.CTkCheckBox(plot_type_frame, text=_("气泡图 (Bubble Plot)"), variable=self.app.bubble_plot_var).pack(
            side="left", padx=5)
        # 柱状图
        ctk.CTkCheckBox(plot_type_frame, text=_("柱状图 (Bar Plot)"), variable=self.app.bar_plot_var).pack(side="left",
                                                                                                           padx=5)
        # Upset图
        ctk.CTkCheckBox(plot_type_frame, text=_("Upset图"), variable=self.app.upset_plot_var).pack(side="left", padx=5)
        # 基因-概念网络图
        ctk.CTkCheckBox(plot_type_frame, text=_("基因-概念网络图 (Cnet)"), variable=self.app.cnet_plot_var).pack(
            side="left", padx=5)

        # 输出目录和启动按钮
        ctk.CTkLabel(enrich_tab, text=_("图表输出目录:"), font=app_font_bold).grid(row=7, column=0, columnspan=4,
                                                                                   padx=10, pady=(15, 5), sticky="w")
        output_dir_frame = ctk.CTkFrame(enrich_tab, fg_color="transparent")
        output_dir_frame.grid(row=8, column=0, columnspan=4, sticky="ew", padx=10)
        output_dir_frame.grid_columnconfigure(0, weight=1)
        # 输出目录输入框
        self.app.enrichment_output_dir_entry = ctk.CTkEntry(output_dir_frame,
                                                            placeholder_text=_("选择一个目录保存图片"), font=app_font)
        self.app.enrichment_output_dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        # 浏览目录按钮
        ctk.CTkButton(output_dir_frame, text=_("浏览..."), width=100, font=app_font,
                      command=lambda: self.app._browse_directory(self.app.enrichment_output_dir_entry)).grid(row=0,
                                                                                                             column=1)
        # 富集分析启动按钮
        ctk.CTkButton(enrich_tab, text=_("开始富集分析与绘图"), font=app_font_bold,
                      command=self.app.start_enrichment_task).grid(row=9, column=0, columnspan=4, padx=10, pady=15,
                                                                   sticky="e")