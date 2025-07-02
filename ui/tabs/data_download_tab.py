# 文件路径: ui/tabs/data_download_tab.py

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import os
from typing import TYPE_CHECKING, Dict

from cotton_toolkit.pipelines import run_download_pipeline
from cotton_toolkit.config.loader import get_local_downloaded_file_path
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class DataDownloadTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}
        self.FILE_TYPE_MAP = {
            "gff3": "Annotation (gff3)", "GO": "GO", "IPR": "IPR",
            "KEGG_pathways": "KEGG Pathways", "KEGG_orthologs": "KEGG Orthologs",
            "homology_ath": _("同源关系 (homology)"),
        }
        self._genome_option_menu_command = self._on_genome_selection_change

        super().__init__(parent, app)

        if self.action_button:
            self.action_button.configure(text=_("开始下载"), command=self.start_download_task)

        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        genome_card = ttkb.LabelFrame(parent_frame, text=_("1. 选择要下载的基因组"), bootstyle="primary")
        genome_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        genome_card.grid_columnconfigure(0, weight=1)
        initial_value = _("配置未加载")
        self.genome_option_menu = ttkb.OptionMenu(genome_card, self.selected_genome_var, initial_value,
                                                  *[initial_value], command=self._genome_option_menu_command,
                                                  bootstyle="info")
        self.genome_option_menu.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.dynamic_content_frame = ttkb.LabelFrame(parent_frame, text=_("2. 选择要下载的文件类型"), bootstyle="info")
        self.dynamic_content_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.dynamic_content_frame.grid_columnconfigure(0, weight=1)

        options_card = ttkb.LabelFrame(parent_frame, text=_("3. 下载选项"), bootstyle="secondary")
        options_card.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        options_card.grid_columnconfigure(0, weight=1)
        ttkb.Checkbutton(options_card, text=_("强制重新下载 (覆盖本地已存在文件)"), variable=self.force_download_var,
                         bootstyle="round-toggle").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        ttkb.Checkbutton(options_card, text=_("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                         variable=self.use_proxy_for_download_var, bootstyle="round-toggle").grid(row=1, column=0,
                                                                                                  sticky="w", padx=10,
                                                                                                  pady=5)

    def _update_dynamic_widgets(self, genome_id: str):
        for widget in self.dynamic_content_frame.winfo_children(): widget.destroy()
        self.file_type_vars.clear()
        if not genome_id or not self.app.genome_sources_data: return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info: return
        checkbox_frame = ttk.Frame(self.dynamic_content_frame);
        checkbox_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        status_card = ttkb.LabelFrame(self.dynamic_content_frame, text=_("文件状态"), bootstyle="light");
        status_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10);
        status_card.grid_columnconfigure(1, weight=1)
        self.refresh_button = ttkb.Button(status_card, text=_("刷新状态"), width=12,
                                          command=lambda: self._update_dynamic_widgets(self.selected_genome_var.get()),
                                          bootstyle="info-outline");
        self.refresh_button.grid(row=0, column=2, sticky="e", padx=(0, 10), pady=(5, 0))
        status_map = {'not_downloaded': {"text": _("未下载"), "color": self.app.style.colors.danger},
                      'downloaded': {"text": _("已下载 (待处理)"), "color": self.app.style.colors.warning},
                      'processed': {"text": _("已就绪"), "color": self.app.style.colors.success}}
        status_row_idx, checkbox_col_idx, checkbox_row_idx, checkbox_count = 1, 0, 0, 0
        for key, display_name in self.FILE_TYPE_MAP.items():
            url_attr = f"{key}_url"
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                var = tk.BooleanVar(value=True);
                self.file_type_vars[key] = var
                ttkb.Checkbutton(checkbox_frame, text=display_name, variable=var, bootstyle="round-toggle").grid(
                    row=checkbox_row_idx, column=checkbox_col_idx, sticky='w', padx=5, pady=5)
                checkbox_col_idx += 1
                if checkbox_col_idx >= 2: checkbox_col_idx = 0; checkbox_row_idx += 1
                checkbox_count += 1
                local_path = get_local_downloaded_file_path(self.app.current_config, genome_info, key);
                status_key = 'not_downloaded'
                if local_path and os.path.exists(local_path):
                    is_special_excel = local_path.lower().endswith(('.xlsx', '.xlsx.gz'))
                    if is_special_excel:
                        csv_path = local_path.rsplit('.', 2)[0] + '.csv' if local_path.lower().endswith('.gz') else \
                        local_path.rsplit('.', 1)[0] + '.csv'
                        status_key = 'processed' if os.path.exists(csv_path) else 'downloaded'
                    else:
                        status_key = 'processed'
                status_info = status_map[status_key];
                ttk.Label(status_card, text=f"{display_name}:", anchor="e").grid(row=status_row_idx, column=0,
                                                                                 sticky="w", padx=(10, 5), pady=2);
                ttk.Label(status_card, text=status_info["text"], foreground=status_info["color"], anchor="w").grid(
                    row=status_row_idx, column=1, sticky="w", padx=5, pady=2);
                status_row_idx += 1
        if checkbox_count == 0: ttk.Label(checkbox_frame,
                                          text=_("当前基因组版本在配置文件中没有可供下载的URL链接。")).pack(padx=10,
                                                                                                           pady=10)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _on_genome_selection_change(self, selection):
        self._update_dynamic_widgets(selection)

    def update_assembly_dropdowns(self, assembly_ids: list):
        filtered_ids = [gid for gid in assembly_ids if "arabidopsis" not in gid.lower()];
        values = filtered_ids if filtered_ids else [_("无可用基因组")];
        dropdown = self.genome_option_menu
        if not (dropdown and dropdown.winfo_exists()): return
        menu = dropdown['menu'];
        menu.delete(0, 'end')
        for value in values: menu.add_command(label=value, command=tk._setit(self.selected_genome_var, value,
                                                                             self._on_genome_selection_change))
        if self.selected_genome_var.get() not in values: self.selected_genome_var.set(values[0])
        self._on_genome_selection_change(self.selected_genome_var.get())

    def update_from_config(self):
        if self.app.current_config: self.force_download_var.set(
            self.app.current_config.downloader.force_download); self.use_proxy_for_download_var.set(
            self.app.current_config.downloader.use_proxy_for_download)
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        else:
            self.update_assembly_dropdowns([])

    def update_button_state(self, is_running, has_config):
        super().update_button_state(is_running, has_config)
        if hasattr(self, 'refresh_button'): self.refresh_button.configure(
            state="disabled" if is_running or not has_config else "normal")

    def start_download_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"),
                                                                               _("请先加载配置文件。")); return
        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [_("配置未加载"),
                                                            _("无可用基因组")]: self.app.ui_manager.show_error_message(
            _("选择错误"), _("请选择一个有效的基因组进行下载。")); return
        file_types_to_download = [key for key, var in self.file_type_vars.items() if var.get()]
        if not file_types_to_download: self.app.ui_manager.show_error_message(_("选择错误"),
                                                                              _("请至少选择一种要下载的文件类型。")); return
        self.app.current_config.downloader.force_download = self.force_download_var.get();
        self.app.current_config.downloader.use_proxy_for_download = self.use_proxy_for_download_var.get()
        task_kwargs = {'config': self.app.current_config,
                       'cli_overrides': {'versions': [selected_genome_id], 'file_types': file_types_to_download,
                                         'force': self.force_download_var.get()}}
        self.app.event_handler._start_task(task_name=_("数据下载"), target_func=run_download_pipeline,
                                           kwargs=task_kwargs)