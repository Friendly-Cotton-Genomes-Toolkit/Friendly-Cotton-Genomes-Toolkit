# ui/tabs/data_download_tab.py

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
import os
from typing import TYPE_CHECKING, Dict

# 导入后台任务函数
from cotton_toolkit.pipelines import run_download_pipeline, run_preprocess_annotation_files
# 导入状态检查函数
from cotton_toolkit.config.loader import check_annotation_file_status, get_local_downloaded_file_path
from .base_tab import BaseTab

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class DataDownloadTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)
        self.fasta_var = tk.BooleanVar(value=True)
        self.gff_var = tk.BooleanVar(value=True)
        self.cds_var = tk.BooleanVar(value=True)
        self.pep_var = tk.BooleanVar(value=True)
        self.homology_var = tk.BooleanVar(value=True)

        super().__init__(parent, app)
        self._create_base_widgets()
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # 定义安全的颜色和字体
        safe_text_color = ("gray10", "#DCE4EE")
        font_regular = (self.app.font_family, 14)
        font_bold = (self.app.font_family, 15, "bold")

        # 【颜色修正】为所有 CTkLabel 和 CTkCheckBox 添加 text_color 参数
        ctk.CTkLabel(parent_frame, text=_("1. 选择要下载的基因组"), font=font_bold, text_color=safe_text_color).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        self.genome_option_menu = ctk.CTkOptionMenu(parent_frame, variable=self.selected_genome_var,
                                                    values=[_("配置未加载")], command=self._on_genome_selection_change,
                                                    font=font_regular, dropdown_font=font_regular)
        self.genome_option_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))

        ctk.CTkLabel(parent_frame, text=_("2. 选择要下载的文件类型"), font=font_bold, text_color=safe_text_color).grid(
            row=2, column=0, padx=10, pady=(10, 5), sticky="w")
        checkbox_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        checkbox_frame.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))
        ctk.CTkCheckBox(checkbox_frame, text="Genome (fasta)", variable=self.fasta_var, font=font_regular,
                        text_color=safe_text_color).pack(side="left", padx=10)
        ctk.CTkCheckBox(checkbox_frame, text="Annotation (gff3)", variable=self.gff_var, font=font_regular,
                        text_color=safe_text_color).pack(side="left", padx=10)
        ctk.CTkCheckBox(checkbox_frame, text="CDS", variable=self.cds_var, font=font_regular,
                        text_color=safe_text_color).pack(side="left", padx=10)
        ctk.CTkCheckBox(checkbox_frame, text="Protein (pep)", variable=self.pep_var, font=font_regular,
                        text_color=safe_text_color).pack(side="left", padx=10)
        ctk.CTkCheckBox(checkbox_frame, text=_("同源关系 (homology)"), variable=self.homology_var, font=font_regular,
                        text_color=safe_text_color).pack(side="left", padx=10)

        status_header_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        status_header_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(10, 5))
        status_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(status_header_frame, text=_("文件状态"), font=font_bold, text_color=safe_text_color).grid(row=0,
                                                                                                               column=0,
                                                                                                               sticky="w")
        self.refresh_button = ctk.CTkButton(status_header_frame, text=_("刷新状态"), width=100,
                                            command=self._refresh_status, font=font_regular)
        self.refresh_button.grid(row=0, column=1, sticky="e")

        self.status_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        self.status_frame.grid(row=5, column=0, sticky="ew", padx=15, pady=0)
        self.status_frame.grid_columnconfigure(1, weight=1)  # 确保状态文本有足够空间

        ctk.CTkLabel(parent_frame, text=_("3. 下载选项"), font=font_bold, text_color=safe_text_color).grid(row=6,
                                                                                                           column=0,
                                                                                                           padx=10,
                                                                                                           pady=(15, 5),
                                                                                                           sticky="w")
        options_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        options_frame.grid(row=7, column=0, sticky="w", padx=5, pady=0)
        ctk.CTkCheckBox(options_frame, text=_("强制重新下载 (覆盖本地已存在文件)"), variable=self.force_download_var,
                        font=font_regular, text_color=safe_text_color).pack(anchor="w", padx=10, pady=5)
        ctk.CTkCheckBox(options_frame, text=_("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                        variable=self.use_proxy_for_download_var, font=font_regular, text_color=safe_text_color).pack(
            anchor="w", padx=10, pady=5)

        self.start_button = ctk.CTkButton(parent_frame, text=_("开始下载"), command=self.start_download_task, height=40,
                                          font=font_bold)
        self.start_button.grid(row=8, column=0, sticky="ew", padx=10, pady=(25, 10))

    def _update_file_status_display(self):
        for widget in self.status_frame.winfo_children():
            widget.destroy()
        genome_id = self.selected_genome_var.get()
        if not genome_id or not self.app.current_config or not self.app.genome_sources_data: return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info: return
        status_map = {'not_downloaded': {"text": _("未下载"), "color": ("#D32F2F", "#E57373")},
                      'not_processed': {"text": _("已下载"), "color": ("#F57C00", "#FFB74D")},
                      'processed': {"text": _("已处理"), "color": ("#388E3C", "#A5D6A7")}}
        files_to_check = {'fasta': 'simple', 'gff': 'simple', 'cds': 'simple', 'pep': 'simple', 'homology': 'simple',
                          'GO': 'annotation', 'IPR': 'annotation', 'KEGG_pathways': 'annotation',
                          'KEGG_orthologs': 'annotation'}
        status_labels = []
        for file_type, check_type in files_to_check.items():
            if not (hasattr(genome_info, f"{file_type}_url") and getattr(genome_info, f"{file_type}_url")): continue
            original_path = get_local_downloaded_file_path(self.app.current_config, genome_info, file_type)
            status_key = 'not_downloaded'
            if original_path and os.path.exists(original_path):
                status_key = 'processed' if check_type == 'simple' or os.path.exists(
                    original_path.replace('.xlsx.gz', '.csv').replace('.xlsx', '.csv')) else 'not_processed'
            status_labels.append(
                (f"{file_type.upper()}:", status_map[status_key]["text"], status_map[status_key]["color"]))

        font_regular = (self.app.font_family, 14)
        safe_text_color = ("gray10", "#DCE4EE")
        for i, (label_text, status_text, color) in enumerate(status_labels):
            ctk.CTkLabel(self.status_frame, text=label_text, anchor="w", font=font_regular,
                         text_color=safe_text_color).grid(row=i, column=0, sticky="w", padx=(0, 10))
            ctk.CTkLabel(self.status_frame, text=status_text, text_color=color, anchor="w", font=font_regular).grid(
                row=i, column=1, sticky="w")



    def _on_genome_selection_change(self, selection):
        """当用户在下拉菜单中选择一个新的基因组时调用。"""
        self._update_file_status_display()

    def _refresh_status(self):
        """手动刷新当前选中基因组版本的文件状态。"""
        self.app._log_to_viewer(_("正在手动刷新文件状态..."), "INFO")
        self._update_file_status_display()

    def update_assembly_dropdowns(self, assembly_ids: list):
        filtered_ids = [gid for gid in assembly_ids if "arabidopsis" not in gid.lower()]

        values = filtered_ids if filtered_ids else [_("无可用基因组")]
        self.genome_option_menu.configure(values=values)
        if self.selected_genome_var.get() not in values:
            if values:
                self.selected_genome_var.set(values[0])
            else:
                self.selected_genome_var.set("")

        # 初始加载时也更新一次状态
        self._update_file_status_display()

    def _start_download(self):
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return
        selected_assembly = self.assembly_dropdown_var.get()
        if not selected_assembly or selected_assembly == _("无可用版本"):
            self.app.show_error_message(_("错误"), _("请选择一个要下载的基因组版本。"))
            return

        force_value = self.force_download_var.get()
        cli_overrides = {"versions": [selected_assembly], "force": force_value}

        if hasattr(self.app, '_start_task'):
            self.app._start_task(
                task_name=_("数据下载"),
                target_func=run_download_pipeline,
                kwargs={'config': self.app.current_config, 'cli_overrides': cli_overrides}
            )

    def update_from_config(self):
        if self.app.current_config:
            self.force_download_var.set(self.app.current_config.downloader.force_download)
            self.use_proxy_for_download_var.set(self.app.current_config.downloader.use_proxy_for_download)
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'): self.start_button.configure(state=state)

    def _update_download_genomes_list(self):
        """根据配置动态更新下载列表，并增加“预处理状态”显示。"""
        for widget in self.download_genomes_checkbox_frame.winfo_children():
            widget.destroy()
        self.download_genome_vars.clear()

        processed_color, not_processed_color, not_downloaded_color = ("#28a745", "#73bf69"), ("#ff9800", "#ffb74d"), (
            "#d9534f", "#e57373")
        default_color = self.app.default_label_text_color

        if not self.app.current_config or not self.app.genome_sources_data:
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("请先加载配置文件")).pack()
            return

        self.app._log_to_viewer(_("正在刷新数据下载与预处理状态..."))
        for genome_id, details in self.app.genome_sources_data.items():
            entry_frame = ctk.CTkFrame(self.download_genomes_checkbox_frame, fg_color="transparent")
            entry_frame.pack(fill="x", expand=True, padx=5, pady=2)
            entry_frame.grid_columnconfigure(1, weight=1)

            var = tk.BooleanVar(value=False)
            display_text = f"{genome_id} ({details.species_name})"
            ctk.CTkCheckBox(entry_frame, text=display_text, variable=var, font=(self.app.font_family, 14)).grid(row=0, column=0,
                                                                                                       sticky="w")
            self.download_genome_vars[genome_id] = var

            anno_keys = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs']
            statuses = [check_annotation_file_status(self.app.current_config, details, key) for key in anno_keys]

            if all(s == 'processed' for s in statuses):
                status_text, status_color = "✓ " + _("已处理"), processed_color
            elif all(s == 'not_downloaded' for s in statuses):
                status_text, status_color = "✗ " + _("未下载"), not_downloaded_color
            else:
                status_text, status_color = "● " + _("未处理/部分处理"), not_processed_color

            ctk.CTkLabel(entry_frame, text=status_text, font=(self.app.font_family, 14), text_color=status_color).grid(row=0,
                                                                                                              column=1,
                                                                                                              sticky="e",
                                                                                                              padx=10)
        self.app._log_to_viewer(_("状态刷新完成。"))

    def _toggle_all_download_genomes(self, select: bool):
        """全选或取消全选所有下载基因组的复选框"""
        for var in self.download_genome_vars.values():
            var.set(select)

    def start_download_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"));
            return

        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [_("配置未加载"), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("选择错误"), _("请选择一个有效的基因组进行下载。"));
            return

        file_types = [ft for ft, var in
                      [("fasta", self.fasta_var), ("gff", self.gff_var), ("cds", self.cds_var), ("pep", self.pep_var),
                       ("homology", self.homology_var)] if var.get()]
        if not file_types:
            self.app.ui_manager.show_error_message(_("选择错误"), _("请至少选择一种要下载的文件类型。"));
            return

        self.app.current_config.downloader.force_download = self.force_download_var.get()
        self.app.current_config.downloader.use_proxy_for_download = self.use_proxy_for_download_var.get()

        task_kwargs = {
            'config': self.app.current_config, 'genome_ids': [selected_genome_id],
            'file_types': file_types, 'force': self.force_download_var.get(),

        }

        self.app.event_handler._start_task(  # 委托给 EventHandler
            task_name=_("数据下载"),
            target_func=run_download_pipeline,
            kwargs=task_kwargs
        )

    def start_preprocess_task(self):
        """启动注释文件预处理任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        self.app.event_handler._start_task(  # 委托给 EventHandler
            task_name=_("预处理注释文件"),
            target_func=run_preprocess_annotation_files,
            kwargs={'config': self.app.current_config}
        )
