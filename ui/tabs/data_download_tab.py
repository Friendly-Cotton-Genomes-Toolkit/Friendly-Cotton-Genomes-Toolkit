# 文件路径: ui/tabs/data_download_tab.py

import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Dict, Callable, Any
import threading
import ttkbootstrap as ttkb

from cotton_toolkit.config.loader import get_local_downloaded_file_path
from cotton_toolkit.pipelines import run_download_pipeline, run_preprocess_annotation_files, run_build_blast_db_pipeline
from cotton_toolkit.pipelines.preprocessing import check_preprocessing_status
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):  # builtins._ 未设置或导入builtins失败
    # 如果在测试或独立运行此模块时，_ 可能未设置
    def _(text: str) -> str:
        return text


class DataDownloadTab(BaseTab):
    # 【已修正】构造函数现在遵循正确的初始化顺序
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # 步骤 1: 提前定义所有 _create_widgets() 需要用到的实例变量
        self.task_status_widgets: Dict[str, Dict[str, tk.Widget]] = {}
        self.selected_genome_var = tk.StringVar()
        self.use_proxy_for_download_var = tk.BooleanVar(value=False)
        self.force_download_var = tk.BooleanVar(value=False)
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}

        self.FILE_TYPE_DISPLAY_NAMES_KEYS = {
            "predicted_cds": _("Predicted CDS"),
            "predicted_protein": _("Predicted Protein"),
            "gff3": _("注释 (gff3)"),
            "GO": "GO",
            "IPR": "IPR",
            "KEGG_pathways": _("KEGG 通路"),
            "KEGG_orthologs": _("KEGG 直系同源"),
            "homology_ath": _("同源关系 (拟南芥)"),
        }
        self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED: Dict[str, str] = {}
        self.dynamic_widgets = {}

        # 步骤 2: 调用父类的构造函数。
        # 父类会调用 _create_widgets()，此时所有需要的变量都已存在。
        super().__init__(parent, app, translator)

        # 步骤 3: 在父类完全初始化后，再配置由父类创建的组件（例如 action_button）
        if self.action_button:
            self.download_button = self.action_button
            self.download_button.configure(text=self._("开始下载"), command=self.start_download_task)
            action_frame = self.download_button.master

            self.build_blast_db_button = ttkb.Button(action_frame, text=self._("预处理BLAST数据库"),
                                                     command=self.start_build_blast_db_task, bootstyle="primary")
            self.build_blast_db_button.grid(row=0, column=0, sticky="se", padx=(0, 10), pady=10)

            self.preprocess_button = ttkb.Button(action_frame, text=self._("预处理注释文件"),
                                                 command=self.start_preprocess_task, bootstyle="info")
            self.preprocess_button.grid(row=0, column=1, sticky="se", padx=(0, 10), pady=10)

            self.download_button.grid(row=0, column=2, sticky="se", padx=(0, 15), pady=10)

        # 步骤 4: 最后执行依赖于已创建组件的更新
        self.update_from_config()

    def update_task_status(self, task_key: str, message: str):
        """
        线程安全地更新UI上特定任务的状态。
        这个方法会被后台线程调用。
        """
        # 使用 self.app.after 将UI更新操作调度到主线程执行
        self.app.after(0, self._update_ui_task_status, task_key, message)

    def _update_ui_task_status(self, task_key: str, message: str):
        """这个方法总是在主线程中执行。"""
        # 尝试获取与 task_key 关联的UI组件
        widgets = self.task_status_widgets.get(task_key)

        # 如果组件还不存在，就创建它们
        if not widgets:
            # 使用翻译后的友好名称
            display_name = self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.get(task_key, task_key)

            # 在进度详情卡片中创建新的一行
            row_index = len(self.task_status_widgets)

            name_label = ttkb.Label(self.progress_details_card, text=f"{display_name}:", font=self.app.app_font_bold)
            name_label.grid(row=row_index, column=0, sticky="w", padx=(10, 5), pady=2)

            status_label = ttkb.Label(self.progress_details_card, text=message, width=20)  # 给一个宽度防止跳动
            status_label.grid(row=row_index, column=1, sticky="ew", padx=5, pady=2)

            self.task_status_widgets[task_key] = {'name': name_label, 'status': status_label}
        else:
            # 如果组件已存在，只更新状态标签的文本
            status_label = widgets.get('status')
            if status_label and status_label.winfo_exists():
                status_label.configure(text=message)

    def _clear_task_status_display(self):
        """在开始新任务前清空旧的状态显示。"""
        for widgets_dict in self.task_status_widgets.values():
            for widget in widgets_dict.values():
                widget.destroy()
        self.task_status_widgets.clear()

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

        # --- 任务实时进度框架 ---
        self.progress_details_card = ttkb.LabelFrame(parent_frame, text=self._("任务进度详情"), bootstyle="secondary")
        self.progress_details_card.grid(row=4, column=0, sticky="nsew", padx=10, pady=10)
        self.progress_details_card.grid_columnconfigure(1, weight=1)
        parent_frame.grid_rowconfigure(4, weight=1)

        self.force_download_check = ttkb.Checkbutton(self.options_card,
                                                     text=self._("强制重新下载 (覆盖本地已存在文件)"),
                                                     variable=self.force_download_var, bootstyle="round-toggle")
        self.force_download_check.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.use_proxy_check = ttkb.Checkbutton(self.options_card,
                                                text=self._("对数据下载使用网络代理 (请在配置编辑器中设置)"),
                                                variable=self.use_proxy_for_download_var, bootstyle="round-toggle")
        self.use_proxy_check.grid(row=1, column=0, sticky="w", padx=10, pady=5)



        self._update_dynamic_widgets(self.selected_genome_var.get())

        if hasattr(self, 'download_button'):
            self.download_button.configure(text=self._("开始下载"))
        if hasattr(self, 'preprocess_button'):
            self.preprocess_button.configure(text=self._("预处理注释文件"))

    def _update_dynamic_widgets(self, genome_id: str):
        for widget in self.dynamic_content_frame.winfo_children():
            widget.destroy()
        self.file_type_vars.clear()
        self.dynamic_widgets.clear()

        if not genome_id or not self.app.genome_sources_data or not self.app.current_config:
            return
        genome_info = self.app.genome_sources_data.get(genome_id)
        if not genome_info:
            return

        all_statuses = check_preprocessing_status(self.app.current_config, genome_info)

        is_dark = self.app.style.theme.type == 'dark'
        status_colors = {
            'not_downloaded': "#e57373" if is_dark else "#d9534f",  # 未下载 (红色)
            'downloaded': "#ffb74d" if is_dark else "#f0ad4e",  # 待处理 (橙色)
            'organized_only': "#64b5f6" if is_dark else "#428bca",  # 仅整理 (蓝色)
            'db_only': "#81c784" if is_dark else "#428bca",  # 仅建库 (蓝色)
            'processed': self.app.style.colors.success,  # 已就绪 (深绿)
        }
        status_texts = {
            'not_downloaded': self._("未下载"),
            'downloaded': self._("已下载 (待处理)"),
            'organized_only': self._("仅整理 (待建库)"),
            'db_only': self._("仅建库 (待整理)"),
            'processed': self._("已就绪")
        }

        # --- 文件类型选择区 ---
        checkbox_header = ttkb.Label(self.dynamic_content_frame, text=self._("选择文件类型"),
                                     font=self.app.app_font_bold)
        checkbox_header.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5), columnspan=3)
        self.dynamic_widgets['checkbox_header'] = checkbox_header

        sep1 = ttkb.Separator(self.dynamic_content_frame)
        sep1.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10), columnspan=3)

        checkbox_frame = ttkb.Frame(self.dynamic_content_frame)
        checkbox_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=0, columnspan=3)
        self.dynamic_widgets['checkbox_frame'] = checkbox_frame

        # --- 文件状态区 ---
        status_header = ttkb.Label(self.dynamic_content_frame, text=self._("文件状态"), font=self.app.app_font_bold)
        status_header.grid(row=3, column=0, sticky="w", padx=10, pady=(20, 5), columnspan=2)
        self.dynamic_widgets['status_header'] = status_header

        refresh_button = ttkb.Button(self.dynamic_content_frame, text=self._("刷新状态"), width=12,
                                     command=lambda: self._update_dynamic_widgets(self.selected_genome_var.get()),
                                     bootstyle="info-outline")
        refresh_button.grid(row=3, column=2, sticky="e", padx=10, pady=(15, 0))
        self.dynamic_widgets['refresh_button'] = refresh_button

        sep2 = ttkb.Separator(self.dynamic_content_frame)
        sep2.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10), columnspan=3)

        status_frame = ttkb.Frame(self.dynamic_content_frame)
        status_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=0, columnspan=3)
        status_frame.grid_columnconfigure(1, weight=1)
        self.dynamic_widgets['status_frame'] = status_frame

        all_file_keys = self.FILE_TYPE_DISPLAY_NAMES_KEYS.keys()

        checkbox_row_idx, checkbox_col_idx, status_row_idx, checkbox_count = 0, 0, 0, 0

        for key in all_file_keys:
            display_name = self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.get(key, key)
            url_attr = f"{key}_url"

            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                # Checkbox 渲染逻辑不变
                var = tk.BooleanVar(value=True)
                self.file_type_vars[key] = var
                ttkb.Checkbutton(checkbox_frame, text=display_name, variable=var, bootstyle="round-toggle").grid(
                    row=checkbox_row_idx, column=checkbox_col_idx, sticky='w', padx=5, pady=5)
                checkbox_col_idx += 1
                if checkbox_col_idx >= 3:  # 每行最多3个
                    checkbox_col_idx = 0
                    checkbox_row_idx += 1
                checkbox_count += 1

                # --- 核心修改 2: 状态判断逻辑被极大简化 ---
                # 直接从后端返回的字典中获取状态，提供一个默认值以防万一
                status_key = all_statuses.get(key, 'not_downloaded')

                # 状态标签渲染 (这部分代码无需修改)
                file_type_label = ttkb.Label(status_frame, text=f"{display_name}:", font=self.app.app_font_bold)
                file_type_label.grid(row=status_row_idx, column=0, sticky="w", padx=(0, 10), pady=2)

                status_label = ttk.Label(status_frame, text=status_texts.get(status_key, ""),
                                         foreground=status_colors.get(status_key))
                status_label.grid(row=status_row_idx, column=1, sticky="w", padx=0, pady=2)

                status_row_idx += 1

        if checkbox_count == 0:
            no_url_label = ttk.Label(checkbox_frame, text=self._("当前基因组版本在配置文件中没有可供下载的URL链接。"))
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
        if hasattr(self, 'build_blast_db_button'):
            self.build_blast_db_button.configure(state="disabled" if is_running or not has_config else "normal")
        if hasattr(self, 'preprocess_button'):
            self.preprocess_button.configure(state="disabled" if is_running or not has_config else "normal")
        if 'refresh_button' in self.dynamic_widgets and self.dynamic_widgets['refresh_button'].winfo_exists():
            self.dynamic_widgets['refresh_button'].configure(
                state="disabled" if is_running or not has_config else "normal")


    def start_build_blast_db_task(self):
        """
        启动构建BLAST数据库的任务。
        此版本使用新的状态检查系统来确定是否需要运行。
        """
        # 1. 基本检查：确保配置已加载且基因组已选择
        if not self.app.current_config: self.app.ui_manager.show_error_message(self._("错误"),
                                                                               self._("请先加载配置文件。")); return
        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [self._("配置未加载"), self._("无可用基因组")]:
            self.app.ui_manager.show_error_message(self._("选择错误"), self._("请选择一个有效的基因组。"));
            return
        genome_info = self.app.genome_sources_data.get(selected_genome_id)
        if not genome_info:
            msg = self._("找不到基因组 '{}' 的信息。").format(selected_genome_id)
            self.app.ui_manager.show_error_message(self._("错误"), msg);
            return

        all_statuses = check_preprocessing_status(self.app.current_config, genome_info)
        blast_keys_to_check = ['predicted_cds', 'predicted_protein']
        needs_processing = any(
            all_statuses.get(key) in ['downloaded', 'organized_only'] for key in blast_keys_to_check if
            hasattr(genome_info, f"{key}_url") and getattr(genome_info, f"{key}_url"))
        applicable_files_exist = any(
            hasattr(genome_info, f"{key}_url") and getattr(genome_info, f"{key}_url") for key in blast_keys_to_check)

        if not applicable_files_exist:
            msg = self._("无法开始预处理，因为当前基因组版本未配置预测CDS或蛋白质文件的URL。")
            self.app.ui_manager.show_warning_message(self._("缺少配置"), msg)
            return
        if not needs_processing:
            self.app.ui_manager.show_info_message(self._("已就绪"),
                                                  self._("所有适用的BLAST数据库均已预处理完成，无需再次运行。"))
            return

        # --- 创建通信工具和对话框 ---
        self._clear_task_status_display()
        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(self._("操作取消"), self._("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=self._("预处理BLAST数据库"),
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        # --- 准备任务参数 ---
        task_kwargs = {
            'config': self.app.current_config,
            'selected_assembly_id': selected_genome_id,
            'status_callback': self.update_task_status,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        self.app.event_handler.start_task(
            task_name=self._("预处理BLAST数据库"),
            target_func=run_build_blast_db_pipeline,
            on_success=lambda result: self._update_dynamic_widgets(self.selected_genome_var.get()),
            kwargs=task_kwargs
        )

    def start_download_task(self):
        try:
            # --- 参数验证  ---
            if not self.app.current_config:
                self.app.ui_manager.show_error_message(self._("错误"), self._("请先加载配置文件。"))
                return

            selected_genome_id = self.selected_genome_var.get()
            if not selected_genome_id or selected_genome_id in [self._("配置未加载"), self._("无可用基因组")]:
                self.app.ui_manager.show_error_message(self._("选择错误"), self._("请选择一个有效的基因组进行下载。"))
                return

            file_types_to_download = [key for key, var in self.file_type_vars.items() if var.get()]
            if not file_types_to_download:
                self.app.ui_manager.show_error_message(self._("选择错误"), self._("请至少选择一种要下载的文件类型。"))
                return

            # --- 创建通信工具和对话框  ---
            cancel_event = threading.Event()

            def on_cancel_action():
                self.app.ui_manager.show_info_message(self._("操作取消"), self._("已发送取消请求，下载任务将尽快停止。"))
                cancel_event.set()

            progress_dialog = self.app.ui_manager.show_progress_dialog(
                title=self._("数据下载中"),
                on_cancel=on_cancel_action
            )

            def ui_progress_updater(percentage, message):
                if progress_dialog and progress_dialog.winfo_exists():
                    self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

            # --- 准备任务参数 ---
            cli_overrides = {
                'versions': [selected_genome_id],
                'file_types': file_types_to_download,
                'force': self.force_download_var.get(),
                'use_proxy_for_download': self.use_proxy_for_download_var.get()
            }

            task_kwargs = {
                'config': self.app.current_config,
                'cli_overrides': cli_overrides,
                'cancel_event': cancel_event,
                'progress_callback': ui_progress_updater
            }

            self.app.event_handler.start_task(
                task_name=self._("数据下载"),
                target_func=run_download_pipeline,
                on_success=lambda result: self._update_dynamic_widgets(self.selected_genome_var.get()),
                kwargs=task_kwargs
            )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            error_message = f"{self._('启动下载任务时发生未知错误:')}\n\n{type(e).__name__}: {e}\n\n{error_details}"
            self.app.ui_manager.show_error_message(self._("任务启动失败"), error_message)
            raise RuntimeError(error_message)

    def start_preprocess_task(self):
        # --- 参数验证 ---
        if not self.app.current_config: self.app.ui_manager.show_error_message(self._("错误"),
                                                                               self._("请先加载配置文件。")); return
        selected_genome_id = self.selected_genome_var.get()
        if not selected_genome_id or selected_genome_id in [self._("配置未加载"), self._("无可用基因组")]:
            self.app.ui_manager.show_error_message(self._("选择错误"), self._("请选择一个有效的基因组进行预处理。"));
            return
        genome_info = self.app.genome_sources_data.get(selected_genome_id)
        if not genome_info:
            msg = self._("找不到基因组 '{}' 的信息。").format(selected_genome_id)
            self.app.ui_manager.show_error_message(self._("错误"), msg);
            return

        all_statuses = check_preprocessing_status(self.app.current_config, genome_info)
        annotation_keys_to_check = ['predicted_cds', 'gff3', 'GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs',
                                    'homology_ath']
        missing_files_display_names = []
        for key in annotation_keys_to_check:
            url_attr = f"{key}_url"
            if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
                if all_statuses.get(key) == 'not_downloaded':
                    missing_files_display_names.append(self.FILE_TYPE_DISPLAY_NAMES_TRANSLATED.get(key, key))
        if missing_files_display_names:
            file_list_formatted = "\n- ".join(missing_files_display_names)
            msg = self._("无法开始预处理，以下必需的注释文件尚未下载：\n\n- {file_list}\n\n请先下载它们。").format(
                file_list=file_list_formatted)
            self.app.ui_manager.show_warning_message(self._("缺少文件"), msg)
            return

        all_processed = all(all_statuses.get(key) == 'processed' for key in annotation_keys_to_check if
                            hasattr(genome_info, f"{key}_url") and getattr(genome_info, f"{key}_url"))
        if all_processed:
            self.app.ui_manager.show_info_message(self._("已就绪"), self._("注释文件已全部预处理完成，无需再次运行。"))
            return

        # --- 创建通信工具和对话框 ---
        self._clear_task_status_display()
        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(self._("操作取消"), self._("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=self._("预处理注释文件"),
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        # --- 准备任务参数 (加入通信工具) ---
        task_kwargs = {
            'config': self.app.current_config,
            'selected_assembly_id': selected_genome_id,
            'status_callback': self.update_task_status,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        self.app.event_handler.start_task(
            task_name=self._("预处理文件"),
            target_func=run_preprocess_annotation_files,
            on_success=lambda result: self._update_dynamic_widgets(self.selected_genome_var.get()),
            kwargs=task_kwargs
        )
