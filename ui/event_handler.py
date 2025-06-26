# 文件: cotton_tool/ui/event_handler.py
import json
import os
import threading
import traceback
import webbrowser
import time  # <--- 核心修改：使用正确的time模块
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, Optional, Any, List
import copy
import tkinter as tk
import customtkinter as ctk
import pandas as pd
from PIL import Image

# 导入应用内模块
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.pipelines import run_functional_annotation, run_enrichment_pipeline
from cotton_toolkit.tools.batch_ai_processor import process_single_csv_file
from cotton_toolkit.utils.localization import setup_localization
from .dialogs import MessageDialog, ProgressDialog

# 避免循环导入，同时为IDE提供类型提示
if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class EventHandler:
    """处理所有用户交互、后台消息和任务启动。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app

    def initialize_message_handlers(self) -> Dict[str, Callable]:
        """返回消息类型到其处理函数的映射。"""
        return {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "hide_progress_dialog": self.app.ui_manager._hide_progress_dialog,
            "update_sheets_dropdown": self._handle_update_sheets_dropdown,
            "csv_columns_fetched": self._handle_csv_columns_fetched,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_models_failed": self._handle_ai_models_failed,
            "ai_test_result": self._handle_ai_test_result,
            "auto_identify_success": self._handle_auto_identify_success,
            "auto_identify_fail": self._handle_auto_identify_fail,
            "auto_identify_error": self._handle_auto_identify_error,
        }

    # --- 后台消息处理方法 ---

    def _handle_csv_columns_fetched(self, data: tuple):
        """处理从后台线程获取到的CSV列名。"""
        columns, error_msg = data
        if 'ai_assistant' in self.app.tool_tab_instances:
            ai_tab = self.app.tool_tab_instances['ai_assistant']
            if hasattr(ai_tab, 'update_column_dropdown_ui'):
                ai_tab.update_column_dropdown_ui(columns, error_msg)

    def _handle_startup_complete(self, data: dict):
        """处理后台启动任务完成的消息，确保正确设置config_path。"""
        app = self.app
        app.ui_manager._hide_progress_dialog()
        app.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")

        config_path_from_load = data.get("config_path")

        if config_data:
            app.current_config = config_data
            # 使用传递过来的明确路径，而不是依赖对象内部的属性
            app.config_path = config_path_from_load
            app._log_to_viewer(_("默认配置文件加载成功。"))
        else:
            app._log_to_viewer(_("未找到或无法加载默认配置文件。"), "WARNING")

        # 后续的UI更新流程现在可以获取到正确的 app.config_path
        app.ui_manager.update_ui_from_config()
        app.ui_manager.update_language_ui()
        app.ui_manager.update_button_states()


    def _handle_startup_failed(self, data: str):
        self.app.ui_manager._hide_progress_dialog()
        self.app.ui_manager.show_error_message(_("启动错误"), str(data))
        self.app.ui_manager.update_button_states()

    def _handle_config_load_task_done(self, data: tuple):
        app = self.app
        app.ui_manager._hide_progress_dialog()
        success, result_data, filepath = data
        if success:
            app.current_config = result_data
            app.config_path = os.path.abspath(filepath)
            app.ui_manager.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
            app.genome_sources_data = get_genome_data_sources(app.current_config, logger_func=app._log_to_viewer)
            app.ui_manager.update_ui_from_config()
        else:
            app.ui_manager.show_error_message(_("加载失败"), str(result_data))

    def _handle_task_done(self, data: tuple):
        app = self.app
        success, task_display_name, result_data = data
        app.ui_manager._finalize_task_ui(task_display_name, success, result_data)

        # 特定任务的结果处理
        if "富集分析" in task_display_name:
            if success and result_data:
                app.ui_manager._show_plot_results(result_data)
            elif success:
                app.ui_manager.show_info_message(_("分析完成"),
                                                 _("富集分析完成，但没有发现任何显著富集的结果，因此未生成图表。"))

    def _handle_error(self, data: str):
        app = self.app
        app.ui_manager.show_error_message(_("任务执行出错"), data)
        app.ui_manager._finalize_task_ui(app.active_task_name or _("未知任务"), success=False)
        if hasattr(app, 'status_label') and app.status_label.winfo_exists():
            status_text = f"{_('任务终止于')}: {str(data)[:100]}..."
            app.status_label.configure(text=status_text)
        if app.error_dialog_lock.locked():
            app.error_dialog_lock.release()

    def _handle_status(self, data: str):
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.status_label.configure(text=str(data)[:150])

    def _handle_progress(self, data: tuple):
        percentage, text = data
        if self.app.progress_dialog and self.app.progress_dialog.winfo_exists():
            self.app.progress_dialog.update_progress(percentage, text)

    def _handle_ai_models_fetched(self, data: tuple):
        provider_key, models = data
        self.app._log_to_viewer(f"{provider_key} {_('模型列表获取成功。')} ")
        self.app.ui_manager.update_ai_model_dropdown(provider_key, models)
        self.app.ui_manager.show_info_message(_("刷新成功"),
                                              f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')}")

    def _handle_ai_models_failed(self, data: tuple):
        provider_key, error_msg = data
        self.app._log_to_viewer(f"{provider_key} {_('模型列表获取失败:')} {error_msg}", "ERROR")
        self.app.ui_manager.update_ai_model_dropdown(provider_key, [], error=True)
        self.app.ui_manager.show_warning_message(_("刷新失败"),
                                                 f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")

    def _handle_update_sheets_dropdown(self, data: tuple):
        sheet_names, excel_path, error = data
        if 'integrate' in self.app.tool_tab_instances:
            integrate_tab = self.app.tool_tab_instances['integrate']
            integrate_tab.update_sheet_dropdowns_ui(sheet_names, excel_path, error)

    def _handle_ai_test_result(self, data: tuple):
        if self.app.progress_dialog:
            self.app.progress_dialog.close()
        success, message = data
        if success:
            self.app.ui_manager.show_info_message(_("测试成功"), message)
        else:
            self.app.ui_manager.show_error_message(_("测试失败"), message)

    def _handle_auto_identify_success(self, data: tuple):
        target_var, assembly_id = data
        if self.app.genome_sources_data and assembly_id in self.app.genome_sources_data.keys():
            if isinstance(target_var, tk.StringVar):
                target_var.set(assembly_id)
                self.app._log_to_viewer(f"UI已自动更新基因为: {assembly_id}", "DEBUG")

    def _handle_auto_identify_fail(self, data=None):
        pass

    def _handle_auto_identify_error(self, data: str):
        self.app._log_to_viewer(f"自动识别基因组时发生错误: {data}", "ERROR")

    # --- 用户界面事件处理 ---

    def on_closing(self):
        app = self.app
        dialog = MessageDialog(
            parent=app, title=_("退出程序"), message=_("您确定要退出吗?"),
            icon_type="question", buttons=[_("确定"), _("取消")], app_font=app.app_font
        )
        dialog.wait_window()
        if dialog.result == _("确定"):
            app.destroy()

    def on_language_change(self, selected_display_name: str):
        app = self.app
        new_language_code = app.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")
        if app.current_config and app.config_path:
            app.current_config.i18n_language = new_language_code
            try:
                if save_config(app.current_config, app.config_path):
                    app._log_to_viewer(
                        _("语言设置 '{}' 已成功保存到 {}").format(new_language_code, os.path.basename(app.config_path)))
                else:
                    raise IOError(_("保存配置时返回False"))
            except Exception as e:
                app.ui_manager.show_error_message(_("保存失败"), _("无法将新的语言设置保存到配置文件中: {}").format(e))
        else:
            app.ui_manager.show_warning_message(_("无法保存"), _("请先加载一个配置文件才能更改并保存语言设置。"))

        app.ui_manager.update_language_ui(new_language_code)

    def change_appearance_mode_event(self, new_mode_display: str):
        app = self.app
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(new_mode_display, "System")
        ctk.set_appearance_mode(new_mode)
        app.ui_settings['appearance_mode'] = new_mode
        self._save_ui_settings()
        app.ui_manager._update_log_tag_colors()

    def toggle_log_viewer(self):
        app = self.app
        if app.log_viewer_visible:
            app.log_textbox.grid_remove()
            app.toggle_log_button.configure(text=_("显示日志"))
            app.log_viewer_visible = False
        else:
            app.log_textbox.grid()
            app.toggle_log_button.configure(text=_("隐藏日志"))
            app.log_viewer_visible = True

    def clear_log_viewer(self):
        app = self.app
        if hasattr(app, 'log_textbox'):
            app.log_textbox.configure(state="normal")
            app.log_textbox.delete("1.0", tk.END)
            app.log_textbox.configure(state="disabled")
            app._log_to_viewer(_("日志已清除。"))

    # --- 任务启动与管理 ---

    def start_app_async_startup(self):
        """启动应用的异步加载流程。"""
        app = self.app
        app.ui_manager._show_progress_dialog(
            title=_("图形界面启动中..."),
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None
        )
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """【最终版】后台加载线程，不再关心UI显示时间。"""
        app = self.app
        loaded_config: Optional[MainConfig] = None
        genome_sources = None
        config_path_to_send = None

        try:
            default_config_path = "config.yml"
            if os.path.exists(default_config_path):
                app.message_queue.put(("progress", (10, _("加载配置文件..."))))
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)
            if loaded_config:
                app.message_queue.put(("progress", (30, _("加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config, logger_func=app._log_to_viewer)

            startup_data = {
                "config": loaded_config,
                "genome_sources": genome_sources,
                "config_path": config_path_to_send
            }
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            error_message = f"{_('应用启动失败')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            app.message_queue.put(("startup_failed", error_message))
        finally:
            # 任务完成，直接发送隐藏消息，由UIManager决定何时真正隐藏
            app.message_queue.put(("hide_progress_dialog", None))


    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any]):
        """启动一个后台任务的通用方法。"""
        app = self.app
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                f"{_('另一个任务')} '{app.active_task_name}' {_('正在运行，请稍候。')}")
            return

        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        app._log_to_viewer(f"{_(task_name)} {_('任务开始...')}")
        app.cancel_current_task_event.clear()

        app.ui_manager._show_progress_dialog(title=_(task_name), message=_("正在处理..."),
                                             on_cancel=app.cancel_current_task_event.set)

        kwargs['cancel_event'] = app.cancel_current_task_event
        kwargs['status_callback'] = self.gui_status_callback
        kwargs['progress_callback'] = self.gui_progress_callback

        def task_wrapper():
            try:
                result_data = target_func(**kwargs)
                if app.cancel_current_task_event.is_set():
                    app.message_queue.put(("task_done", (False, task_name, "CANCELLED")))
                else:
                    app.message_queue.put(("task_done", (True, task_name, result_data)))
            except Exception as e:
                detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                app.message_queue.put(("error", detailed_error))

        threading.Thread(target=task_wrapper, daemon=True).start()

    # --- 其他辅助方法 ---

    def _bind_mouse_wheel_to_scrollable(self, widget):
        if widget and hasattr(widget, 'focus_set'):
            widget.bind("<Enter>", lambda event, w=widget: w.focus_set())

    def _save_ui_settings(self):
        app = self.app
        settings_path = os.path.join(os.getcwd(), "ui_settings.json")
        try:
            data_to_save = {"appearance_mode": app.ui_settings.get("appearance_mode", "System")}
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            app._log_to_viewer(_("外观模式设置已保存。"), "DEBUG")
        except IOError as e:
            app._log_to_viewer(f"{_('错误: 无法保存外观设置:')} {e}", "ERROR")

    def _display_log_message_in_ui(self, message, level):
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            app.log_textbox.configure(state="normal")
            max_lines = 500
            current_lines = int(app.log_textbox.index('end-1c linestart').split('.')[0])
            if current_lines > max_lines:
                app.log_textbox.delete("1.0", f"{current_lines - max_lines + 1}.0")

            # <--- 核心修改：使用正确的 time 模块来生成时间戳 ---
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            color_tag = "normal_log"
            if level == "ERROR":
                color_tag = "error_log"
            elif level == "WARNING":
                color_tag = "warning_log"
            app.log_textbox.insert(tk.END, f"[{timestamp}] {message}\n", color_tag)
            app.log_textbox.see(tk.END)
            app.log_textbox.configure(state="disabled")
            if not hasattr(app.log_textbox, '_tags_configured'):
                app.ui_manager._update_log_tag_colors()
                app.log_textbox._tags_configured = True

    def gui_status_callback(self, message: str, level: str = "INFO"):
        """线程安全的回调函数，用于更新状态栏和日志。"""
        app = self.app
        level_upper = level.upper()
        if level_upper == "ERROR":
            if app.error_dialog_lock.acquire(blocking=False):
                app.message_queue.put(("error", message))
        else:
            app.message_queue.put(("status", message))
        app._log_to_viewer(str(message), level=level_upper)

    def gui_progress_callback(self, percentage, message):
        self.app.message_queue.put(("progress", (percentage, message)))