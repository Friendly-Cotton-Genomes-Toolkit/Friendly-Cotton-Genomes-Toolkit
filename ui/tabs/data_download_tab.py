# ui/tabs/data_download_tab.py

import tkinter as tk
import customtkinter as ctk
import os
from typing import TYPE_CHECKING, Dict

# 导入后台任务函数
from cotton_toolkit.pipelines import run_download_pipeline, run_preprocess_annotation_files
# 导入状态检查函数
from cotton_toolkit.config.loader import check_annotation_file_status
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
        super().__init__(parent, app)
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self._create_widgets()
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame

        # 【核心修改】在顶部添加一个标题
        ctk.CTkLabel(parent_frame, text=_("数据下载"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(5, 15), padx=10, sticky="n")

        # 后续卡片的 row 从 1 开始
        selection_card = ctk.CTkFrame(parent_frame, border_width=0)
        selection_card.grid(row=1, column=0, sticky="ew", padx=5, pady=(5, 10))
        selection_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(selection_card, text=_("版本选择与操作"), font=self.app.app_font_bold).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))

        ctk.CTkLabel(selection_card, text=_("选择基因组:"), font=self.app.app_font).grid(
            row=1, column=0, sticky="w", padx=(15, 5), pady=10)

        self.assembly_dropdown_var = tk.StringVar()

        self.assembly_dropdown = ctk.CTkOptionMenu(
            selection_card, variable=self.assembly_dropdown_var, values=[_("无可用版本")],
            font=self.app.app_font, dropdown_font=self.app.app_font, command=self._on_assembly_selected
        )
        self.assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=10, pady=10)

        self.start_button = ctk.CTkButton(
            selection_card, text=_("下载选中版本的所有文件"), command=self._start_download,
            font=self.app.app_font_bold
        )
        self.start_button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 15))

        files_card = ctk.CTkFrame(parent_frame, border_width=0)
        files_card.grid(row=2, column=0, sticky="ew", padx=5, pady=10)
        files_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(files_card, text=_("下载文件列表"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        self.files_frame = ctk.CTkFrame(files_card, fg_color="transparent")
        self.files_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
        self.files_frame.grid_columnconfigure(0, weight=1)


    def update_assembly_dropdowns(self, assembly_ids: list):
        if not assembly_ids: assembly_ids = [_("无可用版本")]
        self.assembly_dropdown.configure(values=assembly_ids)
        current_selection = self.assembly_dropdown_var.get()
        if current_selection not in assembly_ids:
            self.assembly_dropdown_var.set(assembly_ids[0])
        self._on_assembly_selected(self.assembly_dropdown_var.get())

    def _on_assembly_selected(self, selected_assembly: str):
        for widget in self.files_frame.winfo_children():
            widget.destroy()
        if not self.app.genome_sources_data or selected_assembly == _("无可用版本"):
            ctk.CTkLabel(self.files_frame, text=_("请先加载配置并选择一个有效的基因组版本。")).pack(pady=10)
            return
        genome_info = self.app.genome_sources_data.get(selected_assembly)
        if not genome_info: return
        file_types_to_check = ['gff3', 'GO', 'IPR', 'KEGG_orthologs', 'KEGG_pathways', 'homology_ath']
        found_any_file = False
        for file_type in file_types_to_check:
            if hasattr(genome_info, f"{file_type}_url") and getattr(genome_info, f"{file_type}_url"):
                found_any_file = True
                status = self.app._check_genome_download_status(genome_info, file_type)
                self._add_file_status_row(file_type, status)
        if not found_any_file:
            ctk.CTkLabel(self.files_frame, text=_("该基因组版本没有配置任何可下载的文件。")).pack(pady=10)



    def _add_file_status_row(self, file_type: str, status: str):
        status_map = {"complete": {"text": _("已下载"), "color": ("#2E7D32", "#A5D6A7")},
                      "incomplete": {"text": _("不完整"), "color": ("#D84315", "#FF7043")},
                      "missing": {"text": _("未下载"), "color": ("#495057", "#adb5bd")}}
        info = status_map.get(status, {"text": _("未知"), "color": "gray"})
        row_frame = ctk.CTkFrame(self.files_frame, fg_color="transparent")
        row_frame.pack(fill="x", expand=True, pady=2)
        ctk.CTkLabel(row_frame, text=f"• {file_type.replace('_', ' ').title()}:", anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(row_frame, text=info["text"], text_color=info["color"], anchor="e").pack(side="right", padx=5)



    def _start_download(self):
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return
        selected_assembly = self.assembly_dropdown_var.get()
        if not selected_assembly or selected_assembly == _("无可用版本"):
            self.app.show_error_message(_("错误"), _("请选择一个要下载的基因组版本。"))
            return
        if hasattr(self.app, 'start_download_task'):
            self.app.start_download_task([selected_assembly])



    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        else: self.update_assembly_dropdowns([])

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'):
            self.start_button.configure(state=state)


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
            ctk.CTkCheckBox(entry_frame, text=display_text, variable=var, font=self.app.app_font).grid(row=0, column=0,
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

            ctk.CTkLabel(entry_frame, text=status_text, font=self.app.app_font, text_color=status_color).grid(row=0,
                                                                                                              column=1,
                                                                                                              sticky="e",
                                                                                                              padx=10)
        self.app._log_to_viewer(_("状态刷新完成。"))

    def _toggle_all_download_genomes(self, select: bool):
        """全选或取消全选所有下载基因组的复选框"""
        for var in self.download_genome_vars.values():
            var.set(select)




    def start_download_task(self):
        """启动数据下载任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 1. 获取所有被勾选的版本
        versions_to_download = [gid for gid, var in self.download_genome_vars.items() if var.get()]

        # 2. 【BUG修复】在这里增加前置检查，确保至少选择了一项
        if not versions_to_download:
            self.app.show_warning_message(
                title=_("未选择版本"),
                message=_("请至少勾选一个需要下载的基因组版本。")
            )
            return  # 如果未选择，则终止函数执行

        # 3. 继续执行后续逻辑
        proxies = None
        if self.download_proxy_var.get():
            http_proxy = self.app.current_config.downloader.proxies.http
            https_proxy = self.app.current_config.downloader.proxies.https
            if http_proxy or https_proxy:
                proxies = {'http': http_proxy, 'https': https_proxy}
            else:
                self.app.show_warning_message(_("代理未配置"), _("您开启了代理开关，但配置文件中未找到有效的代理地址。"))
                return

        cli_overrides = {"versions": versions_to_download, "force": self.download_force_checkbox_var.get(),
                         "proxies": proxies}

        self.app._start_task(
            task_name=_("数据下载"),
            target_func=run_download_pipeline,
            kwargs={'config': self.app.current_config, 'cli_overrides': cli_overrides}
        )

    def start_preprocess_task(self):
        """启动注释文件预处理任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return
        self.app._start_task(
            task_name=_("预处理注释文件"),
            target_func=run_preprocess_annotation_files,
            kwargs={'config': self.app.current_config}
        )