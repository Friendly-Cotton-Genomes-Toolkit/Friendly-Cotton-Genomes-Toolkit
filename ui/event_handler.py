# event_handler.py

import logging
import os
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, Optional, Any
import requests
import ttkbootstrap as ttkb

from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.utils.localization import setup_localization
from .dialogs import MessageDialog, ConfirmationDialog
from cotton_toolkit.utils.gene_utils import identify_genome_from_gene_ids

if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger(__name__)


class EventHandler:
    """处理所有用户交互、后台消息和任务启动。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.ui_manager = app.ui_manager
        self.message_handlers = self._initialize_message_handlers()
        self.last_ambiguity_text: str = ""

    def _initialize_message_handlers(self) -> Dict[str, Callable]:
        """
        【修改】增加对新消息类型的处理。
        """
        handlers = {
            # ... 您已有的所有消息处理器 ...
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_test_result": self._handle_ai_test_result,
            "proxy_test_done": self._handle_proxy_test_done,
            "csv_columns_fetched": self._handle_csv_columns_fetched,
            "show_progress_dialog": self.ui_manager._show_progress_dialog,
            "hide_progress_dialog": self.ui_manager._hide_progress_dialog,

            # 【修改】将原有的处理器重命名，并新增一个处理器
            "auto_identify_success": self._handle_auto_identify_result,
        }
        return handlers

    # --- 语言切换处理 ---
    def on_language_change(self, language_name: str):
        """当用户从下拉菜单中选择一个新语言时触发。"""
        app = self.app
        _ = app._  # 使用当前实例的翻译函数

        selected_lang_code = app.LANG_NAME_TO_CODE.get(language_name)
        if not selected_lang_code:
            app.logger.warning(_("Invalid language name selected: {}").format(language_name))
            return

        app.logger.info(_("Language change requested to: {} ({})").format(language_name, selected_lang_code))

        # 步骤 1: 更新并保存 UI 配置文件 (ui_settings.json)，这会影响下次启动时的默认语言
        app.ui_settings['language'] = selected_lang_code
        self.ui_manager.save_ui_settings()

        # 步骤 2: 如果当前加载了主配置文件(config.yml)，则更新并保存它
        app._ = setup_localization(language_code=selected_lang_code)
        _ = app._
        if app.current_config and app.config_path:
            app.current_config.i18n_language = selected_lang_code
            if save_config(app.current_config, app.config_path):
                app.logger.info(
                    _("Main config file '{}' updated with language '{}'.").format(os.path.basename(app.config_path),
                                                                                  selected_lang_code))
                # 更新状态栏提示
                app.message_queue.put(('show_info', {'title': _("配置已保存"),
                                                     'message': _("语言设置已同步到 {}。").format(
                                                         os.path.basename(app.config_path))}))
            else:
                app.logger.error(f"Failed to save language setting to '{app.config_path}'.")
                app.message_queue.put(
                    ('show_error', {'title': _("保存失败"), 'message': _("无法将语言设置写入配置文件。")}))

        # 步骤 3: 实时更新当前界面的所有文本 反正都要重启
        # self.ui_manager.update_language_ui(selected_lang_code)

        # 步骤 4: 弹出重启提示对话框
        # 使用更新后的翻译函数来创建对话框
        dialog = ConfirmationDialog(
            parent=app,
            title=_("需要重启"),
            message=_("语言设置已更改。为了使所有更改完全生效，建议您重启应用程序。"),
            button1_text=_("立即重启"),
            button2_text=_("稍后重启")
        )

        # 步骤 5: 根据用户选择决定是否重启
        if dialog.result is True:
            app.restart_app()

    def on_closing(self):
        """
        【已修改】处理主窗口关闭事件，增加退出确认。
        """
        _ = self.app._
        if self.app.active_task_name:
            # 如果有任务在运行，弹出特定警告
            dialog = ConfirmationDialog(
                parent=self.app,
                title=_("确认退出"),
                message=_("任务'{}'正在运行中，确定要强制退出吗？").format(self.app.active_task_name),
                button1_text=_("强制退出"),
                button2_text=_("取消")
            )
            if dialog.result is True:
                self.app.cancel_current_task_event.set()
                self.app.destroy()
        else:
            # 如果程序空闲，弹出通用退出确认
            dialog = ConfirmationDialog(
                parent=self.app,
                title=_("确认退出"),
                message=_("您确定要退出吗？"),
                button1_text=_("退出"),
                button2_text=_("取消")
            )
            if dialog.result is True:
                self.app.destroy()

    def start_app_async_startup(self):
        _ = self.app._
        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("图形界面启动中..."),
            "message": _("正在初始化应用程序和加载配置，请稍候..."),
            "on_cancel": None
        }))
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        app = self.app
        _ = self.app._
        try:
            loaded_config, genome_sources, config_path_to_send = None, None, None
            app.message_queue.put(("progress", (10, _("正在加载配置文件..."))))
            if os.path.exists(default_config_path := "config.yml"):
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)
            if loaded_config:
                app.message_queue.put(("progress", (30, _("正在加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config, logger_func=logger.info)
            app.message_queue.put(("progress", (80, _("启动完成准备..."))))
            startup_data = {"config": loaded_config, "genome_sources": genome_sources,
                            "config_path": config_path_to_send}
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            app.message_queue.put(("startup_failed", f"{_('应用启动失败')}: {e}\n{traceback.format_exc()}"))
        finally:
            app.message_queue.put(("progress", (100, _("初始化完成。"))))
            app.message_queue.put(("hide_progress_dialog", None))

    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any],
                    on_success: Optional[Callable] = None, task_key: Optional[str] = None):
        """
        启动一个后台任务。
        【已扩展】: 增加一个可选的、语言无关的 task_key。
        """
        app = self.app
        _ = self.app._
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                _("任务 '{}' 正在运行中，请等待其完成后再开始新任务。").format(
                                                    app.active_task_name))
            return

        # 如果没有提供 task_key，则默认使用 task_name
        if task_key is None:
            task_key = task_name

        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        app.cancel_current_task_event.clear()
        self.app.message_queue.put(("show_progress_dialog", {"title": task_name, "message": _("正在处理..."),
                                                             "on_cancel": app.cancel_current_task_event.set}))

        kwargs.update({'cancel_event': app.cancel_current_task_event, 'status_callback': self.gui_status_callback,
                       'progress_callback': self.gui_progress_callback})

        # 将 task_key 传递给线程包装器
        threading.Thread(target=self._task_wrapper, args=(target_func, kwargs, task_name, task_key, on_success),
                         daemon=True).start()

    def _task_wrapper(self, target_func, kwargs, task_name, task_key, on_success: Optional[Callable] = None):
        """
        在后台线程中执行任务的包装器。
        【已扩展】: 传递 task_key。
        """
        _ = self.app._
        result = None
        e = None
        try:
            result = target_func(**kwargs)
            if on_success and not self.app.cancel_current_task_event.is_set():
                self.app.after(0, on_success, result)
        except Exception as exc:
            e = exc
        finally:
            final_data = None
            if self.app.cancel_current_task_event.is_set():
                final_data = (False, task_name, "CANCELLED", task_key)
            elif e:
                final_data = (False, task_name, e, task_key)
            else:
                final_data = (True, task_name, result, task_key)

            if final_data:
                self.app.message_queue.put(("task_done", final_data))


    def _handle_startup_complete(self, data: dict):
        app = self.app
        _ = self.app._
        self.app._log_to_viewer(_("应用程序启动完成。"), "INFO")
        if self.app.ui_manager and hasattr(self.app, 'config_path_display_var'):
            self.app.ui_manager.update_ui_from_config()
        else:
            self.app.logger.warning(_("无法在启动时更新UI配置：UIManager或config_path_display_var未就绪。"))
        app.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")
        config_path_from_load = data.get("config_path")
        if config_data:
            app.current_config = config_data
            app.config_path = config_path_from_load
            logger.info(_("默认配置文件加载成功。"))
        else:
            logger.warning(_("未找到或无法加载默认配置文件。"))
        app.ui_manager.update_ui_from_config()
        app.ui_manager.update_button_states()

    def _handle_startup_failed(self, data: str):
        _ = self.app._
        self.app.ui_manager._hide_progress_dialog()
        self.app.ui_manager.show_error_message(_("启动错误"), str(data))
        self.app.ui_manager.update_button_states()

    def _handle_config_load_task_done(self, data: tuple):
        app = self.app
        _ = self.app._
        success, loaded_config, original_filepath = data
        if not success:
            app.ui_manager.show_error_message(_("加载失败"), str(loaded_config))
            return
        root_config_path = os.path.abspath("config.yml")
        try:
            save_config(loaded_config, root_config_path)
            app.current_config = loaded_config
            app.config_path = root_config_path
            app.ui_manager.show_info_message(_("加载并覆盖成功"), _("已将 '{}' 的内容加载并保存至 '{}'。").format(
                os.path.basename(original_filepath), os.path.basename(root_config_path)))
            app.genome_sources_data = get_genome_data_sources(app.current_config, logger_func=logger.info)
            app.ui_manager.update_ui_from_config()
        except Exception as e:
            error_msg = _("无法将加载的配置保存到根目录 'config.yml'。\n错误: {}").format(e)
            app.ui_manager.show_error_message(_("保存失败"), error_msg)
            logger.error(f"{error_msg}\n{traceback.format_exc()}")

    def _handle_task_done(self, data: tuple):
        """
        使用语言无关的 task_key 来判断是否需要刷新。
        """
        app = self.app
        _ = self.app._
        success, task_display_name, result_data, task_key = data

        app.ui_manager._finalize_task_ui(task_display_name, success, result_data)

        # --- 使用 task_key 进行判断 ---
        refresh_trigger_keys = ["download", "preprocess_anno", "preprocess_blast"]
        if success and task_key in refresh_trigger_keys:
            if download_tab := app.tool_tab_instances.get('download'):
                if hasattr(download_tab, '_update_dynamic_widgets'):
                    selected_genome = download_tab.selected_genome_var.get()
                    app.after(50, lambda: download_tab._update_dynamic_widgets(selected_genome))
                    app.logger.info(_("数据下载选项卡状态已在任务 '{}' 完成后自动刷新。").format(task_display_name))

        elif "富集分析" in task_display_name and success and result_data:
            if hasattr(self.app.ui_manager, '_show_plot_results'):
                self.app.ui_manager._show_plot_results(result_data)

    def _handle_error(self, data: str):
        _ = self.app._
        self.app.ui_manager.show_error_message(_("任务执行出错"), data)
        self.app.ui_manager._finalize_task_ui(self.app.active_task_name or _("未知任务"), success=False)

    def _handle_status(self, message: str):
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.latest_log_message_var.set(message)

    def _handle_progress(self, data: tuple):
        if self.app.ui_manager.progress_dialog and self.app.ui_manager.progress_dialog.winfo_exists():
            self.app.ui_manager.progress_dialog.update_progress(*data)

    def _handle_ai_models_fetched(self, data: tuple):
        _ = self.app._
        provider_key, models_or_error = data
        if isinstance(models_or_error, list) and models_or_error:
            # 更新编辑器UI中的下拉选项 (这部分逻辑不变)
            self.app.ui_manager.update_ai_model_dropdown(provider_key, models_or_error)

            # --- 【核心修正】---
            # 将获取到的完整模型列表（用逗号连接成字符串）
            # 更新到内存中配置对象的 available_models 字段
            if self.app.current_config:
                provider_cfg = self.app.current_config.ai_services.providers.get(provider_key)
                if provider_cfg:
                    provider_cfg.available_models = ",".join(models_or_error)
                    self.app.logger.info(
                        f"In-memory config for '{provider_key}' updated with a list of {len(models_or_error)} available models.")
            # --- 修正结束 ---

            self.app.ui_manager.show_info_message(_("刷新成功"),
                                                  _("已成功获取并更新 {} 的模型列表。").format(provider_key))
        else:
            self.app.ui_manager.update_ai_model_dropdown(provider_key, [])
            self.app.ui_manager.show_error_message(_("刷新失败"), str(models_or_error))

    def _handle_ai_test_result(self, data: tuple):
        _ = self.app._
        success, message = data
        self.app.ui_manager.show_info_message(_("测试成功"),
                                              message) if success else self.app.ui_manager.show_error_message(
            _("测试失败"), message)

    def _handle_auto_identify_result(self, data: tuple):

        _ = self.app._
        target_var, result_tuple, current_text = data

        assembly_id, warning_message, _d = result_tuple

        # 步骤 1: 更新UI下拉菜单 (逻辑不变)
        if self.app.genome_sources_data and assembly_id in self.app.genome_sources_data and isinstance(target_var,
                                                                                                       tk.StringVar):
            target_var.set(assembly_id)

        # 步骤 2: 如果有警告信息，则进行状态检查 (逻辑不变)
        if warning_message:
            if current_text != self.last_ambiguity_text:
                MessageDialog(
                    parent=self.app,
                    title=_("注意：检测到歧义"),
                    message=_(warning_message),
                    icon_type="warning"
                )
                self.last_ambiguity_text = current_text

    def _handle_proxy_test_done(self, data: tuple):
        _ = self.app._
        success, message = data
        if success:
            self.app.ui_manager.show_info_message(_("代理测试成功"), message)
        else:
            self.app.ui_manager.show_error_message(_("代理测试失败"), message)

    def change_appearance_mode_event(self, new_mode_display: str):
        app = self.app
        _ = app._
        key_map = {
            _("浅色"): "Light",
            _("深色"): "Dark",
            _("跟随系统"): "System"
        }
        new_mode = key_map.get(new_mode_display, "System")

        app.ui_manager.apply_theme_from_mode(new_mode)
        app.ui_settings['appearance_mode'] = new_mode
        app.ui_manager.save_ui_settings()
        app.ui_manager._update_log_tag_colors()

    def check_annotation_file_status(self, config, genome_info, file_type_key) -> str:
        from cotton_toolkit.config.loader import get_local_downloaded_file_path
        try:
            file_path = get_local_downloaded_file_path(config, genome_info.assembly_id, file_type_key)
            if file_path and os.path.exists(file_path):
                if os.path.getsize(file_path) > 0:
                    return 'complete'
                else:
                    return 'incomplete'
            else:
                return 'missing'
        except Exception as e:
            self.app.logger.error(f"检查文件状态时出错 ('{file_type_key}'): {e}")
            return 'missing'

    def toggle_log_viewer(self):
        app = self.app
        _ = self.app._
        app.log_viewer_visible = not app.log_viewer_visible
        if app.log_viewer_visible:
            app.log_textbox.grid()
        else:
            app.log_textbox.grid_remove()
        app.toggle_log_button.configure(text=_("隐藏日志") if app.log_viewer_visible else _("显示日志"))

    def clear_log_viewer(self):
        _ = self.app._
        if hasattr(self.app, 'log_textbox'):
            self.app.log_textbox.configure(state="normal")
            self.app.log_textbox.delete("1.0", "end")
            self.app.log_textbox.configure(state="disabled")
            self.app._log_to_viewer(_("操作日志已清除。"), "INFO")

    def load_config_file(self, filepath: Optional[str] = None):
        _ = self.app._
        if not filepath:
            filepath = filedialog.askopenfilename(title=_("选择配置文件"),
                                                  filetypes=[("YAML files", "*.yml *.yaml"), ("All files", "*.*")])
            if not filepath:
                return
        self.app.message_queue.put(
            ("show_progress_dialog", {"title": _("加载中..."), "message": _("正在加载配置文件..."), "on_cancel": None}))
        threading.Thread(target=self._load_config_thread, args=(filepath,), daemon=True).start()

    def _load_config_thread(self, filepath: str):
        _ = self.app._
        try:
            config_obj = load_config(os.path.abspath(filepath))
            self.app.message_queue.put(("config_load_task_done", (True, config_obj, filepath)))
        except Exception as e:
            self.app.message_queue.put(("config_load_task_done", (False, str(e), None)))
        finally:
            self.app.message_queue.put(("progress", (100, _("加载完成。"))))
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _generate_default_configs_gui(self):
        _ = self.app._
        root_dir = os.path.abspath(".")
        main_config_path = os.path.join(root_dir, "config.yml")
        sources_config_path = os.path.join(root_dir, "genome_sources.yml")
        existing_files = []
        if os.path.exists(main_config_path):
            existing_files.append("'config.yml'")
        if os.path.exists(sources_config_path):
            existing_files.append("'genome_sources.yml'")
        if existing_files:
            files_str = _(" 和 ").join(existing_files)
            dialog = ConfirmationDialog(self.app, _("文件已存在"),
                                        _("文件 {} 已存在于程序根目录。是否要覆盖它们并生成新的默认配置?").format(
                                            files_str),
                                        button1_text=_("是，覆盖"), button2_text=_("否，取消"))
            if dialog.result is not True:
                self.app._log_to_viewer(_("用户取消了生成默认配置文件的操作。"), "INFO")
                return
        self.app.message_queue.put(("show_progress_dialog", {"title": _("生成配置文件中..."),
                                                             "message": _("正在根目录生成默认配置文件，请稍候..."),
                                                             "on_cancel": None}))
        threading.Thread(target=self._generate_default_configs_thread, args=(root_dir,), daemon=True).start()

    def _generate_default_configs_thread(self, output_dir: str):
        _ = self.app._
        try:
            self.app.message_queue.put(("progress", (20, _("正在生成主配置文件..."))))
            success, new_cfg_path, _d = generate_default_config_files(output_dir, overwrite=True)
            self.app.message_queue.put(("progress", (80, _("生成其他配置文件..."))))
            if success:
                self.app.message_queue.put(("progress", (100, _("配置文件生成完成。"))))
                self.app.message_queue.put(
                    ("task_done", (True, _("生成默认配置"), {'action': 'load_new_config', 'path': new_cfg_path})))
            else:
                self.app.message_queue.put(("error", _("生成默认配置文件失败。")))
        except Exception as e:
            self.app.message_queue.put(("error", f"{_('生成默认配置文件时发生错误:')} {e}\n{traceback.format_exc()}"))
        finally:
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _handle_generate_default_configs_done(self, data: tuple):
        _ = self.app._
        success, task_display_name, result_data = data
        if success and result_data and result_data.get('action') == 'load_new_config':
            new_cfg_path = result_data['path']
            dialog = ConfirmationDialog(self.app, _("生成成功"),
                                        f"{_('默认配置文件已成功生成。')}\n\n{_('是否立即加载?')}",
                                        button1_text=_("是"), button2_text=_("否"))
            if dialog.result is True:
                self.load_config_file(filepath=new_cfg_path)
        elif not success:
            pass

    def _show_about_window(self):
        """
        【已修正】显示一个尺寸动态、内容丰富的“关于”窗口。
        """
        _ = self.app._

        about_win = ttkb.Toplevel(self.app)
        about_win.title(_("关于 FCGT"))
        about_win.bind("<Escape>", lambda e: about_win.destroy())
        about_win.minsize(500, 400)
        about_win.transient(self.app)
        about_win.grab_set()

        main_frame = ttkb.Frame(about_win, padding=15)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(main_frame, highlightthickness=0, bd=0)
        scrollbar = ttkb.Scrollbar(main_frame, orient="vertical", command=canvas.yview, bootstyle="round-primary")
        scrollable_frame = ttkb.Frame(canvas)
        canvas_frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")

        def _bind_scroll(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)

        _bind_scroll(about_win)
        _bind_scroll(main_frame)
        _bind_scroll(canvas)
        _bind_scroll(scrollable_frame)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        labels_to_wrap = []

        def populate_content(parent):
            _ = self.app._
            header_font = self.app.app_font_bold
            content_font = self.app.app_font
            link_font = self.app.app_font.copy()
            link_font.configure(underline=True)

            def bind_all_children_scroll(widget):
                for child in widget.winfo_children():
                    _bind_scroll(child)
                    bind_all_children_scroll(child)

            def add_label(text, font, justify="left", wrappable=True, **kwargs):
                lbl = ttkb.Label(parent, text=text, font=font, justify=justify, **kwargs)
                lbl.pack(fill="x", anchor="w", pady=(0, 2), padx=5)
                if wrappable:
                    labels_to_wrap.append(lbl)
                return lbl

            def add_separator():
                ttkb.Separator(parent).pack(fill="x", anchor="w", pady=10)

            add_label(_("程序名称") + ": Friendly Cotton Genomes Toolkit (FCGT)", content_font)
            add_label(_("版本") + f": {PKG_VERSION}", content_font)
            add_label(_("项目地址") + ":", content_font, wrappable=False)
            gh_link = add_label(PKG_PUBLISH_URL, link_font, wrappable=False, bootstyle="info", cursor="hand2")
            gh_link.bind("<Button-1>", lambda e: webbrowser.open(PKG_PUBLISH_URL))
            add_separator()
            add_label(_("致谢与引用"), header_font)
            add_label(_("本工具依赖 CottonGen 提供的权威数据，感谢其团队持续的开放和维护。"), content_font)

            add_label("CottonGen " + _("文章:"), header_font).pack(pady=(10, 5))
            add_label(
                "• Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. Plants 10(12), 2805.",
                content_font)
            add_label(
                "• Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. Nucleic Acids Research 42(D1), D1229-D1236.",
                content_font)

            add_label("BLAST+ " + _("文章:"), header_font).pack(pady=(10, 5))
            add_label(
                "• Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. BLAST+: architecture and applications. BMC Bioinformatics. 2009 Dec 15;10:421. doi: 10.1186/1471-2105-10-421. PMID: 20003500; PMCID: PMC2803857.",
                content_font)

            add_label(_("基因组引用文献:"), header_font).pack(pady=(10, 5))
            citations = [
                "• NAU-NBI_v1.1: Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015",
                "• UTX-JGI-Interim-release_v1.1:",
                "  Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].",
                "  Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .",
                "  Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.",
                "  Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.",
                "• HAU_v1 / v1.1: Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03",
                "• ZJU-improved_v2.1_a1: Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. Nature genetics. 2019 Jan;51(1):164.",
                "• CRI_v1: Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.",
                "• WHU_v1: Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4",
                "• UTX_v2.1: Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.",
                "• HAU_v2.0: Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. \"High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres.\" Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722"
            ]
            for cit in citations: add_label(cit, content_font)
            add_separator()
            add_label(_("许可证"), header_font)
            add_label(_("本软件根据 Apache License 2.0 获得许可。"), content_font)
            add_separator()
            add_label(_("免责声明"), header_font)
            add_label(_("上述基因组的数据下载与处理均由用户执行，本工具仅进行框架服务。"), content_font)
            bind_all_children_scroll(parent)

        def resize_content(event):
            if not canvas.winfo_exists(): return
            canvas_width = event.width
            canvas.itemconfig(canvas_frame_id, width=canvas_width)
            for lbl in labels_to_wrap:
                if lbl.winfo_exists():
                    lbl.configure(wraplength=canvas_width - 15)

        def on_frame_configure(event):
            if not canvas.winfo_exists(): return
            canvas.configure(scrollregion=canvas.bbox("all"))

        populate_content(scrollable_frame)
        canvas.bind("<Configure>", resize_content)
        scrollable_frame.bind("<Configure>", on_frame_configure)

        button_frame = ttkb.Frame(about_win)
        button_frame.pack(side="bottom", fill="x", pady=(10, 15), padx=10)
        ok_button = ttkb.Button(button_frame, text=_("确定"), command=about_win.destroy, bootstyle="primary")
        ok_button.pack()

        about_win.update_idletasks()
        final_w = 1000
        about_win.geometry(f'{final_w}x1')
        about_win.update_idletasks()
        req_h = scrollable_frame.winfo_reqheight() + button_frame.winfo_reqheight() + 45
        max_h = int(self.app.winfo_height() * 0.85)
        final_h = min(req_h, max_h)
        parent_x, parent_y = self.app.winfo_x(), self.app.winfo_y()
        parent_w, parent_h = self.app.winfo_width(), self.app.winfo_height()
        x = parent_x + (parent_w - final_w) // 2
        y = parent_y + (parent_h - final_h) // 2
        about_win.geometry(f"{final_w}x{final_h}+{x}+{y}")

        # 【核心修正】函数在此处等待窗口关闭，之后不再执行任何操作
        about_win.wait_window()

        def resize_content(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_frame_id, width=canvas_width)
            for lbl in labels_to_wrap:
                lbl.configure(wraplength=canvas_width - 15)

        populate_content(scrollable_frame)
        canvas.bind("<Configure>", resize_content)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        button_frame = ttkb.Frame(about_win)
        button_frame.pack(side="bottom", fill="x", pady=(10, 15), padx=10)
        ok_button = ttkb.Button(button_frame, text=_("确定"), command=about_win.destroy, bootstyle="primary")
        ok_button.pack()

        # --- 最终版动态尺寸与居中 ---
        # 1. 先设置一个固定的宽度
        final_w = 1000
        about_win.geometry(f'{final_w}x1')  # 用最小高度强制设定宽度
        about_win.update_idletasks()  # 强制UI刷新，使文字根据新宽度换行

        # 2. 现在基于换行后的内容计算实际需要的高度
        req_h = scrollable_frame.winfo_reqheight() + button_frame.winfo_reqheight() + 45  # 内容+按钮+所有边距

        # 3. 设定一个最大高度（不超过主窗口的85%），防止窗口过大
        max_h = int(self.app.winfo_height() * 0.85)
        final_h = min(req_h, max_h)

        # 4. 获取主窗口位置，并将“关于”窗口居中
        parent_x = self.app.winfo_x()
        parent_y = self.app.winfo_y()
        parent_w = self.app.winfo_width()
        parent_h = self.app.winfo_height()
        x = parent_x + (parent_w - final_w) // 2
        y = parent_y + (parent_h - final_h) // 2
        about_win.geometry(f"{final_w}x{final_h}+{x}+{y}")

        about_win.wait_window()

    def _open_online_help(self):
        _ = self.app._
        try:
            webbrowser.open(PKG_HELP_URL)
        except Exception as e:
            self.app.ui_manager.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))

    def _browse_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        _ = self.app._
        if filepath := filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)

    def _browse_save_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        _ = self.app._
        if filepath := filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                    defaultextension=filetypes_list[0][1].replace("*", "")):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)

    def _browse_directory(self, entry_widget: ttkb.Entry):
        _ = self.app._
        if directory_path := filedialog.askdirectory(title=_("选择目录")):
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory_path)

    def _auto_identify_genome_version(self, gene_input_textbox: tk.Text, target_assembly_var: tk.StringVar):
        """
        【已修改】将当前文本内容也传递给后台线程。
        """
        current_text = gene_input_textbox.get("1.0", "end").strip()
        if not current_text or current_text in self.app.placeholders.values():
            # 如果文本框为空或为占位符，重置状态
            self.last_ambiguity_text = ""
            return

        gene_ids = [g.strip() for g in current_text.replace(",", "\n").splitlines() if g.strip()]
        if not gene_ids or not self.app.genome_sources_data: return

        # 将当前文本内容 (current_text) 作为参数传递给线程
        threading.Thread(target=self._identify_genome_thread, args=(gene_ids, target_assembly_var, current_text),
                         daemon=True).start()

    def _identify_genome_thread(self, gene_ids, target_assembly_var, current_text):
        """
        【已修改】将当前文本内容连同识别结果一起放入消息队列。
        """
        try:
            result_tuple = identify_genome_from_gene_ids(
                gene_ids,
                self.app.genome_sources_data,
                status_callback=self.gui_status_callback
            )
            if result_tuple:
                # 将 target_var, result_tuple, 和 current_text 一起发送
                self.app.message_queue.put(("auto_identify_success", (target_assembly_var, result_tuple, current_text)))
        except Exception as e:
            logger.error(f"自动识别基因组时发生错误: {e}")

    def test_proxy_connection(self):
        app = self.app
        _ = self.app._
        http_proxy = app.proxy_http_entry.get().strip()
        https_proxy = app.proxy_https_entry.get().strip()
        if not http_proxy and not https_proxy:
            app.ui_manager.show_info_message(_("信息"), _("请先填写HTTP或HTTPS代理地址。"))
            return
        proxies = {k: v for k, v in {'http': http_proxy, 'https': https_proxy}.items() if v}
        self.app.message_queue.put(("show_progress_dialog",
                                    {"title": _("正在测试代理..."), "message": _("尝试通过代理连接到测试站点..."),
                                     "on_cancel": None}))
        threading.Thread(target=self._test_proxy_thread, args=(proxies,), daemon=True).start()

    def _test_proxy_thread(self, proxies: dict):
        _ = self.app._
        test_url = "https://httpbin.org/get"
        try:
            self.app.message_queue.put(("progress", (20, _("发送请求..."))))
            response = requests.get(test_url, proxies=proxies, timeout=15)
            response.raise_for_status()
            origin_ip = response.json().get('origin', 'N/A')
            message = f"{_('连接成功！')}\n{_('测试站点报告的IP地址是:')} {origin_ip}"
            self.app.message_queue.put(("proxy_test_done", (True, message)))
            self.app.message_queue.put(("progress", (100, _("测试完成。"))))
        except requests.exceptions.RequestException as e:
            self.app.message_queue.put(("proxy_test_done", (False, f"{_('连接失败。')}\n{_('错误详情:')} {e}")))
            self.app.message_queue.put(("progress", (100, _("测试失败。"))))
        finally:
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _gui_fetch_ai_models(self, provider_key: str, use_proxy: bool):
        app = self.app
        _ = self.app._
        app.logger.info(f"正在获取 '{provider_key}' 的模型列表... (使用代理: {use_proxy})")
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                _("任务 '{}' 正在运行中，请等待其完成后再开始新任务。").format(
                                                    app.active_task_name))
            return
        try:
            safe_key = provider_key.replace('-', '_')
            api_key = getattr(app, f"ai_{safe_key}_apikey_entry").get().strip()
            base_url = getattr(app, f"ai_{safe_key}_baseurl_entry").get().strip() or None
        except AttributeError:
            app.ui_manager.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载。"))
            return
        if not api_key or "YOUR_" in api_key:
            app.ui_manager.show_warning_message(_("缺少API Key"),
                                                _("请先在编辑器中为 '{}' 填写有效的API Key。").format(provider_key))
            return
        proxies = None
        if use_proxy:
            http_p, https_p = app.proxy_http_entry.get().strip(), app.proxy_https_entry.get().strip()
            if http_p or https_p: proxies = {'http': http_p, 'https': https_p}
        app.active_task_name = f"{_('刷新模型列表')}: {provider_key}"
        app.cancel_current_task_event.clear()
        self.app.message_queue.put(("show_progress_dialog",
                                    {"title": _("正在获取模型..."), "message": _("连接到 {}...").format(provider_key),
                                     "on_cancel": app.cancel_current_task_event.set}))
        thread_kwargs = {'provider': provider_key, 'api_key': api_key, 'base_url': base_url, 'proxies': proxies,
                         'cancel_event': app.cancel_current_task_event, 'progress_callback': self.gui_progress_callback}
        threading.Thread(target=self._fetch_models_thread, kwargs=thread_kwargs, daemon=True).start()

    def _fetch_models_thread(self, **kwargs):
        provider = kwargs.get('provider')
        _ = self.app._
        cancel_event = kwargs.get('cancel_event')
        progress = kwargs.get('progress_callback', lambda p, m: None)
        try:
            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")))
                return
            progress(10, _("开始连接AI服务..."))
            models = AIWrapper.get_models(provider=kwargs.get('provider'), api_key=kwargs.get('api_key'),
                                          base_url=kwargs.get('base_url'), proxies=kwargs.get('proxies'),
                                          cancel_event=cancel_event)
            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")))
            else:
                self.app.message_queue.put(("ai_models_fetched", (provider, models)))
                progress(90, _("数据处理中..."))
        except Exception as e:
            if not (cancel_event and cancel_event.is_set()):
                self.app.message_queue.put(("ai_models_fetched", (provider, str(e))))
        finally:
            self.app.message_queue.put(("progress", (100, _("刷新完成。"))))
            self.app.message_queue.put(("hide_progress_dialog", None))
            self.app.active_task_name = None

    def gui_status_callback(self, message: str, level: str = "INFO"):
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        log_level = level.upper() if level.upper() in valid_levels else "INFO"
        logger.log(logging.getLevelName(log_level), message)
        self.app.message_queue.put(("status", message))

    def gui_progress_callback(self, percentage: float, message: str):
        self.app.message_queue.put(("progress", (percentage, message)))

    def _handle_csv_columns_fetched(self, data: tuple):
        columns, error_msg = data
        if ai_tab := self.app.tool_tab_instances.get('ai_assistant'):
            ai_tab.update_column_dropdown_ui(columns, error_msg)
        else:
            logger.warning("无法找到AI助手选项卡实例来更新列名。")
