# 文件路径: ui/gui_app.py

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
from cotton_toolkit.utils.localization import setup_localization
from cotton_toolkit.utils.logger import setup_global_logger
from ui.event_handler import EventHandler
from ui.ui_manager import UIManager

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class CottonToolkitApp(ttkb.Window):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}
    DARK_THEMES = ["darkly", "cyborg", "solar", "superhero", "vapor"]

    @property
    def AI_PROVIDERS(self):
        return {"google": {"name": "Google Gemini"}, "openai": {"name": "OpenAI"},
                "deepseek": {"name": "DeepSeek (深度求索)"}, "qwen": {"name": "Qwen (通义千问)"},
                "siliconflow": {"name": "SiliconFlow (硅基流动)"}, "grok": {"name": "Grok (xAI)"},
                "openai_compatible": {"name": self._("通用OpenAI兼容接口")}}

    TOOL_TAB_ORDER = [
        "download", "annotation", "enrichment", "xlsx_to_csv", "genome_identifier",
        "homology", "locus_conversion", "gff_query", "ai_assistant"
    ]
    TAB_TITLE_KEYS = {
        "download": _("数据下载"), "annotation": _("功能注释"), "enrichment": _("富集分析与绘图"),
        "xlsx_to_csv": _("XLSX转CSV"), "genome_identifier": _("基因组鉴定"), "homology": _("同源转换"),
        "locus_conversion": _("位点转换"), "gff_query": _("GFF查询"), "ai_assistant": _("AI助手"),
    }

    def __init__(self, translator: Callable[[str], str]):
        super().__init__(themename='flatly')  # 立即设置一个默认主题

        self._ = translator
        self.logger = logging.getLogger(__name__)
        self.app_icon_path: Optional[str] = None
        self._patch_all_toplevels()

        self.title_text_key = "Friendly Cotton Genomes Toolkit - FCGT"
        self.title(self._(self.title_text_key))
        self.geometry("1200x750")
        self.minsize(1200, 600)


        # 【核心修改点 1】绑定 <FocusIn> 事件
        # 这个事件在一个更可靠的时刻触发，即当窗口实际获得键盘焦点时。
        self.bind("<FocusIn>", self._on_first_focus, add='+')

        self._setup_fonts()
        # ... (类的其他初始化代码保持不变) ...
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

        self.ui_manager = UIManager(self, translator=self._)
        self.event_handler = EventHandler(self)
        self._create_image_assets()
        setup_global_logger(log_level_str="INFO", log_queue=self.log_queue)

        # UI Manager现在只负责加载设置，而不应用主题
        self.ui_manager.load_settings()
        self.ui_manager.setup_initial_ui()

        self.event_handler.start_app_async_startup()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.event_handler.on_closing)
        self.set_app_icon()

    def _patch_all_toplevels(self):
        """
        通过“猴子补丁”技术，自动为所有新创建的Toplevel窗口（弹窗）
        应用深色标题栏、强制刷新逻辑以及应用图标。
        """
        app_instance = self

        def apply_customizations(toplevel_self):
            # 1. 设置图标
            if app_instance.app_icon_path:
                try:
                    toplevel_self.iconbitmap(app_instance.app_icon_path)
                except tk.TclError:
                    # 在某些系统或特殊窗口上可能失败，静默处理
                    pass

            # 2. 安排刷新任务以适配标题栏
            def _refresh_dialog_task():
                app_instance.configure_title_bar_color(toplevel_self)
                toplevel_self.withdraw()
                toplevel_self.deiconify()

            toplevel_self.after(50, _refresh_dialog_task)

        # --- 为 ttkbootstrap 的 Toplevel 打补丁 ---
        original_ttkb_init = ttkb.Toplevel.__init__

        def new_ttkb_init(toplevel_self, *args, **kwargs):
            original_ttkb_init(toplevel_self, *args, **kwargs)
            apply_customizations(toplevel_self)

        ttkb.Toplevel.__init__ = new_ttkb_init

        # --- 为标准 tkinter 的 Toplevel 打补丁 ---
        original_tk_init = tk.Toplevel.__init__

        def new_tk_init(toplevel_self, *args, **kwargs):
            original_tk_init(toplevel_self, *args, **kwargs)
            apply_customizations(toplevel_self)

        tk.Toplevel.__init__ = new_tk_init

    def configure_title_bar_color(self, window_obj):
        """
        【简化版】仅负责为给定的窗口对象设置标题栏颜色属性。
        """
        if sys.platform != "win32" or windll is None:
            return
        try:
            is_dark = self.style.theme.type == 'dark'
            hwnd = windll.user32.GetParent(window_obj.winfo_id())
            if not hwnd: return

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = c_int(1 if is_dark else 0)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(value), sizeof(value)
            )
        except Exception as e:
            self.logger.warning(f"为窗口 {window_obj} 配置标题栏颜色时出错: {e}")

    def _on_first_focus(self, event):
        """当窗口第一次获得焦点时，执行此操作，确保标题栏刷新。"""
        # 解除绑定，确保这个函数只被调用一次
        self.unbind("<FocusIn>")
        self.logger.info("Window has gained focus for the first time. Applying initial theme.")
        # 从加载的设置中应用主题
        self.ui_manager.apply_initial_theme()

    def apply_theme_and_update_dependencies(self, theme_name: str):
        """
        应用TTK主题，并强制执行一次完整的窗口视觉刷新，以同步原生标题栏。
        """
        try:
            # 1. 应用TTK主题到所有Tkinter控件
            self.style.theme_use(theme_name)

            # 2. 更新所有依赖主题色的内部UI组件
            self._setup_fonts()
            self.default_text_color = self.style.lookup('TLabel', 'foreground')
            if hasattr(self.ui_manager, '_update_log_tag_colors'):
                self.ui_manager._update_log_tag_colors()

            # 3. 安排一次强制刷新
            # after_idle确保此操作在当前所有UI事件处理完后执行，避免冲突
            self.after_idle(self.refresh_window_visuals)

        except Exception as e:
            self.logger.error(f"应用主题并刷新时出错: {e}")

    def refresh_window_visuals(self):
        """
        通过“隐藏再显示”的强制手段，刷新整个窗口的视觉表现。
        这是为了确保Windows原生标题栏能够同步更新。
        """
        self.logger.info("正在强制刷新窗口视觉效果...")

        # a. 先应用标题栏颜色设置
        self.configure_title_bar_color(self)

        # b. 执行“隐藏-显示”操作，这会强制Windows重绘整个窗口框架
        self.withdraw()
        self.deiconify()

    def _configure_dark_title_bar(self, window_obj):
        """根据主应用主题，配置任意窗口对象的标题栏颜色并强制刷新。"""
        if sys.platform != "win32" or windll is None:
            return

        try:
            is_dark = self.style.theme.type == 'dark'
            hwnd = windll.user32.GetParent(window_obj.winfo_id())
            if not hwnd: return

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = c_int(1 if is_dark else 0)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(value), sizeof(value)
            )

            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_FRAMECHANGED = 0x0020
            windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED)

        except Exception as e:
            self.logger.warning(f"Could not configure title bar for {window_obj}: {e}")


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
            self.logger.warning(self._("图片资源未找到: '{}'").format(image_path))
        except Exception as e:
            self.logger.error(self._("获取图片资源 '{}' 路径时发生错误: {}").format(file_name, e))
        return None

    def _create_editor_widgets(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        row_counter = 0

        def get_row():
            nonlocal row_counter
            r = row_counter
            row_counter += 1
            return r

        section_1_title = ttkb.Label(parent, text=f"◇ {self._('通用设置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_1_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_1_title] = "通用设置"

        c1 = ttkb.Frame(parent);
        c1.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
        c1.grid_columnconfigure(1, weight=1)
        lbl1 = ttkb.Label(c1, text=self._("日志级别"));
        lbl1.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl1] = "日志级别"
        self.general_log_level_var = tk.StringVar()
        self.general_log_level_menu = ttkb.OptionMenu(c1, self.general_log_level_var, "INFO",
                                                      *["DEBUG", "INFO", "WARNING", "ERROR"], bootstyle='info-outline')
        self.general_log_level_menu.grid(row=0, column=1, sticky="ew", padx=5)
        tip1 = ttkb.Label(c1, text=self._("设置应用程序的日志详细程度。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip1.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip1] = "设置应用程序的日志详细程度。"

        c2 = ttkb.Frame(parent);
        c2.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c2.grid_columnconfigure(1, weight=1)
        lbl2 = ttkb.Label(c2, text=self._("HTTP代理"));
        lbl2.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl2] = "HTTP代理"
        self.proxy_http_entry = ttkb.Entry(c2);
        self.proxy_http_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip2 = ttkb.Label(c2, text=self._("例如: http://127.0.0.1:7890"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip2.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip2] = "例如: http://127.0.0.1:7890"

        c3 = ttkb.Frame(parent);
        c3.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c3.grid_columnconfigure(1, weight=1)
        lbl3 = ttkb.Label(c3, text=self._("HTTPS代理"));
        lbl3.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl3] = "HTTPS代理"
        self.proxy_https_entry = ttkb.Entry(c3);
        self.proxy_https_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip3 = ttkb.Label(c3, text=self._("例如: https://127.0.0.1:7890"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip3.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip3] = "例如: https://127.0.0.1:7890"

        proxy_button_frame = ttkb.Frame(parent);
        proxy_button_frame.grid(row=get_row(), column=0, sticky="e", padx=5, pady=5)
        self.test_proxy_button = ttkb.Button(proxy_button_frame, text=self._("测试代理连接"),
                                             command=self.event_handler.test_proxy_connection,
                                             bootstyle="primary-outline");
        self.test_proxy_button.pack()
        self.translatable_widgets[self.test_proxy_button] = "测试代理连接"

        section_2_title = ttkb.Label(parent, text=f"◇ {self._('数据下载器配置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_2_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_2_title] = "数据下载器配置"

        c4 = ttkb.Frame(parent);
        c4.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c4.grid_columnconfigure(1, weight=1)
        lbl4 = ttkb.Label(c4, text=self._("基因组源文件"));
        lbl4.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl4] = "基因组源文件"
        self.downloader_sources_file_entry = ttkb.Entry(c4);
        self.downloader_sources_file_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip4 = ttkb.Label(c4, text=self._("定义基因组下载链接的YAML文件。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip4.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip4] = "定义基因组下载链接的YAML文件。"

        c5 = ttkb.Frame(parent);
        c5.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c5.grid_columnconfigure(1, weight=1)
        lbl5 = ttkb.Label(c5, text=self._("下载输出根目录"));
        lbl5.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl5] = "下载输出根目录"
        self.downloader_output_dir_entry = ttkb.Entry(c5);
        self.downloader_output_dir_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip5 = ttkb.Label(c5, text=self._("所有下载文件存放的基准目录。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip5.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip5] = "所有下载文件存放的基准目录。"

        c6 = ttkb.Frame(parent);
        c6.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
        c6.grid_columnconfigure(1, weight=1)
        lbl6 = ttkb.Label(c6, text=self._("强制重新下载"));
        lbl6.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl6] = "强制重新下载"
        self.downloader_force_download_var = tk.BooleanVar()
        self.downloader_force_download_switch = ttkb.Checkbutton(c6, variable=self.downloader_force_download_var,
                                                                 bootstyle="round-toggle");
        self.downloader_force_download_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip6 = ttkb.Label(c6, text=self._("如果文件已存在，是否覆盖。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip6.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip6] = "如果文件已存在，是否覆盖。"

        c7 = ttkb.Frame(parent);
        c7.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c7.grid_columnconfigure(1, weight=1)
        lbl7 = ttkb.Label(c7, text=self._("最大下载线程数"));
        lbl7.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl7] = "最大下载线程数"
        self.downloader_max_workers_entry = ttkb.Entry(c7);
        self.downloader_max_workers_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip7 = ttkb.Label(c7, text=self._("多线程下载时使用的最大线程数。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip7.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip7] = "多线程下载时使用的最大线程数。"

        c8 = ttkb.Frame(parent);
        c8.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
        c8.grid_columnconfigure(1, weight=1)
        lbl8 = ttkb.Label(c8, text=self._("为下载使用代理"));
        lbl8.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl8] = "为下载使用代理"
        self.downloader_use_proxy_var = tk.BooleanVar()
        self.downloader_use_proxy_switch = ttkb.Checkbutton(c8, variable=self.downloader_use_proxy_var,
                                                            bootstyle="round-toggle");
        self.downloader_use_proxy_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip8 = ttkb.Label(c8, text=self._("是否为数据下载启用代理。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip8.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip8] = "是否为数据下载启用代理。"

        section_3_title = ttkb.Label(parent, text=f"◇ {self._('AI 服务配置')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_3_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_3_title] = "AI 服务配置"

        c9 = ttkb.Frame(parent);
        c9.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
        c9.grid_columnconfigure(1, weight=1)
        lbl9 = ttkb.Label(c9, text=self._("默认AI服务商"));
        lbl9.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl9] = "默认AI服务商"
        self.ai_default_provider_var = tk.StringVar()
        provider_names = [p['name'] for p in self.AI_PROVIDERS.values()]
        self.ai_default_provider_menu = ttkb.OptionMenu(c9, self.ai_default_provider_var, provider_names[0],
                                                        *provider_names, bootstyle='info-outline')
        self.ai_default_provider_menu.grid(row=0, column=1, sticky="ew", padx=5)
        tip9 = ttkb.Label(c9, text=self._("选择默认使用的AI模型提供商。"), font=self.app_comment_font,
                          bootstyle="secondary");
        tip9.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip9] = "选择默认使用的AI模型提供商。"

        c10 = ttkb.Frame(parent);
        c10.grid(row=get_row(), column=0, sticky="ew", pady=2, padx=5);
        c10.grid_columnconfigure(1, weight=1)
        lbl10 = ttkb.Label(c10, text=self._("最大并行AI任务数"));
        lbl10.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl10] = "最大并行AI任务数"
        self.batch_ai_max_workers_entry = ttkb.Entry(c10);
        self.batch_ai_max_workers_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        tip10 = ttkb.Label(c10, text=self._("执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"),
                           font=self.app_comment_font, bootstyle="secondary");
        tip10.grid(row=1, column=1, sticky="w", padx=5)
        self.translatable_widgets[tip10] = "执行AI任务时并行处理的最大数量，建议根据CPU核心数和网络情况设置。"

        c11 = ttkb.Frame(parent);
        c11.grid(row=get_row(), column=0, sticky="ew", pady=4, padx=5);
        c11.grid_columnconfigure(1, weight=1)
        lbl11 = ttkb.Label(c11, text=self._("为AI服务使用代理"));
        lbl11.grid(row=0, column=0, sticky="w", padx=(5, 10), pady=2)
        self.translatable_widgets[lbl11] = "为AI服务使用代理"
        self.ai_use_proxy_var = tk.BooleanVar()
        self.ai_use_proxy_switch = ttkb.Checkbutton(c11, variable=self.ai_use_proxy_var, bootstyle="round-toggle");
        self.ai_use_proxy_switch.grid(row=0, column=1, sticky="w", padx=5)
        tip11 = ttkb.Label(c11, text=self._("是否为连接AI模型API启用代理。"), font=self.app_comment_font,
                           bootstyle="secondary");
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
            apikey_entry = ttkb.Entry(card);
            apikey_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_apikey_entry", apikey_entry)

            lbl_model = ttkb.Label(card, text="Model")
            lbl_model.grid(row=1, column=0, sticky="w", padx=10, pady=5)
            self.translatable_widgets[lbl_model] = "Model"
            model_frame = ttkb.Frame(card);
            model_frame.grid(row=1, column=1, sticky="ew", pady=5, padx=5);
            model_frame.grid_columnconfigure(0, weight=1)
            model_var = tk.StringVar(value=self._("点击刷新获取列表"))
            model_dropdown = ttkb.OptionMenu(model_frame, model_var, self._("点击刷新..."), bootstyle="info");
            model_dropdown.configure(state="disabled");
            model_dropdown.grid(row=0, column=0, sticky="ew")
            setattr(self, f"ai_{safe_key}_model_selector", (model_dropdown, model_var))

            button_frame = ttkb.Frame(model_frame);
            button_frame.grid(row=0, column=1, padx=(10, 0))
            btn_refresh = ttkb.Button(button_frame, text=self._("刷新"), width=8,
                                      command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                       use_proxy=False),
                                      bootstyle='outline');
            btn_refresh.pack(side="left")
            self.translatable_widgets[btn_refresh] = "刷新"
            btn_proxy_refresh = ttkb.Button(button_frame, text=self._("代理刷新"), width=10,
                                            command=lambda pk=p_key: self.event_handler._gui_fetch_ai_models(pk,
                                                                                                             use_proxy=True),
                                            bootstyle='info-outline');
            btn_proxy_refresh.pack(side="left", padx=(5, 0))
            self.translatable_widgets[btn_proxy_refresh] = "代理刷新"

            lbl_baseurl = ttkb.Label(card, text="Base URL")
            lbl_baseurl.grid(row=2, column=0, sticky="w", padx=10, pady=5)
            self.translatable_widgets[lbl_baseurl] = "Base URL"
            baseurl_entry = ttkb.Entry(card);
            baseurl_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
            setattr(self, f"ai_{safe_key}_baseurl_entry", baseurl_entry)

        section_4_title = ttkb.Label(parent, text=f"◇ {self._('AI 提示词模板')} ◇", font=self.app_subtitle_font,
                                     bootstyle="primary")
        section_4_title.grid(row=get_row(), column=0, pady=(25, 10), sticky="w", padx=5)
        self.translatable_widgets[section_4_title] = "AI 提示词模板"

        f_trans = ttkb.Frame(parent);
        f_trans.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_trans.grid_columnconfigure(1, weight=1)
        lbl_trans = ttkb.Label(f_trans, text=self._("翻译提示词"));
        lbl_trans.grid(row=0, column=0, sticky="nw", padx=(5, 10))
        self.translatable_widgets[lbl_trans] = "翻译提示词"
        bg_t, fg_t = self.style.lookup('TFrame', 'background'), self.style.lookup('TLabel', 'foreground')
        self.ai_translation_prompt_textbox = tk.Text(f_trans, height=7, font=self.app_font_mono, wrap="word",
                                                     relief="flat", background=bg_t, foreground=fg_t,
                                                     insertbackground=fg_t)
        self.ai_translation_prompt_textbox.grid(row=0, column=1, sticky="ew", padx=5)

        f_ana = ttkb.Frame(parent);
        f_ana.grid(row=get_row(), column=0, sticky="ew", pady=8, padx=5);
        f_ana.grid_columnconfigure(1, weight=1)
        lbl_ana = ttkb.Label(f_ana, text=self._("分析提示词"));
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
                widget.delete("1.0", tk.END);
                widget.insert("1.0", str(value or ""))
            elif isinstance(widget, ttkb.Entry):
                widget.delete(0, tk.END);
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

            if apikey_widget := getattr(self, f"ai_{safe_key}_apikey_entry", None):
                set_val(apikey_widget, p_cfg.api_key)

            if baseurl_widget := getattr(self, f"ai_{safe_key}_baseurl_entry", None):
                set_val(baseurl_widget, p_cfg.base_url)

            if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                _dropdown, var = model_selector
                var.set(p_cfg.model or "")

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
                if max_workers_val <= 0:
                    raise ValueError
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
                if model_selector := getattr(self, f"ai_{safe_key}_model_selector", None):
                    dropdown, var = model_selector
                    p_cfg.model = var.get()

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

        ttkb.Label(page, textvariable=self.config_path_display_var, font=self.app_font, bootstyle="secondary").pack(
            pady=(10, 20))

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
                           command=self.event_handler._generate_default_configs_gui,
                           bootstyle="info")
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
                instance = TabClass(parent=tab_frame, app=self, translator=self._)
                self.tools_notebook.add(tab_frame, text=self.TAB_TITLE_KEYS[key])
                self.tool_tab_instances[key] = instance
        if self.tools_notebook.tabs(): self.tools_notebook.select(0)

    def set_app_icon(self):
        """设置主窗口和所有未来弹窗的图标。"""
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "icon.ico")

            if os.path.exists(icon_path):
                # 【修改】将找到的路径保存到实例属性中
                self.app_icon_path = icon_path
                self.iconbitmap(self.app_icon_path)
            else:
                self.logger.warning(f"应用图标文件未找到: {icon_path}")

        except Exception as e:
            self.logger.warning(f"加载主窗口图标失败: {e}")

    def _update_wraplength(self, event):
        wraplength = event.width - 20
        if hasattr(self, 'config_warning_label'):
            self.config_warning_label.configure(wraplength=wraplength)

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

            if event.delta:
                scroll_units = -2 if event.delta > 0 else 2
                self.editor_canvas.yview_scroll(scroll_units, "units")
            else:
                if event.num == 5:
                    self.editor_canvas.yview_scroll(5, "units")
                elif event.num == 4:
                    self.editor_canvas.yview_scroll(-5, "units")

            return "break"

        def _bind_scroll_to_all(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)

            for child in widget.winfo_children():
                child.bind("<MouseWheel>", _on_mousewheel, add="+")
                child.bind("<Button-4>", _on_mousewheel, add="+")
                child.bind("<Button-5>", _on_mousewheel, add="+")
                _bind_scroll_to_all(child)

        widgets_to_bind = [self.editor_canvas, self.editor_scroll_frame]
        for widget in widgets_to_bind:
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
        self.logger.info(
            self._("UI font set to: {}, Monospace font to: {}").format(self.font_family, self.mono_font_family))
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
            self.logger.critical(self._("处理消息队列时出错: {}").format(e), exc_info=True)
        self.after(100, self.check_queue_periodic)

    def reconfigure_logging(self, log_level_str: str):
        try:
            if isinstance(new_level := logging.getLevelName(log_level_str.upper()), int):
                if (root := logging.getLogger()).getEffectiveLevel() != new_level:
                    root.setLevel(new_level)
                    for handler in root.handlers: handler.setLevel(new_level)
                    self.logger.info(self._("全局日志级别已更新为: {}").format(log_level_str))
        except Exception as e:
            self.logger.error(self._("配置日志级别时出错: {}").format(e))

    def restart_app(self):
        """重启当前应用程序。"""
        self.logger.info("Application restart requested by user.")
        try:
            self.destroy()
        except Exception as e:
            self.logger.error(f"Error during pre-restart cleanup: {e}")

        python = sys.executable
        os.execv(python, [python] + sys.argv)