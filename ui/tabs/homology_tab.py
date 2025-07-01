# ui/tabs/homology_tab.py

import tkinter as tk
from tkinter import ttk, font as tkfont # Import ttk and tkfont
import ttkbootstrap as ttkb # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants

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


class HomologyTab(BaseTab): # Assuming BaseTab is converted to ttkbootstrap
    def __init__(self, parent, app: "CottonToolkitApp"):

        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.homology_strict_priority_var = tk.BooleanVar(value=True)

        super().__init__(parent, app)

        self._create_base_widgets()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(1, weight=1)

        # Access fonts directly from self.app
        font_regular = self.app.app_font
        font_bold = self.app.app_font_bold
        font_title = self.app.app_title_font
        font_mono = self.app.app_font_mono # Use the monospace font

        # Use ttk.Frame for cards, remove fg_color="transparent"
        # Can use ttkbootstrap's themed frames for styling, e.g., 'secondary.TFrame'
        card1 = ttk.Frame(parent_frame)
        card1.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
        card1.grid_columnconfigure(1, weight=1)

        ttk.Label(card1, text=_("基因同源转换"), font=font_title,
                  foreground=self.app.style.colors.primary).grid(row=0, column=0,
                                                                                                      columnspan=2,
                                                                                                      pady=(5, 10),
                                                                                                      padx=10,
                                                                                                      sticky="n")

        ttk.Label(card1, text=_("源基因组:"), font=font_regular).grid(row=1, column=0,
                                                                                                     padx=(15, 5),
                                                                                                     pady=10,
                                                                                                     sticky="w")
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        self.source_assembly_dropdown = ttkb.OptionMenu(card1, self.selected_homology_source_assembly,
                                                        _("加载中..."),  # 默认值
                                                        *[_("加载中...")],  # 选项列表
                                                        command=self._on_homology_assembly_selection,
                                                        bootstyle="info")
        self.source_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        ttk.Label(card1, text=_("目标基因组:"), font=font_regular).grid(row=2, column=0,
                                                                                                       padx=(15, 5),
                                                                                                       pady=10,
                                                                                                       sticky="w")
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        self.target_assembly_dropdown = ttkb.OptionMenu(card1, self.selected_homology_target_assembly,
                                                        _("加载中..."),  # 默认值
                                                        *[_("加载中...")],  # 选项列表
                                                        command=self._on_homology_assembly_selection,
                                                        bootstyle="info")
        self.target_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        ttk.Label(card1, text=_("基因ID列表:"), font=font_regular).grid(row=3, column=0,
                                                                                                       padx=(15, 5),
                                                                                                       pady=10,
                                                                                                       sticky="nw")
        # Use tk.Text for textbox
        # 修复：tk.Text 的背景色和前景色通过 style.lookup 获取
        self.homology_map_genes_textbox = tk.Text(card1, height=8, font=font_mono, wrap="word",
                                                  background=self.app.style.lookup('TText', 'background'),
                                                  foreground=self.app.style.lookup('TText', 'foreground'),
                                                  relief="flat")
        self.homology_map_genes_textbox.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.app.ui_manager._add_placeholder(self.homology_map_genes_textbox, "homology_genes")
        self.homology_map_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._clear_placeholder(
            self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._add_placeholder(
            self.homology_map_genes_textbox, "homology_genes"))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)


        card2 = ttk.Frame(parent_frame)
        card2.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=10)
        card2.grid_columnconfigure((1, 3), weight=1)

        ttk.Label(card2, text=_("参数设置"), font=font_bold).grid(row=0, column=0,
                                                                                                 columnspan=4, padx=10,
                                                                                                 pady=(10, 15),
                                                                                                 sticky="w")
        # 修复：ttkb.Checkbutton 不支持直接的 font 参数
        self.strict_switch = ttkb.Checkbutton(card2, text=_("严格匹配模式"), variable=self.homology_strict_priority_var,
                                           bootstyle="round-toggle")
        self.strict_switch.grid(row=1, column=0, columnspan=2, padx=15, pady=10, sticky="w")

        ttk.Label(card2, text=_("Top N:"), font=font_regular).grid(row=2, column=0,
                                                                                                  padx=(15, 5), pady=5,
                                                                                                  sticky="w")
        self.homology_top_n_entry = ttk.Entry(card2, font=font_regular)
        self.homology_top_n_entry.insert(0, "1")
        self.homology_top_n_entry.grid(row=2, column=1, padx=(0, 10), pady=5, sticky="ew")

        ttk.Label(card2, text=_("E-value:"), font=font_regular).grid(row=2, column=2,
                                                                                                    padx=(15, 5),
                                                                                                    pady=5, sticky="w")
        self.homology_evalue_entry = ttk.Entry(card2, font=font_regular)
        self.homology_evalue_entry.insert(0, "1e-10")
        self.homology_evalue_entry.grid(row=2, column=3, padx=(0, 10), pady=5, sticky="ew")

        ttk.Label(card2, text=_("PID (%):"), font=font_regular).grid(row=3, column=0,
                                                                                                    padx=(15, 5),
                                                                                                    pady=5, sticky="w")
        self.homology_pid_entry = ttk.Entry(card2, font=font_regular)
        self.homology_pid_entry.insert(0, "30.0")
        self.homology_pid_entry.grid(row=3, column=1, padx=(0, 10), pady=5, sticky="ew")

        ttk.Label(card2, text=_("Score:"), font=font_regular).grid(row=3, column=2,
                                                                                                  padx=(15, 5), pady=5,
                                                                                                  sticky="w")
        self.homology_score_entry = ttk.Entry(card2, font=font_regular)
        self.homology_score_entry.insert(0, "50.0")
        self.homology_score_entry.grid(row=3, column=3, padx=(0, 10), pady=5, sticky="ew")

        card3 = ttk.Frame(parent_frame)
        card3.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=10)
        card3.grid_columnconfigure(1, weight=1)

        ttk.Label(card3, text=_("输出文件"), font=font_bold).grid(row=0, column=0,
                                                                                                 columnspan=3, padx=10,
                                                                                                 pady=(10, 15),
                                                                                                 sticky="w")
        ttk.Label(card3, text=_("输出路径:"), font=font_regular).grid(row=1, column=0,
                                                                                                     padx=(15, 5),
                                                                                                     pady=10,
                                                                                                     sticky="w")
        self.homology_output_file_entry = ttk.Entry(card3, font=font_regular)
        self.homology_output_file_entry.grid(row=1, column=1, padx=0, pady=10, sticky="ew")
        # 修复：ttkb.Button 不支持直接的 font 参数
        self.browse_button = ttkb.Button(card3, text=_("浏览..."), width=12,
                                           command=self._browse_output_file, bootstyle="outline")
        self.browse_button.grid(row=1, column=2, padx=10, pady=10)

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_button = ttkb.Button(parent_frame, text=_("开始转换"),
                                        command=self._start_homology_task, bootstyle="success")
        self.start_button.grid(row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=(10, 5))


    def _browse_output_file(self):
        self.app.event_handler._browse_save_file( # 委托给 EventHandler
            self.homology_output_file_entry,
            [(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")]
        )

    def _start_homology_task(self):
        """ 启动基因组转换任务 """
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip()
        source_gene_ids_list = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not source_gene_ids_list:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"))
            return

        source_assembly = self.selected_homology_source_assembly.get()
        target_assembly = self.selected_homology_target_assembly.get()
        if not all([source_assembly, target_assembly]) or _("加载中...") in [source_assembly, target_assembly]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择有效的源和目标基因组。"))
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
            self.app.ui_manager.show_error_message(_("输入错误"), _("高级筛选选项中的阈值必须是有效的数字。"))
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

        # 辅助函数：销毁并重新创建 OptionMenu
        def recreate_option_menu(old_dropdown, variable, new_values, default_row, default_column, **kwargs_for_grid_pack):
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

                command = old_dropdown.cget('command') if 'command' in old_dropdown.configure() else None
                bootstyle = old_dropdown.cget('bootstyle')
                old_dropdown.destroy()
            else:
                # If old_dropdown doesn't exist or is destroyed, use default command and bootstyle
                command = self._on_homology_assembly_selection
                bootstyle = "info"

            if variable.get() not in new_values:
                variable.set(new_values[0] if new_values else "")

            new_dropdown = ttkb.OptionMenu(
                parent_frame,
                variable,
                variable.get(),
                *new_values,
                command=command,
                bootstyle=bootstyle
            )

            if grid_info:
                new_dropdown.grid(**{k: v for k, v in grid_info.items() if k != 'in'})
            elif pack_info:
                new_dropdown.pack(**{k: v for k, v in pack_info.items() if k != 'in'})
            else:
                # Fallback if no layout info was found (e.g., widget not yet laid out)
                new_dropdown.grid(row=default_row, column=default_column, sticky="ew", padx=10, pady=10) # Adjusted for HomologyTab grid layout

            return new_dropdown

        # Recreate source assembly dropdown
        self.source_assembly_dropdown = recreate_option_menu(
            self.source_assembly_dropdown,
            self.selected_homology_source_assembly,
            assembly_ids,
            default_row=1, default_column=1 # Corrected default grid positions for source
        )

        # Recreate target assembly dropdown
        self.target_assembly_dropdown = recreate_option_menu(
            self.target_assembly_dropdown,
            self.selected_homology_target_assembly,
            assembly_ids,
            default_row=2, default_column=1 # Corrected default grid positions for target
        )

        # 2. 检查当前值是否在列表中，如果不在或为空，则设置默认值
        is_valid_list = bool(assembly_ids and _("加载中...") not in assembly_ids[0]) # Adjusted placeholder check

        if is_valid_list:
            # 检查源基因组下拉菜单
            if self.selected_homology_source_assembly.get() not in assembly_ids:
                self.selected_homology_source_assembly.set(assembly_ids[0])

            # 检查目标基因组下拉菜单
            if self.selected_homology_target_assembly.get() not in assembly_ids:
                self.selected_homology_target_assembly.set(assembly_ids[0])


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

        # Get current theme to select appropriate warning color
        current_theme = self.app.style.theme.name
        is_dark_theme = "dark" in current_theme.lower()

        # Use ttkbootstrap colors or define specific ones
        warning_color = self.app.style.colors.warning
        ok_color = self.app.style.colors.success # Or a neutral color like secondary

        source_info = self.app.genome_sources_data.get(source_id)

        # Assuming you have labels for displaying these warnings in your _create_widgets
        # If not, you'd need to add them. For now, just logging.
        # Example for source version display:
        # if hasattr(self, 'source_version_label'):
        #     if source_info and source_info.get('homology_version'):
        #         self.source_version_label.configure(text=f"Homology DB: {source_info['homology_version']}", foreground=ok_color)
        #     else:
        #         self.source_version_label.configure(text=_("Homology DB: Not available"), foreground=warning_color)
        # This part of the code snippet was incomplete, so I'm not adding new UI elements.
        # It's up to you to implement specific labels for these warnings in the UI.