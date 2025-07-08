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
from typing import Optional, Dict, Any, Callable  # 确保导入 Callable

import ttkbootstrap as ttkb

from cotton_toolkit.config.loader import save_config, load_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.utils.localization import setup_localization
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.ui_manager import UIManager


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    # 【修改】AI_PROVIDERS 的值也需要通过翻译函数
    @property
    def AI_PROVIDERS(self):
        return {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                "openai_compatible": {"name": self._("通用OpenAI兼容接口")}}

    TOOL_TAB_ORDER = [
        "download",
        "annotation",
        "enrichment",
        "xlsx_to_csv",
        "genome_identifier",
        "homology",
        "locus_conversion",
        "gff_query",
        "ai_assistant"
    ]
    TAB_TITLE_KEYS = {
        "download": "数据下载",
        "annotation": "功能注释",
        "enrichment": "富集分析与绘图",
        "xlsx_to_csv": "XLSX转CSV",
        "genome_identifier": "基因组鉴定",
        "homology": "同源转换",
        "locus_conversion": "位点转换",
        "gff_query": "GFF查询",
        "ai_assistant": "AI助手",
    }

    # 【修改】构造函数接收 translator
    def __init__(self, translator: Callable[[str], str]):
        super().__init__(themename="flatly")
        # 【修改】将 translator 保存为实例属性，后续都用 self._
        self._ = translator
        self.logger = logging.getLogger(__name__)

        self.title_text_key = "Friendly Cotton Genomes Toolkit - FCGT"
        # 【修改】使用 self._ 进行翻译
        self.title(self._(self.title_text_key))
        self.geometry("1200x750")
        self.minsize(1200, 600)

        self._setup_fonts()
        self.placeholder_color = (self.style.colors.secondary, self.style.colors.secondary)
        self.default_text_color = self.style.lookup('TLabel', 'foreground')
        self.secondary_text_color = self.style.colors.info

        self.placeholders = {
            "homology_genes": "粘贴基因ID，每行一个...",
            "gff_genes": "粘贴基因ID，每行一个...",
            "gff_region": "例如: A01:1-100000",
            "genes_input": "在此处粘贴要注释的基因ID，每行一个。",
            "enrichment_genes_input": "在此处粘贴用于富集分析的基因ID，每行一个。\n如果包含Log2FC，格式为：基因ID\tLog2FC\n（注意：使用制表符分隔，从Excel直接复制的列即为制表符分隔）。",
            "custom_prompt": "在此处输入您的自定义提示词模板，必须包含 {text} 占位符...",
            "default_prompt_empty": "Default prompt is empty, please set it in the configuration editor."
        }

        self.home_widgets: Dict[str, Any] = {}
        self.editor_widgets: Dict[str, Any] = {}
        self.translatable_widgets = {}

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
        self.log_viewer_visible = False

        self.config_path_display_var = tk.StringVar()
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()

        # 【修改】将 self._ 传递给 UIManager
        self.ui_manager = UIManager(self, translator=self._)
        self.event_handler = EventHandler(self)

        self._create_image_assets()
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        self.ui_manager.setup_initial_ui()

        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()

        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)
        self.set_app_icon()

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
            # 【修改】使用 self._
            self.logger.warning(self._("图片资源未找到: '{}'").format(image_path))
        except Exception as e:
            # 【修改】使用 self._
            self.logger.error(self._("获取图片资源 '{}' 路径时发生错误: {}").format(file_name, e))
        return None

    def _create_editor_widgets(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        def get_row():
            nonlocal row_counter; r = row_counter; row_counter += 1; return r

        def section(title_key):
            # 【修改】使用 self._
            ttkb.Label(parent, text=f"◇ {self._(title_key)} ◇", font=self.app_subtitle_font, bootstyle="primary").grid(
                row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)

        def create_entry_row(label_key, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
            container.grid_columnconfigure(1, weight=1)
            # 【修改】使用 self._
            ttkb.Label(container, text=self._(label_key)).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            widget = ttkb.Entry(container);
            widget.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
            # 【修改】使用 self._
            if tooltip_key: ttkb.Label(container, text=self._(tooltip_key), font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget

        def create_switch_row(label_key, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            # 【修改】使用 self._
            ttkb.Label(container, text=self._(label_key)).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            var = tk.BooleanVar();
            widget = ttkb.Checkbutton(container, variable=var, bootstyle="round-toggle");
            widget.grid(row=0, column=1, sticky="w", padx=5)
            # 【修改】使用 self._
            if tooltip_key: ttkb.Label(container, text=self._(tooltip_key), font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget, var

        def create_option_menu_row(label_key, var, default, values, tooltip_key=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            # 【修改】使用 self._
            ttkb.Label(container, text=self._(label_key)).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            var.set(default);
            widget = ttkb.OptionMenu(container, var, default, *values, bootstyle='info-outline');
            widget.grid(row=0, column=1, sticky="ew", padx=5)
            # 【修改】使用 self._
            if tooltip_key: ttkb.Label(container, text=self._(tooltip_key), font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget

        # 【修改】所有硬编码的中文都改为 key，用 self._ 翻译
        section("通用设置")
        self.general_log_level_var = tk.StringVar()
        self.general_log_level_menu = create_option_menu_row("日志级别", self.general_log_level_var, "INFO",
                                                             ["DEBUG", "INFO", "WARNING", "ERROR"],
                                                             "设置应用程序的日志详细程度。")

        self.proxy_http_entry = create_entry_row("HTTP代理", "例如: http://127.0.0.1:7890")
        self.proxy_https_entry = create_entry_row("HTTPS代理", "例如: https://127.0.0.1:7890")

        proxy_button_frame = ttkb.Frame(parent)
        proxy_button_frame.grid(row=get_row(), column=0, sticky="e", padx=5, pady=5)
        self.test_proxy_button = ttkb.Button(proxy_button_frame, text=self._("测试代理连接"),
                                             command=self.event_handler.test_proxy_connection,
                                             bootstyle="primary-outline")
        self.test_proxy_button.pack()

        section("数据下载器配置")
        self.downloader_sources_file_entry = create_entry_row("基因组源文件", "定义基因组下载链接的YAML文件。")
        self.downloader_output_dir_entry = create_entry_row("下载输出根目录", "所有下载文件存放的基准目录。")
        self.downloader_force_download_switch, self.downloader_force_download_var = create_switch_row("强制重新下载",
                                                                                                      "如果文件已存在，是否覆盖。")
        self.downloader_max_workers_entry = create_entry_row("最大下载线程数", "多线程下载时使用的最大线程数。")
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = create_switch_row("为下载使用代理",
                                                                                            "是否为数据下载启用代理。")

        section("AI 服务配置")
        self.ai_default_provider_var = tk.StringVar()
        self.ai_default_provider_menu = create_option_menu_row("默认AI服务商", self.ai_default_provider_var,
                                                               "Google Gemini",
                                                               [p['name'] for p in self.AI_PROVIDERS.values()],
                                                               "选择默认使用的AI模型提供商。")
        self.batch_ai_max_workers_entry = create_entry_row("最大并行AI任务数", "执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。")
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row("为AI服务使用代理",
                                                                            "是否为连接AI模型API启用代理。")

        for p_key, p_info in self.AI_PROVIDERS.items():
            card = ttkb.LabelFrame(parent, text=p_info['name'], bootstyle="secondary")
            card.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)
            safe_key = p_key.replace('-', '_')

            ttkb.Label(card, text="API Key").grid(row=0, column=0, sticky="w", padx=10, pady=5)
            apikey_entry = ttkb.Entry(card);
            apikey_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)

            ttkb.Label(card, text="Model").grid(row=1, column=0, sticky="w", padx=10, pady=5)
            model_frame = ttkb.Frame(card);
            model_frame.grid(row=1, column=1, sticky="ew", pady=5, padx=5);
            model_frame.grid_columnconfigure(0, weight=1)
            model_var = tk.StringVar(value=self._("点击刷新获取列表"))
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, self._("点击刷新..."), bootstyle="info");
            model_dropdown.configure(state="disabled");
            model_dropdown.grid(row=0, column=0, sticky="ew")
            button_frame = ttkb.Frame(model_frame);
            button_frame.grid(row=0, column=1, padx=(10, 0))
            ttkb.Button(button_frame, text=self._("刷新"), width=8,
                        command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk, use_proxy=False),
                        bootstyle='outline').pack(side="left")
            ttkb.Button(button_frame, text=self._("代理刷新"), width=10,
                        command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk, use_proxy=True),
                        bootstyle='info-outline').pack(side="left", padx=(5, 0))
            setattr(self, f"ai_{safe_key}_model_selector", (model_dropdown, model_var))

            ttkb.Label(card, text="Base URL").grid(row=2, column=0, sticky="w", padx=10, pady=5)
            baseurl_entry = ttkb.Entry(card);
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        section("AI 提示词模板")
        f_trans = ttkb.Frame(parent);
        f_trans.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_trans.grid_columnconfigure(1, weight=1)
        ttkb.Label(f_trans, text=self._("翻译提示词")).grid(row=0, column=0, sticky="nw", padx=(5, 10))
        bg_t, fg_t = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        self.ai_translation_prompt_textbox = tk.Text(f_trans, height=7, font=self.app_font_mono, wrap="word",
                                                     relief="flat", background=bg_t, foreground=fg_t,
                                                     insertbackground=fg_t)
        self.ai_translation_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

        f_ana = ttkb.Frame(parent);
        f_ana.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_ana.grid_columnconfigure(1, weight=1)
        ttkb.Label(f_ana, text=self._("分析提示词")).grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.ai_analysis_prompt_textbox = tk.Text(f_ana, height=7, font=self.app_font_mono, wrap="word", relief="flat",
                                                  background=bg_t, foreground=fg_t, insertbackground=fg_t)
        self.ai_analysis_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

    def _apply_config_values_to_editor(self):
        if not self.current_config or not self.editor_ui_built: return
        cfg = self.current_config

        # 这是一个内部帮助函数，用于设置输入框的值
        def set_val(widget, value):
            if not widget: return
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END);
                widget.insert("1.0", str(value or ""))
            elif isinstance(widget, ttkb.Entry):
                widget.delete(0, tk.END);
                widget.insert(0, str(value or ""))

        # --- 常规设置 ---
        self.general_log_level_var.set(cfg.log_level)
        set_val(self.proxy_http_entry, cfg.proxies.http)
        set_val(self.proxy_https_entry, cfg.proxies.https)

        # --- 下载器配置 ---
        set_val(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        set_val(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(cfg.downloader.force_download)
        set_val(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        self.downloader_use_proxy_var.set(cfg.downloader.use_proxy_for_download)

        # --- AI 服务配置 ---
        set_val(self.batch_ai_max_workers_entry, cfg.batch_ai_processor.max_workers)
        self.ai_default_provider_var.set(self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name', ''))
        self.ai_use_proxy_var.set(cfg.ai_services.use_proxy_for_ai)

        # --- AI 服务商具体设置【已修正】---
        for p_key, p_cfg in cfg.ai_services.providers.items():
            safe_key = p_key.replace('-', '_')

            # 【修正】从 "p_cfg" 读取值，并设置到 "widget" 中
            if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry", None):
                set_val(apikey_widget, p_cfg.api_key)  # <-- 已修正

            # 【修正】从 "p_cfg" 读取值，并设置到 "widget" 中
            if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry", None):
                set_val(baseurl_widget, p_cfg.base_url)  # <-- 已修正

            if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                _dropdown, var = model_selector
                # 这里的模型下拉菜单逻辑是正确的
                var.set(p_cfg.model or "")

        # --- AI 提示词模板 ---
        set_val(self.ai_translation_prompt_textbox, cfg.ai_prompts.translation_prompt)
        set_val(self.ai_analysis_prompt_textbox, cfg.ai_prompts.analysis_prompt)

        self.logger.info(self._("配置已应用到编辑器UI。"))

    def _save_config_from_editor(self):
        if not self.current_config or not self.config_path:
            # 【修改】使用 self._
            self.ui_manager.show_error_message(self._("错误"), self._("没有加载配置文件，无法保存。"))
            return
        try:
            cfg = self.current_config
            cfg.log_level = self.general_log_level_var.get()
            cfg.proxies.http = self.proxy_http_entry.get() or None
            cfg.proxies.https = self.proxy_https_entry.get() or None
            cfg.downloader.genome_sources_file = self.downloader_sources_file_entry.get()
            cfg.downloader.download_output_base_dir = self.downloader_output_dir_entry.get()
            cfg.downloader.force_download = self.downloader_force_download_var.get()
            cfg.downloader.max_workers = int(self.downloader_max_workers_entry.get() or 3)
            cfg.downloader.use_proxy_for_download = self.downloader_use_proxy_var.get()

            try:
                max_workers_val = int(self.batch_ai_max_workers_entry.get())
                if max_workers_val <= 0:
                    raise ValueError
                cfg.batch_ai_processor.max_workers = max_workers_val
            except (ValueError, TypeError):
                # 【修改】使用 self._
                cfg.batch_ai_processor.max_workers = 4
                self.logger.warning(self._("无效的最大工作线程数值，已重置为默认值 4。"))

            cfg.ai_services.default_provider = next(
                (k for k, v in self.AI_PROVIDERS.items() if v['name'] == self.ai_default_provider_var.get()), 'google')
            cfg.ai_services.use_proxy_for_ai = self.ai_use_proxy_var.get()

            for p_key, p_cfg in cfg.ai_services.providers.items():
                safe_key = p_key.replace('-', '_')
                if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry",
                                            None): p_cfg.api_key = apikey_widget.get()
                if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry",
                                             None): p_cfg.base_url = baseurl_widget.get() or None
                if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                    dropdown, var = model_selector
                    p_cfg.model = var.get()

            cfg.ai_prompts.translation_prompt = self.ai_translation_prompt_textbox.get("1.0", tk.END).strip()
            cfg.ai_prompts.analysis_prompt = self.ai_analysis_prompt_textbox.get("1.0", tk.END).strip()

            if save_config(cfg, self.config_path):
                # 【修改】使用 self._
                self.ui_manager.show_info_message(self._("保存成功"), self._("配置文件已更新。"))
                self.ui_manager.update_ui_from_config()
            else:
                # 【修改】使用 self._
                self.ui_manager.show_error_message(self._("保存失败"), self._("写入文件时发生未知错误。"))
        except Exception as e:
            # 【修改】使用 self._
            self.ui_manager.show_error_message(self._("保存错误"),
                                               self._("保存配置时发生错误:\n{}").format(traceback.format_exc()))

    def _create_home_frame(self, parent):
        page = ttkb.Frame(parent)
        page.grid_columnconfigure(0, weight=1)

        # 将标题标签也存起来以便翻译
        title_label = ttkb.Label(page, text=self.title_text_key, font=self.app_title_font)
        title_label.pack(pady=(40, 10))
        self.translatable_widgets[title_label] = self.title_text_key

        ttkb.Label(page, textvariable=self.config_path_display_var, font=self.app_font, bootstyle="secondary").pack(
            pady=(10, 20))
        cards_frame = ttkb.Frame(page)
        cards_frame.pack(pady=20, padx=20, fill="x", expand=False)
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        def create_card(p, col, title_key, buttons):
            # 【修改】将 card 和 button 存入 self.translatable_widgets
            card = ttkb.LabelFrame(p, text=self._(title_key), bootstyle="primary")
            card.grid(row=0, column=col, padx=10, pady=10, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)
            self.translatable_widgets[card] = title_key  # 追踪卡片标题

            for i, (text_key, cmd, style) in enumerate(buttons):
                # 这里的样式转换逻辑似乎与 ttkbootstrap 的新版本或预期不符，暂时保留
                if style == "outline":
                    style = "primary"
                elif style == "info-outline":
                    style = "info"

                btn = ttkb.Button(card, text=self._(text_key), command=cmd, bootstyle=style)
                btn.grid(row=i, column=0, sticky="ew", padx=20, pady=10)
                self.translatable_widgets[btn] = text_key  # 追踪按钮文本

        # 定义按钮时直接使用文本key
        config_buttons = [
            ("加载配置文件...", self.event_handler.load_config_file, "outline"),
            ("生成默认配置...", self.event_handler._generate_default_configs_gui, "info-outline")
        ]
        help_buttons = [
            ("在线帮助文档", self.event_handler._open_online_help, "outline"),
            ("关于本软件", self.event_handler._show_about_window, "info-outline")
        ]

        create_card(cards_frame, 0, "配置文件", config_buttons)
        create_card(cards_frame, 1, "帮助与支持", help_buttons)
        return page

    def _create_tools_frame(self, parent):
        frame = ttkb.Frame(parent);
        frame.grid_columnconfigure(0, weight=1);
        frame.grid_rowconfigure(0, weight=1)
        self.tools_notebook = ttkb.Notebook(frame, bootstyle="info");
        self.tools_notebook.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        return frame



    def _populate_tools_notebook(self):
        self.tool_tab_instances.clear()

        from ui.tabs.ai_assistant_tab import AIAssistantTab
        from ui.tabs.data_download_tab import DataDownloadTab
        from ui.tabs.annotation_tab import AnnotationTab
        from ui.tabs.enrichment_tab import EnrichmentTab
        from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
        from ui.tabs.gff_query_tab import GFFQueryTab
        from ui.tabs.homology_tab import HomologyTab
        from ui.tabs.locus_conversion_tab import LocusConversionTab
        from ui.tabs.xlsx_converter_tab import XlsxConverterTab

        tab_map = {
            "download": DataDownloadTab,
            "xlsx_to_csv": XlsxConverterTab,
            "genome_identifier": GenomeIdentifierTab,
            "homology": HomologyTab,
            "locus_conversion": LocusConversionTab,
            "gff_query": GFFQueryTab,
            "ai_assistant": AIAssistantTab,
            "annotation": AnnotationTab,
            "enrichment": EnrichmentTab
        }
        for key in self.TOOL_TAB_ORDER:
            if TabClass := tab_map.get(key):
                tab_frame = ttkb.Frame(self.tools_notebook)
                # 【修改】将 self._ 传入 TabClass
                instance = TabClass(parent=tab_frame, app=self, translator=self._)
                # 【修改】使用 self._ 翻译 Notebook 的标签
                self.tools_notebook.add(tab_frame, text=self._(self.TAB_TITLE_KEYS[key]))
                self.tool_tab_instances[key] = instance
        if self.tools_notebook.tabs(): self.tools_notebook.select(0)

    def set_app_icon(self):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path): self.iconbitmap(icon_path)
        except Exception as e:
            # 【修改】使用 self._
            self.logger.warning(self._("加载主窗口图标失败: {}。").format(e))

    def _create_editor_frame(self, parent):
        page = ttkb.Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        top_frame = ttkb.Frame(page)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_frame.grid_columnconfigure(0, weight=1)
        # 【修改】使用 self._
        ttkb.Label(top_frame, text=self._("!! 警告: 配置文件可能包含敏感信息，请勿轻易分享。"), font=self.app_font_bold,
                   bootstyle="danger").grid(row=0, column=0, sticky="w", padx=5)
        self.save_editor_button = ttkb.Button(top_frame, text=self._("应用并保存"), command=self._save_config_from_editor,
                                              bootstyle='success')
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)

        self.editor_canvas = tk.Canvas(page, highlightthickness=0, bd=0,
                                       background=self.style.lookup('TFrame', 'background'))
        self.editor_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        scrollbar = ttkb.Scrollbar(page, orient="vertical", command=self.editor_canvas.yview, bootstyle="round")
        scrollbar.grid(row=1, column=1, sticky="ns", pady=10)

        self.editor_canvas.configure(yscrollcommand=scrollbar.set)

        self.editor_scroll_frame = ttkb.Frame(self.editor_canvas)
        window_id = self.editor_canvas.create_window((0, 0), window=self.editor_scroll_frame, anchor="nw")

        self._last_editor_canvas_width = 0

        def on_frame_configure(event):
            self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all"))

        def on_canvas_resize(event):
            if event.width != self._last_editor_canvas_width:
                self.editor_canvas.itemconfig(window_id, width=event.width)
                self._last_editor_canvas_width = event.width
            self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all"))

        self.editor_scroll_frame.bind("<Configure>", on_frame_configure)
        self.editor_canvas.bind("<Configure>", on_canvas_resize)

        def _on_mousewheel(event):
            if self.editor_canvas.winfo_exists():
                is_on_canvas_or_frame = event.widget == self.editor_canvas or \
                                        self.editor_scroll_frame.winfo_exists() and \
                                        self.editor_scroll_frame.winfo_toplevel() == event.widget.winfo_toplevel() and \
                                        self.editor_scroll_frame.winfo_containing(event.x_root, event.y_root) is not None

                if event.widget == self.editor_canvas or event.widget.master == self.editor_scroll_frame or event.widget == self.editor_scroll_frame:
                    if event.num == 5 or event.delta == -120:
                        self.editor_canvas.yview_scroll(1, "units")
                    if event.num == 4 or event.delta == 120:
                        self.editor_canvas.yview_scroll(-1, "units")
                    return "break"

        self.editor_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.editor_canvas.bind("<Button-4>", _on_mousewheel)
        self.editor_canvas.bind("<Button-5>", _on_mousewheel)

        self.editor_scroll_frame.bind("<MouseWheel>", _on_mousewheel)
        self.editor_scroll_frame.bind("<Button-4>", _on_mousewheel)
        self.editor_scroll_frame.bind("<Button-5>", _on_mousewheel)

        # 【修改】使用 self._
        self.editor_no_config_label = ttkb.Label(page, text=self._("请先从“主页”加载或生成一个配置文件。"),
                                                 font=self.app_subtitle_font, bootstyle="secondary")
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew", columnspan=2)
        return page

    def _handle_editor_ui_update(self):
        if not self.editor_ui_built: return
        has_config = bool(self.current_config)
        if self.editor_canvas and self.editor_canvas.winfo_exists():
            slaves = self.editor_canvas.master.grid_slaves(row=1, column=1)
            if slaves:
                scrollbar = slaves[0]
                if has_config:
                    self.editor_canvas.grid();
                    scrollbar.grid();
                    self.editor_no_config_label.grid_remove()
                    self._apply_config_values_to_editor()
                else:
                    self.editor_canvas.grid_remove();
                    scrollbar.grid_remove();
                    self.editor_no_config_label.grid()
        if hasattr(self, 'save_editor_button'):
            self.save_editor_button.configure(state="normal" if has_config else "disabled")

    def _setup_fonts(self):
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "sans-serif"];
        mono_stack = ["Consolas", "Courier New", "monospace"]
        self.font_family = next((f for f in font_stack if f in tkfont.families()), "sans-serif")
        self.mono_font_family = next((f for f in mono_stack if f in tkfont.families()), "monospace")
        # 【修改】使用 self._
        self.logger.info(self._("UI font set to: {}, Monospace font to: {}").format(self.font_family, self.mono_font_family))
        self.app_font = tkfont.Font(family=self.font_family, size=12);
        self.app_font_italic = tkfont.Font(family=self.font_family, size=12, slant="italic");
        self.app_font_bold = tkfont.Font(family=self.font_family, size=13, weight="bold");
        self.app_subtitle_font = tkfont.Font(family=self.font_family, size=16, weight="bold");
        self.app_title_font = tkfont.Font(family=self.font_family, size=24, weight="bold");
        self.app_comment_font = tkfont.Font(family=self.font_family, size=11);
        self.app_font_mono = tkfont.Font(family=self.mono_font_family, size=12)
        for style_name in ['TButton', 'TCheckbutton', 'TMenubutton', 'TLabel', 'TEntry', 'Toolbutton',
                           'Labelframe.TLabel']:
            self.style.configure(style_name, font=self.app_font)
        self.style.configure('success.TButton', font=self.app_font_bold)
        self.style.configure('info-outline.TButton', font=self.app_font)
        self.style.configure('outline.TButton', font=self.app_font)

    def _log_to_viewer(self, message, level="INFO"):
        if logging.getLogger().getEffectiveLevel() <= logging.getLevelName(level.upper()):
            self.log_queue.put((message, level))

    def check_queue_periodic(self):
        try:
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                self.ui_manager.display_log_message_in_ui(log_message, log_level)
        except queue.Empty:
            pass
        try:
            while not self.message_queue.empty():
                msg_type, data = self.message_queue.get_nowait()
                if handler := self.event_handler.message_handlers.get(msg_type):
                    handler(data) if data is not None else handler()
        except queue.Empty:
            pass
        except Exception as e:
            # 【修改】使用 self._
            self.logger.critical(self._("处理消息队列时出错: {}").format(e), exc_info=True)
        self.after(100, self.check_queue_periodic)

    def reconfigure_logging(self, log_level_str: str):
        try:
            if isinstance(new_level := logging.getLevelName(log_level_str.upper()), int):
                if (root := logging.getLogger()).getEffectiveLevel() != new_level:
                    root.setLevel(new_level)
                    for handler in root.handlers: handler.setLevel(new_level)
                    # 【修改】使用 self._
                    self.logger.info(self._("全局日志级别已更新为: {}").format(log_level_str))
        except Exception as e:
            # 【修改】使用 self._
            self.logger.error(self._("配置日志级别时出错: {}").format(e))


if __name__ == "__main__":
    # 定义默认语言和一个默认的配置文件路径
    DEFAULT_LANGUAGE = 'zh-hans'
    DEFAULT_CONFIG_PATH = 'config.yml'

    lang_code = DEFAULT_LANGUAGE

    try:
        if os.path.exists(DEFAULT_CONFIG_PATH):
            config = load_config(DEFAULT_CONFIG_PATH)
            lang_code = getattr(config, 'language', DEFAULT_LANGUAGE)
            print(f"Config file loaded. Language set to '{lang_code}'.")
        else:
            print(f"Config file not found at '{DEFAULT_CONFIG_PATH}'. Using default language '{lang_code}'.")
    except Exception as e:
        print(f"Error loading config, falling back to default language. Error: {e}")
        lang_code = DEFAULT_LANGUAGE

    # 【修改】setup_localization 会返回翻译函数，我们捕获它
    translator = setup_localization(lang_code)

    # 【修改】将 translator 注入主应用
    app = CottonToolkitApp(translator=translator)
    app.mainloop()