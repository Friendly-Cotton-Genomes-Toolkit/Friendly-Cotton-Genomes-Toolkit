import copy
import logging # Ensure logging is imported
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from queue import Queue
from tkinter import filedialog, font as tkfont, ttk
from typing import Dict, Optional, Any, List

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

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

_ = lambda s: str(s)

# REMOVE THIS LINE or comment it out
# logger = logging.getLogger("cotton_toolkit.gui")


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    AI_PROVIDERS = {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                    "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                    "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                    "openai_compatible": {"name": _("通用OpenAI兼容接口")}}

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
        super().__init__(themename="litera")

        # Initialize the instance-specific logger for the app object
        self.logger = logging.getLogger(__file__) # ADD THIS LINE. This attaches the logger to the instance.
        self.logger.info("CottonToolkitApp initialized.") # Optional: log app start


        self.app = self # This line is redundant, `self` already refers to the app instance

        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1100x750")
        self.minsize(800, 600)

        self._setup_fonts()

        self.placeholder_color = (self.style.colors.secondary, self.style.colors.secondary)
        # 获取默认文本颜色和次要文本颜色，确保它们是通过lookup或直接的颜色属性
        self.default_text_color = self.style.lookup('TLabel', 'foreground') or '#000000'
        # secondary 颜色是 Colors 对象的一个直接属性
        self.secondary_text_color = self.style.colors.secondary


        self.placeholders = {
            "homology_genes": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
            "gff_genes": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
            "gff_region": _("例如: Gh_A01:1-100000"),
            "genes_input": _("在此处粘贴基因ID，每行一个或用逗号/空格分隔..."),
        }

        self.cancel_model_fetch_event = threading.Event()

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
        self.translatable_widgets: Dict[tk.Widget, Any] = {}
        self.log_viewer_visible: bool = False
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.editor_ui_built: bool = False

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

        self.logo_tk_image = None
        self.home_tk_icon = None
        self.tools_tk_icon = None
        self.settings_tk_icon = None
        self.folder_tk_icon = None
        self.new_file_tk_icon = None
        self.help_tk_icon = None
        self.info_tk_icon = None

        self.logo_image = None
        self.home_icon = None
        self.tools_icon = None
        self.settings_icon = None
        self.folder_icon = None
        self.new_file_icon = None
        self.help_icon = None
        self.info_icon = None

        self.home_button, self.editor_button, self.tools_button = None, None, None
        self.status_label, self.progress_bar = None, None
        self.log_viewer_label_widget, self.toggle_log_button, self.clear_log_button, self.log_textbox = None, None, None, None
        self.language_label, self.language_optionmenu = None, None
        self.appearance_mode_label, self.appearance_mode_optionemenu = None, None

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

        self.ui_manager = UIManager(self)
        self.event_handler = EventHandler(self)

        self._create_image_assets()

        # Ensure setup_global_logger uses the instance logger if needed,
        # but it's typically fine to pass a queue.
        # It's okay to pass self.log_queue here.
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        self.ui_manager.setup_initial_ui()

        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)
        self.set_app_icon()

    def _create_image_assets(self):
        """加载所有图片资源"""
        self.logo_image_path = self._get_image_resource_path("logo.png")
        self.home_icon_path = self._get_image_resource_path("home.png")
        self.tools_icon_path = self._get_image_resource_path("tools.png")
        self.settings_icon_path = self._get_image_resource_path("settings.png")
        self.folder_icon_path = self._get_image_resource_path("folder.png")
        self.new_file_icon_path = self._get_image_resource_path("new-file.png")
        self.help_icon_path = self._get_image_resource_path("help.png")
        self.info_icon_path = self._get_image_resource_path("info.png")

    def _get_image_resource_path(self, file_name):
        try:
            if hasattr(sys, '_MEIPASS'):
                base_path = os.path.join(sys._MEIPASS, "assets")
            else:
                base_path = os.path.join(os.path.dirname(__file__), "assets")
            image_path = os.path.join(base_path, file_name)
            if os.path.exists(image_path):
                return image_path
            else:
                print(f"警告: 图片资源未找到，检查路径: '{image_path}'")
                return None
        except Exception as e:
            print(f"警告: 获取图片资源 '{file_name}' 路径时发生错误: {e}")
            return None

    def _gui_start_ai_connection_test(self, provider_key: str):
        """
        启动一个后台任务来测试指定的AI服务商连接。
        """
        self._log_to_viewer(f"INFO: 正在测试 '{provider_key}' 的连接...")

        safe_key = provider_key.replace('-', '_')
        try:
            api_key = getattr(self, f"ai_{safe_key}_apikey_entry").get().strip()

            model_selector = getattr(self, f"ai_{safe_key}_model_selector")
            _frame, entry, dropdown, dropdown_var, _button = model_selector
            model = dropdown_var.get() if dropdown.winfo_ismapped() else entry.get().strip()

            base_url = getattr(self, f"ai_{safe_key}_baseurl_entry").get().strip() or None
        except AttributeError:
            self.ui_manager.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载。"))
            return

        proxies = None
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and hasattr(ai_tab, 'ai_proxy_var') and ai_tab.ai_proxy_var.get():
            http_proxy = self.proxy_http_entry.get().strip()
            https_proxy = self.proxy_https_entry.get().strip()
            if http_proxy or https_proxy:
                proxies = {'http': http_proxy, 'https': https_proxy}

        self.ui_manager._show_progress_dialog(
            title=_("正在测试..."),
            message=_("正在连接到 {}...").format(provider_key)
        )

        def test_thread():
            success, message = AIWrapper.test_connection(
                provider=provider_key,
                api_key=api_key,
                model=model,
                base_url=base_url,
                proxies=proxies
            )
            self.message_queue.put(("ai_test_result", (success, message)))
            self.message_queue.put(("hide_progress_dialog", None))

        threading.Thread(target=test_thread, daemon=True).start()

    def _create_editor_widgets(self, parent):
        """
        只创建一次配置编辑器的所有UI控件，但不填充数据。
        """
        parent.grid_columnconfigure(0, weight=1)
        current_row = 0

        def create_section_title(p, title_text):
            nonlocal current_row
            ttk.Label(p, text=f"◇ {title_text} ◇", font=self.app_subtitle_font,
                      foreground=self.style.colors.primary).grid(row=current_row, column=0,
                                                                                        pady=(25, 10), sticky="w",
                                                                                        padx=5)
            current_row += 1

        def create_entry_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ttk.Frame(p)
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ttk.Label(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            entry = ttk.Entry(row_frame, font=self.app.app_font)
            entry.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ttk.Label(row_frame, text=tooltip, font=self.app.app_comment_font,
                                             foreground=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)
            current_row += 1
            return entry

        def create_switch_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ttk.Frame(p)
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ttk.Label(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            var = tk.BooleanVar()
            # 修复：ttkb.Checkbutton 不支持直接的 font 参数
            switch = ttkb.Checkbutton(row_frame, text="", variable=var, bootstyle="round-toggle")
            switch.grid(row=0, column=1, sticky="w")
            if tooltip:
                tooltip_label = ttk.Label(row_frame, text=tooltip, font=self.app.app_comment_font,
                                             foreground=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=10)
            current_row += 1
            return switch, var

        def create_textbox_row(p, label_text, tooltip):
            nonlocal current_row
            row_frame = ttk.Frame(p)
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ttk.Label(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="nw", padx=(5, 10))
            # 修复：使用 style.lookup 获取 'TText' 的背景色和前景色
            textbox_bg = self.style.lookup('TText', 'background') or '#FFFFFF'
            textbox_fg = self.style.lookup('TText', 'foreground') or '#000000'

            textbox = tk.Text(row_frame, height=7, font=self.app.app_font, wrap="word",
                                         relief="flat", background=textbox_bg,
                                         foreground=textbox_fg)
            self.ui_manager._bind_mouse_wheel_to_scrollable(textbox)
            textbox.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ttk.Label(row_frame, text=tooltip, font=self.app.app_comment_font,
                                             foreground=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return textbox

        def create_option_menu_row(p, label_text, tooltip, options):
            nonlocal current_row
            row_frame = ttk.Frame(p)
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label = ttk.Label(row_frame, text=label_text, font=self.app_font)
            label.grid(row=0, column=0, sticky="w", padx=(5, 10))
            var = tk.StringVar()
            # 修复：ttkb.OptionMenu 不支持直接的 font 参数
            option_menu = ttkb.OptionMenu(row_frame, var, options[0] if options else "", *options,
                                            style='info.TButton')
            option_menu.grid(row=0, column=1, sticky="ew")
            if tooltip:
                tooltip_label = ttk.Label(row_frame, text=tooltip, font=self.app.app_comment_font,
                                             foreground=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=0)
            current_row += 1
            return option_menu, var

        def create_model_selector_row(p, label_text, tooltip, provider_key):
            nonlocal current_row
            row_frame = ttk.Frame(p)
            row_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(4, 0), padx=5)
            row_frame.grid_columnconfigure(1, weight=1)
            label_widget = ttk.Label(row_frame, text=label_text, font=self.app.app_font)
            label_widget.grid(row=0, column=0, sticky="w", padx=(5, 10))
            entry_container = ttk.Frame(row_frame)
            entry_container.grid(row=0, column=1, sticky="ew")
            entry_container.grid_columnconfigure(0, weight=1)
            entry = ttk.Entry(entry_container, font=self.app.app_font)
            entry.grid(row=0, column=0, sticky="ew")
            var = tk.StringVar(value=_("点击刷新"))
            # 修复：ttkb.OptionMenu 不支持直接的 font 参数
            dropdown = ttkb.OptionMenu(entry_container, var, _("点击刷新"), _("点击刷新"),
                                         style='info.TButton')
            dropdown.grid(row=0, column=0, sticky="ew")
            dropdown.grid_remove()
            # 修复：ttkb.Button 不支持直接的 font 参数
            button = ttkb.Button(entry_container, text=_("刷新"), width=8,
                                   command=lambda p_k=provider_key: self._gui_fetch_ai_models(p_k),
                                   style='info.TButton')
            button.grid(row=0, column=1, padx=(10, 0))
            if tooltip:
                tooltip_label = ttk.Label(row_frame, text=tooltip, font=self.app.app_comment_font,
                                             foreground=self.secondary_text_color, wraplength=500, justify="left")
                tooltip_label.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=2)

            current_row += 1
            return (row_frame, entry, dropdown, var, button)

        def create_provider_card(p, title):
            card = ttk.LabelFrame(p, text=title, bootstyle="info")
            card.pack(fill="x", expand=True, pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)
            return card

        create_section_title(parent, _("通用设置"))
        self.general_log_level_menu, self.general_log_level_var = create_option_menu_row(
            parent,
            _("日志级别"),
            _("设置应用程序的日志详细程度。DEBUG最详细，ERROR最精简。"),
            ["DEBUG", "INFO", "WARNING", "ERROR"]
        )
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

        create_section_title(parent, _("AI 服务配置"))
        provider_display_names = [v['name'] for v in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu, self.ai_default_provider_var = create_option_menu_row(parent, _("默认AI服务商"),
                                                                                             _("选择默认使用的AI模型提供商。"),
                                                                                             provider_display_names)
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row(parent, _("为AI服务使用网络代理"),
                                                                            _("是否为连接AI模型API启用代理。"))

        providers_container_frame = ttk.Frame(parent)
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

            test_button_frame = ttk.Frame(card)
            test_button_frame.grid(row=card.grid_size()[1], column=1, sticky="e", padx=10, pady=(5, 10))
            # 修复：ttkb.Button 不支持直接的 font 参数
            test_button = ttkb.Button(test_button_frame, text=_("测试连接"), width=12,
                                        command=lambda p_k=p_key: self._gui_start_ai_connection_test(p_k),
                                        style='info.TButton')
            test_button.pack()

            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)
            setattr(self, f"ai_{safe_key}_model_selector", model_selector)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        create_section_title(parent, _("AI 提示词模板"))
        self.ai_translation_prompt_textbox = create_textbox_row(parent, _("翻译提示词"),
                                                                _("用于翻译任务的提示词模板。必须包含 {text} 占位符。"))
        self.ai_analysis_prompt_textbox = create_textbox_row(parent, _("分析提示词"),
                                                             _("用于分析任务的提示词模板。必须包含 {text} 占位符。"))

        create_section_title(parent, _("功能注释工具配置"))
        self.anno_db_root_dir_entry = create_entry_row(parent, _("数据库根目录"), _("存放注释数据库文件的目录。"))

    def _apply_config_values_to_editor(self):
        """
        将 self.current_config 的值填充到已创建的编辑器控件中。
        """
        if not self.current_config or not hasattr(self, 'downloader_sources_file_entry'):
            self.logger.debug("Config or editor widgets not ready for value population.", "DEBUG")
            return

        cfg = self.current_config

        def update_widget(widget, value, is_textbox=False):
            if widget and widget.winfo_exists():
                if is_textbox:
                    widget.configure(state="normal")
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", str(value) if value is not None else "")
                    widget.configure(state="disabled")
                else:
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value) if value is not None else "")

        if hasattr(cfg, 'log_level'):
            self.general_log_level_var.set(cfg.log_level)
        if hasattr(cfg, 'i18n_language'):
            display_name = self.LANG_CODE_TO_NAME.get(cfg.i18n_language, "简体中文")
            self.general_i18n_lang_var.set(display_name)
        if hasattr(cfg, 'proxies'):
            update_widget(self.proxy_http_entry, cfg.proxies.http)
            update_widget(self.proxy_https_entry, cfg.proxies.https)

        dl_cfg = cfg.downloader
        update_widget(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        update_widget(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(bool(cfg.downloader.force_download))
        update_widget(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        self.downloader_use_proxy_var.set(bool(dl_cfg.use_proxy_for_download))

        ai_cfg = cfg.ai_services
        default_display_name = self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name',
                                                                                               cfg.ai_services.default_provider)
        self.ai_default_provider_var.set(default_display_name)
        self.ai_use_proxy_var.set(bool(ai_cfg.use_proxy_for_ai))

        for p_key, p_cfg in ai_cfg.providers.items():
            safe_key = p_key.replace('-', '_')
            if hasattr(self, f"ai_{safe_key}_apikey_entry"):
                update_widget(getattr(self, f"ai_{safe_key}_apikey_entry"), p_cfg.api_key)

                model_selector = getattr(self, f"ai_{safe_key}_model_selector")
                _frame, entry, dropdown, dropdown_var, _button = model_selector
                update_widget(entry, p_cfg.model)
                dropdown_var.set(p_cfg.model)

                update_widget(getattr(self, f"ai_{safe_key}_baseurl_entry"), p_cfg.base_url)

        update_widget(self.ai_translation_prompt_textbox, cfg.ai_prompts.translation_prompt, is_textbox=True)
        update_widget(self.ai_analysis_prompt_textbox, cfg.ai_prompts.analysis_prompt, is_textbox=True)
        update_widget(self.anno_db_root_dir_entry, cfg.annotation_tool.database_root_dir)

        self._log_to_viewer(_("配置编辑器的值已从当前配置刷新。"), "DEBUG")

        self.ui_manager.update_button_states()

        self._log_to_viewer(_("UI已根据当前配置刷新。"))

        if self.current_config and hasattr(self.current_config, 'log_level'):
            self.reconfigure_logging(self.current_config.log_level)

    def _save_config_from_editor(self):
        """
        从静态UI控件中收集数据并保存配置。
        """
        if not self.current_config or not self.config_path:
            self.ui_manager.show_error_message(_("错误"), _("没有加载配置文件，无法保存。"))
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

            def get_model_value(selector_tuple):
                _frame, entry, dropdown, dropdown_var, _button = selector_tuple
                if dropdown.winfo_ismapped():
                    return dropdown_var.get()
                else:
                    return entry.get().strip()

            if hasattr(updated_config, 'log_level'):
                updated_config.log_level = self.general_log_level_var.get()

            if hasattr(updated_config, 'i18n_language'):
                code_to_save = self.LANG_NAME_TO_CODE.get(self.general_i18n_lang_var.get(), "zh-hans")
                updated_config.i18n_language = code_to_save

            if hasattr(updated_config, 'proxies'):
                updated_config.proxies.http = self.proxy_http_entry.get() or None
                updated_config.proxies.https = self.proxy_https_entry.get() or None

            dl_cfg = updated_config.downloader
            dl_cfg.genome_sources_file = self.downloader_sources_file_entry.get()
            dl_cfg.download_output_base_dir = self.downloader_output_dir_entry.get()
            dl_cfg.force_download = self.downloader_force_download_var.get()
            dl_cfg.max_workers = to_int(self.downloader_max_workers_entry.get(), 3)
            dl_cfg.use_proxy_for_download = self.downloader_use_proxy_var.get()

            ai_cfg = updated_config.ai_services

            selected_display_name = self.ai_default_provider_var.get()
            provider_key_to_save = ai_cfg.default_provider

            name_to_key_map = {v['name']: k for k, v in self.AI_PROVIDERS.items()}
            if selected_display_name in name_to_key_map:
                provider_key_to_save = name_to_key_map[selected_display_name]

            ai_cfg.default_provider = provider_key_to_save
            ai_cfg.use_proxy_for_ai = self.ai_use_proxy_var.get()

            for p_key in ai_cfg.providers:
                safe_key = p_key.replace('-', '_')
                if hasattr(self, f"ai_{safe_key}_apikey_entry"):
                    ai_cfg.providers[p_key].api_key = getattr(self, f"ai_{safe_key}_apikey_entry").get()
                    ai_cfg.providers[p_key].model = get_model_value(getattr(self, f"ai_{safe_key}_model_selector"))
                    if hasattr(self, f"ai_{safe_key}_baseurl_entry"):
                        ai_cfg.providers[p_key].base_url = getattr(self, f"ai_{safe_key}_baseurl_entry").get() or None

            prompt_cfg = updated_config.ai_prompts
            prompt_cfg.translation_prompt = self.ai_translation_prompt_textbox.get("1.0", tk.END).strip()
            prompt_cfg.analysis_prompt = self.ai_analysis_prompt_textbox.get("1.0", tk.END).strip()

            updated_config.annotation_tool.database_root_dir = self.anno_db_root_dir_entry.get()

            if save_config(updated_config, self.config_path):
                self.current_config = updated_config
                self.ui_manager.show_info_message(_("保存成功"), _("配置文件已更新。"))
                self.ui_manager.update_ui_from_config()
            else:
                self.ui_manager.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))

        except Exception as e:
            detailed_error = f"{_('在更新或保存配置时发生错误')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.ui_manager.show_error_message(_("保存错误"), detailed_error)

    def _create_home_frame(self, parent):
        """
        创建并返回主页框架。
        采用两列等宽的网格布局，使卡片能随窗口宽度动态调整，更美观。
        """
        # This will be the actual frame that gets gridded into main_content_frame
        home_page_frame = ttk.Frame(parent)
        home_page_frame.grid_rowconfigure(0, weight=1)
        home_page_frame.grid_columnconfigure(0, weight=1)

        # Create Canvas and Scrollbar INSIDE home_page_frame, and pack them
        canvas = tk.Canvas(home_page_frame, highlightthickness=0, background=self.style.lookup('TCanvas', 'background'))
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttkb.Scrollbar(home_page_frame, orient="vertical", command=canvas.yview, bootstyle="round")
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Create the inner scrollable frame
        scrollable_content_frame = ttk.Frame(canvas)
        canvas_window_id = canvas.create_window((0, 0), window=scrollable_content_frame, anchor="nw", width=home_page_frame.winfo_width())

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window_id, width=event.width)

        scrollable_content_frame.bind("<Configure>", _on_frame_configure)

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window_id, width=event.width)

        canvas.bind('<Configure>', _on_canvas_resize)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        scrollable_content_frame.grid_columnconfigure(0, weight=1)

        # Now, populate scrollable_content_frame with the actual home page content (cards, labels, etc.)
        top_info_frame = ttk.Frame(scrollable_content_frame)
        top_info_frame.grid(row=0, column=0, pady=(40, 20), padx=40, sticky="ew")
        top_info_frame.grid_columnconfigure(0, weight=1)

        title_label = ttk.Label(top_info_frame, text="", font=self.app.app_title_font)
        title_label.pack(pady=(0, 10))
        self.translatable_widgets[title_label] = self.title_text_key # Register for translation

        self.config_path_label = ttk.Label(top_info_frame,
                                              textvariable=self.config_path_display_var,
                                              wraplength=800,
                                              font=self.app.app_font,
                                              foreground=self.secondary_text_color)
        self.config_path_label.pack(pady=(10, 0))
        # self.config_path_display_var itself might contain translatable parts,
        # but the variable itself isn't a widget. Its content is updated dynamically.

        cards_frame = ttk.Frame(scrollable_content_frame)
        cards_frame.grid(row=1, column=0, pady=20, padx=20, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        config_card = ttk.Frame(cards_frame, relief="raised", borderwidth=1, bootstyle="primary")
        config_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)

        config_title = ttk.Label(config_card, text="", font=self.app.card_title_font)
        config_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[config_title] = "配置文件" # Register for translation

        # 修复：ttkb.Button 不支持直接的 font 参数，通过 style 预设。
        load_button = ttkb.Button(config_card, text="", command=self.event_handler.load_config_file,
                                  style='primary.TButton')
        load_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[load_button] = "加载配置文件..." # Register for translation

        # 修复：ttkb.Button 不支持直接的 font 参数，通过 style 预设。
        gen_button = ttkb.Button(config_card, text="", command=self.event_handler._generate_default_configs_gui,
                                   style='info.TButton')
        gen_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[gen_button] = "生成默认配置..." # Register for translation

        help_card = ttk.Frame(cards_frame, relief="raised", borderwidth=1, bootstyle="secondary")
        help_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)

        help_title = ttk.Label(help_card, text="", font=self.app.card_title_font)
        help_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.translatable_widgets[help_title] = "帮助与支持" # Register for translation

        # 修复：ttkb.Button 不支持直接的 font 参数，通过 style 预设。
        docs_button = ttkb.Button(help_card, text="", command=self.event_handler._open_online_help,
                                  style='primary.TButton')
        docs_button.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.translatable_widgets[docs_button] = "在线帮助文档" # Register for translation

        # 修复：ttkb.Button 不支持直接的 font 参数，通过 style 预设。
        about_button = ttkb.Button(help_card, text="", command=self.event_handler._show_about_window,
                                  style='info.TButton')
        about_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 20))
        self.translatable_widgets[about_button] = "关于本软件" # Register for translation

        return home_page_frame # Returns the top-level frame for the home page

    def _create_tools_frame(self, parent):
        """
        创建“数据工具”选项卡的主框架。
        :param parent:
        :return:
        """

        frame = ttk.Frame(parent)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ttk.Label(frame, text=_("数据工具"), font=self.app.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        self.tools_notebook = ttkb.Notebook(frame, bootstyle="info")
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
            tab_frame = ttk.Frame(self.tools_notebook)
            self.tools_notebook.add(tab_frame, text=tab_name)

            if TabClass := tab_class_map.get(key):
                self.tool_tab_instances[key] = TabClass(parent=tab_frame, app=self)
            else:
                self.logger.warning(f"No Tab class found for key '{key}'.", "WARNING")
        self.tools_notebook.select(self.tools_notebook.tabs()[0])

    def set_app_icon(self):
        try:
            if hasattr(sys, '_MEIPASS'):
                base_path = sys._MEIPASS
            else:
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
        page = ttk.Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        top_frame = ttk.Frame(page)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_frame.grid_columnconfigure(0, weight=1)

        warning_color = self.style.colors.danger
        ttk.Label(top_frame, text=_("!! 警告: 配置文件可能包含API Key等敏感信息，请勿轻易分享给他人。"),
                     font=self.app.app_font_bold, foreground=warning_color).grid(row=0, column=0, sticky="w", padx=5)

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.save_editor_button = ttkb.Button(top_frame, text=_("应用并保存配置"),
                                                command=self._save_config_from_editor,
                                                style='success.TButton')
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)

        # 修复：使用 style.lookup 获取 'TCanvas' 的背景色
        self.editor_canvas = tk.Canvas(page, highlightthickness=0, background=self.style.lookup('TCanvas', 'background'))
        self.editor_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        editor_scrollbar = ttkb.Scrollbar(page, orient="vertical", command=self.editor_canvas.yview, bootstyle="round")
        editor_scrollbar.grid(row=1, column=1, sticky="ns", pady=10)
        self.editor_canvas.configure(yscrollcommand=editor_scrollbar.set)

        self.editor_scroll_frame = ttk.Frame(self.editor_canvas)
        editor_window_id = self.editor_canvas.create_window((0, 0), window=self.editor_scroll_frame, anchor="nw")

        def _on_editor_frame_configure(event):
            self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all"))
            self.editor_canvas.itemconfig(editor_window_id, width=event.width)

        self.editor_scroll_frame.bind("<Configure>", _on_editor_frame_configure)

        def _on_editor_mousewheel(event):
            self.editor_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.editor_canvas.bind_all("<MouseWheel>", _on_editor_mousewheel)

        self.editor_scroll_frame.grid_columnconfigure(0, weight=1)

        self.editor_no_config_label = ttk.Label(page, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                   font=self.app.app_subtitle_font,
                                                   foreground=self.secondary_text_color)
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew", columnspan=2)

        self.bind('<Control-s>', lambda event: self._save_config_from_editor())
        self.bind('<Control-S>', lambda event: self._save_config_from_editor())
        self.editor_canvas.bind('<Control-s>', lambda event: self._save_config_from_editor())
        self.editor_canvas.bind('<Control-S>', lambda event: self._save_config_from_editor())

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
                self.ui_manager.show_error_message(_("内部错误"), f"{_('未知的服务商密钥:')} {provider_key}")
                return
        except AttributeError:
            self.ui_manager.show_error_message(_("UI错误"), _("配置编辑器UI尚未完全加载。"))
            return

        if not api_key or "YOUR_" in api_key:
            self.ui_manager.show_warning_message(_("缺少API Key"),
                                                 _("请先在编辑器中为 '{}' 填写有效的API Key。").format(provider_key))
            return

        proxies_to_use = None
        ai_tab = self.tool_tab_instances.get('ai_assistant')
        if ai_tab and hasattr(ai_tab, 'ai_proxy_var') and ai_tab.ai_proxy_var.get():
            http_proxy = self.proxy_http_entry.get().strip()
            https_proxy = self.proxy_https_entry.get().strip()
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

        self.cancel_model_fetch_event.clear()

        self.ui_manager._show_progress_dialog(
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
                self.message_queue.put(("hide_progress_dialog", None))

        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def _handle_editor_ui_update(self):
        """
        仅用数据更新已存在的配置编辑器UI，或切换其可见性。
        """
        if not self.editor_ui_built:
            self.logger.error("ERROR: _handle_editor_ui_update called before editor UI was built.")
            return

        if self.current_config:
            self.editor_canvas.grid()
            try:
                # 确保这里 grid_slaves[0] 存在，如果不存在说明滚动条未被创建或隐藏
                self.grid_slaves(row=1, column=1)[0].grid(row=1, column=1, sticky="ns", pady=10)
            except IndexError:
                pass # 如果滚动条不存在，则不做处理
            self.editor_no_config_label.grid_remove()
            self._apply_config_values_to_editor()
            self.save_editor_button.configure(state="normal")
        else:
            self.editor_canvas.grid_remove()
            try:
                self.grid_slaves(row=1, column=1)[0].grid_remove()
            except IndexError:
                pass
            self.editor_no_config_label.grid()
            self.save_editor_button.configure(state="disabled")

    def _setup_fonts(self):
        """设置全局字体"""
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        monospace_font_stack = ["Consolas", "Courier New", "monospace"]
        available_fonts = tkfont.families()

        selected_font = "sans-serif"
        for font_name in font_stack:
            if font_name in available_fonts:
                selected_font = font_name
                print(f"INFO: UI font has been set to: {selected_font}")
                break
        self.font_family = selected_font

        selected_mono_font = "monospace"
        for font_name in monospace_font_stack:
            if font_name in available_fonts:
                selected_mono_font = font_name
                print(f"INFO: Monospace UI font has been set to: {selected_mono_font}")
                break
        self.mono_font_family = selected_mono_font

        self.app_font = tkfont.Font(family=selected_font, size=14)
        self.app_font_italic = tkfont.Font(family=selected_font, size=14, slant="italic")
        self.app_font_bold = tkfont.Font(family=selected_font, size=15, weight="bold")
        self.app_subtitle_font = tkfont.Font(family=selected_font, size=16)
        self.app_title_font = tkfont.Font(family=selected_font, size=24, weight="bold")
        self.app_comment_font = tkfont.Font(family=selected_font, size=12)
        self.app_font_mono = tkfont.Font(family=selected_mono_font, size=12)
        self.card_title_font = tkfont.Font(family=selected_font, size=18, weight="bold")

        # 【重要新增】为 ttkbootstrap 按钮设置默认字体样式
        # ttkbootstrap 的按钮字体通过 Style 设置，而不是直接通过 font 参数
        # 这里定义了一个通用样式，以确保所有ttkbootstrap按钮使用app_font
        self.style.configure('TButton', font=self.app_font)
        self.style.configure('info.TButton', font=self.app_font) # 为带有 info 样式的按钮设置字体
        self.style.configure('success.TButton', font=self.app_font_bold) # 为成功按钮设置粗体
        self.style.configure('primary.TButton', font=self.app_font)
        self.style.configure('outline.TButton', font=self.app_font) # 为 outline 按钮设置字体
        self.style.configure('info-outline.TButton', font=self.app_font) # 为 info-outline 按钮设置字体
        # Checkbutton 的字体可以通过 TCheckbutton 样式控制
        self.style.configure('TCheckbutton', font=self.app_font)
        # OptionMenu 的内部是 TMenubutton，其字体可以通过 TMenubutton 样式控制
        self.style.configure('TMenubutton', font=self.app_font)
        self.style.configure('toolbutton', font=self.app_font) # For Radiobutton with toolbutton style

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
                    self.logger.warning(f"未知的消息类型: '{message_type}'") # Changed to self.logger.warning
        except queue.Empty:
            pass
        except Exception as e:
            self.logger.critical(f"在 check_queue_periodic 中发生未处理的异常: {e}", exc_info=True)
        self.after(100, self.check_queue_periodic)

    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        """【新增】任务结束时统一处理UI更新的辅助函数。"""
        self.ui_manager._finalize_task_ui(task_display_name, success, result_data)

    def reconfigure_logging(self, log_level_str: str):
        """
        智能地、强制地重新配置全局日志级别，包括所有处理器。
        """
        try:
            root_logger = logging.getLogger()
            new_level = logging.getLevelName(log_level_str.upper())

            if not isinstance(new_level, int):
                self.logger.warning(f"警告: 无效的日志级别 '{log_level_str}'")
                return

            current_level = root_logger.getEffectiveLevel()

            if current_level != new_level:
                root_logger.setLevel(new_level)

                for handler in root_logger.handlers:
                    handler.setLevel(new_level)

                self.logger.info(f"全局日志级别已更新为: {log_level_str}")

        except Exception as e:
            self.logger.error(f"配置日志级别时出错: {e}")

    def _browse_directory(self, entry_widget: ttk.Entry):
        """打开目录选择对话框并填充到输入框。"""
        directory = filedialog.askdirectory(title=_("选择目录"))
        if directory and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()
    app.mainloop()