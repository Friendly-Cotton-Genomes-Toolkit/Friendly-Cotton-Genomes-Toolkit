import json
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
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.pipelines import run_preprocess_annotation_files
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
        # 【核心修改2】在这里注册新的消息处理器
        return {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "hide_progress_dialog": self.app.ui_manager._hide_progress_dialog,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_test_result": self._handle_ai_test_result,
            "auto_identify_success": self._handle_auto_identify_success,
            "proxy_test_done": self._handle_proxy_test_done,
            "csv_columns_fetched": self._handle_csv_columns_fetched, # 新增的处理器
        }

    # --- 【核心修改】添加回遗漏的启动函数 ---
    def start_app_async_startup(self):
        """启动应用的异步加载流程。"""
        self.app.ui_manager._show_progress_dialog(title=_("图形界面启动中..."),
                                                  message=_("正在初始化应用程序和加载配置，请稍候..."))
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """后台加载线程。"""
        app = self.app
        try:
            loaded_config, genome_sources, config_path_to_send = None, None, None
            if os.path.exists(default_config_path := "config.yml"):
                app.message_queue.put(("progress", (10, _("加载配置文件..."))))
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)
            if loaded_config:
                app.message_queue.put(("progress", (30, _("加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config, logger_func=logger.info)
            startup_data = {"config": loaded_config, "genome_sources": genome_sources,
                            "config_path": config_path_to_send}
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            app.message_queue.put(("startup_failed", f"{_('应用启动失败')}: {e}\n{traceback.format_exc()}"))
        finally:
            app.message_queue.put(("hide_progress_dialog", None))

    # ------------------------------------------

    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any]):
        app = self.app
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"),
                                                f"{_('任务')} '{app.active_task_name}' {_('正在运行。')}")
            return
        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        app.cancel_current_task_event.clear()
        app.ui_manager._show_progress_dialog(title=task_name, message=_("正在处理..."),
                                             on_cancel=app.cancel_current_task_event.set)
        kwargs.update({'cancel_event': app.cancel_current_task_event, 'status_callback': self.gui_status_callback,
                       'progress_callback': self.gui_progress_callback})
        threading.Thread(target=self._task_wrapper, args=(target_func, kwargs, task_name), daemon=True).start()

    def _task_wrapper(self, target_func, kwargs, task_name):
        try:
            result = target_func(**kwargs)
            data = (False, task_name, "CANCELLED") if self.app.cancel_current_task_event.is_set() else (True, task_name,
                                                                                                        result)
            self.app.message_queue.put(("task_done", data))
        except Exception as e:
            self.app.message_queue.put(("error", f"{_('任务执行出错')}: {e}\n{traceback.format_exc()}"))

    # --- 后台消息处理 ---

    def _handle_startup_complete(self, data: dict):
        app = self.app
        app.ui_manager._hide_progress_dialog()
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
        app.ui_manager._hide_progress_dialog()
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
                    download_tab._update_dynamic_widgets(selected_genome)
                    app.logger.info("数据下载选项卡状态已在任务完成后自动刷新。")

        elif task_display_name == _("位点转换"):
            if success and result_data:
                self.app.ui_manager.show_info_message(_("转换成功"), result_data)

        elif "富集分析" in task_display_name and success and result_data:
            app.ui_manager._show_plot_results(result_data)

    def _handle_error(self, data: str):
        self.app.ui_manager.show_error_message(_("任务执行出错"), data)
        self.app.ui_manager._finalize_task_ui(self.app.active_task_name or _("未知任务"), success=False)

    def _handle_status(self, data: str):
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.status_label.configure(text=str(data)[:150])

    def _handle_progress(self, data: tuple):
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
    def on_closing(self):
        dialog = MessageDialog(self.app, _("退出程序"), _("您确定要退出吗?"), "question", [_("确定"), _("取消")])
        if dialog.wait_window() or dialog.result == _("确定"):
            self.app.destroy()

    def on_language_change(self, selected_display_name: str):
        app = self.app
        new_lang_code = app.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")
        if app.current_config and app.config_path:
            app.current_config.i18n_language = new_lang_code
            try:
                save_config(app.current_config, app.config_path)
            except Exception as e:
                app.ui_manager.show_error_message(_("保存失败"), _("无法保存语言设置: {}").format(e))
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
        app.log_textbox.grid() if app.log_viewer_visible else app.log_textbox.grid_remove()
        app.toggle_log_button.configure(text=_("隐藏日志") if app.log_viewer_visible else _("显示日志"))

    def clear_log_viewer(self):
        if hasattr(self.app, 'log_textbox'):
            self.app.log_textbox.configure(state="normal");
            self.app.log_textbox.delete("1.0", "end");
            self.app.log_textbox.configure(state="disabled")

    def load_config_file(self, filepath: Optional[str] = None):
        if not filepath and not (filepath := filedialog.askopenfilename(title=_("选择配置文件"),
                                                                        filetypes=[("YAML files", "*.yml *.yaml"),
                                                                                   ("All files", "*.*")])):
            return
        self.app.ui_manager._show_progress_dialog(title=_("加载中..."), message=_("正在加载配置文件..."))
        threading.Thread(target=self._load_config_thread, args=(filepath,), daemon=True).start()

    def _load_config_thread(self, filepath: str):
        try:
            self.app.message_queue.put(
                ("config_load_task_done", (True, load_config(os.path.abspath(filepath)), filepath)))
        except Exception as e:
            self.app.message_queue.put(("config_load_task_done", (False, str(e), None)))

    def _generate_default_configs_gui(self):
        if not (output_dir := filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))): return
        main_config_path = os.path.join(output_dir, "config.yml")
        if os.path.exists(main_config_path):
            dialog = MessageDialog(self.app, _("文件已存在"), _("配置文件 'config.yml' 已存在，是否覆盖?"), "question",
                                   [_("是"), _("否")])
            if dialog.wait_window() or dialog.result != _("是"): return
        try:
            success, new_cfg_path, _d = generate_default_config_files(output_dir, overwrite=True)
            if success:
                dialog = MessageDialog(self.app, _("生成成功"),
                                       f"{_('默认配置文件已成功生成。')}\n\n{_('是否立即加载?')}", "info",
                                       [_("是"), _("否")])
                if dialog.wait_window() or dialog.result == _("是"): self.load_config_file(filepath=new_cfg_path)
        except Exception as e:
            self.app.ui_manager.show_error_message(_("生成错误"), f"{_('生成默认配置文件时发生错误:')} {e}")

    def _show_about_window(self):
        if hasattr(self.app, 'about_window') and self.app.about_window.winfo_exists():
            self.app.about_window.focus();
            return
        self.app.about_window = about_window = ttkb.Toplevel(self.app)
        about_window.title(_("关于 FCGT"));
        about_window.geometry("850x700");
        about_window.transient(self.app);
        about_window.grab_set()
        canvas = tk.Canvas(about_window, highlightthickness=0, background=self.app.style.lookup('TFrame', 'background'))
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar = ttkb.Scrollbar(about_window, orient="vertical", command=canvas.yview, bootstyle="round");
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollable_frame = ttkb.Frame(canvas);
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"), width=event.width)

        scrollable_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        scrollable_frame.grid_columnconfigure(0, weight=1)
        header_frame = ttkb.Frame(scrollable_frame);
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        if logo := self.app.ui_manager.icon_cache.get("logo"): ttkb.Label(header_frame, image=logo).pack(side="left",
                                                                                                         padx=(0, 15))
        title_frame = ttkb.Frame(header_frame);
        title_frame.pack(side="left", fill="x", expand=True)
        ttkb.Label(title_frame, text=_("友好棉花基因组工具包 (FCGT)"), font=self.app.app_title_font).pack(anchor="w")
        ttkb.Label(title_frame, text=f"Version: {PKG_VERSION}", bootstyle="secondary").pack(anchor="w")
        ttkb.Label(title_frame, text=_('本软件遵守 Apache-2.0 license 开源协议'), bootstyle="secondary").pack(
            anchor="w")
        ttkb.Button(scrollable_frame, text=_("关闭"), command=about_window.destroy, bootstyle='info').grid(pady=30)

    def _open_online_help(self):
        try:
            webbrowser.open(PKG_HELP_URL)
        except Exception as e:
            self.app.ui_manager.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))

    def _browse_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        if filepath := filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)

    def _browse_save_file(self, entry_widget: ttkb.Entry, filetypes_list: list):
        if filepath := filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                    defaultextension=filetypes_list[0][1].replace("*", "")):
            entry_widget.delete(0, "end");
            entry_widget.insert(0, filepath)

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
        app.ui_manager._show_progress_dialog(title=_("正在测试代理..."), message=_("尝试通过代理连接到测试站点..."))
        threading.Thread(target=self._test_proxy_thread, args=(proxies,), daemon=True).start()

    def _test_proxy_thread(self, proxies: dict):
        test_url = "https://httpbin.org/get"
        try:
            response = requests.get(test_url, proxies=proxies, timeout=15)
            response.raise_for_status()
            origin_ip = response.json().get('origin', 'N/A')
            message = f"{_('连接成功！')}\n{_('测试站点报告的IP地址是:')} {origin_ip}"
            self.app.message_queue.put(("proxy_test_done", (True, message)))
        except requests.exceptions.RequestException as e:
            self.app.message_queue.put(("proxy_test_done", (False, f"{_('连接失败。')}\n{_('错误详情:')} {e}")))
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
        app.ui_manager._show_progress_dialog(title=_("正在获取模型..."), message=_("连接到 {}...").format(provider_key),
                                             on_cancel=app.cancel_current_task_event.set)
        thread_kwargs = {'provider': provider_key, 'api_key': api_key, 'base_url': base_url, 'proxies': proxies,
                         'cancel_event': app.cancel_current_task_event}
        threading.Thread(target=self._fetch_models_thread, kwargs=thread_kwargs, daemon=True).start()

    def _fetch_models_thread(self, **kwargs):
        provider = kwargs.get('provider')
        cancel_event = kwargs.get('cancel_event')
        try:
            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")));
                return
            models = AIWrapper.get_models(**kwargs)
            if cancel_event and cancel_event.is_set():
                self.app.message_queue.put(("ai_models_fetched", (provider, "CANCELLED")))
            else:
                self.app.message_queue.put(("ai_models_fetched", (provider, models)))
        except Exception as e:
            if not (cancel_event and cancel_event.is_set()):
                self.app.message_queue.put(("ai_models_fetched", (provider, str(e))))
        finally:
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
        """处理从后台线程获取到的CSV列名。"""
        columns, error_msg = data
        # 从app实例中安全地获取AI助手选项卡
        if ai_tab := self.app.tool_tab_instances.get('ai_assistant'):
            # 调用AI助手选项卡自己的UI更新方法
            ai_tab.update_column_dropdown_ui(columns, error_msg)
        else:
            logger.warning("无法找到AI助手选项卡实例来更新列名。")


