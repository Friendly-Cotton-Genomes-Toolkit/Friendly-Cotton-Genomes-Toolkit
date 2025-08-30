# 文件路径: ui/gui_app.py
# 最终完整、修正、无功能遗漏版

import logging
import os
import queue
import sys
import threading
import traceback
from queue import Queue
from tkinter import font as tkfont
from typing import Optional, Dict, Any, Callable
import tkinter as tk
import ttkbootstrap as ttkb
import json
import subprocess
from ui import get_persistent_settings_path
from ui.dialogs import FirstLaunchDialog

try:
    from ctypes import windll, byref, sizeof, c_int
except ImportError:
    windll = None

from cotton_toolkit.config.loader import save_config, load_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.ui_manager import UIManager, determine_initial_theme
from ui.tabs import *

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "en": "English"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    DARK_THEMES = ["darkly", "cyborg", "solar", "superhero", "vapor"]

    @property
    def EDITOR_LAYOUT(self):
        """
        定义配置编辑器UI的布局蓝图。
        - type: 控件类型
        - label_key: 显示的标签文本（用于翻译）
        - config_path: 对应在MainConfig模型中的路径
        - tip_key: 提示文本（用于翻译）
        - options: 适用于下拉菜单的选项
        """
        return [
            {'type': 'section', 'label_key': "通用设置"},
            {'type': 'optionmenu', 'label_key': "日志级别", 'config_path': 'log_level',
             'options': ["DEBUG", "INFO", "WARNING", "ERROR"], 'tip_key': "设置应用程序的日志详细程度。"},
            {'type': 'entry', 'label_key': "HTTP代理", 'config_path': 'proxies.http',
             'tip_key': "例如: http://127.0.0.1:7890"},
            {'type': 'entry', 'label_key': "HTTPS代理", 'config_path': 'proxies.https',
             'tip_key': "例如: https://127.0.0.1:7890"},
            {'type': 'button', 'label_key': "测试代理连接", 'command': self.event_handler.test_proxy_connection,
             'style': 'primary-outline', 'align': 'e'},

            {'type': 'section', 'label_key': "数据下载器配置"},
            {'type': 'entry', 'label_key': "基因组源文件", 'config_path': 'downloader.genome_sources_file',
             'tip_key': "定义基因组下载链接的YAML文件。"},
            {'type': 'entry', 'label_key': "下载输出根目录", 'config_path': 'downloader.download_output_base_dir',
             'tip_key': "所有下载文件存放的基准目录。"},
            {'type': 'checkbutton', 'label_key': "强制重新下载", 'config_path': 'downloader.force_download',
             'tip_key': "如果文件已存在，是否覆盖。"},
            {'type': 'entry', 'label_key': "最大下载线程数", 'config_path': 'downloader.max_workers',
             'tip_key': "多线程下载时使用的最大线程数。"},
            {'type': 'checkbutton', 'label_key': "为下载使用代理", 'config_path': 'downloader.use_proxy_for_download',
             'tip_key': "是否为数据下载启用代理。"},

            {'type': 'section', 'label_key': "AI 服务配置"},
            {'type': 'optionmenu', 'label_key': "默认AI服务商", 'config_path': 'ai_services.default_provider',
             'options_map': self.AI_PROVIDERS, 'tip_key': "选择默认使用的AI模型提供商。"},
            {'type': 'entry', 'label_key': "最大并行AI任务数", 'config_path': 'batch_ai_processor.max_workers',
             'tip_key': "执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"},
            {'type': 'checkbutton', 'label_key': "为AI服务使用代理", 'config_path': 'ai_services.use_proxy_for_ai',
             'tip_key': "是否为连接AI模型API启用代理。"},
            {'type': 'section', 'label_key': "AI 提示词模板"},
            {'type': 'text', 'label_key': "翻译提示词", 'config_path': 'ai_prompts.translation_prompt', 'height': 7},
            {'type': 'text', 'label_key': "分析提示词", 'config_path': 'ai_prompts.analysis_prompt', 'height': 7},
        ]

    @property
    def AI_PROVIDERS(self):
        return {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                "openai_compatible": {"name": self._("通用OpenAI兼容接口")}}



    @property
    def TAB_TITLE_KEYS(self):
        return {
            "download": _("数据下载"), "annotation": _("功能注释"), "sequence_extraction": _("序列提取"),
            "seq_analysis": _("序列分析"), "enrichment": _("富集分析与绘图"),
            "genome_identifier": _("基因组鉴定"), "homology": _("快速同源转换"),
            "arabidopsis_conversion": _("棉花-拟南芥互转"),
            "locus_conversion": _("位点转换"), "gff_query": _("GFF查询"),
            "quantification":_("表达量标准化"),"blast": _("本地BLAST"),
            "ai_assistant": _("AI助手"),
        }

    TOOL_TAB_ORDER = [
        "download", "annotation", "enrichment", "sequence_extraction", "seq_analysis",
        "genome_identifier", "homology", "arabidopsis_conversion", "locus_conversion",
        "gff_query","quantification","blast", "ai_assistant",
    ]


    def __init__(self, translator: Callable[[str], str]):

        initial_theme = determine_initial_theme()
        super().__init__(themename=initial_theme)

        self._ = translator
        self.logger = logging.getLogger("ui.gui_app")

        self.app_icon_path: Optional[str] = self.resource_path("logo.ico")
        self.logo_image_path: Optional[str] = self.resource_path("logo.png")
        self.home_icon_path: Optional[str] = self.resource_path("home.png")
        self.tools_icon_path: Optional[str] = self.resource_path("tools.png")
        self.settings_icon_path: Optional[str] = self.resource_path("settings.png")

        self._patch_all_toplevels()

        self.title_text_key = _("Friendly Cotton Genomes Toolkit - FCGT")
        self.title(self._(self.title_text_key))
        self.geometry("1500x900")
        self.minsize(1400, 800)

        try:
            if self.app_icon_path and os.path.exists(self.app_icon_path):
                self.iconbitmap(self.app_icon_path)
                self.logger.info(_("成功加载并设置应用图标: {}").format(self.app_icon_path))
            else:
                self.logger.warning(_("应用图标文件未找到，请检查路径: {}").format(self.app_icon_path))
        except Exception as e:
            self.logger.warning(_("加载主窗口图标失败: {}").format(e))

        # 1. 立即设置所有字体。这会产生第二条日志。
        self._setup_fonts()

        # 2. 初始化所有变量和管理器
        self.placeholder_color = ("#6c757d", "#a0a0a0")
        self.default_text_color = self.style.lookup('TLabel', 'foreground')
        self.secondary_text_color = self.style.lookup('TLabel', 'foreground')

        self.placeholders = {
            "homology_genes": self._("粘贴基因ID，每行一个..."),
            "gff_genes": self._("粘贴基因ID，每行一个..."),
            "gff_region": self._("例如: A01:1-100000"),
            "genes_input": self._("在此处粘贴要注释的基因ID，每行一个"),
            "extract_seq_single": self._("输入单个基因ID, 例如: Ghir_D09G022830"),
            "extract_seq_multi": self._("每行输入一个基因ID...\nGhir_D09G022830\nGhir_D11G011140"),
            "seq_analysis_placeholder": "> Seq1_Header\nACGTACGTACGT...\n\n> Seq2_Header\nTTGGCCAA...",
            "enrichment_genes_input": self._(
                "在此处粘贴用于富集分析的基因ID，每行一个。\n如果包含Log2FC，格式为：基因ID\tLog2FC\n（注意：使用制表符分隔，从Excel直接复制的列即为制表符分隔）"),
            "custom_prompt": self._("在此处输入您的自定义提示词模板，必须包含 {text} 占位符..."),
            "default_prompt_empty": self._("Default prompt is empty, please set it in the configuration editor."),
            "blast": self._('在此处键入您的FASTA(Q)格式序列')
        }

        self.home_widgets: Dict[str, Any] = {}
        self.editor_widgets: Dict[str, Any] = {}
        self.translatable_widgets = {}
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.genome_sources_data = {}
        # 日志队列和消息队列
        self.log_queue = Queue()
        self.message_queue = Queue()

        # 统一的日志设置
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        self.active_task_name: Optional[str] = None
        self.cancel_current_task_event = threading.Event()
        self.ui_settings = {}
        self.tool_tab_instances = {}
        self.tool_buttons = {}
        self.latest_log_message_var = tk.StringVar(value="")
        self.editor_canvas: Optional[tk.Canvas] = None
        self.editor_ui_built = False
        self.log_viewer_visible = False
        self.config_path_display_var = tk.StringVar()
        self.sources_path_display_var = tk.StringVar()
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()

        self._check_for_first_launch()

        self.ui_manager = UIManager(self, translator=self._)
        self.event_handler = EventHandler(self)

        def clear_log_viewer():
            self.ui_manager.clear_log_viewer()

        self.event_handler.clear_log_viewer = clear_log_viewer

        self.apply_theme_and_update_dependencies(initial_theme)

        self.ui_manager.load_settings()
        self.ui_manager.setup_initial_ui()

        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)

    def _check_for_first_launch(self):
        """
        检查是否是首次启动，如果是，则显示欢迎和说明对话框。
        """
        ui_settings_path = get_persistent_settings_path()
        show_welcome = False

        try:
            with open(ui_settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # 检查 "first_launch" 键是否存在且为 True
                if not settings.get('first_launch', False):
                    show_welcome = True
        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或格式错误，也视为首次启动
            show_welcome = True

        if show_welcome:
            # 直接以主窗口 (self) 为父窗口显示对话框
            FirstLaunchDialog(parent=self, title='Welcome!')

            # 用户关闭对话框后，更新设置文件
            try:
                current_settings = {}
                if os.path.exists(ui_settings_path):
                    # 再次读取以防万一有其他设置
                    with open(ui_settings_path, 'r', encoding='utf-8') as f:
                        current_settings = json.load(f)

                current_settings['first_launch'] = True

                with open(ui_settings_path, 'w', encoding='utf-8') as f:
                    json.dump(current_settings, f, indent=4)
                logging.info("'first_launch' flag set to True in ui_settings.json.")

            except Exception as e:
                logging.error(f"Failed to update ui_settings.json after first launch dialog: {e}")

    def resource_path(self, relative_path: str):
        """
        获取资源的绝对路径。
        """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, "ui", "assets", relative_path)

    def _patch_all_toplevels(self):
        app_instance = self

        def apply_customizations(toplevel_self):
            if app_instance.app_icon_path:
                try:
                    toplevel_self.iconbitmap(app_instance.app_icon_path)
                except tk.TclError:
                    pass

            def _safer_refresh_task():
                app_instance.configure_title_bar_color(toplevel_self)
                toplevel_self.update_idletasks()

            toplevel_self.after(10, _safer_refresh_task)

        original_ttkb_init = ttkb.Toplevel.__init__

        def new_ttkb_init(toplevel_self, *args, **kwargs):
            original_ttkb_init(toplevel_self, *args, **kwargs)
            apply_customizations(toplevel_self)

        ttkb.Toplevel.__init__ = new_ttkb_init

        original_tk_init = tk.Toplevel.__init__

        def new_tk_init(toplevel_self, *args, **kwargs):
            original_tk_init(toplevel_self, *args, **kwargs)
            apply_customizations(toplevel_self)

        tk.Toplevel.__init__ = new_tk_init

    def configure_title_bar_color(self, window_obj):
        """
        根据当前主题和操作系统，配置窗口的原生标题栏颜色。
        - Windows: 使用 DWM API 强制设置深色/浅色模式。
        - macOS: 使用 Tcl 命令请求系统更改应用外观。
        - Linux: 无法直接控制，依赖用户系统主题，仅记录日志。
        """
        # 提前检查，如果窗口不存在则直接返回
        if not window_obj.winfo_exists():
            return

        try:
            is_dark = self.style.theme.type == 'dark'

            # --- Windows 平台逻辑 ---
            if sys.platform == "win32" and windll is not None:
                hwnd = windll.user32.GetParent(window_obj.winfo_id())
                if not hwnd: return

                # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (适用于较新 Windows 10/11)
                # DWMWA_CAPTION_COLOR = 35 (适用于较新 Windows 11, 但更复杂)
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = c_int(1 if is_dark else 0)
                windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(value), sizeof(value)
                )

            # --- macOS 平台逻辑 ---
            elif sys.platform == "darwin":
                mode = "dark" if is_dark else "light"
                try:
                    # 通过 Tcl 命令告知 macOS 系统切换应用的外观模式
                    self.tk.call("tk::mac::setAppearance", mode)
                except tk.TclError:
                    # 在一些较旧的 Tcl/Tk 版本上可能不支持此命令
                    self.logger.warning(_("无法设置macOS标题栏外观 (当前Tcl/Tk版本可能过旧)。"))

            # --- Linux 平台逻辑 ---
            elif "linux" in sys.platform:
                # 在 Linux 上，没有统一的 API 来更改标题栏主题。
                # 它由用户的桌面环境（GNOME, KDE 等）和其系统主题控制。
                # 我们在此处仅记录一条信息以供参考。
                self.logger.info(_("在Linux上，标题栏外观由您的桌面环境系统主题控制。"))

        except Exception as e:
            # 捕获其他潜在错误，例如窗口句柄失效等
            self.logger.warning(_("配置标题栏颜色时发生未知错误: {}").format(e))

    def apply_theme_and_update_dependencies(self, theme_name: str):
        try:
            # 步骤1: 应用新的ttkbootstrap主题
            self.style.theme_use(theme_name)

            # 步骤2: 立即请求Windows系统更改标题栏颜色
            self.configure_title_bar_color(self)

            self.update()

            self._force_apply_fonts()

            # 更新其他UI依赖项
            self.default_text_color = self.style.lookup('TLabel', 'foreground')
            if hasattr(self, 'ui_manager'):
                self.ui_manager.update_sidebar_style()
                self.ui_manager._update_log_tag_colors()

            self.after_idle(self.refresh_window_visuals)
        except Exception as e:
            self.logger.error(_("应用主题并刷新时出错: {}").format(e))

    def refresh_window_visuals(self):
        self.logger.debug(_("正在刷新窗口视觉效果..."))
        # 强制处理所有待处理的UI事件，确保窗口处于稳定状态
        self.update_idletasks()
        # 应用标题栏颜色
        self.configure_title_bar_color(self)

        # 增加一个微小的延迟后再次应用，这是解决Windows渲染问题的可靠技巧
        self.after(50, lambda: self.configure_title_bar_color(self))
        self.logger.debug(self._("刷新完成。"))

    def _build_editor_ui(self, parent):
        """根据 EDITOR_LAYOUT 蓝图构建编辑器UI。"""
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        is_dark = self.style.theme.type == 'dark'
        comment_fg = "#a0a0a0" if is_dark else "#6c757d"

        # 遍历蓝图，为每个条目创建控件
        for item in self.EDITOR_LAYOUT:
            item_type = item.get('type')

            frame = ttkb.Frame(parent)
            frame.grid(row=row_counter, column=0, sticky="ew", padx=5, pady=item.get('pady', 2))
            if item_type != 'section':
                frame.grid_columnconfigure(1, weight=1)

            # 根据类型调用相应的构建辅助函数
            if item_type == 'section':
                self._build_section(frame, item)
            elif item_type == 'entry':
                self._build_entry(frame, item, comment_fg)
            elif item_type == 'optionmenu':
                self._build_optionmenu(frame, item, comment_fg)
            elif item_type == 'checkbutton':
                self._build_checkbutton(frame, item, comment_fg)
            elif item_type == 'button':
                self._build_button(frame, item)
            elif item_type == 'text':
                self._build_text(frame, item)

            row_counter += 1

        # 单独处理动态的AI Provider卡片
        self._build_ai_provider_cards(parent, row_counter)

    # --- UI 构建辅助函数 ---

    def _build_section(self, frame, item):
        label = ttkb.Label(frame, text=f"◇ {self._(item['label_key'])} ◇", font=self.app_subtitle_font,
                           bootstyle="primary")
        label.grid(row=0, column=0, pady=(25, 10), sticky="w")
        self.translatable_widgets[label] = item['label_key']

    def _build_entry(self, frame, item, comment_fg):
        lbl = ttkb.Label(frame, text=self._(item['label_key']))
        lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))
        self.translatable_widgets[lbl] = item['label_key']

        entry = ttkb.Entry(frame)
        entry.grid(row=0, column=1, sticky="ew")
        self.editor_widgets[item['config_path']] = {'widget': entry, 'type': 'entry'}

        if tip_key := item.get('tip_key'):
            tip = ttkb.Label(frame, text=self._(tip_key), font=self.app_comment_font, foreground=comment_fg)
            tip.grid(row=1, column=1, sticky="w", padx=5)
            self.translatable_widgets[tip] = tip_key

    def _build_optionmenu(self, frame, item, comment_fg):
        lbl = ttkb.Label(frame, text=self._(item['label_key']))
        lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))
        self.translatable_widgets[lbl] = item['label_key']

        var = tk.StringVar()
        options = item.get('options', [])
        # 特殊处理AI服务商，它的选项来自一个字典
        if options_map := item.get('options_map'):
            options = [p['name'] for p in options_map.values()]

        menu = ttkb.OptionMenu(frame, var, options[0] if options else "", *options, bootstyle='info-outline')
        menu.grid(row=0, column=1, sticky="ew")
        self.editor_widgets[item['config_path']] = {'widget': var, 'type': 'optionmenu',
                                                    'options_map': item.get('options_map')}

        if tip_key := item.get('tip_key'):
            tip = ttkb.Label(frame, text=self._(tip_key), font=self.app_comment_font, foreground=comment_fg)
            tip.grid(row=1, column=1, sticky="w", padx=5)
            self.translatable_widgets[tip] = tip_key

    def _build_checkbutton(self, frame, item, comment_fg):
        lbl = ttkb.Label(frame, text=self._(item['label_key']))
        lbl.grid(row=0, column=0, sticky="w", padx=(5, 10))
        self.translatable_widgets[lbl] = item['label_key']

        var = tk.BooleanVar()
        chk = ttkb.Checkbutton(frame, variable=var, bootstyle="round-toggle")
        chk.grid(row=0, column=1, sticky="w")
        self.editor_widgets[item['config_path']] = {'widget': var, 'type': 'checkbutton'}

        if tip_key := item.get('tip_key'):
            tip = ttkb.Label(frame, text=self._(tip_key), font=self.app_comment_font, foreground=comment_fg)
            tip.grid(row=1, column=1, sticky="w", padx=5)
            self.translatable_widgets[tip] = tip_key

    def _build_button(self, frame, item):
        btn = ttkb.Button(frame, text=self._(item['label_key']), command=item.get('command'),
                          bootstyle=item.get('style', 'primary'))
        # 1. 从“蓝图”中获取对齐字符 ('e' 代表右对齐, 'w' 代表左对齐)
        align_char = item.get('align', 'w')

        side_value = 'right' if align_char == 'e' else 'left'
        btn.pack(side=side_value, padx=5, pady=5)
        self.translatable_widgets[btn] = item['label_key']

    def _build_text(self, frame, item):
        lbl = ttkb.Label(frame, text=self._(item['label_key']))
        lbl.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.translatable_widgets[lbl] = item['label_key']

        bg, fg = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        text_widget = tk.Text(frame, height=item.get('height', 5), font=self.app_font_mono, wrap="word",
                              relief="flat", background=bg, foreground=fg, insertbackground=fg)
        text_widget.grid(row=0, column=1, sticky="ew")
        self.editor_widgets[item['config_path']] = {'widget': text_widget, 'type': 'text'}

    def _build_ai_provider_cards(self, parent, start_row):
        """动态创建所有AI Provider的配置卡片。"""
        row_counter = start_row
        for p_key, p_info in self.AI_PROVIDERS.items():
            card = ttkb.LabelFrame(parent, text=p_info['name'], bootstyle="secondary")
            card.grid(row=row_counter, column=0, sticky="ew", pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)
            row_counter += 1

            # API Key
            lbl_apikey = ttkb.Label(card, text="API Key")
            lbl_apikey.grid(row=0, column=0, sticky="w", padx=10, pady=5)
            apikey_entry = ttkb.Entry(card)
            apikey_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5)
            self.editor_widgets[f'ai_services.providers.{p_key}.api_key'] = {'widget': apikey_entry, 'type': 'entry'}

            # Base URL
            lbl_baseurl = ttkb.Label(card, text="Base URL")
            lbl_baseurl.grid(row=2, column=0, sticky="w", padx=10, pady=5)
            baseurl_entry = ttkb.Entry(card)
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
            self.editor_widgets[f'ai_services.providers.{p_key}.base_url'] = {'widget': baseurl_entry, 'type': 'entry'}

            # Model Dropdown (handled specially as it's dynamic)
            lbl_model = ttkb.Label(card, text="Model")
            lbl_model.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            model_frame = ttkb.Frame(card)
            model_frame.grid(row=1, column=1, sticky="ew", pady=5, padx=5)
            model_frame.grid_columnconfigure(0, weight=1)

            model_var = tk.StringVar(value=self._("点击刷新获取列表"))
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, self._("点击刷新..."), bootstyle="info")
            model_dropdown.configure(state="disabled")
            model_dropdown.grid(row=0, column=0, sticky="ew")
            # We store the widget and var for dynamic updates, and the var for saving.
            self.editor_widgets[f'ai_services.providers.{p_key}.model'] = {'widget': model_var, 'type': 'optionmenu',
                                                                           'dropdown': model_dropdown}

            btn_frame = ttkb.Frame(model_frame)
            btn_frame.grid(row=0, column=1, padx=(10, 0))
            btn_refresh = ttkb.Button(btn_frame, text=self._("刷新"), width=8,
                                      command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                       use_proxy=False),
                                      bootstyle='outline')
            btn_refresh.pack(side="left")
            btn_proxy_refresh = ttkb.Button(btn_frame, text=self._("代理刷新"), width=10,
                                            command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                             use_proxy=True),
                                            bootstyle='info-outline')
            btn_proxy_refresh.pack(side="left", padx=(5, 0))


    def _create_editor_widgets(self, parent):
        """
        此函数现在只调用新的UI构建器。
        """
        self.editor_widgets.clear()
        self._build_editor_ui(parent)
        self.logger.info(_("配置编辑器UI已通过数据驱动模式构建。"))

    def _apply_config_values_to_editor(self):
        """
        从配置对象(self.current_config)加载值并应用到UI控件。
        """
        if not self.current_config or not self.editor_ui_built: return

        def get_value_from_path(config_obj, path):
            """一个健壮的函数，可以从混合了对象和字典的结构中获取值。"""
            keys = path.split('.')
            val = config_obj
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)
                else:
                    val = getattr(val, key, None)

                if val is None:
                    return None
            return val

        for path, info in self.editor_widgets.items():
            widget = info['widget']
            widget_type = info['type']
            value = get_value_from_path(self.current_config, path)
            value = '' if value is None else value

            if widget_type == 'entry':
                widget.delete(0, tk.END)
                widget.insert(0, str(value))
            elif widget_type == 'text':
                widget.delete("1.0", tk.END)
                widget.insert("1.0", str(value))
            elif widget_type == 'checkbutton':
                widget.set(bool(value))
            elif widget_type == 'optionmenu':
                if options_map := info.get('options_map'):
                    display_value = next((p['name'] for code, p in options_map.items() if code == value), "")
                    widget.set(display_value)
                else:
                    widget.set(str(value))

                if 'dropdown' in info and (dropdown := info.get('dropdown')):
                    # 确保即使没有可用模型列表，也显示当前配置的值
                    current_model_name = str(value) if value else self._("无")
                    menu = dropdown['menu']
                    menu.delete(0, 'end')
                    menu.add_command(label=current_model_name, command=tk._setit(widget, current_model_name))
                    dropdown.config(state="normal")

        self.logger.info(self._("配置已成功加载并应用到编辑器UI。"))

    def _save_config_from_editor(self):
        """
        从UI控件收集用户输入的值，并保存到配置对象(self.current_config)。
        """
        if not self.current_config or not self.config_path:
            self.ui_manager.show_error_message(self._("错误"), self._("没有加载配置文件，无法保存。"))
            return

        def set_value_by_path(config_obj, path, value):
            """一个健壮的函数，可以将值设置到混合了对象和字典的结构中。"""
            keys = path.split('.')
            target = config_obj
            for key in keys[:-1]:
                if isinstance(target, dict):
                    target = target.get(key)
                else:
                    target = getattr(target, key, None)
                if target is None:
                    return  # 无法找到路径，无法设置

            last_key = keys[-1]
            if isinstance(target, dict):
                target[last_key] = value
            else:
                setattr(target, last_key, value)

        try:
            for path, info in self.editor_widgets.items():
                widget = info['widget']
                widget_type = info['type']
                value = None

                if widget_type in ['entry', 'optionmenu']:
                    value = widget.get()
                elif widget_type == 'text':
                    value = widget.get("1.0", tk.END).strip()
                elif widget_type == 'checkbutton':
                    value = widget.get()

                if 'max_workers' in path:
                    try:
                        value = int(value) if value else 4
                    except (ValueError, TypeError):
                        value = 4

                if ('.http' in path or '.https' in path or '.base_url' in path) and not value:
                    value = None

                if 'options_map' in info and (options_map := info.get('options_map')):
                    value = next((code for code, p in options_map.items() if p['name'] == value),
                                 list(options_map.keys())[0])

                if value is not None:
                    set_value_by_path(self.current_config, path, value)

            if save_config(self.current_config, self.config_path):
                self.ui_manager.show_info_message(self._("保存成功"), self._("配置文件已更新。"))
                self.ui_manager.update_ui_from_config()
            else:
                self.ui_manager.show_error_message(self._("保存失败"), self._("写入文件时发生未知错误。"))
        except Exception as e:
            self.ui_manager.show_error_message(self._("保存错误"),
                                               self._("保存配置时发生错误:\n{}").format(traceback.format_exc()))


    def _create_home_frame(self, parent):
        page = ttkb.Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        title_label = ttkb.Label(page, text=self._(self.title_text_key), font=self.app_title_font)
        title_label.pack(pady=(40, 10))
        self.translatable_widgets[title_label] = self.title_text_key

        path_frame = ttkb.Frame(page)
        path_frame.pack(pady=(10, 20), padx=20, fill="x")
        path_frame.grid_columnconfigure(0, weight=1)

        # 主配置文件路径
        ttkb.Label(path_frame, textvariable=self.config_path_display_var, font=self.app_font).grid(row=0, column=0)

        # 基因组源文件路径
        ttkb.Label(path_frame, textvariable=self.sources_path_display_var, font=self.app_font).grid(row=1, column=0)

        cards_frame = ttkb.Frame(page)
        cards_frame.pack(pady=20, padx=20, fill="x", expand=False)
        cards_frame.grid_columnconfigure((0, 1), weight=1)
        card1 = ttkb.LabelFrame(cards_frame, text=self._("配置文件"), bootstyle="primary")
        card1.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        card1.grid_columnconfigure(0, weight=1)
        self.translatable_widgets[card1] = "配置文件"
        btn1 = ttkb.Button(card1, text=self._("加载配置文件..."), command=self.event_handler.load_config_file,
                           bootstyle="primary")
        btn1.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        self.translatable_widgets[btn1] = "加载配置文件..."
        btn2 = ttkb.Button(card1, text=self._("生成默认配置..."),
                           command=self.event_handler._generate_default_configs_gui, bootstyle="info")
        btn2.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        self.translatable_widgets[btn2] = "生成默认配置..."
        card2 = ttkb.LabelFrame(cards_frame, text=self._("帮助与支持"), bootstyle="primary")
        card2.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        card2.grid_columnconfigure(0, weight=1)
        self.translatable_widgets[card2] = "帮助与支持"
        btn3 = ttkb.Button(card2, text=self._("在线帮助文档"), command=self.event_handler._open_online_help,
                           bootstyle="primary")
        btn3.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        self.translatable_widgets[btn3] = "在线帮助文档"
        btn4 = ttkb.Button(card2, text=self._("关于本软件"), command=self.event_handler._show_about_window,
                           bootstyle="info")
        btn4.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        self.translatable_widgets[btn4] = "关于本软件"
        return page

    def _create_tools_frame(self, parent):
        frame = ttkb.Frame(parent)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        self.tools_nav_frame = ttkb.Frame(frame, padding=(5, 0))
        self.tools_nav_frame.grid(row=0, column=0, sticky="ns")
        self.tools_content_frame = ttkb.Frame(frame, padding=(10, 0))
        self.tools_content_frame.grid(row=0, column=1, sticky='nsew')
        self.tools_content_frame.grid_rowconfigure(0, weight=1)
        self.tools_content_frame.grid_columnconfigure(0, weight=1)
        self.tool_content_pages = {}
        return frame

    def _populate_tools_ui(self):
        """用正确的顺序和完整的映射关系来创建所有工具按钮和页面。"""
        for widget in self.tools_nav_frame.winfo_children(): widget.destroy()
        for widget in self.tools_content_frame.winfo_children(): widget.destroy()

        self.tool_tab_instances.clear()
        self.tool_content_pages = {}
        self.tool_buttons.clear()

        tab_map = {
            "download": DataDownloadTab,
            "annotation": AnnotationTab,
            "sequence_extraction": SequenceExtractionTab,
            "seq_analysis": SeqAnalysisTab,
            "enrichment": EnrichmentTab,
            "genome_identifier": GenomeIdentifierTab,
            "homology": HomologyTab,
            "arabidopsis_conversion": ArabidopsisHomologyConversionTab,
            "locus_conversion": LocusConversionTab,
            "gff_query": GFFQueryTab,
            "quantification": QuantificationTab,
            "blast": BlastTab,
            "ai_assistant": AIAssistantTab,
        }

        for key in self.TOOL_TAB_ORDER:
            if TabClass := tab_map.get(key):
                content_page = ttkb.Frame(self.tools_content_frame)
                instance = TabClass(parent=content_page, app=self, translator=self._)
                self.tool_tab_instances[key] = instance
                self.tool_content_pages[key] = content_page
                content_page.grid(row=0, column=0, sticky='nsew')
                content_page.grid_remove()

                btn_text = self.TAB_TITLE_KEYS.get(key, key)
                btn = ttkb.Button(
                    master=self.tools_nav_frame,
                    text=btn_text,
                    bootstyle="outline-info",
                    command=lambda k=key: self.on_tool_button_select(k)
                )
                btn.pack(fill='x', padx=10, pady=4)
                self.tool_buttons[key] = btn

        if self.TOOL_TAB_ORDER:
            self.on_tool_button_select(self.TOOL_TAB_ORDER[0])

    def on_tool_button_select(self, selected_key: str):
        for key, button in self.tool_buttons.items():
            button.config(bootstyle="info" if key == selected_key else "outline-info")
        self._switch_tool_content_page(selected_key)

    def _switch_tool_content_page(self, key_to_show: str):
        """切换在主内容区显示的工具页面，并确保页面内容被刷新。"""
        for key, page in self.tool_content_pages.items():
            if key == key_to_show:
                page.grid()

                if instance := self.tool_tab_instances.get(key):
                    if hasattr(instance, 'update_from_config'):
                        instance.update_from_config()
                        self.logger.debug(f"Tab '{key}' has been refreshed upon selection.")
            else:
                page.grid_remove()

    def refresh_all_tool_tabs(self):
        """
        遍历所有已创建的工具选项卡实例，并调用它们的 update_from_config 方法。
        这确保了在配置更改后，所有选项卡的数据都是最新的。
        """
        self.logger.info(self._("正在刷新所有工具选项卡以应用新配置..."))
        for key, instance in self.tool_tab_instances.items():
            if hasattr(instance, 'update_from_config'):
                try:
                    # 调用每个选项卡自己的刷新方法
                    instance.update_from_config()
                    self.logger.debug(f"Successfully refreshed tab: {key}")
                except Exception as e:
                    self.logger.error(_("刷新选项卡 {key} 时失败: {}").format(e))

    def _update_wraplength(self, event):
        wraplength = event.width - 20
        if hasattr(self, 'config_warning_label'):
            self.config_warning_label.configure(wraplength=wraplength, justify="left")

    def _create_editor_frame(self, parent):
        page = ttkb.Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        top_frame = ttkb.Frame(page)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_frame.grid_columnconfigure(0, weight=1)

        self.config_warning_label = ttkb.Label(top_frame,
                                               text=self._("!! 警告: 配置文件可能包含敏感信息，请勿轻易分享。"),
                                               font=self.app_font_bold, bootstyle="danger")
        self.config_warning_label.grid(row=0, column=0, sticky="w", padx=5)
        top_frame.bind("<Configure>", self._update_wraplength)

        self.save_editor_button = ttkb.Button(top_frame, text=self._("应用并保存"),
                                              command=self._save_config_from_editor,
                                              bootstyle='success')
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)

        def save_via_shortcut(event=None):
            self.logger.debug(f"快捷键 '{event.keysym}' 触发保存操作。")
            if self.save_editor_button['state'] == 'normal':
                self._save_config_from_editor()
            return "break"

        page.bind_all("<Control-s>", save_via_shortcut)
        page.bind_all("<Return>", save_via_shortcut)

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
            if not self.editor_canvas or not self.editor_canvas.winfo_exists():
                return
            scroll_units = 0
            if event.num == 5 or event.delta < 0:
                scroll_units = 2
            elif event.num == 4 or event.delta > 0:
                scroll_units = -2

            if scroll_units != 0:
                self.editor_canvas.yview_scroll(scroll_units, "units")

            return "break"

        for widget in [self.editor_canvas, self.editor_scroll_frame]:
            widget.bind_all("<MouseWheel>", _on_mousewheel)
            widget.bind_all("<Button-4>", _on_mousewheel)
            widget.bind_all("<Button-5>", _on_mousewheel)

        self.editor_no_config_label = ttkb.Label(page, text=self._("请先从“主页”加载或生成一个配置文件。"),
                                                 font=self.app_subtitle_font, bootstyle="secondary")
        self.editor_no_config_label.grid(row=1, column=0, sticky="nsew", columnspan=2)

        return page

    def _handle_editor_ui_update(self):
        if not self.editor_ui_built: return
        has_config = bool(self.current_config)
        if hasattr(self, 'editor_canvas') and self.editor_canvas and self.editor_canvas.winfo_exists():
            slaves = self.editor_canvas.master.grid_slaves(row=1, column=1)
            if slaves:
                scrollbar = slaves[0]
                if has_config:
                    self.editor_canvas.grid()
                    scrollbar.grid()
                    self.editor_no_config_label.grid_remove()
                    self._apply_config_values_to_editor()
                else:
                    self.editor_canvas.grid_remove()
                    scrollbar.grid_remove()
                    self.editor_no_config_label.grid()
        if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(
            state="normal" if has_config else "disabled")

    def _force_apply_fonts(self):
        """强制将应用内定义的字体应用到所有相关样式，覆盖主题的默认设置。"""
        self.logger.debug("Forcing custom font application to all styles.")
        for style_name in ['TButton', 'TCheckbutton', 'TMenubutton', 'TLabel', 'TEntry', 'Toolbutton',
                           'Labelframe.TLabel']:
            self.style.configure(style_name, font=self.app_font)
        self.style.configure('success.TButton', font=self.app_font_bold)
        self.style.configure('outline.TButton', font=self.app_font)

    def _setup_fonts(self):
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "sans-serif"]
        mono_stack = ["Consolas", "Courier New", "monospace"]
        self.font_family = next((f for f in font_stack if f in tkfont.families()), "sans-serif")
        self.mono_font_family = next((f for f in mono_stack if f in tkfont.families()), "monospace")
        self.logger.info(
            self._("UI font set to: {}, Monospace font to: {}").format(self.font_family, self.mono_font_family))
        self.app_font = tkfont.Font(family=self.font_family, size=12)
        self.app_font_italic = tkfont.Font(family=self.font_family, size=12, slant="italic")
        self.app_font_bold = tkfont.Font(family=self.font_family, size=13, weight="bold")
        self.app_subtitle_font = tkfont.Font(family=self.font_family, size=16, weight="bold")
        self.app_title_font = tkfont.Font(family=self.font_family, size=24, weight="bold")

        self.app_comment_font = tkfont.Font(family=self.font_family, size=10)

        self.app_font_mono = tkfont.Font(family=self.mono_font_family, size=12)
        for style_name in ['TButton', 'TCheckbutton', 'TMenubutton', 'TLabel', 'TEntry', 'Toolbutton',
                           'Labelframe.TLabel']:
            self.style.configure(style_name, font=self.app_font)
        self.style.configure('success.TButton', font=self.app_font_bold)
        self.style.configure('outline.TButton', font=self.app_font)

        self._force_apply_fonts()

    def check_queue_periodic(self):
        try:
            # --- 日志队列批处理 ---
            log_records_batch = []
            # 设定一个合理的上限，比如一次最多处理100条，防止单次UI更新过久
            max_batch_size = 100
            while len(log_records_batch) < max_batch_size:
                try:
                    log_record = self.log_queue.get_nowait()
                    log_records_batch.append(log_record)
                except queue.Empty:
                    # 队列空了，停止获取
                    break

            # 只有在确实有日志需要处理时，才调用UI更新函数
            if log_records_batch:
                self.ui_manager.display_log_message_in_ui(log_records_batch)

            # --- 消息队列处理 ---
            max_messages_to_process = 5
            for _ in range(max_messages_to_process):
                try:
                    msg_type, data = self.message_queue.get_nowait()
                    if handler := self.event_handler.message_handlers.get(msg_type):
                        handler(data) if data is not None else handler()
                except queue.Empty:
                    break
        except Exception as e:
            self.logger.error(f"处理队列时发生错误: {e}")
            self.logger.debug(traceback.format_exc())
        finally:
            self.after(100, self.check_queue_periodic)

    def reconfigure_logging(self, log_level_str: str):
        try:
            # 将字符串级别转换为整数级别，如果无效则默认为 INFO
            new_level = logging.getLevelName(log_level_str.upper())
            if not isinstance(new_level, int):
                new_level = logging.INFO
                self.logger.warning(f"无效的日志级别 '{log_level_str}'，已重置为 INFO。")

            # 移除错误的检查条件，总是更新所有处理器的级别
            root = logging.getLogger()

            for handler in root.handlers:
                handler.setLevel(new_level)

            # 使用 self.logger 记录级别变更，确保这条消息本身不会被即将生效的更高日志级别过滤掉
            self.logger.info(self._("全局日志级别已更新为: {}").format(log_level_str))

        except Exception as e:
            self.logger.error(self._("配置日志级别时出错: {}").format(e))

    def restart_app(self):
        sys.exit(0)

        self.logger.info(_("用户请求重启应用程序。"))
        try:
            # 1. 准备命令列表和工作目录 (这部分逻辑是正确的，无需修改)
            command = []
            working_dir = ""

            if hasattr(sys, '__compiled__'):
                self.logger.info(_("检测到在Nuitka环境中运行。"))
                command = [sys.executable] + sys.argv[1:]
                working_dir = os.path.dirname(sys.executable)
            else:
                self.logger.info(_("检测到在标准Python脚本环境中运行。"))
                command = [sys.executable] + sys.argv
                working_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

            self.logger.info(_("准备重启命令: {}").format(' '.join(command)))
            self.logger.info(_("设置工作目录为: {}").format(working_dir))

            # 2. 准备 Popen 的跨平台参数
            kwargs = {
                'cwd': working_dir,
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.DEVNULL,
            }

            if sys.platform == "win32":
                # 在Windows上，DETACHED_PROCESS 标志提供了额外的独立性保证。
                DETACHED_PROCESS = 0x00000008
                kwargs['creationflags'] = DETACHED_PROCESS

            # 3. 执行重启
            subprocess.Popen(command, **kwargs)

            # 4. 平稳地退出当前实例
            self.logger.info(_("正在关闭当前实例。"))
            self.destroy()

        except Exception as e:
            self.logger.error(_("重启过程中发生错误: {}").format(e))
            if hasattr(self, 'ui_manager'):
                self.ui_manager.show_error_message(_("重启失败"), str(e))
