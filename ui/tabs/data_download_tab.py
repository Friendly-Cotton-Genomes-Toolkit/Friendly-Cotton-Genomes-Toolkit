# ui/tabs/data_download_tab.py

import tkinter as tk
from tkinter import ttk  # Import ttk module
import ttkbootstrap as ttkb  # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants
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


class DataDownloadTab(BaseTab):  # Assuming BaseTab is converted to ttkbootstrap
    def __init__(self, parent, app: "CottonToolkitApp"):
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)

        # This dictionary now stores dynamically created widget variables
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}
        # This dictionary defines all possible file types and their display names, corresponding to models.py
        # The UI will decide whether to display these options based on whether the URL exists in the configuration file.
        self.FILE_TYPE_MAP = {
            "gff3": "Annotation (gff3)",
            "GO": "GO",
            "IPR": "IPR",
            "KEGG_pathways": "KEGG Pathways",
            "KEGG_orthologs": "KEGG Orthologs",
            "homology_ath": _("同源关系 (homology)"),
        }

        # Store initial command and bootstyle for OptionMenu recreation
        self._genome_option_menu_command = self._on_genome_selection_change
        self._genome_option_menu_bootstyle = "info"

        super().__init__(parent, app)
        self._create_base_widgets()
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        font_bold = self.app.app_font_bold  # Use font from app
        font_regular = self.app.app_font  # Use font from app
        # Fix: Colors object has no 'foreground' attribute, should use get_foreground() method
        safe_text_color = self.app.style.lookup('TLabel', 'foreground')  # Use foreground from theme

        ttk.Label(parent_frame, text=_("1. 选择要下载的基因组"), font=font_bold, foreground=safe_text_color).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        # Fix: ttkb.OptionMenu does not support direct font parameter
        initial_value = [_("配置未加载")][0]  # Ensure a default value
        self.genome_option_menu = ttkb.OptionMenu(parent_frame, self.selected_genome_var,
                                                  initial_value,  # Default value
                                                  *_([_("配置未加载")]),  # Option list
                                                  command=self._genome_option_menu_command,
                                                  bootstyle=self._genome_option_menu_bootstyle)
        self.genome_option_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))

        # --- Container for dynamic content ---
        # This frame will be populated by the _update_dynamic_widgets method based on the configuration file content.
        # Added bootstyle="secondary" for a card-like appearance
        self.dynamic_content_frame = ttkb.Frame(parent_frame, bootstyle="secondary")
        self.dynamic_content_frame.grid(row=2, column=0, sticky="nsew", padx=10)
        self.dynamic_content_frame.grid_columnconfigure(0, weight=1)

        # --- Static download options ---
        ttk.Label(parent_frame, text=_("3. 下载选项"), font=font_bold, foreground=safe_text_color).grid(row=3,
                                                                                                        column=0,
                                                                                                        padx=10,
                                                                                                        pady=(15, 5),
                                                                                                        sticky="w")
        options_frame = ttk.Frame(parent_frame)
        options_frame.grid(row=4, column=0, sticky="w", padx=5, pady=0)
        # Fix: ttkb.Checkbutton does not support direct font parameter
        ttkb.Checkbutton(options_frame, text=_("强制重新下载 (覆盖本地已存在文件)"), variable=self.force_download_var,
                         bootstyle="round-toggle",
                         ).pack(anchor="w", padx=10, pady=5)
        # Fix: ttkb.Checkbutton does not support direct font parameter
        ttkb.Checkbutton(options_frame, text=_("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                         variable=self.use_proxy_for_download_var, bootstyle="round-toggle",
                         ).pack(anchor="w", padx=10, pady=5)

        # Fix: ttkb.Button does not support direct font parameter
        self.start_button = ttkb.Button(parent_frame, text=_("开始下载"), command=self.start_download_task,
                                        bootstyle="success")
        self.start_button.grid(row=5, column=0, sticky="ew", padx=10, pady=(25, 10))

    def _update_dynamic_widgets(self, genome_id: str):
        """Dynamically creates file type checkboxes and file status labels based on the selected genome."""
        # Clean up old widgets
        for widget in self.dynamic_content_frame.winfo_children():
            widget.destroy()
        self.file_type_vars.clear()

        if not genome_id or not self.app.genome_sources_data: return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info: return

        font_bold = self.app.app_font_bold
        font_regular = self.app.app_font
        # Fix: Colors object has no 'foreground' attribute, should use get_foreground() method
        safe_text_color = self.app.style.lookup('TLabel', 'foreground')
        # Check for dark theme to adjust placeholder color
        current_theme = self.app.style.theme.name
        is_dark_theme = "dark" in current_theme.lower()
        placeholder_color_value = self.app.placeholder_color[1] if is_dark_theme else self.app.placeholder_color[0]

        ttk.Label(self.dynamic_content_frame, text=_("2. 选择要下载的文件类型"), font=font_bold,
                  foreground=safe_text_color).grid(row=0, column=0, sticky="w", pady=(10, 5))
        checkbox_frame = ttk.Frame(self.dynamic_content_frame)
        checkbox_frame.grid(row=1, column=0, sticky="w", pady=(0, 10))

        status_header_frame = ttk.Frame(self.dynamic_content_frame)
        status_header_frame.grid(row=2, column=0, sticky="ew", pady=(10, 5))
        status_header_frame.grid_columnconfigure(0, weight=1)
        ttk.Label(status_header_frame, text=_("文件状态"), font=font_bold, foreground=safe_text_color).grid(row=0,
                                                                                                            column=0,
                                                                                                            sticky="w")
        # Fix: ttkb.Button does not support direct font parameter
        self.refresh_button = ttkb.Button(status_header_frame, text=_("刷新状态"), width=12,
                                          command=lambda: self._update_dynamic_widgets(
                                              self.selected_genome_var.get()), bootstyle="info-outline")
        self.refresh_button.grid(row=0, column=1, sticky="e")

        status_frame = ttk.Frame(self.dynamic_content_frame)
        status_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=0)
        status_frame.grid_columnconfigure(1, weight=1)

        # Using ttkbootstrap theme colors
        status_map = {'not_downloaded': {"text": _("未下载"), "color": self.app.style.colors.danger},
                      'downloaded': {"text": _("已下载 (待处理)"), "color": self.app.style.colors.warning},
                      'processed': {"text": _("已就绪"), "color": self.app.style.colors.success}}

        status_row_idx = 0
        checkbox_count = 0

        for key, display_name in self.FILE_TYPE_MAP.items():
            url_attr = f"{key}_url"
            # Core logic: Only display relevant UI if the corresponding URL attribute exists in the genome info object and is not empty.
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                var = tk.BooleanVar(value=True)
                self.file_type_vars[key] = var
                # Fix: ttkb.Checkbutton does not support direct font parameter
                ttkb.Checkbutton(checkbox_frame, text=display_name, variable=var,
                                 bootstyle="round-toggle",
                                 ).pack(side="left", padx=10, pady=5)
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
                        status_key = 'processed'  # For non-Excel files, downloaded means ready.

                status_info = status_map[status_key]
                ttk.Label(status_frame, text=f"{display_name}:", anchor="e", width=20, font=font_regular,
                          foreground=safe_text_color).grid(row=status_row_idx, column=0, sticky="w", padx=(0, 10))
                ttk.Label(status_frame, text=status_info["text"], foreground=status_info["color"], anchor="w",
                          font=font_regular).grid(row=status_row_idx, column=1, sticky="w")
                status_row_idx += 1

        if checkbox_count == 0:
            ttk.Label(checkbox_frame, text=_("当前基因组版本在配置文件中没有可供下载的URL链接。"),
                      foreground=safe_text_color).pack()

    def _on_genome_selection_change(self, selection):
        """Called when the user selects a new genome from the dropdown menu."""
        self._update_dynamic_widgets(selection)

    def _refresh_status(self):
        """Manually refreshes the file status for the currently selected genome version."""
        self.app._log_to_viewer(_("正在手动刷新文件状态..."), "INFO")
        self._update_dynamic_widgets(self.selected_genome_var.get())

    def update_assembly_dropdowns(self, assembly_ids: list):
        filtered_ids = [gid for gid in assembly_ids if "arabidopsis" not in gid.lower()]

        values = filtered_ids if filtered_ids else [_("无可用基因组")]

        old_dropdown = self.genome_option_menu

        # Add a check to ensure old_dropdown is a valid widget and is mapped
        if old_dropdown is None or not old_dropdown.winfo_exists():
            # This is the initial creation or after a full destruction.
            # The dropdown needs to be created from scratch.
            parent_frame = self.scrollable_frame  # Or direct parent if known
            new_initial_value = values[0] if values else ""
            self.genome_option_menu = ttkb.OptionMenu(
                parent_frame,
                self.selected_genome_var,
                new_initial_value,  # Set initial value safely
                *values,
                command=self._genome_option_menu_command,  # Use stored command
                bootstyle=self._genome_option_menu_bootstyle  # Use stored bootstyle
            )
            self.genome_option_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))
            self.selected_genome_var.set(new_initial_value)
            self._update_dynamic_widgets(self.selected_genome_var.get())
            self.app.logger.debug("DataDownloadTab: Initial assembly dropdown created.")
            return

        parent_frame = old_dropdown.master

        # Get layout information *before* checking winfo_ismapped or destroying,
        # but check winfo_manager only if it exists.
        layout_info = {}
        manager_type = None
        if hasattr(old_dropdown, 'winfo_manager'):
            manager_type = old_dropdown.winfo_manager()
            if manager_type == "grid":
                layout_info = old_dropdown.grid_info()
            elif manager_type == "pack":
                layout_info = old_dropdown.pack_info()

        # Get current variable
        variable = self.selected_genome_var

        # Destroy old OptionMenu
        old_dropdown.destroy()

        # Ensure a default value to initialize the new OptionMenu
        new_initial_value = variable.get()
        if new_initial_value not in values and values:
            new_initial_value = values[0]
        elif not values:
            new_initial_value = _("无可用基因组")

        # Recreate OptionMenu
        self.genome_option_menu = ttkb.OptionMenu(
            parent_frame,
            variable,
            new_initial_value,
            *values,
            command=self._genome_option_menu_command,  # Use stored command
            bootstyle=self._genome_option_menu_bootstyle  # Use stored bootstyle
        )
        variable.set(new_initial_value)

        # Apply layout based on saved information
        if layout_info and manager_type:
            if manager_type == "grid":
                self.genome_option_menu.grid(**{k: v for k, v in layout_info.items() if k != 'in'})
            elif manager_type == "pack":
                self.genome_option_menu.pack(**{k: v for k, v in layout_info.items() if k != 'in'})
        else:
            # Fallback: if no layout info, ensure it's still visible
            # For DataDownloadTab, it's grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))
            self.genome_option_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))

        self._update_dynamic_widgets(variable.get())

    def update_from_config(self):
        if self.app.current_config:
            self.force_download_var.set(self.app.current_config.downloader.force_download)
            self.use_proxy_for_download_var.set(self.app.current_config.downloader.use_proxy_for_download)
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'): self.start_button.configure(state=state)
        if hasattr(self, 'refresh_button'): self.refresh_button.configure(state=state)

    def start_download_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [_("配置未加载"), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("选择错误"), _("请选择一个有效的基因组进行下载。"))
            return

        # Accurately get the file types checked by the user and actually displayed on the current interface.
        file_types_to_download = [key for key, var in self.file_type_vars.items() if var.get()]
        if not file_types_to_download:
            self.app.ui_manager.show_error_message(_("选择错误"), _("请至少选择一种要下载的文件类型。"))
            return

        self.app.current_config.downloader.force_download = self.force_download_var.get()
        self.app.current_config.downloader.use_proxy_for_download = self.use_proxy_for_download_var.get()

        task_kwargs = {
            'config': self.app.current_config,
            'cli_overrides': {
                'versions': [selected_genome_id],
                'file_types': file_types_to_download,  # Pass the precise list to the backend
                'force': self.force_download_var.get(),
            }
        }
        self.app.event_handler._start_task(
            task_name=_("数据下载"),
            target_func=run_download_pipeline,
            kwargs=task_kwargs
        )

    def start_preprocess_task(self):
        """Starts the annotation file preprocessing task."""
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        self.app.event_handler._start_task(  # Delegate to EventHandler
            task_name=_("预处理注释文件"),
            target_func=run_preprocess_annotation_files,
            kwargs={'config': self.app.current_config}
        )