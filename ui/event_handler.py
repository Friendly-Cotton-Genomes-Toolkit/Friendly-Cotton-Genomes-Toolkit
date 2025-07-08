import logging
import os
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, Optional, Any
import requests
import re
import ttkbootstrap as ttkb


from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.core.ai_wrapper import AIWrapper
from .dialogs import MessageDialog
from .utils.gui_helpers import identify_genome_from_gene_ids

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
        self.message_handlers = self._initialize_message_handlers()

    def _initialize_message_handlers(self) -> Dict[str, Callable]:
        """返回消息类型到其处理函数的映射。"""
        return {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,  # 用于进度条更新
            "hide_progress_dialog": self.app.ui_manager._hide_progress_dialog,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_test_result": self._handle_ai_test_result,
            "auto_identify_success": self._handle_auto_identify_success,
            "proxy_test_done": self._handle_proxy_test_done,
            "csv_columns_fetched": self._handle_csv_columns_fetched,
            "show_progress_dialog": self.app.ui_manager._show_progress_dialog  # 新增：处理显示进度弹窗的消息
        }

    def start_app_async_startup(self):
        """启动应用的异步加载流程。"""
        # 启动时显示进度弹窗的消息发送到队列，而不是直接调用
        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("图形界面启动中..."),
            "message": _("正在初始化应用程序和加载配置，请稍候..."),
            "on_cancel": None  # 启动过程不允许取消
        }))
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """后台加载线程。"""
        app = self.app
        try:
            loaded_config, genome_sources, config_path_to_send = None, None, None
            # 修改进度报告方式，通过队列发送
            app.message_queue.put(("progress", (10, _("正在加载配置文件..."))))
            if os.path.exists(default_config_path := "config.yml"):
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)

            if loaded_config:
                app.message_queue.put(("progress", (30, _("正在加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config, logger_func=logger.info)

            app.message_queue.put(("progress", (80, _("启动完成准备..."))))  # 启动最后阶段
            startup_data = {"config": loaded_config, "genome_sources": genome_sources,
                            "config_path": config_path_to_send}
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            app.message_queue.put(("startup_failed", f"{_('应用启动失败')}: {e}\n{traceback.format_exc()}"))
        finally:
            app.message_queue.put(("progress", (100, _("初始化完成。"))))  # 确保进度到100%
            app.message_queue.put(("hide_progress_dialog", None))

    def on_closing(self):
        dialog = MessageDialog(self.app, _("退出程序"), _("您确定要退出吗?"), "question", [_("确定"), _("取消")])
        if dialog.wait_window() or dialog.result == _("确定"):
            self.app.destroy()

    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any]):
        app = self.app
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                f"{_('任务')} '{app.active_task_name}' {_('正在运行。')}")
            return

        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        app.cancel_current_task_event.clear()

        # 发送消息到队列，让UI主线程显示进度弹窗
        self.app.message_queue.put(("show_progress_dialog", {
            "title": task_name,
            "message": _("正在处理..."),
            "on_cancel": app.cancel_current_task_event.set
        }))

        # 将 status_callback 和 progress_callback 直接传递给后台任务
        kwargs.update({
            'cancel_event': app.cancel_current_task_event,
            'status_callback': self.gui_status_callback,
            'progress_callback': self.gui_progress_callback  # 确保这里传递了
        })
        threading.Thread(target=self._task_wrapper, args=(target_func, kwargs, task_name), daemon=True).start()

    def _task_wrapper(self, target_func, kwargs, task_name):
        """
        包装后台任务的执行，处理结果、错误和取消。
        """
        try:
            result = target_func(**kwargs)
            # 根据取消事件状态发送不同的task_done消息
            data = (False, task_name, "CANCELLED") if self.app.cancel_current_task_event.is_set() else (True, task_name,
                                                                                                        result)
            self.app.message_queue.put(("task_done", data))
        except Exception as e:
            # 捕获任务执行中的任何异常，并发送错误消息到UI
            self.app.message_queue.put(("error", f"{_('任务执行出错')}: {e}\n{traceback.format_exc()}"))
        finally:
            self.app.message_queue.put(("progress", (100, _("任务完成。"))))  # 确保任务结束时进度到100%
            self.app.message_queue.put(("hide_progress_dialog", None))  # 确保最终关闭弹窗

    # --- 后台消息处理函数 (由 app.check_queue_periodic 调用) ---

    def _handle_startup_complete(self, data: dict):
        app = self.app

        self.app._log_to_viewer(_("应用程序启动完成。"), "INFO")
        # 确保 UI Manager 存在且 app.config_path_display_var 已初始化
        if self.app.ui_manager and hasattr(self.app, 'config_path_display_var'):
            self.app.ui_manager.update_ui_from_config()
        else:
            self.app.logger.warning(_("无法在启动时更新UI配置：UIManager或config_path_display_var未就绪。"))

        app.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")
        config_path_from_load = data.get("config_path")
        lang_code_to_set = 'zh-hans'
        if config_data:
            app.current_config = config_data
            app.config_path = config_path_from_load
            lang_code_to_set = app.current_config.i18n_language
            logger.info(_("默认配置文件加载成功。"))
        else:
            logger.warning(_("未找到或无法加载默认配置文件。"))
        app.ui_manager.update_ui_from_config()
        app.ui_manager.update_language_ui(lang_code_to_set)
        app.ui_manager.update_button_states()

    def _handle_startup_failed(self, data: str):
        self.app.ui_manager._hide_progress_dialog()
        self.app.ui_manager.show_error_message(_("启动错误"), str(data))
        self.app.ui_manager.update_button_states()

    def _handle_config_load_task_done(self, data: tuple):
        app = self.app
        # UI_Manager负责隐藏进度弹窗，这里不再直接调用
        # app.ui_manager._hide_progress_dialog()
        success, result_data, filepath = data
        if success:
            app.current_config = result_data
            app.config_path = os.path.abspath(filepath)
            app.ui_manager.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
            app.genome_sources_data = get_genome_data_sources(app.current_config, logger_func=logger.info)
            app.ui_manager.update_ui_from_config()
        else:
            app.ui_manager.show_error_message(_("加载失败"), str(result_data))

    def _handle_task_done(self, data: tuple):
        app = self.app
        success, task_display_name, result_data = data
        app.ui_manager._finalize_task_ui(task_display_name, success, result_data)

        if task_display_name in [_("数据下载"), _("预处理注释文件")]:
            if download_tab := app.tool_tab_instances.get('download'):
                if hasattr(download_tab, '_update_dynamic_widgets'):
                    selected_genome = download_tab.selected_genome_var.get()
                    app.after(10, lambda: download_tab._update_dynamic_widgets(selected_genome))
                    app.logger.info(_("数据下载选项卡状态已在任务完成后自动刷新。"))
        elif task_display_name == _("位点转换"):
            if success and result_data:
                self.app.ui_manager.show_info_message(_("转换成功"), result_data)
        elif "富集分析" in task_display_name and success and result_data:
            if hasattr(self.app.ui_manager, '_show_plot_results') and result_data:
                self.app.ui_manager._show_plot_results(result_data)

    def _handle_error(self, data: str):
        self.app.ui_manager.show_error_message(_("任务执行出错"), data)
        self.app.ui_manager._finalize_task_ui(self.app.active_task_name or _("未知任务"), success=False)

    def _handle_status(self, message: str):
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.latest_log_message_var.set(message)

    def _handle_progress(self, data: tuple):
        # data 是 (percentage, message)
        if self.app.ui_manager.progress_dialog and self.app.ui_manager.progress_dialog.winfo_exists():
            self.app.ui_manager.progress_dialog.update_progress(*data)

    def _handle_ai_models_fetched(self, data: tuple):
        provider_key, models_or_error = data
        if isinstance(models_or_error, list):
            self.app.ui_manager.update_ai_model_dropdown(provider_key, models_or_error)
            self.app.ui_manager.show_info_message(_("刷新成功"),
                                                  f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')}")
        else:
            self.app.ui_manager.update_ai_model_dropdown(provider_key, [])
            self.app.ui_manager.show_error_message(_("刷新失败"), str(models_or_error))

    def _handle_ai_test_result(self, data: tuple):
        success, message = data
        self.app.ui_manager.show_info_message(_("测试成功"),
                                              message) if success else self.app.ui_manager.show_error_message(
            _("测试失败"), message)

    def _handle_auto_identify_success(self, data: tuple):
        target_var, assembly_id = data
        if self.app.genome_sources_data and assembly_id in self.app.genome_sources_data and isinstance(target_var,
                                                                                                       tk.StringVar):
            target_var.set(assembly_id)

    def _handle_proxy_test_done(self, data: tuple):
        success, message = data
        if success:
            self.app.ui_manager.show_info_message(_("代理测试成功"), message)
        else:
            self.app.ui_manager.show_error_message(_("代理测试失败"), message)

    # --- 用户界面事件处理 ---

    def on_language_change(self, selected_display_name: str):
        """
        处理语言切换的核心逻辑。
        """
        app = self.app
        # 1. 从显示名称 (如 "English") 获取语言代码 (如 "en")
        new_lang_code = app.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")

        # 2. 更新 UI 设置字典 (而不是项目配置文件)
        app.ui_settings['language'] = new_lang_code

        # 3. 调用 UI 管理器的方法来保存 UI 设置 (到 ui_settings.json)
        app.ui_manager._save_ui_settings()

        # 4. 通知 UI 管理器使用新语言代码更新整个界面
        app.ui_manager.update_language_ui(new_lang_code)

    def change_appearance_mode_event(self, new_mode_display: str):
        app = self.app
        new_mode = {"浅色": "Light", "深色": "Dark", "系统": "System"}.get(new_mode_display, "System")
        app.ui_manager._set_ttk_theme_from_app_mode(new_mode)
        app.ui_settings['appearance_mode'] = new_mode
        app.ui_manager._save_ui_settings()
        app.ui_manager._update_log_tag_colors()

    def toggle_log_viewer(self):
        app = self.app
        app.log_viewer_visible = not app.log_viewer_visible
        if app.log_viewer_visible:
            app.log_textbox.grid()
        else:
            app.log_textbox.grid_remove()
        app.toggle_log_button.configure(text=_("隐藏日志") if app.log_viewer_visible else _("显示日志"))

    def clear_log_viewer(self):
        if hasattr(self.app, 'log_textbox'):
            self.app.log_textbox.configure(state="normal")
            self.app.log_textbox.delete("1.0", "end")
            self.app.log_textbox.configure(state="disabled")
            self.app._log_to_viewer(_("操作日志已清除。"), "INFO")

    def load_config_file(self, filepath: Optional[str] = None):
        if not filepath:
            filepath = filedialog.askopenfilename(title=_("选择配置文件"),
                                                  filetypes=[("YAML files", "*.yml *.yaml"),
                                                             ("All files", "*.*")])
            if not filepath:
                return

        # 发送消息到队列，让UI主线程显示进度弹窗
        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("加载中..."),
            "message": _("正在加载配置文件..."),
            "on_cancel": None  # 加载配置不允许取消
        }))
        threading.Thread(target=self._load_config_thread, args=(filepath,), daemon=True).start()

    def _load_config_thread(self, filepath: str):
        try:
            config_obj = load_config(os.path.abspath(filepath))
            self.app.message_queue.put(("config_load_task_done", (True, config_obj, filepath)))
        except Exception as e:
            self.app.message_queue.put(("config_load_task_done", (False, str(e), None)))
        finally:
            self.app.message_queue.put(("progress", (100, _("加载完成。"))))  # 确保加载结束时进度到100%
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _generate_default_configs_gui(self):
        if not (output_dir := filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))): return
        main_config_path = os.path.join(output_dir, "config.yml")
        if os.path.exists(main_config_path):
            dialog = MessageDialog(self.app, _("文件已存在"), _("配置文件 'config.yml' 已存在，是否覆盖?"), "question",
                                   [_("是"), _("否")])
            if dialog.wait_window() or dialog.result != _("是"):
                return

        # 显示进度弹窗，这里是生成文件，不需要取消按钮
        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("生成配置文件中..."),
            "message": _("正在生成默认配置文件，请稍候..."),
            "on_cancel": None
        }))

        threading.Thread(target=self._generate_default_configs_thread, args=(output_dir,), daemon=True).start()

    def _generate_default_configs_thread(self, output_dir: str):
        try:
            # 模拟进度，实际的 generate_default_config_files 没有进度回调
            self.app.message_queue.put(("progress", (20, _("正在生成主配置文件..."))))
            success, new_cfg_path, _d = generate_default_config_files(output_dir, overwrite=True)
            self.app.message_queue.put(("progress", (80, _("生成其他配置文件..."))))  # 模拟进度
            if success:
                self.app.message_queue.put(("progress", (100, _("配置文件生成完成。"))))
                # 成功后询问是否立即加载，这部分仍然在主线程处理，所以通过队列发送
                self.app.message_queue.put(
                    ("task_done", (True, _("生成默认配置"), {'action': 'load_new_config', 'path': new_cfg_path})))
                # 这里发送一个特殊的 task_done 消息，让 UI 知道后续要弹窗询问
            else:
                self.app.message_queue.put(("error", _("生成默认配置文件失败。")))
        except Exception as e:
            self.app.message_queue.put(("error", f"{_('生成默认配置文件时发生错误:')} {e}\n{traceback.format_exc()}"))
        finally:
            self.app.message_queue.put(("hide_progress_dialog", None))

    def _handle_generate_default_configs_done(self, data: tuple):
        # 这个新的处理函数用于在生成配置完成后，根据 _generate_default_configs_thread 的结果，
        # 在主线程中显示询问弹窗。
        success, task_display_name, result_data = data
        if success and result_data and result_data.get('action') == 'load_new_config':
            new_cfg_path = result_data['path']
            dialog = MessageDialog(self.app, _("生成成功"),
                                   f"{_('默认配置文件已成功生成。')}\n\n{_('是否立即加载?')}", "info",
                                   [_("是"), _("否")])
            if dialog.wait_window() or dialog.result == _("是"):
                self.load_config_file(filepath=new_cfg_path)
        elif not success:
            # error 消息会通过 _handle_error 处理，所以这里不需要重复显示错误
            pass

    def _show_about_window(self):
        if hasattr(self.app, 'about_window') and self.app.about_window.winfo_exists():
            self.app.about_window.focus()
            return

        self.app.about_window = about_window = ttkb.Toplevel(self.app)
        about_window.title(_("关于 FCGT"))
        about_window.geometry("850x700")
        about_window.transient(self.app)
        about_window.grab_set()

        # 使用 ttkb.Frame 作为 Canvas 的直接父容器，方便布局和样式继承
        # 主框架，包含 Canvas 和 Scrollbar
        main_content_frame = ttkb.Frame(about_window)
        main_content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_content_frame.grid_columnconfigure(0, weight=1)
        main_content_frame.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(main_content_frame, highlightthickness=0, bd=0,
                           background=self.app.style.lookup('TFrame', 'background'))
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttkb.Scrollbar(main_content_frame, orient="vertical", command=canvas.yview, bootstyle="round")
        scrollbar.grid(row=0, column=1, sticky="ns")

        canvas.configure(yscrollcommand=scrollbar.set)

        # 实际内容将放置在这个 Frame 中，它在 Canvas 上
        scrollable_content_frame = ttkb.Frame(canvas)
        # 将这个 Frame 放到 Canvas 上
        canvas_window_id = canvas.create_window((0, 0), window=scrollable_content_frame, anchor="nw",
                                                width=canvas.winfo_width())

        # 绑定事件以调整滚动区域和Canvas内部窗口的宽度
        def _on_frame_configure(event):
            # 更新Canvas的滚动区域以匹配内部Frame的大小
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 确保内部Frame的宽度与Canvas的宽度一致
            canvas.itemconfig(canvas_window_id, width=canvas.winfo_width())

        def _on_canvas_resize(event):
            # 当Canvas大小改变时，调整内部Frame的宽度
            canvas.itemconfig(canvas_window_id, width=event.width)
            # 重新配置滚动区域
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_content_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_resize)  # Bind to canvas resize

        # Mouse wheel binding for the canvas (Windows/macOS)
        def _on_mousewheel(event):
            if event.num == 5 or event.delta == -120:  # Scroll down
                canvas.yview_scroll(1, "units")
            if event.num == 4 or event.delta == 120:  # Scroll up
                canvas.yview_scroll(-1, "units")
            return "break"  # Prevent event propagation

        canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        canvas.bind_all("<Button-4>", _on_mousewheel, add="+")  # Linux scroll up
        canvas.bind_all("<Button-5>", _on_mousewheel, add="+")  # Linux scroll down

        scrollable_content_frame.grid_columnconfigure(0, weight=1)

        # --- Header Section (Logo, Title, Version, License) ---
        header_frame = ttkb.Frame(scrollable_content_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        if logo := self.app.ui_manager.icon_cache.get("logo"):
            ttkb.Label(header_frame, image=logo).pack(side="left", padx=(0, 15))

        title_version_frame = ttkb.Frame(header_frame)
        title_version_frame.pack(side="left", fill="x", expand=True)

        ttkb.Label(title_version_frame, text=_("友好棉花基因组工具包 (FCGT)"), font=self.app.app_title_font).pack(
            anchor="w")
        ttkb.Label(title_version_frame, text=f"Version: {PKG_VERSION}", bootstyle="secondary").pack(anchor="w")
        ttkb.Label(title_version_frame, text=_('本软件遵守 Apache-2.0 license 开源协议'), bootstyle="secondary").pack(
            anchor="w")

        # --- About Text Widget (tk.Text for rich formatting) ---
        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        link_color = self.app.style.colors.info

        about_text_widget = tk.Text(scrollable_content_frame,
                                    wrap="word", relief="flat",
                                    background=text_bg, foreground=text_fg, insertbackground=text_fg,
                                    font=self.app.app_font,
                                    height=25,  # Set a reasonable initial height for visibility
                                    borderwidth=0, highlightthickness=0)
        about_text_widget.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")  # Make it expandable

        # Configure tags for various styles
        about_text_widget.tag_configure("h3", font=self.app.app_font_bold, foreground=self.app.style.colors.primary,
                                        spacing3=10)
        about_text_widget.tag_configure("h4", font=self.app.app_font_bold, spacing3=5)
        about_text_widget.tag_configure("bold", font=self.app.app_font_bold)
        about_text_widget.tag_configure("link", foreground=link_color, underline=1)

        # Link callback function
        def _open_github_link(event):
            webbrowser.open_new(PKG_PUBLISH_URL)

        about_text_widget.tag_bind("link", "<Button-1>", _open_github_link)
        about_text_widget.tag_bind("link", "<Enter>", lambda e: about_text_widget.config(cursor="hand2"))
        about_text_widget.tag_bind("link", "<Leave>", lambda e: about_text_widget.config(cursor=""))
        about_text_widget.tag_configure("list", lmargin1=20, lmargin2=40, spacing1=5)
        about_text_widget.tag_configure("bullet", offset=-5)  # For bullet point indent

        # Make widget editable to insert text
        about_text_widget.config(state="normal")

        # --- Populate Text Widget ---
        about_text_widget.insert(tk.END, "FCGT (Friendly Cotton Genomes Toolkit)", "bold")
        about_text_widget.insert(tk.END, _(" 是一款专为棉花研究者，特别是"), "")
        about_text_widget.insert(tk.END, _("非生物信息专业背景"), "bold")
        about_text_widget.insert(tk.END,
                                 _("的科研人员和学生设计的基因组数据分析工具箱。我们致力于将复杂的数据处理流程封装在简洁的图形界面（GUI）和命令行（CLI）背后，让您无需进行繁琐的环境配置和代码编写，即可"),
                                 "")
        about_text_widget.insert(tk.END, _("开箱即用"), "bold")
        about_text_widget.insert(tk.END, "。\n\n", "")

        about_text_widget.insert(tk.END,
                                 _("本工具包提供了一系列强大的棉花基因组数据处理工具，包括多版本间的同源基因映射（Liftover）、基因功能注释、基因位点查询、富集分析、AI助手批量处理数据等。它旨在成为您日常科研工作中不可或缺的得力助手。\n\n"),
                                 "")

        # --- Core Features and Highlights ---
        about_text_widget.insert(tk.END, _("核心亮点与功能\n"), "h3")
        about_text_widget.insert(tk.END, "• ", "bullet")
        about_text_widget.insert(tk.END, _("极致友好，开箱即用"), "bold")
        about_text_widget.insert(tk.END, _(": 图形界面优先，无需复杂配置，多语言支持。\n"), "")
        about_text_widget.insert(tk.END, "• ", "bullet")
        about_text_widget.insert(tk.END, _("高效的自动化与批量处理"), "bold")
        about_text_widget.insert(tk.END, _(": 多线程加速，命令行支持。\n"), "")
        about_text_widget.insert(tk.END, "• ", "bullet")
        about_text_widget.insert(tk.END, _("精准的基因组工具集"), "bold")
        about_text_widget.insert(tk.END, _(": 棉花版 Liftover，一站式数据工具，标准化数据下载。\n"), "")
        about_text_widget.insert(tk.END, "• ", "bullet")
        about_text_widget.insert(tk.END, _("跨平台，随处可用"), "bold")
        about_text_widget.insert(tk.END, _(": 为Windows提供预编译可执行文件。\n\n"), "")

        about_text_widget.insert(tk.END, _("项目开源地址：\n"), "")
        about_text_widget.insert(tk.END, PKG_PUBLISH_URL, "link")  # Display the URL and make it clickable
        about_text_widget.insert(tk.END, _("\n此软件由 Gemini AI 协助开发，功能持续迭代，欢迎学术交流和贡献。\n\n"), "")

        # --- Data Sources & Citations ---
        about_text_widget.insert(tk.END, _("数据来源与引文\n"), "h3")
        about_text_widget.insert(tk.END, _("本工具依赖 CottonGen 提供的权威数据，感谢其团队持续的开放和维护。\n\n"), "")

        about_text_widget.insert(tk.END, _("CottonGen 文章\n"), "h4")
        about_text_widget.insert(tk.END,
                                 "• Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. Plants 10(12), 2805.\n",
                                 "")
        about_text_widget.insert(tk.END,
                                 "• Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. Nucleic Acids Research 42(D1), D1229-D1236.\n\n",
                                 "")

        about_text_widget.insert(tk.END, _("基因组引用文献\n"), "h4")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "NAU-NBI_v1.1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "UTX-JGI-Interim-release_v1.1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].\n  Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .\n  Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.\n  Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "HAU_v1 / v1.1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "ZJU-improved_v2.1_a1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. Nature genetics. 2019 Jan;51(1):164.\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "CRI_v1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "WHU_v1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "UTX_v2.1: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.\n\n",
                                 "")
        about_text_widget.insert(tk.END, "• ", "")
        about_text_widget.insert(tk.END, "HAU_v2.0: ", "bold")
        about_text_widget.insert(tk.END,
                                 "Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. \"High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres.\" Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722\n\n",
                                 "")

        # --- Acknowledgements ---
        about_text_widget.insert(tk.END, _("致谢与许可\n"), "h3")
        about_text_widget.insert(tk.END, _("感谢所有为本项目提供数据、算法和灵感的科研人员与开源社区。\n"), "")

        # Set text widget to disabled (read-only)
        about_text_widget.config(state="disabled")

        # --- Close Button ---
        # Position this button at the bottom of the main_content_frame
        close_button_frame = ttkb.Frame(main_content_frame)
        close_button_frame.grid(row=1, column=0, columnspan=2, pady=10)  # row 1 is below canvas+scrollbar
        close_button_frame.grid_columnconfigure(0, weight=1)

        ttkb.Button(close_button_frame, text=_("关闭"), command=about_window.destroy, bootstyle='info').grid(row=0,
                                                                                                             column=0,
                                                                                                             pady=5)

        about_window.update_idletasks()
        self.app.update_idletasks()
        main_x = self.app.winfo_x()
        main_y = self.app.winfo_y()
        main_width = self.app.winfo_width()
        main_height = self.app.winfo_height()

        about_width = about_window.winfo_width()
        about_height = about_window.winfo_height()

        x_pos = main_x + (main_width // 2) - (about_width // 2)
        y_pos = main_y + (main_height // 2) - (about_height // 2)

        about_window.geometry(f"+{x_pos}+{y_pos}")

    def _open_online_help(self):
        try:
            webbrowser.open(PKG_HELP_URL)
        except Exception as e:
            self.app.ui_manager.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))

    def _browse_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        """打开文件浏览对话框并更新Entry widget."""
        if filepath := filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)

    def _browse_save_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        """打开保存文件对话框并更新Entry widget."""
        if filepath := filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                    defaultextension=filetypes_list[0][1].replace("*", "")):
            entry_widget.delete(0, "end");
            entry_widget.insert(0, filepath)

    def _browse_directory(self, entry_widget: ttkb.Entry):
        """打开目录浏览对话框并更新Entry widget."""
        if directory_path := filedialog.askdirectory(title=_("选择目录")):
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory_path)

    def _auto_identify_genome_version(self, gene_input_textbox: tk.Text, target_assembly_var: tk.StringVar):
        current_text = gene_input_textbox.get("1.0", "end").strip()
        if not current_text or current_text in self.app.placeholders.values(): return
        gene_ids = [g.strip() for g in current_text.replace(",", "\n").splitlines() if g.strip()]
        if not gene_ids or not self.app.genome_sources_data: return
        threading.Thread(target=self._identify_genome_thread, args=(gene_ids, target_assembly_var), daemon=True).start()

    def _identify_genome_thread(self, gene_ids, target_assembly_var):
        try:
            if assembly_id := identify_genome_from_gene_ids(gene_ids, self.app.genome_sources_data):
                self.app.message_queue.put(("auto_identify_success", (target_assembly_var, assembly_id)))
        except Exception as e:
            logger.error(f"自动识别基因组时发生错误: {e}")

    def test_proxy_connection(self):
        app = self.app
        http_proxy = app.proxy_http_entry.get().strip()
        https_proxy = app.proxy_https_entry.get().strip()
        if not http_proxy and not https_proxy:
            app.ui_manager.show_info_message(_("信息"), _("请先填写HTTP或HTTPS代理地址。"))
            return
        proxies = {k: v for k, v in {'http': http_proxy, 'https': https_proxy}.items() if v}

        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("正在测试代理..."),
            "message": _("尝试通过代理连接到测试站点..."),
            "on_cancel": None
        }))
        threading.Thread(target=self._test_proxy_thread, args=(proxies,), daemon=True).start()

    def _test_proxy_thread(self, proxies: dict):
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
        app.logger.info(f"正在获取 '{provider_key}' 的模型列表... (使用代理: {use_proxy})")
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                f"{_('任务')} '{app.active_task_name}' {_('正在运行。')}")
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

        self.app.message_queue.put(("show_progress_dialog", {
            "title": _("正在获取模型..."),
            "message": _("连接到 {}...").format(provider_key),
            "on_cancel": app.cancel_current_task_event.set
        }))

        thread_kwargs = {'provider': provider_key, 'api_key': api_key, 'base_url': base_url, 'proxies': proxies,
                         'cancel_event': app.cancel_current_task_event,
                         'progress_callback': self.gui_progress_callback}  # 传递进度回调
        threading.Thread(target=self._fetch_models_thread, kwargs=thread_kwargs, daemon=True).start()

    def _fetch_models_thread(self, **kwargs):
        provider = kwargs.get('provider')
        cancel_event = kwargs.get('cancel_event')
        progress = kwargs.get('progress_callback', lambda p, m: None)  # 获取进度回调
        try:
            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")));
                return

            progress(10, _("开始连接AI服务..."))
            models = AIWrapper.get_models(
                provider=kwargs.get('provider'),
                api_key=kwargs.get('api_key'),
                base_url=kwargs.get('base_url'),
                proxies=kwargs.get('proxies'),
                progress_callback=lambda p, m: progress(10 + int(p * 0.8), m),  # 10%-90%
                cancel_event=cancel_event
            )

            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")))
            else:
                self.app.message_queue.put(("ai_models_fetched", (provider, models)))
                progress(90, _("数据处理中..."))  # 模拟处理完成前的进度
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