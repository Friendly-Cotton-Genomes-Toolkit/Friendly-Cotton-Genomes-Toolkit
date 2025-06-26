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
from cotton_toolkit.utils.logger import setup_global_logger
from ui import ProgressDialog, MessageDialog, AnnotationTab
from ui.event_handler import EventHandler
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.data_download_tab import DataDownloadTab
from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
from ui.tabs.gff_query_tab import GFFQueryTab
from ui.tabs.homology_tab import HomologyTab
from ui.tabs.locus_conversion_tab import LocusConversionTab
from ui.tabs.xlsx_converter_tab import XlsxConverterTab
from ui.ui_manager import UIManager
from ui.utils.gui_helpers import identify_genome_from_gene_ids

print("INFO: gui_app.py - All modules imported.")

# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #

logger = logging.getLogger("cotton_toolkit.gui")


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    AI_PROVIDERS = {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                    "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                    "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                    "openai_compatible": {"name": _("通用OpenAI兼容接口")}}

    # 定义工具选项卡的顺序
    TOOL_TAB_ORDER = [
        "download",
        "xlsx_to_csv",
        "genome_identifier",
        "homology",
        "locus_conversion",
        "gff_query",
        "annotation",
        "ai_assistant",
    ]

    # 定义用于翻译的选项卡标题键
    TAB_TITLE_KEYS = {
        "download": "数据下载",
        "xlsx_to_csv": "XLSX转CSV",
        "genome_identifier": "基因组鉴定",
        "homology": "同源转换",
        "locus_conversion": "位点转换",
        "gff_query": "GFF查询",
        "annotation": "功能注释",
        "ai_assistant": "AI助手",
    }


    def __init__(self):
        super().__init__()
        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1100x750")
        self.minsize(800, 600)

        # 1. 为占位符功能提供颜色定义
        self.placeholder_color = ("gray50", "gray50")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]
        self.placeholders = {
            "homology_genes": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
            "gff_genes": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
            "gff_region": _("例如: Gh_A01:1-100000"),
            "genes_input": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
        }

        # 2. 为AI模型获取功能初始化事件对象
        self.cancel_model_fetch_event = threading.Event()

        # 3. 为旧的“整合分析”UI控件初始化Tkinter变量 (提高代码健壮性)
        #    尽管这些控件可能已不再主界面使用，但初始化可以防止潜在错误
        self.selected_bsa_sheet = tk.StringVar()
        self.selected_hvg_sheet = tk.StringVar()
        self.selected_bsa_assembly = tk.StringVar()
        self.selected_hvg_assembly = tk.StringVar()


        # --- 核心状态变量 ---
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data: Optional[Dict[str, Any]] = None
        self.excel_sheet_cache: Dict[str, List[str]] = {}
        self.config_path_display_var = tk.StringVar(value=_("未加载配置"))
        self.log_queue = Queue()
        self.message_queue = Queue()
        self.active_task_name: Optional[str] = None
        self.progress_dialog: Optional['ProgressDialog'] = None
        self.cancel_current_task_event = threading.Event()
        self.error_dialog_lock = threading.Lock()
        self.ui_settings: Dict[str, Any] = {}
        self.about_window: Optional[ctk.CTkToplevel] = None
        self.translatable_widgets: Dict[ctk.CTkBaseClass, Any] = {}
        self.log_viewer_visible: bool = False
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.editor_ui_built: bool = False

        # --- 初始化所有UI属性 ---
        self.home_frame = None
        self.editor_frame = None
        self.tools_frame = None
        self.navigation_frame = None
        self.main_content_frame = None
        self.status_bar_frame = None
        self.log_viewer_frame = None
        self.editor_scroll_frame = None
        self.editor_no_config_label = None
        self.save_editor_button = None
        self.tools_notebook = None
        self.tool_tab_instances = {}

        self.logo_image, self.home_icon, self.tools_icon, self.settings_icon = None, None, None, None
        self.folder_icon, self.new_file_icon, self.help_icon, self.info_icon = None, None, None, None

        self.home_button, self.editor_button, self.tools_button = None, None, None
        self.status_label, self.progress_bar = None, None
        self.log_viewer_label_widget, self.toggle_log_button, self.clear_log_button, self.log_textbox = None, None, None, None
        self.language_label, self.language_optionmenu = None, None
        self.appearance_mode_label, self.appearance_mode_optionemenu = None, None

        # 编辑器控件
        self.general_log_level_menu, self.general_log_level_var = None, None
        self.general_i18n_lang_menu, self.general_i18n_lang_var = None, None
        self.proxy_http_entry, self.proxy_https_entry = None, None
        self.downloader_sources_file_entry, self.downloader_output_dir_entry = None, None
        self.downloader_force_download_switch, self.downloader_force_download_var = None, None
        self.downloader_max_workers_entry = None
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = None, None
        self.ai_default_provider_menu, self.ai_default_provider_var = None, None
        self.ai_use_proxy_switch, self.ai_use_proxy_var = None, None
        self.ai_translation_prompt_textbox, self.ai_analysis_prompt_textbox = None, None
        self.anno_db_root_dir_entry = None
        self.pipeline_input_excel_entry, self.pipeline_bsa_sheet_entry, self.pipeline_hvg_sheet_entry = None, None, None
        self.pipeline_output_sheet_entry, self.pipeline_bsa_assembly_entry, self.pipeline_hvg_assembly_entry = None, None, None
        self.pipeline_bridge_species_entry, self.pipeline_gff_db_dir_entry = None, None
        self.pipeline_force_gff_db_switch, self.pipeline_force_gff_db_var = None, None
        self.pipeline_common_hvg_log2fc_entry = None
        self.s2b_sort_by_entry, self.s2b_ascending_entry, self.s2b_top_n_entry = None, None, None
        self.s2b_evalue_entry, self.s2b_pid_entry, self.s2b_score_entry = None, None, None
        self.b2t_sort_by_entry, self.b2t_ascending_entry, self.b2t_top_n_entry = None, None, None
        self.b2t_evalue_entry, self.b2t_pid_entry, self.b2t_score_entry = None, None, None

        # --- 初始化管理器 ---
        self.ui_manager = UIManager(self)
        self.event_handler = EventHandler(self)
        self.message_handlers = self.event_handler.initialize_message_handlers()

        # --- 设置字体和资源 ---
        self._setup_fonts()
        self._create_image_assets()
        self.secondary_text_color = ("#495057", "#999999")

        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        # --- 创建主布局和页面 ---
        self.ui_manager.create_main_layout()
        self.ui_manager.init_pages()

        # 启动异步加载和主循环
        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)
        self.set_app_icon()


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

        self.proxy_http_entry = create_entry_row(parent, _("HTTP代理"), _("HTTP代理地址，例如 'http://your-proxy:port'。不使用则留空。"))
        self.proxy_https_entry = create_entry_row(parent, _("HTTPS代理"), _("HTTPS代理地址，例如 'https://your-proxy:port'。不使用则留空。"))


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
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = create_switch_row(parent, _("为数据下载使用网络代理"), _("是否为基因组数据和注释文件下载启用代理。"))

        # --- AI Services Configuration ---
        create_section_title(parent, _("AI 服务配置"))
        provider_display_names = [v['name'] for v in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu, self.ai_default_provider_var = create_option_menu_row(parent, _("默认AI服务商"),
                                                                                             _("选择默认使用的AI模型提供商。"),
                                                                                             provider_display_names)
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row(parent, _("为AI服务使用网络代理"), _("是否为连接AI模型API启用代理。"))


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
            display_name = self.LANG_CODE_TO_NAME.get(cfg.i18n_language, "简体中文")
            self.general_i18n_lang_var.set(display_name)
        if hasattr(cfg, 'proxies'):
            update_widget(self.proxy_http_entry, cfg.proxies.http)
            update_widget(self.proxy_https_entry, cfg.proxies.https)


        # --- Downloader Configuration ---
        dl_cfg = cfg.downloader
        update_widget(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        update_widget(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(bool(cfg.downloader.force_download))
        update_widget(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        self.downloader_use_proxy_var.set(bool(dl_cfg.use_proxy_for_download))

        # --- AI Services Configuration ---
        ai_cfg = cfg.ai_services
        default_display_name = self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name',
                                                                                               cfg.ai_services.default_provider)
        self.ai_default_provider_var.set(default_display_name)
        self.ai_use_proxy_var.set(bool(ai_cfg.use_proxy_for_ai))

        for p_key, p_cfg in cfg.ai_services.providers.items():
            safe_key = p_key.replace('-', '_')
            if hasattr(self, f"ai_{safe_key}_apikey_entry"):
                update_widget(getattr(self, f"ai_{safe_key}_apikey_entry"), p_cfg.api_key)

                model_selector = getattr(self, f"ai_{safe_key}_model_selector")
                _frame, entry, dropdown, dropdown_var, _button = model_selector
                update_widget(entry, p_cfg.model)
                dropdown_var.set(p_cfg.model)

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

        ### --- 核心修改：使用 ui_manager 来调用按钮更新方法 --- ###
        self.ui_manager.update_button_states()

        self._log_to_viewer(_("UI已根据当前配置刷新。"))

        if self.current_config and hasattr(self.current_config, 'log_level'):
            self.reconfigure_logging(self.current_config.log_level)

    def _save_config_from_editor(self):
        """
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
                code_to_save = self.LANG_NAME_TO_CODE.get(self.general_i18n_lang_var.get(), "zh-hans")
                updated_config.i18n_language = code_to_save

            if hasattr(updated_config, 'proxies'):
                updated_config.proxies.http = self.proxy_http_entry.get() or None
                updated_config.proxies.https = self.proxy_https_entry.get() or None

            # --- Update Downloader Config ---
            dl_cfg = updated_config.downloader
            dl_cfg.genome_sources_file = self.downloader_sources_file_entry.get()
            dl_cfg.download_output_base_dir = self.downloader_output_dir_entry.get()
            dl_cfg.force_download = self.downloader_force_download_var.get()
            dl_cfg.max_workers = to_int(self.downloader_max_workers_entry.get(), 3)
            dl_cfg.use_proxy_for_download = self.downloader_use_proxy_var.get()


            # --- Update AI Services Config ---
            ai_cfg = updated_config.ai_services

            # 将用户选择的显示名称转换回程序的内部键再保存
            selected_display_name = self.ai_default_provider_var.get()
            provider_key_to_save = ai_cfg.default_provider  # 默认为旧值
            ai_cfg.use_proxy_for_ai = self.ai_use_proxy_var.get()

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
                self.ui_manager.update_ui_from_config()
            else:
                self.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))

        except Exception as e:
            detailed_error = f"{_('在更新或保存配置时发生错误')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.show_error_message(_("保存错误"), detailed_error)

    def _create_home_frame(self, parent):
        """
        【最终布局优化版】创建并返回主页框架。
        采用两列等宽的网格布局，使卡片能随窗口宽度动态调整，更美观。
        """
        # 使用可滚动的框架，并让其内容在垂直方向上居中
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)  # 允许内容水平居中

        # --- 顶部信息区 (保持不变) ---
        top_info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        top_info_frame.grid(row=0, column=0, pady=(40, 20), padx=40, sticky="ew")
        top_info_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(top_info_frame, text="", font=self.app_title_font)
        title_label.pack(pady=(0, 10))
        self.translatable_widgets[title_label] = self.title_text_key

        self.config_path_label = ctk.CTkLabel(top_info_frame,
                                              textvariable=self.config_path_display_var,
                                              wraplength=800,
                                              font=self.app_font,
                                              text_color=self.secondary_text_color)
        self.config_path_label.pack(pady=(10, 0))

        ### --- 核心修改：全新、更具扩展性的卡片布局 --- ###

        # 1. 创建一个容器，这个容器会水平填满整个区域
        #    并直接使用它的网格系统来放置两个卡片
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, pady=20, padx=20, sticky="ew")

        # 2. 将容器的网格配置为两列，并且两列的权重都为1
        #    这意味着它们会平分所有可用的水平空间，从而将卡片推向两侧
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        # --- 配置卡片 ---
        # 3. 将第一个卡片直接放入容器的第 0 列
        config_card = ctk.CTkFrame(cards_frame)
        # 使用 sticky="nsew" 让卡片填满其所在的网格单元
        config_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)  # 让卡片内部的按钮可以水平扩展

        config_title = ctk.CTkLabel(config_card, text="", font=self.card_title_font)
        config_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[config_title] = "配置文件"

        load_button = ctk.CTkButton(config_card, text="", command=self.load_config_file, height=40)
        load_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[load_button] = "加载配置文件..."

        gen_button = ctk.CTkButton(config_card, text="", command=self._generate_default_configs_gui, height=40)
        gen_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[gen_button] = "生成默认配置..."

        # --- 帮助与支持卡片 ---
        # 4. 将第二个卡片直接放入容器的第 1 列
        help_card = ctk.CTkFrame(cards_frame)
        help_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)  # 让卡片内部的按钮可以水平扩展

        help_title = ctk.CTkLabel(help_card, text="", font=self.card_title_font)
        help_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[help_title] = "帮助与支持"

        docs_button = ctk.CTkButton(help_card, text="", command=self._open_online_help, height=40)
        docs_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[docs_button] = "在线帮助文档"

        about_button = ctk.CTkButton(help_card, text="", command=self._show_about_window, height=40)
        about_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[about_button] = "关于本软件"

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
        self.card_title_font = ctk.CTkFont(family=selected_font, size=18, weight="bold")



    def _update_assembly_id_dropdowns(self):
        """
        【健壮版】更新所有工具选项卡中的基因组版本下拉菜单。

        该方法的核心职责是：
        1. 从 self.genome_sources_data 中获取一份最新的、可用的基因组版本ID列表。
        2. 遍历所有已经实例化的工具选项卡 (例如 HomologyTab, AnnotationTab 等)。
        3. 如果某个选项卡实例拥有一个名为 `update_assembly_dropdowns` 的方法，
           就把最新的基因组ID列表传递给它，由它自己去更新内部的下拉菜单。

        这种设计模式（称为“委托”或“依赖注入”）极大地降低了主程序（gui_app）与各个
        子模块（各选项卡）之间的耦合度，使得添加或修改工具选项卡时，无需改动
        gui_app.py 中的这个核心更新逻辑。
        """
        if not self.genome_sources_data:
            # 如果基因组源数据尚未加载，准备一个表示“无数据”的列表
            assembly_ids = [_("无可用基因组")]
        else:
            # 如果数据已加载，则提取所有基因组版本的ID作为列表
            # 如果列表为空，也提供一个友好的提示
            assembly_ids = list(self.genome_sources_data.keys()) or [_("无可用基因组")]

        # 遍历所有已创建的工具选项卡实例
        for tab_instance in self.tool_tab_instances.values():
            # 检查当前遍历到的选项卡实例是否有关心基因组列表更新的方法
            if hasattr(tab_instance, 'update_assembly_dropdowns'):
                try:
                    # 如果有，就调用它，并将最新的基因组ID列表作为参数传入
                    tab_instance.update_assembly_dropdowns(assembly_ids)
                except Exception as e:
                    # 捕获并记录在更新特定选项卡时可能发生的任何意外错误，以防止整个程序崩溃
                    self._log_to_viewer(f"Error updating assembly dropdowns for {tab_instance.__class__.__name__}: {e}",
                                        "ERROR")

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
        self.event_handler._start_task(task_name, target_func, kwargs)


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

    def clear_log_viewer(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self._log_to_viewer(_("日志已清除。"))

    def _log_to_viewer(self, message, level="INFO"):
        """向UI日志队列发送消息。"""
        root_logger = logging.getLogger()
        message_level_num = logging.getLevelName(level.upper())
        if isinstance(message_level_num, int) and message_level_num >= root_logger.getEffectiveLevel():
            self.log_queue.put((message, level))


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


    def check_queue_periodic(self):
        """主事件循环，处理后台消息。"""
        try:
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                self.event_handler._display_log_message_in_ui(log_message, log_level)

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
            # 使用 logging 模块记录严重错误，而不是 print
            logger.critical(f"在 check_queue_periodic 中发生未处理的异常: {e}", exc_info=True)

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
        """
        【最终稳定版】处理后台启动任务完成的消息。
        这是修复启动时UI状态不更新问题的关键。
        """
        # 1. 首先，安全地隐藏启动时显示的进度对话框
        self._hide_progress_dialog()

        # 2. 从后台线程传递过来的数据中，提取基因组源和配置信息
        self.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")

        # 3. 如果成功加载了配置数据
        if config_data:
            self.current_config = config_data
            # 从加载的对象中获取文件的绝对路径
            self.config_path = getattr(config_data, 'config_file_abs_path_', None)
            self._log_to_viewer(_("默认配置文件加载成功。"))
        else:
            # 如果没有找到或加载失败
            self._log_to_viewer(_("未找到或无法加载默认配置文件。"), "WARNING")

        # 4. --- 核心修复：在这里执行一次完整的UI刷新 ---
        #    首先，调用 _apply_config_to_ui 来更新所有依赖配置数据的UI元素
        #    （包括我们最关心的主页配置路径标签）。
        self._apply_config_to_ui()

        #    然后，调用 update_language_ui 来确保所有控件的语言都是最新的。
        self.update_language_ui()

        # 5. 最后，根据当前状态（是否有任务、是否有配置）更新所有按钮的可点击状态
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



    def _check_genome_download_status(self, genome_info: dict, file_key: str) -> str:
        """
        检查单个基因组的单个文件类型是否已完整下载。
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
