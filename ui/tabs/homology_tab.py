# ui/tabs/homology_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

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

        self.scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        self._create_widgets()
        self.update_from_config()

    def _create_widgets(self):
        # 所有控件都创建在 self.scrollable_frame 上
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)  # 为两列布局

        # --- 卡片1: 基因组与基因列表 ---
        card1 = ctk.CTkFrame(parent_frame, border_width=0)
        card1.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(5, 10))
        card1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card1, text=_("基因组与基因列表"), font=self.app.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                          padx=10, pady=(10, 15),
                                                                                          sticky="w")

        # 源基因组
        ctk.CTkLabel(card1, text=_("源基因组:"), font=self.app.app_font).grid(row=1, column=0, padx=(15, 5), pady=10,
                                                                              sticky="w")
        self.selected_homology_source_assembly = tk.StringVar()
        self.source_assembly_dropdown = ctk.CTkOptionMenu(card1, variable=self.selected_homology_source_assembly,
                                                          values=[_("加载中...")], font=self.app.app_font,
                                                          dropdown_font=self.app.app_font)
        self.source_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        # 目标基因组
        ctk.CTkLabel(card1, text=_("目标基因组:"), font=self.app.app_font).grid(row=2, column=0, padx=(15, 5), pady=10,
                                                                                sticky="w")
        self.selected_homology_target_assembly = tk.StringVar()
        self.target_assembly_dropdown = ctk.CTkOptionMenu(card1, variable=self.selected_homology_target_assembly,
                                                          values=[_("加载中...")], font=self.app.app_font,
                                                          dropdown_font=self.app.app_font)
        self.target_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        # 基因ID输入框
        ctk.CTkLabel(card1, text=_("基因ID列表:"), font=self.app.app_font).grid(row=3, column=0, padx=(15, 5), pady=10,
                                                                                sticky="nw")
        self.homology_map_genes_textbox = ctk.CTkTextbox(card1, height=150, font=self.app.app_font_mono, wrap="word")
        self.homology_map_genes_textbox.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="ew")

        # --- 卡片2: 参数设置 ---
        card2 = ctk.CTkFrame(parent_frame, border_width=0)
        card2.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        card2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card2, text=_("参数设置"), font=self.app.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                  padx=10, pady=(10, 15), sticky="w")

        self.homology_strict_priority_var = tk.BooleanVar(value=True)
        self.strict_switch = ctk.CTkSwitch(card2, text=_("严格匹配模式"), variable=self.homology_strict_priority_var,
                                           font=self.app.app_font)
        self.strict_switch.grid(row=1, column=0, columnspan=2, padx=15, pady=10, sticky="w")

        # --- 卡片3: 输出文件 ---
        card3 = ctk.CTkFrame(parent_frame, border_width=0)
        card3.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        card3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card3, text=_("输出文件"), font=self.app.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                  padx=10, pady=(10, 15), sticky="w")

        ctk.CTkLabel(card3, text=_("输出路径:"), font=self.app.app_font).grid(row=1, column=0, padx=(15, 5), pady=10,
                                                                              sticky="w")
        self.homology_output_file_entry = ctk.CTkEntry(card3, font=self.app.app_font)
        self.homology_output_file_entry.grid(row=1, column=1, padx=0, pady=10, sticky="ew")
        self.browse_button = ctk.CTkButton(card3, text=_("浏览..."), width=100, command=self._browse_output_file)
        self.browse_button.grid(row=1, column=2, padx=10, pady=10)

        # 开始按钮
        self.start_button = ctk.CTkButton(parent_frame, text=_("开始转换"), height=40, font=self.app.app_font_bold,
                                          command=self._start_homology_task)
        self.start_button.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=(10, 15))


    def _browse_output_file(self):
        self.app._browse_save_file(
            self.homology_output_file_entry,
            [(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")]
        )

    def _start_homology_task(self):
        # 具体逻辑在主程序中实现，以保持UI和核心逻辑分离
        self.app.start_homology_task()

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