# ui/tabs/homology_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING

# 导入后端处理函数
from cotton_toolkit.pipelines import run_homology_mapping

if TYPE_CHECKING:
    from ui.gui_app import CottonToolkitApp

# 设置一个全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class HomologyTab(ctk.CTkFrame):
    """ “基因组转换”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 1. 将所有相关的Tkinter变量从gui_app.py移到这里
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.homology_top_n_var = tk.StringVar(value="1")
        self.homology_evalue_var = tk.StringVar(value="1e-10")
        self.homology_pid_var = tk.StringVar(value="30.0")
        self.homology_score_var = tk.StringVar(value="50.0")
        self.homology_strict_priority_var = tk.BooleanVar(value=True)

        # 增加两个用于显示文件路径的变量
        self.homology_map_s2b_file_path_var = tk.StringVar()
        self.homology_map_b2t_file_path_var = tk.StringVar()

        # 2. 调用UI创建方法
        self._create_widgets()

        # 3. 初始化UI状态
        self.update_from_config()

    def _create_widgets(self):
        """ 创建“基因组转换”选项卡的全部UI控件 """
        self.grid_columnconfigure(0, weight=1)

        main_input_frame = ctk.CTkFrame(self)
        main_input_frame.pack(fill="x", padx=10, pady=10)
        main_input_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(main_input_frame, text=_("1. 输入基因ID列表:"), font=self.app.app_font_bold).grid(row=0, column=0,
                                                                                                       padx=10,
                                                                                                       pady=(10, 5),
                                                                                                       sticky="w")
        self.homology_map_genes_textbox = ctk.CTkTextbox(main_input_frame, height=150, font=self.app.app_font,
                                                         wrap="word")
        self.homology_map_genes_textbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        self.app._bind_mouse_wheel_to_scrollable(self.homology_map_genes_textbox)

        self.app._add_placeholder(self.homology_map_genes_textbox, self.app.placeholder_key_homology)
        self.homology_map_genes_textbox.bind("<FocusIn>",
                                             lambda e: self.app._clear_placeholder(self.homology_map_genes_textbox,
                                                                                   self.app.placeholder_key_homology))
        self.homology_map_genes_textbox.bind("<FocusOut>",
                                             lambda e: self.app._add_placeholder(self.homology_map_genes_textbox,
                                                                                 self.app.placeholder_key_homology))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)

        ctk.CTkLabel(main_input_frame, text=_("2. 选择源与目标基因组:"), font=self.app.app_font_bold).grid(row=2,
                                                                                                           column=0,
                                                                                                           padx=10,
                                                                                                           pady=(15, 5),
                                                                                                           sticky="w")

        assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [_("无可用版本")]

        source_frame = ctk.CTkFrame(main_input_frame, fg_color="transparent")
        source_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        source_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(source_frame, text=_("源基因组:"), font=self.app.app_font).grid(row=0, column=0, padx=5)
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(source_frame,
                                                                       variable=self.selected_homology_source_assembly,
                                                                       values=assembly_ids,
                                                                       command=self._on_homology_assembly_selection,
                                                                       font=self.app.app_font)
        self.homology_map_source_assembly_dropdown.grid(row=0, column=1, padx=5, sticky="ew")

        target_frame = ctk.CTkFrame(main_input_frame, fg_color="transparent")
        target_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        target_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(target_frame, text=_("目标基因组:"), font=self.app.app_font).grid(row=0, column=0, padx=5)
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(target_frame,
                                                                       variable=self.selected_homology_target_assembly,
                                                                       values=assembly_ids,
                                                                       command=self._on_homology_assembly_selection,
                                                                       font=self.app.app_font)
        self.homology_map_target_assembly_dropdown.grid(row=0, column=1, padx=5, sticky="ew")

        warning_frame = ctk.CTkFrame(main_input_frame, fg_color="transparent")
        warning_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=0, sticky="ew")
        warning_frame.grid_columnconfigure((0, 1), weight=1)

        self.homology_source_version_warning_label = ctk.CTkLabel(warning_frame, text="",
                                                                  font=self.app.app_comment_font)
        self.homology_source_version_warning_label.grid(row=0, column=0, sticky="w")

        self.homology_target_version_warning_label = ctk.CTkLabel(warning_frame, text="",
                                                                  font=self.app.app_comment_font)
        self.homology_target_version_warning_label.grid(row=0, column=1, sticky="w")

        advanced_options_card = ctk.CTkFrame(self, fg_color=("gray90", "gray25"))
        advanced_options_card.pack(fill="x", padx=10, pady=10)
        advanced_options_card.grid_columnconfigure(1, weight=1)
        advanced_options_card.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(advanced_options_card, text=_("高级同源筛选选项 (可选):"), font=self.app.app_font_bold).grid(row=0,
                                                                                                                  column=0,
                                                                                                                  columnspan=4,
                                                                                                                  padx=10,
                                                                                                                  pady=(
                                                                                                                      10,
                                                                                                                      10),
                                                                                                                  sticky="w")

        ctk.CTkLabel(advanced_options_card, text=_("E-value ≤"), font=self.app.app_font).grid(row=1, column=0,
                                                                                              padx=(10, 0),
                                                                                              pady=5, sticky="e")
        self.homology_evalue_entry = ctk.CTkEntry(advanced_options_card, textvariable=self.homology_evalue_var)
        self.homology_evalue_entry.grid(row=1, column=1, padx=(5, 15), pady=5, sticky="ew")

        ctk.CTkLabel(advanced_options_card, text=_("PID ≥"), font=self.app.app_font).grid(row=1, column=2, padx=(10, 0),
                                                                                          pady=5, sticky="e")
        self.homology_pid_entry = ctk.CTkEntry(advanced_options_card, textvariable=self.homology_pid_var)
        self.homology_pid_entry.grid(row=1, column=3, padx=(5, 10), pady=5, sticky="ew")

        ctk.CTkLabel(advanced_options_card, text=_("Score ≥"), font=self.app.app_font).grid(row=2, column=0,
                                                                                            padx=(10, 0),
                                                                                            pady=5, sticky="e")
        self.homology_score_entry = ctk.CTkEntry(advanced_options_card, textvariable=self.homology_score_var)
        self.homology_score_entry.grid(row=2, column=1, padx=(5, 15), pady=5, sticky="ew")

        ctk.CTkLabel(advanced_options_card, text=_("Top N ="), font=self.app.app_font).grid(row=2, column=2,
                                                                                            padx=(10, 0),
                                                                                            pady=5, sticky="e")
        self.homology_top_n_entry = ctk.CTkEntry(advanced_options_card, textvariable=self.homology_top_n_var,
                                                 placeholder_text=_("0 表示所有"))
        self.homology_top_n_entry.grid(row=2, column=3, padx=(5, 10), pady=5, sticky="ew")

        switch_frame = ctk.CTkFrame(advanced_options_card, fg_color="transparent")
        switch_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=(5, 10), sticky="w")

        self.homology_strict_switch = ctk.CTkSwitch(
            switch_frame, text=_("仅匹配同亚组、同源染色体上的基因 (严格模式)"),
            variable=self.homology_strict_priority_var,
            font=self.app.app_font,
            command=self._toggle_homology_warning_label
        )
        self.homology_strict_switch.pack(side="left")

        self.homology_warning_label = ctk.CTkLabel(
            switch_frame, text=_("关闭后可能导致不同染色体的基因发生错配"),
            text_color=("#D32F2F", "#E57373")
        )

        output_frame = ctk.CTkFrame(self, fg_color="transparent")
        output_frame.pack(fill="x", padx=10, pady=(5, 10))
        output_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(output_frame, text=_("3. 输出结果:"), font=self.app.app_font_bold).grid(row=0, column=0,
                                                                                             columnspan=3,
                                                                                             sticky="w", pady=(10, 5))
        self.homology_map_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app.app_font)
        self.homology_map_output_csv_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ctk.CTkButton(output_frame, text=_("选择目录..."), font=self.app.app_font,
                      command=lambda: self.app._select_output_directory(self.homology_map_output_csv_entry)).grid(row=1,
                                                                                                                  column=2)

        start_button_frame = ctk.CTkFrame(self, fg_color="transparent")
        start_button_frame.pack(fill="x", padx=10, pady=(5, 10))
        start_button_frame.grid_columnconfigure(0, weight=1)

        self.start_homology_map_button = ctk.CTkButton(start_button_frame, text=_("开始基因组转换"),
                                                       font=self.app.app_font_bold, height=40,
                                                       command=self.start_homology_map_task)
        self.start_homology_map_button.grid(row=0, column=0, sticky="e")

        self._toggle_homology_warning_label()

    def update_from_config(self):
        """ 根据主应用的配置来更新这个选项卡的UI状态 """
        if not self.app.current_config or not self.app.genome_sources_data:
            assembly_ids = [_("无可用版本")]
        else:
            assembly_ids = list(self.app.genome_sources_data.keys())

        self.homology_map_source_assembly_dropdown.configure(values=assembly_ids)
        self.homology_map_target_assembly_dropdown.configure(values=assembly_ids)

        if self.app.current_config:
            pipe_cfg = self.app.current_config.integration_pipeline
            if pipe_cfg.bsa_assembly_id in assembly_ids:
                self.selected_homology_source_assembly.set(pipe_cfg.bsa_assembly_id)
            if pipe_cfg.hvg_assembly_id in assembly_ids:
                self.selected_homology_target_assembly.set(pipe_cfg.hvg_assembly_id)

        # 触发一次更新，以确保文件路径等显示正确
        self._on_homology_assembly_selection()

    def update_assembly_dropdowns(self, assembly_ids: list):
        """由主应用调用，用于更新本选项卡内的基因组下拉菜单。"""

        # 安全地检查并设置默认值
        # 如果当前选中的值不在新的列表中，就默认选第一个
        current_source = self.selected_homology_source_assembly.get()
        if current_source not in assembly_ids:
            self.selected_homology_source_assembly.set(assembly_ids[0] if "无可用" not in assembly_ids[0] else "")

        current_target = self.selected_homology_target_assembly.get()
        if current_target not in assembly_ids:
            self.selected_homology_target_assembly.set(assembly_ids[0] if "无可用" not in assembly_ids[0] else "")

        # 更新下拉菜单的选项列表
        self.homology_map_source_assembly_dropdown.configure(values=assembly_ids)
        self.homology_map_target_assembly_dropdown.configure(values=assembly_ids)


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
        self.app._auto_identify_genome_version(self.homology_map_genes_textbox, self.selected_homology_source_assembly)

    def _on_homology_assembly_selection(self, event=None):
        """ 当同源映射工具中的源或目标基因组被选择时，更新UI """
        self._update_homology_version_warnings()

    def _toggle_homology_warning_label(self):
        """ 根据严格模式开关，显示或隐藏警告标签 """
        if self.homology_strict_priority_var.get():
            self.homology_warning_label.pack_forget()
        else:
            self.homology_warning_label.pack(side="left", padx=15, pady=0)

    def _update_homology_version_warnings(self):
        """ 检查所选基因组的同源库版本并在UI上显示警告 """
        if not self.app.current_config or not self.app.genome_sources_data:
            return

        source_id = self.selected_homology_source_assembly.get()
        target_id = self.selected_homology_target_assembly.get()

        warning_color = ("#D84315", "#FF7043")
        ok_color = ("#2E7D32", "#A5D6A7")

        source_info = self.app.genome_sources_data.get(source_id)
        if source_info and hasattr(source_info, 'bridge_version'):
            if source_info.bridge_version and source_info.bridge_version.lower() == 'tair10':
                self.homology_source_version_warning_label.configure(text="⚠️ " + _("使用旧版 tair10"),
                                                                     text_color=warning_color)
            else:
                self.homology_source_version_warning_label.configure(text="✓ " + _("使用新版 Araport11"),
                                                                     text_color=ok_color)
        else:
            self.homology_source_version_warning_label.configure(text="")

        target_info = self.app.genome_sources_data.get(target_id)
        if target_info and hasattr(target_info, 'homology_type'):
            if target_info.homology_type and target_info.homology_type.lower() == 'tair10':
                self.homology_target_version_warning_label.configure(text="⚠️ " + _("使用旧版 tair10"),
                                                                     text_color=warning_color)
            else:
                self.homology_target_version_warning_label.configure(text="✓ " + _("使用新版 Araport11"),
                                                                     text_color=ok_color)
        else:
            self.homology_target_version_warning_label.configure(text="")