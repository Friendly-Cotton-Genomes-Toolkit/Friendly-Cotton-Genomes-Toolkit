# gui_app.py

import copy
import json
import logging
from logging import handlers
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from queue import Queue
from tkinter import filedialog, font as tkfont
from typing import Callable, Dict, Optional, Any, List  # 确保 Tuple 被导入

import customtkinter as ctk
import pandas as pd
import yaml
from PIL import Image

from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.pipelines import (
    run_functional_annotation,
    run_enrichment_pipeline,
)
from cotton_toolkit.utils.localization import setup_localization
from cotton_toolkit.utils.logger import setup_global_logger, set_log_level
from ui import ProgressDialog, MessageDialog, AnnotationTab
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.data_download_tab import DataDownloadTab
from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
from ui.tabs.gff_query_tab import GFFQueryTab
from ui.tabs.homology_tab import HomologyTab
from ui.tabs.locus_conversion_tab import LocusConversionTab
from ui.tabs.xlsx_converter_tab import XlsxConverterTab
from ui.utils.gui_helpers import identify_genome_from_gene_ids

print("INFO: gui_app.py - All modules imported.")

# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #

logger = logging.getLogger("cotton_toolkit.gui")


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}

    AI_PROVIDERS = {
        "google": {"name": "Google Gemini"},
        "openai": {"name": "OpenAI"},
        "deepseek": {"name": "DeepSeek (深度求索)"},
        "qwen": {"name": "Qwen (通义千问)"},
        "siliconflow": {"name": "SiliconFlow (硅基流动)"},
        "grok": {"name": "Grok (xAI)"},
        "openai_compatible": {"name": _("通用OpenAI兼容接口")}
    }

    # 在 gui_app.py 的 CottonToolkitApp 类中

    def __init__(self):
        super().__init__()
        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1100x750")
        self.minsize(800, 600)

        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data: Optional[Dict[str, Any]] = None
        self.excel_sheet_cache: Dict[str, List[str]] = {}

        self.log_queue: Queue = Queue()
        self.message_queue: Queue = Queue()
        self.message_handlers = self._initialize_message_handlers()
        self.active_task_name: Optional[str] = None
        self.progress_dialog: Optional[ProgressDialog] = None
        self.cancel_current_task_event = threading.Event()
        self.cancel_model_fetch_event = threading.Event()
        self.error_dialog_lock = threading.Lock()

        self.ui_settings: Dict[str, Any] = {}
        self.about_window: Optional[ctk.CTkToplevel] = None
        self.translatable_widgets: Dict[ctk.CTkBaseClass, Any] = {}
        self.log_viewer_visible: bool = False

        self._setup_fonts()
        self.secondary_text_color = ("#495057", "#999999")
        self.placeholder_color = ("#868e96", "#5c5c5c")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]
        self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]

        self._create_image_assets()

        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()

        self.placeholders = {
            "genes_input": _(
                "输入基因ID (每行一个或用逗号/Tab分隔)。\n若进行富集分析且包含Log2FC，格式为 '基因,Log2FC'。"),
            "homology_genes": _("输入要转换的基因ID，每行一个或用逗号/Tab分隔。"),
            "gff_genes": _("输入或粘贴基因ID，每行一个或用逗号分隔。"),
            "gff_region": _("例如: A03:1000-2000")
        }

        self.TAB_TITLE_KEYS = {
            "download": "数据下载", "homology": "基因组转换", "locus_conversion": "位点转换",
            "gff_query": "基因位点查询", "annotation": "功能注释", "ai_assistant": "AI 助手",
            "genome_identifier": "基因组类别鉴定", "xlsx_to_csv": "XLSX转CSV"
        }
        self.TOOL_TAB_ORDER = ["download", "homology", "locus_conversion", "gff_query", "annotation", "ai_assistant",
                               "genome_identifier", "xlsx_to_csv"]

        self.tool_tab_instances: Dict[str, ctk.CTkFrame] = {}
        self.editor_ui_built: bool = False

        # --- 在初始化时就设置好控制台日志 ---
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        self._load_ui_settings()
        self._create_layout()
        self._init_pages_and_final_setup()
        self._start_app_async_startup()


    def _create_image_assets(self):
        """加载所有图片资源"""
        self.logo_image = self._load_image_resource("logo.png", (48, 48))
        self.home_icon = self._load_image_resource("home.png")
        self.tools_icon = self._load_image_resource("tools.png")
        self.settings_icon = self._load_image_resource("settings.png")
        self.folder_icon = self._load_image_resource("folder.png")
        self.new_file_icon = self._load_image_resource("new-file.png")
        self.help_icon = self._load_image_resource("help.png")
        self.info_icon = self._load_image_resource("info.png")


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

    def _initialize_message_handlers(self) -> Dict[str, Callable]:
        """返回消息类型到其处理函数的映射字典。"""
        return {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "hide_progress_dialog": self._hide_progress_dialog,
            "update_sheets_dropdown": self._handle_update_sheets_dropdown,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_models_failed": self._handle_ai_models_failed,
            "auto_identify_success": self._handle_auto_identify_success,
            "auto_identify_fail": self._handle_auto_identify_fail,
            "auto_identify_error": self._handle_auto_identify_error,
            "ai_test_result": self._handle_ai_test_result,
        }


    # 在 CottonToolkitApp class 内部
    def _fetch_ai_models(self, provider_key: str):
        """
        直接从静态UI输入框获取API Key和URL来刷新模型列表。
        现在会检查AI助手的代理开关。
        """
        self._log_to_viewer(
            f"{_('正在获取')} '{self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)}' {_('的模型列表...')} ")

        api_key = ""
        base_url = None

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
                api_key = self.ai_openai_compatible_apikey_entry.get().strip()
                base_url = self.ai_openai_compatible_baseurl_entry.get().strip() or None
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

        # --- 统一代理逻辑 ---
        proxies_to_use = None
        # 检查AI助手的代理开关是否打开
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and hasattr(ai_tab, 'ai_proxy_var') and ai_tab.ai_proxy_var.get():  # 仅在开关打开时才读取代理地址
            # 代理地址本身还是从配置编辑器的输入框读取，这是统一的配置源
            http_proxy = self.downloader_proxy_http_entry.get().strip()
            https_proxy = self.downloader_proxy_https_entry.get().strip()
            if http_proxy or https_proxy:
                proxies_to_use = {}
                if http_proxy:
                    proxies_to_use['http'] = http_proxy
                if https_proxy:
                    proxies_to_use['https'] = https_proxy
                self._log_to_viewer(f"DEBUG: 将使用代理刷新模型列表: {proxies_to_use}", "DEBUG")
            else:
                self._log_to_viewer("DEBUG: AI代理开关已打开，但配置编辑器中未设置代理地址。", "DEBUG")
        else:
            self._log_to_viewer("DEBUG: AI代理开关关闭，不使用代理刷新模型列表。", "DEBUG")
        # --- 统一代理逻辑结束 ---

        self.cancel_model_fetch_event.clear()

        # 1. 创建 ProgressDialog 实例
        self.progress_dialog = ProgressDialog(
            self,
            title=_("获取模型列表"),
            on_cancel=self.cancel_model_fetch_event.set,
            app_font=self.app_font
        )
        # 2. 更新其文本
        self.progress_dialog.update_progress(0, _("正在从 {} 获取模型列表，请稍候...").format(
            self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)))


        def fetch_in_thread():
            try:
                timeout_seconds = 30
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
                # --- 发送消息让主线程安全地关闭弹窗 ---
                self.message_queue.put(("hide_progress_dialog", None))

        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        """
        【统一修正版】显示一个模态的进度弹窗。
        现在总是使用更健壮的 ProgressDialog 类。
        """
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close() # 安全地关闭任何已存在的弹窗

        self.progress_dialog = ProgressDialog(
            parent=self,
            title=title,
            on_cancel=on_cancel,
            app_font=self.app_font
        )
        self.progress_dialog.update_progress(0, message)
        # ProgressDialog 内部会自动居中和显示

    def _hide_progress_dialog(self, data=None):  # data 参数是为了兼容旧的调用
        """
        【优化版】安全地隐藏并销毁进度弹窗。
        此方法现在委托给 ProgressDialog 自己的 close 方法。
        """
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close()
        self.progress_dialog = None



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
        self._bind_mouse_wheel_to_scrollable(self.log_textbox)
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

        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(side="top", fill="both", expand=True)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_rowconfigure(0, weight=1)

        self._create_navigation_frame(parent=top_frame)

        self.main_content_frame = ctk.CTkFrame(top_frame, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)


    def _init_pages_and_final_setup(self):
        self._log_to_viewer(f"{_('当前工作目录:')} {os.getcwd()}")

        self.home_frame = self._create_home_frame(self.main_content_frame)
        self.editor_frame = self._create_editor_frame(self.main_content_frame)
        self.tools_frame = self._create_tools_frame(self.main_content_frame)

        self._populate_tools_notebook()

        if not self.editor_ui_built:
            self._create_editor_widgets(self.editor_scroll_frame)
            self.editor_ui_built = True
        self._handle_editor_ui_update()

        self.select_frame_by_name("home")
        self.update_language_ui()
        self._update_button_states()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_app_icon()

    def _start_app_async_startup(self):
        """
        启动应用的异步加载流程。
        """
        # 立即显示启动进度对话框
        self._show_progress_dialog(
            title=_("图形界面启动中..."),
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None  # 启动阶段不允许取消
        )

        # 启动一个专门用于加载的后台线程
        threading.Thread(target=self._initial_load_thread, daemon=True).start()


    def _initial_load_thread(self):
        """
        在后台执行所有耗时的加载操作，完成后将结果放入消息队列。
        """
        loaded_config: Optional[MainConfig] = None
        genome_sources = None

        try:
            default_config_path = "config.yml"
            if os.path.exists(default_config_path):
                # 1. 加载主配置文件，load_config 应该返回 MainConfig 实例
                self.message_queue.put(("progress", (10, _("加载配置文件..."))))
                loaded_config = load_config(os.path.abspath(default_config_path))
                # 确保 config_path 也被设置，这里直接从 loaded_config 获取更新后的字段名
                self.config_path = getattr(loaded_config, 'config_file_abs_path_', None)  # 更新字段名称


            # 2. 如果主配置加载成功，则加载基因组源数据
            if loaded_config: # 确保 loaded_config 确实是 MainConfig 实例
                self.message_queue.put(("progress", (30, _("加载基因组源数据..."))))
                # 传递 loaded_config (MainConfig 实例) 给 get_genome_data_sources
                # 这里使用 self._log_to_viewer 作为 logger_func
                genome_sources = get_genome_data_sources(loaded_config, logger_func=self._log_to_viewer)

            # 3. 将所有加载结果打包，发送“启动完成”消息
            startup_data = {
                "config": loaded_config,
                "genome_sources": genome_sources
            }
            self.message_queue.put(("startup_complete", startup_data))

        except Exception as e:
            # 如果加载过程中任何一步出错，发送“启动失败”消息
            error_message = f"{_('应用启动失败')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.message_queue.put(("startup_failed", error_message))
        finally:
            # 无论成功失败，都发送消息让主线程处理关闭弹窗
            self.message_queue.put(("hide_progress_dialog", None))


    def _create_editor_frame(self, parent):
        """
        【优化版】创建配置编辑器的主框架，包含一个可滚动区域和一个提示标签。
        """
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)  # 第1行用于主内容区域

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

        # 1. 创建包含所有配置项的可滚动框架
        self.editor_scroll_frame = ctk.CTkScrollableFrame(page)
        self.editor_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
        self._bind_mouse_wheel_to_scrollable(self.editor_scroll_frame)

        # 2. 创建一个“未加载配置”的提示标签
        self.editor_no_config_label = ctk.CTkLabel(page, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                   font=self.app_subtitle_font,
                                                   text_color=self.secondary_text_color)
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew")

        # 绑定快捷键 (此逻辑不变)
        page.bind('<Control-s>', lambda event: self._save_config_from_editor())
        page.bind('<Control-S>', lambda event: self._save_config_from_editor())
        self.editor_scroll_frame.bind('<Control-s>', lambda event: self._save_config_from_editor())
        self.editor_scroll_frame.bind('<Control-S>', lambda event: self._save_config_from_editor())

        return page

    def _get_settings_path(self):
        """获取UI设置文件的路径"""
        # 将设置文件保存在程序根目录，方便用户查找和管理
        return "ui_settings.json"

    def _load_ui_settings(self):
        """加载UI设置，现在只处理外观模式。"""
        settings_path = self._get_settings_path()
        defaults = {"appearance_mode": "System"}

        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self.ui_settings = json.load(f)
            else:
                self.ui_settings = defaults
        except (json.JSONDecodeError, IOError):
            self.ui_settings = defaults

        # 应用加载的或默认的外观模式
        appearance_mode = self.ui_settings.get("appearance_mode", "System")
        ctk.set_appearance_mode(appearance_mode)

        # 更新下拉菜单的显示值
        mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
        self.selected_appearance_var.set(mode_map_to_display.get(appearance_mode, _("系统")))

    def _save_ui_settings(self):
        """保存UI设置，现在只处理外观模式。"""
        settings_path = self._get_settings_path()
        try:
            # 只保存外观设置，不触碰语言设置
            data_to_save = {"appearance_mode": self.ui_settings.get("appearance_mode", "System")}
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            self._log_to_viewer(_("外观模式设置已保存。"), "DEBUG")
        except IOError as e:
            self._log_to_viewer(f"{_('错误: 无法保存外观设置:')} {e}", "ERROR")

    def show_info_message(self, title: str, message: str):
        self._log_to_viewer(f"INFO - {title}: {message}", "INFO")
        dialog = MessageDialog(parent=self, title=_(title), message=_(message), icon_type="info",
                               app_font=self.app_font)
        dialog.wait_window()

    def show_error_message(self, title: str, message: str):
        self._log_to_viewer(f"ERROR - {title}: {message}", "ERROR")
        dialog = MessageDialog(parent=self, title=_(title), message=message, icon_type="error", app_font=self.app_font)
        dialog.wait_window()

    def show_warning_message(self, title: str, message: str):
        self._log_to_viewer(f"WARNING - {title}: {message}", "WARNING")
        dialog = MessageDialog(parent=self, title=_(title), message=_(message), icon_type="warning",
                               app_font=self.app_font)
        dialog.wait_window()

    def _load_image_resource(self, file_name, size=(24, 24)):
        try:
            if hasattr(sys, '_MEIPASS'):
                base_path = os.path.join(sys._MEIPASS, "assets")
            else:
                base_path = os.path.join(os.path.dirname(__file__), "assets")
            image_path = os.path.join(base_path, file_name)
            if os.path.exists(image_path):
                return ctk.CTkImage(Image.open(image_path), size=size)
            else:
                print(f"警告: 图片资源未找到，检查路径: '{image_path}'")
                raise FileNotFoundError
        except Exception as e:
            if not isinstance(e, FileNotFoundError):
                 print(f"警告: 加载图片资源 '{file_name}' 时发生错误: {e}")
            placeholder = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            return ctk.CTkImage(placeholder, size=size)



        except Exception as e:
            # 捕获所有异常（包括上面主动抛出的 FileNotFoundError）
            # 打印原始警告（如果是文件不存在的话）
            if not isinstance(e, FileNotFoundError):
                print(f"警告: 加载图片资源 '{file_name}' 时发生错误: {e}")

            # --- 核心修改：创建并返回一个透明的占位图 ---
            placeholder = Image.new('RGBA', (1, 1), (0, 0, 0, 0))  # 创建一个1x1的完全透明的图像
            return ctk.CTkImage(placeholder, size=size)



    def _create_navigation_frame(self, parent):
        self.navigation_frame = ctk.CTkFrame(parent, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(4, weight=1)  # 调整权重行以适应按钮数量

        nav_header_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        nav_logo_label = ctk.CTkLabel(nav_header_frame, text="", image=self.logo_image)
        nav_logo_label.pack(pady=(0, 10))

        self.nav_title_label = ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold"))
        self.nav_title_label.pack()

        # --- 导航按钮 ---
        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=self.home_icon, font=self.app_font_bold,
                                         command=lambda: self.select_frame_by_name("home"))
        self.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.editor_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                           text=_("配置编辑器"), fg_color="transparent",
                                           text_color=("gray10", "gray90"),
                                           anchor="w", image=self.settings_icon, font=self.app_font_bold,
                                           command=lambda: self.select_frame_by_name("editor"))
        self.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.tools_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=self.tools_icon, font=self.app_font_bold,
                                          command=lambda: self.select_frame_by_name("tools"))
        self.tools_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)  # 行号提前

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

        self.tools_notebook = ctk.CTkTabview(self.main_content_frame)
        self.tools_notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)


    def select_frame_by_name(self, name):
        # 设置按钮高亮
        self.home_button.configure(fg_color=self.home_button.cget("hover_color") if name == "home" else "transparent")
        self.editor_button.configure(
            fg_color=self.editor_button.cget("hover_color") if name == "editor" else "transparent")
        self.tools_button.configure(
            fg_color=self.tools_button.cget("hover_color") if name == "tools" else "transparent")

        # 隐藏所有页面
        self.home_frame.grid_forget()
        self.editor_frame.grid_forget()
        # self.integrate_frame.grid_forget() # 移除此行
        self.tools_frame.grid_forget()

        # 根据名称显示对应的页面
        if name == "home":
            self.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "editor":
            self.editor_frame.grid(row=0, column=0, sticky="nsew")
            self._handle_editor_ui_update()
        # elif name == "integrate": # 移除此分支
        #     self.integrate_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "tools":
            self.tools_frame.grid(row=0, column=0, sticky="nsew")

    def _create_editor_widgets(self, parent):
        """
        只创建一次配置编辑器的所有UI控件，但不填充数据。
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
            self._bind_mouse_wheel_to_scrollable(textbox)
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

            # 根据我们之前的约定，这里的 tooltip 文本已被修改
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=_("要使用的模型名称。多个模型请用英文逗号 (,) 分隔。"),
                                             font=self.app_comment_font,
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

            # --- 通用设置 ---

        create_section_title(parent, _("通用设置"))
        self.general_log_level_menu, self.general_log_level_var = create_option_menu_row(
            parent,
            _("日志级别"),
            _("设置应用程序的日志详细程度。DEBUG最详细，ERROR最精简。"),
            ["DEBUG", "INFO", "WARNING", "ERROR"]
        )
        # --- 命令行语言设置 ---
        self.general_i18n_lang_menu, self.general_i18n_lang_var = create_option_menu_row(
            parent,
            _("命令行语言"),
            _("设置在后端或命令行模式下运行时，输出日志和消息所使用的语言。"),
            list(self.LANG_CODE_TO_NAME.values())  # 使用“简体中文”等友好名称
        )

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

            # API Key 输入行
            apikey_entry = create_entry_row(card, "  " + _("API Key"), "")

            # 模型选择器行
            model_selector = create_model_selector_row(card, "  " + _("模型"), _("要使用的模型名称。"), p_key)

            # Base URL 输入行
            baseurl_entry = create_entry_row(card, "  " + _("Base URL"),
                                             _("部分服务商或代理需要填写，例如 http://localhost:8080/v1"))

            # --- 新增：测试连接按钮 ---
            test_button_frame = ctk.CTkFrame(card, fg_color="transparent")
            test_button_frame.grid(row=card.grid_size()[1], column=1, sticky="e", padx=10, pady=(5, 10))

            test_button = ctk.CTkButton(
                test_button_frame,
                text=_("测试连接"),
                width=100,
                font=self.app_font,
                # 使用 lambda 传递当前的服务商key
                command=lambda p_k=p_key: self.start_ai_connection_test(p_k)
            )
            test_button.pack()

            # 保存对控件的引用
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

    def start_ai_connection_test(self, provider_key: str):
        """
        启动一个后台任务来测试指定的AI服务商连接。
        """
        self._log_to_viewer(f"INFO: 正在测试 '{provider_key}' 的连接...")

        # 1. 从UI输入框直接获取最新的配置信息
        safe_key = provider_key.replace('-', '_')
        try:
            api_key = getattr(self, f"ai_{safe_key}_apikey_entry").get().strip()

            model_selector = getattr(self, f"ai_{safe_key}_model_selector")
            _frame, entry, dropdown, dropdown_var, _button = model_selector
            model = dropdown_var.get() if dropdown.winfo_viewable() else entry.get().strip()

            base_url = getattr(self, f"ai_{safe_key}_baseurl_entry").get().strip() or None
        except AttributeError:
            self.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载。"))
            return

        # 2. 检查代理设置
        proxies = None
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and ai_tab.ai_proxy_var.get():
            http_proxy = self.downloader_proxy_http_entry.get().strip()
            https_proxy = self.downloader_proxy_https_entry.get().strip()
            if http_proxy or https_proxy:
                proxies = {'http': http_proxy, 'https': https_proxy}

        # 3. 显示一个小的“测试中”弹窗
        self.progress_dialog = ProgressDialog(self, title=_("正在测试..."), app_font=self.app_font)
        self.progress_dialog.update_progress(0, _("正在连接到 {}...").format(provider_key))

        # 4. 在后台线程中执行测试
        def test_thread():
            success, message = AIWrapper.test_connection(
                provider=provider_key,
                api_key=api_key,
                model=model,
                base_url=base_url,
                proxies=proxies
            )
            # 将结果放入消息队列，由主线程处理
            self.message_queue.put(("ai_test_result", (success, message)))

        threading.Thread(target=test_thread, daemon=True).start()



    def _apply_config_values_to_editor(self):
        """
        将 self.current_config 的值填充到已创建的编辑器控件中。
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

        # --- 通用设置 ---
        if hasattr(cfg, 'log_level'):
            self.general_log_level_var.set(cfg.log_level)

        if hasattr(cfg, 'i18n_language'):
            lang_code_from_config = cfg.i18n_language
            display_name = self.LANG_CODE_TO_NAME.get(lang_code_from_config, "简体中文")
            self.general_i18n_lang_var.set(display_name)

        # --- Downloader Configuration ---
        update_widget(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        update_widget(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)

        # 【修改点 1】确保 force_download 始终为布尔值
        self.downloader_force_download_var.set(bool(cfg.downloader.force_download))

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

        # 【修改点 2】确保 force_gff_db_creation 始终为布尔值
        self.pipeline_force_gff_db_var.set(bool(pipe_cfg.force_gff_db_creation))

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

        # 更新所有按钮状态
        self._update_button_states()
        self._log_to_viewer(_("UI已根据当前配置刷新。"))

        # --- 【新增】在应用配置的最后，根据新配置更新日志级别 ---
        if self.current_config and hasattr(self.current_config, 'log_level'):
            self.reconfigure_logging(self.current_config.log_level)

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

                # --- 更新通用配置 ---

            if hasattr(updated_config, 'log_level'):
                updated_config.log_level = self.general_log_level_var.get()
            if hasattr(updated_config, 'i18n_language'):
                display_name_from_ui = self.general_i18n_lang_var.get()
                # 从显示名称找到对应的代码，如果找不到，默认保存 'zh-hans'
                code_to_save = self.LANG_NAME_TO_CODE.get(display_name_from_ui, "zh-hans")
                updated_config.i18n_language = code_to_save

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

            # 将用户选择的显示名称转换回程序的内部键再保存
            selected_display_name = self.ai_default_provider_var.get()
            provider_key_to_save = ai_cfg.default_provider  # 默认为旧值

            # 创建一个从显示名称到内部键的反向映射
            name_to_key_map = {v['name']: k for k, v in self.AI_PROVIDERS.items()}
            if selected_display_name in name_to_key_map:
                provider_key_to_save = name_to_key_map[selected_display_name]

            ai_cfg.default_provider = provider_key_to_save  # 保存正确的内部键

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
            detailed_error = f"{_('在更新或保存配置时发生错误')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.show_error_message(_("保存错误"), detailed_error)

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

    def _create_tools_frame(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=_("数据工具"), font=self.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        # 【修复】移除了 command=self._on_tab_change
        self.tools_notebook = ctk.CTkTabview(frame, corner_radius=8)

        if hasattr(self.tools_notebook, '_segmented_button'):
            self.tools_notebook._segmented_button.configure(font=self.app_font)
        self.tools_notebook.grid(row=1, column=0, padx=30, pady=10, sticky="nsew")
        return frame


    def _populate_tools_notebook(self):
        self.tool_tab_instances = {}
        tab_class_map = {
            "download": DataDownloadTab, "homology": HomologyTab, "locus_conversion": LocusConversionTab,
            "gff_query": GFFQueryTab, "annotation": AnnotationTab, "ai_assistant": AIAssistantTab,
            "genome_identifier": GenomeIdentifierTab, "xlsx_to_csv": XlsxConverterTab
        }
        for key in self.TOOL_TAB_ORDER:
            tab_name = _(self.TAB_TITLE_KEYS[key])
            tab_frame = self.tools_notebook.add(tab_name)
            if TabClass := tab_class_map.get(key):
                self.tool_tab_instances[key] = TabClass(parent=tab_frame, app=self)
            else:
                self._log_to_viewer(f"WARNING: No Tab class found for key '{key}'.", "WARNING")
        self.tools_notebook.set(_(self.TAB_TITLE_KEYS["download"]))



    def start_annotation_task(self):
        """
        【最终修正版】启动功能注释任务。
        根据 annotation_tab.py 的实际UI控件进行修正。
        """
        # 1. 配置检查
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 2. 从UI控件收集参数
        try:
            # 从 self.app 动态添加的属性中获取控件和值
            gene_ids_text = self.annotation_genes_textbox.get("1.0", tk.END).strip()
            gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]

            # 【修正】获取唯一的基因组ID
            assembly_id = self.selected_annotation_assembly.get()

            # 从复选框获取要执行的注释类型
            anno_types = []
            if self.go_anno_var.get(): anno_types.append('go')
            if self.ipr_anno_var.get(): anno_types.append('ipr')
            if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
            if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

            output_path = self.annotation_output_csv_entry.get().strip() or None


        except AttributeError as e:
            self.show_error_message(_("UI错误"), _("功能注释选项卡似乎缺少必要的UI控件。错误: {}").format(e))
            return

        if not gene_ids: self.show_error_message(_("输入缺失"), _("请输入要注释的基因ID。")); return
        if not assembly_id or assembly_id == _("无可用版本"): self.show_error_message(_("输入缺失"),
                                                                                      _("请选择一个基因组版本。")); return
        if not anno_types: self.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。")); return

        # output_path 是可选的，不强制检查
        task_kwargs = {
            'config': self.current_config,
            'gene_ids': gene_ids,
            'source_genome': assembly_id,
            'target_genome': assembly_id, # 对于简单注释，源和目标是相同的
            'bridge_species': self.current_config.integration_pipeline.bridge_species_name,
            'annotation_types': anno_types,
            'output_path': output_path,
            'output_dir': os.path.join(os.getcwd(), "annotation_results") # 提供一个备用目录
        }

        self._start_task(
            task_name=_("功能注释"),
            target_func=run_functional_annotation,
            kwargs=task_kwargs
        )



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
            if hasattr(sys, '_MEIPASS'):
                # 打包环境
                base_path = sys._MEIPASS
            else:
                # 源码环境：获取项目根目录 (ui文件夹的上一级)
                base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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

    def change_appearance_mode_event(self, selected_display_mode: str):
        """【修正】当外观模式改变时，应用更改并将其保存到 ui_settings.json。"""
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(selected_display_mode, "System")

        # 1. 应用新模式
        ctk.set_appearance_mode(new_mode)

        # 2. 更新内存中的UI设置
        self.ui_settings['appearance_mode'] = new_mode

        # 3. 持久化保存到文件
        self._save_ui_settings()

        # 4. 更新日志颜色等依赖外观模式的UI元素
        self._update_log_tag_colors()

    def on_language_change(self, selected_display_name: str):
        """当语言改变时，只更新主配置文件 config.yml。"""
        if not self.current_config or not self.config_path:
            self.show_warning_message(_("无法保存"), _("请先加载一个配置文件才能更改并保存语言设置。"))
            # 即使无法保存，也应该更新当前会话的语言
            new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")
            self.update_language_ui(new_language_code)
            return

        new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")

        # 1. 更新内存中的配置对象
        self.current_config.i18n_language = new_language_code

        # 2. 将改动保存回 config.yml 文件
        try:
            if save_config(self.current_config, self.config_path):
                self._log_to_viewer(
                    _("语言设置 '{}' 已成功保存到 {}").format(new_language_code, os.path.basename(self.config_path)))
            else:
                raise IOError(_("保存配置时返回False"))
        except Exception as e:
            self.show_error_message(_("保存失败"), _("无法将新的语言设置保存到配置文件中: {}").format(e))

        # 3. 更新当前界面的语言
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
        self._bind_mouse_wheel_to_scrollable(self.log_textbox)
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.log_textbox.tag_config("error_log", foreground="#d9534f")
        self.log_textbox.tag_config("warning_log", foreground="#f0ad4e")


    def browse_download_output_dir(self):
        """
        打开文件夹选择对话框，让用户选择下载文件的输出目录。
        """
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory and self.download_output_dir_entry:
            self.download_output_dir_entry.delete(0, tk.END)
            self.download_output_dir_entry.insert(0, directory)




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


    def _toggle_homology_warning_label(self):
        """根据“基因组转换”的严格模式开关，显示或隐藏警告标签。"""
        # 确保UI控件已创建
        if not hasattr(self, 'homology_warning_label'):
            return

        if self.homology_strict_priority_var.get():
            self.homology_warning_label.pack_forget()  # 开关开启，隐藏警告
        else:
            # 开关关闭，显示警告
            self.homology_warning_label.pack(side="left", padx=15, pady=0)



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
        【完整版】将 self.current_config 的所有设置应用到整个用户界面。
        这是在加载或保存配置后，刷新UI的中央枢纽。
        """
        self._log_to_viewer(_("正在应用配置到整个UI..."), "DEBUG")

        # 1. 更新主页上的当前配置文件路径显示
        path_text = _("当前配置: {}").format(os.path.basename(self.config_path)) if self.config_path else _(
            "未加载配置")
        if hasattr(self, 'config_path_label') and self.config_path_label.winfo_exists():
            self.config_path_label.configure(text=path_text)

        # 2. 更新配置编辑器页面
        # 这个方法会判断是否需要创建UI，并使用新配置填充所有输入框
        self._handle_editor_ui_update()

        # 3. 更新所有工具选项卡中需要显示基因组版本(Assembly ID)的下拉菜单
        self._update_assembly_id_dropdowns()

        # 4. 调用每个选项卡自己的更新方法（如果存在）
        # 这使得每个选项卡可以根据新配置独立更新其内部状态
        for tab_instance in self.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_from_config'):
                try:
                    tab_instance.update_from_config()
                except Exception as e:
                    self._log_to_viewer(f"Error updating tab {tab_instance.__class__.__name__}: {e}", "ERROR")

        # 5. 【核心】智能地更新全局日志级别
        # 这个方法会检查级别是否真的改变，避免重复操作
        if self.current_config and hasattr(self.current_config, 'log_level'):
            self.reconfigure_logging(self.current_config.log_level)

        # 6. 根据当前状态（是否有任务在运行、是否加载了配置）更新所有按钮的可点击状态
        self._update_button_states()

        self._log_to_viewer(_("UI已根据当前配置刷新。"))



    def _handle_editor_ui_update(self):
        """
        【优化版】仅用数据更新已存在的配置编辑器UI，或切换其可见性。
        不再负责创建控件，因此执行速度很快。
        """
        if not self.editor_ui_built:
            self._log_to_viewer("ERROR: _handle_editor_ui_update called before editor UI was built.", "ERROR")
            return

        if self.current_config:
            # 如果有配置，显示滚动框，隐藏提示标签
            self.editor_scroll_frame.grid()
            self.editor_no_config_label.grid_remove()
            # 快速填充数据
            self._apply_config_values_to_editor()
            self.save_editor_button.configure(state="normal")
        else:
            # 如果没有配置，隐藏滚动框，显示提示标签
            self.editor_scroll_frame.grid_remove()
            self.editor_no_config_label.grid()
            self.save_editor_button.configure(state="disabled")



    def _setup_fonts(self):
        """设置全局字体，并实现字体栈回退机制。"""
        # 定义一个字体栈，程序会从前到后依次尝试使用
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        monospace_font_stack = ["Consolas", "Courier New", "monospace"]  # 新增等宽字体栈
        available_fonts = tkfont.families()

        selected_font = "sans-serif"  # 默认的回退字体
        for font_name in font_stack:
            if font_name in available_fonts:
                selected_font = font_name
                print(f"INFO: UI font has been set to: {selected_font}")
                break

        selected_mono_font = "monospace"  # 默认等宽字体
        for font_name in monospace_font_stack:
            if font_name in available_fonts:
                selected_mono_font = font_name
                print(f"INFO: Monospace UI font has been set to: {selected_mono_font}")
                break

        self.app_font = ctk.CTkFont(family=selected_font, size=14)
        self.app_font_italic = ctk.CTkFont(family=selected_font, size=14, slant="italic")
        self.app_font_bold = ctk.CTkFont(family=selected_font, size=15, weight="bold")
        self.app_subtitle_font = ctk.CTkFont(family=selected_font, size=16)
        self.app_title_font = ctk.CTkFont(family=selected_font, size=24, weight="bold")
        self.app_comment_font = ctk.CTkFont(family=selected_font, size=12)
        self.app_font_mono = ctk.CTkFont(family=selected_mono_font, size=12)  # NEW: 等宽字体定义

    def update_language_ui(self, lang_code_to_set: Optional[str] = None):
        """
        【最终版】动态更新整个UI的语言，处理所有控件类型。
        """
        global _

        # 1. 确定要设置的语言代码
        if not lang_code_to_set:
            # 如果未指定语言，则从主配置中读取
            if self.current_config and hasattr(self.current_config, 'i18n_language'):
                lang_code_to_set = self.current_config.i18n_language
            else:
                # 如果没有配置文件，则使用默认语言
                lang_code_to_set = 'zh-hans'

        # 2. 设置全局翻译函数
        _ = setup_localization(language_code=lang_code_to_set)

        # 3. 更新所有需要翻译的UI控件

        # 更新窗口标题
        if hasattr(self, 'title_text_key'):
            self.title(_(self.title_text_key))

        # 更新语言下拉菜单自身的显示值
        display_name_to_set = self.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        if hasattr(self, 'selected_language_var'):
            self.selected_language_var.set(display_name_to_set)

        # 更新外观模式下拉菜单的文本和值
        if hasattr(self, 'appearance_mode_optionemenu'):
            current_mode_key = self.ui_settings.get("appearance_mode", "System")
            mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}

            self.appearance_mode_optionemenu.configure(values=list(mode_map_to_display.values()))
            self.selected_appearance_var.set(mode_map_to_display.get(current_mode_key, _("系统")))

        # 更新工具栏的选项卡标题 (如果存在)
        if hasattr(self, 'tools_notebook') and hasattr(self, 'TOOL_TAB_ORDER'):
            try:
                new_tab_titles = [_(self.TAB_TITLE_KEYS[key]) for key in self.TOOL_TAB_ORDER]
                # CTkTabView 的标题是通过其内部的 _segmented_button 设置的
                if hasattr(self.tools_notebook, '_segmented_button'):
                    self.tools_notebook._segmented_button.configure(values=new_tab_titles)
            except Exception as e:
                logger.warning(f"动态更新TabView标题时出错: {e}")

        # 遍历所有已注册的简单控件进行翻译
        if hasattr(self, 'translatable_widgets'):
            for widget, key_or_options in self.translatable_widgets.items():
                if not (widget and widget.winfo_exists()):
                    continue

                # 对不同注册方式进行处理
                try:
                    if isinstance(key_or_options, str):
                        # 最简单的情况：key直接是待翻译文本
                        widget.configure(text=_(key_or_options))
                    elif isinstance(key_or_options, tuple):
                        # 处理特殊元组格式，例如 ("config_path_display", "当前配置: {}", "未加载配置")
                        widget_type = key_or_options[0]
                        if widget_type == "config_path_display":
                            if self.config_path:
                                widget.configure(text=_(key_or_options[1]).format(os.path.basename(self.config_path)))
                            else:
                                widget.configure(text=_(key_or_options[2]))
                except Exception as e:
                    logger.warning(f"更新控件 {widget} 文本时出错: {e}")

        # 刷新所有文本框的占位符
        if hasattr(self, 'homology_map_genes_textbox'):
            self._add_placeholder(self.homology_map_genes_textbox, self.placeholder_key_homology, force=True)
        if hasattr(self, 'gff_query_genes_textbox'):
            self._add_placeholder(self.gff_query_genes_textbox, self.placeholder_key_gff_genes, force=True)
        if hasattr(self, 'gff_query_region_entry'):
            self.gff_query_region_entry.configure(
                placeholder_text=_(self.placeholders[self.placeholder_key_gff_region]))

        # 记录日志
        self._log_to_viewer(_("界面语言已更新。"), "INFO")

    def _update_assembly_id_dropdowns(self):
        if not self.genome_sources_data:
            assembly_ids = [_("无可用基因组")]
        else:
            assembly_ids = list(self.genome_sources_data.keys()) or [_("无可用基因组")]

        for tab_instance in self.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_assembly_dropdowns'):
                try:
                    tab_instance.update_assembly_dropdowns(assembly_ids)
                except Exception as e:
                    self._log_to_viewer(f"Error updating assembly dropdowns for {tab_instance.__class__.__name__}: {e}", "ERROR")


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

    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any]):
        if self.active_task_name:
            self.show_warning_message(_("任务进行中"), f"{_('另一个任务')} '{self.active_task_name}' {_('正在运行，请稍候。')}")
            return

        self._update_button_states(is_task_running=True)
        self.active_task_name = task_name
        self._log_to_viewer(f"{_(task_name)} {_('任务开始...')}")

        self.cancel_current_task_event.clear()

        self.progress_dialog = ProgressDialog(self, title=_(task_name), on_cancel=self.cancel_current_task_event.set, app_font=self.app_font)

        kwargs['cancel_event'] = self.cancel_current_task_event
        kwargs['status_callback'] = self.gui_status_callback
        kwargs['progress_callback'] = self.gui_progress_callback

        def task_wrapper():
            try:
                result_data = target_func(**kwargs)
                if self.cancel_current_task_event.is_set():
                    self.message_queue.put(("task_done", (False, task_name, "CANCELLED")))
                else:
                    self.message_queue.put(("task_done", (True, task_name, result_data)))
            except Exception as e:
                detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                self.message_queue.put(("error", detailed_error))

        threading.Thread(target=task_wrapper, daemon=True).start()



    def  _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        """【新增】任务结束时统一处理UI更新的辅助函数。"""
        # 调用新弹窗的 close() 方法，它本身就是安全的
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close()
        self.progress_dialog = None  # 清空引用

        self._update_button_states(is_task_running=False)
        self.active_task_name = None

        if result_data == "CANCELLED":
            status_msg = f"{_(task_display_name)} {_('已被用户取消。')}"
        else:
            status_msg = f"{_(task_display_name)} {_('完成。')}" if success else f"{_(task_display_name)} {_('失败。')}"

        # 确保 status_label 存在
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.configure(text=status_msg)


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
        """
        向UI日志框发送日志，但会遵循全局日志级别。
        """
        try:
            # 获取根日志记录器，它的级别是我们统一配置的
            root_logger = logging.getLogger()

            # 获取当前消息的数字级别，例如 "DEBUG" -> 10, "INFO" -> 20
            message_level_num = logging.getLevelName(level.upper())

            # 【关键】只有当消息的级别 >= 根记录器的级别时，才将其放入队列
            if isinstance(message_level_num, int) and message_level_num >= root_logger.getEffectiveLevel():
                # 将日志消息放入队列，由主线程处理
                self.log_queue.put((message, level))

        except Exception as e:
            # 增加一个保险的异常处理，防止此方法自身出错
            print(f"FATAL ERROR in _log_to_viewer: {e}")


    def gui_status_callback(self, message: str, level: str = "INFO"):
        """
        线程安全的回调函数，用于更新状态栏和日志。
        现在能正确处理日志级别(level)参数，以匹配后端调用。
        """
        level_upper = level.upper()

        # 根据日志级别决定如何处理
        if level_upper == "ERROR":
            # 尝试获取锁，如果成功，则发送错误消息到主线程进行弹窗处理
            if self.error_dialog_lock.acquire(blocking=False):
                self.message_queue.put(("error", message))
            # 如果获取锁失败，说明已有另一个错误正在处理，忽略此错误以避免弹窗轰炸
        else:
            # 对于非错误消息（如INFO, WARNING, DEBUG），只更新状态栏的文本
            self.message_queue.put(("status", message))

        # 无论如何，都将原始消息和级别传递给日志查看器进行显示
        self._log_to_viewer(str(message), level=level_upper)

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
        try:
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                self._display_log_message_in_ui(log_message, log_level)

            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()
                handler = self.message_handlers.get(message_type)
                if handler:
                    handler(data) if data is not None else handler()
                else:
                    self._log_to_viewer(f"未知的消息类型: '{message_type}'", "WARNING")
        except queue.Empty:
            pass
        except Exception as e:
            logging.critical(f"在 check_queue_periodic 中发生未处理的异常: {e}", exc_info=True)
        self.after(100, self.check_queue_periodic)



    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        """【新增】任务结束时统一处理UI更新的辅助函数。"""
        try:
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.close()
        except tk.TclError as e:
            self._log_to_viewer(f"关闭进度弹窗时捕获到无害的TclError: {e}", "DEBUG")
        finally:
            self.progress_dialog = None

        self._update_button_states(is_task_running=False)
        self.active_task_name = None

        if result_data == "CANCELLED":
            status_msg = f"{task_display_name} {_('已被用户取消。')}"
        else:
            status_msg = f"{task_display_name} {_('完成。')}" if success else f"{task_display_name} {_('失败。')}"
        self.status_label.configure(text=status_msg)

    def _handle_startup_complete(self, data: dict):
        self._hide_progress_dialog()
        self.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")
        if config_data:
            self.current_config = config_data
            self.config_path = getattr(config_data, '_config_file_abs_path_', None)
            self._log_to_viewer(_("默认配置文件加载成功。"))
            self._apply_config_to_ui()
        else:
            self._log_to_viewer(_("未找到或无法加载默认配置文件。"), "WARNING")
        self.update_language_ui()
        self._update_button_states()

    def _handle_startup_failed(self, data: str):
        self._hide_progress_dialog()
        self.show_error_message(_("启动错误"), str(data))
        self._update_button_states()

    def _handle_config_load_task_done(self, data: tuple):
        self._hide_progress_dialog()
        success, result_data, filepath = data
        if success:
            self.current_config = result_data
            self.config_path = os.path.abspath(filepath)
            self.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
            self.genome_sources_data = get_genome_data_sources(self.current_config, logger_func=self._log_to_viewer)
            self._apply_config_to_ui()
        else:
            self.show_error_message(_("加载失败"), str(result_data))

    def _handle_task_done(self, data: tuple):
        success, task_display_name, result_data = data
        self._finalize_task_ui(task_display_name, success, result_data)

        if task_display_name == _("位点转换"):
            if hasattr(self, 'locus_conversion_result_textbox'):
                textbox = self.locus_conversion_result_textbox
                textbox.configure(state="normal")
                textbox.delete("1.0", tk.END)
                if success and result_data is not None and not result_data.empty:
                    textbox.insert("1.0", result_data.to_string(index=False))
                elif success:
                    textbox.insert("1.0", _("未找到有效的同源区域。"))
                else:
                    textbox.insert("1.0", _("任务执行失败，无结果。"))
                textbox.configure(state="disabled")

        elif "富集分析" in task_display_name:  # 匹配 "GO富集分析", "KEGG富集分析" 等
            if success and result_data:
                self._show_plot_results(result_data)
            elif success:
                self.show_info_message(_("分析完成"), _("富集分析完成，但没有发现任何显著富集的结果，因此未生成图表。"))

    def _handle_error(self, data: str):
        # 弹出错误消息对话框
        self.show_error_message(_("任务执行出错"), data)
        # 调用新的统一处理函数来重置UI
        self._finalize_task_ui(self.active_task_name or _("未知任务"), success=False)
        # 更新状态栏以显示错误
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            status_text = f"{_('任务终止于')}: {str(data)[:100]}..."
            self.status_label.configure(text=status_text)

        # 释放错误对话框锁
        if self.error_dialog_lock.locked():
            self.error_dialog_lock.release()



    def _handle_status(self, data: str):
        self.status_label.configure(text=str(data)[:150])

    def _handle_progress(self, data: tuple):
        percentage, text = data
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.update_progress(percentage, text)

    def _handle_update_sheets_dropdown(self, data: tuple):
        sheet_names, excel_path, error = data
        self._update_sheet_dropdowns_ui(sheet_names, excel_path, error)

    def _handle_ai_models_fetched(self, data: tuple):
        provider_key, models = data
        self._log_to_viewer(f"{provider_key} {_('模型列表获取成功。')} ")
        model_selector_tuple = getattr(self, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
        if model_selector_tuple:
            _frame, entry, dropdown, dropdown_var, _button = model_selector_tuple
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
            self.show_info_message(_("刷新成功"), f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')}")

    def _handle_ai_models_failed(self, data: tuple):
        provider_key, error_msg = data
        self._log_to_viewer(f"{provider_key} {_('模型列表获取失败:')} {error_msg}", "ERROR")
        model_selector_tuple = getattr(self, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
        if model_selector_tuple:
            _a, entry, dropdown, _a, _a = model_selector_tuple
            dropdown.grid_remove()
            entry.grid()
            self.show_warning_message(_("刷新失败"),
                                      f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")

    def _handle_auto_identify_success(self, data: tuple):
        target_var, assembly_id = data
        if self.genome_sources_data and assembly_id in self.genome_sources_data.keys():
            if isinstance(target_var, tk.StringVar):
                target_var.set(assembly_id)
                self._log_to_viewer(f"UI已自动更新基因为: {assembly_id}", "DEBUG")


    def _handle_auto_identify_fail(self, data=None):
        pass  # 识别失败，静默处理

    def _handle_auto_identify_error(self, data: str):
        self._log_to_viewer(f"自动识别基因组时发生错误: {data}", "ERROR")

    def _handle_ai_test_result(self, data: tuple):
        if self.progress_dialog:
            self.progress_dialog.close()
        success, message = data
        if success:
            self.show_info_message(_("测试成功"), message)
        else:
            self.show_error_message(_("测试失败"), message)


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
        将鼠标进入事件绑定到控件，使其自动获取焦点，从而启用滚轮滚动。
        """
        if widget and hasattr(widget, 'focus_set'):
            widget.bind("<Enter>", lambda event, w=widget: w.focus_set())


    def on_closing(self):
        dialog = MessageDialog(
            parent=self,
            title=_("退出程序"),
            message=_("您确定要退出吗?"),
            icon_type="question",
            buttons=[_("确定"), _("取消")],
            app_font=self.app_font
        )
        # wait_window 会阻塞程序，直到弹窗关闭
        dialog.wait_window()

        # 弹窗关闭后，检查其 result 属性
        if dialog.result == _("确定"):
            self.destroy()  # 如果用户点击了“确定”，则关闭主程序

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
                    # 加载完成后，将结果和成功状态打包，发送一个特定的完成消息
                    self.message_queue.put(("config_load_task_done", (True, config_data, filepath)))
                except Exception as e:
                    # 如果加载失败，发送带有失败状态和详细错误信息的消息
                    detailed_error = f"{e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                    self.message_queue.put(("config_load_task_done", (False, detailed_error, None)))

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
                if save_config(config_data, save_path):
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
        【逻辑修正版】处理“生成默认配置”按钮的点击事件。
        修正了对话框不会等待用户选择的问题。
        """

        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if not output_dir:
            self._log_to_viewer(_("用户取消了目录选择。"))
            return

        self._log_to_viewer(f"{_('用户选择的配置目录:')} {output_dir}")
        main_config_filename = "config.yml" # 配置文件的默认路径
        main_config_path = os.path.join(output_dir, main_config_filename)

        should_overwrite = False
        if os.path.exists(main_config_path):
            # 1. 创建对话框实例
            dialog = MessageDialog(
                parent=self,
                title=_("文件已存在"),
                message=_("配置文件 '{}' 已存在于所选目录中。\n\n您想覆盖它吗？\n(选择“否”将直接加载现有文件)").format(
                    main_config_filename),
                buttons=[_("是 (覆盖)"), _("否 (加载)")],
                icon_type="question",
                app_font=self.app_font
            )

            # 2. 调用 wait_window() 使程序暂停，直到对话框关闭
            dialog.wait_window()

            # 3. 在对话框关闭后，从其 .result 属性获取用户的选择
            user_choice = dialog.result

            # 4. 根据用户的选择执行正确的逻辑
            if user_choice == _("是 (覆盖)"):
                should_overwrite = True
            elif user_choice == _("否 (加载)"):
                self.load_config_file(filepath=main_config_path)
                return  # 直接加载并结束此函数
            else:
                # 如果用户关闭了窗口或点击了其他按钮（如果有的话）
                self._log_to_viewer(_("用户取消了操作。"))
                return  # 结束此函数

        # 只有在文件不存在或用户明确选择“覆盖”时，才会执行到这里
        try:
            self._log_to_viewer(_("正在生成默认配置文件..."))
            success, new_main_cfg_path, new_gs_cfg_path = generate_default_config_files(
                output_dir,
                overwrite=should_overwrite,
                main_config_filename=main_config_filename
            )
            if success:
                msg = f"{_('默认配置文件已成功生成到:')}\n{new_main_cfg_path}\n{new_gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"

                # 同样，这里的弹窗也需要等待
                load_dialog = MessageDialog(parent=self, title=_("生成成功"), message=msg, buttons=[_("是"), _("否")],
                                            icon_type="info", app_font=self.app_font)
                load_dialog.wait_window()
                if load_dialog.result == _("是"):
                    self.load_config_file(filepath=new_main_cfg_path)
            else:
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
            self._log_to_viewer(f"{_('基因组源文件已保存到:')} {abs_path}")
            self.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}")
            self._log_to_viewer(
                f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}")
            self._log_to_viewer(
                f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")

    def _update_button_states(self, is_task_running=False):
        # 这个方法现在是安全的，因为它不再引用任何已经被删除的按钮
        action_state = "disabled" if is_task_running else "normal"

        # 侧边栏和配置按钮
        if hasattr(self, 'navigation_frame'):
            for btn_name in ['home_button', 'editor_button', 'tools_button', 'load_config_button', 'gen_config_button']:
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    if btn.winfo_exists():
                        btn.configure(state=action_state)

        # 通过Tab实例来更新按钮状态
        for tab_key, tab_instance in self.tool_tab_instances.items():
            if hasattr(tab_instance, 'update_button_state'):
                tab_instance.update_button_state(is_task_running, bool(self.current_config))


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





    def _select_output_directory(self, target_entry_widget: ctk.CTkEntry):
        """
        打开一个文件对话框让用户选择一个目录，然后将选定的目录路径
        填充到指定的 Entry widget 中。如果 Entry 中已有文件名，则保留文件名。
        """
        initial_dir = os.path.dirname(target_entry_widget.get()) if target_entry_widget.get() else os.getcwd()
        selected_dir = filedialog.askdirectory(
            parent=self,
            initialdir=initial_dir,
            title=_("选择输出目录")
        )
        if selected_dir:
            current_file_name = os.path.basename(target_entry_widget.get())
            if current_file_name:  # If there's an existing filename, preserve it
                new_path = os.path.join(selected_dir, current_file_name)
            else:  # Otherwise, just use the directory
                new_path = selected_dir
            target_entry_widget.delete(0, tk.END)
            target_entry_widget.insert(0, new_path)

    def _auto_identify_genome_version(self, gene_input_textbox: ctk.CTkTextbox, target_assembly_var: tk.StringVar):
        current_text = gene_input_textbox.get("1.0", tk.END).strip()
        # 检查是否为占位符
        is_placeholder = False
        for key, value in self.placeholders.items():
            if current_text == _(value):
                is_placeholder = True
                break

        if not current_text or is_placeholder:
            return

        gene_ids = [gene.strip() for gene in current_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids:
            return

        if not self.genome_sources_data:
            self._log_to_viewer(_("警告: 基因组源数据未加载，无法自动识别基因组。"), "WARNING")
            return

        self._log_to_viewer(_("正在尝试自动识别基因组版本..."), "INFO")

        def _identify_in_thread():
            try:
                identified_assembly_id = identify_genome_from_gene_ids(
                    gene_ids,
                    self.genome_sources_data,
                    status_callback=self._log_to_viewer
                )
                if identified_assembly_id:
                    self.message_queue.put(("auto_identify_success", (target_assembly_var, identified_assembly_id)))
                else:
                    self.message_queue.put(("auto_identify_fail", None))
            except Exception as e:
                self.message_queue.put(("auto_identify_error", str(e)))

        threading.Thread(target=_identify_in_thread, daemon=True).start()


    def _update_language_ui(self):
        """
        动态更新整个UI的语言。此版本能正确处理 CTkTabView 的标题。
        """
        # 更新窗口标题
        self.title(_(self.title_text_key))

        # 更新菜单栏
        if hasattr(self, 'menu_bar'):
            self.file_menu.entryconfigure(0, label=_("加载配置..."))
            self.file_menu.entryconfigure(1, label=_("保存配置..."))
            self.file_menu.entryconfigure(3, label=_("退出"))

            self.settings_menu.entryconfigure(0, label=_("语言"))
            self.settings_menu.entryconfigure(1, label=_("主题"))

            self.help_menu.entryconfigure(0, label=_("查看帮助文档"))
            self.help_menu.entryconfigure(1, label=_("关于"))

            self.menu_bar.entryconfigure(0, label=_("文件"))
            self.menu_bar.entryconfigure(1, label=_("设置"))
            self.menu_bar.entryconfigure(2, label=_("帮助"))

        # --- 正确地更新 TabView 标题 ---
        try:
            # 1. 生成一个新的、翻译后的标题列表，顺序由 TOOL_TAB_ORDER 保证
            new_tab_titles = [_(self.TAB_TITLE_KEYS[key]) for key in self.TOOL_TAB_ORDER]

            # 2. 直接配置 TabView 内部的分段按钮的 `values` 属性
            if hasattr(self, 'tools_notebook') and hasattr(self.tools_notebook, '_segmented_button'):
                self.tools_notebook._segmented_button.configure(values=new_tab_titles)
            else:
                logger.warning("无法找到 tools_notebook 或其 _segmented_button 来更新选项卡标题。")

        except Exception as e:
            logger.critical(f"动态更新TabView时发生严重错误: {e}")

        # 更新所有其他已注册的、需要翻译的控件
        for widget, key_or_options in self.translatable_widgets.items():
            try:
                if isinstance(key_or_options, str):  # 简单文本
                    widget.configure(text=_(key_or_options))
                elif isinstance(key_or_options, dict):  # 带有占位符的文本
                    placeholder_key = key_or_options.get("placeholder")
                    if placeholder_key and widget.cget("text") == placeholder_key:
                        # 注意：这里我们不翻译占位符本身，因为它们是临时的
                        pass
                    elif "text" in key_or_options:
                        widget.configure(text=_(key_or_options["text"]))
            except Exception as e:
                logger.warning(f"更新控件 {widget} 文本时出错: {e}")

        # 刷新占位符文本（如果它们当前正显示的话）
        if hasattr(self, 'homology_map_genes_textbox'):
            self._add_placeholder(self.homology_map_genes_textbox, self.placeholder_genes_homology_key, force=True)
        if hasattr(self, 'gff_query_genes_textbox'):
            self._add_placeholder(self.gff_query_genes_textbox, self.placeholder_genes_gff_key, force=True)

        self._log_to_viewer(_("界面语言已更新。"), "INFO")



    def _on_annotation_gene_input_change(self, event=None):
        """
        功能注释输入框基因ID变化时触发基因组自动识别。
        """
        self._auto_identify_genome_version(self.annotation_genes_textbox, self.selected_annotation_assembly)


    def _update_homology_version_warnings(self):
        """【新增】检查所选基因组的同源库版本并在UI上显示警告。"""
        if not self.current_config or not self.genome_sources_data:
            return

        source_id = self.selected_homology_source_assembly.get()
        target_id = self.selected_homology_target_assembly.get()

        warning_color = ("#D84315", "#FF7043")  # 橙色警告
        ok_color = ("#2E7D32", "#A5D6A7")  # 绿色正常

        # 检查源基因组标签是否存在并更新
        if hasattr(self,
                   'homology_source_version_warning_label') and self.homology_source_version_warning_label.winfo_exists():
            source_info = self.genome_sources_data.get(source_id)
            if source_info and hasattr(source_info, 'bridge_version'):
                if source_info.bridge_version and source_info.bridge_version.lower() == 'tair10':
                    self.homology_source_version_warning_label.configure(
                        text="⚠️ " + _("使用旧版 tair10"), text_color=warning_color
                    )
                else:
                    self.homology_source_version_warning_label.configure(
                        text="✓ " + _("使用新版 Araport11"), text_color=ok_color
                    )
            else:
                self.homology_source_version_warning_label.configure(text="")

        # 检查目标基因组标签是否存在并更新
        if hasattr(self,
                   'homology_target_version_warning_label') and self.homology_target_version_warning_label.winfo_exists():
            target_info = self.genome_sources_data.get(target_id)
            if target_info and hasattr(target_info, 'homology_type'):
                if target_info.homology_type and target_info.homology_type.lower() == 'TAIR10':
                    self.homology_target_version_warning_label.configure(
                        text="⚠️ " + _("使用旧版 tair10"), text_color=warning_color
                    )
                else:
                    self.homology_target_version_warning_label.configure(
                        text="✓ " + _("使用新版 Araport11"), text_color=ok_color
                    )
            else:
                self.homology_target_version_warning_label.configure(text="")


    def _add_placeholder(self, textbox_widget, placeholder_key, force=False):
        """如果文本框为空，则向其添加占位符文本和样式。"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        # 通过固定的key获取源文本，然后翻译
        placeholder_text = _(self.placeholders.get(placeholder_key, ""))

        if not current_text or force:
            if force and current_text == placeholder_text: return  # 如果强制刷新且内容已是占位符，则无需操作
            if force: textbox_widget.delete("1.0", tk.END)

            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[
                1]

            textbox_widget.configure(font=self.app_font_italic, text_color=placeholder_color_value)
            textbox_widget.insert("1.0", placeholder_text)

    def _clear_placeholder(self, textbox_widget, placeholder_key):
        """如果文本框中的内容是占位符，则清除它，并恢复正常字体和颜色。"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        # 通过固定的key获取源文本，然后翻译
        placeholder_text = _(self.placeholders.get(placeholder_key, ""))

        if current_text == placeholder_text:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(font=self.app_font, text_color=self.default_text_color)

    def reconfigure_logging(self, log_level_str: str):
        """
        【最终修正版】智能地、强制地重新配置全局日志级别，包括所有处理器。
        """
        try:
            # 获取根日志记录器
            root_logger = logging.getLogger()

            # 获取将要设置的数字级别，例如 "INFO" -> 20
            new_level = logging.getLevelName(log_level_str.upper())

            # 必须确保 new_level 是一个有效的数字级别
            if not isinstance(new_level, int):
                self._log_to_viewer(f"警告: 无效的日志级别 '{log_level_str}'", "WARNING")
                return

            # 获取根记录器当前的级别
            current_level = root_logger.getEffectiveLevel()

            # 只有在需要改变级别时才执行操作
            if current_level != new_level:
                # 1. 设置根记录器的级别，这是最高阀门
                root_logger.setLevel(new_level)

                # 2. 【关键】遍历所有现有的处理器，强制将它们的级别也一同更新
                for handler in root_logger.handlers:
                    handler.setLevel(new_level)

                # 在UI日志框中记录这次成功的操作
                self._log_to_viewer(f"全局日志级别已更新为: {log_level_str}", "INFO")

        except Exception as e:
            self._log_to_viewer(f"配置日志级别时出错: {e}", "ERROR")


    def _browse_directory(self, entry_widget: ctk.CTkEntry):
        """打开目录选择对话框并填充到输入框。"""
        directory = filedialog.askdirectory(title=_("选择目录"))
        if directory and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory)


    def _show_plot_results(self, image_paths: List[str]):
        """在一个新窗口中显示生成的图表。"""
        if not image_paths:
            self.show_info_message(_("无结果"), _("没有生成任何图表文件。"))
            return

        window = ctk.CTkToplevel(self)
        window.title(_("富集分析结果"))
        window.geometry("800x650")
        window.transient(self)
        window.grab_set()

        if len(image_paths) == 1:
            # 只显示一张图片
            img = ctk.CTkImage(Image.open(image_paths[0]), size=(780, 600))
            label = ctk.CTkLabel(window, text="", image=img)
            label.pack(expand=True, fill="both", padx=10, pady=10)
        else:
            # 创建一个可滚动的框架来显示多张图片
            scroll_frame = ctk.CTkScrollableFrame(window)
            scroll_frame.pack(expand=True, fill="both")
            for i, path in enumerate(image_paths):
                try:
                    ctk.CTkLabel(scroll_frame, text=os.path.basename(path), font=self.app_font_bold).pack(pady=(15, 5))
                    img = ctk.CTkImage(Image.open(path), size=(750, 580))
                    label = ctk.CTkLabel(scroll_frame, text="", image=img)
                    label.pack(pady=(0, 10))
                except Exception as e:
                    ctk.CTkLabel(scroll_frame, text=f"{_('加载图片失败:')} {os.path.basename(path)}\n{e}").pack()

    def start_enrichment_task(self):
        """
        【新增】启动富集分析与绘图任务。
        """
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 从 AnnotationTab 实例获取UI控件
        anno_tab = self.tool_tab_instances.get('annotation')
        if not anno_tab:
            self.show_error_message(_("UI错误"), _("无法找到功能注释选项卡实例。"))
            return

        try:
            gene_ids_text = anno_tab.annotation_genes_textbox.get("1.0", tk.END).strip()
            assembly_id = anno_tab.selected_annotation_assembly.get()
            output_dir = anno_tab.enrichment_output_dir_entry.get().strip()
            analysis_type = anno_tab.analysis_type_var.get().lower()
            has_header = anno_tab.has_header_var.get()
            has_log2fc = anno_tab.has_log2fc_var.get()

            plot_types = []
            if anno_tab.bubble_plot_var.get(): plot_types.append('bubble')
            if anno_tab.bar_plot_var.get(): plot_types.append('bar')

        except AttributeError as e:
            self.show_error_message(_("UI错误"), f"{_('功能注释选项卡似乎缺少必要的UI控件。')}\n{e}")
            return

        # 解析基因列表
        lines = gene_ids_text.splitlines()
        if has_header and len(lines) > 1:
            lines = lines[1:]

        study_gene_ids = []
        gene_log2fc_map = {} if has_log2fc else None

        try:
            if has_log2fc:
                for i, line in enumerate(lines):
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    if len(parts) >= 2:
                        gene_id, log2fc_str = parts[0], parts[1]
                        gene_log2fc_map[gene_id] = float(log2fc_str)
                        study_gene_ids.append(gene_id)
                    else:  # 格式错误
                        raise ValueError(f"{_('第 {i + 1} 行格式错误，需要两列 (基因, Log2FC):')} '{line}'")
            else:
                for line in lines:
                    if not line.strip(): continue
                    parts = re.split(r'[\s,;]+', line.strip())
                    study_gene_ids.extend([p for p in parts if p])
        except ValueError as e:
            self.show_error_message(_("输入格式错误"), str(e))
            return

        study_gene_ids = sorted(list(set(study_gene_ids)))

        # 输入验证
        if not study_gene_ids: self.show_error_message(_("输入缺失"), _("请输入或粘贴要分析的基因ID。")); return
        if not assembly_id or assembly_id == _("加载中..."): self.show_error_message(_("输入缺失"),
                                                                                     _("请选择一个基因组版本。")); return
        if not plot_types: self.show_error_message(_("输入缺失"), _("请至少选择一种图表类型进行绘制。")); return
        if not output_dir: self.show_error_message(_("输入缺失"), _("请选择图表的输出目录。")); return

        task_kwargs = {
            'config': self.current_config,
            'assembly_id': assembly_id,
            'study_gene_ids': study_gene_ids,
            'analysis_type': analysis_type,
            'plot_types': plot_types,
            'output_dir': output_dir,
            'gene_log2fc_map': gene_log2fc_map,
            # 从配置文件获取默认绘图参数，这里简化为固定值，后续可改为从UI获取
            'top_n': 20,
            'sort_by': 'p.adjust',
            'show_title': True,
            'width': 8.0,
            'height': 6.0,
            'file_format': 'png',
            'collapse_transcripts': True
        }

        self._start_task(
            task_name=f"{analysis_type.upper()} {_('富集分析')}",
            target_func=run_enrichment_pipeline,
            kwargs=task_kwargs
        )

    def _check_genome_download_status(self, genome_info: dict, file_key: str) -> str:
        """
        【已修正】检查单个基因组的单个文件类型是否已完整下载。
        返回 'complete', 'incomplete', 'missing' 三种状态之一。
        """
        if not self.current_config or not genome_info:
            return 'missing'

        # 使用 get_local_downloaded_file_path 检查文件是否存在
        local_path = get_local_downloaded_file_path(self.current_config, genome_info, file_key)

        url_attr = f"{file_key}_url"
        if hasattr(genome_info, url_attr) and getattr(genome_info, url_attr):
            # 如果配置了URL
            if local_path and os.path.exists(local_path):
                return 'complete'  # 文件已下载
            else:
                return 'missing'  # 文件未下载
        else:
            # 如果未配置URL，则认为此文件类型不适用
            return 'not_applicable'  # 或者可以返回一个新状态


    def _refresh_ai_models_on_tab(self):
        """刷新AI助手页面上当前选定服务商的模型列表。"""
        selected_display_name = self.ai_selected_provider_var.get()
        name_to_key_map = {v['name']: k for k, v in self.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_display_name)
        if provider_key:
            # 调用与配置编辑器中相同的后台刷新逻辑
            self._fetch_ai_models(provider_key)


    def _save_config_from_ui(self):
        """一个简单的后台保存配置的方法，用于UI交互。"""
        if self.current_config and self.config_path:
            if save_config(self.current_config, self.config_path):
                self._log_to_viewer(_("配置已自动保存。"), "INFO")
            else:
                self._log_to_viewer(_("自动保存配置失败。"), "WARNING")

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()
    app.mainloop()
