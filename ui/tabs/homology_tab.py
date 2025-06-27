# ui/tabs/homology_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

# 导入后端处理函数
from cotton_toolkit.pipelines import run_homology_mapping
from ui.tabs.base_tab import BaseTab

if TYPE_CHECKING:
    from ui.gui_app import CottonToolkitApp

# 设置一个全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class HomologyTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):

        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.homology_strict_priority_var = tk.BooleanVar(value=True)

        super().__init__(parent, app)

        self._create_base_widgets()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(1, weight=1)

        safe_text_color = ("gray10", "#DCE4EE")
        font_regular = (self.app.font_family, 14)
        font_bold = (self.app.font_family, 15, "bold")
        font_title = (self.app.font_family, 24, "bold")
        font_mono = (self.app.mono_font_family, 12)

        card1 = ctk.CTkFrame(parent_frame, fg_color="transparent")
        card1.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
        card1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card1, text=_("基因同源转换"), font=font_title, text_color=safe_text_color).grid(row=0, column=0,
                                                                                                      columnspan=2,
                                                                                                      pady=(5, 10),
                                                                                                      padx=10,
                                                                                                      sticky="n")

        ctk.CTkLabel(card1, text=_("源基因组:"), font=font_regular, text_color=safe_text_color).grid(row=1, column=0,
                                                                                                     padx=(15, 5),
                                                                                                     pady=10,
                                                                                                     sticky="w")
        self.source_assembly_dropdown = ctk.CTkOptionMenu(card1, variable=self.selected_homology_source_assembly,
                                                          values=[_("加载中...")], font=font_regular,
                                                          dropdown_font=font_regular,
                                                          command=self._on_homology_assembly_selection)
        self.source_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        ctk.CTkLabel(card1, text=_("目标基因组:"), font=font_regular, text_color=safe_text_color).grid(row=2, column=0,
                                                                                                       padx=(15, 5),
                                                                                                       pady=10,
                                                                                                       sticky="w")
        self.target_assembly_dropdown = ctk.CTkOptionMenu(card1, variable=self.selected_homology_target_assembly,
                                                          values=[_("加载中...")], font=font_regular,
                                                          dropdown_font=font_regular,
                                                          command=self._on_homology_assembly_selection)
        self.target_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        ctk.CTkLabel(card1, text=_("基因ID列表:"), font=font_regular, text_color=safe_text_color).grid(row=3, column=0,
                                                                                                       padx=(15, 5),
                                                                                                       pady=10,
                                                                                                       sticky="nw")
        self.homology_map_genes_textbox = ctk.CTkTextbox(card1, height=150, font=font_mono, wrap="word")
        self.homology_map_genes_textbox.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.app.ui_manager._add_placeholder(self.homology_map_genes_textbox, "homology_genes")
        self.homology_map_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._clear_placeholder(
            self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._add_placeholder(
            self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)

        card2 = ctk.CTkFrame(parent_frame, fg_color="transparent")
        card2.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=10)
        card2.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(card2, text=_("参数设置"), font=font_bold, text_color=safe_text_color).grid(row=0, column=0,
                                                                                                 columnspan=4, padx=10,
                                                                                                 pady=(10, 15),
                                                                                                 sticky="w")
        self.strict_switch = ctk.CTkSwitch(card2, text=_("严格匹配模式"), variable=self.homology_strict_priority_var,
                                           font=font_regular, text_color=safe_text_color)
        self.strict_switch.grid(row=1, column=0, columnspan=2, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(card2, text=_("Top N:"), font=font_regular, text_color=safe_text_color).grid(row=2, column=0,
                                                                                                  padx=(15, 5), pady=5,
                                                                                                  sticky="w")
        self.homology_top_n_entry = ctk.CTkEntry(card2, font=font_regular)
        self.homology_top_n_entry.insert(0, "1")
        self.homology_top_n_entry.grid(row=2, column=1, padx=(0, 10), pady=5, sticky="ew")

        ctk.CTkLabel(card2, text=_("E-value:"), font=font_regular, text_color=safe_text_color).grid(row=2, column=2,
                                                                                                    padx=(15, 5),
                                                                                                    pady=5, sticky="w")
        self.homology_evalue_entry = ctk.CTkEntry(card2, font=font_regular)
        self.homology_evalue_entry.insert(0, "1e-10")
        self.homology_evalue_entry.grid(row=2, column=3, padx=(0, 10), pady=5, sticky="ew")

        ctk.CTkLabel(card2, text=_("PID (%):"), font=font_regular, text_color=safe_text_color).grid(row=3, column=0,
                                                                                                    padx=(15, 5),
                                                                                                    pady=5, sticky="w")
        self.homology_pid_entry = ctk.CTkEntry(card2, font=font_regular)
        self.homology_pid_entry.insert(0, "30.0")
        self.homology_pid_entry.grid(row=3, column=1, padx=(0, 10), pady=5, sticky="ew")

        ctk.CTkLabel(card2, text=_("Score:"), font=font_regular, text_color=safe_text_color).grid(row=3, column=2,
                                                                                                  padx=(15, 5), pady=5,
                                                                                                  sticky="w")
        self.homology_score_entry = ctk.CTkEntry(card2, font=font_regular)
        self.homology_score_entry.insert(0, "50.0")
        self.homology_score_entry.grid(row=3, column=3, padx=(0, 10), pady=5, sticky="ew")

        card3 = ctk.CTkFrame(parent_frame, fg_color="transparent")
        card3.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=10)
        card3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card3, text=_("输出文件"), font=font_bold, text_color=safe_text_color).grid(row=0, column=0,
                                                                                                 columnspan=3, padx=10,
                                                                                                 pady=(10, 15),
                                                                                                 sticky="w")
        ctk.CTkLabel(card3, text=_("输出路径:"), font=font_regular, text_color=safe_text_color).grid(row=1, column=0,
                                                                                                     padx=(15, 5),
                                                                                                     pady=10,
                                                                                                     sticky="w")
        self.homology_output_file_entry = ctk.CTkEntry(card3, font=font_regular)
        self.homology_output_file_entry.grid(row=1, column=1, padx=0, pady=10, sticky="ew")
        self.browse_button = ctk.CTkButton(card3, text=_("浏览..."), width=100, command=self._browse_output_file,
                                           font=font_regular)
        self.browse_button.grid(row=1, column=2, padx=10, pady=10)

        self.start_button = ctk.CTkButton(parent_frame, text=_("开始转换"), height=40, font=font_bold,
                                          command=self._start_homology_task)
        self.start_button.grid(row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=(10, 5))


    def _browse_output_file(self):
        self.app.event_handler._browse_save_file( # 委托给 EventHandler
            self.homology_output_file_entry,
            [(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")]
        )

    def _start_homology_task(self):
        """ 启动基因组转换任务 """
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip()
        source_gene_ids_list = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not source_gene_ids_list:
            self.app.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"))
            return

        source_assembly = self.selected_homology_source_assembly.get()
        target_assembly = self.selected_homology_target_assembly.get()
        if not all([source_assembly, target_assembly]) or _("加载中...") in [source_assembly, target_assembly]:
            self.app.show_error_message(_("输入缺失"), _("请选择有效的源和目标基因组。"))
            return

        try:
            # 从UI控件中获取值并构建参数字典
            criteria_overrides = {
                "top_n": int(self.homology_top_n_entry.get()),
                "evalue_threshold": float(self.homology_evalue_entry.get()),
                "pid_threshold": float(self.homology_pid_entry.get()),
                "score_threshold": float(self.homology_score_entry.get()),
                "strict_subgenome_priority": self.homology_strict_priority_var.get()
            }
        except (ValueError, TypeError):
            self.app.show_error_message(_("输入错误"), _("高级筛选选项中的阈值必须是有效的数字。"))
            return

        output_csv = self.homology_output_file_entry.get().strip() or None

        # 使用 _start_task 启动后台任务，并传入所有参数
        self.app.event_handler._start_task(  # 委托给 EventHandler
            task_name=_("基因组转换"),
            target_func=run_homology_mapping,
            kwargs={
                'config': self.app.current_config,
                'source_assembly_id': source_assembly,
                'target_assembly_id': target_assembly,
                'gene_ids': source_gene_ids_list,
                'region': None,
                'output_csv_path': output_csv,
                'criteria_overrides': criteria_overrides
            }
        )

    def update_from_config(self):
        if self.app.current_config:
            self.homology_output_file_entry.delete(0, tk.END)
            default_path = "homology_results.xlsx"
            self.homology_output_file_entry.insert(0, default_path)
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_button_state(self, is_running, has_config):
        if not has_config or is_running:
            self.start_button.configure(state="disabled")
        else:
            self.start_button.configure(state="normal")

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """
        【已修改】更新下拉菜单，并设置默认值为第一项。
        """
        if not assembly_ids:
            assembly_ids = [_("加载中...")]

        # 1. 更新下拉菜单的可选项列表
        self.source_assembly_dropdown.configure(values=assembly_ids)
        self.target_assembly_dropdown.configure(values=assembly_ids)

        # 2. 检查当前值是否在列表中，如果不在或为空，则设置默认值
        is_valid_list = bool(assembly_ids and "加载中" not in assembly_ids[0])

        if is_valid_list:
            # 检查源基因组下拉菜单
            if self.selected_homology_source_assembly.get() not in assembly_ids:
                self.selected_homology_source_assembly.set(assembly_ids[0])

            # 检查目标基因组下拉菜单
            if self.selected_homology_target_assembly.get() not in assembly_ids:
                self.selected_homology_target_assembly.set(assembly_ids[0])


    def start_homology_map_task(self):
        """ 启动基因组转换任务 (基于基因列表) """
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip()
        source_gene_ids_list = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not source_gene_ids_list:
            self.app.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"))
            return

        source_assembly = self.selected_homology_source_assembly.get()
        target_assembly = self.selected_homology_target_assembly.get()
        if not all([source_assembly, target_assembly]):
            self.app.show_error_message(_("输入缺失"), _("请选择源和目标基因组。"))
            return

        try:
            criteria_overrides = {
                "top_n": int(self.homology_top_n_var.get()),
                "evalue_threshold": float(self.homology_evalue_var.get()),
                "pid_threshold": float(self.homology_pid_var.get()),
                "score_threshold": float(self.homology_score_var.get()),
                "strict_subgenome_priority": self.homology_strict_priority_var.get()
            }
        except (ValueError, TypeError):
            self.app.show_error_message(_("输入错误"), _("高级筛选选项中的阈值必须是有效的数字。"))
            return

        output_csv = self.homology_map_output_csv_entry.get().strip() or None

        self.app._start_task(
            task_name=_("基因组转换"),
            target_func=run_homology_mapping,
            kwargs={
                'config': self.app.current_config,
                'source_assembly_id': source_assembly,
                'target_assembly_id': target_assembly,
                'gene_ids': source_gene_ids_list,
                'region': None,
                'output_csv_path': output_csv,
                'criteria_overrides': criteria_overrides
            }
        )

    def _on_homology_gene_input_change(self, event=None):
        """ 同源映射输入框基因ID变化时触发基因组自动识别 """
        self.app.event_handler._auto_identify_genome_version(self.homology_map_genes_textbox, self.selected_homology_source_assembly) # 委托给 EventHandler

    def _on_homology_assembly_selection(self, event=None):
        """ 当同源映射工具中的源或目标基因组被选择时，更新UI """
        self._update_homology_version_warnings()


    def _update_homology_version_warnings(self):
        """ 检查所选基因组的同源库版本并在UI上显示警告 """
        if not self.app.current_config or not self.app.genome_sources_data:
            return

        source_id = self.selected_homology_source_assembly.get()
        target_id = self.selected_homology_target_assembly.get()

        warning_color = ("#D84315", "#FF7043")
        ok_color = ("#2E7D32", "#A5D6A7")

        source_info = self.app.genome_sources_data.get(source_id)
