# 文件路径: ui/tabs/enrichment_tab.py

import os
import tkinter as tk
from tkinter import ttk, filedialog
from typing import TYPE_CHECKING, Callable, Optional, List

import ttkbootstrap as ttkb
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from cotton_toolkit.tools.enrichment_analyzer import run_go_enrichment, run_kegg_enrichment
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class EnrichmentTab(BaseTab):
    """
    负责GO和KEGG富集分析的UI界面。
    """

    def __init__(self, parent, app: "CottonToolkitApp"):
        # --- 初始化变量 ---
        self.app = app
        self.analysis_type_var = tk.StringVar(value=_("GO 富集分析"))
        self.assembly_id_var = tk.StringVar()
        self.top_n_var = tk.IntVar(value=20)
        self.p_value_cutoff_var = tk.DoubleVar(value=0.05)
        self.sort_by_var = tk.StringVar(value="FDR")

        self.results_df = None
        self.figure: Optional[Figure] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.toolbar: Optional[NavigationToolbar2Tk] = None

        super().__init__(parent, app)

        # 重置基类创建的按钮
        if self.action_button:
            self.action_button.configure(text=_("开始分析"), command=self.start_analysis_task)
            self.action_button.grid(row=0, column=2, sticky="e", padx=15, pady=10)

        # 添加额外的操作按钮
        action_frame = self.action_button.master
        self.save_chart_button = ttkb.Button(action_frame, text=_("保存图表"), command=self.save_chart,
                                             state="disabled")
        self.save_chart_button.grid(row=0, column=0, sticky="e", padx=(0, 10), pady=10)
        self.save_results_button = ttkb.Button(action_frame, text=_("保存结果"), command=self.save_results,
                                               state="disabled")
        self.save_results_button.grid(row=0, column=1, sticky="e", padx=(0, 10), pady=10)

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(2, weight=1)

        # --- 1. 设置区域 ---
        settings_frame = ttkb.Frame(parent_frame)
        settings_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        settings_frame.grid_columnconfigure(1, weight=1)

        # 标题
        self.title_label = ttkb.Label(settings_frame, text=_("GO/KEGG 富集分析"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, columnspan=4, pady=(0, 15))

        # 分析类型
        self.analysis_type_label = ttkb.Label(settings_frame, text=_("分析类型:"), font=self.app.app_font_bold)
        self.analysis_type_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        analysis_types = [_("GO 富集分析"), _("KEGG 富集分析")]
        self.analysis_type_menu = ttkb.OptionMenu(settings_frame, self.analysis_type_var, self.analysis_type_var.get(),
                                                  *analysis_types)
        self.analysis_type_menu.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        # 基因组版本
        self.assembly_id_label = ttkb.Label(settings_frame, text=_("基因组版本:"), font=self.app.app_font_bold)
        self.assembly_id_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.assembly_id_menu = ttkb.OptionMenu(settings_frame, self.assembly_id_var, _("无可用基因组"))
        self.assembly_id_menu.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        # --- 2. 基因输入区域 ---
        input_card = ttkb.LabelFrame(parent_frame, text=_("输入基因列表"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        input_card.grid_columnconfigure(0, weight=1)
        input_card.grid_rowconfigure(0, weight=1)

        self.gene_input_text = tk.Text(input_card, height=12, wrap="word", font=self.app.app_font)
        self.gene_input_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.app.ui_manager.add_placeholder(self.gene_input_text, "enrichment_genes_input")
        self.gene_input_text.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.gene_input_text,
                                                                                              "enrichment_genes_input"))
        self.gene_input_text.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.gene_input_text,
                                                                                                "enrichment_genes_input"))

        # --- 3. 结果和绘图区域 ---
        results_card = ttkb.LabelFrame(parent_frame, text=_("富集结果"), bootstyle="secondary")
        results_card.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        results_card.grid_columnconfigure(0, weight=1)
        results_card.grid_rowconfigure(1, weight=1)

        # 绘图设置
        plot_options_frame = ttkb.Frame(results_card)
        plot_options_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        self.top_n_label = ttkb.Label(plot_options_frame, text=_("显示 Top N:"))
        self.top_n_label.pack(side="left", padx=(0, 5))
        top_n_spinbox = ttkb.Spinbox(plot_options_frame, from_=5, to=50, textvariable=self.top_n_var, width=5)
        top_n_spinbox.pack(side="left", padx=5)

        self.p_value_label = ttkb.Label(plot_options_frame, text=_("P值阈值:"))
        self.p_value_label.pack(side="left", padx=(15, 5))
        p_value_spinbox = ttkb.Spinbox(plot_options_frame, from_=0.0, to=1.0, increment=0.01,
                                       textvariable=self.p_value_cutoff_var, width=6)
        p_value_spinbox.pack(side="left", padx=5)

        self.sort_by_label = ttkb.Label(plot_options_frame, text=_("排序依据:"))
        self.sort_by_label.pack(side="left", padx=(15, 5))
        sort_by_menu = ttkb.OptionMenu(plot_options_frame, self.sort_by_var, self.sort_by_var.get(),
                                       *["FDR", "p_value"])
        sort_by_menu.pack(side="left", padx=5)

        update_plot_button = ttkb.Button(plot_options_frame, text=_("更新图表"), command=self.update_plot,
                                         state="disabled")
        update_plot_button.pack(side="left", padx=15)
        self.update_plot_button = update_plot_button

        # 绘图区域
        self.plot_frame = ttkb.Frame(results_card, bootstyle="light")
        self.plot_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.plot_frame.grid_columnconfigure(0, weight=1)
        self.plot_frame.grid_rowconfigure(0, weight=1)

    def retranslate_ui(self, translator: Callable[[str], str]):
        """在语言切换后更新此选项卡中的所有UI文本。"""
        self.title_label.config(text=translator("GO/KEGG 富集分析"))
        self.analysis_type_label.config(text=translator("分析类型:"))
        self.assembly_id_label.config(text=translator("基因组版本:"))
        self.input_card.config(text=translator("输入基因列表"))
        self.results_card.config(text=translator("富集结果"))
        self.top_n_label.config(text=translator("显示 Top N:"))
        self.p_value_label.config(text=translator("P值阈值:"))
        self.sort_by_label.config(text=translator("排序依据:"))
        self.update_plot_button.config(text=translator("更新图表"))

        # 更新 Action Buttons
        self.action_button.config(text=translator("开始分析"))
        self.save_chart_button.config(text=translator("保存图表"))
        self.save_results_button.config(text=translator("保存结果"))

        # 更新分析类型下拉菜单
        self.analysis_type_var.set(translator(self.analysis_type_var.get()))
        menu = self.analysis_type_menu["menu"]
        menu.delete(0, "end")
        analysis_types = [translator("GO 富集分析"), translator("KEGG 富集分析")]
        for t in analysis_types:
            menu.add_command(label=t, command=tk._setit(self.analysis_type_var, t))

        # 刷新占位符和图表
        self.refresh_placeholders()
        self.update_plot(translator)

    def refresh_placeholders(self):
        """刷新输入框的占位符"""
        text_widget = self.gene_input_text
        if text_widget.get("1.0", tk.END).strip() == "" or text_widget.cget("foreground") != self.app.style.lookup(
                'TLabel', 'foreground'):
            self.app.ui_manager.add_placeholder(text_widget, "enrichment_genes_input")

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        self.app.ui_manager.update_option_menu(
            self.assembly_id_menu, self.assembly_id_var, assembly_ids
        )

    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_button_state(self, is_running: bool, has_config: bool):
        super().update_button_state(is_running, has_config)
        state = "disabled" if is_running or not has_config else "normal"
        self.save_chart_button.config(state="disabled" if is_running else self.save_chart_button.cget('state'))
        self.save_results_button.config(state="disabled" if is_running else self.save_results_button.cget('state'))
        self.update_plot_button.config(state="disabled" if is_running else self.update_plot_button.cget('state'))

    def start_analysis_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_list_str = self.gene_input_text.get("1.0", tk.END).strip()
        if not gene_list_str or gene_list_str == self.app.placeholders.get("enrichment_genes_input"):
            self.app.ui_manager.show_error_message(_("输入错误"), _("请输入基因列表。"))
            return

        # 解析基因列表，支持 GeneID 和 GeneID\tLog2FC 格式
        study_genes = [line.split('\t')[0] for line in gene_list_str.split('\n') if line]

        assembly_id = self.assembly_id_var.get()
        if not assembly_id or assembly_id == _("无可用基因组"):
            self.app.ui_manager.show_error_message(_("选择错误"), _("请选择一个有效的基因组版本。"))
            return

        output_dir = os.path.join(self.app.current_config.enrichment.output_dir, assembly_id)
        os.makedirs(output_dir, exist_ok=True)

        task_name_key, target_func, kwargs = None, None, {}

        analysis_type = self.analysis_type_var.get()

        genome_source_info = self.app.genome_sources_data.get(assembly_id)
        if not genome_source_info:
            self.app.ui_manager.show_error_message(_("错误"),
                                                   _("找不到选中基因组 '{}' 的配置信息。").format(assembly_id))
            return

        if analysis_type == _("GO 富集分析"):
            task_name_key = "GO 富集分析"
            target_func = run_go_enrichment
            go_path = self.app.get_annotation_filepath(assembly_id, 'GO')
            if not go_path: return
            kwargs = {'study_gene_ids': study_genes, 'go_annotation_path': go_path, 'output_dir': output_dir,
                      'gene_id_regex': genome_source_info.gene_id_regex}

        elif analysis_type == _("KEGG 富集分析"):
            task_name_key = "KEGG 富集分析"
            target_func = run_kegg_enrichment
            kegg_path = self.app.get_annotation_filepath(assembly_id, 'KEGG_pathways')
            if not kegg_path: return
            kwargs = {'study_gene_ids': study_genes, 'kegg_pathways_path': kegg_path, 'output_dir': output_dir,
                      'gene_id_regex': genome_source_info.gene_id_regex}

        if task_name_key and target_func:
            self.app.event_handler._start_task(
                task_name=_(task_name_key),
                target_func=target_func,
                kwargs=kwargs,
                on_success=self.on_analysis_complete
            )
        else:
            self.app.ui_manager.show_error_message(_("错误"), _("未知的分析类型: {}").format(analysis_type))

    def on_analysis_complete(self, results_df: Optional[pd.DataFrame]):
        if results_df is None or results_df.empty:
            self.app.ui_manager.show_info_message(_("无结果"), _("富集分析未发现任何显著结果。"))
            self.results_df = None
            self.save_chart_button.config(state="disabled")
            self.save_results_button.config(state="disabled")
            self.update_plot_button.config(state="disabled")
            self.clear_plot()
            return

        self.results_df = results_df
        self.save_chart_button.config(state="normal")
        self.save_results_button.config(state="normal")
        self.update_plot_button.config(state="normal")
        self.update_plot()
        self.app.ui_manager.show_info_message(_("分析完成"), _("富集分析已成功完成。"))

    def update_plot(self, translator: Callable[[str], str] = _):
        if self.results_df is None:
            return

        self.clear_plot()

        df = self.results_df.copy()
        df = df[df['p_value'] <= self.p_value_cutoff_var.get()]

        if df.empty:
            self.app.logger.warning(_("根据当前P值阈值，没有可供显示的数据。"))
            return

        sort_by = self.sort_by_var.get()
        plot_df = df.sort_values(by=sort_by, ascending=True).head(self.top_n_var.get())
        plot_df = plot_df.sort_values(by='RichFactor', ascending=True)

        self.figure = Figure(figsize=(10, 8), dpi=100)
        ax = self.figure.add_subplot(111)

        # 绘图
        sc = ax.scatter(plot_df['RichFactor'], plot_df['Description'],
                        s=plot_df['GeneNumber'] * 15, c=plot_df['FDR'],
                        cmap='viridis_r', alpha=0.7)

        self.figure.colorbar(sc, label=translator('FDR'))

        # 使用 translator 来设置图表文本
        ax.set_title(translator('富集分析气泡图'), fontsize=16)
        ax.set_xlabel(translator('Rich Factor (富集因子)'), fontsize=12)
        ax.set_ylabel(translator('Term Description (描述)'), fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)
        self.figure.tight_layout()

        # 将图表嵌入到Tkinter窗口
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.draw()

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def clear_plot(self):
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None
        if self.toolbar:
            self.toolbar.destroy()
            self.toolbar = None
        if self.figure:
            self.figure.clear()
            self.figure = None

    def save_chart(self):
        if not self.figure:
            self.app.ui_manager.show_warning_message(_("无图表"), _("没有可供保存的图表。"))
            return

        file_path = filedialog.asksaveasfilename(
            title=_("保存图表"),
            filetypes=[(_("PNG 图像"), "*.png"), (_("PDF 文件"), "*.pdf"), (_("SVG 文件"), "*.svg")],
            defaultextension=".png"
        )
        if file_path:
            self.figure.savefig(file_path, bbox_inches='tight', dpi=300)
            self.app.ui_manager.show_info_message(_("成功"), _("图表已成功保存至 {}").format(file_path))

    def save_results(self):
        if self.results_df is None or self.results_df.empty:
            self.app.ui_manager.show_warning_message(_("无结果"), _("没有可供保存的结果。"))
            return

        file_path = filedialog.asksaveasfilename(
            title=_("保存富集结果"),
            filetypes=[(_("CSV 文件"), "*.csv")],
            defaultextension=".csv"
        )
        if file_path:
            self.results_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            self.app.ui_manager.show_info_message(_("成功"), _("结果已成功保存至 {}").format(file_path))