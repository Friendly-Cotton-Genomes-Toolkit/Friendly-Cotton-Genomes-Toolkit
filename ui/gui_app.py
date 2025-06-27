import copy
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from queue import Queue
from tkinter import filedialog, font as tkfont
from typing import Dict, Optional, Any, List  # 确保 Tuple 被导入

import customtkinter as ctk
from PIL import Image

from cotton_toolkit.config.loader import save_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.utils.logger import setup_global_logger
from ui import AnnotationTab
from ui.event_handler import EventHandler
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.data_download_tab import DataDownloadTab
from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
from ui.tabs.gff_query_tab import GFFQueryTab
from ui.tabs.homology_tab import HomologyTab
from ui.tabs.locus_conversion_tab import LocusConversionTab
from ui.tabs.xlsx_converter_tab import XlsxConverterTab
from ui.ui_manager import UIManager

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

        self._setup_fonts()

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

        # --- 核心状态变量 ---
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data: Optional[Dict[str, Any]] = None
        self.excel_sheet_cache: Dict[str, List[str]] = {}
        self.config_path_display_var = tk.StringVar(value=_("未加载配置"))
        self.log_queue = Queue()
        self.message_queue = Queue()
        self.active_task_name: Optional[str] = None
        self.cancel_current_task_event = threading.Event()
        self.ui_settings: Dict[str, Any] = {}
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

        # --- 初始化管理器 ---
        self.ui_manager = UIManager(self)
        self.event_handler = EventHandler(self)  # EventHandler 负责初始化其消息处理器

        # --- 设置字体和资源 ---
        self._create_image_assets()  # 图片资源加载保留在 gui_app
        self.secondary_text_color = ("#495057", "#999999")

        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        # --- 创建主布局和页面 (委托给 UIManager) ---
        self.ui_manager.setup_initial_ui()

        # 启动异步加载和主循环
        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)  # 委托给 EventHandler
        self.set_app_icon()  # 图标设置保留在 gui_app

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
            # 捕获所有异常（包括上面主动抛出的 FileNotFoundError）
            # 打印原始警告（如果是文件不存在的话）
            if not isinstance(e, FileNotFoundError):
                print(f"警告: 加载图片资源 '{file_name}' 时发生错误: {e}")

            # --- 核心修改：创建并返回一个透明的占位图 ---
            placeholder = Image.new('RGBA', (1, 1), (0, 0, 0, 0))  # 创建一个1x1的完全透明的图像
            return ctk.CTkImage(placeholder, size=size)

    def _gui_start_ai_connection_test(self, provider_key: str):
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
            self.ui_manager.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载。"))  # 修改调用
            return

        # 2. 检查代理设置
        proxies = None
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and ai_tab.ai_proxy_var.get():
            http_proxy = self.proxy_http_entry.get().strip()
            https_proxy = self.proxy_https_entry.get().strip()
            if http_proxy or https_proxy:
                proxies = {'http': http_proxy, 'https': https_proxy}

        # 3. 显示一个小的“测试中”弹窗 (委托给 UIManager)
        self.ui_manager._show_progress_dialog(self, title=_("正在测试..."), app_font=self.app_font)  # 修改调用
        self.ui_manager.progress_dialog.update_progress(0, _("正在连接到 {}...").format(provider_key))  # 修改调用

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
            # 【修正】使用 self.app_font 而不是 self.app.app_font
            textbox = ctk.CTkTextbox(row_frame, height=120, font=self.app_font, wrap="word")
            self.ui_manager._bind_mouse_wheel_to_scrollable(textbox)
            textbox.grid(row=0, column=1, sticky="ew")
            if tooltip:
                # 【修正】使用 self.app_comment_font 而不是 self.app.app_comment_font
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
            # 【修正】使用 self.app_font 而不是 self.app.app_font
            option_menu = ctk.CTkOptionMenu(row_frame, variable=var, values=options, font=self.app_font,
                                            dropdown_font=self.app_font)
            option_menu.grid(row=0, column=1, sticky="ew")
            if tooltip:
                # 【修正】使用 self.app_comment_font 而不是 self.app.app_comment_font
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
            # 【修正】使用 self.app_font 而不是 self.app.app_font
            dropdown = ctk.CTkOptionMenu(entry_container, variable=var, values=[_("点击刷新")], font=self.app_font,
                                         dropdown_font=self.app_font)
            dropdown.grid(row=0, column=0, sticky="ew")
            dropdown.grid_remove()
            # 【修正】使用 self.app_font 而不是 self.app.app_font
            button = ctk.CTkButton(entry_container, text=_("刷新"), width=60, font=self.app_font,
                                   command=lambda p_key=provider_key: self._gui_fetch_ai_models(p_key))
            button.grid(row=0, column=1, padx=(10, 0))
            if tooltip:
                # 【修正】使用 self.app_comment_font 而不是 self.app.app_comment_font
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
            # 【修正】使用 self.app_font_bold 而不是 self.app.app_font_bold
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
            list(self.LANG_CODE_TO_NAME.values())
        )

        self.proxy_http_entry = create_entry_row(parent, _("HTTP代理"),
                                                 _("HTTP代理地址，例如 'http://your-proxy:port'。不使用则留空。"))
        self.proxy_https_entry = create_entry_row(parent, _("HTTPS代理"),
                                                  _("HTTPS代理地址，例如 'https://your-proxy:port'。不使用则留空。"))

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
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = create_switch_row(parent,
                                                                                            _("为数据下载使用网络代理"),
                                                                                            _("是否为基因组数据和注释文件下载启用代理。"))

        # --- AI Services Configuration ---
        create_section_title(parent, _("AI 服务配置"))
        provider_display_names = [v['name'] for v in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu, self.ai_default_provider_var = create_option_menu_row(parent, _("默认AI服务商"),
                                                                                             _("选择默认使用的AI模型提供商。"),
                                                                                             provider_display_names)
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row(parent, _("为AI服务使用网络代理"),
                                                                            _("是否为连接AI模型API启用代理。"))

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
            baseurl_entry = create_entry_row(card, "  " + _("Base URL"),
                                             _("部分服务商或代理需要填写，例如 http://localhost:8080/v1"))

            test_button_frame = ctk.CTkFrame(card, fg_color="transparent")
            test_button_frame.grid(row=card.grid_size()[1], column=1, sticky="e", padx=10, pady=(5, 10))
            test_button = ctk.CTkButton(test_button_frame, text=_("测试连接"), width=100, font=self.app_font,
                                        command=lambda p_k=p_key: self._gui_start_ai_connection_test(p_k))
            test_button.pack()

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

        self._log_to_viewer(_("配置编辑器的值已从当前配置刷新。"), "DEBUG")

        ### --- 核心修改：使用 ui_manager 来调用按钮更新方法 --- ###
        self.ui_manager.update_button_states()  # 修改调用

        self._log_to_viewer(_("UI已根据当前配置刷新。"))

        if self.current_config and hasattr(self.current_config, 'log_level'):
            self.reconfigure_logging(self.current_config.log_level)

    def _save_config_from_editor(self):
        """
        从静态UI控件中收集数据并保存配置。
        """
        if not self.current_config or not self.config_path:
            self.ui_manager.show_error_message(_("错误"), _("没有加载配置文件，无法保存。"))  # 修改调用
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

            # --- Save the final object ---
            if save_config(updated_config, self.config_path):
                self.current_config = updated_config
                self.ui_manager.show_info_message(_("保存成功"), _("配置文件已更新。"))  # 修改调用
                self.ui_manager.update_ui_from_config()  # 修改调用
            else:
                self.ui_manager.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))  # 修改调用

        except Exception as e:
            detailed_error = f"{_('在更新或保存配置时发生错误')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.ui_manager.show_error_message(_("保存错误"), detailed_error)  # 修改调用

    def _create_home_frame(self, parent):
        """
        创建并返回主页框架。
        采用两列等宽的网格布局，使卡片能随窗口宽度动态调整，更美观。
        """
        # 使用可滚动的框架，并让其内容在垂直方向上居中
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

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

        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, pady=20, padx=20, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        config_card = ctk.CTkFrame(cards_frame)
        config_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)

        config_title = ctk.CTkLabel(config_card, text="", font=self.card_title_font)
        config_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[config_title] = "配置文件"

        load_button = ctk.CTkButton(config_card, text="", command=self.event_handler.load_config_file, height=40)
        load_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[load_button] = "加载配置文件..."

        gen_button = ctk.CTkButton(config_card, text="", command=self.event_handler._generate_default_configs_gui,
                                   height=40)
        gen_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[gen_button] = "生成默认配置..."

        help_card = ctk.CTkFrame(cards_frame)
        help_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)

        help_title = ctk.CTkLabel(help_card, text="", font=self.card_title_font)
        help_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[help_title] = "帮助与支持"

        docs_button = ctk.CTkButton(help_card, text="", command=self.event_handler._open_online_help, height=40)
        docs_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[docs_button] = "在线帮助文档"

        about_button = ctk.CTkButton(help_card, text="", command=self.event_handler._show_about_window, height=40)
        about_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[about_button] = "关于本软件"

        return frame

    def _create_tools_frame(self, parent):
        """
        创建“数据工具”选项卡的主框架。
        :param parent:
        :return:
        """

        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=_("数据工具"), font=self.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        self.tools_notebook = ctk.CTkTabview(frame, corner_radius=8)

        if hasattr(self.tools_notebook, '_segmented_button'):
            self.tools_notebook._segmented_button.configure(font=self.app_font)
        self.tools_notebook.grid(row=1, column=0, padx=30, pady=10, sticky="nsew")
        return frame

    def _populate_tools_notebook(self):
        """
        填充工具选项卡视图，实例化各个工具选项卡。
        """
        self.tool_tab_instances = {}
        tab_class_map = {
            "download": DataDownloadTab, "homology": HomologyTab, "locus_conversion": LocusConversionTab,
            "gff_query": GFFQueryTab, "annotation": AnnotationTab, "ai_assistant": AIAssistantTab,
            "genome_identifier": GenomeIdentifierTab, "xlsx_to_csv": XlsxConverterTab
        }
        for key in self.TOOL_TAB_ORDER:
            tab_name = _(self.TAB_TITLE_KEYS[key])
            tab_frame = self.tools_notebook.add(tab_name)

            # --- 核心修正 ---
            # 将每个选项卡页的背景设置为透明，以解决黑块问题
            tab_frame.configure(fg_color="transparent")

            if TabClass := tab_class_map.get(key):
                # 传递 self.ui_manager 和 self.event_handler 给每个 Tab 实例
                self.tool_tab_instances[key] = TabClass(parent=tab_frame, app=self)
            else:
                self._log_to_viewer(f"WARNING: No Tab class found for key '{key}'.", "WARNING")
        self.tools_notebook.set(_(self.TAB_TITLE_KEYS["download"]))

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

    def _create_editor_frame(self, parent):
        """
        创建配置编辑器的主框架，包含一个可滚动区域和一个提示标签。
        此方法保持在 gui_app.py 中，因为它定义了编辑器页面自身的结构。
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
        self.ui_manager._bind_mouse_wheel_to_scrollable(self.editor_scroll_frame)

        # 2. 创建一个“未加载配置”的提示标签
        self.editor_no_config_label = ctk.CTkLabel(page, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                   font=self.app_subtitle_font,
                                                   text_color=self.secondary_text_color)
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew")

        # 绑定快捷键
        page.bind('<Control-s>', lambda event: self._save_config_from_editor())
        page.bind('<Control-S>', lambda event: self._save_config_from_editor())
        self.editor_scroll_frame.bind('<Control-s>', lambda event: self._save_config_from_editor())
        self.editor_scroll_frame.bind('<Control-S>', lambda event: self._save_config_from_editor())

        return page

    def _gui_fetch_ai_models(self, provider_key: str):
        """
        直接从静态UI输入框获取API Key和URL来刷新模型列表。
        现在会检查AI助手的代理开关。
        """
        self._log_to_viewer(
            f"{_('正在获取')} '{self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)}' {_('的模型列表...')}")

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
                self.ui_manager.show_error_message(_("内部错误"), f"{_('未知的服务商密钥:')} {provider_key}")  # 修改调用
                return
        except AttributeError:
            self.ui_manager.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载，请稍后再试。"))  # 修改调用
            return

        if not api_key or "YOUR_" in api_key:
            self.ui_manager.show_warning_message(_("缺少API Key"),  # 修改调用
                                                 _("请先在编辑器中为 '{}' 填写有效的API Key。").format(provider_key))
            return

        # --- 统一代理逻辑 ---
        proxies_to_use = None
        # 检查AI助手的代理开关是否打开
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and hasattr(ai_tab, 'ai_proxy_var') and ai_tab.ai_proxy_var.get():  # 仅在开关打开时才读取代理地址
            # 代理地址本身还是从配置编辑器的输入框读取，这是统一的配置源
            http_proxy = self.proxy_http_entry.get().strip()  # 从 gui_app 的属性获取
            https_proxy = self.proxy_https_entry.get().strip()  # 从 gui_app 的属性获取
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

        # 1. 为 ProgressDialog 提供一个实例 (由 UIManager 创建和管理)
        self.ui_manager._show_progress_dialog(  # 修改调用
            title=_("获取模型列表"),
            message=_("正在从 {} 获取模型列表，请稍候...").format(
                self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)),
            on_cancel=self.cancel_model_fetch_event.set,
        )

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

    def _handle_editor_ui_update(self):
        """
        仅用数据更新已存在的配置编辑器UI，或切换其可见性。
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
        """【修改】设置全局字体, 保存字体家族名称而不是CTkFont对象。"""
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        monospace_font_stack = ["Consolas", "Courier New", "monospace"]
        available_fonts = tkfont.families()

        # 普通字体
        selected_font = "sans-serif"
        for font_name in font_stack:
            if font_name in available_fonts:
                selected_font = font_name
                print(f"INFO: UI font has been set to: {selected_font}")
                break
        self.font_family = selected_font

        # 等宽字体
        selected_mono_font = "monospace"
        for font_name in monospace_font_stack:
            if font_name in available_fonts:
                selected_mono_font = font_name
                print(f"INFO: Monospace UI font has been set to: {selected_mono_font}")
                break
        self.mono_font_family = selected_mono_font

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

    def _log_to_viewer(self, message, level="INFO"):
        """向UI日志队列发送消息。"""
        root_logger = logging.getLogger()
        message_level_num = logging.getLevelName(level.upper())
        if isinstance(message_level_num, int) and message_level_num >= root_logger.getEffectiveLevel():
            self.log_queue.put((message, level))

    def check_queue_periodic(self):
        try:
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                if self.ui_manager:
                    self.ui_manager.display_log_message_in_ui(log_message, log_level)
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()
                handler = self.event_handler.message_handlers.get(message_type)
                if handler:
                    handler(data) if data is not None else handler()
                else:
                    logger.warning(f"未知的消息类型: '{message_type}'")
        except queue.Empty:
            pass
        except Exception as e:
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

    def reconfigure_logging(self, log_level_str: str):
        """
        智能地、强制地重新配置全局日志级别，包括所有处理器。
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()
    app.mainloop()