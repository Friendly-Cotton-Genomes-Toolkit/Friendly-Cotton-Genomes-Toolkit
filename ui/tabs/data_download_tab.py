# 文件路径: ui/tabs/data_download_tab.py

import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Dict, Callable, Any

import ttkbootstrap as ttkb

from cotton_toolkit.config.loader import get_local_downloaded_file_path
from cotton_toolkit.pipelines import run_download_pipeline, run_preprocess_annotation_files
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp


class DataDownloadTab(BaseTab):
    # 【修改】构造函数接收 translator 并传递给父类
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self._translator = translator  # 临时保存一下，因为 super().__init__ 会覆盖 self._
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}

        self.FILE_TYPE_DISPLAY_NAMES_KEYS = {
            "gff3": "注释 (gff3)",
            "GO": "GO",
            "IPR": "IPR",
            "KEGG_pathways": "KEGG 通路",
            "KEGG_orthologs": "KEGG 直系同源",
            "homology_ath": "同源关系 (拟南芥)",
        }
        self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED: Dict[str, str] = {}

        self._genome_option_menu_command = self._on_genome_selection_change
        self.dynamic_widgets = {}

        # 调用父类构造函数，它会设置好 self._
        super().__init__(parent, app, translator)

        if self.action_button:
            self.download_button = self.action_button
            # 【修改】使用 self._
            self.download_button.configure(text=self._("开始下载"), command=self.start_download_task)
            action_frame = self.download_button.master

            # 【修改】使用 self._
            self.preprocess_button = ttkb.Button(action_frame, text=self._("预处理注释文件"),
                                                 command=self.start_preprocess_task, bootstyle="primary")
            self.preprocess_button.grid(row=0, column=0, sticky="se", padx=(0, 10), pady=10)
            self.download_button.grid(row=0, column=1, sticky="se", padx=(0, 15), pady=10)

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # 【修改】所有 _() 调用都改为 self._()
        self.title_label = ttkb.Label(parent_frame, text=self._("数据下载与预处理"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        self.genome_card = ttkb.LabelFrame(parent_frame, text=self._("选择基因组"), bootstyle="secondary")
        self.genome_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.genome_card.grid_columnconfigure(1, weight=1)

        self.genome_version_label = ttkb.Label(self.genome_card, text=self._("基因组版本:"),
                                               font=self.app.app_font_bold)
        self.genome_version_label.grid(row=0, column=0, sticky="w", padx=(10, 5), pady=10)

        initial_value = self._("配置未加载")
        self.genome_option_menu = ttkb.OptionMenu(self.genome_card, self.selected_genome_var, initial_value,
                                                  *[initial_value], command=self._on_genome_selection_change,
                                                  bootstyle="info")
        self.genome_option_menu.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

        self.dynamic_content_frame = ttkb.LabelFrame(parent_frame, text=self._("文件类型与状态"), bootstyle="secondary")
        self.dynamic_content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.dynamic_content_frame.grid_columnconfigure(0, weight=1)

        self.options_card = ttkb.LabelFrame(parent_frame, text=self._("下载选项"), bootstyle="secondary")
        self.options_card.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        self.options_card.grid_columnconfigure(0, weight=1)

        self.force_download_check = ttkb.Checkbutton(self.options_card,
                                                     text=self._("强制重新下载 (覆盖本地已存在文件)"),
                                                     variable=self.force_download_var, bootstyle="round-toggle")
        self.force_download_check.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.use_proxy_check = ttkb.Checkbutton(self.options_card,
                                                text=self._("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                                                variable=self.use_proxy_for_download_var, bootstyle="round-toggle")
        self.use_proxy_check.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    def retranslate_ui(self, translator: Callable[[str], str]):
        self._ = translator  # 确保 self._ 是最新的
        self.title_label.configure(text=self._("数据下载与预处理"))
        self.genome_card.configure(text=self._("选择基因组"))
        self.genome_version_label.configure(text=self._("基因组版本:"))
        self.dynamic_content_frame.configure(text=self._("文件类型与状态"))
        self.options_card.configure(text=self._("下载选项"))
        self.force_download_check.configure(text=self._("强制重新下载 (覆盖本地已存在文件)"))
        self.use_proxy_check.configure(text=self._("对数据下载使用网络代理 (请在配置编辑器中设置)"))

        self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.clear()
        for key, display_name_key in self.FILE_TYPE_DISPLAY_NAMES_KEYS.items():
            self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED[key] = self._(display_name_key)

        self.app.ui_manager.update_option_menu(
            self.genome_option_menu,
            self.selected_genome_var,
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [],
            self._("无可用基因组"),
            self._on_genome_selection_change
        )

        self._update_dynamic_widgets(self.selected_genome_var.get())

        if hasattr(self, 'download_button'):
            self.download_button.configure(text=self._("开始下载"))
        if hasattr(self, 'preprocess_button'):
            self.preprocess_button.configure(text=self._("预处理注释文件"))

    def _update_dynamic_widgets(self, genome_id: str):
        for widget in self.dynamic_content_frame.winfo_children(): widget.destroy()
        self.file_type_vars.clear()
        self.dynamic_widgets.clear()

        if not genome_id or not self.app.genome_sources_data: return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info: return

        checkbox_frame = ttkb.LabelFrame(self.dynamic_content_frame, text=self._("选择文件类型"), bootstyle="light")
        checkbox_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.dynamic_widgets['checkbox_frame'] = checkbox_frame

        status_card = ttkb.LabelFrame(self.dynamic_content_frame, text=self._("文件状态"), bootstyle="light")
        status_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        status_card.grid_columnconfigure(1, weight=1)
        self.dynamic_widgets['status_card'] = status_card

        refresh_button = ttkb.Button(status_card, text=self._("刷新状态"), width=12,
                                     command=lambda: self._update_dynamic_widgets(self.selected_genome_var.get()),
                                     bootstyle="info-outline")
        refresh_button.grid(row=0, column=2, sticky="e", padx=(0, 10), pady=(5, 0))
        self.dynamic_widgets['refresh_button'] = refresh_button

        status_map = {
            'not_downloaded': {"text": self._("未下载"), "color": self.app.style.colors.danger},
            'downloaded': {"text": self._("已下载 (待处理)"), "color": self.app.style.colors.warning},
            'processed': {"text": self._("已就绪"), "color": self.app.style.colors.success}
        }

        status_row_idx, checkbox_col_idx, checkbox_row_idx, checkbox_count = 1, 0, 0, 0
        for key in self.FILE_TYPE_DISPLAY_NAMES_KEYS.keys():
            display_name = self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.get(key, key)
            url_attr = f"{key}_url"
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                var = tk.BooleanVar(value=True)
                self.file_type_vars[key] = var
                ttkb.Checkbutton(checkbox_frame, text=display_name, variable=var, bootstyle="round-toggle").grid(
                    row=checkbox_row_idx, column=checkbox_col_idx, sticky='w', padx=5, pady=5)
                checkbox_col_idx += 1
                if checkbox_col_idx >= 2: checkbox_col_idx = 0; checkbox_row_idx += 1
                checkbox_count += 1

                local_path = get_local_downloaded_file_path(self.app.current_config, genome_info, key)
                status_key = 'not_downloaded'
                if local_path and os.path.exists(local_path):
                    is_special_excel = local_path.lower().endswith(('.xlsx', '.xlsx.gz'))
                    if is_special_excel:
                        csv_path = local_path.rsplit('.', 2)[0] + '.csv' if local_path.lower().endswith('.gz') else \
                            local_path.rsplit('.', 1)[0] + '.csv'
                        status_key = 'processed' if os.path.exists(csv_path) else 'downloaded'
                    else:
                        status_key = 'processed'
                status_info = status_map[status_key]

                file_type_label = ttkb.Label(status_card, text=f"{display_name}:", font=self.app.app_font_bold,
                                             anchor="e")
                file_type_label.grid(row=status_row_idx, column=0, sticky="w", padx=(10, 5), pady=2)
                file_type_label.bind('<Configure>', lambda e, label=file_type_label: label.config(wraplength=e.width))

                status_label = ttk.Label(status_card, text=status_info["text"], foreground=status_info["color"],
                                         anchor="w")
                status_label.grid(row=status_row_idx, column=1, sticky="ew", padx=5, pady=2)
                status_label.bind('<Configure>', lambda e, label=status_label: label.config(wraplength=e.width))

                status_row_idx += 1

        if checkbox_count == 0:
            no_url_label = ttk.Label(checkbox_frame,
                                     text=self._("当前基因组版本在配置文件中没有可供下载的URL链接。"))
            no_url_label.pack(padx=10, pady=10)
            self.dynamic_widgets['no_url_label'] = no_url_label

        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _on_genome_selection_change(self, selection: str):
        self._update_dynamic_widgets(selection)

    def update_assembly_dropdowns(self, assembly_ids: list):
        filtered_ids = [gid for gid in assembly_ids if "arabidopsis" not in gid.lower()]
        values = filtered_ids if filtered_ids else [self._("无可用基因组")]
        dropdown = self.genome_option_menu
        if not (dropdown and dropdown.winfo_exists()): return

        self.app.ui_manager.update_option_menu(
            dropdown,
            self.selected_genome_var,
            values,
            self._("无可用基因组"),
            self._on_genome_selection_change
        )

        if self.selected_genome_var.get() not in values:
            self.selected_genome_var.set(values[0])
            self._on_genome_selection_change(self.selected_genome_var.get())

    def update_from_config(self):
        if self.app.current_config:
            self.force_download_var.set(self.app.current_config.downloader.force_download)
            self.use_proxy_for_download_var.set(self.app.current_config.downloader.use_proxy_for_download)

        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        else:
            self.update_assembly_dropdowns([])
        self._update_dynamic_widgets(self.selected_genome_var.get())

    def update_button_state(self, is_running, has_config):
        super().update_button_state(is_running, has_config)
        if hasattr(self, 'preprocess_button'):
            self.preprocess_button.configure(state="disabled" if is_running or not has_config else "normal")
        if 'refresh_button' in self.dynamic_widgets and self.dynamic_widgets['refresh_button'].winfo_exists():
            self.dynamic_widgets['refresh_button'].configure(
                state="disabled" if is_running or not has_config else "normal")

    def start_download_task(self):
        # 【修改】所有 _() 调用都改为 self._()
        if not self.app.current_config: self.app.ui_manager.show_error_message(self._("错误"),
                                                                               self._("请先加载配置文件。")); return
        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [self._("配置未加载"), self._("无可用基因组")]:
            self.app.ui_manager.show_error_message(self._("选择错误"), self._("请选择一个有效的基因组进行下载。"));
            return
        file_types_to_download = [key for key, var in self.file_type_vars.items() if var.get()]
        if not file_types_to_download:
            self.app.ui_manager.show_error_message(self._("选择错误"), self._("请至少选择一种要下载的文件类型。"));
            return
        self.app.current_config.downloader.force_download = self.force_download_var.get()
        self.app.current_config.downloader.use_proxy_for_download = self.use_proxy_for_download_var.get()
        task_kwargs = {
            'config': self.app.current_config,
            'cli_overrides': {'versions': [selected_genome_id], 'file_types': file_types_to_download,
                              'force': self.force_download_var.get()}
        }
        self.app.event_handler._start_task(task_name=self._("数据下载"), target_func=run_download_pipeline,
                                           kwargs=task_kwargs)

    def start_preprocess_task(self):
        # 【修改】所有 _() 调用都改为 self._()
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(self._("错误"), self._("请先加载配置文件。"));
            return
        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [self._("配置未加载"), self._("无可用基因组")]:
            self.app.ui_manager.show_error_message(self._("选择错误"), self._("请选择一个有效的基因组进行预处理。"));
            return
        genome_info = self.app.genome_sources_data.get(selected_genome_id)
        if not genome_info:
            msg = self._("找不到基因组 '{}' 的信息。").format(selected_genome_id)
            self.app.ui_manager.show_error_message(self._("错误"), msg);
            return

        excel_anno_keys = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']
        missing_files_display_names = []
        for key in excel_anno_keys:
            url_attr = f"{key}_url"
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                local_path = get_local_downloaded_file_path(self.app.current_config, genome_info, key)
                if not local_path or not os.path.exists(local_path):
                    missing_files_display_names.append(self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.get(key, key))

        if missing_files_display_names:
            file_list_formatted = "\n- ".join(missing_files_display_names)

            # 【修改】使用 self._() 来翻译，并移除所有调试用的 print 语句
            msg = self._("无法开始预处理，以下必需的注释文件尚未下载：\n\n- {file_list}\n\n请先下载它们。").format(
                file_list=file_list_formatted)

            self.app.ui_manager.show_warning_message(self._("缺少文件"), msg)
            return

        task_kwargs = {'config': self.app.current_config}
        self.app.event_handler._start_task(task_name=self._("预处理注释文件"),
                                           target_func=run_preprocess_annotation_files,
                                           kwargs=task_kwargs)