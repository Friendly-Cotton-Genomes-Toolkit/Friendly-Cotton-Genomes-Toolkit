# gui_app.py

import copy
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import traceback
import webbrowser
from queue import Queue
from tkinter import filedialog, font as tkfont
import tkinter as tk
from typing import Callable, Dict, Optional, Any, Tuple # 确保 Tuple 被导入

import customtkinter as ctk
import pandas as pd
import yaml
from PIL import Image

# --- 【核心修改】修正导入并移除备用代码逻辑 ---
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.tools_pipeline import run_functional_annotation, run_ai_task, AIWrapper
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.core.downloader import download_genome_data
# 从 pipelines.py 导入所有需要的函数
from cotton_toolkit.pipelines import (
    integrate_bsa_with_hvg,
    run_gff_gene_lookup_standalone,
    run_homology_map_standalone  # 导入正确的、统一的函数
)
from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text
from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL

print("INFO: gui_app.py - All modules imported.")


# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #


logger = logging.getLogger("cotton_toolkit.gui")


def identify_genome_from_gene_ids(
        gene_ids: list[str],
        genome_sources: dict[str, Any],
        status_callback: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    通过基因ID列表识别最可能的基因组版本。
    【已增强】增加详细的匹配分数日志，并能检测和警告混合基因组输入。
    """
    if not gene_ids or not genome_sources:
        return None

    log = status_callback if status_callback else print

    gene_ids_to_check = [
        gid for gid in gene_ids
        if gid and not gid.lower().startswith(('scaffold', 'unknown', 'chr'))
    ]

    if not gene_ids_to_check:
        log("DEBUG: 过滤后没有用于识别的有效基因ID。", "DEBUG")
        return None

    scores = {}
    total_valid_ids = len(gene_ids_to_check)

    # 1. 计算每个基因组的匹配分数
    for assembly_id, source_info in genome_sources.items():
        # 兼容处理字典和对象
        if isinstance(source_info, dict):
            regex_pattern = source_info.get('gene_id_regex')
        else:
            regex_pattern = getattr(source_info, 'gene_id_regex', None)

        if not regex_pattern:
            continue

        try:
            # 使用 re.IGNORECASE 使匹配不区分大小写，增加灵活性
            regex = re.compile(regex_pattern, re.IGNORECASE)
            match_count = sum(1 for gene_id in gene_ids_to_check if regex.match(gene_id))

            if match_count > 0:
                score = (match_count / total_valid_ids) * 100
                scores[assembly_id] = score
        except re.error as e:
            log(f"警告: 基因组 '{assembly_id}' 的正则表达式无效: {e}", "WARNING")
            continue

    if not scores:
        log("INFO: 无法根据输入的基因ID可靠地自动识别基因组 (没有任何基因组的正则表达式匹配到输入ID)。")
        return None

    # 2. 对分数进行排序和分析
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    # 【新功能】打印详细的诊断日志
    log("DEBUG: 基因组自动识别诊断分数:", "DEBUG")
    for assembly_id, score in sorted_scores:
        log(f"  - {assembly_id}: {score:.2f}%", "DEBUG")

    best_match_id, highest_score = sorted_scores[0]

    # 3. 【新功能】检查是否存在混合输入
    # 找出所有匹配度超过10%的“显著匹配”项
    significant_matches = [s for s in sorted_scores if s[1] > 10.0]
    if len(significant_matches) > 1:
        # 如果存在多于一个显著匹配项，则发出警告
        top_matches_str = ", ".join([f"{asm_id} ({score:.1f}%)" for asm_id, score in significant_matches[:3]])
        log(f"警告: 检测到混合的基因组ID输入。可能性较高的基因组包括: {top_matches_str}", "WARNING")

    # 4. 判断最终结果 (降低识别阈值至50%)
    if highest_score > 50:
        log(f"INFO: 自动识别基因为 '{best_match_id}'，置信度: {highest_score:.2f}%.")
        return best_match_id
    else:
        log("INFO: 无法根据输入的基因ID可靠地自动识别基因组 (最高匹配度未超过50%阈值)。")
        return None


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}

    # --- AI服务商及其元数据 ---
    AI_PROVIDERS = {
        "google": {"name": "Google Gemini"},
        "openai": {"name": "OpenAI"},
        "deepseek": {"name": "DeepSeek (深度求索)"},
        "qwen": {"name": "Qwen (通义千问)"},
        "siliconflow": {"name": "SiliconFlow (硅基流动)"},
        "grok": {"name": "Grok (xAI)"},  # <--- 在此添加
        "openai_compatible": {"name": _("通用OpenAI兼容接口")}
    }

    def __init__(self):
        super().__init__()

        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1000x700")
        self.minsize(1000, 700)

        # --- 【第1步】初始化所有变量 ---
        self.log_queue = queue.Queue()
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.ui_settings: Dict[str, Any] = {}
        self.message_queue: Queue = Queue()
        self.about_window: Optional[ctk.CTkToplevel] = None
        self.translatable_widgets: Dict[ctk.CTkBaseClass, Any] = {}
        self.active_task_name: Optional[str] = None
        self.log_viewer_visible: bool = False
        self.error_dialog_lock: threading.Lock = threading.Lock()
        self.tool_tab_frames: Dict[str, ctk.CTkFrame] = {}
        self.tool_tab_ui_loaded: Dict[str, bool] = {}

        # 定义UI中使用的占位符文本
        self.placeholder_genes_homology_key = "placeholder_genes_homology"
        self.placeholder_genes_gff_key = "placeholder_genes_gff"
        self.placeholder_region_gff_key = "placeholder_gff_region"  # <--- 这个键名保持不变

        self.placeholders = {
            self.placeholder_genes_homology_key: _(
                "输入或粘贴基因ID，每行一个或用逗号分隔。\n例如:\nGh_A01G0001\nGh_A01G0002,Gh_A01G0003"
            ),
            self.placeholder_genes_gff_key: _(
                "输入或粘贴基因ID，每行一个或用逗号分隔。\n例如:\nGh_D05G1268\nCOTTON_D_gene_10014361"
            ),
            # --- 【修改点】更新这里的提示文字 ---
            self.placeholder_region_gff_key: _("例如: A03:1000-2000"),
        }


        # --- 关键修改：定义固定的、程序化的选项卡键和顺序 ---
        self.TAB_TITLE_KEYS = {
            "download": "数据下载",
            "homology": "基因组转换",
            "locus_conversion": "位点转换",
            "gff_query": "基因位点查询",
            "annotation": "功能注释",
            "ai_assistant": "AI 助手",
            "genome_identifier": "基因组类别鉴定",
            "xlsx_to_csv": "XLSX转CSV"
        }
        # 这个列表保证了选项卡的显示顺序是固定的
        self.TOOL_TAB_ORDER = ["download", "homology", "locus_conversion", "gff_query", "annotation", "ai_assistant",
                               "genome_identifier", "xlsx_to_csv"]

        self.editor_ui_loaded: bool = False

        self.cancel_model_fetch_event: threading.Event = threading.Event()
        self.progress_dialog: Optional[ctk.CTkToplevel] = None
        self.progress_dialog_text_var: Optional[tk.StringVar] = None
        self.progress_dialog_bar: Optional[ctk.CTkProgressBar] = None

        self.excel_sheet_cache = {}

        self.placeholder_genes_homology_key: str = "例如:\nGhir.A01G000100\nGhir.A01G000200\n(每行一个基因ID，或逗号分隔)"
        self.placeholder_genes_gff_key: str = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(每行一个基因ID，与下方区域查询二选一)"

        self.DOWNLOAD_TASK_KEY = "download"
        self.INTEGRATE_TASK_KEY = "integrate"
        self.HOMOLOGY_MAP_TASK_KEY = "homology_map"
        self.GFF_QUERY_TASK_KEY = "gff_query"

        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.ai_task_type_var = tk.StringVar(value=_("翻译"))
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=False)
        self.kegg_path_anno_var = tk.BooleanVar(value=False)
        self.selected_bsa_assembly = tk.StringVar()
        self.selected_hvg_assembly = tk.StringVar()
        self.selected_bsa_sheet = tk.StringVar()
        self.selected_hvg_sheet = tk.StringVar()
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.selected_gff_query_assembly = tk.StringVar()
        self.download_force_checkbox_var = tk.BooleanVar()
        self.download_genome_vars: Dict[str, tk.BooleanVar] = {}
        self.download_proxy_var = tk.BooleanVar(value=False)
        self.ai_proxy_var = tk.BooleanVar(value=False)
        self.selected_locus_source_assembly = tk.StringVar()
        self.selected_locus_target_assembly = tk.StringVar()
        self.selected_annotation_assembly = tk.StringVar()

        self.homology_map_s2b_file_path_var = tk.StringVar(value=_("根据基因组自动识别"))
        self.homology_map_b2t_file_path_var = tk.StringVar(value=_("根据基因组自动识别"))
        self.locus_conversion_s2b_file_path_var = tk.StringVar(value=_("根据基因组自动识别"))
        self.locus_conversion_b2t_file_path_var = tk.StringVar(value=_("根据基因组自动识别"))

        self.homology_map_gene_input_widget = None
        self.locus_conversion_gene_input_widget = None
        self.gff_query_gene_input_widget = None
        self.annotation_gene_input_widget = None
        self.identifier_genes_textbox = None
        self.identifier_result_label = None

        self.genome_sources_data: Optional[Dict[str, Any]] = None

        self._setup_fonts()

        self.secondary_text_color = ("#495057", "#999999")
        self.placeholder_color = ("#868e96", "#5c5c5c")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]
        try:
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        except Exception:
            self.default_label_text_color = ("#000000", "#FFFFFF")

        self.logo_image = self._load_image_resource("logo.png", (48, 48))
        self.home_icon = self._load_image_resource("home.png")
        self.integrate_icon = self._load_image_resource("integrate.png")
        self.tools_icon = self._load_image_resource("tools.png")
        self.settings_icon = self._load_image_resource("settings.png")
        self.folder_icon = self._load_image_resource("folder.png")
        self.new_file_icon = self._load_image_resource("new-file.png")
        self.help_icon = self._load_image_resource("help.png")
        self.info_icon = self._load_image_resource("info.png")

        self._load_ui_settings()
        self._create_layout()
        self._init_pages_and_final_setup()
        self._start_app_async_startup()

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

    # 在 CottonToolkitApp class 内部
    def _fetch_ai_models(self, provider_key: str):
        """
        直接从静态UI输入框获取API Key和URL来刷新模型列表。
        【已修复】现在会检查AI助手的代理开关。
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
        if hasattr(self, 'ai_proxy_var') and self.ai_proxy_var.get():
            # 仅在开关打开时才读取代理地址
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
        self._show_progress_dialog(
            title=_("获取模型列表"),
            message=_("正在从 {} 获取模型列表，请稍候...").format(
                self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)),
            on_cancel=lambda: self.cancel_model_fetch_event.set()
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


    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        """显示一个模态的进度弹窗，包含进度条和取消按钮。"""
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.destroy()  # 销毁任何已存在的弹窗，避免重复

        self.progress_dialog = ctk.CTkToplevel(self)
        self.progress_dialog.title(title)
        self.progress_dialog.transient(self)  # 使其模态化，阻止与主窗口交互
        self.progress_dialog.grab_set()  # 捕获焦点
        self.progress_dialog.resizable(False, False)
        self.progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁用关闭按钮，强制通过代码控制

        main_frame = ctk.CTkFrame(self.progress_dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.progress_dialog_text_var = tk.StringVar(value=message)
        ctk.CTkLabel(main_frame, textvariable=self.progress_dialog_text_var,
                     font=self.app_font, wraplength=300, justify="center").pack(pady=10, padx=10)

        self.progress_dialog_bar = ctk.CTkProgressBar(main_frame, width=250, mode="indeterminate")
        self.progress_dialog_bar.pack(pady=10)
        self.progress_dialog_bar.start()  # 启动不确定模式动画

        if on_cancel:  # 如果提供了取消回调函数，则显示取消按钮
            cancel_button = ctk.CTkButton(main_frame, text=_("强制停止"), command=on_cancel, font=self.app_font)
            cancel_button.pack(pady=(10, 0))

        # 居中弹窗
        self.progress_dialog.update_idletasks()  # 强制更新以获取实际尺寸
        x = self.winfo_x() + (self.winfo_width() // 2) - (self.progress_dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (self.progress_dialog.winfo_height() // 2)
        self.progress_dialog.geometry(f"+{x}+{y}")
        self.progress_dialog.deiconify()  # 显示弹窗

    def _hide_progress_dialog(self):
        """
        隐藏并销毁进度弹窗。
        确保在销毁前释放焦点，并立即清空引用。
        """
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            try:
                self.progress_dialog.grab_release() # 确保释放焦点
                self.progress_dialog.destroy()     # 直接销毁，不延迟
            except tk.TclError as e:
                # 如果窗口已经因为某种原因被销毁，捕获 TclError
                print(f"DEBUG: TclError during progress_dialog destruction/release: {e}")
            finally:
                # 无论销毁是否成功，立即清空引用，防止后续代码误用
                self.progress_dialog = None
                self.progress_dialog_text_var = None
                self.progress_dialog_bar = None

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
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(side="top", fill="both", expand=True)
        self.top_frame.grid_columnconfigure(1, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1)
        self._create_navigation_frame(parent=self.top_frame)
        self._create_main_content_area(parent=self.top_frame)

        # gui_app.py

    def _init_pages_and_final_setup(self):
        # 在日志中输出当前工作目录，以便用户了解相对路径的基准
        self._log_to_viewer(f"{_('当前工作目录:')} {os.getcwd()}")

        # 1. 创建所有主内容区域的 Frame 并赋值给 self 属性
        self.home_frame = self._create_home_frame(self.main_content_frame)
        self.editor_frame = self._create_editor_frame(self.main_content_frame)
        self.integrate_frame = self._create_integrate_frame(self.main_content_frame)
        self.tools_frame = self._create_tools_frame(self.main_content_frame)

        # 2. 同步填充所有工具选项卡的内容 (不再懒加载)
        self._populate_tools_notebook()

        # 3. 【修改】调用新的主控方法来处理编辑器UI
        self._handle_editor_ui_update()

        # 4. 设置初始显示的页面 (例如 "home")
        self.select_frame_by_name("home")

        # 5. 更新UI语言和按钮状态 (这些方法现在可以安全地调用，因为所有基础UI元素都已创建)
        self.update_language_ui()
        self._update_button_states()

        # 6. 启动消息队列的周期性检查 (确保主线程能够处理来自后台的消息)
        self.check_queue_periodic()

        # 7. 设置窗口关闭协议和应用程序图标
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_app_icon()

    def _start_app_async_startup(self):
        """
        启动应用的异步加载流程。
        """

        # 启动一个专门用于加载的后台线程
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """
        在后台执行所有耗时的加载操作，完成后将结果放入消息队列。
        """

        try:
            # 1. 加载主配置文件
            default_config_path = "config.yml"
            loaded_config = None
            if os.path.exists(default_config_path):
                # load_config 内部会处理版本不兼容等错误并抛出异常
                loaded_config = load_config(os.path.abspath(default_config_path))

            # 2. 如果主配置加载成功，则加载基因组源数据
            genome_sources = None
            if loaded_config:
                genome_sources = get_genome_data_sources(loaded_config)

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
    def _create_editor_frame(self, parent):
        """
        创建配置编辑器的主框架，只包含布局和按钮，不包含具体内容。
        """
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)  # 第1行用于滚动框架

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

        self.editor_scroll_frame = ctk.CTkScrollableFrame(page)
        self.editor_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
        self._bind_mouse_wheel_to_scrollable(self.editor_scroll_frame)

        # --- 新增：为配置编辑器框架绑定 Ctrl+S 快捷键 ---
        # '<Control-s>' 或 '<Control-S>' 都是 macOS 和 Windows 上的 Ctrl+S
        # 使用 lambda 函数来调用 _save_config_from_editor
        page.bind('<Control-s>', lambda event: self._save_config_from_editor())
        page.bind('<Control-S>', lambda event: self._save_config_from_editor())  # 兼容大写S，虽然通常小写就够了

        # 确保滚动框架内的控件也能触发这个绑定，需要将绑定传递到内部控件
        # 注意：这可能会有点复杂，因为 CustomTkinter 的事件传递有时不完全像标准 Tkinter。
        # 最稳妥的方式是对所有相关的输入控件（Entry, Textbox）也绑定这个快捷键。
        # 但我们先从 top-level 的 frame 绑定开始，看效果。
        # 如果需要更全面的覆盖，可能需要遍历 editor_scroll_frame 的所有子控件并绑定。
        # 对于可滚动框架内的实际输入控件，通常最好直接绑定到它们上面。
        # 这里我们先只绑定到 'page' 和 'editor_scroll_frame' 自身。
        self.editor_scroll_frame.bind('<Control-s>', lambda event: self._save_config_from_editor())
        self.editor_scroll_frame.bind('<Control-S>', lambda event: self._save_config_from_editor())

        return page

    def _get_settings_path(self):
        """获取UI设置文件的路径"""
        # 将设置文件保存在程序根目录，方便用户查找和管理
        return "ui_settings.json"

    def _load_ui_settings(self):
        """加载UI设置，如果文件不存在则使用默认值"""
        settings_path = self._get_settings_path()
        # 默认值
        defaults = {"language": "zh-hans", "appearance_mode": "System"}

        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self.ui_settings = json.load(f)
            else:
                self.ui_settings = defaults
        except (json.JSONDecodeError, IOError):
            # 如果文件损坏或无法读取，也使用默认值
            self.ui_settings = defaults

        # 仅应用主题，不设置变量，变量的设置统一由 update_language_ui 管理
        ctk.set_appearance_mode(self.ui_settings.get("appearance_mode", "System"))

    def _save_ui_settings(self):
        """保存当前的UI设置到文件"""
        settings_path = self._get_settings_path()
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.ui_settings, f, indent=4)
            self._log_to_viewer(_("界面设置已保存。"))
        except IOError as e:
            self._log_to_viewer(f"{_('错误: 无法保存界面设置:')} {e}", "ERROR")

    def _show_custom_dialog(self, title, message, buttons, icon_type=None):
        # 1. 创建窗口并立即隐藏，避免闪烁
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()

        # 2. 设置窗口基础属性
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)

        result = [None]

        # 3. 创建并打包所有内部控件 (这部分代码不变)
        main_frame = ctk.CTkFrame(dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(padx=10, pady=10, fill="both", expand=True)
        icon_text = ""
        if icon_type == "error":
            icon_text = "❌"
        elif icon_type == "warning":
            icon_text = "⚠️"
        elif icon_type == "question":
            icon_text = "❓"
        elif icon_type == "info":
            icon_text = "ℹ️"
        if icon_text:
            ctk.CTkLabel(content_frame, text=icon_text, font=("Segoe UI Emoji", 26)).pack(pady=(10, 10))
        ctk.CTkLabel(content_frame, text=message, font=self.app_font, wraplength=400, justify="center").pack(
            pady=(0, 20), padx=10, fill="x")
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 10), anchor="center")

        def on_button_click(button_text):
            result[0] = button_text
            # 在销毁窗口前，先释放焦点捕获
            dialog.grab_release()
            dialog.destroy()

        for i, button_text in enumerate(buttons):
            is_primary = (i == 0 and len(buttons) > 1 and button_text in [_("确定"), _("Yes")]) or len(buttons) == 1
            btn = ctk.CTkButton(button_frame, text=button_text, command=lambda bt=button_text: on_button_click(bt),
                                font=self.app_font)
            if not is_primary:
                btn.configure(fg_color="transparent", border_width=1,
                              border_color=ctk.ThemeManager.theme["CTkButton"]["border_color"])
            btn.pack(side="left" if len(buttons) > 1 else "top", padx=10)

        # 4. 强制更新以计算窗口的最终所需尺寸
        dialog.update_idletasks()

        # 5. 计算并设置屏幕居中位置
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 6. 在窗口可见之前设置图标
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 设置对话框图标失败: {e}")

        # 7. 设置关闭协议
        dialog.protocol("WM_DELETE_WINDOW", lambda: on_button_click(buttons[-1] if buttons else None))

        # 8. 一切就绪后，显示窗口
        dialog.deiconify()

        # 9. 捕获焦点并等待
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0]

    def _load_image_resource(self, file_name, size=(24, 24)):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath("./assets")
            image_path = os.path.join(base_path, file_name)
            if os.path.exists(image_path):
                return ctk.CTkImage(Image.open(image_path), size=size)
        except Exception as e:
            print(f"警告: 无法加载图片资源 '{file_name}': {e}")
        return None

    def _create_navigation_frame(self, parent):
        self.navigation_frame = ctk.CTkFrame(parent, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(5, weight=1)  # 调整权重行

        nav_header_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        nav_logo_label = ctk.CTkLabel(nav_header_frame, text="", image=self.logo_image)
        nav_logo_label.pack(pady=(0, 10))

        self.nav_title_label = ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold"))
        self.nav_title_label.pack()

        # --- 【顺序和新增按钮修改】 ---
        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=self.home_icon, font=self.app_font_bold,
                                         command=lambda: self.select_frame_by_name("home"))
        self.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # 配置编辑器按钮
        self.editor_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                           text=_("配置编辑器"), fg_color="transparent",
                                           text_color=("gray10", "gray90"),
                                           anchor="w", image=self.settings_icon, font=self.app_font_bold,
                                           command=lambda: self.select_frame_by_name("editor"))
        self.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.integrate_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                              text=_("联合分析"), fg_color="transparent",
                                              text_color=("gray10", "gray90"), anchor="w", image=self.integrate_icon,
                                              font=self.app_font_bold,
                                              command=lambda: self.select_frame_by_name("integrate"))
        self.integrate_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)  # 行号+1

        self.tools_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=self.tools_icon, font=self.app_font_bold,
                                          command=lambda: self.select_frame_by_name("tools"))
        self.tools_button.grid(row=4, column=0, sticky="ew", padx=10, pady=5)  # 行号+1
        # --- 修改结束 ---

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

        # 创建一个笔记本（tabview）用于工具页面
        # 移除 values 参数，因为 CTkTabview 的构造函数不支持
        self.tools_notebook = ctk.CTkTabview(self.main_content_frame, command=self._on_tab_change)
        self.tools_notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def select_frame_by_name(self, name):
        # 设置按钮高亮
        self.home_button.configure(fg_color=self.home_button.cget("hover_color") if name == "home" else "transparent")
        self.editor_button.configure(
            fg_color=self.editor_button.cget("hover_color") if name == "editor" else "transparent")
        self.integrate_button.configure(
            fg_color=self.integrate_button.cget("hover_color") if name == "integrate" else "transparent")
        self.tools_button.configure(
            fg_color=self.tools_button.cget("hover_color") if name == "tools" else "transparent")

        # 隐藏所有页面
        self.home_frame.grid_forget()
        self.editor_frame.grid_forget()
        self.integrate_frame.grid_forget()
        self.tools_frame.grid_forget()

        # 根据名称显示对应的页面
        if name == "home":
            self.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "editor":
            self.editor_frame.grid(row=0, column=0, sticky="nsew")
            # 【修改】调用新的主控方法，它会智能判断是否需要创建UI
            self._handle_editor_ui_update()
        elif name == "integrate":
            self.integrate_frame.grid(row=0, column=0, sticky="nsew")
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
            if tooltip:
                tooltip_label = ctk.CTkLabel(row_frame, text=tooltip, font=self.app_comment_font,
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

            apikey_entry = create_entry_row(card, "  " + _("API Key"), "")
            model_selector = create_model_selector_row(card, "  " + _("模型"), _("要使用的模型名称。"), p_key)
            baseurl_entry = create_entry_row(card, "  " + _("Base URL"), "")

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

    # ==================== 请将以下完整方法添加到您的 App 类中 ====================

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

    def _create_integrate_frame(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # 标题和描述
        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.pack(pady=(20, 15), padx=30, fill="x")
        ctk.CTkLabel(title_frame, text=_("联合分析"), font=self.app_title_font).pack()
        ctk.CTkLabel(title_frame, text=_("结合BSA定位区间与高变异基因(HVG)，筛选候选基因，为精细定位提供依据。"),
                     font=self.app_font, text_color=self.secondary_text_color, wraplength=600).pack(pady=(5, 0))

        # --- 卡片1: 输入文件 ---
        input_card = ctk.CTkFrame(frame)
        input_card.pack(fill="x", padx=30, pady=10)
        input_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(input_card, text=_("第一步: 选择包含BSA和HVG数据的Excel文件"), font=self.app_font_bold).grid(row=0,
                                                                                                                  column=0,
                                                                                                                  columnspan=3,
                                                                                                                  padx=15,
                                                                                                                  pady=15,
                                                                                                                  sticky="w")
        excel_path_label = ctk.CTkLabel(input_card, text=_("Excel文件路径:"), font=self.app_font)
        excel_path_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_card, font=self.app_font, height=35,
                                               placeholder_text=_("点击“浏览”选择文件，或从配置加载"))
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 15), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_card, text=_("BSA数据工作表:"), font=self.app_font)
        bsa_sheet_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 15), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_card, text=_("HVG数据工作表:"), font=self.app_font)
        hvg_sheet_label.grid(row=3, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_hvg_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_hvg_sheet_dropdown.grid(row=3, column=1, columnspan=2, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片2: 基因组版本 ---
        version_card = ctk.CTkFrame(frame)
        version_card.pack(fill="x", padx=30, pady=10)
        version_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(version_card, text=_("第二步: 指定对应的基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                         column=0,
                                                                                                         columnspan=2,
                                                                                                         padx=15,
                                                                                                         pady=15,
                                                                                                         sticky="w")
        bsa_assembly_label = ctk.CTkLabel(version_card, text=_("BSA基因组版本:"), font=self.app_font)
        bsa_assembly_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 15), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_card, text=_("HVG基因组版本:"), font=self.app_font)
        hvg_assembly_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片3: 运行 ---
        run_card = ctk.CTkFrame(frame, fg_color="transparent")
        run_card.pack(fill="x", padx=30, pady=20)
        self.integrate_start_button = ctk.CTkButton(run_card, text=_("开始联合分析"), height=50,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.integrate_start_button.pack(fill="x", expand=True)

        return frame

    def _create_tools_frame(self, parent):

        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=_("数据工具"), font=self.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        self.tools_notebook = ctk.CTkTabview(frame, corner_radius=8, command=self._on_tab_change)
        if hasattr(self.tools_notebook, '_segmented_button'):
            self.tools_notebook._segmented_button.configure(font=self.app_font)
        self.tools_notebook.grid(row=1, column=0, padx=30, pady=10, sticky="nsew")

        return frame

    def _populate_tools_notebook(self):
        """
        使用固定的键和顺序填充所有工具选项卡，并设置按需加载。
        """
        self.tool_tab_frames = {}
        self.tool_tab_ui_loaded = {}

        for key in self.TOOL_TAB_ORDER:
            # 使用固定的键从字典获取待翻译文本，然后进行翻译
            tab_name = _(self.TAB_TITLE_KEYS[key])
            tab_frame = self.tools_notebook.add(tab_name)
            self.tool_tab_frames[key] = tab_frame
            self.tool_tab_ui_loaded[key] = False

        # “数据下载”是第一个，需要预先加载其内容
        download_key = "download"
        if download_key in self.tool_tab_frames:
            self._populate_download_tab_structure(self.tool_tab_frames[download_key])
            self.tool_tab_ui_loaded[download_key] = True

        # 设置回调命令，用于实现按需加载
        self.tools_notebook.configure(command=self._on_tool_tab_selected)

        # 确保启动后默认显示的选项卡是 "数据下载"
        self.tools_notebook.set(_(self.TAB_TITLE_KEYS["download"]))

    def _on_tool_tab_selected(self, tab_name=None):
        """
        按需加载所选工具选项卡的UI界面。
        此版本使用固定的键来反向查找，以支持多语言动态切换。
        """
        # 定义UI构建方法的映射
        tab_populators = {
            "download": self._populate_download_tab_structure,
            "homology": self._populate_homology_map_tab_structure,
            "locus_conversion": self._populate_locus_conversion_tab_structure,
            "gff_query": self._populate_gff_query_tab_structure,
            "annotation": self._populate_annotation_tab_structure,
            "ai_assistant": self._populate_ai_assistant_tab_structure,
            "genome_identifier": self._populate_genome_identifier_tab_structure,
            "xlsx_to_csv": self._populate_xlsx_to_csv_tab_structure,
        }

        # 获取当前被选中的选项卡的显示名称（已翻译）
        selected_tab_name = self.tools_notebook.get()

        # --- 关键修复：通过遍历固定的键值对来找到对应的程序化键 ---
        selected_tab_key = None
        for key, untranslated_text in self.TAB_TITLE_KEYS.items():
            if _(untranslated_text) == selected_tab_name:
                selected_tab_key = key
                break

        # 如果找到了key，并且这个选项卡的UI尚未加载
        if selected_tab_key and not self.tool_tab_ui_loaded.get(selected_tab_key, False):
            if selected_tab_key in tab_populators:
                self._log_to_viewer(f"INFO: Loading UI for tab '{selected_tab_name}'...")

                # 获取正确的Frame来填充UI
                frame_to_populate = self.tool_tab_frames[selected_tab_key]

                # 调用对应的UI构建方法
                tab_populators[selected_tab_key](frame_to_populate)

                # 标记为已加载
                self.tool_tab_ui_loaded[selected_tab_key] = True

    def start_xlsx_to_csv_conversion(self):
        """启动XLSX到CSV的转换任务"""
        from cotton_toolkit.core.convertXlsx2csv import convert_xlsx_to_single_csv

        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()

        if not input_path or not os.path.exists(input_path):
            self.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
            return

        # 如果输出路径为空，则自动生成一个
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.insert(0, output_path)

        self.active_task_name = _("XLSX转CSV")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self._update_button_states(is_task_running=True)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.start()

        # 在后台线程中运行转换，防止UI卡顿
        threading.Thread(
            target=lambda: (
                result := convert_xlsx_to_single_csv(input_path, output_path),
                self.task_done_callback(result, self.active_task_name)
            ),
            daemon=True
        ).start()

    def _populate_annotation_tab_structure(self, parent_frame):
        """
        填充功能注释选项卡内容。
        【已修复】创建时直接加载基因组版本列表。
        """
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)

        # 获取当前可用的基因组版本列表
        assembly_ids = [_("无可用版本")]
        if self.genome_sources_data:
            ids = list(self.genome_sources_data.keys())
            if ids:
                assembly_ids = ids

        input_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_frame, text=_("输入基因ID (每行一个或逗号分隔):"), font=self.app_font_bold).grid(row=0,
                                                                                                            column=0,
                                                                                                            columnspan=2,
                                                                                                            sticky="w",
                                                                                                            pady=(0, 5))
        self.annotation_genes_textbox = ctk.CTkTextbox(input_frame, height=180, font=self.app_font, wrap="word")
        self.annotation_genes_textbox.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self._add_placeholder(self.annotation_genes_textbox, self.placeholder_genes_homology_key)
        self.annotation_genes_textbox.bind("<FocusIn>",
                                           lambda event: self._clear_placeholder(self.annotation_genes_textbox,
                                                                                 self.placeholder_genes_homology_key))
        self.annotation_genes_textbox.bind("<FocusOut>",
                                           lambda event: self._add_placeholder(self.annotation_genes_textbox,
                                                                               self.placeholder_genes_homology_key))
        self.annotation_genes_textbox.bind("<KeyRelease>", self._on_annotation_gene_input_change)
        self.annotation_gene_input_widget = self.annotation_genes_textbox

        options_frame = ctk.CTkFrame(input_frame)
        options_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        options_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(options_frame, text=_("选择基因组版本:"), font=self.app_font_bold).pack(anchor="w", padx=10,
                                                                                             pady=(0, 5))
        self.annotation_assembly_dropdown = ctk.CTkOptionMenu(
            options_frame, variable=self.selected_annotation_assembly, values=assembly_ids,  # <-- 修复点
            font=self.app_font, dropdown_font=self.app_font
        )
        self.annotation_assembly_dropdown.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(options_frame, text=_("选择注释类型:"), font=self.app_font_bold).pack(anchor="w", padx=10,
                                                                                           pady=(15, 5))
        self.go_anno_checkbox = ctk.CTkCheckBox(options_frame, text=_("GO 功能注释"), variable=self.go_anno_var,
                                                font=self.app_font)
        self.go_anno_checkbox.pack(anchor="w", padx=10, pady=2)
        self.ipr_anno_checkbox = ctk.CTkCheckBox(options_frame, text=_("InterPro Domain 注释"),
                                                 variable=self.ipr_anno_var, font=self.app_font)
        self.ipr_anno_checkbox.pack(anchor="w", padx=10, pady=2)
        self.kegg_ortho_checkbox = ctk.CTkCheckBox(options_frame, text=_("KEGG Orthologs 注释"),
                                                   variable=self.kegg_ortho_anno_var, font=self.app_font)
        self.kegg_ortho_checkbox.pack(anchor="w", padx=10, pady=2)
        self.kegg_path_checkbox = ctk.CTkCheckBox(options_frame, text=_("KEGG Pathways 注释"),
                                                  variable=self.kegg_path_anno_var, font=self.app_font)
        self.kegg_path_checkbox.pack(anchor="w", padx=10, pady=(2, 10))

        output_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        output_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        output_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font_bold).grid(row=0, column=0,
                                                                                             sticky="w", pady=(0, 5))
        self.annotation_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font)
        self.annotation_output_csv_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(output_frame, text=_("选择目录"), font=self.app_font,
                      command=lambda: self._select_output_directory(self.annotation_output_csv_entry)).grid(row=1,
                                                                                                            column=1,
                                                                                                            sticky="e")

        start_button_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        start_button_frame.grid(row=4, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        self.start_annotation_button = ctk.CTkButton(start_button_frame, text=_("开始功能注释"),
                                                     font=self.app_font_bold, command=self.start_annotation_task)
        self.start_annotation_button.pack(side="right")



    def _load_prompts_to_ai_tab(self):
        """将配置中的Prompt模板加载到AI助手页面的输入框中。"""
        if not self.current_config: return

        # 直接从 MainConfig 对象访问 prompts
        prompts_cfg = self.current_config.ai_prompts
        trans_prompt = prompts_cfg.translation_prompt
        analy_prompt = prompts_cfg.analysis_prompt

        if hasattr(self, 'ai_translate_prompt_textbox'):
            self.ai_translate_prompt_textbox.delete("1.0", tk.END)
            self.ai_translate_prompt_textbox.insert("1.0", trans_prompt)

        if hasattr(self, 'ai_analyze_prompt_textbox'):
            self.ai_analyze_prompt_textbox.delete("1.0", tk.END)
            self.ai_analyze_prompt_textbox.insert("1.0", analy_prompt)

    def _populate_ai_assistant_tab_structure(self, page):
        """创建AI助手页面，为不同任务提供独立的、可编辑的Prompt输入框。"""
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1) # Row for main_card

        ctk.CTkLabel(page, text=_("使用AI批量处理表格数据"), font=self.app_title_font, wraplength=500).grid(
            row=0, column=0, pady=(20, 10), padx=20, sticky="n") # Use grid

        # AI信息卡片
        ai_info_card = ctk.CTkFrame(page, fg_color=("gray90", "gray20"))
        ai_info_card.grid(row=1, column=0, sticky="ew", padx=20, pady=10) # Use grid
        ai_info_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ai_info_card, text=_("当前AI配置:"), font=self.app_font_bold).grid(row=0, column=0, padx=10,
                                                                                        pady=(10, 5), sticky="w")
        self.ai_info_provider_label = ctk.CTkLabel(ai_info_card, text=_("服务商: -"), font=self.app_font)
        self.ai_info_provider_label.grid(row=1, column=0, padx=20, pady=2, sticky="w")
        self.ai_info_model_label = ctk.CTkLabel(ai_info_card, text=_("模型: -"), font=self.app_font)
        self.ai_info_model_label.grid(row=1, column=1, padx=10, pady=2, sticky="w")
        self.ai_info_key_label = ctk.CTkLabel(ai_info_card, text=_("API Key: -"), font=self.app_font)
        self.ai_info_key_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(2, 10), sticky="w")

        # --- UI主要功能区域 ---
        main_card = ctk.CTkFrame(page)
        main_card.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10)) # Use grid
        main_card.grid_columnconfigure(1, weight=1)
        main_card.grid_rowconfigure(3, weight=1) # For Prompt input box

        # Task selection and file input
        ctk.CTkLabel(main_card, text=_("输入CSV文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=10,
                                                                                 sticky="w")
        self.ai_input_file_entry = ctk.CTkEntry(main_card, placeholder_text=_("选择一个CSV文件"), height=35,
                                             font=self.app_font)
        self.ai_input_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ctk.CTkButton(main_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.ai_input_file_entry, [("CSV files", "*.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=(0, 10))

        ctk.CTkLabel(main_card, text=_("选择任务类型:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                  sticky="w")
        self.ai_task_type_menu = ctk.CTkOptionMenu(main_card, variable=self.ai_task_type_var,
                                                   values=[_("翻译"), _("分析")], command=self._on_ai_task_type_change,
                                                   height=35, font=self.app_font, dropdown_font=self.app_font)
        self.ai_task_type_menu.grid(row=1, column=1, columnspan=2, padx=(0, 10), sticky="ew")

        # Prompt Input Area
        ctk.CTkLabel(main_card, text=_("Prompt 指令 (用 {text} 代表单元格内容):"), font=self.app_font).grid(row=2,
                                                                                                            column=0,
                                                                                                            columnspan=3,
                                                                                                            padx=10,
                                                                                                            pady=(10,
                                                                                                                  0),
                                                                                                            sticky="w")

        # Create Prompt input boxes for translation and analysis tasks
        self.ai_translate_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_translate_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        self.ai_analyze_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_analyze_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        # Other parameters
        param_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        param_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10) # Use grid
        param_frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(param_frame, text=_("源列名:"), font=self.app_font).grid(row=0, column=0, padx=5)
        self.ai_source_col_entry = ctk.CTkEntry(param_frame, placeholder_text="Description", height=35,
                                             font=self.app_font)
        self.ai_source_col_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(param_frame, text=_("新列名:"), font=self.app_font).grid(row=0, column=2, padx=5)
        self.ai_new_col_entry = ctk.CTkEntry(param_frame, placeholder_text=_("描述/解释"), height=35,
                                          font=self.app_font)
        self.ai_new_col_entry.grid(row=0, column=3, sticky="ew")

        ai_proxy_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        ai_proxy_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=10) # Use grid
        self.ai_proxy_switch = ctk.CTkSwitch(ai_proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.ai_proxy_var, font=self.app_font)
        self.ai_proxy_switch.pack(side="left") # This is fine as it's the only widget packed within ai_proxy_frame

        # Start button outside main_card
        self.ai_start_button = ctk.CTkButton(page, text=_("开始AI任务"), height=40, command=self.start_ai_task,
                                             font=self.app_font_bold)
        self.ai_start_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20)) # Use grid for consistency within 'page'

        # Initial display of the correct Prompt input box based on default task type
        self._on_ai_task_type_change(self.ai_task_type_var.get())

    def _on_ai_task_type_change(self, choice):
        """根据AI任务类型切换显示的Prompt输入框。"""
        if choice == _("分析"):
            self.ai_analyze_prompt_textbox.grid()
            self.ai_translate_prompt_textbox.grid_remove()
        else:  # 默认为翻译
            self.ai_translate_prompt_textbox.grid()
            self.ai_analyze_prompt_textbox.grid_remove()

    def start_annotation_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.anno_input_file_entry.get().strip()
        gene_col = self.anno_gene_col_entry.get().strip()
        output_dir_parent = os.path.dirname(input_file) if input_file else "."
        output_dir = os.path.join(output_dir_parent, "annotation_results")

        if not input_file or not gene_col:
            self.show_error_message(_("输入缺失"), _("请输入文件路径和基因列名。"))
            return

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        if not anno_types:
            self.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。"))
            return

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("功能注释")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)  # 使用不确定模式
        self.progress_bar.start()

        threading.Thread(target=run_functional_annotation, kwargs={
            "config": self.current_config, "input_file": input_file, "output_dir": output_dir,
            "annotation_types": anno_types, "gene_column_name": gene_col,
            "status_callback": self.gui_status_callback
        }, daemon=True).start()

    def start_ai_task(self):
        """启动AI任务，并从正确的UI控件获取Prompt。"""
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.ai_input_file_entry.get().strip()
        source_col = self.ai_source_col_entry.get().strip()
        new_col = self.ai_new_col_entry.get().strip()
        task_type_display = self.ai_task_type_var.get()

        if not all([input_file, source_col, new_col]):
            self.show_error_message(_("输入缺失"), _("请输入文件路径、源列名和新列名。"));
            return

        # --- 根据任务类型从对应的输入框获取Prompt ---
        task_type = "analyze" if task_type_display == _("分析") else "translate"
        if task_type == 'analyze':
            prompt = self.ai_analyze_prompt_textbox.get("1.0", tk.END).strip()
        else:
            prompt = self.ai_translate_prompt_textbox.get("1.0", tk.END).strip()

        if not prompt or "{text}" not in prompt:
            self.show_error_message(_("Prompt格式错误"), _("Prompt指令不能为空，且必须包含占位符 '{text}'。"));
            return
        # --- 修改结束 ---

        temp_config = self.current_config.copy()
        proxy_status_msg = "OFF"
        if self.ai_proxy_var.get():
            proxies_cfg = self.current_config.get("downloader", {}).get("proxies")
            if not proxies_cfg or not (proxies_cfg.get('http') or proxies_cfg.get('httpss')):
                self.show_warning_message(_("代理未配置"), _("您开启了代理开关，但配置文件中未找到有效的代理地址。"))
                return
            proxy_status_msg = "ON"
        else:
            temp_config['downloader'] = self.current_config.get('downloader', {}).copy()
            temp_config['downloader']['proxies'] = None

        output_dir_parent = os.path.dirname(input_file)
        output_dir = os.path.join(output_dir_parent, "ai_results")

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("AI 助手")
        self._log_to_viewer(
            f"{self.active_task_name} ({task_type_display}) {_('任务开始...')} ({_('代理')}: {proxy_status_msg})")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        def task_wrapper():
            success = False
            try:
                success = run_ai_task(
                    config=temp_config, input_file=input_file, output_dir=output_dir,
                    source_column=source_col, new_column=new_col, task_type=task_type,
                    custom_prompt_template=prompt, status_callback=self.gui_status_callback
                )
            except Exception as e:
                # 捕获任何意外的严重错误，并记录详细的Traceback
                detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                self.gui_status_callback(f"[ERROR] {detailed_error}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

        # cotton_tool/gui_app.py

    def _update_ai_assistant_tab_info(self):
        """
        更新AI助手页面的配置信息显示。
        在尝试操作控件前先检查它们是否存在，以兼容懒加载。
        """
        if not hasattr(self, 'ai_info_provider_label') or not self.ai_info_provider_label.winfo_exists():
            self._log_to_viewer("DEBUG: AI assistant info labels not yet created, skipping update.", "DEBUG")
            return

        if not self.current_config:
            provider, model, key_status = "-", "-", _("未加载配置")
            key_color = self.secondary_text_color
        else:
            # 直接通过属性访问dataclass对象
            ai_cfg = self.current_config.ai_services
            provider_name = ai_cfg.default_provider
            provider_cfg = ai_cfg.providers.get(provider_name)  # 获取ProviderConfig对象

            # 为了兼容旧的显示逻辑，我们反向查找一下显示名称
            provider_display_name = provider_name
            for p_key, p_info in self.AI_PROVIDERS.items():
                if p_key == provider_name:
                    provider_display_name = p_info.get('name', provider_name)
                    break

            if provider_cfg:
                model = provider_cfg.model
                api_key = provider_cfg.api_key
            else:
                model = _("未设置")
                api_key = ""

            if not api_key or "YOUR_" in api_key or not api_key.strip():
                key_status = _("未配置或无效")
                key_color = ("#d9534f", "#e57373")  # red
            else:
                key_status = f"{api_key[:5]}...{api_key[-4:]} ({_('已配置')})"
                key_color = ("#28a745", "#73bf69")  # green

            provider = provider_display_name  # 使用显示名称

        self.ai_info_provider_label.configure(text=f"{_('服务商')}: {provider}")
        self.ai_info_model_label.configure(text=f"{_('模型')}: {model}")
        self.ai_info_key_label.configure(text=f"{_('API Key')}: {key_status}", text_color=key_color)

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
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
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
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(selected_display_mode, "System")
        ctk.set_appearance_mode(new_mode)

        # 更新日志颜色以匹配新模式
        self._update_log_tag_colors()

        # 更新并保存UI设置
        self.ui_settings['appearance_mode'] = new_mode
        self.ui_settings['appearance_mode_display'] = selected_display_mode
        self._save_ui_settings()

    def on_language_change(self, selected_display_name: str):
        new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "en")

        # 更新并保存UI设置
        self.ui_settings['language'] = new_language_code
        self._save_ui_settings()

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
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.log_textbox.tag_config("error_log", foreground="#d9534f")
        self.log_textbox.tag_config("warning_log", foreground="#f0ad4e")


    def _populate_download_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        target_card = ctk.CTkFrame(page)
        target_card.pack(fill="both", expand=True, pady=(15, 10), padx=15)
        target_card.grid_columnconfigure(0, weight=1)
        target_card.grid_rowconfigure(2, weight=1)

        target_header_frame = ctk.CTkFrame(target_card, fg_color="transparent")
        target_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        target_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(target_header_frame, text=_("下载目标: 选择基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                            column=0,
                                                                                                            sticky="w")

        selection_buttons_frame = ctk.CTkFrame(target_header_frame, fg_color="transparent")
        selection_buttons_frame.grid(row=0, column=1, sticky="e")

        self.dl_select_all_button = ctk.CTkButton(selection_buttons_frame, text=_("全选"), width=80, height=28,
                                                  font=self.app_font,
                                                  command=lambda: self._toggle_all_download_genomes(True))
        self.dl_deselect_all_button = ctk.CTkButton(selection_buttons_frame, text=_("取消全选"), width=90, height=28,
                                                    font=self.app_font,
                                                    command=lambda: self._toggle_all_download_genomes(False))
        self.dl_select_all_button.pack(side="left", padx=(0, 10))
        self.dl_deselect_all_button.pack(side="left")

        ctk.CTkLabel(target_card, text=_("勾选需要下载的基因组版本。若不勾选任何项，将默认下载所有可用版本。"),
                     text_color=self.secondary_text_color, font=self.app_font, wraplength=500).grid(row=1, column=0,
                                                                                                    padx=10,
                                                                                                    pady=(0, 10),
                                                                                                    sticky="w")

        self.download_genomes_checkbox_frame = ctk.CTkScrollableFrame(target_card, label_text="")
        self.download_genomes_checkbox_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._bind_mouse_wheel_to_scrollable(self.download_genomes_checkbox_frame)

        self._bind_mouse_wheel_to_scrollable(self.download_genomes_checkbox_frame)

        options_frame = ctk.CTkFrame(page)
        options_frame.pack(fill="x", expand=False, pady=10, padx=15)
        options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options_frame, text=_("下载选项"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                      padx=10, pady=(10, 15),
                                                                                      sticky="w")

        # --- 代理开关 ---
        proxy_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        proxy_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.dl_proxy_switch = ctk.CTkSwitch(proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.download_proxy_var, font=self.app_font)
        self.dl_proxy_switch.pack(side="left")

        force_download_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        force_download_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))
        self.dl_force_switch_label = ctk.CTkLabel(force_download_frame, text=_("强制重新下载:"), font=self.app_font)
        self.dl_force_switch_label.pack(side="left", padx=(0, 10))
        self.dl_force_switch = ctk.CTkSwitch(force_download_frame, text="", variable=self.download_force_checkbox_var)
        self.dl_force_switch.pack(side="left")

        self.download_start_button = ctk.CTkButton(page, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.download_start_button.pack(fill="x", padx=15, pady=(10, 15), side="bottom")

    def browse_download_output_dir(self):
        """
        打开文件夹选择对话框，让用户选择下载文件的输出目录。
        """
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory and self.download_output_dir_entry:
            self.download_output_dir_entry.delete(0, tk.END)
            self.download_output_dir_entry.insert(0, directory)

    def _update_download_genomes_list(self):
        """
        根据当前配置，动态更新下载页面的基因组版本复选框列表，并高亮显示已存在的项。
        在尝试操作 download_genomes_checkbox_frame 之前，检查其是否存在。
        """
        # 优化：在操作控件前先检查其是否存在
        if not hasattr(self,
                       'download_genomes_checkbox_frame') or not self.download_genomes_checkbox_frame.winfo_exists():
            self._log_to_viewer("DEBUG: download_genomes_checkbox_frame does not exist yet, skipping update.", "DEBUG")
            return  # 如果控件还未创建，则跳过此次更新

        # 清理旧的复选框和变量
        for widget in self.download_genomes_checkbox_frame.winfo_children():
            widget.destroy()
        self.download_genome_vars.clear()

        # 定义颜色 (亮色模式, 暗色模式)
        existing_item_color = ("#28a745", "#73bf69")
        default_color = self.default_label_text_color

        if not self.current_config:
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("请先加载配置文件"),
                         text_color=self.secondary_text_color).pack()
            return

        genome_sources = get_genome_data_sources(self.current_config)
        downloader_cfg = self.current_config.downloader
        base_download_dir = (downloader_cfg.download_output_base_dir
                             if downloader_cfg and downloader_cfg.download_output_base_dir
                             else "downloaded_cotton_data")

        if not genome_sources or not isinstance(genome_sources, dict):
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("配置文件中未找到基因组源"),
                         text_color=self.secondary_text_color).pack()
            return

        # 为每个基因组版本创建一个复选框
        for genome_id, details in genome_sources.items():
            var = tk.BooleanVar(value=False)
            species_name = details.get('species_name', _('未知物种'))
            display_text = f"{genome_id} ({species_name})"

            # --- 检查目录是否存在 ---
            safe_dir_name = species_name.replace(" ", "_").replace(".", "_").replace("(", "").replace(")", "").replace(
                "'", "")
            version_output_dir = os.path.join(base_download_dir, safe_dir_name)
            text_color_to_use = existing_item_color if os.path.exists(version_output_dir) else default_color

            cb = ctk.CTkCheckBox(
                self.download_genomes_checkbox_frame,
                text=display_text,
                variable=var,
                font=self.app_font,
                text_color=text_color_to_use
            )
            cb.pack(anchor="w", padx=10, pady=5)
            self.download_genome_vars[genome_id] = var

    def _toggle_all_download_genomes(self, select: bool):
        """全选或取消全选所有下载基因组的复选框"""
        for var in self.download_genome_vars.values():
            var.set(select)

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

    def _populate_homology_map_tab_structure(self, parent_frame):
        """
        填充基因组转换（同源映射）选项卡内容。
        【已修复】创建时直接加载基因组版本列表。
        """
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)

        # 获取当前可用的基因组版本列表
        assembly_ids = [_("无可用版本")]
        if self.genome_sources_data:
            ids = list(self.genome_sources_data.keys())
            if ids:
                assembly_ids = ids

        input_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(input_frame, text=_("输入源基因ID (每行一个或逗号分隔):"), font=self.app_font_bold).grid(row=0,
                                                                                                              column=0,
                                                                                                              sticky="w",
                                                                                                              pady=(0,
                                                                                                                    5))
        self.homology_map_genes_textbox = ctk.CTkTextbox(input_frame, height=120, font=self.app_font, wrap="word")
        self.homology_map_genes_textbox.grid(row=1, column=0, sticky="nsew", rowspan=3, padx=(0, 10))
        self.homology_map_genes_textbox.bind("<FocusIn>",
                                             lambda event: self._clear_placeholder(self.homology_map_genes_textbox,
                                                                                   self.placeholder_genes_homology_key))
        self.homology_map_genes_textbox.bind("<FocusOut>",
                                             lambda event: self._add_placeholder(self.homology_map_genes_textbox,
                                                                                 self.placeholder_genes_homology_key))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)
        self.homology_map_gene_input_widget = self.homology_map_genes_textbox

        ctk.CTkLabel(input_frame, text=_("选择源基因组版本:"), font=self.app_font_bold).grid(row=0, column=1,
                                                                                             sticky="w", pady=(0, 5))
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame, variable=self.selected_homology_source_assembly, values=assembly_ids,  # <-- 修复点
            command=self._on_homology_assembly_selection, font=self.app_font, dropdown_font=self.app_font
        )
        self.homology_map_source_assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ctk.CTkLabel(input_frame, text=_("选择目标基因组版本:"), font=self.app_font_bold).grid(row=2, column=1,
                                                                                               sticky="w", pady=(10, 5))
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame, variable=self.selected_homology_target_assembly, values=assembly_ids,  # <-- 修复点
            command=self._on_homology_assembly_selection, font=self.app_font, dropdown_font=self.app_font
        )
        self.homology_map_target_assembly_dropdown.grid(row=3, column=1, sticky="ew", padx=(0, 10))

        ctk.CTkLabel(input_frame, text=_("源到桥梁同源文件 (自动识别):"), font=self.app_font).grid(row=4, column=0,
                                                                                                   sticky="w",
                                                                                                   pady=(10, 5))
        self.homology_map_s2b_file_label = ctk.CTkLabel(input_frame, textvariable=self.homology_map_s2b_file_path_var,
                                                        font=self.app_font_mono, text_color=self.secondary_text_color,
                                                        wraplength=400, anchor="w", justify="left")
        self.homology_map_s2b_file_label.grid(row=5, column=0, columnspan=2, sticky="ew", padx=(0, 10))

        ctk.CTkLabel(input_frame, text=_("桥梁到目标同源文件 (自动识别):"), font=self.app_font).grid(row=6, column=0,
                                                                                                     sticky="w",
                                                                                                     pady=(10, 5))
        self.homology_map_b2t_file_label = ctk.CTkLabel(input_frame, textvariable=self.homology_map_b2t_file_path_var,
                                                        font=self.app_font_mono, text_color=self.secondary_text_color,
                                                        wraplength=400, anchor="w", justify="left")
        self.homology_map_b2t_file_label.grid(row=7, column=0, columnspan=2, sticky="ew", padx=(0, 10))

        output_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        output_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        output_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font_bold).grid(row=0, column=0,
                                                                                             sticky="w", pady=(0, 5))
        self.homology_map_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font)
        self.homology_map_output_csv_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(output_frame, text=_("选择目录"), font=self.app_font,
                      command=lambda: self._select_output_directory(self.homology_map_output_csv_entry)).grid(row=1,
                                                                                                              column=1,
                                                                                                              sticky="e")

        start_button_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        start_button_frame.grid(row=9, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        self.start_homology_map_button = ctk.CTkButton(start_button_frame, text=_("开始基因组转换"),
                                                       font=self.app_font_bold, command=self.start_homology_map_task)
        self.start_homology_map_button.pack(side="right")

    def _populate_gff_query_tab_structure(self, parent_frame):
        """
        填充GFF基因查询选项卡内容。
        【已修复】创建时直接加载基因组版本列表。
        """
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)

        # 获取当前可用的基因组版本列表
        assembly_ids = [_("无可用版本")]
        if self.genome_sources_data:
            ids = list(self.genome_sources_data.keys())
            if ids:
                assembly_ids = ids

        input_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_frame, text=_("输入基因ID (每行一个或逗号分隔，与区域查询二选一):"),
                     font=self.app_font_bold).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.gff_query_genes_textbox = ctk.CTkTextbox(input_frame, height=120, font=self.app_font, wrap="word")
        self.gff_query_genes_textbox.grid(row=1, column=0, sticky="nsew", rowspan=2, padx=(0, 10))
        self._add_placeholder(self.gff_query_genes_textbox, self.placeholder_genes_gff_key)
        self.gff_query_genes_textbox.bind("<FocusIn>",
                                          lambda event: self._clear_placeholder(self.gff_query_genes_textbox,
                                                                                self.placeholder_genes_gff_key))
        self.gff_query_genes_textbox.bind("<FocusOut>",
                                          lambda event: self._add_placeholder(self.gff_query_genes_textbox,
                                                                              self.placeholder_genes_gff_key))
        self.gff_query_genes_textbox.bind("<KeyRelease>", self._on_gff_query_gene_input_change)
        self.gff_query_gene_input_widget = self.gff_query_genes_textbox

        ctk.CTkLabel(input_frame, text=_("输入染色体区域 (例如: Chr01:1000-2000，与基因ID查询二选一):"),
                     font=self.app_font_bold).grid(row=3, column=0, sticky="w", pady=(10, 5))
        self.gff_query_region_entry = ctk.CTkEntry(input_frame, font=self.app_font)
        self.gff_query_region_entry.grid(row=4, column=0, sticky="ew", padx=(0, 10))

        ctk.CTkLabel(input_frame, text=_("选择基因组版本:"), font=self.app_font_bold).grid(row=0, column=1, sticky="w",
                                                                                           pady=(0, 5), padx=(10, 0))
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame, variable=self.selected_gff_query_assembly, values=assembly_ids,  # <-- 修复点
            command=self._on_gff_query_assembly_selection, font=self.app_font, dropdown_font=self.app_font
        )
        self.gff_query_assembly_dropdown.grid(row=1, column=1, sticky="ew", padx=(10, 10))

        output_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        output_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        output_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font_bold).grid(row=0, column=0,
                                                                                             sticky="w", pady=(0, 5))
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font)
        self.gff_query_output_csv_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(output_frame, text=_("选择目录"), font=self.app_font,
                      command=lambda: self._select_output_directory(self.gff_query_output_csv_entry)).grid(row=1,
                                                                                                           column=1,
                                                                                                           sticky="e")

        start_button_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        start_button_frame.grid(row=6, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        self.start_gff_query_button = ctk.CTkButton(start_button_frame, text=_("开始基因查询"), font=self.app_font_bold,
                                                    command=self.start_gff_query_task)
        self.start_gff_query_button.pack(side="right")



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
        【已修正】根据 self.current_config 的状态，更新整个应用程序的UI。
        """
        self._log_to_viewer(_("正在应用配置到整个UI..."))

        # 更新主页的配置路径显示
        if self.config_path:
            path_text = _("当前配置: {}").format(os.path.basename(self.config_path))
        else:
            path_text = _("未加载配置")

        if hasattr(self, 'config_path_label') and self.config_path_label.winfo_exists():
            self.config_path_label.configure(text=path_text)

        # 【核心修复】现在调用新的主控方法，它只会更新值，不会重建UI
        if hasattr(self, 'editor_frame') and self.editor_frame.winfo_exists():
            self._handle_editor_ui_update()

        # 更新整合分析页面
        if hasattr(self, 'integrate_frame') and self.integrate_frame.winfo_exists():
            if self.current_config:
                pipe_cfg = self.current_config.integration_pipeline

                # 更新输入框
                # 先清除旧值，再插入新值
                self.integrate_excel_entry.delete(0, tk.END)
                if pipe_cfg.input_excel_path:
                    self.integrate_excel_entry.insert(0, pipe_cfg.input_excel_path)

                # 更新下拉菜单的选中项
                self.selected_bsa_sheet.set(pipe_cfg.bsa_sheet_name or _("请先指定Excel文件"))
                self.selected_hvg_sheet.set(pipe_cfg.hvg_sheet_name or _("请先指定Excel文件"))
                self.selected_bsa_assembly.set(pipe_cfg.bsa_assembly_id or _("无可用版本"))
                self.selected_hvg_assembly.set(pipe_cfg.hvg_assembly_id or _("无可用版本"))

                # 确保下拉菜单的列表和值都是最新的
                self._update_assembly_id_dropdowns()
                self._update_excel_sheet_dropdowns()

            else:
                self.integrate_excel_entry.delete(0, tk.END)
                self.selected_bsa_sheet.set(_("请先指定Excel文件"))
                self.selected_hvg_sheet.set(_("请先指定Excel文件"))
                self.selected_bsa_assembly.set(_("无可用版本"))
                self.selected_hvg_assembly.set(_("无可用版本"))

        # 更新所有工具页面
        if hasattr(self, 'tools_notebook') and self.tools_notebook.winfo_exists():
            self._update_download_genomes_list()
            self._update_ai_assistant_tab_info()
            self._load_prompts_to_ai_tab()
            if self.current_config:
                pipe_cfg = self.current_config.integration_pipeline
                self.selected_homology_source_assembly.set(pipe_cfg.bsa_assembly_id)
                self.selected_homology_target_assembly.set(pipe_cfg.hvg_assembly_id)
                self.selected_gff_query_assembly.set(pipe_cfg.bsa_assembly_id or pipe_cfg.hvg_assembly_id)

        # 更新所有按钮状态
        self._update_button_states()
        self._log_to_viewer(_("UI已根据当前配置刷新。"))

    def _handle_editor_ui_update(self):
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
            self._log_to_viewer("DEBUG: Editor UI not built. Creating for the first time...", "DEBUG")

            # 清理可能存在的占位符文本
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()

            # 只有在存在配置时才构建UI
            if self.current_config:
                self._create_editor_widgets(self.editor_scroll_frame) # 创建所有 UI 控件
                self.editor_ui_built = True  # 设置标志，表示UI已创建
                self.save_editor_button.configure(state="normal") # 启用保存按钮

                # **关键修改：在这里立即填充数据**
                # 确保 UI 控件创建后，立即用 current_config 的值填充它们
                self._apply_config_values_to_editor()
            else:
                # 如果没有配置，显示提示信息
                ctk.CTkLabel(self.editor_scroll_frame, text=_("请先从“主页”加载或生成一个配置文件。"),
                             font=self.app_subtitle_font, text_color=self.secondary_text_color).grid(row=0, column=0,
                                                                                                     pady=50,
                                                                                                     sticky="nsew")
                self.editor_scroll_frame.grid_rowconfigure(0, weight=1)
                if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")
                return  # 不往下执行数据填充

        # 4. 如果UI已经存在，无论当前配置是否已更新，都尝试用新数据填充/更新它。
        #    这将确保当 current_config 在外部（比如通过加载文件）更新时，编辑器界面也会刷新。
        if self.current_config:
            self._apply_config_values_to_editor() # 确保每次打开编辑器时，都用最新的配置刷新 UI
        else:
            # 如果到这里仍然没有配置（例如，程序刚启动且无默认配置），则禁用保存按钮
            if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")
            return


        # 4. 如果UI已经存在，则什么都不做，以保留用户的输入
        if self.current_config:
            pass
        else:
            # 如果到这里仍然没有配置（例如，程序刚启动且无默认配置），则禁用保存按钮
            if hasattr(self, 'save_editor_button'): self.save_editor_button.configure(state="disabled")

    def _setup_fonts(self):
        """设置全局字体，并实现字体栈回退机制。"""
        # 定义一个字体栈，程序会从前到后依次尝试使用
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        monospace_font_stack = ["Consolas", "Courier New", "monospace"] # 新增等宽字体栈
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
        self.app_font_mono = ctk.CTkFont(family=selected_mono_font, size=12) # NEW: 等宽字体定义

    def update_language_ui(self, lang_code_to_set=None):
        """
        动态更新整个UI的语言。此版本能正确处理 CTkTabView 的标题。
        """
        global _
        if not lang_code_to_set:
            lang_code_to_set = self.ui_settings.get('language', 'zh-hans')

        # --- 更新UI语言下拉菜单本身的显示值 ---
        display_name_to_set = self.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        self.selected_language_var.set(display_name_to_set)

        try:
            _ = setup_cli_i18n(language_code=lang_code_to_set, app_name="cotton_toolkit")
        except Exception as e:
            _ = lambda s: s
            logging.error(f"语言设置错误: {e}")

        # 1. 更新窗口标题和已注册的普通控件
        self.title(_(self.title_text_key))
        for widget, key_or_options in self.translatable_widgets.items():
            if not (widget and widget.winfo_exists()): continue
            try:
                if isinstance(key_or_options, str):
                    widget.configure(text=_(key_or_options))
                elif isinstance(key_or_options, tuple) and key_or_options[0] == "values":
                    widget.configure(values=[_(v) for v in key_or_options[1]])
            except Exception as e:
                logger.warning(f"更新控件 {widget} 文本时出错: {e}")

        # 2. 正确地更新 TabView 标题
        try:
            # 根据固定的顺序生成一个新的、翻译后的标题列表
            new_tab_titles = [_(self.TAB_TITLE_KEYS[key]) for key in self.TOOL_TAB_ORDER]

            # 直接配置 TabView 内部的分段按钮的 `values` 属性
            if hasattr(self, 'tools_notebook') and hasattr(self.tools_notebook, '_segmented_button'):
                self.tools_notebook._segmented_button.configure(values=new_tab_titles)
            else:
                logger.warning("无法找到 tools_notebook 或其 _segmented_button 来更新选项卡标题。")

        except Exception as e:
            logger.critical(f"动态更新TabView时发生严重错误: {e}")

        # 3. 更新其他特定控件
        if hasattr(self, 'appearance_mode_optionemenu'):
            self.appearance_mode_optionemenu.configure(values=[_("浅色"), _("深色"), _("系统")])
            current_mode_display = self.selected_appearance_var.get()
            if "Light" in current_mode_display:
                self.selected_appearance_var.set(_("浅色"))
            elif "Dark" in current_mode_display:
                self.selected_appearance_var.set(_("深色"))
            else:
                self.selected_appearance_var.set(_("系统"))

        self._log_to_viewer(_("界面语言已更新。"), "INFO")


    def _update_assembly_id_dropdowns(self):
        """
        用从配置文件加载的基因组版本列表更新所有相关的下拉菜单。
        此版本通过预设StringVar的值来避免UI状态冲突。
        """
        if not self.genome_sources_data:
            self._log_to_viewer(_("警告: 基因组源数据为空，无法更新下拉菜单。"), "WARNING")
            assembly_ids = [_("无可用基因组")]
        else:
            assembly_ids = list(self.genome_sources_data.keys())

        # --- 关键修复：在更新选项列表前，先为控件变量设置一个有效值 ---
        # 1. 确定一个新的、有效的默认值
        new_default_value = ""
        if assembly_ids and assembly_ids[0] != _("无可用基因组"):
            new_default_value = assembly_ids[0]

        # 2. 获取所有相关的StringVar变量
        all_assembly_vars = [
            self.selected_bsa_assembly, self.selected_hvg_assembly,
            self.selected_homology_source_assembly, self.selected_homology_target_assembly,
            self.selected_locus_source_assembly, self.selected_locus_target_assembly,
            self.selected_gff_query_assembly, self.selected_annotation_assembly
        ]

        # 3. 检查并重置每个变量的值
        for var in all_assembly_vars:
            # 如果变量的当前值不在新的有效列表中，就重置它
            if var.get() not in assembly_ids:
                var.set(new_default_value)

        # 4. 获取所有相关的下拉菜单控件
        all_dropdown_widgets = [
            getattr(self, 'integrate_bsa_assembly_dropdown', None),
            getattr(self, 'integrate_hvg_assembly_dropdown', None),
            getattr(self, 'homology_map_source_assembly_dropdown', None),
            getattr(self, 'homology_map_target_assembly_dropdown', None),
            getattr(self, 'locus_source_assembly_dropdown', None),
            getattr(self, 'locus_target_assembly_dropdown', None),
            getattr(self, 'gff_query_assembly_dropdown', None),
            getattr(self, 'annotation_assembly_dropdown', None)
        ]

        # 5. 现在可以安全地用新的列表更新所有下拉菜单的选项了
        for widget in all_dropdown_widgets:
            if widget and widget.winfo_exists():
                widget.configure(values=assembly_ids)

        # 6. 尝试根据配置文件恢复用户的选择（如果有效的话）
        if self.current_config:
            pipe_cfg = self.current_config.integration_pipeline
            if pipe_cfg.bsa_assembly_id in assembly_ids:
                self.selected_bsa_assembly.set(pipe_cfg.bsa_assembly_id)
            if pipe_cfg.hvg_assembly_id in assembly_ids:
                self.selected_hvg_assembly.set(pipe_cfg.hvg_assembly_id)

        # 7. 最后，手动触发一次UI更新，以确保文件路径等显示正确
        self._on_homology_assembly_selection()
        self._on_locus_assembly_selection()

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

    def browse_integrate_excel(self):  #
        filepath = filedialog.askopenfilename(title=_("选择输入Excel文件"),
                                              filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*")))  #
        if filepath:  #
            self.integrate_excel_entry.delete(0, tk.END)  #
            self.integrate_excel_entry.insert(0, filepath)  #
            self._update_excel_sheet_dropdowns()  #

    def start_integrate_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("联合分析")

        # 将UI参数收集移到包装器内部，确保在线程中获取最新值
        def task_wrapper():
            success = False
            try:
                cfg_pipeline = self.current_config.setdefault('integration_pipeline', {})
                cfg_pipeline['bsa_assembly_id'] = self.selected_bsa_assembly.get()
                cfg_pipeline['hvg_assembly_id'] = self.selected_hvg_assembly.get()
                cfg_pipeline['bsa_sheet_name'] = self.selected_bsa_sheet.get()
                cfg_pipeline['hvg_sheet_name'] = self.selected_hvg_sheet.get()
                excel_override = self.integrate_excel_entry.get().strip() or None

                self.gui_status_callback(f"{self.active_task_name} {_('任务开始...')}")
                self.progress_bar.grid();
                self.progress_bar.set(0)

                success = integrate_bsa_with_hvg(
                    config=self.current_config,
                    input_excel_path_override=excel_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback,
                )
            except Exception as e:
                detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                self.gui_status_callback(f"[ERROR] {detailed_error}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

    def start_homology_map_task(self):
        """
        【已修复】启动基因组转换任务，使用正确的参数名调用后端函数。
        """
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"));
            return

        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip()
        placeholder_text = _(self.placeholders[self.placeholder_genes_homology_key])

        if gene_ids_text == placeholder_text:
            source_gene_ids_list = []
        else:
            source_gene_ids_list = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if
                                    gene.strip()]

        if not source_gene_ids_list:
            self.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"));
            return

        source_assembly = self.selected_homology_source_assembly.get()
        target_assembly = self.selected_homology_target_assembly.get()
        output_csv = self.homology_map_output_csv_entry.get().strip() or None

        if not all([source_assembly, target_assembly]):
            self.show_error_message(_("输入缺失"), _("请选择源基因组和目标基因组。"));
            return

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因组转换")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        def task_wrapper():
            run_homology_map_standalone(
                config=self.current_config,
                source_assembly_id=source_assembly,
                target_assembly_id=target_assembly,
                gene_ids=source_gene_ids_list,
                region=None,
                output_csv_path=output_csv,
                status_callback=self.gui_status_callback,
                progress_callback=self.gui_progress_callback,
                task_done_callback=lambda s: self.task_done_callback(s, self.active_task_name)
            )

        threading.Thread(target=task_wrapper, daemon=True).start()

    def start_gff_query_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因位点查询")

        assembly_id_override = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_entry.get("1.0", tk.END).strip()
        current_placeholder = _(self.placeholder_genes_gff_key)
        if gene_ids_text == current_placeholder or not gene_ids_text:
            gene_ids_list = None
        else:
            gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        region_str = self.gff_query_region_entry.get().strip()
        output_csv_path = self.gff_query_output_csv_entry.get().strip() or None
        region_tuple = None
        if region_str:
            try:
                parts = region_str.split(':')
                if len(parts) == 2 and '-' in parts[1]:
                    chrom = parts[0]
                    start_end = parts[1].split('-')
                    start = int(start_end[0])
                    end = int(start_end[1])
                    region_tuple = (chrom, start, end)
                else:
                    raise ValueError("Format error")
            except Exception:
                self.show_error_message(_("输入错误"), _("染色体区域格式不正确。请使用 'chr:start-end' 格式。"));
                self._update_button_states(False);
                return

        if not assembly_id_override or assembly_id_override == _("加载中..."):
            self.show_error_message(_("输入缺失"), _("请选择一个基因组版本ID。"));
            self._update_button_states(False);
            return
        if not gene_ids_list and not region_tuple:
            self.show_error_message(_("输入缺失"), _("必须提供基因ID列表或染色体区域进行查询。"));
            self._update_button_states(False);
            return

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_gff_gene_lookup_standalone, kwargs={
            "config": self.current_config, "assembly_id_override": assembly_id_override,
            "gene_ids_override": gene_ids_list, "region_override": region_tuple,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

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
        # 将日志消息放入队列，由主线程处理
        self.log_queue.put((message, level))

    def show_info_message(self, title, message):
        self._log_to_viewer(f"{title}: {message}", level="INFO")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color=self.default_label_text_color)
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="info")

    def show_error_message(self, title, message):
        self._log_to_viewer(f"ERROR - {title}: {message}", level="ERROR")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="red")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="error")

    def show_warning_message(self, title, message):
        self._log_to_viewer(f"WARNING - {title}: {message}", level="WARNING")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="orange")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="warning")

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
        """
        此版本修复了重复的消息处理逻辑和错误的窗口关闭调用。
        """
        try:
            # --- 处理日志队列 ---
            while not self.log_queue.empty():
                log_message, log_level = self.log_queue.get_nowait()
                self._display_log_message_in_ui(log_message, log_level)

            # --- 处理主消息队列 ---
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()

                if message_type == "startup_complete":
                    self._hide_progress_dialog()
                    # --- 在这里接收基因组源数据 ---
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

                elif message_type == "startup_failed":
                    self._hide_progress_dialog()  # <--- 新增此行，用于在失败时也关闭加载窗口
                    self.show_error_message(_("启动错误"), str(data))
                    self._update_button_states()

                elif message_type == "config_load_task_done":
                    self._hide_progress_dialog()
                    success, result_data, filepath = data
                    if success:
                        self.current_config = result_data
                        self.config_path = os.path.abspath(filepath)
                        self.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
                        # 加载完新配置后，也需要重新加载基因组源数据
                        self.genome_sources_data = get_genome_data_sources(self.current_config,
                                                                           logger=self._log_to_viewer)
                        self._apply_config_to_ui()
                    else:
                        self.show_error_message(_("加载失败"), str(result_data))

                elif message_type == "task_done":
                    success, task_display_name = data
                    self.progress_bar.grid_remove()
                    if not self.error_dialog_lock.locked():
                        final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))
                        self.status_label.configure(text=final_message,
                                                    text_color=("green" if success else ("#d9534f", "#e57373")))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked(): self.error_dialog_lock.release()

                elif message_type == "error":
                    self.show_error_message(_("任务执行出错"), data)
                    self.progress_bar.grid_remove()
                    self.status_label.configure(text=f"{_('任务终止于')}: {data[:100]}",
                                                text_color=("#d9534f", "#e57373"))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked(): self.error_dialog_lock.release()

                elif message_type == "status":
                    self.status_label.configure(text=str(data)[:150])

                elif message_type == "progress":
                    percentage, text = data
                    if not self.progress_bar.winfo_viewable(): self.progress_bar.grid()
                    self.progress_bar.set(percentage / 100.0)
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)")

                elif message_type == "hide_progress_dialog":
                    self._hide_progress_dialog()  # 统一调用正确的隐藏方法

                elif message_type == "update_sheets_dropdown":
                    sheet_names, excel_path, error = data
                    self._update_sheet_dropdowns_ui(sheet_names, excel_path, error)

                elif message_type == "ai_models_fetched":
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
                        self.show_info_message(_("刷新成功"),
                                               f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')} ")

                elif message_type == "ai_models_failed":
                    provider_key, error_msg = data
                    self._log_to_viewer(f"{provider_key} {_('模型列表获取失败:')} {error_msg}", "ERROR")
                    model_selector_tuple = getattr(self, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
                    if model_selector_tuple:
                        _a, entry, dropdown, _a, _a = model_selector_tuple
                        dropdown.grid_remove()
                        entry.grid()
                        self.show_warning_message(_("刷新失败"),
                                                  f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")

                elif message_type == "auto_identify_success":
                    target_var, assembly_id = data
                    if self.genome_sources_data and assembly_id in self.genome_sources_data.keys():
                        target_var.set(assembly_id)
                        self._log_to_viewer(f"UI已自动更新基因为: {assembly_id}", "DEBUG")
                        self._on_homology_assembly_selection(None)
                        self._on_locus_assembly_selection(None)

                elif message_type == "auto_identify_fail":
                    pass  # 识别失败，静默处理

                elif message_type == "auto_identify_error":
                    self._log_to_viewer(f"自动识别基因组时发生错误: {data}", "ERROR")


        except queue.Empty:
            pass
        except Exception as e:
            logging.critical(f"Unhandled exception in check_queue_periodic: {e}", exc_info=True)

        self.after(100, self.check_queue_periodic)

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
        为 CustomTkinter 的可滚动widget（如 CTkScrollableFrame, CTkTextbox）绑定鼠标滚轮事件。
        直接绑定到 CustomTkinter 控件，因为它会处理底层的 Tkinter 组件。
        注意：CustomTkinter 在内部已经为 CTkScrollableFrame 和 CTkTextbox 实现了基本的滚轮功能。
        这个方法主要用于确保自定义的或额外的滚轮绑定能够正常工作，
        或者在某些情况下增强默认行为（尽管通常不推荐修改CTk的内部实现）。

        对于 CTkScrollableFrame，它内部有一个 canvas，事件需要绑定到 canvas 上。
        对于 CTkTextbox，它有自己的内部 Text 控件，事件需要绑定到该 Text 控件上。
        """
        # 对于 CTkScrollableFrame
        if hasattr(widget, "_canvas") and isinstance(widget._canvas, ctk.CTkCanvas):
            canvas = widget._canvas
            canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                        add="+")
            canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkScrollableFrame canvas: {widget}", "DEBUG")

        # 对于 CTkTextbox
        elif hasattr(widget, "_textbox") and isinstance(widget._textbox, tk.Text):
            textbox = widget._textbox
            textbox.bind("<MouseWheel>", lambda event: textbox.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                         add="+")
            textbox.bind("<Button-4>", lambda event: textbox.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            textbox.bind("<Button-5>", lambda event: textbox.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkTextbox internal Text: {widget}", "DEBUG")

    def on_closing(self):
        if self._show_custom_dialog(_("退出"), _("您确定要退出吗?"), buttons=[_("确定"), _("取消")],
                                    icon_type="question") == _("确定"):
            self.destroy()

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
        【全新版本】处理“生成默认配置”按钮的点击事件。
        能够检测文件是否存在，并根据用户的选择执行覆盖或加载操作。
        """
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if not output_dir:
            self._log_to_viewer(_("用户取消了目录选择。"))
            return

        self._log_to_viewer(f"{_('用户选择的配置目录:')} {output_dir}")
        main_config_filename = "config.yml"  # 使用硬编码以确保检查的文件名正确
        main_config_path = os.path.join(output_dir, main_config_filename)

        should_overwrite = False
        # 检查配置文件是否已存在
        if os.path.exists(main_config_path):
            # 如果文件存在，弹窗询问用户
            user_choice = self._show_custom_dialog(
                title=_("文件已存在"),
                message=_("配置文件 '{}' 已存在于所选目录中。\n\n您想覆盖它吗？\n(选择“否”将直接加载现有文件)").format(
                    main_config_filename),
                buttons=[_("是 (覆盖)"), _("否 (加载)")],
                icon_type="question"
            )

            if user_choice == _("是 (覆盖)"):
                should_overwrite = True
            elif user_choice == _("否 (加载)"):
                # 用户选择不覆盖，则直接加载现有文件
                self.load_config_file(filepath=main_config_path)
                return  # 结束流程
            else:
                # 用户关闭了对话框
                self._log_to_viewer(_("用户取消了覆盖操作。"))
                return

        # 如果文件不存在，或者用户同意覆盖，则执行生成
        try:
            self._log_to_viewer(_("正在生成默认配置文件..."))
            success, new_main_cfg_path, new_gs_cfg_path = generate_default_config_files(
                output_dir,
                overwrite=should_overwrite,
                main_config_filename=main_config_filename
            )
            if success:
                msg = f"{_('默认配置文件已成功生成到:')}\n{new_main_cfg_path}\n{new_gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"
                if self._show_custom_dialog(_("生成成功"), msg, [_("是"), _("否")], "info") == _("是"):
                    self.load_config_file(filepath=new_main_cfg_path)
            else:
                # generate_default_config_files 内部应该已经打印了日志
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
            self._log_to_viewer(f"{_('基因组源文件已保存到:')} {abs_path}");
            self.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")  #
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")  #

    def _update_button_states(self, is_task_running=False):
        action_state = "disabled" if is_task_running else "normal"
        task_button_state = "normal" if self.current_config and not is_task_running else "disabled"

        # 所有任务按钮
        if hasattr(self, 'download_start_button') and self.download_start_button.winfo_exists():
            self.download_start_button.configure(state=task_button_state)
        if hasattr(self, 'integrate_start_button') and self.integrate_start_button.winfo_exists():
            self.integrate_start_button.configure(state=task_button_state)
        if hasattr(self, 'homology_map_start_button') and self.homology_map_start_button.winfo_exists():
            self.homology_map_start_button.configure(state=task_button_state)
        if hasattr(self, 'gff_query_start_button') and self.gff_query_start_button.winfo_exists():
            self.gff_query_start_button.configure(state=task_button_state)
        if hasattr(self, 'anno_start_button') and self.anno_start_button.winfo_exists():  # For annotation tab
            self.anno_start_button.configure(state=task_button_state)
        if hasattr(self, 'ai_start_button') and self.ai_start_button.winfo_exists():  # For AI assistant tab
            self.ai_start_button.configure(state=task_button_state)
        if hasattr(self, 'convert_start_button') and self.convert_start_button.winfo_exists():  # For XLSX to CSV tab
            self.convert_start_button.configure(state=task_button_state)
        if hasattr(self, 'locus_convert_start_button') and self.locus_convert_start_button.winfo_exists():
            self.locus_convert_start_button.configure(state=task_button_state)


        # 侧边栏和配置按钮
        if hasattr(self, 'navigation_frame'):  # 确保导航框架已经创建
            # 遍历这些按钮，并检查它们是否存在
            for btn_name in ['home_button', 'editor_button', 'integrate_button', 'tools_button',
                             'load_config_button', 'gen_config_button']:  #
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    if btn.winfo_exists():  # 确保控件在Tkinter中仍存在
                        btn.configure(state=action_state)

    def start_download_task(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 禁用所有操作按钮，表明任务正在进行
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("数据下载")

        # 将后台任务的执行逻辑包裹在一个函数中
        def task_wrapper():
            success = False
            try:
                # 1. 从UI复选框中收集需要下载的基因组ID列表
                versions_to_download = [gid for gid, var in self.download_genome_vars.items() if var.get()]
                # 如果用户没有勾选任何项，则列表为空，后台会理解为下载所有
                if not versions_to_download:
                    versions_to_download = None

                # 2. 根据UI开关状态决定是否使用代理
                proxies_to_use = None
                if self.download_proxy_var.get():
                    # 仅当开关打开时，才从配置中读取代理地址
                    proxies_to_use = self.current_config.downloader.proxies
                    if not proxies_to_use or not (proxies_to_use.http or proxies_to_use.https):
                        # 如果代理地址未配置，则通过消息队列报错并终止任务
                        self.gui_status_callback(f"[ERROR] {_('您开启了代理开关，但配置文件中未找到有效的代理地址。')}")
                        return  # 提前终止线程

                # 3. 准备传递给后台的配置
                # 使用 deepcopy 创建一个临时配置副本，避免修改内存中的原始配置对象
                temp_config_obj = copy.deepcopy(self.current_config)
                temp_config_obj.downloader.proxies = proxies_to_use  # 覆盖代理设置

                # 因为 deepcopy 可能不会复制非标准的私有属性，所以我们手动复制它。
                if hasattr(self.current_config, '_config_file_abs_path_'):
                    temp_config_obj._config_file_abs_path_ = self.current_config._config_file_abs_path_

                force_download_override = self.download_force_checkbox_var.get()

                # 4. 更新UI状态，准备开始任务
                self.gui_status_callback(
                    f"{self.active_task_name} {_('任务开始...')} ({_('代理')}: {'ON' if proxies_to_use else 'OFF'})")
                self.gui_progress_callback(0, _("正在准备下载..."))  # 使用 progress 回调来更新状态

                # 5. 调用后台下载函数
                success = download_genome_data(
                    config=temp_config_obj,
                    genome_versions_to_download_override=versions_to_download,
                    force_download_override=force_download_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback
                )
            except Exception as e:
                # 捕获任何意外的严重错误
                detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
                self.gui_status_callback(f"[ERROR] {detailed_error}")
                success = False
            finally:
                # 无论成功或失败，都确保调用任务结束回调
                self.task_done_callback(success, self.active_task_name)

        # 启动包含以上全部逻辑的后台线程
        threading.Thread(target=task_wrapper, daemon=True).start()

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

    def _sync_integrate_tab_to_config(self):
        """
        当联合分析页面的输入控件发生变化时，将其值更新到 self.current_config 中。
        """
        if not self.current_config:
            return

        try:
            pipe_cfg = self.current_config.integration_pipeline

            # 从UI控件获取值
            excel_path = self.integrate_excel_entry.get().strip()
            bsa_sheet = self.selected_bsa_sheet.get()
            hvg_sheet = self.selected_hvg_sheet.get()
            bsa_assembly = self.selected_bsa_assembly.get()
            hvg_assembly = self.selected_hvg_assembly.get()

            # 更新内存中的配置对象
            pipe_cfg.input_excel_path = excel_path
            pipe_cfg.bsa_sheet_name = bsa_sheet if bsa_sheet not in [_("请先指定Excel文件"), _("读取中...")] else ""
            pipe_cfg.hvg_sheet_name = hvg_sheet if hvg_sheet not in [_("请先指定Excel文件"), _("读取中...")] else ""
            pipe_cfg.bsa_assembly_id = bsa_assembly if bsa_assembly not in [_("加载中..."), _("无可用版本")] else ""
            pipe_cfg.hvg_assembly_id = hvg_assembly if hvg_assembly not in [_("加载中..."), _("无可用版本")] else ""

            self._log_to_viewer(_("联合分析页面的输入已同步到内存配置。"), "DEBUG")

            # 切换到编辑器时，它会从这个更新过的配置中读取值

        except Exception as e:
            self._log_to_viewer(f"{_('同步UI到配置时出错')}: {e}", "ERROR")

    # ----------------------------------------------------------------------
    # 新增：创建位点转换选项卡的方法
    # ----------------------------------------------------------------------
    def _populate_locus_conversion_tab_structure(self, parent_frame):
        """
        填充位点转换工具的UI界面。
        【已修复】将基因ID输入框替换为区域输入框，以匹配任务逻辑。
        """
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 顶部的基因组选择菜单 (保持不变) ---
        assembly_ids = [_("无可用版本")]
        if self.genome_sources_data:
            ids = list(self.genome_sources_data.keys())
            if ids:
                assembly_ids = ids

        top_frame = ctk.CTkFrame(parent_frame)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(top_frame, text=_("源基因组:"), font=self.app_font).grid(row=0, column=0, padx=(10, 5), pady=5,
                                                                              sticky="w")
        self.locus_source_assembly_dropdown = ctk.CTkOptionMenu(
            top_frame, variable=self.selected_locus_source_assembly, values=assembly_ids,
            font=self.app_font, dropdown_font=self.app_font, command=self._on_locus_assembly_selection
        )
        self.locus_source_assembly_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(top_frame, text=_("目标基因组:"), font=self.app_font).grid(row=0, column=2, padx=(10, 5), pady=5,
                                                                                sticky="w")
        self.locus_target_assembly_dropdown = ctk.CTkOptionMenu(
            top_frame, variable=self.selected_locus_target_assembly, values=assembly_ids,
            font=self.app_font, dropdown_font=self.app_font, command=self._on_locus_assembly_selection
        )
        self.locus_target_assembly_dropdown.grid(row=0, column=3, padx=(5, 10), pady=5, sticky="ew")

        # --- 【核心修改】将基因ID输入框替换为区域输入框 ---
        input_card = ctk.CTkFrame(parent_frame, fg_color="transparent")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        input_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_card, text=_("输入染色体区域:"), font=self.app_font_bold).grid(row=0, column=0, sticky="w")

        # 创建正确的 Entry 控件，并赋值给 self.locus_conversion_region_entry
        self.locus_conversion_region_entry = ctk.CTkEntry(
            input_card,
            font=self.app_font,
            placeholder_text=_("例如: A03:1000-2000")
        )
        self.locus_conversion_region_entry.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        # --- 修改结束 ---

        # --- 输出和运行按钮 (保持不变, 行号顺延) ---
        output_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        output_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(10, 0))
        output_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font_bold).grid(row=0, column=0,
                                                                                             sticky="w", pady=(0, 5))
        self.locus_conversion_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font)
        self.locus_conversion_output_csv_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(output_frame, text=_("选择目录"), font=self.app_font,
                      command=lambda: self._select_output_directory(self.locus_conversion_output_csv_entry)).grid(row=1,
                                                                                                                  column=1,
                                                                                                                  sticky="e")

        run_button = ctk.CTkButton(parent_frame, text=_("开始转换"), font=self.app_font_bold,
                                   command=self.start_locus_conversion_task)
        run_button.grid(row=3, column=0, padx=10, pady=(20, 10), sticky="e")

    # ----------------------------------------------------------------------
    # 新增：启动位点转换任务的槽函数
    # ----------------------------------------------------------------------
    def start_locus_conversion_task(self):
        """
        启动位点转换任务，使用正确的参数名调用后端函数。
        """

        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 从UI控件获取数据
        source_assembly = self.selected_locus_source_assembly.get()
        target_assembly = self.selected_locus_target_assembly.get()
        # "位点转换"的核心是通过区域进行查询
        region_str = self.locus_conversion_region_entry.get().strip()
        output_csv = self.locus_conversion_output_csv_entry.get().strip() or None

        # 输入验证
        if not all([source_assembly, target_assembly, region_str]):
            self.show_error_message(_("输入缺失"), _("请填写所有必要的输入字段（源基因组、目标基因组、染色体区域）。"))
            return

        # 解析区域字符串
        region_tuple = None
        try:
            chrom, pos_range = region_str.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom, start, end)
        except ValueError:
            self.show_error_message(_("输入错误"), _("染色体区域格式不正确。请使用 'A03:1000-2000' 格式。"))
            return

        # 更新UI状态，准备执行任务
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("位点转换")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        # 定义并启动后台线程
        def task_wrapper():
            run_homology_map_standalone(
                config=self.current_config,
                source_assembly_id=source_assembly,
                target_assembly_id=target_assembly,
                region=region_tuple,
                gene_ids=None,
                output_csv_path=output_csv,
                status_callback=self.gui_status_callback,
                progress_callback=self.gui_progress_callback,
                task_done_callback=lambda s: self.task_done_callback(s, self.active_task_name)
            )

        threading.Thread(target=task_wrapper, daemon=True).start()


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

    def _populate_xlsx_to_csv_tab_structure(self, page):
        """创建“XLSX转CSV”页面的UI"""
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)  # Allow card to expand

        ctk.CTkLabel(page, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app_font_bold, wraplength=500).grid(
            row=0, column=0, pady=(20, 10), padx=20, sticky="n")  # Use grid

        # 添加功能说明标签
        info_label = ctk.CTkLabel(page, text=_(
            "此工具会将一个Excel文件中的所有工作表(Sheet)内容合并到一个CSV文件中。\n适用于所有Sheet表头格式一致的情况。"),
                                  font=self.app_font, wraplength=600, justify="center",
                                  text_color=self.secondary_text_color)
        info_label.grid(row=1, column=0, pady=(0, 20), padx=30, sticky="ew")  # Use grid

        # 创建一个卡片容纳主要控件
        card = ctk.CTkFrame(page)
        card.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)  # Use grid, make it expandable
        card.grid_columnconfigure(1, weight=1)

        # 输入文件选择
        ctk.CTkLabel(card, text=_("输入Excel文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=(20, 10),
                                                                              sticky="w")
        self.xlsx_input_entry = ctk.CTkEntry(card, placeholder_text=_("选择要转换的 .xlsx 文件"), height=35,
                                             font=self.app_font)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        ctk.CTkButton(card, text=_("浏览..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(row=0,
                                                                                                                  column=2,
                                                                                                                  padx=10,
                                                                                                                  pady=(
                                                                                                                      20,
                                                                                                                      10))

        # 输出文件选择
        ctk.CTkLabel(card, text=_("输出CSV文件:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                            sticky="w")
        self.csv_output_entry = ctk.CTkEntry(card, placeholder_text=_("选择保存位置和文件名 (不填则自动命名)"),
                                             height=35, font=self.app_font)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(card, text=_("另存为..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        # 开始转换按钮
        self.convert_start_button = ctk.CTkButton(page, text=_("开始转换"), height=40,
                                                  command=self.start_xlsx_to_csv_conversion, font=self.app_font_bold)
        self.convert_start_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(20, 20))  # Use grid


    def _on_tab_change(self, tab_name: str):
        """
        当 CustomTkinter Tabview 的选项卡发生变化时触发。
        tab_name: 当前选中的选项卡名称。
        """
        self._log_to_viewer(f"{_('选项卡已切换到:')} {tab_name}", "DEBUG")

        # 当切换到“数据工具”选项卡时，确保基因组下拉菜单是最新的
        # 因为数据下载、基因组转换、功能注释等工具都在这个 Tabview 内部
        if tab_name == self.tab_keys["homology"] or \
                tab_name == self.tab_keys["locus_conversion"] or \
                tab_name == self.tab_keys["gff_query"] or \
                tab_name == self.tab_keys["annotation"] or \
                tab_name == self.tab_keys["download"]:  # Download tab also uses genome sources
            self._update_assembly_id_dropdowns()

    def _update_homology_file_display_for_locus_tab(self):
        """
        根据位点转换选项卡中选择的源基因组和目标基因组，
        自动识别并更新同源文件路径的显示。
        """
        source_assembly_id = self.selected_locus_source_assembly.get()
        target_assembly_id = self.selected_locus_target_assembly.get()

        if not self.current_config or not self.genome_sources_data:
            self.locus_conversion_s2b_file_path_var.set(_("请先加载配置并确保基因组源数据可用"))
            self.locus_conversion_b2t_file_path_var.set(_("请先加载配置并确保基因组源数据可用"))
            return

        # 处理源到桥梁文件 (Source to Bridge)
        source_genome_info = self.genome_sources_data.get(source_assembly_id)
        if source_genome_info and hasattr(source_genome_info, 'homology_ath_url') and source_genome_info.homology_ath_url: # Added hasattr check
            from cotton_toolkit.config.loader import get_local_downloaded_file_path # Local import

            s2b_path = get_local_downloaded_file_path(self.current_config, source_genome_info, 'homology_ath')
            if s2b_path and os.path.exists(s2b_path):
                self.locus_conversion_s2b_file_path_var.set(os.path.basename(s2b_path))
                self.locus_conversion_s2b_file_label.configure(fg_color="transparent")
            else:
                self.locus_conversion_s2b_file_path_var.set(_("未找到文件，请检查下载或配置。") + f"\n({s2b_path or ''})")
                self.locus_conversion_s2b_file_label.configure(text_color="red")
        else:
            self.locus_conversion_s2b_file_path_var.set(_("源基因组未配置同源文件URL。"))
            self.locus_conversion_s2b_file_label.configure(text_color="orange")

        # 处理桥梁到目标文件 (Bridge to Target)
        target_genome_info = self.genome_sources_data.get(target_assembly_id)
        if target_genome_info and hasattr(target_genome_info, 'homology_ath_url') and target_genome_info.homology_ath_url: # Added hasattr check
            from cotton_toolkit.config.loader import get_local_downloaded_file_path # Local import

            b2t_path = get_local_downloaded_file_path(self.current_config, target_genome_info, 'homology_ath')
            if b2t_path and os.path.exists(b2t_path):
                self.locus_conversion_b2t_file_path_var.set(os.path.basename(b2t_path))
                self.locus_conversion_b2t_file_label.configure(fg_color="transparent")
            else:
                self.locus_conversion_b2t_file_path_var.set(_("未找到文件，请检查下载或配置。") + f"\n({b2t_path or ''})")
                self.locus_conversion_b2t_file_label.configure(text_color="red")
        else:
            self.locus_conversion_b2t_file_path_var.set(_("目标基因组未配置同源文件URL。"))
            self.locus_conversion_b2t_file_label.configure(text_color="orange")

    def _auto_identify_genome_version(self, gene_input_textbox: ctk.CTkTextbox, target_assembly_var: tk.StringVar):
        """
        从文本框中读取基因ID，尝试自动识别基因组版本，并更新下拉菜单。
        """
        current_text = gene_input_textbox.get("1.0", tk.END).strip()
        if not current_text or current_text == self.placeholder_genes_homology_key or current_text == self.placeholder_genes_gff_key:
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

    def _populate_genome_identifier_tab_structure(self, parent_frame):
        """
        填充“基因组类别鉴定”工具的UI界面。
        """
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(1, weight=1)

        # --- 标题和描述 ---
        info_frame = ctk.CTkFrame(parent_frame)
        info_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(info_frame, text=_("基因组类别鉴定工具"), font=ctk.CTkFont(size=15, weight="bold"))
        title_label.grid(row=0, column=0, padx=10, pady=(5, 2), sticky="w")

        desc_label = ctk.CTkLabel(info_frame, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"),
                                  wraplength=400, justify="left")
        desc_label.grid(row=1, column=0, padx=10, pady=(2, 5), sticky="w")

        warning_label = ctk.CTkLabel(info_frame,
                                     text=_("注意：以 'scaffold'、'Unknown' 或染色体编号（如 'Chr'）开头的ID无法用于检查。"),
                                     font=ctk.CTkFont(size=12), text_color="orange", wraplength=400, justify="left")
        warning_label.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="w")

        # --- 基因输入文本框 ---
        self.identifier_genes_textbox = ctk.CTkTextbox(parent_frame, height=200)
        self.identifier_genes_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # --- 操作区域 ---
        action_frame = ctk.CTkFrame(parent_frame)
        action_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        identify_button = ctk.CTkButton(action_frame, text=_("开始鉴定"), command=self._run_genome_identification)
        identify_button.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.identifier_result_label = ctk.CTkLabel(action_frame, text=_("鉴定结果将显示在这里。"),
                                                    font=ctk.CTkFont(size=13))
        self.identifier_result_label.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def _populate_genome_identifier_tab_structure(self, parent_frame):
        """
        填充“基因组类别鉴定”工具的UI界面。
        """
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(1, weight=1)

        # --- 标题和描述 ---
        info_frame = ctk.CTkFrame(parent_frame)
        info_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(info_frame, text=_("基因组类别鉴定工具"), font=ctk.CTkFont(size=15, weight="bold"))
        title_label.grid(row=0, column=0, padx=10, pady=(5, 2), sticky="w")

        desc_label = ctk.CTkLabel(info_frame, text=_("在此处粘贴一个基因列表，工具将尝试识别它们属于哪个基因组版本。"),
                                  wraplength=400, justify="left")
        desc_label.grid(row=1, column=0, padx=10, pady=(2, 5), sticky="w")

        warning_label = ctk.CTkLabel(info_frame,
                                     text=_("注意：以 'scaffold'、'Unknown' 或染色体编号（如 'Chr'）开头的ID无法用于检查。"),
                                     font=ctk.CTkFont(size=12), text_color="orange", wraplength=400, justify="left")
        warning_label.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="w")

        # --- 基因输入文本框 ---
        self.identifier_genes_textbox = ctk.CTkTextbox(parent_frame, height=200)
        self.identifier_genes_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # --- 操作区域 ---
        action_frame = ctk.CTkFrame(parent_frame)
        action_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        identify_button = ctk.CTkButton(action_frame, text=_("开始鉴定"), command=self._run_genome_identification)
        identify_button.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.identifier_result_label = ctk.CTkLabel(action_frame, text=_("鉴定结果将显示在这里。"),
                                                    font=ctk.CTkFont(size=13))
        self.identifier_result_label.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def _run_genome_identification(self):
        """
        执行基因组类别鉴定。
        """
        self.identifier_result_label.configure(text=_("正在鉴定中..."))
        gene_ids_text = self.identifier_genes_textbox.get("1.0", tk.END).strip()

        if not gene_ids_text:
            self.identifier_result_label.configure(text=_("请输入基因ID。"), text_color="orange")
            return

        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids:
            self.identifier_result_label.configure(text=_("请输入有效的基因ID。"), text_color="orange")
            return

        if not self.genome_sources_data:
            self._log_to_viewer(_("警告: 基因组源数据未加载，无法进行鉴定。"), "WARNING")
            self.identifier_result_label.configure(text=_("错误：基因组源未加载。"), text_color="red")
            return

        identified_assembly = identify_genome_from_gene_ids(gene_ids, self.genome_sources_data, self._log_to_viewer)

        if identified_assembly:
            result_text = f"鉴定结果: {identified_assembly}"
            self.identifier_result_label.configure(text=_(result_text), text_color=self.theme_manager.get_color("text"))
        else:
            self.identifier_result_label.configure(text=_("未能识别到匹配的基因组。"), text_color="orange")

    def _run_genome_identification(self):
        """
        执行基因组类别鉴定。
        """
        self.identifier_result_label.configure(text=_("正在鉴定中..."))
        gene_ids_text = self.identifier_genes_textbox.get("1.0", tk.END).strip()

        if not gene_ids_text:
            self.identifier_result_label.configure(text=_("请输入基因ID。"), text_color="orange")
            return

        gene_ids = [gene.strip() for gene in gene_ids_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids:
            self.identifier_result_label.configure(text=_("请输入有效的基因ID。"), text_color="orange")
            return

        if not self.genome_sources_data:
            self._log_to_viewer(_("警告: 基因组源数据未加载，无法进行鉴定。"), "WARNING")
            self.identifier_result_label.configure(text=_("错误：基因组源未加载。"), text_color="red")
            return

        identified_assembly = identify_genome_from_gene_ids(gene_ids, self.genome_sources_data, self._log_to_viewer)

        if identified_assembly:
            result_text = f"鉴定结果: {identified_assembly}"
            self.identifier_result_label.configure(text=_(result_text), text_color=self.theme_manager.get_color("text"))
        else:
            self.identifier_result_label.configure(text=_("未能识别到匹配的基因组。"), text_color="orange")

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



    def _on_homology_gene_input_change(self, event=None):
        """
        同源映射输入框基因ID变化时触发基因组自动识别。
        """
        self._auto_identify_genome_version(self.homology_map_genes_textbox, self.selected_homology_source_assembly)

    def _on_gff_query_gene_input_change(self, event=None):
        """
        GFF查询输入框基因ID变化时触发基因组自动识别。
        """
        self._auto_identify_genome_version(self.gff_query_genes_textbox, self.selected_gff_query_assembly)

    def _on_annotation_gene_input_change(self, event=None):
        """
        功能注释输入框基因ID变化时触发基因组自动识别。
        """
        self._auto_identify_genome_version(self.annotation_genes_textbox, self.selected_annotation_assembly)

    def _on_homology_assembly_selection(self, event=None):
        """
        当同源映射工具中的源或目标基因组被选择时，更新对应的同源文件路径显示。
        【已修复】使用 get_local_downloaded_file_path 自动、准确地确定路径。
        """
        if not self.current_config or not self.genome_sources_data:
            self.homology_map_s2b_file_path_var.set(_("配置或基因组数据未加载"))
            self.homology_map_b2t_file_path_var.set(_("配置或基因组数据未加载"))
            return

        source_assembly_id = self.selected_homology_source_assembly.get()
        target_assembly_id = self.selected_homology_target_assembly.get()
        default_color = self.default_label_text_color
        warning_color = ("#D32F2F", "#E57373")  # 用于未找到文件的红色警告

        # 更新 源 -> 桥梁 的文件路径
        s2b_path_display = _("请先选择源基因组")
        if source_assembly_id:
            source_info = self.genome_sources_data.get(source_assembly_id)
            if source_info:
                # 使用辅助函数自动确定路径
                s2b_path = get_local_downloaded_file_path(self.current_config, source_info, 'homology_ath')
                if s2b_path and os.path.exists(s2b_path):
                    s2b_path_display = s2b_path
                    if hasattr(self, 'homology_map_s2b_file_label'):
                        self.homology_map_s2b_file_label.configure(text_color=default_color)
                else:
                    s2b_path_display = _("文件未找到: {}").format(os.path.basename(s2b_path) if s2b_path else 'N/A')
                    if hasattr(self, 'homology_map_s2b_file_label'):
                        self.homology_map_s2b_file_label.configure(text_color=warning_color)
        if hasattr(self, 'homology_map_s2b_file_path_var'):
            self.homology_map_s2b_file_path_var.set(s2b_path_display)

        # 更新 桥梁 -> 目标 的文件路径
        b2t_path_display = _("请先选择目标基因组")
        if target_assembly_id:
            target_info = self.genome_sources_data.get(target_assembly_id)
            if target_info:
                # 使用辅助函数自动确定路径
                b2t_path = get_local_downloaded_file_path(self.current_config, target_info, 'homology_ath')
                if b2t_path and os.path.exists(b2t_path):
                    b2t_path_display = b2t_path
                    if hasattr(self, 'homology_map_b2t_file_label'):
                        self.homology_map_b2t_file_label.configure(text_color=default_color)
                else:
                    b2t_path_display = _("文件未找到: {}").format(os.path.basename(b2t_path) if b2t_path else 'N/A')
                    if hasattr(self, 'homology_map_b2t_file_label'):
                        self.homology_map_b2t_file_label.configure(text_color=warning_color)
        if hasattr(self, 'homology_map_b2t_file_path_var'):
            self.homology_map_b2t_file_path_var.set(b2t_path_display)

    def _on_locus_assembly_selection(self, event=None):
        """
        当位点转换工具中的源或目标基因组被选择时，更新UI。
        【已修复】使用 get_local_downloaded_file_path 自动、准确地确定路径。
        """
        if not self.current_config or not self.genome_sources_data:
            self.locus_conversion_s2b_file_path_var.set(_("配置或基因组数据未加载"))
            self.locus_conversion_b2t_file_path_var.set(_("配置或基因组数据未加载"))
            return

        source_assembly_id = self.selected_locus_source_assembly.get()
        target_assembly_id = self.selected_locus_target_assembly.get()
        default_color = self.default_label_text_color
        warning_color = ("#D32F2F", "#E57373")  # 用于未找到文件的红色警告

        # 更新 源 -> 桥梁 的文件路径
        s2b_path_display = _("请先选择源基因组")
        if source_assembly_id:
            source_info = self.genome_sources_data.get(source_assembly_id)
            if source_info:
                s2b_path = get_local_downloaded_file_path(self.current_config, source_info, 'homology_ath')
                if s2b_path and os.path.exists(s2b_path):
                    s2b_path_display = s2b_path
                    if hasattr(self, 'locus_conversion_s2b_file_label'):
                        self.locus_conversion_s2b_file_label.configure(text_color=default_color)
                else:
                    s2b_path_display = _("文件未找到: {}").format(os.path.basename(s2b_path) if s2b_path else 'N/A')
                    if hasattr(self, 'locus_conversion_s2b_file_label'):
                        self.locus_conversion_s2b_file_label.configure(text_color=warning_color)
        if hasattr(self, 'locus_conversion_s2b_file_path_var'):
            self.locus_conversion_s2b_file_path_var.set(s2b_path_display)

        # 更新 桥梁 -> 目标 的文件路径
        b2t_path_display = _("请先选择目标基因组")
        if target_assembly_id:
            target_info = self.genome_sources_data.get(target_assembly_id)
            if target_info:
                b2t_path = get_local_downloaded_file_path(self.current_config, target_info, 'homology_ath')
                if b2t_path and os.path.exists(b2t_path):
                    b2t_path_display = b2t_path
                    if hasattr(self, 'locus_conversion_b2t_file_label'):
                        self.locus_conversion_b2t_file_label.configure(text_color=default_color)
                else:
                    b2t_path_display = _("文件未找到: {}").format(os.path.basename(b2t_path) if b2t_path else 'N/A')
                    if hasattr(self, 'locus_conversion_b2t_file_label'):
                        self.locus_conversion_b2t_file_label.configure(text_color=warning_color)
        if hasattr(self, 'locus_conversion_b2t_file_path_var'):
            self.locus_conversion_b2t_file_path_var.set(b2t_path_display)


    def _add_placeholder(self, textbox_widget, placeholder_text, force=False):
        """
        如果文本框为空，则向其添加占位符文本和样式（斜体、灰色）。
        """
        if not textbox_widget.winfo_exists():
            return

        current_text = textbox_widget.get("1.0", tk.END).strip()

        if not current_text or force:
            if force:
                textbox_widget.delete("1.0", tk.END)

            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[
                1]

            # --- 同时设置字体和颜色 ---
            textbox_widget.configure(font=self.app_font_italic, text_color=placeholder_color_value)
            textbox_widget.insert("0.0", placeholder_text)

    def _clear_placeholder(self, textbox_widget, placeholder_text):
        """
        如果文本框中的内容是占位符，则清除它，并恢复正常字体和颜色。
        """
        if not textbox_widget.winfo_exists():
            return

        current_text = textbox_widget.get("1.0", tk.END).strip()

        if current_text == placeholder_text:
            textbox_widget.delete("1.0", tk.END)
            # --- 关键修改：同时恢复字体和颜色 ---
            textbox_widget.configure(font=self.app_font, text_color=self.default_text_color)


    def _on_gff_query_assembly_selection(self, choice):
        """处理GFF基因查询页面基因组选择事件。"""
        self._log_to_viewer(f"{_('GFF基因查询 - 基因组选择')}: {self.selected_gff_query_assembly.get()}")
        # 此处通常不需要更新文件显示，因为GFF文件路径是在任务启动时确定的
        # 但如果未来有类似同源文件的自动识别需求，可以在这里添加。


    def reconfigure_logging(self, log_level_str: str):
        """根据给定的字符串，动态地重新配置应用的根日志级别。"""
        try:
            log_level = getattr(logging, log_level_str.upper(), logging.INFO)
            # 获取根logger并设置其级别
            logging.getLogger().setLevel(log_level)
            self._log_to_viewer(f"日志级别已更新为: {log_level_str}", "INFO")
            # 用DEBUG级别发送一条测试消息，如果能看到，说明设置成功
            logging.debug("这是一个 DEBUG 级别的测试消息。如果能看到，说明级别设置成功。")
        except Exception as e:
            self._log_to_viewer(f"错误: 动态更新日志级别失败: {e}", "ERROR")


if __name__ == "__main__":  #
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()  #
    app.mainloop()  #
