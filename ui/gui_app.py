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

try:
    from ctypes import windll, byref, sizeof, c_int
except ImportError:
    windll = None

from cotton_toolkit.config.loader import save_config, load_config
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.ui_manager import UIManager, determine_initial_theme
from ui.tabs import (
    AIAssistantTab, DataDownloadTab, AnnotationTab, EnrichmentTab, SequenceExtractionTab,
    GenomeIdentifierTab, GFFQueryTab, HomologyTab, LocusConversionTab, BlastTab, HomologyConversionTab
)

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "en": "English"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    DARK_THEMES = ["darkly", "cyborg", "solar", "superhero", "vapor"]

    @property
    def AI_PROVIDERS(self):
        return {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                "openai_compatible": {"name": self._("通用OpenAI兼容接口")}}

    TOOL_TAB_ORDER = [
        "download", "annotation", "enrichment", "sequence_extraction",
        "genome_identifier", "homology", "arabidopsis_conversion", "locus_conversion", "gff_query",
        "blast", "ai_assistant",
    ]

    @property
    def TAB_TITLE_KEYS(self):
        return {
            "download": _("数据下载"), "annotation": _("功能注释"), "sequence_extraction": _("CDS序列提取"),
            "enrichment": _("富集分析与绘图"),
            "genome_identifier": _("基因组鉴定"), "homology": _("同源转换"),
            "arabidopsis_conversion":_("棉花-拟南芥互转"),
            "locus_conversion": _("位点转换"), "gff_query": _("GFF查询"), "blast": _("本地BLAST"),
            "ai_assistant": _("AI助手"),
        }

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
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()

        self.ui_manager = UIManager(self, translator=self._)
        self.event_handler = EventHandler(self)

        def clear_log_viewer():
            self.ui_manager._clear_log_viewer_ui()

        self.event_handler.clear_log_viewer = clear_log_viewer

        self.apply_theme_and_update_dependencies(initial_theme)

        self.ui_manager.load_settings()
        self.ui_manager.setup_initial_ui()

        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)

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

    def _create_editor_widgets(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        is_dark_theme = self.style.theme.type == 'dark'
        comment_fg_color = "#a0a0a0" if is_dark_theme else "#6c757d"

        def get_row():
            nonlocal row_counter
            r = row_counter
            row_counter += 1
            return r

        section_1_title = ttkb.Label(parent, text=f"◇ {self._('通用设置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_1_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_1_title] = "通用设置"

        c1 = ttkb.Frame(parent)
        c1.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5)
        c1.grid_columnconfigure(1, weight=1)
        lbl1 = ttkb.Label(c1, text=self._("日志级别"))
        lbl1.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl1] = "日志级别"
        self.general_log_level_var = tk.StringVar()
        self.general_log_level_menu = ttkb.OptionMenu(c1, self.general_log_level_var, "INFO",
                                                      *["DEBUG", "INFO", "WARNING", "ERROR"], bootstyle='info-outline')
        self.general_log_level_menu.grid(row=0, column=1, sticky="ew", padx=5)
        tip1 = ttkb.Label(c1, text=self._("设置应用程序的日志详细程度。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip1.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip1] = "设置应用程序的日志详细程度。"

        c2 = ttkb.Frame(parent)
        c2.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c2.grid_columnconfigure(1, weight=1)
        lbl2 = ttkb.Label(c2, text=self._("HTTP代理"))
        lbl2.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl2] = "HTTP代理"
        self.proxy_http_entry = ttkb.Entry(c2)
        self.proxy_http_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip2 = ttkb.Label(c2, text=self._("例如: http://127.0.0.1:7890"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip2.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip2] = "例如: http://127.0.0.1:7890"

        c3 = ttkb.Frame(parent)
        c3.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c3.grid_columnconfigure(1, weight=1)
        lbl3 = ttkb.Label(c3, text=self._("HTTPS代理"))
        lbl3.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl3] = "HTTPS代理"
        self.proxy_https_entry = ttkb.Entry(c3)
        self.proxy_https_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip3 = ttkb.Label(c3, text=self._("例如: https://127.0.0.1:7890"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip3.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip3] = "例如: https://127.0.0.1:7890"

        proxy_button_frame = ttkb.Frame(parent)
        proxy_button_frame.grid(row=get_row(), column=0, sticky="e", padx=5, pady=5)
        self.test_proxy_button = ttkb.Button(proxy_button_frame, text=self._("测试代理连接"),
                                             command=self.event_handler.test_proxy_connection,
                                             bootstyle="primary-outline")
        self.test_proxy_button.pack()
        self.translatable_widgets[self.test_proxy_button] = "测试代理连接"

        section_2_title = ttkb.Label(parent, text=f"◇ {self._('数据下载器配置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_2_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_2_title] = "数据下载器配置"

        c4 = ttkb.Frame(parent)
        c4.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c4.grid_columnconfigure(1, weight=1)
        lbl4 = ttkb.Label(c4, text=self._("基因组源文件"))
        lbl4.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl4] = "基因组源文件"
        self.downloader_sources_file_entry = ttkb.Entry(c4)
        self.downloader_sources_file_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip4 = ttkb.Label(c4, text=self._("定义基因组下载链接的YAML文件。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip4.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip4] = "定义基因组下载链接的YAML文件。"

        c5 = ttkb.Frame(parent)
        c5.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c5.grid_columnconfigure(1, weight=1)
        lbl5 = ttkb.Label(c5, text=self._("下载输出根目录"))
        lbl5.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl5] = "下载输出根目录"
        self.downloader_output_dir_entry = ttkb.Entry(c5)
        self.downloader_output_dir_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip5 = ttkb.Label(c5, text=self._("所有下载文件存放的基准目录。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip5.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip5] = "所有下载文件存放的基准目录。"

        c6 = ttkb.Frame(parent)
        c6.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5)
        c6.grid_columnconfigure(1, weight=1)
        lbl6 = ttkb.Label(c6, text=self._("强制重新下载"))
        lbl6.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl6] = "强制重新下载"
        self.downloader_force_download_var = tk.BooleanVar()
        self.downloader_force_download_switch = ttkb.Checkbutton(c6, variable=self.downloader_force_download_var,
                                                                 bootstyle="round-toggle")
        self.downloader_force_download_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip6 = ttkb.Label(c6, text=self._("如果文件已存在，是否覆盖。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip6.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip6] = "如果文件已存在，是否覆盖。"

        c7 = ttkb.Frame(parent)
        c7.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c7.grid_columnconfigure(1, weight=1)
        lbl7 = ttkb.Label(c7, text=self._("最大下载线程数"))
        lbl7.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl7] = "最大下载线程数"
        self.downloader_max_workers_entry = ttkb.Entry(c7)
        self.downloader_max_workers_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip7 = ttkb.Label(c7, text=self._("多线程下载时使用的最大线程数。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip7.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip7] = "多线程下载时使用的最大线程数。"

        c8 = ttkb.Frame(parent)
        c8.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5)
        c8.grid_columnconfigure(1, weight=1)
        lbl8 = ttkb.Label(c8, text=self._("为下载使用代理"))
        lbl8.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl8] = "为下载使用代理"
        self.downloader_use_proxy_var = tk.BooleanVar()
        self.downloader_use_proxy_switch = ttkb.Checkbutton(c8, variable=self.downloader_use_proxy_var,
                                                            bootstyle="round-toggle")
        self.downloader_use_proxy_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip8 = ttkb.Label(c8, text=self._("是否为数据下载启用代理。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip8.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip8] = "是否为数据下载启用代理。"

        section_3_title = ttkb.Label(parent, text=f"◇ {self._('AI 服务配置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_3_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_3_title] = "AI 服务配置"

        c9 = ttkb.Frame(parent)
        c9.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5)
        c9.grid_columnconfigure(1, weight=1)
        lbl9 = ttkb.Label(c9, text=self._("默认AI服务商"))
        lbl9.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl9] = "默认AI服务商"
        self.ai_default_provider_var = tk.StringVar()
        provider_names = [p['name'] for p in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu = ttkb.OptionMenu(c9, self.ai_default_provider_var, provider_names[0],
                                                        *provider_names, bootstyle='info-outline')
        self.ai_default_provider_menu.grid(row=0, column=1, sticky="ew", padx=5)
        tip9 = ttkb.Label(c9, text=self._("选择默认使用的AI模型提供商。"), font=self.app_comment_font,
                          foreground=comment_fg_color)
        tip9.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip9] = "选择默认使用的AI模型提供商。"

        c10 = ttkb.Frame(parent)
        c10.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5)
        c10.grid_columnconfigure(1, weight=1)
        lbl10 = ttkb.Label(c10, text=self._("最大并行AI任务数"))
        lbl10.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl10] = "最大并行AI任务数"
        self.batch_ai_max_workers_entry = ttkb.Entry(c10)
        self.batch_ai_max_workers_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip10 = ttkb.Label(c10, text=self._("执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"),
                           font=self.app_comment_font, foreground=comment_fg_color)
        tip10.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip10] = "执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"

        c11 = ttkb.Frame(parent)
        c11.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5)
        c11.grid_columnconfigure(1, weight=1)
        lbl11 = ttkb.Label(c11, text=self._("为AI服务使用代理"))
        lbl11.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl11] = "为AI服务使用代理"
        self.ai_use_proxy_var = tk.BooleanVar()
        self.ai_use_proxy_switch = ttkb.Checkbutton(c11, variable=self.ai_use_proxy_var, bootstyle="round-toggle")
        self.ai_use_proxy_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip11 = ttkb.Label(c11, text=self._("是否为连接AI模型API启用代理。"), font=self.app_comment_font,
                           foreground=comment_fg_color)
        tip11.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip11] = "是否为连接AI模型API启用代理。"

        for p_key, p_info in self.AI_PROVIDERS.items():
            card = ttkb.LabelFrame(parent, text=p_info['name'], bootstyle="secondary")
            card.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5)
            card.grid_columnconfigure(1, weight=1)
            safe_key = p_key.replace('-', '_')
            lbl_apikey = ttkb.Label(card, text="API Key")
            lbl_apikey.grid(row=0, column=0, sticky="w", padx=10, pady=5)
            self.translatable_widgets[lbl_apikey] = "API Key"
            apikey_entry = ttkb.Entry(card)
            apikey_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)
            lbl_model = ttkb.Label(card, text="Model")
            lbl_model.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            self.translatable_widgets[lbl_model] = "Model"
            model_frame = ttkb.Frame(card)
            model_frame.grid(row=1, column=1, sticky="ew", pady=5, padx=5)
            model_frame.grid_columnconfigure(0, weight=1)
            model_var = tk.StringVar(value=self._("点击刷新获取列表"))
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, self._("点击刷新..."), bootstyle="info")
            model_dropdown.configure(state="disabled")
            model_dropdown.grid(row=0, column=0, sticky="ew")
            setattr(self, f"ai_{safe_key}_model_selector", (model_dropdown, model_var))
            button_frame = ttkb.Frame(model_frame)
            button_frame.grid(row=0, column=1, padx=(10, 0))
            btn_refresh = ttkb.Button(button_frame, text=self._("刷新"), width=8,
                                      command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                       use_proxy=False),
                                      bootstyle='outline')
            btn_refresh.pack(side="left")
            self.translatable_widgets[btn_refresh] = "刷新"
            btn_proxy_refresh = ttkb.Button(button_frame, text=self._("代理刷新"), width=10,
                                            command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                             use_proxy=True),
                                            bootstyle='info-outline')
            btn_proxy_refresh.pack(side="left", padx=(5, 0))
            self.translatable_widgets[btn_proxy_refresh] = "代理刷新"
            lbl_baseurl = ttkb.Label(card, text="Base URL")
            lbl_baseurl.grid(row=2, column=0, sticky="w", padx=10, pady=5)
            self.translatable_widgets[lbl_baseurl] = "Base URL"
            baseurl_entry = ttkb.Entry(card)
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        section_4_title = ttkb.Label(parent, text=f"◇ {self._('AI 提示词模板')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_4_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_4_title] = "AI 提示词模板"

        f_trans = ttkb.Frame(parent)
        f_trans.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5)
        f_trans.grid_columnconfigure(1, weight=1)
        lbl_trans = ttkb.Label(f_trans, text=self._("翻译提示词"))
        lbl_trans.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.translatable_widgets[lbl_trans] = "翻译提示词"
        bg_t, fg_t = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        self.ai_translation_prompt_textbox = tk.Text(f_trans, height=7, font=self.app_font_mono, wrap="word",
                                                     relief="flat", background=bg_t, foreground=fg_t,
                                                     insertbackground=fg_t)
        self.ai_translation_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

        f_ana = ttkb.Frame(parent)
        f_ana.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5)
        f_ana.grid_columnconfigure(1, weight=1)
        lbl_ana = ttkb.Label(f_ana, text=self._("分析提示词"))
        lbl_ana.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.translatable_widgets[lbl_ana] = "分析提示词"
        self.ai_analysis_prompt_textbox = tk.Text(f_ana, height=7, font=self.app_font_mono, wrap="word", relief="flat",
                                                  background=bg_t, foreground=fg_t, insertbackground=fg_t)
        self.ai_analysis_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

    def _apply_config_values_to_editor(self):
        if not self.current_config or not self.editor_ui_built: return
        cfg = self.current_config

        def set_val(widget, value):
            if not widget: return
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", str(value or ""))
            elif isinstance(widget, ttkb.Entry):
                widget.delete(0, tk.END)
                widget.insert(0, str(value or ""))

        self.general_log_level_var.set(cfg.log_level)
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
            if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry",
                                        None): set_val(apikey_widget, p_cfg.api_key)
            if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry",
                                         None): set_val(baseurl_widget, p_cfg.base_url)
            if model_selector := getattr(self, f"ai_{safe_key}_model_selector",
                                         None): _dropdown, var = model_selector; var.set(p_cfg.model or "")
        set_val(self.ai_translation_prompt_textbox, cfg.ai_prompts.translation_prompt)
        set_val(self.ai_analysis_prompt_textbox, cfg.ai_prompts.analysis_prompt)
        self.logger.info(self._("配置已应用到编辑器UI。"))

    def _save_config_from_editor(self):
        if not self.current_config or not self.config_path:
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
                if max_workers_val <= 0: raise ValueError
                cfg.batch_ai_processor.max_workers = max_workers_val
            except (ValueError, TypeError):
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
                if model_selector := getattr(self, f"ai_{safe_key}_model_selector",
                                             None): dropdown, var = model_selector; p_cfg.model = var.get()
            cfg.ai_prompts.translation_prompt = self.ai_translation_prompt_textbox.get("1.0", tk.END).strip()
            cfg.ai_prompts.analysis_prompt = self.ai_analysis_prompt_textbox.get("1.0", tk.END).strip()
            if save_config(cfg, self.config_path):
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
        ttkb.Label(page, textvariable=self.config_path_display_var, font=self.app_font).pack(pady=(10, 20))
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
            "enrichment": EnrichmentTab,
            "genome_identifier": GenomeIdentifierTab,
            "homology": HomologyTab,
            "arabidopsis_conversion":HomologyConversionTab,
            "locus_conversion": LocusConversionTab,
            "gff_query": GFFQueryTab,
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
            max_log_messages_to_process = 10
            for _ in range(max_log_messages_to_process):
                try:
                    # 从日志队列中获取完整的 LogRecord 对象
                    log_record = self.log_queue.get_nowait()
                    try:
                        self.ui_manager.display_log_message_in_ui(log_record)
                    except Exception as e:
                        # 修改: 将print替换为logger.error
                        self.logger.error(_("GUI日志处理时发生异常: {}").format(e))
                        self.logger.debug(traceback.format_exc())

                except queue.Empty:
                    break

            max_messages_to_process = 5
            for _ in range(max_messages_to_process):
                try:
                    msg_type, data = self.message_queue.get_nowait()
                    if handler := self.event_handler.message_handlers.get(msg_type):
                        handler(data) if data is not None else handler()
                except queue.Empty:
                    break
        except Exception as e:
            # 修改: 将print替换为logger.error
            self.logger.error(f"处理消息队列时出错: {e}")
            self.logger.debug(traceback.format_exc())

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
        self.logger.info(_("Application restart requested by user."))
        try:
            self.destroy()
        except Exception as e:
            self.logger.error(_("Error during pre-restart cleanup: {}").format(e))
        python = sys.executable
        os.execv(python, [python] + sys.argv)
