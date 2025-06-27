# ui/tabs/data_download_tab.py

import tkinter as tk

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
        super().__init__(parent, app)
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)

        # 这个字典现在用来存储动态创建的控件变量
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}
        # 这个字典定义了所有可能的文件类型及其显示名称，与 models.py 对应
        # UI将根据配置文件中URL是否存在，来决定是否显示这些选项
        self.FILE_TYPE_MAP = {
            "gff3": "Annotation (gff3)",
            "GO": "GO",
            "IPR": "IPR",
            "KEGG_pathways": "KEGG Pathways",
            "KEGG_orthologs": "KEGG Orthologs",
            "homology_ath": _("同源关系 (homology)"),
        }

        self._create_base_widgets()
        self.update_from_config()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        font_bold = (self.app.font_family, 15, "bold")
        safe_text_color = ("gray10", "#DCE4EE")

        ctk.CTkLabel(parent_frame, text=_("1. 选择要下载的基因组"), font=font_bold, text_color=safe_text_color).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        self.genome_option_menu = ctk.CTkOptionMenu(parent_frame, variable=self.selected_genome_var,
                                                    values=[_("配置未加载")], command=self._on_genome_selection_change)
        self.genome_option_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 15))

        # --- 动态内容区域的容器 ---
        # 这个框架将由 _update_dynamic_widgets 方法根据配置文件内容填充
        self.dynamic_content_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        self.dynamic_content_frame.grid(row=2, column=0, sticky="nsew", padx=10)
        self.dynamic_content_frame.grid_columnconfigure(0, weight=1)

        # --- 静态下载选项 ---
        ctk.CTkLabel(parent_frame, text=_("3. 下载选项"), font=font_bold, text_color=safe_text_color).grid(row=3,
                                                                                                           column=0,
                                                                                                           padx=10,
                                                                                                           pady=(15, 5),
                                                                                                           sticky="w")
        options_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        options_frame.grid(row=4, column=0, sticky="w", padx=5, pady=0)
        ctk.CTkCheckBox(options_frame, text=_("强制重新下载 (覆盖本地已存在文件)"), variable=self.force_download_var,
                        text_color=safe_text_color).pack(anchor="w", padx=10, pady=5)
        ctk.CTkCheckBox(options_frame, text=_("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                        variable=self.use_proxy_for_download_var, text_color=safe_text_color).pack(anchor="w", padx=10,
                                                                                                   pady=5)

        self.start_button = ctk.CTkButton(parent_frame, text=_("开始下载"), command=self.start_download_task, height=40,
                                          font=font_bold)
        self.start_button.grid(row=5, column=0, sticky="ew", padx=10, pady=(25, 10))

    def _update_dynamic_widgets(self, genome_id: str):
        """根据选择的基因组，动态创建文件类型复选框和文件状态标签。"""
        # 清理旧控件
        for widget in self.dynamic_content_frame.winfo_children():
            widget.destroy()
        self.file_type_vars.clear()

        if not genome_id or not self.app.genome_sources_data: return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info: return

        font_bold = (self.app.font_family, 15, "bold")
        font_regular = (self.app.font_family, 14)
        safe_text_color = ("gray10", "#DCE4EE")

        ctk.CTkLabel(self.dynamic_content_frame, text=_("2. 选择要下载的文件类型"), font=font_bold,
                     text_color=safe_text_color).grid(row=0, column=0, sticky="w", pady=(10, 5))
        checkbox_frame = ctk.CTkFrame(self.dynamic_content_frame, fg_color="transparent")
        checkbox_frame.grid(row=1, column=0, sticky="w", pady=(0, 10))

        status_header_frame = ctk.CTkFrame(self.dynamic_content_frame, fg_color="transparent")
        status_header_frame.grid(row=2, column=0, sticky="ew", pady=(10, 5))
        status_header_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(status_header_frame, text=_("文件状态"), font=font_bold, text_color=safe_text_color).grid(row=0,
                                                                                                               column=0,
                                                                                                               sticky="w")
        self.refresh_button = ctk.CTkButton(status_header_frame, text=_("刷新状态"), width=100,
                                            command=lambda: self._update_dynamic_widgets(
                                                self.selected_genome_var.get()))
        self.refresh_button.grid(row=0, column=1, sticky="e")

        status_frame = ctk.CTkFrame(self.dynamic_content_frame, fg_color="transparent")
        status_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=0)
        status_frame.grid_columnconfigure(1, weight=1)

        status_map = {'not_downloaded': {"text": _("未下载"), "color": ("#D32F2F", "#E57373")},
                      'downloaded': {"text": _("已下载 (待处理)"), "color": ("#F57C00", "#FFB74D")},
                      'processed': {"text": _("已就绪"), "color": ("#388E3C", "#A5D6A7")}}

        status_row_idx = 0
        checkbox_count = 0

        for key, display_name in self.FILE_TYPE_MAP.items():
            url_attr = f"{key}_url"
            # 核心逻辑：只有当基因组信息对象中存在对应的URL属性，且该URL不为空时，才显示相关UI
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                var = tk.BooleanVar(value=True)
                self.file_type_vars[key] = var
                ctk.CTkCheckBox(checkbox_frame, text=display_name, variable=var, font=font_regular,
                                text_color=safe_text_color).pack(side="left", padx=10, pady=5)
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
                        status_key = 'processed'  # 对于非Excel文件，下载即认为是就绪状态

                status_info = status_map[status_key]
                ctk.CTkLabel(status_frame, text=f"{display_name}:", anchor="e", width=180, font=font_regular,
                             text_color=safe_text_color).grid(row=status_row_idx, column=0, sticky="w", padx=(0, 10))
                ctk.CTkLabel(status_frame, text=status_info["text"], text_color=status_info["color"], anchor="w",
                             font=font_regular).grid(row=status_row_idx, column=1, sticky="w")
                status_row_idx += 1

        if checkbox_count == 0:
            ctk.CTkLabel(checkbox_frame, text=_("当前基因组版本在配置文件中没有可供下载的URL链接。"),
                         text_color=safe_text_color).pack()



    def _on_genome_selection_change(self, selection):
        """当用户在下拉菜单中选择一个新的基因组时调用。"""
        self._update_dynamic_widgets(selection)

    def _refresh_status(self):
        """手动刷新当前选中基因组版本的文件状态。"""
        self.app._log_to_viewer(_("正在手动刷新文件状态..."), "INFO")
        self._update_dynamic_widgets(self.selected_genome_var.get())

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
        self._update_dynamic_widgets(self.selected_genome_var.get())

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
        if hasattr(self, 'refresh_button'): self.refresh_button.configure(state=state)


    def start_download_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [_("配置未加载"), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("选择错误"), _("请选择一个有效的基因组进行下载。"))
            return

        # 精确地从 file_type_vars 中获取用户勾选的、且当前界面上实际显示的类型
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
                'file_types': file_types_to_download,  # 将精确的列表传递给后台
                'force': self.force_download_var.get(),
            }
        }
        self.app.event_handler._start_task(
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
