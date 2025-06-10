# gui_app.py
import copy
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import asdict
from queue import Queue
from tkinter import filedialog, font as tkfont
from typing import Callable, Dict, Optional, Any, Tuple

import customtkinter as ctk
import pandas as pd
import yaml
from PIL import Image

from cotton_toolkit.config.models import MainConfig, GenomeSourcesConfig

try:
    from cotton_toolkit.tools_pipeline import run_functional_annotation, run_ai_task, AIWrapper
    from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
        get_genome_data_sources
    from cotton_toolkit.core.downloader import download_genome_data
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg, run_homology_mapping_standalone, \
        run_gff_gene_lookup_standalone
    from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text
    from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL

    COTTON_TOOLKIT_LOADED = True
    print("INFO: gui_app.py - Successfully imported COTTON_TOOLKIT modules.")  #
except ImportError as e:
    print(f"错误：无法导入 cotton_toolkit 模块 (gui_app.py): {e}")  #
    COTTON_TOOLKIT_LOADED = False  #
    PKG_VERSION = "DEV"
    PKG_HELP_URL = "https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/docs/HELP.md"  #


    def load_config(config_path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(config_path):
            print(f"ERROR: 配置文件 '{config_path}' 未找到。")  # Changed to f-string for clarity
            return None
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                print(f"ERROR: 配置文件 '{config_path}' 的顶层结构必须是一个字典。")
                return None

            if data.get('config_version') != 1:
                # 使用 print 明确指出版本不兼容问题
                print(f"ERROR: 配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")
                raise ValueError(f"配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")

            # 将字典转换为 MainConfig 对象 (如果 COTTON_TOOLKIT_LOADED 为 True)
            if COTTON_TOOLKIT_LOADED:  # Ensure this check exists if it's a mock
                config_obj = MainConfig.from_dict(data)  #
            else:
                config_obj = data  # For mock, just return the dict

            # 确保 _config_file_abs_path_ 字段在返回前设置
            if isinstance(config_obj, MainConfig):
                config_obj._config_file_abs_path_ = os.path.abspath(config_path)
            elif isinstance(config_obj, dict):  # For mock scenario
                config_obj['_config_file_abs_path_'] = os.path.abspath(config_path)

            print(f"INFO: 配置文件 '{config_path}' 加载成功。")
            return config_obj
        except yaml.YAMLError as e:
            print(f"ERROR: 解析配置文件 '{config_path}' 失败: {e}")
            return None
        except ValueError as e:
            # 重新抛出版本错误，让调用者可以捕获
            raise e
        except Exception as e:
            print(f"ERROR: 加载配置文件 '{config_path}' 时发生未知错误: {e}")
            return None


    def save_config_to_yaml(config_dict, file_path):
        print(f"MOCK (gui_app.py): save_config_to_yaml({file_path})")  #
        with open(file_path, 'w', encoding='utf-8') as f: yaml.dump(config_dict, f)  #
        return True  #


    # cotton_toolkit/config/loader.py

    def get_genome_data_sources(main_config: MainConfig) -> Optional[Dict[str, Any]]:
        """从主配置对象中获取或加载基因组数据源。"""

        # 【修复】直接通过属性访问，而不是 .get() 方法，这更安全和规范
        downloader_cfg = main_config.downloader
        if not downloader_cfg:
            print(_("错误: 配置对象不完整，缺少 'downloader' 部分。"))
            return None

        # 【修复】直接通过属性访问
        gs_file_rel = downloader_cfg.genome_sources_file
        if not gs_file_rel:
            print(_("错误: 主配置的 'downloader' 部分缺少 'genome_sources_file' 定义。"))
            return None

        main_config_dir = os.path.dirname(
            main_config._config_file_abs_path_) if main_config._config_file_abs_path_ else os.getcwd()
        gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

        if not os.path.exists(gs_file_path_abs):
            print(_("错误: 基因组源文件 '{}' 未找到。").format(gs_file_path_abs))
            return None

        try:
            with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data.get('list_version') != 1:
                print(_("错误: 基因组源文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(gs_file_path_abs))
                return None

            gs_config = GenomeSourcesConfig.from_dict(data)
            return {k: asdict(v) for k, v in gs_config.genome_sources.items()}
        except Exception as e:
            print(_("错误: 加载或解析基因组源文件 '{}' 失败: {}").format(gs_file_path_abs, e))
            return None


    def generate_default_config_files(
            output_dir: str,
            main_config_filename: str = "config.yml",
            genome_sources_filename: str = "genome_sources_list.yml",
            overwrite: bool = False
    ) -> Tuple[bool, str, str]:
        """通过实例化配置类来生成默认的配置文件，并支持覆盖选项。"""
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                print(_("错误: 创建目录 '{}' 失败: {}").format(output_dir, e))
                return False, "", ""

        main_config_path = os.path.join(output_dir, main_config_filename)
        genome_sources_path = os.path.join(output_dir, genome_sources_filename)

        success_main = False
        success_gs = False

        # 生成主配置文件，增加覆盖判断
        if os.path.exists(main_config_path) and not overwrite:
            print(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_path))
            success_main = True
        else:
            main_conf_default = MainConfig()
            main_conf_default.downloader.genome_sources_file = genome_sources_filename
            success_main = save_config(main_conf_default, main_config_path)

        # 生成基因组源文件，增加覆盖判断
        if os.path.exists(genome_sources_path) and not overwrite:
            print(_("警告: 基因组源文件 '{}' 已存在，跳过生成。").format(genome_sources_path))
            success_gs = True
        else:
            gs_conf_default = GenomeSourcesConfig()
            success_gs = save_config(gs_conf_default, genome_sources_path)

        return success_main and success_gs, main_config_path, genome_sources_path


    def download_genome_data(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("下载")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.DOWNLOAD_TASK_KEY, True, task_display_name)  #


    def integrate_bsa_with_hvg(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("整合分析")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.INTEGRATE_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_homology_mapping_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("同源映射")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.HOMOLOGY_MAP_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_gff_gene_lookup_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("GFF基因查询")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.GFF_QUERY_TASK_KEY, True, task_display_name)  #
        return True  #


    def setup_cli_i18n(language_code='en', app_name='cotton_toolkit'):  #
        return lambda s: str(s) + f" (mock_{language_code})"  #

# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}

    # --- AI服务商及其元数据 ---
    AI_PROVIDERS = {
        "google": {"name": "Google Gemini"},
        "openai": {"name": "OpenAI"},
        "deepseek": {"name": "DeepSeek (月之暗面)"},
        "qwen": {"name": "Qwen (通义千问)"},
        "siliconflow": {"name": "SiliconFlow (硅基流动)"},
        "grok": {"name": "Grok (xAI)"},  # <--- 在此添加
        "openai_compatible": {"name": _("通用OpenAI兼容接口")}
    }

    def __init__(self):
        super().__init__()

        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1000x700")
        self.minsize(1000, 700)

        # --- 【第1步】初始化所有变量，为后续方法做准备 ---
        self.log_queue = queue.Queue()
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.ui_settings: Dict[str, Any] = {}
        self.message_queue: Queue = Queue()
        self.about_window: Optional[ctk.CTkToplevel] = None
        self.translatable_widgets: Dict[ctk.CTkBaseClass, Any] = {}
        self.active_task_name: Optional[str] = None
        self.log_viewer_visible: bool = False
        self.error_dialog_lock: threading.Lock = threading.Lock()
        self.tool_tab_frames: Dict[str, ctk.CTkFrame] = {}

        # 记录每个工具选项卡是否已加载其UI
        self.tool_tab_ui_loaded: Dict[str, bool] = {}  #

        self.tab_keys: Dict[str, str] = {
            "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
            "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
        }

        # 标记配置编辑器UI是否已加载
        self.editor_ui_loaded: bool = False  #

        # 用于取消模型获取的事件和进度弹窗
        self.cancel_model_fetch_event: threading.Event = threading.Event()
        self.progress_dialog: Optional[ctk.CTkToplevel] = None
        self.progress_dialog_text_var: Optional[tk.StringVar] = None
        self.progress_dialog_bar: Optional[ctk.CTkProgressBar] = None

        self.excel_sheet_cache = {}  # 新增：用于缓存Excel文件的工作表名称，避免重复读取

        self.placeholder_genes_homology_key: str = "例如:\nGhir.A01G000100\nGhir.A01G000200\n(每行一个基因ID，或逗号分隔)"
        self.placeholder_genes_gff_key: str = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(每行一个基因ID，与下方区域查询二选一)"

        self.DOWNLOAD_TASK_KEY = "download"
        self.INTEGRATE_TASK_KEY = "integrate"
        self.HOMOLOGY_MAP_TASK_KEY = "homology_map"
        self.GFF_QUERY_TASK_KEY = "gff_query"

        # 初始化 Tkinter 变量
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.ai_task_type_var = tk.StringVar(value=_("翻译"))
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=False)
        self.kegg_path_anno_var = tk.BooleanVar(value=False)
        self.selected_bsa_assembly = tk.StringVar()
        self.selected_hvg_assembly = tk.StringVar()
        self.selected_bsa_sheet = tk.StringVar()
        self.selected_hvg_sheet = tk.StringVar()
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.selected_gff_query_assembly = tk.StringVar()
        self.download_force_checkbox_var = tk.BooleanVar()
        self.download_genome_vars: Dict[str, tk.BooleanVar] = {}
        self.download_proxy_var = tk.BooleanVar(value=False)
        self.ai_proxy_var = tk.BooleanVar(value=False)

        # --- 【第2步】设置字体，因为后续创建UI都需要它 ---
        self._setup_fonts()

        # --- 【第3步】设置颜色变量和加载图标 ---
        self.secondary_text_color = ("#495057", "#999999")
        self.placeholder_color = ("#868e96", "#5c5c5c")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]
        try:
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        except Exception:
            self.default_label_text_color = ("#000000", "#FFFFFF")

        self.logo_image = self._load_image_resource("logo.png", (48, 48))
        self.home_icon = self._load_image_resource("home.png")
        self.integrate_icon = self._load_image_resource("integrate.png")
        self.tools_icon = self._load_image_resource("tools.png")
        self.settings_icon = self._load_image_resource("settings.png")
        self.folder_icon = self._load_image_resource("folder.png")
        self.new_file_icon = self._load_image_resource("new-file.png")
        self.help_icon = self._load_image_resource("help.png")
        self.info_icon = self._load_image_resource("info.png")

        # --- 【第4步】加载UI设置（如主题），这会影响控件外观 ---
        self._load_ui_settings()

        # --- 【第5步】创建基础UI布局（如状态栏、日志区、导航栏）---
        self._create_layout()

        # --- 【第6步】最后，创建并填充所有主页面，并完成最终设置 ---
        self._init_pages_and_final_setup()

        self._start_app_async_startup()

    def toggle_log_viewer(self):
        """切换日志文本框的可见性。"""
        if self.log_viewer_visible:
            # 当前可见，则隐藏
            self.log_textbox.grid_remove()
            self.toggle_log_button.configure(text=_("显示日志"))
            self.log_viewer_visible = False
        else:
            # 当前隐藏，则显示
            self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
            self.toggle_log_button.configure(text=_("隐藏日志"))
            self.log_viewer_visible = True

    # 在 CottonToolkitApp class 内部
    def _fetch_ai_models(self, provider_key: str):
        """
        直接从静态UI输入框获取API Key和URL来刷新模型列表。
        """
        self._log_to_viewer(
            f"{_('正在获取')} '{self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)}' {_('的模型列表...')} ")

        api_key = ""
        base_url = None  # 默认为None，让AIWrapper处理

        # 新的静态方式：根据 provider_key 直接访问对应控件
        try:
            if provider_key == "google":
                api_key = self.ai_google_apikey_entry.get().strip()
                base_url = self.ai_google_baseurl_entry.get().strip() or None
            elif provider_key == "openai":
                api_key = self.ai_openai_apikey_entry.get().strip()
                base_url = self.ai_openai_baseurl_entry.get().strip() or None
            elif provider_key == "deepseek":
                api_key = self.ai_deepseek_apikey_entry.get().strip()
                base_url = self.ai_deepseek_baseurl_entry.get().strip() or None
            elif provider_key == "qwen":
                api_key = self.ai_qwen_apikey_entry.get().strip()
                base_url = self.ai_qwen_baseurl_entry.get().strip() or None
            elif provider_key == "siliconflow":
                api_key = self.ai_siliconflow_apikey_entry.get().strip()
                base_url = self.ai_siliconflow_baseurl_entry.get().strip() or None
            elif provider_key == "grok":
                api_key = self.ai_grok_apikey_entry.get().strip()
                base_url = self.ai_grok_baseurl_entry.get().strip() or None
            elif provider_key == "openai_compatible":
                api_key = self.ai_openai_compatible_apikey_entry.get().strip()  # 已修正
                base_url = self.ai_openai_compatible_baseurl_entry.get().strip() or None  # 已修正
            else:
                self.show_error_message(_("内部错误"), f"{_('未知的服务商密钥:')} {provider_key}")
                return
        except AttributeError:
            self.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载，请稍后再试。"))
            return

        if not api_key or "YOUR_" in api_key:
            self.show_warning_message(_("缺少API Key"),
                                      _("请先在编辑器中为 '{}' 填写有效的API Key。").format(provider_key))
            return

        # 从UI读取代理设置
        proxies_to_use = None
        http_proxy = self.downloader_proxy_http_entry.get().strip()
        https_proxy = self.downloader_proxy_https_entry.get().strip()
        if http_proxy or https_proxy:
            proxies_to_use = {}
            if http_proxy:
                proxies_to_use['http'] = http_proxy
            if https_proxy:
                proxies_to_use['https'] = https_proxy
            self._log_to_viewer(f"DEBUG: 将使用代理刷新模型列表: {proxies_to_use}", "DEBUG")

        # 清除之前的取消事件，为新的获取任务做准备
        self.cancel_model_fetch_event.clear()
        self._show_progress_dialog(
            title=_("获取模型列表"),
            message=_("正在从 {} 获取模型列表，请稍候...").format(
                self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)),
            on_cancel=lambda: self.cancel_model_fetch_event.set()
        )

        def fetch_in_thread():
            try:
                timeout_seconds = 30
                # AIWrapper.get_models 会处理 base_url 为 None 的情况
                models = AIWrapper.get_models(
                    provider=provider_key,
                    api_key=api_key,
                    base_url=base_url,
                    cancel_event=self.cancel_model_fetch_event,
                    proxies=proxies_to_use,
                    timeout=timeout_seconds
                )
                if self.cancel_model_fetch_event.is_set():
                    self.message_queue.put(("ai_models_failed", (provider_key, _("操作已取消"))))
                    return

                self.message_queue.put(("ai_models_fetched", (provider_key, models)))
            except Exception as e:
                self.message_queue.put(("ai_models_failed", (provider_key, str(e))))
            finally:
                # 确保在任何情况下都关闭进度弹窗
                self.message_queue.put(("hide_progress_dialog", None))

        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        """显示一个模态的进度弹窗，包含进度条和取消按钮。"""
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.destroy()  # 销毁任何已存在的弹窗，避免重复

        self.progress_dialog = ctk.CTkToplevel(self)
        self.progress_dialog.title(title)
        self.progress_dialog.transient(self)  # 使其模态化，阻止与主窗口交互
        self.progress_dialog.grab_set()  # 捕获焦点
        self.progress_dialog.resizable(False, False)
        self.progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁用关闭按钮，强制通过代码控制

        main_frame = ctk.CTkFrame(self.progress_dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.progress_dialog_text_var = tk.StringVar(value=message)
        ctk.CTkLabel(main_frame, textvariable=self.progress_dialog_text_var,
                     font=self.app_font, wraplength=300, justify="center").pack(pady=10, padx=10)

        self.progress_dialog_bar = ctk.CTkProgressBar(main_frame, width=250, mode="indeterminate")
        self.progress_dialog_bar.pack(pady=10)
        self.progress_dialog_bar.start()  # 启动不确定模式动画

        if on_cancel:  # 如果提供了取消回调函数，则显示取消按钮
            cancel_button = ctk.CTkButton(main_frame, text=_("强制停止"), command=on_cancel, font=self.app_font)
            cancel_button.pack(pady=(10, 0))

        # 居中弹窗
        self.progress_dialog.update_idletasks()  # 强制更新以获取实际尺寸
        x = self.winfo_x() + (self.winfo_width() // 2) - (self.progress_dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (self.progress_dialog.winfo_height() // 2)
        self.progress_dialog.geometry(f"+{x}+{y}")
        self.progress_dialog.deiconify()  # 显示弹窗

    def _hide_progress_dialog(self):
        """
        (这是修正后的版本)
        隐藏并销毁进度弹窗，使用 after() 避免竞态条件。
        """
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.grab_release()

            # 【核心修改】不直接销毁，而是通过 after 调度销毁操作。
            # 这给了Tkinter事件循环一个微小但足够的时间来处理完所有与此窗口相关的挂起事件。
            self.progress_dialog.after(10, self.progress_dialog.destroy)

        # 立即将引用置空，防止后续代码误用
        self.progress_dialog = None
        self.progress_dialog_text_var = None
        self.progress_dialog_bar = None

    def _create_log_viewer_widgets(self):
        """创建并打包操作日志区域的全部控件，并添加折叠功能。"""
        self.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(self.log_viewer_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        self.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold)
        self.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        self.translatable_widgets[self.log_viewer_label_widget] = "操作日志"

        # 创建一个按钮容器
        buttons_sub_frame = ctk.CTkFrame(log_header_frame, fg_color="transparent")
        buttons_sub_frame.grid(row=0, column=1, sticky="e")

        # 添加新的“显示/隐藏”按钮
        self.toggle_log_button = ctk.CTkButton(buttons_sub_frame, text=_("显示日志"), width=90, height=28,
                                               command=self.toggle_log_viewer, font=self.app_font)
        self.toggle_log_button.pack(side="left", padx=(0, 10))
        self.translatable_widgets[self.toggle_log_button] = ("toggle_button", "显示日志", "隐藏日志")  # 特殊注册

        self.clear_log_button = ctk.CTkButton(buttons_sub_frame, text=_("清除日志"), width=80, height=28,
                                              command=self.clear_log_viewer, font=self.app_font)
        self.clear_log_button.pack(side="left")
        self.translatable_widgets[self.clear_log_button] = "清除日志"

        # 创建日志文本框，但先不显示
        self.log_textbox = ctk.CTkTextbox(self.log_viewer_frame, height=140, state="disabled", wrap="word",
                                          font=self.app_font)
        # 注意：这里只创建，不调用 .grid()，因为它默认是隐藏的

        self._update_log_tag_colors()

    def _update_log_tag_colors(self):
        """根据当前的外观模式更新日志文本框的标签颜色。"""
        if hasattr(self, 'log_textbox') and self.log_textbox.winfo_exists():
            # 获取当前是 "Light" 还是 "Dark" 模式
            current_mode = ctk.get_appearance_mode()

            # 根据模式选择对应的单一颜色值
            error_color = "#d9534f" if current_mode == "Light" else "#e57373"
            warning_color = "#f0ad4e" if current_mode == "Light" else "#ffb74d"

            # 使用单一颜色值为 tag 进行配置
            self.log_textbox.tag_config("error_log", foreground=error_color)
            self.log_textbox.tag_config("warning_log", foreground=warning_color)

    def _create_status_bar_widgets(self):
        """创建并打包状态栏的全部控件。"""
        self.status_bar_frame.grid_columnconfigure(0, weight=1)

        # 1. 状态文本标签
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        # 2. 进度条
        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()  # 默认隐藏，只在任务进行时显示

    def _create_layout(self):
        self.status_bar_frame = ctk.CTkFrame(self, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self._create_status_bar_widgets()
        self.log_viewer_frame = ctk.CTkFrame(self)
        self.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self._create_log_viewer_widgets()
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(side="top", fill="both", expand=True)
        self.top_frame.grid_columnconfigure(1, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1)
        self._create_navigation_frame(parent=self.top_frame)
        self._create_main_content_area(parent=self.top_frame)

        # gui_app.py

    def _init_pages_and_final_setup(self):
        # 1. 创建所有主内容区域的 Frame 并赋值给 self 属性
        self.home_frame = self._create_home_frame(self.main_content_frame)
        self.editor_frame = self._create_editor_frame(self.main_content_frame)
        self.integrate_frame = self._create_integrate_frame(self.main_content_frame)
        self.tools_frame = self._create_tools_frame(self.main_content_frame)

        # 2. 同步填充所有工具选项卡的内容 (不再懒加载)
        self._populate_tools_notebook()

        # 3. 【修改】调用新的主控方法来处理编辑器UI
        self._handle_editor_ui_update()

        # 4. 设置初始显示的页面 (例如 "home")
        self.select_frame_by_name("home")

        # 5. 更新UI语言和按钮状态 (这些方法现在可以安全地调用，因为所有基础UI元素都已创建)
        self.update_language_ui()
        self._update_button_states()

        # 6. 启动消息队列的周期性检查 (确保主线程能够处理来自后台的消息)
        self.check_queue_periodic()

        # 7. 设置窗口关闭协议和应用程序图标
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_app_icon()

    def _start_app_async_startup(self):
        """
        (新的、简化的启动方法)
        启动应用的异步加载流程。
        """
        self._show_progress_dialog(
            title=_("正在启动..."),
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None  # 启动阶段不允许取消
        )
        # 启动一个专门用于加载的后台线程
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """
        在后台执行所有耗时的加载操作，完成后将结果放入消息队列。
        """

        try:
            # 1. 加载主配置文件
            default_config_path = "config.yml"
            loaded_config = None
            if os.path.exists(default_config_path):
                # load_config 内部会处理版本不兼容等错误并抛出异常
                loaded_config = load_config(os.path.abspath(default_config_path))

            # 2. 如果主配置加载成功，则加载基因组源数据
            genome_sources = None
            if loaded_config:
                genome_sources = get_genome_data_sources(loaded_config)

            # 3. 将所有加载结果打包，发送“启动完成”消息
            startup_data = {
                "config": loaded_config,
                "genome_sources": genome_sources
            }
            self.message_queue.put(("startup_complete", startup_data))

        except Exception as e:
            # 如果加载过程中任何一步出错，发送“启动失败”消息
            error_message = f"{_('应用启动失败')}: {e}"
            self.message_queue.put(("startup_failed", error_message))

    def _create_editor_frame(self, parent):
        """
        【已重构】创建配置编辑器的主框架，只包含布局和按钮，不包含具体内容。
        """
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)  # 第1行用于滚动框架

        top_frame = ctk.CTkFrame(page, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_frame.grid_columnconfigure(0, weight=1)

        warning_color = ("#D32F2F", "#E57373")
        ctk.CTkLabel(top_frame, text=_("!! 警告: 配置文件可能包含API Key等敏感信息，请勿轻易分享给他人。"),
                     font=self.app_font_bold, text_color=warning_color).grid(row=0, column=0, sticky="w", padx=5)

        self.save_editor_button = ctk.CTkButton(top_frame, text=_("应用并保存配置"),
                                                command=self._save_config_from_editor,
                                                font=self.app_font)
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)

        self.editor_scroll_frame = ctk.CTkScrollableFrame(page)
        self.editor_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
        self._bind_mouse_wheel_to_scrollable(self.editor_scroll_frame)

        return page

    def _get_settings_path(self):
        """获取UI设置文件的路径"""
        # 将设置文件保存在程序根目录，方便用户查找和管理
        return "ui_settings.json"

    def _load_ui_settings(self):
        """加载UI设置，如果文件不存在则使用默认值"""
        settings_path = self._get_settings_path()
        # 默认值
        defaults = {"language": "zh-hans", "appearance_mode": "System"}

        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self.ui_settings = json.load(f)
            else:
                self.ui_settings = defaults
        except (json.JSONDecodeError, IOError):
            # 如果文件损坏或无法读取，也使用默认值
            self.ui_settings = defaults

        # 仅应用主题，不设置变量，变量的设置统一由 update_language_ui 管理
        ctk.set_appearance_mode(self.ui_settings.get("appearance_mode", "System"))

    def _save_ui_settings(self):
        """保存当前的UI设置到文件"""
        settings_path = self._get_settings_path()
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.ui_settings, f, indent=4)
            self._log_to_viewer(_("界面设置已保存。"))
        except IOError as e:
            self._log_to_viewer(f"{_('错误: 无法保存界面设置:')} {e}", "ERROR")

    def _show_custom_dialog(self, title, message, buttons, icon_type=None):
        # 1. 创建窗口并立即隐藏，避免闪烁
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()

        # 2. 设置窗口基础属性
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)

        result = [None]

        # 3. 创建并打包所有内部控件 (这部分代码不变)
        main_frame = ctk.CTkFrame(dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(padx=10, pady=10, fill="both", expand=True)
        icon_text = ""
        if icon_type == "error":
            icon_text = "❌"
        elif icon_type == "warning":
            icon_text = "⚠️"
        elif icon_type == "question":
            icon_text = "❓"
        elif icon_type == "info":
            icon_text = "ℹ️"
        if icon_text:
            ctk.CTkLabel(content_frame, text=icon_text, font=("Segoe UI Emoji", 26)).pack(pady=(10, 10))
        ctk.CTkLabel(content_frame, text=message, font=self.app_font, wraplength=400, justify="center").pack(
            pady=(0, 20), padx=10, fill="x")
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 10), anchor="center")

        def on_button_click(button_text):
            result[0] = button_text
            dialog.destroy()

        for i, button_text in enumerate(buttons):
            is_primary = (i == 0 and len(buttons) > 1 and button_text in [_("确定"), _("Yes")]) or len(buttons) == 1
            btn = ctk.CTkButton(button_frame, text=button_text, command=lambda bt=button_text: on_button_click(bt),
                                font=self.app_font)
            if not is_primary:
                btn.configure(fg_color="transparent", border_width=1,
                              border_color=ctk.ThemeManager.theme["CTkButton"]["border_color"])
            btn.pack(side="left" if len(buttons) > 1 else "top", padx=10)

        # 4. 强制更新以计算窗口的最终所需尺寸
        dialog.update_idletasks()

        # 5. 计算并设置屏幕居中位置
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 6. 在窗口可见之前设置图标
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 设置对话框图标失败: {e}")

        # 7. 设置关闭协议
        dialog.protocol("WM_DELETE_WINDOW", lambda: on_button_click(buttons[-1] if buttons else None))

        # 8. 一切就绪后，显示窗口
        dialog.deiconify()

        # 9. 捕获焦点并等待
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0]

    def _load_image_resource(self, file_name, size=(24, 24)):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath("./assets")
            image_path = os.path.join(base_path, file_name)
            if os.path.exists(image_path):
                return ctk.CTkImage(Image.open(image_path), size=size)
        except Exception as e:
            print(f"警告: 无法加载图片资源 '{file_name}': {e}")
        return None

    def _create_navigation_frame(self, parent):
        self.navigation_frame = ctk.CTkFrame(parent, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(5, weight=1)  # 调整权重行

        nav_header_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        nav_logo_label = ctk.CTkLabel(nav_header_frame, text="", image=self.logo_image)
        nav_logo_label.pack(pady=(0, 10))

        self.nav_title_label = ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold"))
        self.nav_title_label.pack()

        # --- 【顺序和新增按钮修改】 ---
        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=self.home_icon, font=self.app_font_bold,
                                         command=lambda: self.select_frame_by_name("home"))
        self.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # 配置编辑器按钮
        self.editor_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                           text=_("配置编辑器"), fg_color="transparent",
                                           text_color=("gray10", "gray90"),
                                           anchor="w", image=self.settings_icon, font=self.app_font_bold,
                                           command=lambda: self.select_frame_by_name("editor"))
        self.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.integrate_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                              text=_("联合分析"), fg_color="transparent",
                                              text_color=("gray10", "gray90"), anchor="w", image=self.integrate_icon,
                                              font=self.app_font_bold,
                                              command=lambda: self.select_frame_by_name("integrate"))
        self.integrate_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)  # 行号+1

        self.tools_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=self.tools_icon, font=self.app_font_bold,
                                          command=lambda: self.select_frame_by_name("tools"))
        self.tools_button.grid(row=4, column=0, sticky="ew", padx=10, pady=5)  # 行号+1
        # --- 修改结束 ---

        settings_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        self.language_label = ctk.CTkLabel(settings_frame, text=_("语言"), font=self.app_font)
        self.language_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

        self.language_optionmenu = ctk.CTkOptionMenu(settings_frame, variable=self.selected_language_var,
                                                     values=list(self.LANG_CODE_TO_NAME.values()),
                                                     command=self.on_language_change, font=self.app_font,
                                                     dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        self.appearance_mode_label = ctk.CTkLabel(settings_frame, text=_("外观模式"), font=self.app_font)
        self.appearance_mode_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")

        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(settings_frame, variable=self.selected_appearance_var,
                                                             values=[_("浅色"), _("深色"), _("系统")],
                                                             font=self.app_font, dropdown_font=self.app_font,
                                                             command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=3, column=0, padx=5, pady=(0, 10), sticky="ew")

        self.translatable_widgets[self.appearance_mode_optionemenu] = ("values", ["浅色", "深色", "系统"])

    def _create_main_content_area(self, parent):
        self.main_content_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

    def select_frame_by_name(self, name):
        # 设置按钮高亮
        self.home_button.configure(fg_color=self.home_button.cget("hover_color") if name == "home" else "transparent")
        self.editor_button.configure(
            fg_color=self.editor_button.cget("hover_color") if name == "editor" else "transparent")
        self.integrate_button.configure(
            fg_color=self.integrate_button.cget("hover_color") if name == "integrate" else "transparent")
        self.tools_button.configure(
            fg_color=self.tools_button.cget("hover_color") if name == "tools" else "transparent")

        # 隐藏所有页面
        self.home_frame.grid_forget()
        self.editor_frame.grid_forget()
        self.integrate_frame.grid_forget()
        self.tools_frame.grid_forget()

        # 根据名称显示对应的页面
        if name == "home":
            self.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "editor":
            self.editor_frame.grid(row=0, column=0, sticky="nsew")
            # 【修改】调用新的主控方法，它会智能判断是否需要创建UI
            self._handle_editor_ui_update()
        elif name == "integrate":
            self.integrate_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "tools":
            self.tools_frame.grid(row=0, column=0, sticky="nsew")

    def _create_editor_widgets(self, parent):
        """
        【新方法】只创建一次配置编辑器的所有UI控件，但不填充数据。
        """
        parent.grid_columnconfigure(0, weight=1)
        current_row = 0

        # --- 所有辅助函数现在定义在此方法内部 ---
        def create_section_title(p, title_text):
            nonlocal current_row
            ctk.CTkLabel(p, text=f"◇ {title_text} ◇", font=self.app_subtitle_font).grid(row=current_row, column=0,
                                                                                        pady=(25, 10), sticky="w",
                                                                                        padx=5)
            current_row += 1

        def create_entry_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            entry = ctk.CTkEntry(row_frame, font=self.app_font)
            entry.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)
            current_row += 1
            return entry

        def create_switch_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            var = tk.BooleanVar()
            switch = ctk.CTkSwitch(row_frame, text="", variable=var)
            switch.grid(row=0, column=1, sticky="w")
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=10)
            current_row += 1
            return switch, var

        def create_textbox_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="nw", padx=(5, 10))
            textbox = ctk.CTkTextbox(row_frame, height=120, font=self.app_font, wrap="word")
            textbox.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return textbox

        def create_option_menu_row(p, label_text, tooltip, options):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            var = tk.StringVar()
            option_menu = ctk.CTkOptionMenu(row_frame, variable=var, values=options, font=self.app_font,
                                            dropdown_font=self.app_font)
            option_menu.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return option_menu, var

        def create_model_selector_row(p, label_text, tooltip, provider_key):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label_widget = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label_widget.grid(row=0, column=0, sticky="w", padx=(5, 10))
            entry_container = ctk.CTkFrame(row_frame, fg_color="transparent")
            entry_container.grid(row=0, column=1, sticky="ew")
            entry_container.grid_columnconfigure(0, weight=1)
            entry = ctk.CTkEntry(entry_container, font=self.app_font)
            entry.grid(row=0, column=0, sticky="ew")
            var = tk.StringVar()
            dropdown = ctk.CTkOptionMenu(entry_container, variable=var, values=[_("点击刷新")], font=self.app_font,
                                         dropdown_font=self.app_font)
            dropdown.grid(row=0, column=0, sticky="ew")
            dropdown.grid_remove()
            button = ctk.CTkButton(entry_container, text=_("刷新"), width=60, font=self.app_font,
                                   command=lambda p_key=provider_key: self._fetch_ai_models(p_key))
            button.grid(row=0, column=1, padx=(10, 0))
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)
            current_row += 1
            return (row_frame, entry, dropdown, var, button)

        def create_provider_card(p, title):
            card = ctk.CTkFrame(p, border_width=1, corner_radius=8)
            card.pack(fill="x", expand=True, pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)
            card_title = ctk.CTkLabel(card, text=title, font=self.app_font_bold)
            card_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 8))
            return card

        # --- Downloader Configuration ---
        create_section_title(parent, _("数据下载器配置"))
        self.downloader_sources_file_entry = create_entry_row(parent, _("基因组源文件"),
                                                              _("定义基因组下载链接的YAML文件路径。"))
        self.downloader_output_dir_entry = create_entry_row(parent, _("下载输出根目录"),
                                                            _("所有下载文件存放的基准目录。"))
        self.downloader_force_download_switch, self.downloader_force_download_var = create_switch_row(parent,
                                                                                                      _("强制重新下载"),
                                                                                                      _("如果文件已存在，是否强制重新下载。"))
        self.downloader_max_workers_entry = create_entry_row(parent, _("最大下载线程数"),
                                                             _("多线程下载时使用的最大线程数。"))
        self.downloader_proxy_http_entry = create_entry_row(parent, _("HTTP代理"),
                                                            _("HTTP代理地址，例如 'http://your-proxy:port'。不使用则留空。"))
        self.downloader_proxy_https_entry = create_entry_row(parent, _("HTTPS代理"),
                                                             _("HTTPS代理地址，例如 'https://your-proxy:port'。不使用则留空。"))

        # --- AI Services Configuration ---
        create_section_title(parent, _("AI 服务配置"))
        provider_display_names = [v['name'] for v in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu, self.ai_default_provider_var = create_option_menu_row(parent, _("默认AI服务商"),
                                                                                             _("选择默认使用的AI模型提供商。"),
                                                                                             provider_display_names)

        providers_container_frame = ctk.CTkFrame(parent, fg_color="transparent")
        providers_container_frame.grid(row=current_row, column=0, sticky='ew', padx=0, pady=0)
        providers_container_frame.grid_columnconfigure(0, weight=1)
        current_row += 1

        for p_key, p_info in self.AI_PROVIDERS.items():
            provider_display_name = p_info['name']
            card = create_provider_card(providers_container_frame, provider_display_name)
            safe_key = p_key.replace('-', '_')

            apikey_entry = create_entry_row(card, "  " + _("API Key"), "")
            model_selector = create_model_selector_row(card, "  " + _("模型"), _("要使用的模型名称。"), p_key)
            baseurl_entry = create_entry_row(card, "  " + _("Base URL"), "")

            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)
            setattr(self, f"ai_{safe_key}_model_selector", model_selector)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        # --- AI Prompts Configuration ---
        create_section_title(parent, _("AI 提示词模板"))
        self.ai_translation_prompt_textbox = create_textbox_row(parent, _("翻译提示词"),
                                                                _("用于翻译任务的提示词模板。必须包含 {text} 占位符。"))
        self.ai_analysis_prompt_textbox = create_textbox_row(parent, _("分析提示词"),
                                                             _("用于分析任务的提示词模板。必须包含 {text} 占位符。"))

        # --- Annotation Tool Configuration ---
        create_section_title(parent, _("功能注释工具配置"))
        self.anno_db_root_dir_entry = create_entry_row(parent, _("数据库根目录"), _("存放注释数据库文件的目录。"))

        # --- Integration Pipeline Configuration ---
        create_section_title(parent, _("整合分析流程配置"))
        self.pipeline_input_excel_entry = create_entry_row(parent, _("输入Excel路径"),
                                                           _("包含BSA和HVG数据的Excel文件路径。"))
        self.pipeline_bsa_sheet_entry = create_entry_row(parent, _("BSA工作表名"), _("输入Excel中BSA数据的工作表名称。"))
        self.pipeline_hvg_sheet_entry = create_entry_row(parent, _("HVG工作表名"), _("输入Excel中HVG数据的工作表名称。"))
        self.pipeline_output_sheet_entry = create_entry_row(parent, _("输出工作表名"),
                                                            _("整合分析结果将被写入的新工作表名称。"))
        self.pipeline_bsa_assembly_entry = create_entry_row(parent, _("BSA基因组版本ID"),
                                                            _("BSA数据所基于的基因组版本ID。"))
        self.pipeline_hvg_assembly_entry = create_entry_row(parent, _("HVG基因组版本ID"),
                                                            _("HVG数据所基于的基因组版本ID。"))
        self.pipeline_bridge_species_entry = create_entry_row(parent, _("桥梁物种名"),
                                                              _("用于跨版本同源映射的桥梁物种名称。"))
        self.pipeline_gff_db_dir_entry = create_entry_row(parent, _("GFF数据库缓存目录"),
                                                          _("gffutils数据库文件的缓存目录。"))
        self.pipeline_force_gff_db_switch, self.pipeline_force_gff_db_var = create_switch_row(parent,
                                                                                              _("强制创建GFF数据库"),
                                                                                              _("即使缓存已存在，也强制重新创建GFF数据库。"))
        self.pipeline_common_hvg_log2fc_entry = create_entry_row(parent, _("共同HVG Log2FC阈值"),
                                                                 _("用于判断“共同TopHVG”类别基因表达差异是否显著的Log2FC绝对值阈值。"))

        # --- Homology Selection Criteria ---
        create_section_title(parent, _("同源筛选标准 (源 -> 桥梁)"))
        self.s2b_sort_by_entry = create_entry_row(parent, _("排序依据"),
                                                  _("排序优先级列表，英文逗号分隔 (Score,Exp,PID)。"))
        self.s2b_ascending_entry = create_entry_row(parent, _("升序/降序"),
                                                    _("与排序依据对应的布尔值列表，英文逗号分隔 (False,True)。"))
        self.s2b_top_n_entry = create_entry_row(parent, _("Top N"), _("每个查询基因选择的最佳匹配数量。"))
        self.s2b_evalue_entry = create_entry_row(parent, _("E-value阈值"), _("匹配E-value的最大值。"))
        self.s2b_pid_entry = create_entry_row(parent, _("PID阈值"), _("匹配PID的最小值。"))
        self.s2b_score_entry = create_entry_row(parent, _("Score阈值"), _("匹配Score的最小值。"))

        create_section_title(parent, _("同源筛选标准 (桥梁 -> 目标)"))
        self.b2t_sort_by_entry = create_entry_row(parent, _("排序依据"),
                                                  _("排序优先级列表，英文逗号分隔 (Score,Exp,PID)。"))
        self.b2t_ascending_entry = create_entry_row(parent, _("升序/降序"),
                                                    _("与排序依据对应的布尔值列表，英文逗号分隔 (False,True)。"))
        self.b2t_top_n_entry = create_entry_row(parent, _("Top N"), _("每个查询基因选择的最佳匹配数量。"))
        self.b2t_evalue_entry = create_entry_row(parent, _("E-value阈值"), _("匹配E-value的最大值。"))
        self.b2t_pid_entry = create_entry_row(parent, _("PID阈值"), _("匹配PID的最小值。"))
        self.b2t_score_entry = create_entry_row(parent, _("Score阈值"), _("匹配Score的最小值。"))

    # ==================== 请将以下完整方法添加到您的 App 类中 ====================

    def _apply_config_values_to_editor(self):
        """
        【新方法】将 self.current_config 的值填充到已创建的编辑器控件中。
        """
        if not self.current_config or not hasattr(self, 'downloader_sources_file_entry'):
            self._log_to_viewer("DEBUG: Config or editor widgets not ready for value population.", "DEBUG")
            return

        cfg = self.current_config

        # --- 定义一个辅助函数，用于安全地更新输入框/文本框 ---
        def update_widget(widget, value, is_textbox=False):
            if widget and widget.winfo_exists():
                if is_textbox:
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", str(value) if value is not None else "")
                else:
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value) if value is not None else "")

        # --- Downloader Configuration ---
        update_widget(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        update_widget(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(cfg.downloader.force_download)
        update_widget(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        update_widget(self.downloader_proxy_http_entry, cfg.downloader.proxies.http)
        update_widget(self.downloader_proxy_https_entry, cfg.downloader.proxies.https)

        # --- AI Services Configuration ---
        default_display_name = self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name',
                                                                                               cfg.ai_services.default_provider)
        self.ai_default_provider_var.set(default_display_name)
        for p_key, p_cfg in cfg.ai_services.providers.items():
            safe_key = p_key.replace('-', '_')
            if hasattr(self, f"ai_{safe_key}_apikey_entry"):
                update_widget(getattr(self, f"ai_{safe_key}_apikey_entry"), p_cfg.api_key)

                model_selector = getattr(self, f"ai_{safe_key}_model_selector")
                _frame, entry, dropdown, dropdown_var, _button = model_selector
                update_widget(entry, p_cfg.model)  # 总是更新Entry
                dropdown_var.set(p_cfg.model)  # 也更新OptionMenu的变量

                update_widget(getattr(self, f"ai_{safe_key}_baseurl_entry"), p_cfg.base_url)

        # --- AI Prompts, Annotation Tool, Integration Pipeline, Homology Criteria ---
        update_widget(self.ai_translation_prompt_textbox, cfg.ai_prompts.translation_prompt, is_textbox=True)
        update_widget(self.ai_analysis_prompt_textbox, cfg.ai_prompts.analysis_prompt, is_textbox=True)
        update_widget(self.anno_db_root_dir_entry, cfg.annotation_tool.database_root_dir)

        pipe_cfg = cfg.integration_pipeline
        update_widget(self.pipeline_input_excel_entry, pipe_cfg.input_excel_path)
        update_widget(self.pipeline_bsa_sheet_entry, pipe_cfg.bsa_sheet_name)
        update_widget(self.pipeline_hvg_sheet_entry, pipe_cfg.hvg_sheet_name)
        update_widget(self.pipeline_output_sheet_entry, pipe_cfg.output_sheet_name)
        update_widget(self.pipeline_bsa_assembly_entry, pipe_cfg.bsa_assembly_id)
        update_widget(self.pipeline_hvg_assembly_entry, pipe_cfg.hvg_assembly_id)
        update_widget(self.pipeline_bridge_species_entry, pipe_cfg.bridge_species_name)
        update_widget(self.pipeline_gff_db_dir_entry, pipe_cfg.gff_db_storage_dir)
        self.pipeline_force_gff_db_var.set(pipe_cfg.force_gff_db_creation)
        update_widget(self.pipeline_common_hvg_log2fc_entry, pipe_cfg.common_hvg_log2fc_threshold)

        s2b = pipe_cfg.selection_criteria_source_to_bridge
        update_widget(self.s2b_sort_by_entry, ",".join(map(str, s2b.sort_by)))
        update_widget(self.s2b_ascending_entry, ",".join(map(str, s2b.ascending)))
        update_widget(self.s2b_top_n_entry, s2b.top_n)
        update_widget(self.s2b_evalue_entry, s2b.evalue_threshold)
        update_widget(self.s2b_pid_entry, s2b.pid_threshold)
        update_widget(self.s2b_score_entry, s2b.score_threshold)

        b2t = pipe_cfg.selection_criteria_bridge_to_target
        update_widget(self.b2t_sort_by_entry, ",".join(map(str, b2t.sort_by)))
        update_widget(self.b2t_ascending_entry, ",".join(map(str, b2t.ascending)))
        update_widget(self.b2t_top_n_entry, b2t.top_n)
        update_widget(self.b2t_evalue_entry, b2t.evalue_threshold)
        update_widget(self.b2t_pid_entry, b2t.pid_threshold)
        update_widget(self.b2t_score_entry, b2t.score_threshold)

        self._log_to_viewer(_("配置编辑器的值已从当前配置刷新。"), "DEBUG")

    def _update_or_create_editor_ui(self):
        """
        【新方法】智能更新或创建配置编辑器UI。
        这是现在所有需要操作编辑器UI的地方都应该调用的唯一入口。
        """
        # 1. 检查父容器是否存在
        if not hasattr(self, 'editor_scroll_frame') or not self.editor_scroll_frame.winfo_exists():
            return

        # 2. 使用一个标志来判断UI是否已创建。如果没有标志，则在 self 上初始化它。
        if not hasattr(self, 'editor_ui_built'):
            self.editor_ui_built = False

        # 3. 如果UI还没有被构建
        if not self.editor_ui_built:
            self._log_to_viewer("DEBUG: Editor UI not built. Creating now...", "DEBUG")
            # 清理可能存在的占位符文本
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()

            # 如果没有配置，显示提示信息，并直接返回
            if not self.current_config:
                ctk.CTkLabel(self.editor_scroll_frame, text=_("请先从“主页”加载或生成一个配置文件。"),
                             font=self.app_subtitle_font, text_color=self.secondary_text_color).grid(row=0,
                                                                                                     column=0,
                                                                                                     pady=50,
                                                                                                     sticky="nsew")
                self.editor_scroll_frame.grid_rowconfigure(0, weight=1)
                if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")
                return  # 不设置 built 标志，以便下次还能尝试创建

            # 如果有配置，则创建控件
            self._create_editor_widgets(self.editor_scroll_frame)
            self.editor_ui_built = True  # 设置标志，表示UI已创建
            if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="normal")

        # 4. 无论UI是刚创建的还是已存在的，都用当前配置数据填充/更新它
        if self.current_config:
            self._apply_config_values_to_editor()
        else:
            # 如果到这里仍然没有配置（例如，程序刚启动且无默认配置），则禁用保存按钮
            if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")

    def _save_config_from_editor(self):
        """
        (这是完整的版本)
        从静态UI控件中收集数据并保存配置。
        """
        if not self.current_config or not self.config_path:
            self.show_error_message(_("错误"), _("没有加载配置文件，无法保存。"))
            return

        self._log_to_viewer(_("正在从编辑器收集配置并准备保存..."))

        try:
            updated_config = copy.deepcopy(self.current_config)

            def to_int(s, default=0):
                try:
                    return int(s)
                except(ValueError, TypeError):
                    return default

            def to_float(s, default=0.0):
                try:
                    return float(s)
                except(ValueError, TypeError):
                    return default

            def to_bool_list(s):
                return [item.strip().lower() == 'true' for item in s.split(',') if item.strip()]

            def to_str_list(s):
                return [item.strip() for item in s.split(',') if item.strip()]

            def get_model_value(selector_tuple):
                _frame, entry, dropdown, dropdown_var, _button = selector_tuple
                if dropdown.winfo_viewable():
                    return dropdown_var.get()
                else:
                    return entry.get().strip()

            # --- Update Downloader Config ---
            dl_cfg = updated_config.downloader
            dl_cfg.genome_sources_file = self.downloader_sources_file_entry.get()
            dl_cfg.download_output_base_dir = self.downloader_output_dir_entry.get()
            dl_cfg.force_download = self.downloader_force_download_var.get()
            dl_cfg.max_workers = to_int(self.downloader_max_workers_entry.get(), 3)
            dl_cfg.proxies.http = self.downloader_proxy_http_entry.get() or None
            dl_cfg.proxies.https = self.downloader_proxy_https_entry.get() or None

            # --- Update AI Services Config ---
            ai_cfg = updated_config.ai_services
            ai_cfg.default_provider = self.ai_default_provider_var.get()
            for p_key in ai_cfg.providers:
                safe_key = p_key.replace('-', '_')
                if hasattr(self, f"ai_{safe_key}_apikey_entry"):
                    ai_cfg.providers[p_key].api_key = getattr(self, f"ai_{safe_key}_apikey_entry").get()
                    ai_cfg.providers[p_key].model = get_model_value(getattr(self, f"ai_{safe_key}_model_selector"))
                    if hasattr(self, f"ai_{safe_key}_baseurl_entry"):
                        ai_cfg.providers[p_key].base_url = getattr(self, f"ai_{safe_key}_baseurl_entry").get() or None

            # --- Update AI Prompts ---
            prompt_cfg = updated_config.ai_prompts
            prompt_cfg.translation_prompt = self.ai_translation_prompt_textbox.get("1.0", tk.END).strip()
            prompt_cfg.analysis_prompt = self.ai_analysis_prompt_textbox.get("1.0", tk.END).strip()

            # --- Update Integration Pipeline Config ---
            pipe_cfg = updated_config.integration_pipeline
            pipe_cfg.input_excel_path = self.pipeline_input_excel_entry.get()
            pipe_cfg.bsa_sheet_name = self.pipeline_bsa_sheet_entry.get()
            pipe_cfg.hvg_sheet_name = self.pipeline_hvg_sheet_entry.get()
            pipe_cfg.output_sheet_name = self.pipeline_output_sheet_entry.get()
            pipe_cfg.bsa_assembly_id = self.pipeline_bsa_assembly_entry.get()
            pipe_cfg.hvg_assembly_id = self.pipeline_hvg_assembly_entry.get()
            pipe_cfg.bridge_species_name = self.pipeline_bridge_species_entry.get()
            pipe_cfg.gff_db_storage_dir = self.pipeline_gff_db_dir_entry.get()
            pipe_cfg.force_gff_db_creation = self.pipeline_force_gff_db_var.get()
            pipe_cfg.common_hvg_log2fc_threshold = to_float(self.pipeline_common_hvg_log2fc_entry.get(), 1.0)

            s2b = pipe_cfg.selection_criteria_source_to_bridge
            s2b.sort_by = to_str_list(self.s2b_sort_by_entry.get())
            s2b.ascending = to_bool_list(self.s2b_ascending_entry.get())
            s2b.top_n = to_int(self.s2b_top_n_entry.get(), 1)
            s2b.evalue_threshold = to_float(self.s2b_evalue_entry.get(), 1.0e-10)
            s2b.pid_threshold = to_float(self.s2b_pid_entry.get(), 30.0)
            s2b.score_threshold = to_float(self.s2b_score_entry.get(), 50.0)

            b2t = pipe_cfg.selection_criteria_bridge_to_target
            b2t.sort_by = to_str_list(self.b2t_sort_by_entry.get())
            b2t.ascending = to_bool_list(self.b2t_ascending_entry.get())
            b2t.top_n = to_int(self.b2t_top_n_entry.get(), 1)
            b2t.evalue_threshold = to_float(self.b2t_evalue_entry.get(), 1.0e-15)
            b2t.pid_threshold = to_float(self.b2t_pid_entry.get(), 40.0)
            b2t.score_threshold = to_float(self.b2t_score_entry.get(), 80.0)

            # --- Save the final object ---
            if save_config(updated_config, self.config_path):
                self.current_config = updated_config
                self.show_info_message(_("保存成功"), _("配置文件已更新。"))
                self._apply_config_to_ui()
            else:
                self.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_error_message(_("保存错误"), f"{_('在更新或保存配置时发生错误')}: {e}")

    def _create_static_editor_ui(self, parent):
        """
        创建静态的、硬编码的UI界面用于配置编辑器。
        此方法只在首次显示编辑器时被调用一次。
        """
        # 清理父框架中的任何占位符
        for widget in parent.winfo_children():
            widget.destroy()

        parent.grid_columnconfigure(0, weight=1)
        current_row = 0

        # --- Helper functions to reduce boilerplate code ---
        def create_section_title(p, title_text):
            nonlocal current_row
            ctk.CTkLabel(p, text=f"◇ {title_text} ◇", font=self.app_subtitle_font).grid(row=current_row, column=0,
                                                                                        pady=(25, 10), sticky="w",
                                                                                        padx=5)
            current_row += 1

        def create_entry_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            # 【修复】让此行框架跨越父容器的2列，以利用可伸展的第1列
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))

            entry = ctk.CTkEntry(row_frame, font=self.app_font)
            entry.grid(row=0, column=1, sticky="ew")

            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)
            current_row += 1
            return entry

        def create_switch_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))

            var = tk.BooleanVar()
            switch = ctk.CTkSwitch(row_frame, text="", variable=var)
            switch.grid(row=0, column=1, sticky="w")

            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=10)
            current_row += 1
            return switch, var

        def create_textbox_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="nw", padx=(5, 10))

            textbox = ctk.CTkTextbox(row_frame, height=120, font=self.app_font, wrap="word")
            textbox.grid(row=0, column=1, sticky="ew")

            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return textbox

        def create_option_menu_row(p, label_text, tooltip, options, default_value):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))

            var = tk.StringVar(value=default_value)
            option_menu = ctk.CTkOptionMenu(row_frame, variable=var, values=options, font=self.app_font,
                                            dropdown_font=self.app_font)
            option_menu.grid(row=0, column=1, sticky="ew")

            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return option_menu, var

        def create_model_selector_row(p, label_text, tooltip, provider_key):
            nonlocal current_row
            row_frame = ctk.CTkFrame(p, fg_color="transparent")
            # 【修复】让此行框架跨越父容器的2列
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)

            label_widget = ctk.CTkLabel(row_frame, text=label_text, font=self.app_font)
            label_widget.grid(row=0, column=0, sticky="w", padx=(5, 10))

            entry_container = ctk.CTkFrame(row_frame, fg_color="transparent")
            entry_container.grid(row=0, column=1, sticky="ew")
            entry_container.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(entry_container, font=self.app_font)
            entry.grid(row=0, column=0, sticky="ew")

            var = tk.StringVar()
            dropdown = ctk.CTkOptionMenu(entry_container, variable=var, values=[_("点击刷新")], font=self.app_font,
                                         dropdown_font=self.app_font)
            dropdown.grid(row=0, column=0, sticky="ew")
            dropdown.grid_remove()

            button = ctk.CTkButton(entry_container, text=_("刷新"), width=60, font=self.app_font,
                                   command=lambda p_key=provider_key: self._fetch_ai_models(p_key))
            button.grid(row=0, column=1, padx=(10, 0))

            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
                                             text_color=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)

            current_row += 1
            return (row_frame, entry, dropdown, var, button)

        def create_provider_card(p, title):
            card = ctk.CTkFrame(p, border_width=1, corner_radius=8)
            card.pack(fill="x", expand=True, pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)

            card_title = ctk.CTkLabel(card, text=title, font=self.app_font_bold)
            card_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 8))
            return card

        # --- Downloader Configuration ---
        create_section_title(parent, _("数据下载器配置"))
        self.downloader_sources_file_entry = create_entry_row(parent, _("基因组源文件"),
                                                              _("定义基因组下载链接的YAML文件路径。"))
        self.downloader_output_dir_entry = create_entry_row(parent, _("下载输出根目录"),
                                                            _("所有下载文件存放的基准目录。"))
        self.downloader_force_download_switch, self.downloader_force_download_var = create_switch_row(parent,
                                                                                                      _("强制重新下载"),
                                                                                                      _("如果文件已存在，是否强制重新下载。"))
        self.downloader_max_workers_entry = create_entry_row(parent, _("最大下载线程数"),
                                                             _("多线程下载时使用的最大线程数。"))
        self.downloader_proxy_http_entry = create_entry_row(parent, _("HTTP代理"),
                                                            _("HTTP代理地址，例如 'http://your-proxy:port'。不使用则留空。"))
        self.downloader_proxy_https_entry = create_entry_row(parent, _("HTTPS代理"),
                                                             _("HTTPS代理地址，例如 'https://your-proxy:port'。不使用则留空。"))

        # --- AI Services Configuration ---
        create_section_title(parent, _("AI 服务配置"))
        provider_display_names = [v['name'] for v in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu, self.ai_default_provider_var = create_option_menu_row(parent, _("默认AI服务商"),
                                                                                             _("选择默认使用的AI模型提供商。"),
                                                                                             provider_display_names,
                                                                                             "Google Gemini")

        providers_container_frame = ctk.CTkFrame(parent, fg_color="transparent")
        providers_container_frame.grid(row=current_row, column=0, sticky='ew', padx=0, pady=0)
        providers_container_frame.grid_columnconfigure(0, weight=1)
        current_row += 1

        # --- Create Provider Cards and Widgets ---
        # Google
        google_card = create_provider_card(providers_container_frame, "Google Gemini")
        self.ai_google_apikey_entry = create_entry_row(google_card, "  " + _("API Key"), "")
        self.ai_google_model_selector = create_model_selector_row(google_card, "  " + _("模型"),
                                                                  _("要使用的Google Gemini模型名称。"), "google")
        self.ai_google_baseurl_entry = create_entry_row(google_card, "  " + _("Base URL"), "")

        # Grok
        grok_card = create_provider_card(providers_container_frame, "Grok (xAI)")
        self.ai_grok_apikey_entry = create_entry_row(grok_card, "  " + _("API Key"), "")
        self.ai_grok_model_selector = create_model_selector_row(grok_card, "  " + _("模型"), _("要使用的Grok模型名称。"),
                                                                "grok")
        self.ai_grok_baseurl_entry = create_entry_row(grok_card, "  " + _("Base URL"), "")

        # OpenAI
        openai_card = create_provider_card(providers_container_frame, "OpenAI")
        self.ai_openai_apikey_entry = create_entry_row(openai_card, "  " + _("API Key"), "")
        self.ai_openai_model_selector = create_model_selector_row(openai_card, "  " + _("模型"),
                                                                  _("要使用的OpenAI模型名称。"), "openai")
        self.ai_openai_baseurl_entry = create_entry_row(openai_card, "  " + _("Base URL"), "")

        # DeepSeek
        deepseek_card = create_provider_card(providers_container_frame, "DeepSeek")
        self.ai_deepseek_apikey_entry = create_entry_row(deepseek_card, "  " + _("API Key"), "")
        self.ai_deepseek_model_selector = create_model_selector_row(deepseek_card, "  " + _("模型"),
                                                                    _("要使用的DeepSeek模型名称。"), "deepseek")
        self.ai_deepseek_baseurl_entry = create_entry_row(deepseek_card, "  " + _("Base URL"), "")

        # Qwen
        qwen_card = create_provider_card(providers_container_frame, "Qwen")
        self.ai_qwen_apikey_entry = create_entry_row(qwen_card, "  " + _("API Key"), "")
        self.ai_qwen_model_selector = create_model_selector_row(qwen_card, "  " + _("模型"),
                                                                _("要使用的通义千问模型名称。"), "qwen")
        self.ai_qwen_baseurl_entry = create_entry_row(qwen_card, "  " + _("Base URL"), "")

        # SiliconFlow
        siliconflow_card = create_provider_card(providers_container_frame, "SiliconFlow")
        self.ai_siliconflow_apikey_entry = create_entry_row(siliconflow_card, "  " + _("API Key"), "")
        self.ai_siliconflow_model_selector = create_model_selector_row(siliconflow_card, "  " + _("模型"),
                                                                       _("要使用的SiliconFlow模型名称。"), "siliconflow")
        self.ai_siliconflow_baseurl_entry = create_entry_row(siliconflow_card, "  " + _("Base URL"), "")

        # OpenAI Compatible
        oai_compat_card = create_provider_card(providers_container_frame, _("通用OpenAI兼容接口"))
        self.ai_openai_compatible_apikey_entry = create_entry_row(oai_compat_card, "  " + _("API Key"), "")
        self.ai_openai_compatible_model_selector = create_model_selector_row(oai_compat_card, "  " + _("模型"),
                                                                             _("要使用的自定义模型名称。"),
                                                                             "openai_compatible")
        self.ai_openai_compatible_baseurl_entry = create_entry_row(oai_compat_card, "  " + _("Base URL"), "")

        # --- AI Prompts Configuration ---
        create_section_title(parent, _("AI 提示词模板"))
        self.ai_translation_prompt_textbox = create_textbox_row(parent, _("翻译提示词"),
                                                                _("用于翻译任务的提示词模板。必须包含 {text} 占位符。"))
        self.ai_analysis_prompt_textbox = create_textbox_row(parent, _("分析提示词"),
                                                             _("用于分析任务的提示词模板。必须包含 {text} 占位符。"))

        # --- Annotation Tool Configuration (Simplified for brevity) ---
        create_section_title(parent, _("功能注释工具配置"))
        self.anno_db_root_dir_entry = create_entry_row(parent, _("数据库根目录"), _("存放注释数据库文件的目录。"))

        # --- Integration Pipeline Configuration ---
        create_section_title(parent, _("整合分析流程配置"))
        self.pipeline_input_excel_entry = create_entry_row(parent, _("输入Excel路径"),
                                                           _("包含BSA和HVG数据的Excel文件路径。"))
        self.pipeline_bsa_sheet_entry = create_entry_row(parent, _("BSA工作表名"), _("输入Excel中BSA数据的工作表名称。"))
        self.pipeline_hvg_sheet_entry = create_entry_row(parent, _("HVG工作表名"), _("输入Excel中HVG数据的工作表名称。"))
        self.pipeline_output_sheet_entry = create_entry_row(parent, _("输出工作表名"),
                                                            _("整合分析结果将被写入的新工作表名称。"))
        self.pipeline_bsa_assembly_entry = create_entry_row(parent, _("BSA基因组版本ID"),
                                                            _("BSA数据所基于的基因组版本ID。"))
        self.pipeline_hvg_assembly_entry = create_entry_row(parent, _("HVG基因组版本ID"),
                                                            _("HVG数据所基于的基因组版本ID。"))
        self.pipeline_bridge_species_entry = create_entry_row(parent, _("桥梁物种名"),
                                                              _("用于跨版本同源映射的桥梁物种名称。"))
        self.pipeline_gff_db_dir_entry = create_entry_row(parent, _("GFF数据库缓存目录"),
                                                          _("gffutils数据库文件的缓存目录。"))
        self.pipeline_force_gff_db_switch, self.pipeline_force_gff_db_var = create_switch_row(parent,
                                                                                              _("强制创建GFF数据库"),
                                                                                              _("即使缓存已存在，也强制重新创建GFF数据库。"))
        self.pipeline_common_hvg_log2fc_entry = create_entry_row(parent, _("共同HVG Log2FC阈值"),
                                                                 _("用于判断“共同TopHVG”类别基因表达差异是否显著的Log2FC绝对值阈值。"))

        # --- Homology Selection Criteria ---
        create_section_title(parent, _("同源筛选标准 (源 -> 桥梁)"))
        self.s2b_sort_by_entry = create_entry_row(parent, _("排序依据"),
                                                  _("排序优先级列表，英文逗号分隔 (Score,Exp,PID)。"))
        self.s2b_ascending_entry = create_entry_row(parent, _("升序/降序"),
                                                    _("与排序依据对应的布尔值列表，英文逗号分隔 (False,True)。"))
        self.s2b_top_n_entry = create_entry_row(parent, _("Top N"), _("每个查询基因选择的最佳匹配数量。"))
        self.s2b_evalue_entry = create_entry_row(parent, _("E-value阈值"), _("匹配E-value的最大值。"))
        self.s2b_pid_entry = create_entry_row(parent, _("PID阈值"), _("匹配PID的最小值。"))
        self.s2b_score_entry = create_entry_row(parent, _("Score阈值"), _("匹配Score的最小值。"))

        create_section_title(parent, _("同源筛选标准 (桥梁 -> 目标)"))
        self.b2t_sort_by_entry = create_entry_row(parent, _("排序依据"),
                                                  _("排序优先级列表，英文逗号分隔 (Score,Exp,PID)。"))
        self.b2t_ascending_entry = create_entry_row(parent, _("升序/降序"),
                                                    _("与排序依据对应的布尔值列表，英文逗号分隔 (False,True)。"))
        self.b2t_top_n_entry = create_entry_row(parent, _("Top N"), _("每个查询基因选择的最佳匹配数量。"))
        self.b2t_evalue_entry = create_entry_row(parent, _("E-value阈值"), _("匹配E-value的最大值。"))
        self.b2t_pid_entry = create_entry_row(parent, _("PID阈值"), _("匹配PID的最小值。"))
        self.b2t_score_entry = create_entry_row(parent, _("Score阈值"), _("匹配Score的最小值。"))

    def _create_status_bar(self, parent):
        self.status_bar_frame = ctk.CTkFrame(parent, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar_frame.grid_columnconfigure(0, weight=1)
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()

    def _create_home_frame(self, parent):
        # 使用可滚动的框架，并让其内容居中
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        # 配置列以允许内容水平居中
        frame.grid_columnconfigure(0, weight=1)

        # --- 顶部信息区 ---
        top_info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        top_info_frame.grid(row=0, column=0, pady=(40, 20), padx=40, sticky="ew")
        top_info_frame.grid_columnconfigure(0, weight=1)  # 允许标签内容居中

        # --- 先将文本赋值给变量，再传递给控件 ---
        title_text = _(self.title_text_key)
        ctk.CTkLabel(top_info_frame, text=title_text, font=self.app_title_font).pack(pady=(0, 10))

        self.config_path_label = ctk.CTkLabel(top_info_frame, text=_("未加载配置"), wraplength=500,
                                              font=self.app_font, text_color=self.secondary_text_color)
        self.translatable_widgets[self.config_path_label] = ("config_path_display", _("当前配置: {}"), _("未加载配置"))
        self.config_path_label.pack(pady=(10, 0))

        # --- 卡片式布局 ---
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1), weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)

        # --- 卡片1: 配置文件操作 ---
        config_card = ctk.CTkFrame(cards_frame)
        config_card.grid(row=0, column=0, padx=20, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)
        config_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(config_card, text=_("配置文件"), font=self.app_font_bold).grid(
            row=0, column=0, pady=(15, 20), padx=20, sticky="w")
        self.load_config_button = ctk.CTkButton(config_card, text=_("加载配置文件..."), image=self.folder_icon,
                                                command=self.load_config_file, height=40, font=self.app_font)
        self.translatable_widgets[self.load_config_button] = "加载配置文件..."
        self.load_config_button.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        self.gen_config_button = ctk.CTkButton(config_card, text=_("生成默认配置..."), image=self.new_file_icon,
                                               command=self._generate_default_configs_gui, height=40,
                                               font=self.app_font,
                                               fg_color="transparent", border_width=1)
        self.translatable_widgets[self.gen_config_button] = "生成默认配置..."
        self.gen_config_button.grid(row=3, column=0, pady=(10, 15), padx=20, sticky="ew")

        # --- 卡片2: 帮助与支持 ---
        help_card = ctk.CTkFrame(cards_frame)
        help_card.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)
        help_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(help_card, text=_("帮助与支持"), font=self.app_font_bold).grid(
            row=0, column=0, pady=(15, 20), padx=20, sticky="w")
        self.help_button = ctk.CTkButton(help_card, text=_("在线帮助文档"), image=self.help_icon,
                                         command=self._open_online_help, height=40, font=self.app_font)
        self.translatable_widgets[self.help_button] = "在线帮助文档"
        self.help_button.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        self.about_button = ctk.CTkButton(help_card, text=_("关于本软件"), image=self.info_icon,
                                          command=self._show_about_window,
                                          height=40, font=self.app_font,
                                          fg_color="transparent", border_width=1)
        self.translatable_widgets[self.about_button] = "关于本软件"
        self.about_button.grid(row=3, column=0, pady=(10, 15), padx=20, sticky="ew")

        return frame

    def _create_integrate_frame(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # 标题和描述
        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.pack(pady=(20, 15), padx=30, fill="x")
        ctk.CTkLabel(title_frame, text=_("联合分析"), font=self.app_title_font).pack()
        ctk.CTkLabel(title_frame, text=_("结合BSA定位区间与高变异基因(HVG)，筛选候选基因，为精细定位提供依据。"),
                     font=self.app_font, text_color=self.secondary_text_color, wraplength=600).pack(pady=(5, 0))

        # --- 卡片1: 输入文件 ---
        input_card = ctk.CTkFrame(frame)
        input_card.pack(fill="x", padx=30, pady=10)
        input_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(input_card, text=_("第一步: 选择包含BSA和HVG数据的Excel文件"), font=self.app_font_bold).grid(row=0,
                                                                                                                  column=0,
                                                                                                                  columnspan=3,
                                                                                                                  padx=15,
                                                                                                                  pady=15,
                                                                                                                  sticky="w")

        excel_path_label = ctk.CTkLabel(input_card, text=_("Excel文件路径:"), font=self.app_font)
        self.translatable_widgets[excel_path_label] = "Excel文件路径:"
        excel_path_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_card, font=self.app_font, height=35,
                                                  placeholder_text=_("点击“浏览”选择文件，或从配置加载"))
        self.translatable_widgets[self.integrate_excel_entry] = ("placeholder", _("从配置加载或在此覆盖"))
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 15), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_card, text=_("BSA数据工作表:"), font=self.app_font)
        self.translatable_widgets[bsa_sheet_label] = "BSA数据工作表:"
        bsa_sheet_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 15), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_card, text=_("HVG数据工作表:"), font=self.app_font)
        self.translatable_widgets[hvg_sheet_label] = "HVG数据工作表:"
        hvg_sheet_label.grid(row=3, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_hvg_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_hvg_sheet_dropdown.grid(row=3, column=1, columnspan=2, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片2: 基因组版本 ---
        version_card = ctk.CTkFrame(frame)
        version_card.pack(fill="x", padx=30, pady=10)
        version_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(version_card, text=_("第二步: 指定对应的基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                         column=0,
                                                                                                         columnspan=2,
                                                                                                         padx=15,
                                                                                                         pady=15,
                                                                                                         sticky="w")

        bsa_assembly_label = ctk.CTkLabel(version_card, text=_("BSA基因组版本:"), font=self.app_font)
        self.translatable_widgets[bsa_assembly_label] = "BSA基因组版本:"
        bsa_assembly_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 15), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_card, text=_("HVG基因组版本:"), font=self.app_font)
        self.translatable_widgets[hvg_assembly_label] = "HVG基因组版本:"
        hvg_assembly_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片3: 运行 ---
        run_card = ctk.CTkFrame(frame, fg_color="transparent")
        run_card.pack(fill="x", padx=30, pady=20)
        self.integrate_start_button = ctk.CTkButton(run_card, text=_("开始联合分析"), height=50,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始联合分析"
        self.integrate_start_button.pack(fill="x", expand=True)

        return frame

    def _create_tools_frame(self, parent):

        def _on_tab_change():
            """当工具区的选项卡发生切换时被调用。"""
            # 不再有懒加载逻辑，所有tabs都在启动时创建
            selected_tab_name = self.tools_notebook.get()
            # 如果需要，可以在这里为特定的tab添加切换逻辑 (例如刷新数据)
            # 例如：if selected_tab_name == _("AI 助手"): self._update_ai_assistant_tab_info()

        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=_("数据工具"), font=self.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        self.tools_notebook = ctk.CTkTabview(frame, corner_radius=8, command=_on_tab_change)
        if hasattr(self.tools_notebook, '_segmented_button'):
            self.tools_notebook._segmented_button.configure(font=self.app_font)
        self.tools_notebook.grid(row=1, column=0, padx=30, pady=10, sticky="nsew")

        return frame

    def _populate_tools_notebook(self):
        tool_tab_definitions = {
            "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
            "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
        }

        # 清理旧的tab和frame，确保每次都是干净的构建
        for tab_frame_key in list(self.tool_tab_frames.keys()):
            tab_frame = self.tool_tab_frames.pop(tab_frame_key, None)
            if tab_frame and tab_frame.winfo_exists():
                tab_frame.destroy()

        for tab_name in list(self.tools_notebook._tab_dict.keys()):
            self.tools_notebook.delete(tab_name)

        self.tool_tab_ui_loaded.clear()  # 重置加载状态

        # 现在，创建 ALL tabs and populate their content synchronously at startup
        for simple_key, display_name in tool_tab_definitions.items():
            tab_frame = self.tools_notebook.add(display_name)
            self.tool_tab_frames[display_name] = tab_frame

            # 不再懒加载：直接填充内容
            if simple_key == "download":
                self._populate_download_tab_structure(tab_frame)
            elif simple_key == "homology":
                self._populate_homology_map_tab_structure(tab_frame)
            elif simple_key == "gff_query":
                self._populate_gff_query_tab_structure(tab_frame)
            elif simple_key == "annotation":
                self._populate_annotation_tab(tab_frame)
            elif simple_key == "ai_assistant":
                self._populate_ai_assistant_tab(tab_frame)
            elif simple_key == "xlsx_to_csv":
                self._populate_xlsx_to_csv_tab(tab_frame)

            # 标记为已加载，因为内容已经创建
            self.tool_tab_ui_loaded[display_name] = True

        # 默认选中第一个工具tab
        if tool_tab_definitions:
            self.tools_notebook.set(list(tool_tab_definitions.values())[0])

    def _populate_xlsx_to_csv_tab(self, page):
        """创建“XLSX转CSV”页面的UI"""
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 10), padx=20)

        # 添加功能说明标签
        info_label = ctk.CTkLabel(page, text=_(
            "此工具会将一个Excel文件中的所有工作表(Sheet)内容合并到一个CSV文件中。\n适用于所有Sheet表头格式一致的情况。"),
                                  font=self.app_font, wraplength=600, justify="center",
                                  text_color=self.secondary_text_color)
        info_label.pack(pady=(0, 20), padx=30)

        # 创建一个卡片容纳主要控件
        card = ctk.CTkFrame(page)
        card.pack(fill="x", expand=True, padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        # 输入文件选择
        ctk.CTkLabel(card, text=_("输入Excel文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=(20, 10),
                                                                              sticky="w")
        self.xlsx_input_entry = ctk.CTkEntry(card, placeholder_text=_("选择要转换的 .xlsx 文件"), height=35,
                                             font=self.app_font)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        ctk.CTkButton(card, text=_("浏览..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(row=0,
                                                                                                                  column=2,
                                                                                                                  padx=10,
                                                                                                                  pady=(
                                                                                                                      20,
                                                                                                                      10))

        # 输出文件选择
        ctk.CTkLabel(card, text=_("输出CSV文件:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                            sticky="w")
        self.csv_output_entry = ctk.CTkEntry(card, placeholder_text=_("选择保存位置和文件名 (不填则自动命名)"),
                                             height=35, font=self.app_font)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(card, text=_("另存为..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        # 开始转换按钮
        self.convert_start_button = ctk.CTkButton(page, text=_("开始转换"), height=40,
                                                  command=self.start_xlsx_to_csv_conversion, font=self.app_font_bold)
        self.convert_start_button.pack(fill="x", padx=20, pady=(20, 20))

    def start_xlsx_to_csv_conversion(self):
        """启动XLSX到CSV的转换任务"""
        from cotton_toolkit.core.convertXlsx2csv import convert_xlsx_to_single_csv

        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()

        if not input_path or not os.path.exists(input_path):
            self.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
            return

        # 如果输出路径为空，则自动生成一个
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.insert(0, output_path)

        self.active_task_name = _("XLSX转CSV")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self._update_button_states(is_task_running=True)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.start()

        # 在后台线程中运行转换，防止UI卡顿
        threading.Thread(
            target=lambda: (
                result := convert_xlsx_to_single_csv(input_path, output_path),
                self.task_done_callback(result, self.active_task_name)
            ),
            daemon=True
        ).start()

    def _populate_annotation_tab(self, page):
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("对基因列表进行 GO/IPR/KEGG 功能注释"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 15), padx=20)

        input_card = ctk.CTkFrame(page)
        input_card.pack(fill="x", padx=20, pady=10)
        input_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(input_card, text=_("输入文件 (含基因ID列):"), font=self.app_font).grid(row=0, column=0, padx=10,
                                                                                            pady=10, sticky="w")
        self.anno_input_file_entry = ctk.CTkEntry(input_card, placeholder_text=_("选择一个Excel或CSV文件"), height=35,
                                                  font=self.app_font)
        self.anno_input_file_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.anno_input_file_entry, [("Table files", "*.xlsx *.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=10, pady=10)

        ctk.CTkLabel(input_card, text=_("基因ID所在列名:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                     sticky="w")
        self.anno_gene_col_entry = ctk.CTkEntry(input_card, placeholder_text=_("例如: gene, gene_id (默认: gene)"),
                                                height=35, font=self.app_font)
        self.anno_gene_col_entry.grid(row=1, column=1, columnspan=2, padx=(5, 10), sticky="ew")

        type_card = ctk.CTkFrame(page)
        type_card.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(type_card, text=_("选择注释类型 (需要本地数据库文件支持)"), font=self.app_font).pack(anchor="w",
                                                                                                          padx=10,
                                                                                                          pady=10)
        checkbox_frame = ctk.CTkFrame(type_card, fg_color="transparent")
        checkbox_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkCheckBox(checkbox_frame, text="GO", variable=self.go_anno_var, font=self.app_font).pack(side="left",
                                                                                                       padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="IPR", variable=self.ipr_anno_var, font=self.app_font).pack(side="left",
                                                                                                         padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                        font=self.app_font).pack(side="left", padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                        font=self.app_font).pack(side="left", padx=15)

        self.anno_start_button = ctk.CTkButton(page, text=_("开始功能注释"), height=40,
                                               command=self.start_annotation_task, font=self.app_font_bold)
        self.anno_start_button.pack(fill="x", padx=20, pady=20)

    def _load_prompts_to_ai_tab(self):
        """将配置中的Prompt模板加载到AI助手页面的输入框中。"""
        if not self.current_config: return

        # 直接从 MainConfig 对象访问 prompts
        prompts_cfg = self.current_config.ai_prompts
        trans_prompt = prompts_cfg.translation_prompt
        analy_prompt = prompts_cfg.analysis_prompt

        if hasattr(self, 'ai_translate_prompt_textbox'):
            self.ai_translate_prompt_textbox.delete("1.0", tk.END)
            self.ai_translate_prompt_textbox.insert("1.0", trans_prompt)

        if hasattr(self, 'ai_analyze_prompt_textbox'):
            self.ai_analyze_prompt_textbox.delete("1.0", tk.END)
            self.ai_analyze_prompt_textbox.insert("1.0", analy_prompt)

    def _populate_ai_assistant_tab(self, page):
        """创建AI助手页面，为不同任务提供独立的、可编辑的Prompt输入框。"""
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(page, text=_("使用AI批量处理表格数据"), font=self.app_title_font, wraplength=500).pack(
            pady=(20, 10), padx=20)

        ai_info_card = ctk.CTkFrame(page, fg_color=("gray90", "gray20"))
        ai_info_card.pack(fill="x", padx=20, pady=10)
        ai_info_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ai_info_card, text=_("当前AI配置:"), font=self.app_font_bold).grid(row=0, column=0, padx=10,
                                                                                        pady=(10, 5), sticky="w")
        self.ai_info_provider_label = ctk.CTkLabel(ai_info_card, text=_("服务商: -"), font=self.app_font)
        self.ai_info_provider_label.grid(row=1, column=0, padx=20, pady=2, sticky="w")
        self.ai_info_model_label = ctk.CTkLabel(ai_info_card, text=_("模型: -"), font=self.app_font)
        self.ai_info_model_label.grid(row=1, column=1, padx=10, pady=2, sticky="w")
        self.ai_info_key_label = ctk.CTkLabel(ai_info_card, text=_("API Key: -"), font=self.app_font)
        self.ai_info_key_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(2, 10), sticky="w")

        # --- UI重构部分 ---
        main_card = ctk.CTkFrame(page)
        main_card.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        main_card.grid_columnconfigure(1, weight=1)
        main_card.grid_rowconfigure(3, weight=1)  # 为Prompt输入框分配权重

        # 任务选择和文件输入
        ctk.CTkLabel(main_card, text=_("输入CSV文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=10,
                                                                                 sticky="w")
        self.ai_input_file_entry = ctk.CTkEntry(main_card, placeholder_text=_("选择一个CSV文件"), height=35,
                                                font=self.app_font)
        self.ai_input_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ctk.CTkButton(main_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.ai_input_file_entry, [("CSV files", "*.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=(0, 10))

        ctk.CTkLabel(main_card, text=_("选择任务类型:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                  sticky="w")
        self.ai_task_type_menu = ctk.CTkOptionMenu(main_card, variable=self.ai_task_type_var,
                                                   values=[_("翻译"), _("分析")], command=self._on_ai_task_type_change,
                                                   height=35, font=self.app_font, dropdown_font=self.app_font)
        self.ai_task_type_menu.grid(row=1, column=1, columnspan=2, padx=(0, 10), sticky="ew")

        # Prompt 输入区域
        ctk.CTkLabel(main_card, text=_("Prompt 指令 (用 {text} 代表单元格内容):"), font=self.app_font).grid(row=2,
                                                                                                            column=0,
                                                                                                            columnspan=3,
                                                                                                            padx=10,
                                                                                                            pady=(10,
                                                                                                                  0),
                                                                                                            sticky="w")

        # 为翻译任务创建Prompt输入框
        self.ai_translate_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_translate_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        # 为分析任务创建Prompt输入框
        self.ai_analyze_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_analyze_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        # 其他参数
        param_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        param_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        param_frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(param_frame, text=_("源列名:"), font=self.app_font).grid(row=0, column=0, padx=5)
        self.ai_source_col_entry = ctk.CTkEntry(param_frame, placeholder_text="Description", height=35,
                                                font=self.app_font)
        self.ai_source_col_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(param_frame, text=_("新列名:"), font=self.app_font).grid(row=0, column=2, padx=5)
        self.ai_new_col_entry = ctk.CTkEntry(param_frame, placeholder_text=_("描述/解释"), height=35,
                                             font=self.app_font)
        self.ai_new_col_entry.grid(row=0, column=3, sticky="ew")

        ai_proxy_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        ai_proxy_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        self.ai_proxy_switch = ctk.CTkSwitch(ai_proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.ai_proxy_var, font=self.app_font)
        self.ai_proxy_switch.pack(side="left")

        self.ai_start_button = ctk.CTkButton(page, text=_("开始AI任务"), height=40, command=self.start_ai_task,
                                             font=self.app_font_bold)
        self.ai_start_button.pack(fill="x", padx=20, pady=(0, 20), side="bottom")

        # 初始时，根据下拉菜单的默认值显示正确的Prompt输入框
        self._on_ai_task_type_change(self.ai_task_type_var.get())

    def _on_ai_task_type_change(self, choice):
        """根据AI任务类型切换显示的Prompt输入框。"""
        if choice == _("分析"):
            self.ai_analyze_prompt_textbox.grid()
            self.ai_translate_prompt_textbox.grid_remove()
        else:  # 默认为翻译
            self.ai_translate_prompt_textbox.grid()
            self.ai_analyze_prompt_textbox.grid_remove()

    def start_annotation_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.anno_input_file_entry.get().strip()
        gene_col = self.anno_gene_col_entry.get().strip()
        output_dir_parent = os.path.dirname(input_file) if input_file else "."
        output_dir = os.path.join(output_dir_parent, "annotation_results")

        if not input_file or not gene_col:
            self.show_error_message(_("输入缺失"), _("请输入文件路径和基因列名。"))
            return

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        if not anno_types:
            self.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。"))
            return

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("功能注释")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)  # 使用不确定模式
        self.progress_bar.start()

        threading.Thread(target=run_functional_annotation, kwargs={
            "config": self.current_config, "input_file": input_file, "output_dir": output_dir,
            "annotation_types": anno_types, "gene_column_name": gene_col,
            "status_callback": self.gui_status_callback
        }, daemon=True).start()

    def start_ai_task(self):
        """启动AI任务，并从正确的UI控件获取Prompt。"""
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.ai_input_file_entry.get().strip()
        source_col = self.ai_source_col_entry.get().strip()
        new_col = self.ai_new_col_entry.get().strip()
        task_type_display = self.ai_task_type_var.get()

        if not all([input_file, source_col, new_col]):
            self.show_error_message(_("输入缺失"), _("请输入文件路径、源列名和新列名。"));
            return

        # --- 根据任务类型从对应的输入框获取Prompt ---
        task_type = "analyze" if task_type_display == _("分析") else "translate"
        if task_type == 'analyze':
            prompt = self.ai_analyze_prompt_textbox.get("1.0", tk.END).strip()
        else:
            prompt = self.ai_translate_prompt_textbox.get("1.0", tk.END).strip()

        if not prompt or "{text}" not in prompt:
            self.show_error_message(_("Prompt格式错误"), _("Prompt指令不能为空，且必须包含占位符 '{text}'。"));
            return
        # --- 修改结束 ---

        temp_config = self.current_config.copy()
        proxy_status_msg = "OFF"
        if self.ai_proxy_var.get():
            proxies_cfg = self.current_config.get("downloader", {}).get("proxies")
            if not proxies_cfg or not (proxies_cfg.get('http') or proxies_cfg.get('httpss')):
                self.show_warning_message(_("代理未配置"), _("您开启了代理开关，但配置文件中未找到有效的代理地址。"))
                return
            proxy_status_msg = "ON"
        else:
            temp_config['downloader'] = self.current_config.get('downloader', {}).copy()
            temp_config['downloader']['proxies'] = None

        output_dir_parent = os.path.dirname(input_file)
        output_dir = os.path.join(output_dir_parent, "ai_results")

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("AI 助手")
        self._log_to_viewer(
            f"{self.active_task_name} ({task_type_display}) {_('任务开始...')} ({_('代理')}: {proxy_status_msg})")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        def task_wrapper():
            success = False
            try:
                success = run_ai_task(
                    config=temp_config, input_file=input_file, output_dir=output_dir,
                    source_column=source_col, new_column=new_col, task_type=task_type,
                    custom_prompt_template=prompt, status_callback=self.gui_status_callback
                )
            except Exception as e:
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

        # cotton_tool/gui_app.py

    def _update_ai_assistant_tab_info(self):
        """
        更新AI助手页面的配置信息显示。
        在尝试操作控件前先检查它们是否存在，以兼容懒加载。
        """
        if not hasattr(self, 'ai_info_provider_label') or not self.ai_info_provider_label.winfo_exists():
            self._log_to_viewer("DEBUG: AI assistant info labels not yet created, skipping update.", "DEBUG")
            return

        if not self.current_config:
            provider, model, key_status = "-", "-", _("未加载配置")
            key_color = self.secondary_text_color
        else:
            # 直接通过属性访问dataclass对象
            ai_cfg = self.current_config.ai_services
            provider_name = ai_cfg.default_provider
            provider_cfg = ai_cfg.providers.get(provider_name)  # 获取ProviderConfig对象

            # 为了兼容旧的显示逻辑，我们反向查找一下显示名称
            provider_display_name = provider_name
            for p_key, p_info in self.AI_PROVIDERS.items():
                if p_key == provider_name:
                    provider_display_name = p_info.get('name', provider_name)
                    break

            if provider_cfg:
                model = provider_cfg.model
                api_key = provider_cfg.api_key
            else:
                model = _("未设置")
                api_key = ""

            if not api_key or "YOUR_" in api_key or not api_key.strip():
                key_status = _("未配置或无效")
                key_color = ("#d9534f", "#e57373")  # red
            else:
                key_status = f"{api_key[:5]}...{api_key[-4:]} ({_('已配置')})"
                key_color = ("#28a745", "#73bf69")  # green

            provider = provider_display_name  # 使用显示名称

        self.ai_info_provider_label.configure(text=f"{_('服务商')}: {provider}")
        self.ai_info_model_label.configure(text=f"{_('模型')}: {model}")
        self.ai_info_key_label.configure(text=f"{_('API Key')}: {key_status}", text_color=key_color)

    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(placeholder_text_key)

            # 根据当前外观模式动态选择单一颜色值
            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[
                1]
            textbox_widget.configure(text_color=placeholder_color_value)

            textbox_widget.insert("0.0", placeholder)

    def _handle_textbox_focus_in(self, event, textbox_widget, placeholder_text_key):
        """当Textbox获得焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        placeholder = _(placeholder_text_key)

        # 检查当前文本是否为占位符
        # 一个更稳妥的检查方式是同时判断内容和颜色
        current_ph_color_tuple = self.placeholder_color
        current_mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0

        is_placeholder = False
        if current_text == placeholder:
            # 尝试获取颜色，如果失败则假定为占位符
            try:
                if textbox_widget.cget("text_color") == current_ph_color_tuple[current_mode_idx]:
                    is_placeholder = True
            except (AttributeError, IndexError):
                is_placeholder = True

        if is_placeholder:
            textbox_widget.delete("1.0", tk.END)
            # 【重要修复】使用在__init__中定义的、适配亮/暗模式的默认颜色元组
            # CTkTextbox.configure 方法可以正确处理颜色元组
            textbox_widget.configure(text_color=self.default_text_color)

    def set_app_icon(self):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 加载主窗口图标失败: {e}。")

    # --- 新增：创建工具栏的方法 ---
    def _create_toolbar(self):
        toolbar_frame = ctk.CTkFrame(self, corner_radius=0, height=45)
        toolbar_frame.pack(side="top", fill="x", padx=0, pady=0)

        load_btn = ctk.CTkButton(toolbar_frame, text=_("加载配置..."), width=100, font=self.toolbar_font,
                                 command=self.load_config_file)
        load_btn.pack(side="left", padx=(10, 5), pady=8)
        self.translatable_widgets[load_btn] = "加载配置..."

        gen_btn = ctk.CTkButton(toolbar_frame, text=_("生成配置..."), width=100, font=self.toolbar_font,
                                command=self._generate_default_configs_gui)
        gen_btn.pack(side="left", padx=5, pady=8)
        self.translatable_widgets[gen_btn] = "生成配置..."

        help_btn = ctk.CTkButton(toolbar_frame, text=_("在线文档"), width=90, font=self.toolbar_font,
                                 command=self._open_online_help)
        help_btn.pack(side="left", padx=(20, 5), pady=8)
        self.translatable_widgets[help_btn] = "在线文档"

        about_btn = ctk.CTkButton(toolbar_frame, text=_("关于"), width=60, font=self.toolbar_font,
                                  command=self.show_about_dialog)
        about_btn.pack(side="left", padx=5, pady=8)
        self.translatable_widgets[about_btn] = "关于"

        exit_btn = ctk.CTkButton(toolbar_frame, text=_("退出"), width=60, font=self.toolbar_font,
                                 command=self.on_closing, fg_color=("#D32F2F", "#B71C1C"),
                                 hover_color=("#E53935", "#C62828"))
        exit_btn.pack(side="right", padx=10, pady=8)
        self.translatable_widgets[exit_btn] = "退出"

    def _open_online_help(self):  #
        try:
            self._log_to_viewer(_("正在浏览器中打开在线帮助文档..."))  #
            webbrowser.open(PKG_HELP_URL)  #
        except Exception as e:  #
            self.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))  #

    def _create_config_widgets_structure(self):

        self.config_frame = ctk.CTkFrame(self.main_container)
        self.config_frame.pack(side="top", pady=(5, 5), padx=10, fill="x")
        self.config_frame.grid_columnconfigure(0, weight=1)
        self.config_path_label_base_key = "配置文件"
        self.config_path_display_part = lambda: os.path.basename(self.config_path) if self.config_path else _(
            "未加载 (请点击“加载配置...”)")
        self.config_path_label = ctk.CTkLabel(self.config_frame,
                                              text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}",
                                              font=self.app_font, anchor="w")
        self.translatable_widgets[self.config_path_label] = ("label_with_dynamic_part", self.config_path_label_base_key,
                                                             self.config_path_display_part)
        self.config_path_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.language_label = ctk.CTkLabel(self.config_frame, text=_("语言:"), font=self.app_font)
        self.translatable_widgets[self.language_label] = "语言:"
        self.language_label.grid(row=0, column=1, padx=(10, 5), pady=10)
        self.language_optionmenu = ctk.CTkOptionMenu(self.config_frame, variable=self.selected_language_var,
                                                     values=list(self.LANG_CODE_TO_NAME.values()),
                                                     command=self.on_language_change, font=self.app_font,
                                                     dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=0, column=2, padx=(0, 10), pady=10)

    def change_appearance_mode_event(self, selected_display_mode: str):
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(selected_display_mode, "System")
        ctk.set_appearance_mode(new_mode)

        # 更新日志颜色以匹配新模式
        self._update_log_tag_colors()

        # 更新并保存UI设置
        self.ui_settings['appearance_mode'] = new_mode
        self.ui_settings['appearance_mode_display'] = selected_display_mode
        self._save_ui_settings()

    def on_language_change(self, selected_display_name: str):
        new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "en")

        # 更新并保存UI设置
        self.ui_settings['language'] = new_language_code
        self._save_ui_settings()

        self.update_language_ui(new_language_code)

    def _create_status_widgets_structure(self):
        self.status_bar_frame = ctk.CTkFrame(self.main_container, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar_frame.grid_columnconfigure(0, weight=1)
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.translatable_widgets[self.status_label] = ("label_with_dynamic_part", self.status_label_base_key,
                                                        lambda: "")
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()

    def _create_log_viewer_structure(self, parent):
        self.log_viewer_frame = ctk.CTkFrame(parent)
        self.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(self.log_viewer_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(log_header_frame, text=_("清除日志"), width=80, height=28, command=self.clear_log_viewer,
                      font=self.app_font).grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(self.log_viewer_frame, height=140, state="disabled", wrap="word",
                                          font=self.app_font)
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.log_textbox.tag_config("error_log", foreground="#d9534f")
        self.log_textbox.tag_config("warning_log", foreground="#f0ad4e")

    def _create_tab_view_structure(self):
        self.tab_view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_view_frame.pack(side="bottom", fill="both", expand=True, padx=10, pady=5)
        self.tab_view = ctk.CTkTabview(self.tab_view_frame, corner_radius=8)
        if hasattr(self.tab_view, '_segmented_button'):
            self.tab_view._segmented_button.configure(font=self.app_font)
        self.tab_view.pack(fill="both", expand=True, padx=0, pady=0)
        self.download_tab_internal_key = "DOWNLOAD_TAB_INTERNAL"
        self.integrate_tab_internal_key = "INTEGRATE_TAB_INTERNAL"
        self.homology_map_tab_internal_key = "HOMOLOGY_MAP_TAB_INTERNAL"
        self.gff_query_tab_internal_key = "GFF_QUERY_TAB_INTERNAL"
        self.editor_tab_internal_key = "EDITOR_TAB_INTERNAL"
        self.download_tab_display_key = "数据下载"
        self.integrate_tab_display_key = "整合分析"
        self.homology_map_tab_display_key = "基因组转换"
        self.gff_query_tab_display_key = "基因位点查询"
        self.editor_tab_display_key = "配置编辑"
        self.tab_view.add(self.download_tab_internal_key)
        self.tab_view.add(self.integrate_tab_internal_key)
        self.tab_view.add(self.homology_map_tab_internal_key)
        self.tab_view.add(self.gff_query_tab_internal_key)
        self.tab_view.add(self.editor_tab_internal_key)
        self._populate_download_tab_structure()
        self._populate_integrate_tab_structure()
        self._populate_homology_map_tab_structure()
        self._populate_gff_query_tab_structure()

    def _populate_download_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        target_card = ctk.CTkFrame(page)
        target_card.pack(fill="both", expand=True, pady=(15, 10), padx=15)
        target_card.grid_columnconfigure(0, weight=1)
        target_card.grid_rowconfigure(2, weight=1)

        target_header_frame = ctk.CTkFrame(target_card, fg_color="transparent")
        target_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        target_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(target_header_frame, text=_("下载目标: 选择基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                            column=0,
                                                                                                            sticky="w")

        selection_buttons_frame = ctk.CTkFrame(target_header_frame, fg_color="transparent")
        selection_buttons_frame.grid(row=0, column=1, sticky="e")

        self.dl_select_all_button = ctk.CTkButton(selection_buttons_frame, text=_("全选"), width=80, height=28,
                                                  font=self.app_font,
                                                  command=lambda: self._toggle_all_download_genomes(True))
        self.dl_deselect_all_button = ctk.CTkButton(selection_buttons_frame, text=_("取消全选"), width=90, height=28,
                                                    font=self.app_font,
                                                    command=lambda: self._toggle_all_download_genomes(False))
        self.dl_select_all_button.pack(side="left", padx=(0, 10))
        self.dl_deselect_all_button.pack(side="left")

        ctk.CTkLabel(target_card, text=_("勾选需要下载的基因组版本。若不勾选任何项，将默认下载所有可用版本。"),
                     text_color=self.secondary_text_color, font=self.app_font, wraplength=500).grid(row=1, column=0,
                                                                                                    padx=10,
                                                                                                    pady=(0, 10),
                                                                                                    sticky="w")

        self.download_genomes_checkbox_frame = ctk.CTkScrollableFrame(target_card, label_text="")
        self.download_genomes_checkbox_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._bind_mouse_wheel_to_scrollable(self.download_genomes_checkbox_frame)

        self._bind_mouse_wheel_to_scrollable(self.download_genomes_checkbox_frame)

        options_frame = ctk.CTkFrame(page)
        options_frame.pack(fill="x", expand=False, pady=10, padx=15)
        options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options_frame, text=_("下载选项"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                      padx=10, pady=(10, 15),
                                                                                      sticky="w")

        # --- 代理开关 ---
        proxy_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        proxy_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.dl_proxy_switch = ctk.CTkSwitch(proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.download_proxy_var, font=self.app_font)
        self.dl_proxy_switch.pack(side="left")

        force_download_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        force_download_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))
        self.dl_force_switch_label = ctk.CTkLabel(force_download_frame, text=_("强制重新下载:"), font=self.app_font)
        self.dl_force_switch_label.pack(side="left", padx=(0, 10))
        self.dl_force_switch = ctk.CTkSwitch(force_download_frame, text="", variable=self.download_force_checkbox_var)
        self.dl_force_switch.pack(side="left")

        self.download_start_button = ctk.CTkButton(page, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.download_start_button.pack(fill="x", padx=15, pady=(10, 15), side="bottom")

    def browse_download_output_dir(self):
        """
        打开文件夹选择对话框，让用户选择下载文件的输出目录。
        """
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory and self.download_output_dir_entry:
            self.download_output_dir_entry.delete(0, tk.END)
            self.download_output_dir_entry.insert(0, directory)

    def _update_download_genomes_list(self):
        """
        根据当前配置，动态更新下载页面的基因组版本复选框列表，并高亮显示已存在的项。
        在尝试操作 download_genomes_checkbox_frame 之前，检查其是否存在。
        """
        # 优化：在操作控件前先检查其是否存在
        if not hasattr(self,
                       'download_genomes_checkbox_frame') or not self.download_genomes_checkbox_frame.winfo_exists():
            self._log_to_viewer("DEBUG: download_genomes_checkbox_frame does not exist yet, skipping update.", "DEBUG")
            return  # 如果控件还未创建，则跳过此次更新

        # 清理旧的复选框和变量
        for widget in self.download_genomes_checkbox_frame.winfo_children():
            widget.destroy()
        self.download_genome_vars.clear()

        # 定义颜色 (亮色模式, 暗色模式)
        existing_item_color = ("#28a745", "#73bf69")
        default_color = self.default_label_text_color

        if not self.current_config:
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("请先加载配置文件"),
                         text_color=self.secondary_text_color).pack()
            return

        genome_sources = get_genome_data_sources(self.current_config)
        downloader_cfg = self.current_config.get("downloader", {})
        base_download_dir = downloader_cfg.get("download_output_base_dir", "downloaded_cotton_data")

        if not genome_sources or not isinstance(genome_sources, dict):
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("配置文件中未找到基因组源"),
                         text_color=self.secondary_text_color).pack()
            return

        # 为每个基因组版本创建一个复选框
        for genome_id, details in genome_sources.items():
            var = tk.BooleanVar(value=False)
            species_name = details.get('species_name', _('未知物种'))
            display_text = f"{genome_id} ({species_name})"

            # --- 检查目录是否存在 ---
            safe_dir_name = species_name.replace(" ", "_").replace(".", "_").replace("(", "").replace(")", "").replace(
                "'", "")
            version_output_dir = os.path.join(base_download_dir, safe_dir_name)
            text_color_to_use = existing_item_color if os.path.exists(version_output_dir) else default_color

            cb = ctk.CTkCheckBox(
                self.download_genomes_checkbox_frame,
                text=display_text,
                variable=var,
                font=self.app_font,
                text_color=text_color_to_use
            )
            cb.pack(anchor="w", padx=10, pady=5)
            self.download_genome_vars[genome_id] = var

    def _toggle_all_download_genomes(self, select: bool):
        """全选或取消全选所有下载基因组的复选框"""
        for var in self.download_genome_vars.values():
            var.set(select)

    def _populate_integrate_tab_structure(self):
        page = self.tab_view.tab(self.integrate_tab_internal_key)
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Card 1: Input Data
        input_frame = ctk.CTkFrame(scrollable_frame)
        input_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        input_frame.grid_columnconfigure(1, weight=1)

        input_label = ctk.CTkLabel(input_frame, text=_("输入数据"), font=self.app_font_bold)
        self.translatable_widgets[input_label] = "输入数据"
        input_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        excel_path_label = ctk.CTkLabel(input_frame, text=_("Excel文件路径:"), font=self.app_font)
        self.translatable_widgets[excel_path_label] = "Excel文件路径:"
        excel_path_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.integrate_excel_entry] = "从配置加载或在此覆盖"
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_frame, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_frame, text=_("BSA数据工作表:"), font=self.app_font)
        self.translatable_widgets[bsa_sheet_label] = "BSA数据工作表:"
        bsa_sheet_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_frame, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 10), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_frame, text=_("HVG数据工作表:"), font=self.app_font)
        self.translatable_widgets[hvg_sheet_label] = "HVG数据工作表:"
        hvg_sheet_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_hvg_sheet_dropdown = ctk.CTkOptionMenu(input_frame, variable=self.selected_hvg_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_hvg_sheet_dropdown.grid(row=3, column=1, columnspan=2, padx=(0, 10), pady=10, sticky="ew")

        # Card 2: Genome Versions
        version_frame = ctk.CTkFrame(scrollable_frame)
        version_frame.pack(fill="x", expand=True, pady=10, padx=5)
        version_frame.grid_columnconfigure(1, weight=1)

        version_label = ctk.CTkLabel(version_frame, text=_("基因组版本"), font=self.app_font_bold)
        self.translatable_widgets[version_label] = "基因组版本"
        version_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        bsa_assembly_label = ctk.CTkLabel(version_frame, text=_("BSA基因组版本:"), font=self.app_font)
        self.translatable_widgets[bsa_assembly_label] = "BSA基因组版本:"
        bsa_assembly_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_frame, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_frame, text=_("HVG基因组版本:"), font=self.app_font)
        self.translatable_widgets[hvg_assembly_label] = "HVG基因组版本:"
        hvg_assembly_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_frame, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        # Start Button
        self.integrate_start_button = ctk.CTkButton(scrollable_frame, text=_("开始整合分析"), height=40,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始整合分析"
        self.integrate_start_button.pack(fill="x", padx=5, pady=(10, 5))

    def _populate_homology_map_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        container = ctk.CTkFrame(page, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure((0, 1), weight=1)
        container.grid_rowconfigure(1, weight=1)
        input_frame = ctk.CTkFrame(container)
        input_frame.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=15, sticky="nsew")
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text=_("输入基因与版本"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                          padx=10, pady=(10, 15),
                                                                                          sticky="w")

        self.homology_map_genes_entry = ctk.CTkTextbox(input_frame, font=self.app_font, wrap="none")
        self.homology_map_genes_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.homology_map_genes_entry.insert("0.0", _(self.placeholder_genes_homology_key))

        # 根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.homology_map_genes_entry.configure(text_color=placeholder_color_value)

        self.homology_map_genes_entry.bind("<FocusIn>",
                                           lambda e: self._handle_textbox_focus_in(e, self.homology_map_genes_entry,
                                                                                   self.placeholder_genes_homology_key))
        self.homology_map_genes_entry.bind("<FocusOut>",
                                           lambda e: self._handle_textbox_focus_out(e, self.homology_map_genes_entry,
                                                                                    self.placeholder_genes_homology_key))

        ctk.CTkLabel(input_frame, text=_("源基因组版本:"), font=self.app_font).grid(row=2, column=0, padx=10, pady=10,
                                                                                    sticky="w")
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_source_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_source_assembly_dropdown.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(input_frame, text=_("目标基因组版本:"), font=self.app_font).grid(row=4, column=0, padx=10, pady=10,
                                                                                      sticky="w")
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_target_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_target_assembly_dropdown.grid(row=5, column=0, columnspan=2, padx=10, pady=(5, 10),
                                                        sticky="ew")
        file_frame = ctk.CTkFrame(container)
        file_frame.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="new")
        file_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(file_frame, text=_("同源与输出文件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                         padx=10, pady=(10, 15),
                                                                                         sticky="w")
        ctk.CTkLabel(file_frame, text=_("源到桥梁文件:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                   pady=5, sticky="w")
        self.homology_map_sb_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_sb_file_entry.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("桥梁到目标文件:"), font=self.app_font).grid(row=3, column=0, padx=(10, 5),
                                                                                     pady=5, sticky="w")
        self.homology_map_bt_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_bt_file_entry.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("结果输出CSV文件:"), font=self.app_font).grid(row=5, column=0, padx=(10, 5),
                                                                                      pady=5, sticky="w")
        self.homology_map_output_csv_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_output_csv_entry.grid(row=6, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        self.homology_map_start_button = ctk.CTkButton(container, text=_("开始同源映射"), height=40,
                                                       command=self.start_homology_map_task, font=self.app_font_bold)
        self.homology_map_start_button.grid(row=1, column=1, padx=(5, 15), pady=15, sticky="sew")

    def _populate_gff_query_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        query_frame = ctk.CTkFrame(page)
        query_frame.pack(fill="x", padx=15, pady=(15, 10))
        query_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(query_frame, text=_("查询条件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                    padx=10, pady=(10, 15), sticky="w")
        ctk.CTkLabel(query_frame, text=_("基因组版本ID:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                    pady=10, sticky="w")
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(query_frame, font=self.app_font, height=35,
                                                             variable=self.selected_gff_query_assembly,
                                                             values=[_("加载中...")], dropdown_font=self.app_font)
        self.gff_query_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ctk.CTkLabel(query_frame, text=_("染色体区域:"), font=self.app_font).grid(row=2, column=0, padx=(10, 5),
                                                                                  pady=10, sticky="w")
        self.gff_query_region_entry = ctk.CTkEntry(query_frame, font=self.app_font, height=35,
                                                   placeholder_text=_("例如: chr1:1000-5000 (与下方基因ID二选一)"))
        self.gff_query_region_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        gene_list_frame = ctk.CTkFrame(page)
        gene_list_frame.pack(fill="both", expand=True, padx=15, pady=10)
        gene_list_frame.grid_columnconfigure(0, weight=1)
        gene_list_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(gene_list_frame, text=_("或输入基因ID (每行一个):"), font=self.app_font).grid(row=0, column=0,
                                                                                                   padx=10, pady=5,
                                                                                                   sticky="w")

        self.gff_query_genes_entry = ctk.CTkTextbox(gene_list_frame, font=self.app_font, wrap="none")
        self.gff_query_genes_entry.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.gff_query_genes_entry.insert("0.0", _(self.placeholder_genes_gff_key))

        # 根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.gff_query_genes_entry.configure(text_color=placeholder_color_value)

        self.gff_query_genes_entry.bind("<FocusIn>",
                                        lambda e: self._handle_textbox_focus_in(e, self.gff_query_genes_entry,
                                                                                self.placeholder_genes_gff_key))
        self.gff_query_genes_entry.bind("<FocusOut>",
                                        lambda e: self._handle_textbox_focus_out(e, self.gff_query_genes_entry,
                                                                                 self.placeholder_genes_gff_key))

        output_frame = ctk.CTkFrame(page)
        output_frame.pack(fill="x", padx=15, pady=10)
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font).pack(padx=10, pady=5, anchor="w")
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font, height=35,
                                                       placeholder_text=_("可选, 默认自动生成"))
        self.gff_query_output_csv_entry.pack(padx=10, pady=5, fill="x")
        self.gff_query_start_button = ctk.CTkButton(page, text=_("开始基因查询"), height=40,
                                                    command=self.start_gff_query_task, font=self.app_font_bold)
        self.gff_query_start_button.pack(fill="x", padx=15, pady=15)

    def _load_initial_config(self):
        """
        在后台线程中异步加载配置文件，并更新UI。
        显示一个启动进度对话框。
        """
        # 立即显示启动进度对话框
        self._show_progress_dialog(
            title=_("图形界面启动中..."),  # <-- 修改这里
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None  # 启动阶段不允许取消
        )

        def startup_task_thread():

            loaded_config_data = None
            config_file_path = None
            genome_sources_data = None

            try:
                self.startup_progress_queue.put((10, _("加载配置文件...")))
                # ... (加载配置文件的逻辑) ...

                self.startup_progress_queue.put((30, _("应用配置到UI...")))
                # **重要：先发送更新配置的数据到主线程**
                self.message_queue.put(("set_initial_config", (loaded_config_data, config_file_path)))
                # 在这里等待主线程处理完 `set_initial_config` 并完成大部分UI属性设置，
                # 但不阻塞当前后台线程太久，仅提供一个建议的等待点。
                # 实际Tkinter的UI更新是异步的，无法直接在这里完全同步。

                self.startup_progress_queue.put((50, _("更新基因组信息...")))
                # ... (get_genome_data_sources 逻辑) ...
                self.message_queue.put(("update_genome_dropdowns_async", genome_sources_data))  #

                self.startup_progress_queue.put((70, _("构建编辑器及工具UI...")))
                # **重要：在这里发送消息触发编辑器UI的构建和填充**
                self.message_queue.put(("populate_editor_ui_async", None))
                # 如果有其他懒加载的UI需要在启动时强制创建，也在这里发送消息

                self.startup_progress_queue.put((90, _("完成基本初始化...")))

            except Exception as e:
                self.startup_progress_queue.put((100, f"[ERROR] {_('启动过程中发生未知错误:')} {e}"))
                self.initial_config_loaded.set()
                return
            finally:
                # 无论成功失败，都标记初始配置加载完成
                self.initial_config_loaded.set()
                # 确保所有UI更新消息都已发送到队列，然后发送最终完成消息
                self.startup_progress_queue.put((100, _("启动完成！")))

        threading.Thread(target=startup_task_thread, daemon=True).start()

    def _apply_config_to_ui(self):
        """
        【已修正】根据 self.current_config 的状态，更新整个应用程序的UI。
        """
        self._log_to_viewer(_("正在应用配置到整个UI..."))

        # 更新主页的配置路径显示
        if self.config_path:
            path_text = _("当前配置: {}").format(os.path.basename(self.config_path))
        else:
            path_text = _("未加载配置")

        if hasattr(self, 'config_path_label') and self.config_path_label.winfo_exists():
            self.config_path_label.configure(text=path_text)

        # 【核心修复】现在调用新的主控方法，它只会更新值，不会重建UI
        if hasattr(self, 'editor_frame') and self.editor_frame.winfo_exists():
            self._handle_editor_ui_update()

        # 更新整合分析页面
        if hasattr(self, 'integrate_frame') and self.integrate_frame.winfo_exists():
            if self.current_config:
                pipe_cfg = self.current_config.integration_pipeline
                self.integrate_excel_entry.delete(0, tk.END)
                self.integrate_excel_entry.insert(0, pipe_cfg.input_excel_path or "")
                self._update_assembly_id_dropdowns()
                self._update_excel_sheet_dropdowns()
                self.selected_bsa_assembly.set(pipe_cfg.bsa_assembly_id)
                self.selected_hvg_assembly.set(pipe_cfg.hvg_assembly_id)
            else:
                self.integrate_excel_entry.delete(0, tk.END)
                self.selected_bsa_sheet.set(_("请先指定Excel文件"))
                self.selected_hvg_sheet.set(_("请先指定Excel文件"))
                self.selected_bsa_assembly.set(_("无可用版本"))
                self.selected_hvg_assembly.set(_("无可用版本"))

        # 更新所有工具页面
        if hasattr(self, 'tools_notebook') and self.tools_notebook.winfo_exists():
            self._update_download_genomes_list()
            self._update_ai_assistant_tab_info()
            self._load_prompts_to_ai_tab()
            if self.current_config:
                pipe_cfg = self.current_config.integration_pipeline
                self.selected_homology_source_assembly.set(pipe_cfg.bsa_assembly_id)
                self.selected_homology_target_assembly.set(pipe_cfg.hvg_assembly_id)
                self.selected_gff_query_assembly.set(pipe_cfg.bsa_assembly_id or pipe_cfg.hvg_assembly_id)

        # 更新所有按钮状态
        self._update_button_states()
        self._log_to_viewer(_("UI已根据当前配置刷新。"))

    def _handle_editor_ui_update(self):
        """
        【新方法】智能更新或创建配置编辑器UI。
        这是现在所有需要操作编辑器UI的地方都应该调用的唯一入口。
        """
        # 1. 检查父容器是否存在
        if not hasattr(self, 'editor_scroll_frame') or not self.editor_scroll_frame.winfo_exists():
            return

        # 2. 使用一个标志来判断UI是否已创建。如果没有标志，则在 self 上初始化它。
        if not hasattr(self, 'editor_ui_built'):
            self.editor_ui_built = False

        # 3. 如果UI还没有被构建
        if not self.editor_ui_built:
            self._log_to_viewer("DEBUG: Editor UI not built. Creating for the first time...", "DEBUG")

            # 清理可能存在的占位符文本
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()

            # 只有在存在配置时才构建UI
            if self.current_config:
                self._create_editor_widgets(self.editor_scroll_frame)
                self.editor_ui_built = True  # 设置标志，表示UI已创建
                self.save_editor_button.configure(state="normal")
            else:
                # 如果没有配置，显示提示信息
                ctk.CTkLabel(self.editor_scroll_frame, text=_("请先从“主页”加载或生成一个配置文件。"),
                             font=self.app_subtitle_font, text_color=self.secondary_text_color).grid(row=0, column=0,
                                                                                                     pady=50,
                                                                                                     sticky="nsew")
                self.editor_scroll_frame.grid_rowconfigure(0, weight=1)
                if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")
                return  # 不往下执行数据填充

        # 4. 无论UI是刚创建的还是已存在的，都用当前配置数据填充/更新它
        if self.current_config:
            self._apply_config_values_to_editor()
        else:
            # 如果到这里仍然没有配置（例如，程序刚启动且无默认配置），则禁用保存按钮
            if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")

    def _setup_fonts(self):
        """设置全局字体，并实现字体栈回退机制。"""
        # 定义一个字体栈，程序会从前到后依次尝试使用
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        available_fonts = tkfont.families()

        selected_font = "sans-serif"  # 默认的回退字体
        for font_name in font_stack:
            if font_name in available_fonts:
                selected_font = font_name
                print(f"INFO: UI font has been set to: {selected_font}")
                break

        self.app_font = ctk.CTkFont(family=selected_font, size=14)
        self.app_font_bold = ctk.CTkFont(family=selected_font, size=15, weight="bold")
        self.app_subtitle_font = ctk.CTkFont(family=selected_font, size=16)
        self.app_title_font = ctk.CTkFont(family=selected_font, size=24, weight="bold")
        self.app_comment_font = ctk.CTkFont(family=selected_font, size=12)

    def update_language_ui(self, lang_code_to_set=None):
        global _
        if not lang_code_to_set: lang_code_to_set = self.ui_settings.get('language', 'zh-hans')
        try:
            _ = setup_cli_i18n(language_code=lang_code_to_set, app_name="cotton_toolkit")
        except Exception as e:
            _ = lambda s: s
            logging.error(f"语言设置错误: {e}")

        # 1. 更新普通控件
        for widget, info in self.translatable_widgets.items():
            if not (widget and widget.winfo_exists()): continue
            if isinstance(info, tuple):
                op, data = info[0], info[1:]
                if op == "values": widget.configure(values=[_(v) for v in data[0]])
            elif isinstance(info, str):
                widget.configure(text=_(info))

        # --- 注册并更新下载页面的新按钮 ---
        if hasattr(self, 'dl_select_all_button'):
            self.dl_select_all_button.configure(text=_("全选"))
        if hasattr(self, 'dl_deselect_all_button'):
            self.dl_deselect_all_button.configure(text=_("取消全选"))
        if hasattr(self, 'dl_force_switch_label'):
            self.dl_force_switch_label.configure(text=_("强制重新下载:"))

        # 2. 更新下拉菜单的当前显示值
        display_lang_name = self.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        if hasattr(self, 'language_optionmenu'): self.language_optionmenu.set(display_lang_name)
        if hasattr(self, 'appearance_mode_optionemenu'):
            current_mode_value = self.ui_settings.get('appearance_mode', 'System')
            mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
            display_text = mode_map_to_display.get(current_mode_value, _("系统"))
            self.appearance_mode_optionemenu.set(display_text)

        # 3. 更新工具选项卡的显示文本
        if hasattr(self, 'tools_notebook') and hasattr(self.tools_notebook, '_segmented_button'):
            try:
                tab_display_names = {
                    "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
                    "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
                }

                # Get the currently selected tab's frame object to restore selection later
                current_selected_display_name = self.tools_notebook.get()
                current_selected_frame = self.tools_notebook.tab(current_selected_display_name)

                # Prepare the new list of display names and the new tab->frame dictionary
                new_display_values = []
                new_tab_dict = {}
                restored_selection_name = None

                for simple_key, internal_key in self.tab_keys.items():
                    # Use the stable self.tool_tab_frames to get the frame
                    frame = self.tool_tab_frames.get(internal_key)
                    if frame:
                        new_display_name = tab_display_names.get(simple_key, internal_key)
                        new_display_values.append(new_display_name)
                        new_tab_dict[new_display_name] = frame
                        # Check if this is the frame we need to re-select
                        if frame == current_selected_frame:
                            restored_selection_name = new_display_name

                # Atomically update the internal state of the CTkTabView
                self.tools_notebook._tab_dict = new_tab_dict
                self.tools_notebook._name_list = new_display_values
                self.tools_notebook._segmented_button.configure(values=new_display_values)

                # Restore the selection with the new (translated) display name
                if restored_selection_name:
                    self.tools_notebook.set(restored_selection_name)

            except Exception as e:
                logging.error(f"动态更新TabView时发生严重错误: {e}")

        # 4. 更新窗口标题
        self.title(_(self.title_text_key))

    def _update_assembly_id_dropdowns(self):
        """直接将配置对象传递给后台函数。"""
        if not self.current_config:
            return
        self._log_to_viewer(_("正在更新基因组版本列表..."))

        genome_sources = get_genome_data_sources(self.current_config)

        if genome_sources and isinstance(genome_sources, dict):
            assembly_ids = list(genome_sources.keys())
            if not assembly_ids:
                assembly_ids = [_("无可用版本")]
        else:
            assembly_ids = [_("无法加载基因组源")]
            self._log_to_viewer(_("警告: 未能从配置文件或源文件中加载基因组列表。"), level="WARNING")

        # --- 为“基因组转换”的目标下拉菜单准备一个特殊的列表 ---
        homology_target_ids = assembly_ids.copy()
        # 在列表最前面插入我们的新选项
        homology_target_ids.insert(0, _("拟南芥 (根据源基因组自动选择)"))
        # ---------------------------------------------------

        # 整合分析 - BSA基因组下拉菜单
        if hasattr(self, 'integrate_bsa_assembly_dropdown') and self.integrate_bsa_assembly_dropdown.winfo_exists():
            self.integrate_bsa_assembly_dropdown.configure(values=assembly_ids)

        # 整合分析 - HVG基因组下拉菜单
        if hasattr(self, 'integrate_hvg_assembly_dropdown') and self.integrate_hvg_assembly_dropdown.winfo_exists():
            self.integrate_hvg_assembly_dropdown.configure(values=assembly_ids)

        # 基因组转换 - 源基因组下拉菜单
        if hasattr(self,
                   'homology_map_source_assembly_dropdown') and self.homology_map_source_assembly_dropdown.winfo_exists():
            self.homology_map_source_assembly_dropdown.configure(values=assembly_ids)

        # --- MODIFICATION START ---
        # 基因组转换 - 目标基因组下拉菜单 (使用我们准备的特殊列表)
        if hasattr(self,
                   'homology_map_target_assembly_dropdown') and self.homology_map_target_assembly_dropdown.winfo_exists():
            self.homology_map_target_assembly_dropdown.configure(values=homology_target_ids)
        # --- MODIFICATION END ---

        # GFF 查询 - 基因组下拉菜单
        if hasattr(self, 'gff_query_assembly_dropdown') and self.gff_query_assembly_dropdown.winfo_exists():
            self.gff_query_assembly_dropdown.configure(values=assembly_ids)
        # 遍历所有可能的下拉菜单，如果它们已经存在，就更新它们
        if hasattr(self, 'integrate_bsa_assembly_dropdown') and self.integrate_bsa_assembly_dropdown.winfo_exists():
            self.integrate_bsa_assembly_dropdown.configure(values=assembly_ids)
            # 尝试设置默认值
            if self.current_config.integration_pipeline.bsa_assembly_id in assembly_ids:
                self.selected_bsa_assembly.set(self.current_config.integration_pipeline.bsa_assembly_id)
            elif assembly_ids and assembly_ids[0] != _("无可用版本") and assembly_ids[0] != _("无法加载基因组源"):
                self.selected_bsa_assembly.set(assembly_ids[0])

        if hasattr(self, 'integrate_hvg_assembly_dropdown') and self.integrate_hvg_assembly_dropdown.winfo_exists():
            self.integrate_hvg_assembly_dropdown.configure(values=assembly_ids)
            if self.current_config.integration_pipeline.hvg_assembly_id in assembly_ids:
                self.selected_hvg_assembly.set(self.current_config.integration_pipeline.hvg_assembly_id)
            elif assembly_ids and assembly_ids[0] != _("无可用版本") and assembly_ids[0] != _("无法加载基因组源"):
                self.selected_hvg_assembly.set(assembly_ids[0])

        # 对于懒加载的选项卡中的下拉菜单，当它们被创建时，它们会从 _apply_config_to_ui 再次触发更新，
        # 此时 self.selected_homology_source_assembly 等变量会被正确设置。
        # 这里我们只检查并更新那些可能在启动时就已经存在的（比如“整合分析”页面）。

        # 由于同源映射和GFF查询的下拉菜单是懒加载的，在它们被创建时，
        # 它们会尝试根据 self.selected_homology_source_assembly / self.selected_gff_query_assembly 的值来设置。
        # 所以，我们只需要确保在 `_apply_config_to_ui` 阶段，这些 StringVar 的值被正确设定即可，
        # 不需要在这里提前配置这些下拉菜单的 `values`。
        # 实际的 `configure(values=...)` 和 `set(default_value)` 会在它们各自的 `_populate_xxx_tab_structure` 方法
        # 被调用时，通过 `_update_assembly_id_dropdowns` 再次触发（或者直接在 `_populate_xxx_tab_structure` 内部完成）。
        #
        # 因此，在 `_apply_config_to_ui` 的末尾，更新这些 StringVar 的值：
        # self.selected_homology_source_assembly.set(integration_cfg.bsa_assembly_id)
        # self.selected_homology_target_assembly.set(integration_cfg.hvg_assembly_id)
        # self.selected_gff_query_assembly.set(default_gff_assembly)
        # 这样，当对应的 Tab 被懒加载时，下拉菜单会使用这些已经设置好的值。

    def _update_excel_sheet_dropdowns(self):
        excel_path = self.integrate_excel_entry.get().strip()

        # 如果路径为空或文件不存在，重置下拉菜单并返回
        if not excel_path or not os.path.exists(excel_path):
            self.integrate_bsa_sheet_dropdown.configure(values=[_("请先指定有效的Excel文件")])
            self.integrate_hvg_sheet_dropdown.configure(values=[_("请先指定有效的Excel文件")])
            self.excel_sheet_cache.pop(excel_path, None)  # 从缓存中移除无效路径
            return

        # 如果文件已在缓存中，直接使用缓存数据更新 UI
        if excel_path in self.excel_sheet_cache:
            sheet_names_to_set = self.excel_sheet_cache[excel_path]
            self._update_sheet_dropdowns_ui(sheet_names_to_set)  # 调用新的 UI 更新方法
            return

        # 文件不在缓存中，异步读取
        self._log_to_viewer(_("正在异步读取Excel工作表，请稍候..."))
        # 立即更新 UI，显示加载状态
        self.integrate_bsa_sheet_dropdown.configure(values=[_("读取中...")])
        self.integrate_hvg_sheet_dropdown.configure(values=[_("读取中...")])

        # 启动一个新线程来读取Excel文件
        def load_sheets_thread():
            try:
                xls = pd.ExcelFile(excel_path)  #
                sheet_names_from_file = xls.sheet_names  #
                self.excel_sheet_cache[excel_path] = sheet_names_from_file  # 缓存结果
                # 将结果和 Excel 路径放入主消息队列
                self.message_queue.put(("update_sheets_dropdown", (sheet_names_from_file, excel_path, None)))
            except Exception as e:
                # 将错误信息放入主消息队列
                self.message_queue.put(
                    ("update_sheets_dropdown", ([], excel_path, f"{_('错误: 无法读取Excel文件')}: {e}")))

        threading.Thread(target=load_sheets_thread, daemon=True).start()

    def _update_sheet_dropdowns_ui(self, sheet_names_to_set, excel_path_for_error=None, error_msg=None):
        """
        实际更新Excel Sheet下拉菜单UI的方法。
        这个方法应该只在主线程中通过消息队列调用。
        """
        bsa_dropdown = self.integrate_bsa_sheet_dropdown
        hvg_dropdown = self.integrate_hvg_sheet_dropdown

        if error_msg:
            self._log_to_viewer(f"{error_msg}", level="ERROR")
            sheet_names_to_set = [_("读取Excel失败")]
            # 如果是错误，并且缓存中存在，为了避免下次还报错，可以考虑清除缓存
            if excel_path_for_error and excel_path_for_error in self.excel_sheet_cache:
                self.excel_sheet_cache.pop(excel_path_for_error, None)

        if not sheet_names_to_set:  # 处理空列表或错误情况
            sheet_names_to_set = [_("Excel文件中无工作表")]

        # 更新下拉菜单的值
        if bsa_dropdown and bsa_dropdown.winfo_exists():
            bsa_dropdown.configure(values=sheet_names_to_set)
        if hvg_dropdown and hvg_dropdown.winfo_exists():
            hvg_dropdown.configure(values=sheet_names_to_set)

        # 尝试设置默认选中值
        if self.current_config:
            # 访问 MainConfig 实例的属性，而不是字典的 get 方法
            cfg_bsa_sheet = self.current_config.integration_pipeline.bsa_sheet_name
            cfg_hvg_sheet = self.current_config.integration_pipeline.hvg_sheet_name

            if cfg_bsa_sheet in sheet_names_to_set:
                self.selected_bsa_sheet.set(cfg_bsa_sheet)
            elif sheet_names_to_set and sheet_names_to_set[0] != _("读取Excel失败") and sheet_names_to_set[0] != _(
                    "Excel文件中无工作表"):
                self.selected_bsa_sheet.set(sheet_names_to_set[0])

            if cfg_hvg_sheet in sheet_names_to_set:
                self.selected_hvg_sheet.set(cfg_hvg_sheet)
            elif sheet_names_to_set and sheet_names_to_set[0] != _("读取Excel失败") and sheet_names_to_set[0] != _(
                    "Excel文件中无工作表"):
                self.selected_hvg_sheet.set(sheet_names_to_set[0])

    def browse_integrate_excel(self):  #
        filepath = filedialog.askopenfilename(title=_("选择输入Excel文件"),
                                              filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*")))  #
        if filepath:  #
            self.integrate_excel_entry.delete(0, tk.END)  #
            self.integrate_excel_entry.insert(0, filepath)  #
            self._update_excel_sheet_dropdowns()  #

    def start_integrate_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("联合分析")

        # 将UI参数收集移到包装器内部，确保在线程中获取最新值
        def task_wrapper():
            success = False
            try:
                cfg_pipeline = self.current_config.setdefault('integration_pipeline', {})
                cfg_pipeline['bsa_assembly_id'] = self.selected_bsa_assembly.get()
                cfg_pipeline['hvg_assembly_id'] = self.selected_hvg_assembly.get()
                cfg_pipeline['bsa_sheet_name'] = self.selected_bsa_sheet.get()
                cfg_pipeline['hvg_sheet_name'] = self.selected_hvg_sheet.get()
                excel_override = self.integrate_excel_entry.get().strip() or None

                self.gui_status_callback(f"{self.active_task_name} {_('任务开始...')}")
                self.progress_bar.grid();
                self.progress_bar.set(0)

                success = integrate_bsa_with_hvg(
                    config=self.current_config,
                    input_excel_path_override=excel_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback,
                )
            except Exception as e:
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

    def start_homology_map_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因组转换")

        gene_ids_text = self.homology_map_genes_entry.get("1.0", tk.END).strip()
        placeholder_text = _(self.placeholder_genes_homology_key)
        source_gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if
                                line.strip() and line.strip() != placeholder_text] if gene_ids_text != placeholder_text else []
        if not source_gene_ids_list:
            self.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"));
            self._update_button_states(False);
            return

        source_assembly_id_override = self.selected_homology_source_assembly.get()
        target_assembly_id_override = self.selected_homology_target_assembly.get()
        s_to_b_homology_file_override = self.homology_map_sb_file_entry.get().strip() or None
        b_to_t_homology_file_override = self.homology_map_bt_file_entry.get().strip() or None
        output_csv_path = self.homology_map_output_csv_entry.get().strip() or None

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_homology_mapping_standalone, kwargs={
            "config": self.current_config, "source_gene_ids_override": source_gene_ids_list,
            "source_assembly_id_override": source_assembly_id_override,
            "target_assembly_id_override": target_assembly_id_override,
            "s_to_b_homology_file_override": s_to_b_homology_file_override,
            "b_to_t_homology_file_override": b_to_t_homology_file_override,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

    def start_gff_query_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因位点查询")

        assembly_id_override = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_entry.get("1.0", tk.END).strip()
        current_placeholder = _(self.placeholder_genes_gff_key)
        if gene_ids_text == current_placeholder or not gene_ids_text:
            gene_ids_list = None
        else:
            gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        region_str = self.gff_query_region_entry.get().strip()
        output_csv_path = self.gff_query_output_csv_entry.get().strip() or None
        region_tuple = None
        if region_str:
            try:
                parts = region_str.split(':')
                if len(parts) == 2 and '-' in parts[1]:
                    chrom = parts[0]
                    start_end = parts[1].split('-')
                    start = int(start_end[0])
                    end = int(start_end[1])
                    region_tuple = (chrom, start, end)
                else:
                    raise ValueError("Format error")
            except Exception:
                self.show_error_message(_("输入错误"), _("染色体区域格式不正确。请使用 'chr:start-end' 格式。"));
                self._update_button_states(False);
                return

        if not assembly_id_override or assembly_id_override == _("加载中..."):
            self.show_error_message(_("输入缺失"), _("请选择一个基因组版本ID。"));
            self._update_button_states(False);
            return
        if not gene_ids_list and not region_tuple:
            self.show_error_message(_("输入缺失"), _("必须提供基因ID列表或染色体区域进行查询。"));
            self._update_button_states(False);
            return

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_gff_gene_lookup_standalone, kwargs={
            "config": self.current_config, "assembly_id_override": assembly_id_override,
            "gene_ids_override": gene_ids_list, "region_override": region_tuple,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

    # Helper for Browse files
    def _browse_file(self, entry_widget, filetypes_list):
        filepath = filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list)  #
        if filepath and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filepath)

    def _browse_save_file(self, entry_widget, filetypes_list):  #
        filepath = filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                defaultextension=filetypes_list[0][1].replace("*", ""))  #
        if filepath and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filepath)

    # --- (其余所有方法，如日志、状态、配置加载/保存等，保持不变) ---
    def clear_log_viewer(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self._log_to_viewer(_("日志已清除。"))

    def _log_to_viewer(self, message, level="INFO"):
        # 将日志消息放入队列，由主线程处理
        self.log_queue.put((message, level))

    def show_info_message(self, title, message):
        self._log_to_viewer(f"{title}: {message}", level="INFO")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color=self.default_label_text_color)
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="info")

    def show_error_message(self, title, message):
        self._log_to_viewer(f"ERROR - {title}: {message}", level="ERROR")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="red")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="error")

    def show_warning_message(self, title, message):
        self._log_to_viewer(f"WARNING - {title}: {message}", level="WARNING")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="orange")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="warning")

    def gui_status_callback(self, message: str):
        """
        线程安全的回调函数，用于更新状态栏和日志。
        能识别 "[ERROR]" 前缀并触发错误处理流程。
        """
        # 检查消息是否标记为错误
        if message.strip().upper().startswith("[ERROR]"):
            # 尝试获取锁，如果成功，则发送错误消息
            if self.error_dialog_lock.acquire(blocking=False):
                # 从消息中移除 "[ERROR]" 标记
                clean_message = message.strip()[7:].strip()
                self.message_queue.put(("error", clean_message))
            # 如果获取锁失败，说明已有另一个错误正在处理，忽略此错误以避免弹窗轰炸
        else:
            self.message_queue.put(("status", message))

        # 无论如何，都将原始消息记录到日志
        self._log_to_viewer(str(message))

    def gui_progress_callback(self, percentage, message):
        self.message_queue.put(("progress", (percentage, message)))  #

    def task_done_callback(self, success=True, task_display_name="任务"):
        self.message_queue.put(("task_done", (success, task_display_name)))

    def _display_log_message_in_ui(self, message, level):
        """
        实际更新日志文本框的UI，只在主线程中调用。
        并限制日志行数以提高性能。
        """
        if self.log_textbox and self.log_textbox.winfo_exists():
            self.log_textbox.configure(state="normal")

            # --- 优化：限制日志行数 ---
            max_lines = 500  # 最大保留的日志行数
            current_lines = int(self.log_textbox.index('end-1c linestart').split('.')[0])
            if current_lines > max_lines:
                # 删除旧的日志行
                self.log_textbox.delete(f"1.0", f"{current_lines - max_lines + 1}.0")
            # --- 优化结束 ---

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            color_tag = "normal_log"
            if level == "ERROR":
                color_tag = "error_log"
            elif level == "WARNING":
                color_tag = "warning_log"

            self.log_textbox.insert(tk.END, f"[{timestamp}] {message}\n", color_tag)
            self.log_textbox.see(tk.END)  # 保持滚动到底部
            self.log_textbox.configure(state="disabled")

            # 首次配置标签颜色只做一次，避免重复调用
            if not hasattr(self.log_textbox, '_tags_configured'):
                self._update_log_tag_colors()
                self.log_textbox._tags_configured = True

    # 在 CottonToolkitApp class 内部，替换此方法
    def check_queue_periodic(self):
        """
        定时检查消息队列，并更新UI。
        """
        try:
            # --- 处理日志队列 ---
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                self._display_log_message_in_ui(log_message, log_level)

            # --- 处理消息队列 ---
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()

                # 在处理关闭进度弹窗的消息时：
                if message_type == "hide_progress_dialog":
                    if self.progress_dialog and self.progress_dialog.winfo_exists():  # <-- 核心修正
                        self.progress_dialog.close()
                        self.progress_dialog = None

                # 当收到配置文件加载完成的消息时
                if message_type == "config_load_task_done":
                    # 无论成功失败，首先关闭加载弹窗
                    self._hide_progress_dialog()
                    success, result_data, filepath = data
                    if success:
                        # 如果成功，更新当前配置，并应用到UI
                        self.current_config = result_data
                        self.config_path = os.path.abspath(filepath)
                        self.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
                        self._apply_config_to_ui()
                    else:
                        # 如果失败，显示错误信息
                        self.show_error_message(_("加载失败"), str(result_data))

                # --- 其他消息处理逻辑保持不变 ---
                elif message_type == "startup_complete":
                    self._hide_progress_dialog()
                    # 从消息数据中正确提取配置对象
                    config_data = data.get("config")

                    if config_data:
                        self.current_config = config_data
                        # 从配置对象内部获取已保存的绝对路径
                        self.config_path = getattr(config_data, '_config_file_abs_path_', None)
                        self._log_to_viewer(_("默认配置文件加载成功。"))
                        self._apply_config_to_ui()
                    else:
                        self._log_to_viewer(_("未找到或无法加载默认配置文件。"), "WARNING")
                    self.update_language_ui()
                    self._update_button_states()

                elif message_type == "startup_failed":
                    self._hide_progress_dialog()
                    self.show_error_message(_("启动错误"), str(data))
                    self._update_button_states()

                elif message_type == "error":
                    self.show_error_message(_("任务执行出错"), data)
                    self.progress_bar.grid_remove()
                    self.status_label.configure(text=f"{_('任务终止于')}: {data[:100]}",
                                                text_color=("#d9534f", "#e57373"))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked(): self.error_dialog_lock.release()

                elif message_type == "task_done":
                    success, task_display_name = data
                    self.progress_bar.grid_remove()
                    if not self.error_dialog_lock.locked():
                        final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))
                        self.status_label.configure(text=final_message,
                                                    text_color=("green" if success else ("#d9534f", "#e57373")))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked(): self.error_dialog_lock.release()

                # ... 其他如 status, progress, ai_models_fetched 等消息处理...
                # (此处省略其他未修改的 elif 块以保持简洁)
                elif message_type == "status":
                    self.status_label.configure(text=str(data)[:150])
                elif message_type == "progress":
                    percentage, text = data
                    if not self.progress_bar.winfo_viewable(): self.progress_bar.grid()
                    self.progress_bar.set(percentage / 100.0)
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)")
                elif message_type == "hide_progress_dialog":
                    self._hide_progress_dialog()
                elif message_type == "update_sheets_dropdown":
                    sheet_names, excel_path, error = data
                    self._update_sheet_dropdowns_ui(sheet_names, excel_path, error)
                elif message_type == "ai_models_fetched":
                    provider_key, models = data
                    self._log_to_viewer(f"{provider_key} {_('模型列表获取成功。')} ")
                    model_selector_tuple = getattr(self, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
                    if model_selector_tuple:
                        _c, entry, dropdown, dropdown_var, _c = model_selector_tuple
                        dropdown.configure(values=models if models else [_("无可用模型")])
                        current_val = entry.get()
                        if models and current_val in models:
                            dropdown_var.set(current_val)
                        elif models:
                            dropdown_var.set(models[0])
                        else:
                            dropdown_var.set(_("无可用模型"))
                        entry.grid_remove()
                        dropdown.grid()
                        self.show_info_message(_("刷新成功"),
                                               f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')} ")
                elif message_type == "ai_models_failed":
                    provider_key, error_msg = data
                    self._log_to_viewer(f"{provider_key} {_('模型列表获取失败:')} {error_msg}", "ERROR")
                    model_selector_tuple = getattr(self, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
                    if model_selector_tuple:
                        _a, entry, dropdown, _a, _a = model_selector_tuple
                        dropdown.grid_remove()
                        entry.grid()
                        self.show_warning_message(_("刷新失败"),
                                                  f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")


        except queue.Empty:
            pass
        except Exception as e:
            logging.critical(f"Unhandled exception in check_queue_periodic: {e}", exc_info=True)

        self.after(100, self.check_queue_periodic)

    def _check_and_hide_startup_dialog(self):
        """
        检查所有启动阶段的UI更新任务是否完成，如果完成则关闭启动对话框。
        """
        # 确保所有必需的UI任务都已完成
        all_tasks_done = all(self.startup_ui_tasks_completed.values())

        # 只有在后台异步加载已完成，并且所有UI更新任务都已完成时才关闭对话框
        if self.initial_config_loaded.is_set() and all_tasks_done:
            self._hide_progress_dialog()
            # 可以选择在这里显示最终的启动成功/失败信息，不再使用弹窗
            # self.show_info_message(_("启动成功"), _("应用程序已成功启动！"))
            # 或者仅更新状态栏
            self.status_label.configure(text=_(self.status_label_base_key), text_color=self.default_label_text_color)
            self.update_language_ui()  # 最终刷新语言和按钮状态
            self._update_button_states()

    def _bind_mouse_wheel_to_scrollable(self, widget):
        """
        为 CustomTkinter 的可滚动widget（如 CTkScrollableFrame, CTkTextbox）绑定鼠标滚轮事件。
        直接绑定到 CustomTkinter 控件，因为它会处理底层的 Tkinter 组件。
        注意：CustomTkinter 在内部已经为 CTkScrollableFrame 和 CTkTextbox 实现了基本的滚轮功能。
        这个方法主要用于确保自定义的或额外的滚轮绑定能够正常工作，
        或者在某些情况下增强默认行为（尽管通常不推荐修改CTk的内部实现）。

        对于 CTkScrollableFrame，它内部有一个 canvas，事件需要绑定到 canvas 上。
        对于 CTkTextbox，它有自己的内部 Text 控件，事件需要绑定到该 Text 控件上。
        """
        # 对于 CTkScrollableFrame
        if hasattr(widget, "_canvas") and isinstance(widget._canvas, ctk.CTkCanvas):
            canvas = widget._canvas
            canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                        add="+")
            canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkScrollableFrame canvas: {widget}", "DEBUG")

        # 对于 CTkTextbox
        elif hasattr(widget, "_textbox") and isinstance(widget._textbox, tk.Text):
            textbox = widget._textbox
            textbox.bind("<MouseWheel>", lambda event: textbox.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                         add="+")
            textbox.bind("<Button-4>", lambda event: textbox.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            textbox.bind("<Button-5>", lambda event: textbox.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkTextbox internal Text: {widget}", "DEBUG")

        # 对于其他可能需要滚动的 CustomTkinter 控件（如 CTkFrame，如果里面放了其他可滚动内容）
        # 可以尝试直接绑定到控件本身，但效果可能不如直接绑定到内部 canvas/text
        else:
            widget.bind("<MouseWheel>",
                        lambda event: widget._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                        add="+")
            # 返回 "break" 可以阻止事件继续传播
            widget.bind("<Enter>", lambda event: widget.bind_all("<MouseWheel>", lambda e: "break"))

            widget.bind("<Button-4>",
                        lambda event: widget.yview_scroll(-1, "units") if hasattr(widget, 'yview_scroll') else None,
                        add="+")
            widget.bind("<Button-5>",
                        lambda event: widget.yview_scroll(1, "units") if hasattr(widget, 'yview_scroll') else None,
                        add="+")
            self._log_to_viewer(f"DEBUG: Attempted generic mouse wheel bind to: {widget}", "DEBUG")

    def on_closing(self):
        if self._show_custom_dialog(_("退出"), _("您确定要退出吗?"), buttons=[_("确定"), _("取消")],
                                    icon_type="question") == _("确定"):
            self.destroy()

    def load_config_file(self, filepath: Optional[str] = None):
        """
        【已修正】加载配置文件，并异步应用到UI。
        """
        if not filepath:
            filepath = filedialog.askopenfilename(
                title=_("选择配置文件"),
                filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*"))
            )

        if filepath:
            self._log_to_viewer(f"{_('尝试加载配置文件:')} {filepath}")
            self._show_progress_dialog(
                title=_("加载配置中..."),
                message=_("正在加载配置文件并应用到UI..."),
                on_cancel=None
            )

            def load_task_thread():
                try:
                    # 后台线程执行实际的加载操作
                    config_data = load_config(os.path.abspath(filepath))
                    # 【核心修改】加载完成后，将结果和成功状态打包，发送一个特定的完成消息
                    self.message_queue.put(("config_load_task_done", (True, config_data, filepath)))
                except Exception as e:
                    # 【核心修改】如果加载失败，发送带有失败状态和错误信息的消息
                    self.message_queue.put(("config_load_task_done", (False, str(e), None)))

            # 启动后台线程
            threading.Thread(target=load_task_thread, daemon=True).start()
        else:
            self._log_to_viewer(_("用户取消加载配置文件。"))

    def save_config_file(self, config_data: Optional[Dict] = None, show_dialog: bool = False) -> bool:
        """保存当前配置, 可选择是否弹出另存为对话框"""
        if config_data is None:
            config_data = self.current_config

        if not config_data:
            self.show_error_message(_("错误"), _("没有可保存的配置。"))
            return False

        save_path = self.config_path
        if show_dialog or not save_path:
            save_path = filedialog.asksaveasfilename(
                title=_("配置文件另存为"),
                filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
                defaultextension=".yml"
            )

        if save_path:
            try:
                if save_config_to_yaml(config_data, save_path):
                    self.config_path = save_path  # 更新当前配置路径
                    self.current_config = config_data
                    self._apply_config_to_ui()  # 重新应用，确保路径等显示正确
                    self.show_info_message(_("保存成功"), _("配置文件已保存至: {}").format(save_path))
                    return True
                else:
                    # save_config_to_yaml 内部会打印错误
                    self.show_error_message(_("保存失败"), _("保存配置文件时发生未知错误，请检查日志。"))
                    return False
            except Exception as e:
                self.show_error_message(_("保存失败"), f"{_('保存配置文件时发生错误:')} {e}")
                return False
        return False

    def on_config_updated(self, new_config_data: Dict):
        """当外部窗口(如编辑器)更新了配置后，由此方法通知主窗口"""
        self.current_config = new_config_data
        self._apply_config_to_ui()
        self._log_to_viewer(_("配置已从高级编辑器更新。"))

    def _generate_default_configs_gui(self):
        """
        【全新版本】处理“生成默认配置”按钮的点击事件。
        能够检测文件是否存在，并根据用户的选择执行覆盖或加载操作。
        """
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if not output_dir:
            self._log_to_viewer(_("用户取消了目录选择。"))
            return

        self._log_to_viewer(f"{_('用户选择的配置目录:')} {output_dir}")
        main_config_filename = "config.yml"  # 使用硬编码以确保检查的文件名正确
        main_config_path = os.path.join(output_dir, main_config_filename)

        should_overwrite = False
        # 检查配置文件是否已存在
        if os.path.exists(main_config_path):
            # 如果文件存在，弹窗询问用户
            user_choice = self._show_custom_dialog(
                title=_("文件已存在"),
                message=_("配置文件 '{}' 已存在于所选目录中。\n\n您想覆盖它吗？\n(选择“否”将直接加载现有文件)").format(
                    main_config_filename),
                buttons=[_("是 (覆盖)"), _("否 (加载)")],
                icon_type="question"
            )

            if user_choice == _("是 (覆盖)"):
                should_overwrite = True
            elif user_choice == _("否 (加载)"):
                # 用户选择不覆盖，则直接加载现有文件
                self.load_config_file(filepath=main_config_path)
                return  # 结束流程
            else:
                # 用户关闭了对话框
                self._log_to_viewer(_("用户取消了覆盖操作。"))
                return

        # 如果文件不存在，或者用户同意覆盖，则执行生成
        try:
            self._log_to_viewer(_("正在生成默认配置文件..."))
            success, new_main_cfg_path, new_gs_cfg_path = generate_default_config_files(
                output_dir,
                overwrite=should_overwrite,
                main_config_filename=main_config_filename
            )
            if success:
                msg = f"{_('默认配置文件已成功生成到:')}\n{new_main_cfg_path}\n{new_gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"
                if self._show_custom_dialog(_("生成成功"), msg, [_("是"), _("否")], "info") == _("是"):
                    self.load_config_file(filepath=new_main_cfg_path)
            else:
                # generate_default_config_files 内部应该已经打印了日志
                self.show_error_message(_("生成失败"), _("生成默认配置文件失败，请检查日志获取详细信息。"))
        except Exception as e:
            self.show_error_message(_("生成错误"), f"{_('生成默认配置文件时发生未知错误:')} {e}")

    def _save_genome_sources_config(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("没有加载主配置文件。")); return  #
        gs_file_rel = self.current_config.get("downloader", {}).get("genome_sources_file")  #
        if not gs_file_rel: self.show_warning_message(_("无法保存"),
                                                      _("主配置文件中未指定基因组源文件路径。")); return  #
        abs_path = os.path.join(os.path.dirname(self.config_path), gs_file_rel) if not os.path.isabs(
            gs_file_rel) and self.config_path else gs_file_rel  #
        content_to_save = self.editor_gs_raw_yaml.get("1.0", tk.END).strip()  #
        try:
            parsed_yaml = yaml.safe_load(content_to_save)  #
            if not isinstance(parsed_yaml, dict): self.show_error_message(_("保存错误"),
                                                                          _("基因组源内容的YAML格式不正确。")); return  #
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content_to_save)  #
            self._log_to_viewer(f"{_('基因组源文件已保存到:')} {abs_path}");
            self.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")  #
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")  #

    def _update_button_states(self, is_task_running=False):
        action_state = "disabled" if is_task_running else "normal"
        task_button_state = "normal" if self.current_config and not is_task_running else "disabled"

        # 所有任务按钮
        if hasattr(self, 'download_start_button') and self.download_start_button.winfo_exists():
            self.download_start_button.configure(state=task_button_state)
        if hasattr(self, 'integrate_start_button') and self.integrate_start_button.winfo_exists():
            self.integrate_start_button.configure(state=task_button_state)
        if hasattr(self, 'homology_map_start_button') and self.homology_map_start_button.winfo_exists():
            self.homology_map_start_button.configure(state=task_button_state)
        if hasattr(self, 'gff_query_start_button') and self.gff_query_start_button.winfo_exists():
            self.gff_query_start_button.configure(state=task_button_state)
        if hasattr(self, 'anno_start_button') and self.anno_start_button.winfo_exists():  # For annotation tab
            self.anno_start_button.configure(state=task_button_state)
        if hasattr(self, 'ai_start_button') and self.ai_start_button.winfo_exists():  # For AI assistant tab
            self.ai_start_button.configure(state=task_button_state)
        if hasattr(self, 'convert_start_button') and self.convert_start_button.winfo_exists():  # For XLSX to CSV tab
            self.convert_start_button.configure(state=task_button_state)

        # 侧边栏和配置按钮
        if hasattr(self, 'navigation_frame'):  # 确保导航框架已经创建
            # 遍历这些按钮，并检查它们是否存在
            for btn_name in ['home_button', 'editor_button', 'integrate_button', 'tools_button',
                             'load_config_button', 'gen_config_button']:  #
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    if btn.winfo_exists():  # 确保控件在Tkinter中仍存在
                        btn.configure(state=action_state)

    def start_download_task(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 禁用所有操作按钮，表明任务正在进行
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("数据下载")

        # 将后台任务的执行逻辑包裹在一个函数中
        def task_wrapper():
            success = False
            try:
                # 1. 从UI复选框中收集需要下载的基因组ID列表
                versions_to_download = [gid for gid, var in self.download_genome_vars.items() if var.get()]
                # 如果用户没有勾选任何项，则列表为空，后台会理解为下载所有
                if not versions_to_download:
                    versions_to_download = None

                # 2. 根据UI开关状态决定是否使用代理
                proxies_to_use = None
                if self.download_proxy_var.get():
                    # 仅当开关打开时，才从配置中读取代理地址
                    proxies_to_use = self.current_config.downloader.proxies
                    if not proxies_to_use or not (proxies_to_use.http or proxies_to_use.https):
                        # 如果代理地址未配置，则通过消息队列报错并终止任务
                        self.gui_status_callback(f"[ERROR] {_('您开启了代理开关，但配置文件中未找到有效的代理地址。')}")
                        return  # 提前终止线程

                # 3. 准备传递给后台的配置
                # 使用 deepcopy 创建一个临时配置副本，避免修改内存中的原始配置对象
                import copy
                temp_config_obj = copy.deepcopy(self.current_config)
                temp_config_obj.downloader.proxies = proxies_to_use  # 覆盖代理设置

                force_download_override = self.download_force_checkbox_var.get()

                # 4. 更新UI状态，准备开始任务
                self.gui_status_callback(
                    f"{self.active_task_name} {_('任务开始...')} ({_('代理')}: {'ON' if proxies_to_use else 'OFF'})")
                self.gui_progress_callback(0, _("正在准备下载..."))  # 使用 progress 回调来更新状态

                # 5. 调用后台下载函数
                success = download_genome_data(
                    config=temp_config_obj,
                    genome_versions_to_download_override=versions_to_download,
                    force_download_override=force_download_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback
                )
            except Exception as e:
                # 捕获任何意外的严重错误
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                # 无论成功或失败，都确保调用任务结束回调
                self.task_done_callback(success, self.active_task_name)

        # 启动包含以上全部逻辑的后台线程
        threading.Thread(target=task_wrapper, daemon=True).start()

    def _show_about_window(self):
        """
        显示经过美化的“关于”窗口。
        """
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.focus()
            return

        self.about_window = ctk.CTkToplevel(self)
        self.about_window.title(_("关于 FCGT"))
        self.about_window.geometry("850x700")
        self.about_window.transient(self)
        self.about_window.grab_set()

        def _on_about_window_close():
            if self.about_window:
                self.about_window.destroy()
                self.about_window = None  # 将变量重置为None

        self.about_window.protocol("WM_DELETE_WINDOW", _on_about_window_close)

        scrollable_frame = ctk.CTkScrollableFrame(self.about_window, corner_radius=0, fg_color="transparent")
        scrollable_frame.pack(expand=True, fill="both")
        scrollable_frame.grid_columnconfigure(0, weight=1)

        base_font_family = self.app_font.cget("family")
        title_font = ctk.CTkFont(family=base_font_family, size=20, weight="bold")
        header_font = ctk.CTkFont(family=base_font_family, size=16, weight="bold")
        text_font = ctk.CTkFont(family=base_font_family, size=14)
        version_font = ctk.CTkFont(family=base_font_family, size=12)  # 新增版本号字体
        link_font = ctk.CTkFont(family=base_font_family, size=14, underline=False)
        link_font_underline = ctk.CTkFont(family=base_font_family, size=14, underline=True)

        header_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        logo_label = ctk.CTkLabel(header_frame, text="", image=self.logo_image)
        logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 15))

        title_label = ctk.CTkLabel(header_frame, text=_("友好棉花基因组工具包 (FCGT)"), font=title_font)
        title_label.grid(row=0, column=1, sticky="w")

        version_label = ctk.CTkLabel(header_frame, text=f"Version: {PKG_VERSION}", font=version_font, text_color="gray")
        version_label.grid(row=1, column=1, sticky="w")

        version_label = ctk.CTkLabel(header_frame, text=_('本软件遵守 Apache-2.0 license 开源协议'), font=version_font,
                                     text_color="gray")
        version_label.grid(row=2, column=1, sticky="w")

        def add_section_header(parent, title_text, top_pady=20):
            ctk.CTkLabel(parent, text=title_text, font=header_font).grid(row=parent.grid_size()[1], column=0,
                                                                         sticky="w", padx=20, pady=(top_pady, 5))
            ctk.CTkFrame(parent, height=2, fg_color="gray50").grid(row=parent.grid_size()[1], column=0, sticky="ew",
                                                                   padx=20)

        def add_section_content(parent, content_text):
            ctk.CTkLabel(parent, text=content_text, font=text_font, wraplength=780, justify="left").grid(
                row=parent.grid_size()[1], column=0, sticky="w", padx=25, pady=(5, 0))

        def create_hyperlink(parent, text, url):
            link_label = ctk.CTkLabel(parent, text=text, text_color=("#0000EE", "#ADD8E6"), cursor="hand2",
                                      font=link_font)
            link_label.bind("<Button-1>", lambda e: webbrowser.open_new(url))
            link_label.bind("<Enter>", lambda e: link_label.configure(font=link_font_underline))
            link_label.bind("<Leave>", lambda e: link_label.configure(font=link_font))
            return link_label

        # --- 开发与致谢区域  ---
        add_section_header(scrollable_frame, _("开发与致谢"))
        dev_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        dev_frame.grid(row=scrollable_frame.grid_size()[1], column=0, sticky="ew", padx=25, pady=5)
        dev_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dev_frame, text=_("作者:"), font=text_font).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(dev_frame, text="PureAmaya", font=text_font).grid(row=0, column=1, sticky="w", padx=10)

        ctk.CTkLabel(dev_frame, text=_("致谢:"), font=text_font).grid(row=1, column=0,
                                                                      sticky="w", pady=(5, 0))
        ctk.CTkLabel(dev_frame, text=_("开源社区和科研工作者"), font=text_font).grid(row=1, column=1, sticky="w",
                                                                                     padx=10, pady=(5, 0))

        add_section_header(scrollable_frame, _("版权与许可"))
        add_section_content(scrollable_frame,
                            (
                             "• requests (Apache-2.0 License)\n"
                             "• tqdm (MIT License)\n"
                             "• gffutils (MIT License)\n"
                             "• pandas (BSD 3-Clause License)\n"
                             "• PyYAML (MIT License)\n"
                             "• numpy (BSD License)\n"
                             "• pillow (MIT-CMU License)\n"
                             "• diskcache (Apache 2.0 License)\n"
                             "• openpyxl (MIT License)\n"
                             "• customtkinter (MIT License)\n"

                            ))

        add_section_header(scrollable_frame, _("在线资源与文档"))

        links_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        links_frame.grid(row=scrollable_frame.grid_size()[1], column=0, sticky="ew", padx=25, pady=5)
        links_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(links_frame, text=_("项目仓库 (GitHub):"), font=text_font).grid(row=0, column=0, sticky="w")
        create_hyperlink(links_frame, PKG_PUBLISH_URL, PKG_PUBLISH_URL).grid(row=0, column=1, sticky="w", padx=10)
        ctk.CTkLabel(links_frame, text=_("在线帮助文档:"), font=text_font).grid(row=1, column=0, sticky="w",
                                                                                pady=(5, 0))
        create_hyperlink(links_frame, PKG_HELP_URL, PKG_HELP_URL).grid(row=1, column=1, sticky="w", padx=10,
                                                                       pady=(5, 0))

        ctk.CTkLabel(links_frame, text="CottonGen:", font=text_font).grid(row=2, column=0, sticky="w", pady=(5, 0))
        create_hyperlink(links_frame, "https://www.cottongen.org/",
                         "https://www.cottongen.org/").grid(row=2, column=1, sticky="w", padx=10, pady=(5, 0))

        add_section_header(scrollable_frame, "CottonGen " + _("文章"))
        add_section_content(scrollable_frame,
                            (
                                "• Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. Plants 10(12), 2805.\n"
                                "• Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. Nucleic Acids Research 42(D1), D1229-D1236."))

        genome_citations = (
            "• NAU-NBI_v1.1:\n Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015\n\n"
            "• UTX-JGI-Interim-release_v1.1:\n  - Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].\n  - Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011.\n  - Yeh, R.-F., et al. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.\n  - Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.\n\n"
            "• HAU_v1 / v1.1:\n Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03\n\n"
            "• ZJU-improved_v2.1_a1:\n Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton.\n\n"
            "• CRI_v1:\n Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.\n\n"
            "• WHU_v1:\n Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4\n\n"
            "• UTX_v2.1:\n Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.\n\n"
            '• HAU_v2.0:\n Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. "High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres." Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722'
        )

        add_section_header(scrollable_frame, _("基因组引用文献"))
        add_section_content(scrollable_frame, genome_citations)

        add_section_header(scrollable_frame, _("免责声明"))
        add_section_content(scrollable_frame, _("上述基因组的数据下载均由用户执行，本工具仅进行通用的分析操作。"))

        close_button = ctk.CTkButton(scrollable_frame, text=_("关闭"), command=_on_about_window_close,
                                     font=self.app_font)
        close_button.grid(row=scrollable_frame.grid_size()[1], column=0, pady=30)


if __name__ == "__main__":  #
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()  #
    app.mainloop()  #
