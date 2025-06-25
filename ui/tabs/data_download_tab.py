# ui/tabs/data_download_tab.py

import tkinter as tk
import customtkinter as ctk
import os
from typing import TYPE_CHECKING, Dict

# 导入后台任务函数
from cotton_toolkit.pipelines import run_download_pipeline, run_preprocess_annotation_files
# 导入状态检查函数
from cotton_toolkit.config.loader import check_annotation_file_status

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class DataDownloadTab(ctk.CTkFrame):
    """ “数据下载”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 1. 将所有 download 相关的 Tkinter 变量移到这里
        self.download_genome_vars: Dict[str, tk.BooleanVar] = {}
        self.download_force_checkbox_var = tk.BooleanVar(value=False)
        self.download_proxy_var = tk.BooleanVar(value=False)

        # 2. 调用UI创建和初始化方法
        self._create_widgets()
        self.update_from_config()

    def _create_widgets(self):
        """创建数据下载选项卡的全部UI控件。"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold

        target_card = ctk.CTkFrame(self)
        target_card.pack(fill="both", expand=True, pady=(15, 10), padx=15)
        target_card.grid_columnconfigure(0, weight=1)
        target_card.grid_rowconfigure(2, weight=1)

        target_header_frame = ctk.CTkFrame(target_card, fg_color="transparent")
        target_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        target_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(target_header_frame, text=_("下载目标: 选择基因组版本"), font=app_font_bold).grid(row=0, column=0,
                                                                                                       sticky="w")

        selection_buttons_frame = ctk.CTkFrame(target_header_frame, fg_color="transparent")
        selection_buttons_frame.grid(row=0, column=1, sticky="e")

        # 注意 command 指向本类的方法
        ctk.CTkButton(selection_buttons_frame, text=_("刷新状态"), width=90, height=28, font=app_font,
                      command=self._update_download_genomes_list).pack(side="left", padx=(0, 10))
        ctk.CTkButton(selection_buttons_frame, text=_("全选"), width=80, height=28, font=app_font,
                      command=lambda: self._toggle_all_download_genomes(True)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(selection_buttons_frame, text=_("取消全选"), width=90, height=28, font=app_font,
                      command=lambda: self._toggle_all_download_genomes(False)).pack(side="left")

        ctk.CTkLabel(target_card, text=_("勾选需要下载的基因组版本。若不勾选任何项，将默认下载所有可用版本。"),
                     text_color=self.app.secondary_text_color, font=app_font, wraplength=500).grid(row=1, column=0,
                                                                                                   padx=10,
                                                                                                   pady=(0, 10),
                                                                                                   sticky="w")

        self.download_genomes_checkbox_frame = ctk.CTkScrollableFrame(target_card, label_text="")
        self.download_genomes_checkbox_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.app._bind_mouse_wheel_to_scrollable(self.download_genomes_checkbox_frame)

        options_frame = ctk.CTkFrame(self)
        options_frame.pack(fill="x", expand=False, pady=10, padx=15)
        options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options_frame, text=_("下载选项"), font=app_font_bold).grid(row=0, column=0, columnspan=2, padx=10,
                                                                                 pady=(10, 15), sticky="w")

        proxy_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        proxy_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        ctk.CTkSwitch(proxy_frame, text=_("使用网络代理 (需在配置中设置)"), variable=self.download_proxy_var,
                      font=app_font).pack(side="left")

        force_download_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        force_download_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))

        ctk.CTkLabel(force_download_frame, text=_("强制重新下载:"), font=app_font).pack(side="left", padx=(0, 10))
        ctk.CTkSwitch(force_download_frame, text="", variable=self.download_force_checkbox_var).pack(side="left")

        ctk.CTkButton(options_frame, text=_("预处理注释文件 (转为标准CSV)"), font=app_font,
                      command=self.start_preprocess_task).grid(row=3, column=0, columnspan=2, padx=10, pady=(5, 15),
                                                               sticky="ew")

        ctk.CTkButton(self, text=_("开始下载"), height=40, command=self.start_download_task, font=app_font_bold).pack(
            fill="x", padx=15, pady=(10, 15), side="bottom")

    def update_from_config(self):
        """由主应用调用，用于在配置加载时更新本页面。"""
        self._update_download_genomes_list()

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

        versions_to_download = [gid for gid, var in self.download_genome_vars.items() if var.get()] or None

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