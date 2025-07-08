# 文件路径: ui/gui_app.py

import logging
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from queue import Queue
from tkinter import font as tkfont
from typing import Optional, Any, Dict, Callable

import ttkbootstrap as ttkb

from cotton_toolkit.config.loader import save_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.data_download_tab import DataDownloadTab
from ui.tabs.annotation_tab import AnnotationTab
from ui.tabs.enrichment_tab import EnrichmentTab
from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
from ui.tabs.gff_query_tab import GFFQueryTab
from ui.tabs.homology_tab import HomologyTab
from ui.tabs.locus_conversion_tab import LocusConversionTab
from ui.tabs.xlsx_converter_tab import XlsxConverterTab
from ui.ui_manager import UIManager

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class CottonToolkitApp(ttkb.Window):
    # --- 类别常数 (使用英文作为 Key) ---
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    AI_PROVIDERS = {
        "google": {"name": "Google Gemini"},
        "openai": {"name": "OpenAI"},
        "deepseek": {"name": "DeepSeek"},
        "qwen": {"name": "Qwen"},
        "siliconflow": {"name": "SiliconFlow"},
        "grok": {"name": "Grok"},
        "openai_compatible": {"name": "Generic OpenAI-Compatible Interface"}
    }
    TOOL_TAB_ORDER = ["download", "annotation", "enrichment", "xlsx_to_csv", "genome_identifier", "homology",
                      "locus_conversion", "gff_query", "ai_assistant"]
    TAB_TITLE_KEYS = {
        "download": "Data Download", "annotation": "Functional Annotation", "enrichment": "Enrichment Analysis",
        "xlsx_to_csv": "XLSX to CSV", "genome_identifier": "Genome Identifier", "homology": "Homology Conversion",
        "locus_conversion": "Locus Conversion", "gff_query": "GFF Query", "ai_assistant": "AI Assistant",
    }

    def __init__(self):
        super().__init__(themename="flatly")
        self.logger = logging.getLogger(__name__)

        self.title_text_key = "Friendly Cotton Genomes Toolkit - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1100x750")
        self.minsize(900, 700)

        self._setup_fonts()
        self.placeholder_color = (self.style.colors.secondary, self.style.colors.secondary)
        self.default_text_color = self.style.lookup('TLabel', 'foreground')
        self.secondary_text_color = self.style.colors.info
        self.placeholders = {}

        # --- 储存需要翻译的 UI 元件 ---
        self.home_widgets: Dict[str, Any] = {}
        self.editor_widgets: Dict[str, Any] = {}
        self.translatable_widgets = {}

        # --- 【修复】补全所有应用状态变量的初始化 ---
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data = {}
        self.log_queue = Queue()
        self.message_queue = Queue()
        self.active_task_name: Optional[str] = None
        self.cancel_current_task_event = threading.Event()
        self.ui_settings = {}
        self.tool_tab_instances = {}
        self.latest_log_message_var = tk.StringVar(value="")
        self.editor_canvas: Optional[tk.Canvas] = None
        self.editor_ui_built = False
        self.log_viewer_visible = False  # <--- 修正 AttributeError 的关键

        self.config_path_display_var = tk.StringVar(value=_("No Configuration Loaded"))
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()

        self.ui_manager = UIManager(self)
        self.event_handler = EventHandler(self)

        self._create_image_assets()
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        self.ui_manager.setup_initial_ui()
        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)
        self.set_app_icon()

    def retranslate_ui(self, translator: Callable[[str], str]):
        """【新增】当语言切换时，由 UIManager 调用此方法来更新非 Tab 页的 UI 文本。"""
        self.title(translator(self.title_text_key))

        # 刷新导航栏按钮和标签
        if hasattr(self, 'home_button'): self.home_button.configure(text=translator("Home"))
        if hasattr(self, 'editor_button'): self.editor_button.configure(text=translator("Config Editor"))
        if hasattr(self, 'tools_button'): self.tools_button.configure(text=translator("Data Tools"))
        if hasattr(self, 'language_label'): self.language_label.configure(text=translator("Language"))
        if hasattr(self, 'appearance_mode_label'): self.appearance_mode_label.configure(
            text=translator("Appearance Mode"))

        # 呼叫各个页面的刷新方法
        self.retranslate_home_ui(translator)
        self.retranslate_editor_ui(translator)

    def _create_home_frame(self, parent):
        page = ttkb.Frame(parent);
        page.grid_columnconfigure(0, weight=1)

        # 储存主页的元件
        title_label = ttkb.Label(page, text=_(self.title_text_key), font=self.app_title_font);
        title_label.pack(pady=(40, 10))
        self.home_widgets['title_label'] = title_label

        config_display_label = ttkb.Label(page, textvariable=self.config_path_display_var, font=self.app_font,
                                          bootstyle="secondary");
        config_display_label.pack(pady=(10, 20))

        cards_frame = ttkb.Frame(page);
        cards_frame.pack(pady=20, padx=20, fill="x", expand=False);
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        def create_card(p, col, title_key, buttons):
            card = ttkb.LabelFrame(p, text=_(title_key), bootstyle="primary");
            card.grid(row=0, column=col, padx=10, pady=10, sticky="nsew");
            card.grid_columnconfigure(0, weight=1)
            self.home_widgets[f"card_{title_key}"] = card
            for i, (text_key, cmd, style) in enumerate(buttons):
                btn = ttkb.Button(card, text=_(text_key), command=cmd, bootstyle=style);
                btn.grid(row=i, column=0, sticky="ew", padx=20, pady=10);
                self.home_widgets[f"button_{text_key}"] = btn

        create_card(cards_frame, 0, "Configuration File",
                    [("Load Configuration...", self.event_handler.load_config_file, "outline"),
                     ("Generate Default...", self.event_handler._generate_default_configs_gui, "info-outline")])
        create_card(cards_frame, 1, "Help & Support", [("Online Help", self.event_handler._open_online_help, "outline"),
                                                       ("About This Software", self.event_handler._show_about_window,
                                                        "info-outline")])
        return page

    def retranslate_home_ui(self, translator: Callable[[str], str]):
        """【新增】更新主页的 UI 文本"""
        if self.home_widgets.get('title_label'): self.home_widgets['title_label'].configure(
            text=translator(self.title_text_key))
        if self.home_widgets.get('card_Configuration File'): self.home_widgets['card_Configuration File'].configure(
            text=translator("Configuration File"))
        if self.home_widgets.get('button_Load Configuration...'): self.home_widgets[
            'button_Load Configuration...'].configure(text=translator("Load Configuration..."))
        if self.home_widgets.get('button_Generate Default...'): self.home_widgets[
            'button_Generate Default...'].configure(text=translator("Generate Default..."))
        if self.home_widgets.get('card_Help & Support'): self.home_widgets['card_Help & Support'].configure(
            text=translator("Help & Support"))
        if self.home_widgets.get('button_Online Help'): self.home_widgets['button_Online Help'].configure(
            text=translator("Online Help"))
        if self.home_widgets.get('button_About This Software'): self.home_widgets[
            'button_About This Software'].configure(text=translator("About This Software"))

        if self.config_path:
            self.config_path_display_var.set(
                translator("Current Config: {}").format(os.path.basename(self.config_path)))
        else:
            self.config_path_display_var.set(translator("No Configuration Loaded"))

    def _create_editor_widgets(self, parent):
        """创建配置编辑器的所有 UI 元件，并将需要翻译的元件存入字典。"""
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        def get_row():
            nonlocal row_counter; r = row_counter; row_counter += 1; return r

        def section(title_key):
            label = ttkb.Label(parent, text=_(title_key), font=self.app_subtitle_font, bootstyle="primary");
            label.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
            self.editor_widgets[f"section_{title_key}"] = label

        def create_entry_row(label_key, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
            container.grid_columnconfigure(1, weight=1)
            label = ttkb.Label(container, text=_(label_key));
            label.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            self.editor_widgets[f"entry_label_{label_key}"] = label
            widget = ttkb.Entry(container);
            widget.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
            if tooltip_key:
                tooltip_label = ttkb.Label(container, text=_(tooltip_key), font=self.app_comment_font,
                                           bootstyle="secondary");
                tooltip_label.grid(row=1, column=1, sticky="w", padx=5)
                self.editor_widgets[f"entry_tooltip_{label_key}"] = tooltip_label
            return widget

        def create_switch_row(label_key, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            label = ttkb.Label(container, text=_(label_key));
            label.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            self.editor_widgets[f"switch_label_{label_key}"] = label
            var = tk.BooleanVar();
            widget = ttkb.Checkbutton(container, variable=var, bootstyle="round-toggle");
            widget.grid(row=0, column=1, sticky="w", padx=5)
            if tooltip_key:
                tooltip_label = ttkb.Label(container, text=_(tooltip_key), font=self.app_comment_font,
                                           bootstyle="secondary");
                tooltip_label.grid(row=1, column=1, sticky="w", padx=5)
                self.editor_widgets[f"switch_tooltip_{label_key}"] = tooltip_label
            return widget, var

        def create_option_menu_row(label_key, var, default, values, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            label = ttkb.Label(container, text=_(label_key));
            label.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            self.editor_widgets[f"option_label_{label_key}"] = label
            var.set(default);
            widget = ttkb.OptionMenu(container, var, default, *values, bootstyle='info-outline');
            widget.grid(row=0, column=1, sticky="ew", padx=5)
            if tooltip_key:
                tooltip_label = ttkb.Label(container, text=_(tooltip_key), font=self.app_comment_font,
                                           bootstyle="secondary");
                tooltip_label.grid(row=1, column=1, sticky="w", padx=5)
                self.editor_widgets[f"option_tooltip_{label_key}"] = tooltip_label
            return widget

        # --- 使用英文 Key 来建立元件 ---
        section("General Settings")
        self.general_log_level_var = tk.StringVar()
        self.general_log_level_menu = create_option_menu_row("Log Level", self.general_log_level_var, "INFO",
                                                             ["DEBUG", "INFO", "WARNING", "ERROR"],
                                                             "Set the verbosity level of the application's logs.")
        self.proxy_http_entry = create_entry_row("HTTP Proxy", "e.g., http://127.0.0.1:7890")
        self.proxy_https_entry = create_entry_row("HTTPS Proxy", "e.g., https://127.0.0.1:7890")
        proxy_button_frame = ttkb.Frame(parent);
        proxy_button_frame.grid(row=get_row(), column=0, sticky="e", padx=5, pady=5)
        self.test_proxy_button = ttkb.Button(proxy_button_frame, text=_("Test Proxy Connection"),
                                             command=self.event_handler.test_proxy_connection,
                                             bootstyle="primary-outline");
        self.test_proxy_button.pack()
        self.editor_widgets["test_proxy_button"] = self.test_proxy_button

        section("Data Downloader Configuration")
        self.downloader_sources_file_entry = create_entry_row("Genome Sources File",
                                                              "YAML file that defines the genome download links.")
        self.downloader_output_dir_entry = create_entry_row("Download Output Root Directory",
                                                            "Base directory where all downloaded files are stored.")
        self.downloader_force_download_switch, self.downloader_force_download_var = create_switch_row(
            "Force Re-download", "Whether to overwrite if the file already exists.")
        self.downloader_max_workers_entry = create_entry_row("Maximum Download Threads",
                                                             "Maximum number of threads to use for multi-threaded downloads.")
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = create_switch_row("Use Proxy for Downloads",
                                                                                            "Whether to enable proxy for data downloads.")

        section("AI Service Configuration")
        self.ai_default_provider_var = tk.StringVar()
        provider_names = [_(p['name']) for p in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu = create_option_menu_row("Default AI Provider", self.ai_default_provider_var,
                                                               "Google Gemini", provider_names,
                                                               "Select the default AI model provider to use.")
        self.batch_ai_max_workers_entry = create_entry_row("Maximum Parallel AI Tasks",
                                                           "The maximum number of parallel processes for AI tasks. It is recommended to set this based on CPU cores and network conditions.")
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row("Use Proxy for AI Services",
                                                                            "Whether to enable proxy for connecting to the AI model API.")

        for p_key, p_info in self.AI_PROVIDERS.items():
            card = ttkb.LabelFrame(parent, text=_(p_info['name']), bootstyle="secondary");
            card.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
            card.grid_columnconfigure(1, weight=1)
            self.editor_widgets[f"provider_card_{p_key}"] = card
            safe_key = p_key.replace('-', '_')
            api_key_label = ttkb.Label(card, text="API Key");
            api_key_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)
            apikey_entry = ttkb.Entry(card);
            apikey_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5);
            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)
            model_label = ttkb.Label(card, text="Model");
            model_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            model_frame = ttkb.Frame(card);
            model_frame.grid(row=1, column=1, sticky="ew", pady=5, padx=5);
            model_frame.grid_columnconfigure(0, weight=1)
            model_var = tk.StringVar(value=_("Click refresh to get the list"));
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, _("Click to refresh..."), bootstyle="info");
            model_dropdown.configure(state="disabled");
            model_dropdown.grid(row=0, column=0, sticky="ew")
            button_frame = ttkb.Frame(model_frame);
            button_frame.grid(row=0, column=1, padx=(10, 0))
            refresh_button = ttkb.Button(button_frame, text=_("Refresh"), width=8,
                                         command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                          use_proxy=False),
                                         bootstyle='outline');
            refresh_button.pack(side="left")
            proxy_refresh_button = ttkb.Button(button_frame, text=_("Refresh with Proxy"), width=15,
                                               command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                                use_proxy=True),
                                               bootstyle='info-outline');
            proxy_refresh_button.pack(side="left", padx=(5, 0))
            setattr(self, f"ai_{safe_key}_model_selector", (model_dropdown, model_var));
            self.editor_widgets[f"refresh_button_{p_key}"] = refresh_button;
            self.editor_widgets[f"proxy_refresh_button_{p_key}"] = proxy_refresh_button
            baseurl_label = ttkb.Label(card, text="Base URL");
            baseurl_label.grid(row=2, column=0, sticky="w", padx=10, pady=5)
            baseurl_entry = ttkb.Entry(card);
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5);
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)
            self.editor_widgets[f"apikey_label_{p_key}"] = api_key_label;
            self.editor_widgets[f"model_label_{p_key}"] = model_label;
            self.editor_widgets[f"baseurl_label_{p_key}"] = baseurl_label

        section("AI Prompt Templates")
        f_trans = ttkb.Frame(parent);
        f_trans.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_trans.grid_columnconfigure(1, weight=1)
        trans_label = ttkb.Label(f_trans, text=_("Translation Prompt"));
        trans_label.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.editor_widgets["translation_prompt_label"] = trans_label
        bg_t, fg_t = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        self.ai_translation_prompt_textbox = tk.Text(f_trans, height=7, font=self.app_font_mono, wrap="word",
                                                     relief="flat", background=bg_t, foreground=fg_t,
                                                     insertbackground=fg_t);
        self.ai_translation_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)
        f_ana = ttkb.Frame(parent);
        f_ana.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_ana.grid_columnconfigure(1, weight=1)
        ana_label = ttkb.Label(f_ana, text=_("Analysis Prompt"));
        ana_label.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.editor_widgets["analysis_prompt_label"] = ana_label
        self.ai_analysis_prompt_textbox = tk.Text(f_ana, height=7, font=self.app_font_mono, wrap="word", relief="flat",
                                                  background=bg_t, foreground=fg_t, insertbackground=fg_t);
        self.ai_analysis_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

    def retranslate_editor_ui(self, translator: Callable[[str], str]):
        """【新增】专门负责更新配置编辑器页面的 UI 文本。"""
        # 定义所有需要翻译的元件和它们的英文 Key
        translation_map = {
            "section_General Settings": "通用设置", "entry_label_Log Level": "日志级别",
            "option_tooltip_Set the verbosity level of the application's logs.": "设置应用程序的日志详细程度。",
            "entry_label_HTTP Proxy": "HTTP代理",
            "entry_tooltip_e.g., http://127.0.0.1:7890": "例如: http://127.0.0.1:7890",
            "entry_label_HTTPS Proxy": "HTTPS代理",
            "entry_tooltip_e.g., https://127.0.0.1:7890": "例如: https://127.0.0.1:7890",
            "test_proxy_button": "测试代理连接", "section_Data Downloader Configuration": "数据下载器配置",
            "entry_label_Genome Sources File": "基因组源文件",
            "entry_tooltip_YAML file that defines the genome download links.": "定义基因组下载链接的YAML文件。",
            "entry_label_Download Output Root Directory": "下载输出根目录",
            "entry_tooltip_Base directory where all downloaded files are stored.": "所有下载文件存放的基准目录。",
            "switch_label_Force Re-download": "强制重新下载",
            "switch_tooltip_Whether to overwrite if the file already exists.": "如果文件已存在，是否覆盖。",
            "entry_label_Maximum Download Threads": "最大下载线程数",
            "entry_tooltip_Maximum number of threads to use for multi-threaded downloads.": "多线程下载时使用的最大线程数。",
            "switch_label_Use Proxy for Downloads": "为下载使用代理",
            "switch_tooltip_Whether to enable proxy for data downloads.": "是否为数据下载启用代理。",
            "section_AI Service Configuration": "AI 服务配置", "option_label_Default AI Provider": "默认AI服务商",
            "option_tooltip_Select the default AI model provider to use.": "选择默认使用的AI模型提供商。",
            "entry_label_Maximum Parallel AI Tasks": "最大并行AI任务数",
            "entry_tooltip_The maximum number of parallel processes for AI tasks. It is recommended to set this based on CPU cores and network conditions.": "执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。",
            "switch_label_Use Proxy for AI Services": "为AI服务使用代理",
            "switch_tooltip_Whether to enable proxy for connecting to the AI model API.": "是否为连接AI模型API启用代理。",
            "section_AI Prompt Templates": "AI 提示词模板", "translation_prompt_label": "翻译提示词",
            "analysis_prompt_label": "分析提示词",
            "warning_label": "!! 警告: 配置文件可能包含敏感信息，请勿轻易分享。", "save_button": "应用并保存",
            "no_config_label": "请先从“主页”加载或生成一个配置文件。"
        }
        for p_key, p_info in self.AI_PROVIDERS.items():
            translation_map[f"provider_card_{p_key}"] = p_info['name']
            translation_map[f"refresh_button_{p_key}"] = "刷新"
            translation_map[f"proxy_refresh_button_{p_key}"] = "代理刷新"

        for widget_key, text_key in translation_map.items():
            if widget := self.editor_widgets.get(widget_key):
                if widget.winfo_exists(): widget.configure(text=translator(text_key))

        provider_names = [translator(p['name']) for p in self.AI_PROVIDERS.values()]
        menu = self.ai_default_provider_menu['menu'];
        menu.delete(0, 'end')
        for name in provider_names: menu.add_command(label=name, command=tk._setit(self.ai_default_provider_var, name))
        if self.current_config:
            current_key = self.current_config.ai_services.default_provider
            current_display_name = translator(self.AI_PROVIDERS.get(current_key, {}).get('name', ''))
            self.ai_default_provider_var.set(current_display_name)

    def _populate_tools_notebook(self):
        self.tool_tab_instances.clear()
        tab_map = {
            "download": DataDownloadTab, "xlsx_to_csv": XlsxConverterTab, "genome_identifier": GenomeIdentifierTab,
            "homology": HomologyTab, "locus_conversion": LocusConversionTab, "gff_query": GFFQueryTab,
            "ai_assistant": AIAssistantTab, "annotation": AnnotationTab, "enrichment": EnrichmentTab
        }
        for key in self.TOOL_TAB_ORDER:
            if TabClass := tab_map.get(key):
                tab_frame = ttkb.Frame(self.tools_notebook)
                self.tools_notebook.add(tab_frame, text=_(self.TAB_TITLE_KEYS[key]))
                self.tool_tab_instances[key] = TabClass(parent=tab_frame, app=self)

        # 【关键】将 App 自己也加入，让 UIManager 可以统一呼叫它的刷新方法
        self.tool_tab_instances["app_main"] = self

        if self.tools_notebook.tabs(): self.tools_notebook.select(0)

    def _create_image_assets(self):
        self.logo_image_path = self._get_image_resource_path("logo.png")
        self.home_icon_path = self._get_image_resource_path("home.png")
        self.tools_icon_path = self._get_image_resource_path("tools.png")
        self.settings_icon_path = self._get_image_resource_path("settings.png")

    def _get_image_resource_path(self, file_name):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(__file__)
            image_path = os.path.join(base_path, "assets", file_name)
            if os.path.exists(image_path): return image_path
            self.logger.warning(_("图片资源未找到: '{}'").format(image_path))
        except Exception as e:
            self.logger.error(_("获取图片资源 '{}' 路径时发生错误: {}").format(file_name, e))
        return None

    def _apply_config_values_to_editor(self):
        if not self.current_config or not self.editor_ui_built: return
        cfg = self.current_config

        def set_val(widget, value):
            if not widget: return
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END); widget.insert("1.0", str(value or ""))
            elif isinstance(widget, ttkb.Entry):
                widget.delete(0, tk.END); widget.insert(0, str(value or ""))

        self.general_log_level_var.set(cfg.log_level)
        set_val(self.proxy_http_entry, cfg.proxies.http)
        set_val(self.proxy_https_entry, cfg.proxies.https)
        set_val(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        set_val(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(cfg.downloader.force_download)
        set_val(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        self.downloader_use_proxy_var.set(cfg.downloader.use_proxy_for_download)
        set_val(self.batch_ai_max_workers_entry, cfg.batch_ai_processor.max_workers)
        provider_name = _(self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name', ''))
        self.ai_default_provider_var.set(provider_name)
        self.ai_use_proxy_var.set(cfg.ai_services.use_proxy_for_ai)
        for p_key, p_cfg in cfg.ai_services.providers.items():
            safe_key = p_key.replace('-', '_')
            if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry", None): apikey_widget.delete(0,
                                                                                                         tk.END); apikey_widget.insert(
                0, p_cfg.api_key or "")
            if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry", None): baseurl_widget.delete(0,
                                                                                                            tk.END); baseurl_widget.insert(
                0, p_cfg.base_url or "")
            if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                _dropdown, var = model_selector
                var.set(p_cfg.model or "")
        set_val(self.ai_translation_prompt_textbox, _(cfg.ai_prompts.translation_prompt))
        set_val(self.ai_analysis_prompt_textbox, _(cfg.ai_prompts.analysis_prompt))
        self.logger.info(_("配置已应用到编辑器UI。"))

    def _save_config_from_editor(self):
        if not self.current_config or not self.config_path: self.ui_manager.show_error_message(_("错误"),
                                                                                               _("没有加载配置文件，无法保存。")); return
        try:
            cfg = self.current_config
            cfg.log_level = self.general_log_level_var.get()
            cfg.proxies.http = self.proxy_http_entry.get() or None;
            cfg.proxies.https = self.proxy_https_entry.get() or None
            cfg.downloader.genome_sources_file = self.downloader_sources_file_entry.get()
            cfg.downloader.download_output_base_dir = self.downloader_output_dir_entry.get()
            cfg.downloader.force_download = self.downloader_force_download_var.get()
            cfg.downloader.max_workers = int(self.downloader_max_workers_entry.get() or 3)
            cfg.downloader.use_proxy_for_download = self.downloader_use_proxy_var.get()
            try:
                max_workers_val = int(self.batch_ai_max_workers_entry.get());
                cfg.batch_ai_processor.max_workers = max_workers_val if max_workers_val > 0 else 4
            except (ValueError, TypeError):
                cfg.batch_ai_processor.max_workers = 4; self.logger.warning(
                    _("无效的最大工作线程数值，已重置为默认值 4。"))
            cfg.ai_services.default_provider = next(
                (k for k, v in self.AI_PROVIDERS.items() if _(v['name']) == self.ai_default_provider_var.get()),
                'google')
            cfg.ai_services.use_proxy_for_ai = self.ai_use_proxy_var.get()
            for p_key, p_cfg in cfg.ai_services.providers.items():
                safe_key = p_key.replace('-', '_')
                if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry",
                                            None): p_cfg.api_key = apikey_widget.get()
                if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry",
                                             None): p_cfg.base_url = baseurl_widget.get() or None
                if model_selector := getattr(self, f"ai_{safe_key}_model_selector",
                                             None): _dropdown, var = model_selector; p_cfg.model = var.get()
            cfg.ai_prompts.translation_prompt = self.ai_translation_prompt_textbox.get("1.0", tk.END).strip()
            cfg.ai_prompts.analysis_prompt = self.ai_analysis_prompt_textbox.get("1.0", tk.END).strip()
            if save_config(cfg, self.config_path):
                self.ui_manager.show_info_message(_("保存成功"),
                                                  _("配置文件已更新。")); self.ui_manager.update_ui_from_config()
            else:
                self.ui_manager.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))
        except Exception as e:
            self.ui_manager.show_error_message(_("保存错误"),
                                               _("保存配置时发生错误:\n{}").format(traceback.format_exc()))

    def _create_tools_frame(self, parent):
        frame = ttkb.Frame(parent);
        frame.grid_columnconfigure(0, weight=1);
        frame.grid_rowconfigure(0, weight=1)
        self.tools_notebook = ttkb.Notebook(frame, bootstyle="info");
        self.tools_notebook.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        return frame

    def set_app_icon(self):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path): self.iconbitmap(icon_path)
        except Exception as e:
            self.logger.warning(_("加载主窗口图标失败: {}。").format(e))

    def _create_editor_frame(self, parent):
        page = ttkb.Frame(parent);
        page.grid_columnconfigure(0, weight=1);
        page.grid_rowconfigure(1, weight=1)
        top_frame = ttkb.Frame(page);
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0));
        top_frame.grid_columnconfigure(0, weight=1)
        warning_label = ttkb.Label(top_frame, text=_("!! 警告: 配置文件可能包含敏感信息，请勿轻易分享。"),
                                   font=self.app_font_bold, bootstyle="danger");
        warning_label.grid(row=0, column=0, sticky="w", padx=5)
        self.editor_widgets["warning_label"] = warning_label
        self.save_editor_button = ttkb.Button(top_frame, text=_("应用并保存"), command=self._save_config_from_editor,
                                              bootstyle='success');
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)
        self.editor_widgets["save_button"] = self.save_editor_button
        self.editor_canvas = tk.Canvas(page, highlightthickness=0, bd=0,
                                       background=self.style.lookup('TFrame', 'background'));
        self.editor_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        scrollbar = ttkb.Scrollbar(page, orient="vertical", command=self.editor_canvas.yview, bootstyle="round");
        scrollbar.grid(row=1, column=1, sticky="ns", pady=10)
        self.editor_canvas.configure(yscrollcommand=scrollbar.set)
        self.editor_scroll_frame = ttkb.Frame(self.editor_canvas);
        window_id = self.editor_canvas.create_window((0, 0), window=self.editor_scroll_frame, anchor="nw")

        def on_frame_configure(event):
            self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all")); self.editor_canvas.itemconfig(
                window_id, width=self.editor_canvas.winfo_width())

        def on_canvas_resize(event):
            self.editor_canvas.itemconfig(window_id, width=event.width); self.editor_canvas.configure(
                scrollregion=self.editor_canvas.bbox("all"))

        self.editor_scroll_frame.bind("<Configure>", on_frame_configure);
        self.editor_canvas.bind("<Configure>", on_canvas_resize)

        def _on_mousewheel(event):
            if self.editor_canvas.winfo_exists() and (event.widget == self.editor_canvas or (
                    self.editor_scroll_frame.winfo_exists() and self.editor_scroll_frame.winfo_containing(event.x_root,
                                                                                                          event.y_root) == self.editor_scroll_frame)):
                if event.num == 5 or event.delta == -120: self.editor_canvas.yview_scroll(1, "units")
                if event.num == 4 or event.delta == 120: self.editor_canvas.yview_scroll(-1, "units")
                return "break"

        self.editor_canvas.bind("<MouseWheel>", _on_mousewheel);
        self.editor_canvas.bind("<Button-4>", _on_mousewheel);
        self.editor_canvas.bind("<Button-5>", _on_mousewheel)
        self.editor_scroll_frame.bind("<MouseWheel>", _on_mousewheel);
        self.editor_scroll_frame.bind("<Button-4>", _on_mousewheel);
        self.editor_scroll_frame.bind("<Button-5>", _on_mousewheel)
        self.editor_no_config_label = ttkb.Label(page, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                 font=self.app_subtitle_font, bootstyle="secondary");
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew", columnspan=2)
        self.editor_widgets["no_config_label"] = self.editor_no_config_label
        return page

    def _handle_editor_ui_update(self):
        if not self.editor_ui_built: return
        has_config = bool(self.current_config)
        if self.editor_canvas and self.editor_canvas.winfo_exists():
            scrollbar = self.editor_canvas.master.grid_slaves(row=1, column=1)[0]
            if has_config:
                self.editor_canvas.grid(); scrollbar.grid(); self.editor_no_config_label.grid_remove(); self._apply_config_values_to_editor()
            else:
                self.editor_canvas.grid_remove(); scrollbar.grid_remove(); self.editor_no_config_label.grid()
        if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(
            state="normal" if has_config else "disabled")

    def _setup_fonts(self):
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "sans-serif"];
        mono_stack = ["Consolas", "Courier New", "monospace"]
        self.font_family = next((f for f in font_stack if f in tkfont.families()), "sans-serif");
        self.mono_font_family = next((f for f in mono_stack if f in tkfont.families()), "monospace")
        self.logger.info(_("UI font set to: {}, Monospace font to: {}").format(self.font_family, self.mono_font_family))
        self.app_font = tkfont.Font(family=self.font_family, size=12);
        self.app_font_italic = tkfont.Font(family=self.font_family, size=12, slant="italic")
        self.app_font_bold = tkfont.Font(family=self.font_family, size=13, weight="bold");
        self.app_subtitle_font = tkfont.Font(family=self.font_family, size=16, weight="bold")
        self.app_title_font = tkfont.Font(family=self.font_family, size=24, weight="bold");
        self.app_comment_font = tkfont.Font(family=self.font_family, size=11);
        self.app_font_mono = tkfont.Font(family=self.mono_font_family, size=12)
        for style_name in ['TButton', 'TCheckbutton', 'TMenubutton', 'TLabel', 'TEntry', 'Toolbutton',
                           'Labelframe.TLabel']: self.style.configure(style_name, font=self.app_font)
        self.style.configure('success.TButton', font=self.app_font_bold);
        self.style.configure('info-outline.TButton', font=self.app_font);
        self.style.configure('outline.TButton', font=self.app_font)

    def _log_to_viewer(self, message, level="INFO"):
        if logging.getLogger().getEffectiveLevel() <= logging.getLevelName(level.upper()): self.log_queue.put(
            (message, level))

    def check_queue_periodic(self):
        try:
            while not self.log_queue.empty(): self.ui_manager.display_log_message_in_ui(*self.log_queue.get_nowait())
        except queue.Empty:
            pass
        try:
            while not self.message_queue.empty():
                msg_type, data = self.message_queue.get_nowait()
                if handler := self.event_handler.message_handlers.get(msg_type): handler(
                    data) if data is not None else handler()
        except queue.Empty:
            pass
        except Exception as e:
            self.logger.critical(_("处理消息队列时出错: {}").format(e), exc_info=True)
        self.after(100, self.check_queue_periodic)

    def reconfigure_logging(self, log_level_str: str):
        try:
            if isinstance(new_level := logging.getLevelName(log_level_str.upper()), int):
                if (root := logging.getLogger()).getEffectiveLevel() != new_level: root.setLevel(new_level); [
                    h.setLevel(new_level) for h in root.handlers]; self.logger.info(
                    _("全局日志级别已更新为: {}").format(log_level_str))
        except Exception as e:
            self.logger.error(_("配置日志级别时出错: {}").format(e))


if __name__ == "__main__":
    app = CottonToolkitApp()
    app.mainloop()