# event_handler.py

import logging
import os
import threading
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, Optional, Any

import requests
import ttkbootstrap as ttkb

from cotton_toolkit import HELP_URL as PKG_HELP_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.utils.advanced_tools_test import check_muscle_executable, check_iqtree_executable, \
    check_trimal_executable
from cotton_toolkit.utils.gene_utils import identify_genome_from_gene_ids
from cotton_toolkit.utils.localization import setup_localization
from cotton_toolkit.utils.network_utils import test_proxy
from .dialogs import ConfirmationDialog, AboutDialog

if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

# 修改: 使用新的日志命名规范
logger = logging.getLogger("ui.event_handler")


class EventHandler:
    """处理所有用户交互、后台消息和任务启动。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.ui_manager = app.ui_manager
        self.message_handlers = self._initialize_message_handlers()
        self.last_ambiguity_text: str = ""

    def _initialize_message_handlers(self) -> Dict[str, Callable]:
        """
        增加对新消息类型的处理。
        """
        handlers = {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "phylo_step_muscle_done": self._handle_phylo_step_muscle_done,
            "phylo_step_trim_done": self._handle_phylo_step_trim_done,
            "phylo_step_iqtree_done": self._handle_phylo_step_iqtree_done,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_test_result": self._handle_ai_test_result,
            "tool_test_done": self._handle_tool_test_done,
            "proxy_test_done": self._handle_proxy_test_done,
            "csv_columns_fetched": self._handle_csv_columns_fetched,
            "show_progress_dialog": self.ui_manager._show_progress_dialog,
            "hide_progress_dialog": self.ui_manager._hide_progress_dialog,
            "auto_identify_success": self._handle_auto_identify_result,

        }
        return handlers

    # --- 语言切换处理 ---
    def on_language_change(self, language_name: str):
        """当用户从下拉菜单中选择一个新语言时触发。"""
        app = self.app
        _ = app._

        selected_lang_code = app.LANG_NAME_TO_CODE.get(language_name)
        if not selected_lang_code:
            logger.warning(_("Invalid language name selected: {}").format(language_name))
            return

        logger.info(_("Language change requested to: {} ({})").format(language_name, selected_lang_code))

        app.ui_settings['language'] = selected_lang_code
        self.ui_manager.save_ui_settings()

        app._ = setup_localization(language_code=selected_lang_code)
        _ = app._
        if app.current_config and app.config_path:
            app.current_config.i18n_language = selected_lang_code
            if save_config(app.current_config, app.config_path):
                logger.info(
                    _("Main config file '{}' updated with language '{}'.").format(os.path.basename(app.config_path),
                                                                                  selected_lang_code))
                app.message_queue.put(('show_info', {'title': _("配置已保存"),
                                                     'message': _("语言设置已同步到 {}。").format(
                                                         os.path.basename(app.config_path))}))
            else:
                logger.error(f"Failed to save language setting to '{app.config_path}'.")
                app.message_queue.put(
                    ('show_error', {'title': _("保存失败"), 'message': _("无法将语言设置写入配置文件。")}))

        dialog = ConfirmationDialog(
            parent=app,
            title=_("需要重启"),
            message=_("语言设置已更改。为了使所有更改完全生效，建议您重启应用程序。"),
            button1_text=_("立即重启"),
            button2_text=_("稍后重启")
        )

        dialog.wait_window()

        if dialog.result is True:
            app.restart_app()

    def on_closing(self):
        """
        处理主窗口关闭事件，增加退出确认。
        """
        _ = self.app._
        if self.app.active_task_name:
            dialog = ConfirmationDialog(
                parent=self.app,
                title=_("确认退出"),
                message=_("任务'{}'正在运行中，确定要强制退出吗？").format(self.app.active_task_name),
                button1_text=_("强制退出"),
                button2_text=_("取消")
            )
            dialog.wait_window()
            if dialog.result is True:
                self.app.cancel_current_task_event.set()
                self.app.destroy()
        else:
            dialog = ConfirmationDialog(
                parent=self.app,
                title=_("确认退出"),
                message=_("您确定要退出吗？"),
                button1_text=_("退出"),
                button2_text=_("取消")
            )
            dialog.wait_window()

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
        # _ 使用的是程序启动时的初始翻译器
        _ = self.app._
        try:
            loaded_config, genome_sources, config_path_to_send = None, None, None

            # 步骤 1: 加载 config.yml
            app.message_queue.put(("progress", (10, _("正在加载配置文件..."))))
            if os.path.exists(default_config_path := "config.yml"):
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)

            if loaded_config:
                # 步骤 2: 根据 config.yml 的语言，重新设置整个应用的翻译系统
                config_lang = loaded_config.i18n_language
                logger.info(_("配置文件中的语言为 '{}'，将以此为准设置应用语言。").format(config_lang))

                # 更新应用核心的翻译器
                app._ = setup_localization(language_code=config_lang)

                # 将更新后的翻译器同步给子模块
                app.ui_manager.translator = app._
                self._ = app._

                # 加载后续数据
                app.message_queue.put(("progress", (30, app._("正在加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config)
            else:
                logger.warning(_("未找到 config.yml，将使用默认语言启动。"))

            app.message_queue.put(("progress", (80, app._("启动完成准备..."))))
            startup_data = {"config": loaded_config, "genome_sources": genome_sources,
                            "config_path": config_path_to_send}
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            app.message_queue.put(("startup_failed", f"{_('应用启动失败')}: {e}\n{traceback.format_exc()}"))
        finally:
            app.message_queue.put(("progress", (100, app._("初始化完成。"))))
            app.message_queue.put(("hide_progress_dialog", None))

    def _cancel_and_cleanup_task(self):
        """
        立即取消任务并清理UI，不再等待后台线程的确认。
        """
        _ = self.app._
        logger.warning(_("用户请求取消当前任务..."))

        # 1. 向后台线程发送取消信号（尽力而为）
        self.app.cancel_current_task_event.set()

        # 2. 核心：不等后台线程响应，立即在UI层面终结任务
        task_display_name = self.app.active_task_name or _("未知任务")
        self.ui_manager._finalize_task_ui(
            task_display_name=task_display_name,
            success=False,  # 任务未成功
            result_data="CANCELLED"  # 结果是“已取消”
        )

        logger.warning(
            _("任务 '{}' 已被强制取消。后台线程可能会在完成最后的IO操作后悄默声地终止。").format(task_display_name)
        )

    def start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any],
                   on_success: Optional[Callable] = None, task_key: Optional[str] = None,
                   is_workflow_step: bool = False):
        """
        启动一个后台任务，并确保所有必要的回调函数（包括自定义的 status_callback）都被正确传递。
        """
        app = self.app
        _ = self.app._
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                _("任务 '{}' 正在运行中，请等待其完成后再开始新任务。").format(
                                                    app.active_task_name))
            return

        if task_key is None:
            task_key = task_name

        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        app.cancel_current_task_event.clear()
        self.app.message_queue.put(("show_progress_dialog", {"title": task_name, "message": _("正在处理..."),
                                                             "on_cancel": self._cancel_and_cleanup_task}))

        # 1. 创建一个新的字典 thread_kwargs，用于传递给后台线程。
        #    这样做可以避免直接修改原始的 kwargs 字典，是更安全的做法。
        thread_kwargs = kwargs.copy()

        # 2. 将所有标准的回调和事件添加到这个新字典中。
        #    我们在 data_download_tab.py 中传入的 'status_callback' 已经存在于 kwargs 中，
        #    所以 thread_kwargs.copy() 会自动包含它。
        thread_kwargs.update({
            'cancel_event': app.cancel_current_task_event,
            'progress_callback': self.gui_progress_callback
        })

        # 3. 启动线程，并将这个构建好的 thread_kwargs 字典传递给包装器。
        threading.Thread(target=self._task_wrapper,
                         args=(target_func, thread_kwargs, task_name, task_key, on_success, is_workflow_step),
                         daemon=True).start()

    def _task_wrapper(self, target_func: Callable, kwargs: Dict[str, Any], task_name: str, task_key: str,
                      on_success: Optional[Callable] = None, is_workflow_step: bool = False):
        """
        在后台线程中执行任务的包装器。
        (此方法无需修改，它会正确地将接收到的 kwargs 解包并传递给目标函数)
        """
        _ = self.app._
        result = None
        e = None
        try:
            # kwargs 字典在这里被解包，所有回调函数 (progress_callback, status_callback, cancel_event)
            # 都会被作为命名参数传递给 target_func (例如 run_preprocess_annotation_files)
            result = target_func(**kwargs)
            if on_success and not self.app.cancel_current_task_event.is_set():
                self.app.after(0, on_success, result)
        except Exception as exc:
            e = exc
            logger.error(_("任务 '{}' 发生错误: {}").format(task_name, exc))
        finally:
            # 只有在不是工作流中间步骤时，才发送通用的 "task_done" 消息
            if not is_workflow_step:
                final_data = None
                if self.app.cancel_current_task_event.is_set():
                    final_data = (False, task_name, "CANCELLED", task_key)
                elif e:
                    final_data = (False, task_name, e, task_key)
                else:
                    final_data = (True, task_name, result, task_key)

                if final_data:
                    self.app.message_queue.put(("task_done", final_data))
            # 如果是工作流步骤，则不执行任何操作，完全依赖 on_success 回调

    def _handle_startup_complete(self, data: dict):
        app = self.app
        _ = self.app._
        # 修改: 使用标准 logger
        logger.info(_("应用程序启动完成。"))
        if self.app.ui_manager and hasattr(self.app, 'config_path_display_var'):
            self.app.ui_manager.update_ui_from_config()
        else:
            logger.warning(_("无法在启动时更新UI配置：UIManager或config_path_display_var未就绪。"))

        # 步骤 1: 将后台加载的数据赋值给主应用实例
        app.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")
        config_path_from_load = data.get("config_path")
        if config_data:
            app.current_config = config_data
            app.config_path = config_path_from_load
            logger.info(_("默认配置文件加载成功。"))
        else:
            logger.warning(_("未找到或无法加载默认配置文件。"))

        if app.current_config:
            # 步骤 2: 根据 config.yml 精确同步【语言下拉菜单】的显示值
            current_lang_code = app.current_config.i18n_language
            lang_display_name = app.LANG_CODE_TO_NAME.get(current_lang_code, "English")
            app.selected_language_var.set(lang_display_name)
            # 这条日志确认了下拉菜单的同步
            logger.info(_("启动时，语言下拉菜单已根据配置文件同步为: {}").format(lang_display_name))

            # 步骤 3: 重新翻译【主窗口标题】
            app.title(_(app.title_text_key))

            # 步骤 4: 重新翻译【所有已注册的静态UI组件】（如主页的按钮和标签）
            logger.info(_("正在刷新静态UI文本..."))
            for widget, text_key in app.translatable_widgets.items():
                if widget and widget.winfo_exists():
                    try:
                        # 检查组件是否支持 'text' 属性
                        if 'text' in widget.keys():
                            widget.configure(text=_(text_key))
                    except Exception as e:
                        # 忽略为不支持的组件设置文本时可能发生的错误
                        logger.debug(f"为组件 {widget} 设置文本时出错 (可忽略): {e}, text_key: {text_key}")

            # 步骤 5: 更新UI的其余部分（按钮状态、路径等）
        app.ui_manager.update_ui_from_config()
        app.ui_manager.update_button_states()

    def _handle_startup_failed(self, data: str):
        _ = self.app._
        self.app.ui_manager._hide_progress_dialog()
        self.app.ui_manager.show_error_message(_("启动错误"), str(data))
        self.app.ui_manager.update_button_states()

    def _handle_phylo_step_muscle_done(self, workflow_instance: Any):
        """委托：将MUSCLE完成事件转发给对应的工作流实例。"""
        if workflow_instance:
            workflow_instance._handle_muscle_done()

    def _handle_phylo_step_trim_done(self, workflow_instance: Any):
        """委托：将trimAl完成事件转发给对应的工作流实例。"""
        if workflow_instance:
            workflow_instance._handle_trim_done()

    def _handle_phylo_step_iqtree_done(self, workflow_instance: Any):
        """委托：将IQ-TREE完成事件转发给对应的工作流实例。"""
        # 为了保持接口一致，我们直接调用最终处理方法。
        if workflow_instance:
            workflow_instance._handle_iqtree_done()

    def _handle_config_load_task_done(self, data: tuple):
        """
        在加载外部配置文件后，先进行版本兼容性检查。
        - 如果不兼容，则弹窗报错并保留旧配置。
        - 如果兼容，则将新配置设为当前配置并刷新UI。
        """
        app = self.app
        _ = self.app._
        success, loaded_config, original_filepath = data

        if not success:
            app.ui_manager.show_error_message(_("加载失败"), str(loaded_config))
            return

        # 成功路径 (level 为 'info' 或 'warning' 时会执行这里)
        root_config_path = os.path.abspath("config.yml")
        try:
            # 1. 将加载的文件内容保存到项目根目录
            save_config(loaded_config, root_config_path)

            # 2. 将其设为当前正在使用的配置
            app.current_config = loaded_config
            app.config_path = root_config_path
            app.ui_manager.show_info_message(_("加载并覆盖成功"), _("已将 '{}' 的内容加载并保存至 '{}'。").format(
                os.path.basename(original_filepath), os.path.basename(root_config_path)))

            app.genome_sources_data = get_genome_data_sources(app.current_config)

            # 3. 全面刷新UI以应用新配置
            app.ui_manager.update_ui_from_config()

            if app.editor_ui_built:
                logger.info(_("配置文件已加载，正在刷新编辑器UI..."))
                app._apply_config_values_to_editor()

            app.refresh_all_tool_tabs()

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

        if success and isinstance(result_data, dict) and result_data.get('action') == 'load_new_config':
            new_cfg_path = result_data.get('path')
            if new_cfg_path:
                logger.info(_("默认配置已生成，将自动加载: {}").format(new_cfg_path))
                # 直接调用加载方法，不再弹窗询问
                self.load_config_file(filepath=new_cfg_path)
                # （可选）向用户发送一个简短的成功通知
                app.message_queue.put(('status', _("默认配置生成成功并已自动加载。")))
            return  # 提前结束，不执行下面的通用逻辑

        refresh_trigger_keys = ["download", "preprocess_anno", "preprocess_blast"]
        if success and task_key in refresh_trigger_keys:
            if download_tab := app.tool_tab_instances.get('download'):
                if hasattr(download_tab, '_update_dynamic_widgets'):
                    selected_genome = download_tab.selected_genome_var.get()
                    app.after(50, lambda: download_tab._update_dynamic_widgets(selected_genome))
                    logger.info(_("数据下载选项卡状态已在任务 '{}' 完成后自动刷新。").format(task_display_name))

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
            self.app.ui_manager.update_ai_model_dropdown(provider_key, models_or_error)

            if self.app.current_config:
                provider_cfg = self.app.current_config.ai_services.providers.get(provider_key)
                if provider_cfg:
                    provider_cfg.available_models = ",".join(models_or_error)
                    # 修改: 使用标准 logger
                    logger.info(
                        f"In-memory config for '{provider_key}' updated with a list of {len(models_or_error)} available models.")

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

        if self.app.genome_sources_data and assembly_id in self.app.genome_sources_data and isinstance(target_var,
                                                                                                       tk.StringVar):
            target_var.set(assembly_id)

        if warning_message:
            # 防止在用户输入过程中，同一个警告信息反复弹出
            if current_text != self.last_ambiguity_text:
                self.app.ui_manager.show_warning_message(
                    title=_("注意：检测到歧义"),
                    message=_(warning_message)
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

    def toggle_log_viewer(self):
        app = self.app
        _ = self.app._
        app.log_viewer_visible = not app.log_viewer_visible
        if hasattr(app, 'log_text_container'):
            if app.log_viewer_visible:
                app.log_text_container.grid()
            else:
                app.log_text_container.grid_remove()
        app.toggle_log_button.configure(text=_("隐藏日志") if app.log_viewer_visible else _("显示日志"))

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
        sources_config_path = os.path.join(root_dir, "genome_sources_list.yml")
        existing_files = []
        if os.path.exists(main_config_path):
            existing_files.append("'config.yml'")
        if os.path.exists(sources_config_path):
            existing_files.append("'genome_sources_list.yml'")
        if existing_files:
            files_str = _(" 和 ").join(existing_files)
            dialog = ConfirmationDialog(self.app, _("文件已存在"),
                                        _("文件 {} 已存在于程序根目录。是否要覆盖它们并生成新的默认配置?").format(
                                            files_str),
                                        button1_text=_("是，覆盖"), button2_text=_("否，取消"))
            if dialog.result is not True:
                logger.info(_("用户取消了生成默认配置文件的操作。"))
                return
        self.app.message_queue.put(("show_progress_dialog", {"title": _("生成配置文件中..."),
                                                             "message": _("正在根目录生成默认配置文件，请稍候..."),
                                                             "on_cancel": None}))
        threading.Thread(target=self._generate_default_configs_thread, args=(root_dir,), daemon=True).start()

    def _generate_default_configs_thread(self, output_dir: str):
        _ = self.app._
        try:
            self.app.message_queue.put(("progress", (20, _("正在生成主配置文件..."))))
            success, new_cfg_path, _4, _g = generate_default_config_files(output_dir, overwrite=True)
            self.app.message_queue.put(("progress", (80, _("生成其他配置文件..."))))
            if success:
                self.app.message_queue.put(("progress", (100, _("配置文件生成完成。"))))
                self.app.message_queue.put(
                    ("task_done",
                     (True, _("生成默认配置"), {'action': 'load_new_config', 'path': new_cfg_path}, "generate_config")))
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
        AboutDialog(parent=self.app, title=self._("关于 FCGT"))

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
            self.last_ambiguity_text = ""
            return

        gene_ids = [g.strip() for g in current_text.replace(",", "\n").splitlines() if g.strip()]
        if not gene_ids or not self.app.genome_sources_data: return

        threading.Thread(target=self._identify_genome_thread, args=(gene_ids, target_assembly_var, current_text),
                         daemon=True).start()

    def _identify_genome_thread(self, gene_ids, target_assembly_var, current_text):
        """
        【已修改】将当前文本内容连同识别结果一起放入消息队列。
        """
        try:
            # 修改: identify_genome_from_gene_ids 不再接受 status_callback
            result_tuple = identify_genome_from_gene_ids(
                gene_ids,
                self.app.genome_sources_data
            )
            if result_tuple:
                self.app.message_queue.put(("auto_identify_success", (target_assembly_var, result_tuple, current_text)))
        except Exception as e:
            # 修改: 使用标准 logger
            logger.error(f"自动识别基因组时发生错误: {e}")

    def test_proxy_connection(self):
        app = self.app
        _ = self.app._

        try:
            http_proxy = app.editor_widgets['proxies.http']['widget'].get().strip()
            https_proxy = app.editor_widgets['proxies.https']['widget'].get().strip()
        except KeyError:
            app.ui_manager.show_error_message(_("UI错误"), _("无法找到代理设置输入框，请确保编辑器已加载。"))
            return

        if not http_proxy and not https_proxy:
            app.ui_manager.show_info_message(_("信息"), _("请先填写HTTP或HTTPS代理地址。"))
            return
        proxies = {k: v for k, v in {'http': http_proxy, 'https': https_proxy}.items() if v}
        self.app.message_queue.put(("show_progress_dialog",
                                    {"title": _("正在测试代理..."), "message": _("尝试通过代理连接到测试站点..."),
                                     "on_cancel": None}))
        threading.Thread(target=self._test_proxy_thread, args=(proxies,), daemon=True).start()

    def _handle_tool_test_done(self, data: tuple):
        """
        这个通用的处理器保持不变，它负责接收并显示所有工具的测试结果。
        """
        tool_name, success, message = data
        title = _("{} 测试结果").format(tool_name)
        if success:
            self.app.ui_manager.show_info_message(title, message)
        else:
            self.app.ui_manager.show_error_message(title, message)

    def _test_proxy_thread(self, proxies: dict):
        """
        在后台线程中调用后端函数来测试代理。
        此方法不再包含任何网络请求逻辑。
        """
        _ = self.app._
        try:
            success, message = test_proxy(proxies)

            # 2. 将后端返回的结果放入消息队列
            self.app.message_queue.put(("proxy_test_done", (success, message)))

        except Exception as e:
            # 捕获调用过程中的意外错误
            error_msg = f"{_('调用代理测试时发生意外错误:')} {e}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self.app.message_queue.put(("proxy_test_done", (False, error_msg)))

        finally:
            # 3. 确保关闭等待对话框
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _gui_fetch_ai_models(self, provider_key: str, use_proxy: bool):
        app = self.app
        _ = self.app._
        logger.info(f"正在获取 '{provider_key}' 的模型列表... (使用代理: {use_proxy})")
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                _("任务 '{}' 正在运行中，请等待其完成后再开始新任务。").format(
                                                    app.active_task_name))
            return

        api_key = ""
        base_url = None

        path_api_key = f'ai_services.providers.{provider_key}.api_key'
        path_base_url = f'ai_services.providers.{provider_key}.base_url'

        if path_api_key not in app.editor_widgets or path_base_url not in app.editor_widgets:
            logger.warning(f"尝试获取 '{provider_key}' 模型时，其UI控件尚未在 editor_widgets 中注册。")
            app.ui_manager.show_warning_message(
                _("UI仍在加载"),
                _("编辑器界面仍在初始化，请稍候一秒再点击刷新。")
            )
            return

        api_key_widget = app.editor_widgets[path_api_key]['widget']
        base_url_widget = app.editor_widgets[path_base_url]['widget']
        api_key = api_key_widget.get().strip()
        base_url = base_url_widget.get().strip() or None

        if not api_key or "YOUR_" in api_key:
            app.ui_manager.show_warning_message(_("缺少API Key"),
                                                _("请先在编辑器中为 '{}' 填写有效的API Key。").format(provider_key))
            return

        proxies = None
        if use_proxy:
            try:
                http_p = app.editor_widgets['proxies.http']['widget'].get().strip()
                https_p = app.editor_widgets['proxies.https']['widget'].get().strip()
                if http_p or https_p:
                    proxies = {'http': http_p, 'https': https_p}
            except KeyError:
                app.ui_manager.show_error_message(_("UI错误"), _("无法找到代理设置输入框，请确保编辑器已加载。"))
                return

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

    def gui_progress_callback(self, percentage: float, message: str):
        self.app.message_queue.put(("progress", (percentage, message)))

    def _handle_csv_columns_fetched(self, data: tuple):
        columns, error_msg = data
        if ai_tab := self.app.tool_tab_instances.get('ai_assistant'):
            ai_tab.update_column_dropdown_ui(columns, error_msg)
        else:
            # 修改: 使用标准 logger
            logger.warning("无法找到AI助手选项卡实例来更新列名。")

    def start_tool_test(self, tool_name: str, backend_function: Callable, config_paths: list[str]):
        """
        一个通用的方法，用于启动任何外部工具的后台测试。

        Args:
            tool_name (str): 在UI上显示的工具名称。
            backend_function (Callable): 在后端实际执行检测的函数。
            config_paths (list[str]): 需要从UI配置中读取的路径键列表。
        """
        _ = self.app._
        try:
            # 1. 从UI控件中动态获取所有需要的路径
            paths = []
            for path_key in config_paths:
                widget = self.app.editor_widgets[path_key]['widget']
                paths.append(widget.get().strip())

        except KeyError as e:
            self.app.ui_manager.show_error_message(_("UI错误"), _("无法找到路径输入框: {}").format(e))
            return

        # 2. 显示通用的等待对话框
        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("正在测试 {}...").format(tool_name),
            "message": _("正在执行命令..."),
            "on_cancel": None
        }))

        # 3. 启动一个通用的后台线程
        threading.Thread(
            target=self._run_generic_test_thread,
            args=(tool_name, backend_function, paths),
            daemon=True
        ).start()

    def _run_generic_test_thread(self, tool_name: str, backend_function: Callable, paths: list):
        """
        一个通用的后台线程，负责调用任何后端检测函数并报告结果。

        Args:
            tool_name (str): 工具名称。
            backend_function (Callable): 后端检测函数。
            paths (list): 从UI获取到的路径参数列表。
        """
        try:
            # 4. 调用后端函数，使用 * 解包列表作为独立参数传入
            success, message = backend_function(*paths)

            # 5. 将结果发送回UI线程进行显示
            self.app.message_queue.put(("tool_test_done", (tool_name, success, message)))
        except Exception as e:
            # 捕获调用过程中的意外错误
            _ = self.app._
            error_msg = _("在测试 {} 期间发生意外错误: {}").format(tool_name, e)
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self.app.message_queue.put(("tool_test_done", (tool_name, False, error_msg)))
        finally:
            # 6. 确保关闭等待对话框
            self.app.message_queue.put(("hide_progress_dialog", None))

