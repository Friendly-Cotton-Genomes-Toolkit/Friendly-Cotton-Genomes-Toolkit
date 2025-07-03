import logging
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from queue import Queue
from tkinter import filedialog, font as tkfont
from typing import Optional, Any, Dict, List

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *

from cotton_toolkit.config.loader import save_config, load_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.data_download_tab import DataDownloadTab
from ui.tabs.genome_identifier_tab import GenomeIdentifierTab
from ui.tabs.gff_query_tab import GFFQueryTab
from ui.tabs.homology_tab import HomologyTab
from ui.tabs.locus_conversion_tab import LocusConversionTab
from ui.tabs.xlsx_converter_tab import XlsxConverterTab
from ui.ui_manager import UIManager

_ = lambda s: str(s)


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    AI_PROVIDERS = {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                    "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                    "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                    "openai_compatible": {"name": _("通用OpenAI兼容接口")}}

    TOOL_TAB_ORDER = ["download", "xlsx_to_csv", "genome_identifier", "homology", "locus_conversion", "gff_query",
                      "ai_assistant"]
    TAB_TITLE_KEYS = {
        "download": "数据下载", "xlsx_to_csv": "XLSX转CSV", "genome_identifier": "基因组鉴定",
        "homology": "同源转换", "locus_conversion": "位点转换", "gff_query": "GFF查询",
        "ai_assistant": "AI助手",
    }

    def __init__(self):
        super().__init__(themename="flatly")
        self.logger = logging.getLogger(__name__)

        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1100x750")
        self.minsize(900, 700)

        self._setup_fonts()
        self.placeholder_color = (self.style.colors.secondary, self.style.colors.secondary)
        self.default_text_color = self.style.lookup('TLabel', 'foreground')
        self.secondary_text_color = self.style.colors.info
        self.placeholders = {
            "homology_genes": _("在此处粘贴基因ID，每行一个..."),
            "gff_genes": _("在此处粘贴基因ID，每行一个..."),
            "gff_region": _("例如: Gh_A01:1-100000"),
        }

        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data = {}
        self.log_queue = Queue()
        self.message_queue = Queue()
        self.active_task_name: Optional[str] = None
        self.cancel_current_task_event = threading.Event()
        self.ui_settings = {}
        self.translatable_widgets = {}
        self.log_viewer_visible = False
        self.editor_ui_built = False
        self.tool_tab_instances = {}

        self.config_path_display_var = tk.StringVar(value=_("未加载配置"))
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
            self.logger.warning(f"图片资源未找到: '{image_path}'")
        except Exception as e:
            self.logger.error(f"获取图片资源 '{file_name}' 路径时发生错误: {e}")
        return None

    def _create_editor_widgets(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        def get_row():
            nonlocal row_counter; r = row_counter; row_counter += 1; return r

        def section(title):
            ttkb.Label(parent, text=f"◇ {title} ◇", font=self.app_subtitle_font, bootstyle="primary").grid(
                row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)

        def create_entry_row(label, tooltip=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
            container.grid_columnconfigure(1, weight=1)
            ttkb.Label(container, text=label).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            widget = ttkb.Entry(container);
            widget.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
            if tooltip: ttkb.Label(container, text=tooltip, font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget

        def create_switch_row(label, tooltip=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            ttkb.Label(container, text=label).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            var = tk.BooleanVar();
            widget = ttkb.Checkbutton(container, variable=var, bootstyle="round-toggle");
            widget.grid(row=0, column=1, sticky="w", padx=5)
            if tooltip: ttkb.Label(container, text=tooltip, font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget, var

        def create_option_menu_row(label, var, default, values, tooltip=""):
            container = ttkb.Frame(parent);
            container.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
            container.grid_columnconfigure(1, weight=1)
            ttkb.Label(container, text=label).grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
            var.set(default);
            widget = ttkb.OptionMenu(container, var, default, *values, bootstyle='info-outline');
            widget.grid(row=0, column=1, sticky="ew", padx=5)
            if tooltip: ttkb.Label(container, text=tooltip, font=self.app_comment_font, bootstyle="secondary").grid(
                row=1, column=1, sticky="w", padx=5)
            return widget

        section(_("通用设置"))
        self.general_log_level_var = tk.StringVar()
        self.general_log_level_menu = create_option_menu_row(_("日志级别"), self.general_log_level_var, "INFO",
                                                             ["DEBUG", "INFO", "WARNING", "ERROR"],
                                                             _("设置应用程序的日志详细程度。"))
        self.general_i18n_lang_var = tk.StringVar()
        self.general_i18n_lang_menu = create_option_menu_row(_("命令行语言"), self.general_i18n_lang_var, "简体中文",
                                                             list(self.LANG_CODE_TO_NAME.values()),
                                                             _("设置后端日志和消息的语言。"))
        self.proxy_http_entry = create_entry_row(_("HTTP代理"), _("例如: http://127.0.0.1:7890"))
        self.proxy_https_entry = create_entry_row(_("HTTPS代理"), _("例如: https://127.0.0.1:7890"))

        proxy_button_frame = ttkb.Frame(parent)
        proxy_button_frame.grid(row=get_row(), column=0, sticky="e", padx=5, pady=5)
        self.test_proxy_button = ttkb.Button(proxy_button_frame, text=_("测试代理连接"),
                                             command=self.event_handler.test_proxy_connection,
                                             bootstyle="primary-outline")
        self.test_proxy_button.pack()

        section(_("数据下载器配置"))
        self.downloader_sources_file_entry = create_entry_row(_("基因组源文件"), _("定义基因组下载链接的YAML文件。"))
        self.downloader_output_dir_entry = create_entry_row(_("下载输出根目录"), _("所有下载文件存放的基准目录。"))
        self.downloader_force_download_switch, self.downloader_force_download_var = create_switch_row(_("强制重新下载"),
                                                                                                      _("如果文件已存在，是否覆盖。"))
        self.downloader_max_workers_entry = create_entry_row(_("最大下载线程数"), _("多线程下载时使用的最大线程数。"))
        self.downloader_use_proxy_switch, self.downloader_use_proxy_var = create_switch_row(_("为下载使用代理"),
                                                                                            _("是否为数据下载启用代理。"))

        section(_("AI 服务配置"))
        self.ai_default_provider_var = tk.StringVar()
        self.ai_default_provider_menu = create_option_menu_row(_("默认AI服务商"), self.ai_default_provider_var,
                                                               "Google Gemini",
                                                               [p['name'] for p in self.AI_PROVIDERS.values()],
                                                               _("选择默认使用的AI模型提供商。"))
        self.batch_ai_max_workers_entry = create_entry_row(_("最大并行AI任务数"), _("执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"))
        self.ai_use_proxy_switch, self.ai_use_proxy_var = create_switch_row(_("为AI服务使用代理"),
                                                                            _("是否为连接AI模型API启用代理。"))

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
            model_var = tk.StringVar(value=_("点击刷新获取列表"))
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, _("点击刷新..."), bootstyle="info");
            model_dropdown.configure(state="disabled");
            model_dropdown.grid(row=0, column=0, sticky="ew")
            button_frame = ttkb.Frame(model_frame);
            button_frame.grid(row=0, column=1, padx=(10, 0))
            ttkb.Button(button_frame, text=_("刷新"), width=8,
                        command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk, use_proxy=False),
                        bootstyle='outline').pack(side="left")
            ttkb.Button(button_frame, text=_("代理刷新"), width=10,
                        command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk, use_proxy=True),
                        bootstyle='info-outline').pack(side="left", padx=(5, 0))
            setattr(self, f"ai_{safe_key}_model_selector", (model_dropdown, model_var))

            ttkb.Label(card, text="Base URL").grid(row=2, column=0, sticky="w", padx=10, pady=5)
            baseurl_entry = ttkb.Entry(card);
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        section(_("AI 提示词模板"))
        f_trans = ttkb.Frame(parent);
        f_trans.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_trans.grid_columnconfigure(1, weight=1)
        ttkb.Label(f_trans, text=_("翻译提示词")).grid(row=0, column=0, sticky="nw", padx=(5, 10))
        bg_t, fg_t = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        self.ai_translation_prompt_textbox = tk.Text(f_trans, height=7, font=self.app_font_mono, wrap="word",
                                                     relief="flat", background=bg_t, foreground=fg_t,
                                                     insertbackground=fg_t)
        self.ai_translation_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

        f_ana = ttkb.Frame(parent);
        f_ana.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_ana.grid_columnconfigure(1, weight=1)
        ttkb.Label(f_ana, text=_("分析提示词")).grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.ai_analysis_prompt_textbox = tk.Text(f_ana, height=7, font=self.app_font_mono, wrap="word", relief="flat",
                                                  background=bg_t, foreground=fg_t, insertbackground=fg_t)
        self.ai_analysis_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

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
        self.general_i18n_lang_var.set(self.LANG_CODE_TO_NAME.get(cfg.i18n_language, "zh-hans"))
        set_val(self.proxy_http_entry, cfg.proxies.http)
        set_val(self.proxy_https_entry, cfg.proxies.https)
        set_val(self.downloader_sources_file_entry, cfg.downloader.genome_sources_file)
        set_val(self.downloader_output_dir_entry, cfg.downloader.download_output_base_dir)
        self.downloader_force_download_var.set(cfg.downloader.force_download)
        set_val(self.downloader_max_workers_entry, cfg.downloader.max_workers)
        self.downloader_use_proxy_var.set(cfg.downloader.use_proxy_for_download)
        set_val(self.batch_ai_max_workers_entry, cfg.batch_ai_processor.max_workers)
        self.ai_default_provider_var.set(self.AI_PROVIDERS.get(cfg.ai_services.default_provider, {}).get('name', ''))
        self.ai_use_proxy_var.set(cfg.ai_services.use_proxy_for_ai)

        for p_key, p_cfg in cfg.ai_services.providers.items():
            safe_key = p_key.replace('-', '_')
            if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry", None): set_val(apikey_widget,
                                                                                            p_cfg.api_key)
            if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry", None): set_val(baseurl_widget,
                                                                                              p_cfg.base_url)
            if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                _dropdown, var = model_selector
                var.set(p_cfg.model or "")

        set_val(self.ai_translation_prompt_textbox, cfg.ai_prompts.translation_prompt)
        set_val(self.ai_analysis_prompt_textbox, cfg.ai_prompts.analysis_prompt)
        self.logger.info("配置已应用到编辑器UI。")

    def _save_config_from_editor(self):
        if not self.current_config or not self.config_path:
            self.ui_manager.show_error_message("错误", "没有加载配置文件，无法保存。")
            return
        try:
            cfg = self.current_config
            cfg.log_level = self.general_log_level_var.get()
            cfg.i18n_language = self.LANG_NAME_TO_CODE.get(self.general_i18n_lang_var.get(), "zh-hans")
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
                cfg.batch_ai_processor.max_workers = 4  # 如果输入无效，则恢复为默认值
                self.logger.warning("无效的最大工作线程数值，已重置为默认值 4。")

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
                self.ui_manager.show_info_message("保存成功", "配置文件已更新。")
                self.ui_manager.update_ui_from_config()
            else:
                self.ui_manager.show_error_message("保存失败", "写入文件时发生未知错误。")
        except Exception as e:
            self.ui_manager.show_error_message("保存错误", f"保存配置时发生错误:\n{traceback.format_exc()}")

    def _create_home_frame(self, parent):
        page = ttkb.Frame(parent);
        page.grid_columnconfigure(0, weight=1)
        ttkb.Label(page, text=self.title_text_key, font=self.app_title_font).pack(pady=(40, 10))
        ttkb.Label(page, textvariable=self.config_path_display_var, font=self.app_font, bootstyle="secondary").pack(
            pady=(10, 20))
        cards_frame = ttkb.Frame(page);
        cards_frame.pack(pady=20, padx=20, fill="x", expand=False);
        cards_frame.grid_columnconfigure((0, 1), weight=1)

        def create_card(p, col, title_key, buttons):
            card = ttkb.LabelFrame(p, text=_(title_key), bootstyle="primary");
            card.grid(row=0, column=col, padx=10, pady=10, sticky="nsew");
            card.grid_columnconfigure(0, weight=1)
            for i, (text_key, cmd, style) in enumerate(buttons):
                btn = ttkb.Button(card, text=_(text_key), command=cmd, bootstyle=style);
                btn.grid(row=i, column=0, sticky="ew", padx=20, pady=10);
                self.translatable_widgets[btn] = text_key

        create_card(cards_frame, 0, "配置文件", [("加载配置文件...", self.event_handler.load_config_file, "outline"),
                                                 ("生成默认配置...", self.event_handler._generate_default_configs_gui,
                                                  "info-outline")])
        create_card(cards_frame, 1, "帮助与支持", [("在线帮助文档", self.event_handler._open_online_help, "outline"),
                                                   ("关于本软件", self.event_handler._show_about_window,
                                                    "info-outline")])
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
        tab_map = {"download": DataDownloadTab, "xlsx_to_csv": XlsxConverterTab,
                   "genome_identifier": GenomeIdentifierTab, "homology": HomologyTab,
                   "locus_conversion": LocusConversionTab, "gff_query": GFFQueryTab, "ai_assistant": AIAssistantTab}
        for key in self.TOOL_TAB_ORDER:
            if TabClass := tab_map.get(key):
                tab_frame = ttkb.Frame(self.tools_notebook)
                self.tools_notebook.add(tab_frame, text=_(self.TAB_TITLE_KEYS[key]))
                self.tool_tab_instances[key] = TabClass(parent=tab_frame, app=self)
        if self.tools_notebook.tabs(): self.tools_notebook.select(0)

    def set_app_icon(self):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path): self.iconbitmap(icon_path)
        except Exception as e:
            self.logger.warning(f"加载主窗口图标失败: {e}。")

    def _create_editor_frame(self, parent):
        page = ttkb.Frame(parent);
        page.grid_columnconfigure(0, weight=1);
        page.grid_rowconfigure(1, weight=1)
        top_frame = ttkb.Frame(page);
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0));
        top_frame.grid_columnconfigure(0, weight=1)
        ttkb.Label(top_frame, text=_("!! 警告: 配置文件可能包含敏感信息，请勿轻易分享。"), font=self.app_font_bold,
                   bootstyle="danger").grid(row=0, column=0, sticky="w", padx=5)
        self.save_editor_button = ttkb.Button(top_frame, text=_("应用并保存"), command=self._save_config_from_editor,
                                              bootstyle='success');
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)
        canvas = tk.Canvas(page, highlightthickness=0, background=self.style.lookup('TFrame', 'background'));
        canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        scrollbar = ttkb.Scrollbar(page, orient="vertical", command=canvas.yview, bootstyle="round");
        scrollbar.grid(row=1, column=1, sticky="ns", pady=10)
        canvas.configure(yscrollcommand=scrollbar.set)
        self.editor_scroll_frame = ttkb.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=self.editor_scroll_frame, anchor="nw")

        def on_configure(event): canvas.configure(scrollregion=canvas.bbox("all")); canvas.itemconfig(window_id,
                                                                                                      width=event.width)

        canvas.bind("<Configure>", on_configure)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.editor_no_config_label = ttkb.Label(page, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                 font=self.app_subtitle_font, bootstyle="secondary");
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew", columnspan=2)
        return page

    def _handle_editor_ui_update(self):
        if not self.editor_ui_built: return
        has_config = bool(self.current_config)
        canvas = self.editor_scroll_frame.master
        if canvas.winfo_exists():
            slaves = canvas.master.grid_slaves(row=1, column=1)
            if slaves:
                scrollbar = slaves[0]
                if has_config:
                    canvas.grid();
                    scrollbar.grid();
                    self.editor_no_config_label.grid_remove()
                    self._apply_config_values_to_editor()
                else:
                    canvas.grid_remove();
                    scrollbar.grid_remove();
                    self.editor_no_config_label.grid()
        if hasattr(self, 'save_editor_button'):
            self.save_editor_button.configure(state="normal" if has_config else "disabled")

    def _setup_fonts(self):
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "sans-serif"];
        mono_stack = ["Consolas", "Courier New", "monospace"]
        self.font_family = next((f for f in font_stack if f in tkfont.families()), "sans-serif")
        self.mono_font_family = next((f for f in mono_stack if f in tkfont.families()), "monospace")
        self.logger.info(f"UI font set to: {self.font_family}, Monospace font to: {self.mono_font_family}")
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
            self.logger.critical(f"处理消息队列时出错: {e}", exc_info=True)
        self.after(100, self.check_queue_periodic)

    def reconfigure_logging(self, log_level_str: str):
        try:
            if isinstance(new_level := logging.getLevelName(log_level_str.upper()), int):
                if (root := logging.getLogger()).getEffectiveLevel() != new_level:
                    root.setLevel(new_level)
                    for handler in root.handlers: handler.setLevel(new_level)
                    self.logger.info(f"全局日志级别已更新为: {log_level_str}")
        except Exception as e:
            self.logger.error(f"配置日志级别时出错: {e}")


if __name__ == "__main__":
    app = CottonToolkitApp()
    app.mainloop()