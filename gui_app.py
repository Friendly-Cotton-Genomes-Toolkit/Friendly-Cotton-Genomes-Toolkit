# gui_app.py
import json
import logging
import sys
from typing import Callable, Dict, Optional
from PIL import Image
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading
from queue import Queue
import os
import time
import yaml
import webbrowser
import pandas as pd

try:
    from cotton_toolkit.tools_pipeline import run_functional_annotation, run_ai_task
    from cotton_toolkit.config.loader import load_config, save_config_to_yaml, get_genome_data_sources, \
        generate_default_config_files
    from cotton_toolkit.core.downloader import download_genome_data
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg, run_homology_mapping_standalone, \
        run_gff_gene_lookup_standalone
    from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text
    from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL

    COTTON_TOOLKIT_LOADED = True
    print("INFO: gui_app.py - Successfully imported COTTON_TOOLKIT modules.")  #
except ImportError as e:
    print(f"错误：无法导入 cotton_toolkit 模块 (gui_app.py): {e}")  #
    COTTON_TOOLKIT_LOADED = False  #
    PKG_VERSION = "DEV"
    PKG_HELP_URL = "https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/docs/HELP.md"  #


    def load_config(path):
        print(f"MOCK (gui_app.py): load_config({path})")  #
        return {"mock_config": True, "i18n_language": "zh-hans", "_config_file_abs_path_": os.path.abspath(path),  #
                "downloader": {"download_output_base_dir": "mock_gui_downloads_from_config/", "force_download": True,  #
                               "genome_sources_file": "mock_genome_sources.yml"},  #
                "integration_pipeline": {"input_excel_path": "mock_gui_integration_input_from_config.xlsx",  #
                                         "output_sheet_name": "MockGUIOutputSheetFromConfig"}}  #


    def save_config_to_yaml(config_dict, file_path):
        print(f"MOCK (gui_app.py): save_config_to_yaml({file_path})")  #
        with open(file_path, 'w', encoding='utf-8') as f: yaml.dump(config_dict, f)  #
        return True  #


    def get_genome_data_sources(main_config):
        print(f"MOCK (gui_app.py): get_genome_data_sources called")  #
        return {"MOCK_GS_1": {"species_name": "Mock Genome 1"}}  #


    def generate_default_config_files(output_dir, overwrite=False, main_config_filename="config.yml",
                                      genome_sources_filename="genome_sources_list.yml"):
        print(f"MOCK (gui_app.py): generate_default_config_files called for {output_dir}")  #
        os.makedirs(output_dir, exist_ok=True)  #
        main_cfg_path_ret = os.path.join(output_dir, main_config_filename)  #
        gs_cfg_path_ret = os.path.join(output_dir, genome_sources_filename)  #
        with open(main_cfg_path_ret, 'w') as f: f.write("mock_config: true\n")  #
        with open(gs_cfg_path_ret, 'w') as f: f.write("mock_gs: true\n")  #
        return True, main_cfg_path_ret, gs_cfg_path_ret  #


    def download_genome_data(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("下载")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.DOWNLOAD_TASK_KEY, True, task_display_name)  #


    def integrate_bsa_with_hvg(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("整合分析")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.INTEGRATE_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_homology_mapping_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("同源映射")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.HOMOLOGY_MAP_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_gff_gene_lookup_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("GFF基因查询")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.GFF_QUERY_TASK_KEY, True, task_display_name)  #
        return True  #


    def setup_cli_i18n(language_code='en', app_name='cotton_toolkit'):  #
        return lambda s: str(s) + f" (mock_{language_code})"  #

# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #


def get_about_text(translator: Callable[[str], str]) -> Dict[str, str]:
    """
    生成结构化的、可翻译的“关于”信息。

    Args:
        translator: 翻译函数 (例如 gettext.gettext)。

    Returns:
        一个包含关于信息的字典。
    """
    _ = translator
    return {
        "title": _("友好棉花基因组工具包 (FCGT)"),
        "subtitle": f"--- {_('由 Gemini AI 辅助开发 · 开源学术项目')} ---",
        "version_info": f"{_('版本')}: {PKG_VERSION}",
        "author_info": f"{_('作者')}: PureAmaya",
        "license_info": f"{_('开源许可')}: Apache License 2.0",
        "description_l1": _("本工具包为棉花基因组数据分析提供专业、易用的工具支持，"),
        "description_l2": _("聚焦于功能缺失基因筛选、同源映射与整合分析。"),
        "help_url_text": _("在线帮助文档"),
        "help_url_target": PKG_HELP_URL,
    }


class AdvancedConfigEditorWindow(ctk.CTkToplevel):
    """
    高级配置编辑器的独立窗口
    """

    def __init__(self, master, config_data: Dict, config_path: str):
        super().__init__(master)

        self.master = master
        self.transient(master)
        self.title(_("高级配置编辑器"))
        self.geometry("800x650")
        self.minsize(700, 550)

        self.original_config = config_data
        self.config_path = config_path
        self.app_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14)
        self.app_font_bold = ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold")

        self.translatable_widgets = {}
        self.editor_dl_force_var = tk.BooleanVar(value=config_data.get("downloader", {}).get("force_download", False))

        self._create_widgets()
        self._apply_config_to_editor_ui()

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.grab_release()
        self.destroy()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        scrollable_frame = ctk.CTkScrollableFrame(self, label_text=_("详细参数配置"), label_font=self.app_font_bold)
        scrollable_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        scrollable_frame.grid_columnconfigure(1, weight=1)

        main_config_frame = ctk.CTkFrame(scrollable_frame)
        main_config_frame.pack(fill="x", expand=True, pady=10, padx=5)
        main_config_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(main_config_frame, text=_("主配置文件 (config.yml)"), font=self.app_font_bold).grid(row=0,
                                                                                                         column=0,
                                                                                                         columnspan=2,
                                                                                                         pady=(10, 15),
                                                                                                         padx=10,
                                                                                                         sticky="w")

        ctk.CTkLabel(main_config_frame, text=_("下载器输出目录:"), font=self.app_font).grid(row=1, column=0, padx=10,
                                                                                            pady=5, sticky="w")
        self.editor_dl_output_dir = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)
        self.editor_dl_output_dir.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(main_config_frame, text=_("强制下载:"), font=self.app_font).grid(row=2, column=0, padx=10, pady=5,
                                                                                      sticky="w")
        self.editor_dl_force_switch = ctk.CTkSwitch(main_config_frame, text="", variable=self.editor_dl_force_var)
        self.editor_dl_force_switch.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(main_config_frame, text=_("HTTP 代理:"), font=self.app_font).grid(row=3, column=0, padx=10, pady=5,
                                                                                       sticky="w")
        self.editor_dl_proxy_http = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30,
                                                 placeholder_text=_("例如: http://user:pass@host:port"))
        self.editor_dl_proxy_http.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(main_config_frame, text=_("HTTPS/SOCKS 代理:"), font=self.app_font).grid(row=4, column=0, padx=10,
                                                                                              pady=5, sticky="w")
        self.editor_dl_proxy_https = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30,
                                                  placeholder_text=_("例如: https://user:pass@host:port"))
        self.editor_dl_proxy_https.grid(row=4, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(main_config_frame, text=_("整合分析输入Excel:"), font=self.app_font).grid(row=5, column=0, padx=10,
                                                                                               pady=5, sticky="w")
        self.editor_pl_excel_path = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)
        self.editor_pl_excel_path.grid(row=5, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(main_config_frame, text=_("整合分析输出Sheet名:"), font=self.app_font).grid(row=6, column=0,
                                                                                                 padx=10, pady=5,
                                                                                                 sticky="w")
        self.editor_pl_output_sheet = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)
        self.editor_pl_output_sheet.grid(row=6, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(main_config_frame, text=_("GFF文件路径 (YAML格式):"), font=self.app_font).grid(row=7, column=0,
                                                                                                    padx=10, pady=5,
                                                                                                    sticky="nw")
        self.editor_pl_gff_files = ctk.CTkTextbox(main_config_frame, height=100, wrap="none", font=self.app_font)
        self.editor_pl_gff_files.grid(row=7, column=1, padx=10, pady=5, sticky="ew")

        gs_config_frame = ctk.CTkFrame(scrollable_frame)
        gs_config_frame.pack(fill="both", expand=True, pady=10, padx=5)
        gs_config_frame.grid_columnconfigure(0, weight=1)
        gs_config_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(gs_config_frame, text=_("基因组源文件 (genome_sources_list.yml)"), font=self.app_font_bold).grid(
            row=0, column=0, columnspan=2, pady=(10, 15), padx=10, sticky="w")
        self.editor_gs_raw_yaml = ctk.CTkTextbox(gs_config_frame, wrap="none", font=self.app_font)
        self.editor_gs_raw_yaml.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")

        gs_buttons_frame = ctk.CTkFrame(gs_config_frame, fg_color="transparent")
        gs_buttons_frame.grid(row=2, column=0, columnspan=2, pady=(10, 10), padx=10, sticky="e")

        self.editor_gs_load_button = ctk.CTkButton(gs_buttons_frame, text=_("从文件重载"),
                                                   command=self._load_genome_sources_to_editor, font=self.app_font)
        self.editor_gs_load_button.pack(side="left", padx=(0, 10))
        self.editor_gs_save_button = ctk.CTkButton(gs_buttons_frame, text=_("仅保存基因组源文件"),
                                                   command=self._save_genome_sources_config, font=self.app_font)
        self.editor_gs_save_button.pack(side="left")

        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=1, column=0, padx=15, pady=15, sticky="ew")
        bottom_frame.grid_columnconfigure(1, weight=1)

        self.cancel_button = ctk.CTkButton(bottom_frame, text=_("取消"), height=40, command=self.on_close,
                                           font=self.app_font_bold, fg_color="transparent", border_width=1)
        self.cancel_button.pack(side="right")
        self.save_all_button = ctk.CTkButton(bottom_frame, text=_("保存所有更改并关闭"), height=40,
                                             command=self._save_and_close, font=self.app_font_bold)
        self.save_all_button.pack(side="right", padx=(0, 10))

    def _apply_config_to_editor_ui(self):
        if not self.original_config: return

        downloader_cfg = self.original_config.get("downloader", {})
        integration_cfg = self.original_config.get("integration_pipeline", {})

        self.editor_dl_output_dir.delete(0, tk.END)
        self.editor_dl_output_dir.insert(0, downloader_cfg.get("download_output_base_dir", ""))
        self.editor_dl_force_var.set(bool(downloader_cfg.get("force_download", False)))

        proxies_cfg = downloader_cfg.get("proxies", {})
        http_proxy = proxies_cfg.get("http", "")
        https_proxy = proxies_cfg.get("https", "")
        self.editor_dl_proxy_http.delete(0, tk.END)
        self.editor_dl_proxy_http.insert(0, http_proxy if http_proxy is not None else "")
        self.editor_dl_proxy_https.delete(0, tk.END)
        self.editor_dl_proxy_https.insert(0, https_proxy if https_proxy is not None else "")

        self.editor_pl_excel_path.delete(0, tk.END)
        self.editor_pl_excel_path.insert(0, integration_cfg.get("input_excel_path", ""))
        self.editor_pl_output_sheet.delete(0, tk.END)
        self.editor_pl_output_sheet.insert(0, integration_cfg.get("output_sheet_name", ""))

        gff_files_yaml = integration_cfg.get("gff_files", {})
        try:
            gff_yaml_str = yaml.dump(gff_files_yaml, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception:
            gff_yaml_str = str(gff_files_yaml)
        self.editor_pl_gff_files.delete("1.0", tk.END)
        self.editor_pl_gff_files.insert("1.0", gff_yaml_str)

        self._load_genome_sources_to_editor()

    def _load_genome_sources_to_editor(self):
        if not self.original_config: return
        gs_file_rel = self.original_config.get("downloader", {}).get("genome_sources_file")
        if not gs_file_rel:
            self.editor_gs_raw_yaml.delete("1.0", tk.END)
            self.editor_gs_raw_yaml.insert("1.0", _("# 未在主配置中指定基因组源文件路径。"))
            return

        abs_path = os.path.join(os.path.dirname(self.config_path), gs_file_rel) if not os.path.isabs(
            gs_file_rel) and self.config_path else gs_file_rel
        if not os.path.exists(abs_path):
            self.editor_gs_raw_yaml.delete("1.0", tk.END)
            self.editor_gs_raw_yaml.insert("1.0", f"{_('# 文件不存在:')} {abs_path}")
            return

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.editor_gs_raw_yaml.delete("1.0", tk.END)
            self.editor_gs_raw_yaml.insert("1.0", content)
        except Exception as e:
            self.editor_gs_raw_yaml.delete("1.0", tk.END)
            self.editor_gs_raw_yaml.insert("1.0", f"{_('# 加载错误:')} {e}")

    def _collect_main_config_from_ui(self) -> Optional[Dict]:
        cfg = self.original_config.copy()

        downloader_cfg = cfg.setdefault("downloader", {})
        integration_cfg = cfg.setdefault("integration_pipeline", {})

        downloader_cfg["download_output_base_dir"] = self.editor_dl_output_dir.get().strip()
        downloader_cfg["force_download"] = self.editor_dl_force_var.get()

        proxies_cfg = downloader_cfg.setdefault("proxies", {})
        http_proxy_val = self.editor_dl_proxy_http.get().strip()
        proxies_cfg["http"] = http_proxy_val if http_proxy_val else None
        https_proxy_val = self.editor_dl_proxy_https.get().strip()
        proxies_cfg["https"] = https_proxy_val if https_proxy_val else None

        integration_cfg["input_excel_path"] = self.editor_pl_excel_path.get().strip()
        integration_cfg["output_sheet_name"] = self.editor_pl_output_sheet.get().strip()

        gff_yaml_str = self.editor_pl_gff_files.get("1.0", tk.END).strip()
        try:
            if gff_yaml_str:
                gff_dict = yaml.safe_load(gff_yaml_str)
                if isinstance(gff_dict, dict):
                    integration_cfg["gff_files"] = gff_dict
                else:
                    self.master.show_error_message(_("保存错误"), _("GFF文件路径的YAML格式不正确。"))
                    return None
            else:
                integration_cfg["gff_files"] = {}
        except yaml.YAMLError as e:
            self.master.show_error_message(_("保存错误"), f"{_('GFF文件路径YAML解析错误:')} {e}")
            return None

        return cfg

    def _save_genome_sources_config(self) -> bool:
        if not self.original_config:
            self.master.show_error_message(_("错误"), _("没有加载主配置文件。"))
            return False

        gs_file_rel = self.original_config.get("downloader", {}).get("genome_sources_file")
        if not gs_file_rel:
            self.master.show_warning_message(_("无法保存"), _("主配置文件中未指定基因组源文件路径。"))
            return False

        abs_path = os.path.join(os.path.dirname(self.config_path), gs_file_rel) if not os.path.isabs(
            gs_file_rel) and self.config_path else gs_file_rel
        content_to_save = self.editor_gs_raw_yaml.get("1.0", tk.END).strip()
        try:
            yaml.safe_load(content_to_save)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content_to_save)
            self.master.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))
            return True
        except Exception as e:
            self.master.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}")
            return False

    def _save_and_close(self):
        updated_config = self._collect_main_config_from_ui()
        if updated_config is None: return

        if self.master.save_config_file(config_data=updated_config):
            self._save_genome_sources_config()
            self.master.on_config_updated(updated_config)
            self.on_close()


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}

    def __init__(self):
        super().__init__()

        # --- 字体和颜色 ---
        self._setup_fonts()  # 调用新的字体设置方法
        self.secondary_text_color = ("#495057", "#999999")  # 用于次要信息标签 (亮, 暗)
        self.placeholder_color = ("#868e96", "#5c5c5c")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]

        try:
            # 从主题中获取标签的默认文字颜色（适配亮/暗模式）
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        except Exception:
            # 如果获取失败，提供一个备用的安全颜色组合 (黑/白)
            self.default_label_text_color = ("#000000", "#FFFFFF")

        # --- 窗口设置 ---
        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1000x700")
        self.minsize(1000, 700)

        # --- 状态和工具 ---
        self.current_config = None
        self.config_path = None
        self.ui_settings = {}
        self.message_queue = Queue()
        self.about_window = None
        self.config_editor_window = None
        self.translatable_widgets = {}
        self.active_task_name = None
        self.tab_keys = {
            "download": "internal_download_tab", "homology": "internal_homology_tab",
            "gff_query": "internal_gff_query_tab", "annotation": "internal_annotation_tab",
            "ai_assistant": "internal_ai_assistant_tab", "xlsx_to_csv": "internal_xlsx_to_csv_tab"
        }


        # --- 占位符 ---
        self.placeholder_genes_homology_key = "例如:\nGhir.A01G000100\nGhir.A01G000200\n(必填)"
        self.placeholder_genes_gff_key = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(与下方区域查询二选一)"

        # --- UI变量 ---
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.ai_task_type_var = tk.StringVar()
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

        # --- 新增AI助手UI变量 ---
        self.ai_task_type_var = tk.StringVar(value=_("翻译"))
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=False)
        self.kegg_path_anno_var = tk.BooleanVar(value=False)

        # --- 图标加载 ---
        self.logo_image = self._load_image_resource("logo.png", (48, 48))
        self.home_icon = self._load_image_resource("home.png")
        self.integrate_icon = self._load_image_resource("integrate.png")
        self.tools_icon = self._load_image_resource("tools.png")

        # 【新增】为新主页按钮加载图标
        self.folder_icon = self._load_image_resource("folder.png")
        self.new_file_icon = self._load_image_resource("new-file.png")
        self.help_icon = self._load_image_resource("help.png")
        self.info_icon = self._load_image_resource("info.png")
        self.settings_icon = self._load_image_resource("settings.png")

        # --- 初始化流程 ---
        self._load_ui_settings()
        self._create_layout()
        self._init_pages_and_final_setup()

    def _create_log_viewer_widgets(self):
        """创建并打包操作日志区域的全部控件。"""
        self.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(self.log_viewer_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        self.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold)
        self.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        self.translatable_widgets[self.log_viewer_label_widget] = "操作日志"

        self.clear_log_button = ctk.CTkButton(log_header_frame, text=_("清除日志"), width=80, height=28,
                                              command=self.clear_log_viewer, font=self.app_font)
        self.clear_log_button.grid(row=0, column=1, sticky="e")
        self.translatable_widgets[self.clear_log_button] = "清除日志"

        self.log_textbox = ctk.CTkTextbox(self.log_viewer_frame, height=140, state="disabled", wrap="word",
                                          font=self.app_font)
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        # 【修复】调用新方法来设置初始颜色
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


    def _init_pages_and_final_setup(self):
        self.home_frame = self._create_home_frame(self.main_content_frame)
        self.integrate_frame = self._create_integrate_frame(self.main_content_frame)
        self.tools_frame = self._create_tools_frame(self.main_content_frame)
        self._populate_tools_notebook()
        self.select_frame_by_name("home")
        self._load_initial_config()
        self.update_language_ui()
        self._update_button_states()
        self.check_queue_periodic()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_app_icon()

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

        # 6. 【关键】在窗口可见之前设置图标
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
        self.navigation_frame.grid_rowconfigure(5, weight=1)

        nav_header_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        nav_logo_label = ctk.CTkLabel(nav_header_frame, text="", image=self.logo_image)
        nav_logo_label.pack(pady=(0, 10))

        self.nav_title_label = ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold"))
        self.nav_title_label.pack()

        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=self.home_icon, font=self.app_font_bold,
                                         command=lambda: self.select_frame_by_name("home"))
        self.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.integrate_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                              text=_("整合分析"), fg_color="transparent",
                                              text_color=("gray10", "gray90"), anchor="w", image=self.integrate_icon,
                                              font=self.app_font_bold,
                                              command=lambda: self.select_frame_by_name("integrate"))
        self.integrate_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.tools_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=self.tools_icon, font=self.app_font_bold,
                                          command=lambda: self.select_frame_by_name("tools"))
        self.tools_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

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

        # 【重要补充】将控件的可选值列表注册到翻译系统
        self.translatable_widgets[self.appearance_mode_optionemenu] = ("values", ["浅色", "深色", "系统"])


    def _create_main_content_area(self, parent):
        self.main_content_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)


    def select_frame_by_name(self, name):
        # 设置按钮高亮
        self.home_button.configure(fg_color=self.home_button.cget("hover_color") if name == "home" else "transparent")
        self.integrate_button.configure(
            fg_color=self.integrate_button.cget("hover_color") if name == "integrate" else "transparent")
        self.tools_button.configure(
            fg_color=self.tools_button.cget("hover_color") if name == "tools" else "transparent")

        # 显示对应的 frame
        self.home_frame.grid_forget()
        self.integrate_frame.grid_forget()
        self.tools_frame.grid_forget()

        if name == "home":
            self.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "integrate":
            self.integrate_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "tools":
            self.tools_frame.grid(row=0, column=0, sticky="nsew")

    def _create_status_bar(self, parent):
        self.status_bar_frame = ctk.CTkFrame(parent, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar_frame.grid_columnconfigure(0, weight=1)
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()

    def _create_home_frame(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # --- 顶部信息区 ---
        top_info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        top_info_frame.pack(pady=(50, 20), padx=30, fill="x")

        ctk.CTkLabel(top_info_frame, text=_(self.title_text_key), font=self.app_title_font).pack(pady=(0, 10))

        about_content = get_about_text(translator=_)
        subtitle_text = about_content.get("subtitle", "")
        ctk.CTkLabel(top_info_frame, text=subtitle_text, font=self.app_subtitle_font,
                     text_color=self.secondary_text_color).pack(pady=(0, 20))

        # 【优化】将当前配置信息移到主区域，更醒目
        self.config_path_label = ctk.CTkLabel(top_info_frame, text=_("未加载配置"), wraplength=500,
                                              font=ctk.CTkFont(size=13), text_color=self.secondary_text_color)
        self.translatable_widgets[self.config_path_label] = ("config_path_display", _("当前配置: {}"), _("未加载配置"))
        self.config_path_label.pack(pady=(10, 0))

        # --- 卡片式布局 ---
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.pack(pady=20, padx=20, fill="x", expand=True)
        cards_frame.grid_columnconfigure((0, 1), weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)

        # 卡片1: 配置文件操作
        config_card = ctk.CTkFrame(cards_frame)
        config_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(config_card, text=_("配置文件"), font=self.app_font_bold).pack(pady=(15, 10))

        self.load_config_button = ctk.CTkButton(config_card, text=_("加载配置文件..."), image=self.folder_icon,
                                                command=self.load_config_file, height=40, font=self.app_font)
        self.translatable_widgets[self.load_config_button] = "加载配置文件..."
        self.load_config_button.pack(pady=10, padx=20, fill="x")

        self.gen_config_button = ctk.CTkButton(config_card, text=_("生成默认配置..."), image=self.new_file_icon,
                                               command=self._generate_default_configs_gui, height=40,
                                               font=self.app_font,
                                               fg_color="transparent", border_width=1)
        self.translatable_widgets[self.gen_config_button] = "生成默认配置..."
        self.gen_config_button.pack(pady=10, padx=20, fill="x", side="bottom")

        # 卡片2: 帮助与支持
        help_card = ctk.CTkFrame(cards_frame)
        help_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(help_card, text=_("帮助与支持"), font=self.app_font_bold).pack(pady=(15, 10))

        self.help_button = ctk.CTkButton(help_card, text=_("在线帮助文档"), image=self.help_icon,
                                         command=self._open_online_help, height=40, font=self.app_font)
        self.translatable_widgets[self.help_button] = "在线帮助文档"
        self.help_button.pack(pady=10, padx=20, fill="x")

        self.about_button = ctk.CTkButton(help_card, text=_("关于本软件"), image=self.info_icon,
                                          command=self.show_about_dialog, height=40, font=self.app_font)
        self.translatable_widgets[self.about_button] = "关于本软件"
        self.about_button.pack(pady=10, padx=20, fill="x")

        self.edit_config_button = ctk.CTkButton(help_card, text=_("高级配置编辑器"), image=self.settings_icon,
                                                command=self.open_config_editor, height=40, font=self.app_font,
                                                fg_color="transparent", border_width=1)
        self.translatable_widgets[self.edit_config_button] = "高级配置编辑器"
        self.edit_config_button.pack(pady=10, padx=20, fill="x", side="bottom")

        return frame


    def _create_integrate_frame(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=_("整合分析: BSA 定位区域筛选高变异基因 (HVG)"), font=self.app_title_font).pack(
            pady=(20, 25), padx=30)

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
        self.translatable_widgets[excel_path_label] = "Excel文件路径:"
        excel_path_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_card, font=self.app_font, height=35,placeholder_text=_("点击“浏览”选择文件，或从配置加载"))
        self.translatable_widgets[self.integrate_excel_entry] = ("placeholder", _("从配置加载或在此覆盖"))
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 15), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_card, text=_("BSA数据工作表:"), font=self.app_font)
        self.translatable_widgets[bsa_sheet_label] = "BSA数据工作表:"
        bsa_sheet_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 15), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_card, text=_("HVG数据工作表:"), font=self.app_font)
        self.translatable_widgets[hvg_sheet_label] = "HVG数据工作表:"
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
        self.translatable_widgets[bsa_assembly_label] = "BSA基因组版本:"
        bsa_assembly_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 15), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_card, text=_("HVG基因组版本:"), font=self.app_font)
        self.translatable_widgets[hvg_assembly_label] = "HVG基因组版本:"
        hvg_assembly_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片3: 运行 ---
        run_card = ctk.CTkFrame(frame, fg_color="transparent")
        run_card.pack(fill="x", padx=30, pady=20)
        self.integrate_start_button = ctk.CTkButton(run_card, text=_("开始整合分析"), height=50,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始整合分析"
        self.integrate_start_button.pack(fill="x", expand=True)

        return frame

    def _create_tools_frame(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
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
        # 【新增】为新功能定义内部键名
        self.tab_keys["xlsx_to_csv"] = "internal_xlsx_to_csv_tab"

        # 重新定义完整的Tab键名列表
        self.tab_keys = {
            "download": "internal_download_tab",
            "homology": "internal_homology_tab",
            "gff_query": "internal_gff_query_tab",
            "annotation": "internal_annotation_tab",
            "ai_assistant": "internal_ai_assistant_tab",
            "xlsx_to_csv": "internal_xlsx_to_csv_tab"  # 新增
        }

        # 使用内部键名创建所有Tabs
        for internal_key in self.tab_keys.values():
            self.tools_notebook.add(internal_key)

        # 填充每个Tab的内容
        self._populate_download_tab_structure(self.tools_notebook.tab(self.tab_keys["download"]))
        self._populate_homology_map_tab_structure(self.tools_notebook.tab(self.tab_keys["homology"]))
        self._populate_gff_query_tab_structure(self.tools_notebook.tab(self.tab_keys["gff_query"]))
        self._populate_annotation_tab(self.tools_notebook.tab(self.tab_keys["annotation"]))
        self._populate_ai_assistant_tab(self.tools_notebook.tab(self.tab_keys["ai_assistant"]))
        self._populate_xlsx_to_csv_tab(self.tools_notebook.tab(self.tab_keys["xlsx_to_csv"]))  # 新增

        self.update_tools_notebook_tabs()

    def _populate_xlsx_to_csv_tab(self, page):
        """创建“XLSX转CSV”页面的UI"""
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 10), padx=20)

        # 添加功能说明标签
        info_label = ctk.CTkLabel(page, text=_(
            "此工具会将一个Excel文件中的所有工作表(Sheet)内容合并到一个CSV文件中。\n适用于所有Sheet表头格式一致的情况。"),
                                  font=self.app_font, wraplength=600, justify="center",
                                  text_color=self.secondary_text_color)
        info_label.pack(pady=(0, 20), padx=30)

        # 创建一个卡片容纳主要控件
        card = ctk.CTkFrame(page)
        card.pack(fill="x", expand=True, padx=20, pady=10)
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
        self.convert_start_button.pack(fill="x", padx=20, pady=(20, 20))

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

    def update_tools_notebook_tabs(self):
        """更新工具区域所有Tab的显示文本"""
        tab_display_names = {
            "download": _("数据下载"),
            "homology": _("基因组转换"),
            "gff_query": _("基因位点查询"),
            "annotation": _("功能注释"),
            "ai_assistant": _("AI 助手"),
            "xlsx_to_csv": _("XLSX转CSV")  # 新增
        }

        # 遍历所有内部键，为对应的Tab设置翻译后的显示文本
        for name, internal_key in self.tab_keys.items():
            display_text = tab_display_names.get(name, internal_key)
            try:
                # 使用内部键名获取Tab，然后配置其显示的text属性
                self.tools_notebook.tab(internal_key).configure(text=display_text)
            except Exception as e:
                logging.warning(f"更新Tab '{name}' 文本时失败: {e}")

    def _populate_annotation_tab(self, page):
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("对基因列表进行 GO/IPR/KEGG 功能注释"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 15), padx=20)

        input_card = ctk.CTkFrame(page)
        input_card.pack(fill="x", padx=20, pady=10)
        input_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(input_card, text=_("输入文件 (含基因ID列):"), font=self.app_font).grid(row=0, column=0, padx=10,
                                                                                            pady=10, sticky="w")
        self.anno_input_file_entry = ctk.CTkEntry(input_card, placeholder_text=_("选择一个Excel或CSV文件"), height=35,
                                                  font=self.app_font)
        self.anno_input_file_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.anno_input_file_entry, [("Table files", "*.xlsx *.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=10, pady=10)

        ctk.CTkLabel(input_card, text=_("基因ID所在列名:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                     sticky="w")
        self.anno_gene_col_entry = ctk.CTkEntry(input_card, placeholder_text=_("例如: gene, gene_id (默认: gene)"),
                                                height=35, font=self.app_font)
        self.anno_gene_col_entry.grid(row=1, column=1, columnspan=2, padx=(5, 10), sticky="ew")

        type_card = ctk.CTkFrame(page)
        type_card.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(type_card, text=_("选择注释类型 (需要本地数据库文件支持)"), font=self.app_font).pack(anchor="w",
                                                                                                          padx=10,
                                                                                                          pady=10)
        checkbox_frame = ctk.CTkFrame(type_card, fg_color="transparent")
        checkbox_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkCheckBox(checkbox_frame, text="GO", variable=self.go_anno_var, font=self.app_font).pack(side="left",
                                                                                                       padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="IPR", variable=self.ipr_anno_var, font=self.app_font).pack(side="left",
                                                                                                         padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                        font=self.app_font).pack(side="left", padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                        font=self.app_font).pack(side="left", padx=15)

        self.anno_start_button = ctk.CTkButton(page, text=_("开始功能注释"), height=40,
                                               command=self.start_annotation_task, font=self.app_font_bold)
        self.anno_start_button.pack(fill="x", padx=20, pady=20)

    def _populate_ai_assistant_tab(self, page):
        page.grid_columnconfigure(0, weight=1)

        def on_task_type_change(choice):
            if choice == _("分析"):
                self.ai_analyze_prompt_label.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")
                self.ai_analyze_prompt_textbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")
            else:
                self.ai_analyze_prompt_textbox.grid_remove()
                self.ai_analyze_prompt_label.grid_remove()

        ctk.CTkLabel(page, text=_("使用AI批量处理表格数据"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 15), padx=20)

        main_card = ctk.CTkFrame(page)
        main_card.pack(fill="both", expand=True, padx=20, pady=10)
        main_card.grid_columnconfigure(1, weight=1)
        main_card.grid_rowconfigure(3, weight=1)

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
                                                   values=[_("翻译"), _("分析")], command=on_task_type_change,
                                                   height=35, font=self.app_font, dropdown_font=self.app_font)
        self.ai_task_type_menu.grid(row=1, column=1, columnspan=2, padx=(0, 10), sticky="ew")

        self.ai_analyze_prompt_label = ctk.CTkLabel(main_card, text=_("分析提示词 (用 {text} 代表单元格内容):"),
                                                    font=self.app_font)
        self.ai_analyze_prompt_textbox = ctk.CTkTextbox(main_card, height=80, font=self.app_font)
        self.ai_analyze_prompt_textbox.insert("1.0",
                                              _("请讲解一下该字段吧：{text}。然后也请告诉我这个描述与我研究的植物雄性不育之间的关系"))
        on_task_type_change(_("翻译"))

        param_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        param_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        param_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(param_frame, text=_("源列名:"), font=self.app_font).grid(row=0, column=0, padx=5)
        self.ai_source_col_entry = ctk.CTkEntry(param_frame, placeholder_text="Description", height=35,
                                                font=self.app_font)
        self.ai_source_col_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(param_frame, text=_("新列名:"), font=self.app_font).grid(row=0, column=2, padx=5)
        self.ai_new_col_entry = ctk.CTkEntry(param_frame, placeholder_text=_("描述/解释"), height=35,
                                             font=self.app_font)
        self.ai_new_col_entry.grid(row=0, column=3, sticky="ew")

        self.ai_start_button = ctk.CTkButton(page, text=_("开始AI任务"), height=40, command=self.start_ai_task,
                                             font=self.app_font_bold)
        self.ai_start_button.pack(fill="x", padx=20, pady=20)

    def start_annotation_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.anno_input_file_entry.get().strip()
        gene_col = self.anno_gene_col_entry.get().strip()
        output_dir_parent = os.path.dirname(input_file) if input_file else "."
        output_dir = os.path.join(output_dir_parent, "annotation_results")

        if not input_file or not gene_col:
            self.show_error_message(_("输入缺失"), _("请输入文件路径和基因列名。"));
            return

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        if not anno_types:
            self.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。"));
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
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.ai_input_file_entry.get().strip()
        source_col = self.ai_source_col_entry.get().strip()
        new_col = self.ai_new_col_entry.get().strip()
        task_type_display = self.ai_task_type_var.get()
        task_type = "translate" if task_type_display == _("翻译") else "analyze"
        prompt = self.ai_analyze_prompt_textbox.get("1.0", tk.END).strip() if task_type == 'analyze' else None

        if not all([input_file, source_col, new_col]):
            self.show_error_message(_("输入缺失"), _("请输入文件路径、源列名和新列名。")); return

        output_dir_parent = os.path.dirname(input_file)
        output_dir = os.path.join(output_dir_parent, "ai_results")

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("AI 助手")
        self._log_to_viewer(f"{self.active_task_name} ({task_type_display}) {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        threading.Thread(target=run_ai_task, kwargs={
            "config": self.current_config, "input_file": input_file, "output_dir": output_dir,
            "source_column": source_col, "new_column": new_col, "task_type": task_type,
            "custom_prompt_template": prompt, "status_callback": self.gui_status_callback,
        }, daemon=True).start()


    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(placeholder_text_key)

            # 【修复】根据当前外观模式动态选择单一颜色值
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

    def show_about_dialog(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.focus_set()
            return

        # 1. 创建窗口并立即隐藏
        self.about_window = ctk.CTkToplevel(self)
        self.about_window.withdraw()

        # 2. 设置窗口基础属性
        self.about_window.title(_("关于"))
        self.about_window.transient(self)
        self.about_window.resizable(False, False)

        # 3. 创建并打包所有内部控件 (这部分代码不变)
        about_frame = ctk.CTkFrame(self.about_window)
        about_frame.pack(fill="both", expand=True, padx=25, pady=20)
        try:
            logo_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_image_path = os.path.join(logo_path, "icon.ico")
            if os.path.exists(icon_image_path):
                logo_image = ctk.CTkImage(light_image=Image.open(icon_image_path),
                                          dark_image=Image.open(icon_image_path), size=(64, 64))
                ctk.CTkLabel(about_frame, image=logo_image, text="").pack(pady=(10, 10))
        except Exception as e:
            print(f"警告: 无法加载Logo图片: {e}")
        about_content = get_about_text(translator=_)
        ctk.CTkLabel(about_frame, text=about_content.get("title", ""), font=self.app_font_bold).pack(pady=(5, 5))
        ctk.CTkLabel(about_frame, text=about_content.get("subtitle", ""), font=self.app_font).pack(pady=(0, 15))
        info_frame = ctk.CTkFrame(about_frame, fg_color="transparent")
        info_frame.pack(pady=5)
        ctk.CTkLabel(info_frame, text=about_content.get("version_info", ""), font=self.app_font).pack(side="left",
                                                                                                      padx=10)
        ctk.CTkLabel(info_frame, text=about_content.get("author_info", ""), font=self.app_font).pack(side="left",
                                                                                                     padx=10)
        ctk.CTkLabel(about_frame, text=about_content.get("license_info", ""), font=self.app_font).pack(pady=5)
        ctk.CTkLabel(about_frame,
                     text=about_content.get("description_l1", "") + "\n" + about_content.get("description_l2", ""),
                     font=self.app_font, justify="center").pack(pady=10)
        hyperlink_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14, underline=True)
        url_target = about_content.get("help_url_target")
        link_frame = ctk.CTkFrame(about_frame, fg_color="transparent")
        link_frame.pack(pady=10)
        ctk.CTkLabel(link_frame, text=f"{about_content.get('help_url_text', '帮助文档')}: ", font=self.app_font).pack(
            side="left")
        url_label = ctk.CTkLabel(link_frame, text='Github', font=hyperlink_font, text_color=("#1f6aa5", "#4a90e2"),
                                 cursor="hand2")
        url_label.pack(side="left", padx=5)
        url_label.bind("<Button-1>", lambda e: webbrowser.open_new(url_target))
        ctk.CTkButton(about_frame, text=_("关闭"), command=self.about_window.destroy, font=self.app_font).pack(
            pady=(20, 10))

        # 4. 强制更新以计算窗口的最终所需尺寸
        self.about_window.update_idletasks()

        # 5. 计算并设置屏幕居中位置
        dialog_width = self.about_window.winfo_reqwidth()
        dialog_height = self.about_window.winfo_reqheight()
        screen_width = self.about_window.winfo_screenwidth()
        screen_height = self.about_window.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        self.about_window.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 6. 【关键】在窗口可见之前设置图标
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                self.about_window.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 设置'关于'窗口图标失败: {e}")

        # 7. 一切就绪后，显示窗口
        self.about_window.deiconify()

        # 8. 捕获焦点并等待
        self.about_window.grab_set()
        self.about_window.wait_window()



    def _create_config_widgets_structure(self):
        self.config_frame = ctk.CTkFrame(self.main_container)
        self.config_frame.pack(side="top", pady=(5, 5), padx=10, fill="x")
        self.config_frame.grid_columnconfigure(0, weight=1)
        self.config_path_label_base_key = "配置文件"
        self.config_path_display_part = lambda: os.path.basename(self.config_path) if self.config_path else _(
            "未加载 (请点击“加载配置...”)")
        self.config_path_label = ctk.CTkLabel(self.config_frame,
                                              text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}",
                                              font=self.app_font, anchor="w")
        self.translatable_widgets[self.config_path_label] = ("label_with_dynamic_part", self.config_path_label_base_key,
                                                             self.config_path_display_part)
        self.config_path_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.language_label = ctk.CTkLabel(self.config_frame, text=_("语言:"), font=self.app_font)
        self.translatable_widgets[self.language_label] = "语言:"
        self.language_label.grid(row=0, column=1, padx=(10, 5), pady=10)
        self.language_optionmenu = ctk.CTkOptionMenu(self.config_frame, variable=self.selected_language_var,
                                                     values=list(self.LANG_CODE_TO_NAME.values()),
                                                     command=self.on_language_change, font=self.app_font,
                                                     dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=0, column=2, padx=(0, 10), pady=10)

    def change_appearance_mode_event(self, selected_display_mode: str):
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(selected_display_mode, "System")
        ctk.set_appearance_mode(new_mode)

        # 【新增】更新日志颜色以匹配新模式
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


    def _create_tab_view_structure(self):
        self.tab_view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_view_frame.pack(side="bottom", fill="both", expand=True, padx=10, pady=5)
        self.tab_view = ctk.CTkTabview(self.tab_view_frame, corner_radius=8)
        if hasattr(self.tab_view, '_segmented_button'):
            self.tab_view._segmented_button.configure(font=self.app_font)
        self.tab_view.pack(fill="both", expand=True, padx=0, pady=0)
        self.download_tab_internal_key = "DOWNLOAD_TAB_INTERNAL"
        self.integrate_tab_internal_key = "INTEGRATE_TAB_INTERNAL"
        self.homology_map_tab_internal_key = "HOMOLOGY_MAP_TAB_INTERNAL"
        self.gff_query_tab_internal_key = "GFF_QUERY_TAB_INTERNAL"
        self.editor_tab_internal_key = "EDITOR_TAB_INTERNAL"
        self.download_tab_display_key = "数据下载"
        self.integrate_tab_display_key = "整合分析"
        self.homology_map_tab_display_key = "基因组转换"
        self.gff_query_tab_display_key = "基因位点查询"
        self.editor_tab_display_key = "配置编辑"
        self.tab_view.add(self.download_tab_internal_key)
        self.tab_view.add(self.integrate_tab_internal_key)
        self.tab_view.add(self.homology_map_tab_internal_key)
        self.tab_view.add(self.gff_query_tab_internal_key)
        self.tab_view.add(self.editor_tab_internal_key)
        self._populate_download_tab_structure()
        self._populate_integrate_tab_structure()
        self._populate_homology_map_tab_structure()
        self._populate_gff_query_tab_structure()
        self._populate_editor_tab_structure()

    def browse_download_output_dir(self):
        """
        打开文件夹选择对话框，让用户选择下载文件的输出目录。
        """
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory and self.download_output_dir_entry:
            self.download_output_dir_entry.delete(0, tk.END)
            self.download_output_dir_entry.insert(0, directory)

    def _populate_download_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)

        target_frame = ctk.CTkFrame(page)
        target_frame.pack(fill="x", expand=True, pady=(15, 10), padx=15)
        target_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(target_frame, text=_("下载目标"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                     padx=10, pady=(10, 15), sticky="w")
        genome_ids_label = ctk.CTkLabel(target_frame, text=_("基因组版本ID:"), font=self.app_font)
        self.translatable_widgets[genome_ids_label] = "基因组版本ID:"
        genome_ids_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.download_genome_ids_entry = ctk.CTkEntry(target_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.download_genome_ids_entry] = ("placeholder",
                                                                     "例如: NBI_v1.1, HAU_v2.0 (留空则下载所有)")
        self.download_genome_ids_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        options_frame = ctk.CTkFrame(page)
        options_frame.pack(fill="x", expand=True, pady=10, padx=15)
        options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options_frame, text=_("下载选项"), font=self.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                      padx=10, pady=(10, 15),
                                                                                      sticky="w")
        output_dir_label = ctk.CTkLabel(options_frame, text=_("下载输出目录:"), font=self.app_font)
        self.translatable_widgets[output_dir_label] = "下载输出目录:"
        output_dir_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.download_output_dir_entry = ctk.CTkEntry(options_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.download_output_dir_entry] = ("placeholder", _("可选, 覆盖配置"))
        self.download_output_dir_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.dl_browse_button = ctk.CTkButton(options_frame, text=_("浏览..."), width=100, height=35,
                                              command=self.browse_download_output_dir, font=self.app_font)
        self.translatable_widgets[self.dl_browse_button] = "浏览..."
        self.dl_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)
        self.dl_force_checkbox = ctk.CTkCheckBox(options_frame, variable=self.download_force_checkbox_var,
                                                 font=self.app_font)
        self.translatable_widgets[self.dl_force_checkbox] = "强制重新下载已存在的文件"
        self.dl_force_checkbox.grid(row=2, column=1, padx=0, pady=15, sticky="w")

        self.download_start_button = ctk.CTkButton(page, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.translatable_widgets[self.download_start_button] = "开始下载"
        self.download_start_button.pack(fill="x", padx=15, pady=(20, 15))

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

    def _populate_homology_map_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        container = ctk.CTkFrame(page, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure((0, 1), weight=1)
        container.grid_rowconfigure(1, weight=1)
        input_frame = ctk.CTkFrame(container)
        input_frame.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=15, sticky="nsew")
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text=_("输入基因与版本"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                          padx=10, pady=(10, 15),
                                                                                          sticky="w")

        self.homology_map_genes_entry = ctk.CTkTextbox(input_frame, font=self.app_font, wrap="none")
        self.homology_map_genes_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.homology_map_genes_entry.insert("0.0", _(self.placeholder_genes_homology_key))

        # 【修复】根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.homology_map_genes_entry.configure(text_color=placeholder_color_value)

        self.homology_map_genes_entry.bind("<FocusIn>",
                                           lambda e: self._handle_textbox_focus_in(e, self.homology_map_genes_entry,
                                                                                   self.placeholder_genes_homology_key))
        self.homology_map_genes_entry.bind("<FocusOut>",
                                           lambda e: self._handle_textbox_focus_out(e, self.homology_map_genes_entry,
                                                                                    self.placeholder_genes_homology_key))

        ctk.CTkLabel(input_frame, text=_("源基因组版本:"), font=self.app_font).grid(row=2, column=0, padx=10, pady=10,
                                                                                    sticky="w")
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_source_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_source_assembly_dropdown.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(input_frame, text=_("目标基因组版本:"), font=self.app_font).grid(row=4, column=0, padx=10, pady=10,
                                                                                      sticky="w")
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_target_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_target_assembly_dropdown.grid(row=5, column=0, columnspan=2, padx=10, pady=(5, 10),
                                                        sticky="ew")
        file_frame = ctk.CTkFrame(container)
        file_frame.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="new")
        file_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(file_frame, text=_("同源与输出文件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                         padx=10, pady=(10, 15),
                                                                                         sticky="w")
        ctk.CTkLabel(file_frame, text=_("源到桥梁文件:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                   pady=5, sticky="w")
        self.homology_map_sb_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_sb_file_entry.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("桥梁到目标文件:"), font=self.app_font).grid(row=3, column=0, padx=(10, 5),
                                                                                     pady=5, sticky="w")
        self.homology_map_bt_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_bt_file_entry.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("结果输出CSV文件:"), font=self.app_font).grid(row=5, column=0, padx=(10, 5),
                                                                                      pady=5, sticky="w")
        self.homology_map_output_csv_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_output_csv_entry.grid(row=6, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        self.homology_map_start_button = ctk.CTkButton(container, text=_("开始同源映射"), height=40,
                                                       command=self.start_homology_map_task, font=self.app_font_bold)
        self.homology_map_start_button.grid(row=1, column=1, padx=(5, 15), pady=15, sticky="sew")

    def _populate_gff_query_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        query_frame = ctk.CTkFrame(page)
        query_frame.pack(fill="x", padx=15, pady=(15, 10))
        query_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(query_frame, text=_("查询条件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                    padx=10, pady=(10, 15), sticky="w")
        ctk.CTkLabel(query_frame, text=_("基因组版本ID:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                    pady=10, sticky="w")
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(query_frame, font=self.app_font, height=35,
                                                             variable=self.selected_gff_query_assembly,
                                                             values=[_("加载中...")], dropdown_font=self.app_font)
        self.gff_query_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ctk.CTkLabel(query_frame, text=_("染色体区域:"), font=self.app_font).grid(row=2, column=0, padx=(10, 5),
                                                                                  pady=10, sticky="w")
        self.gff_query_region_entry = ctk.CTkEntry(query_frame, font=self.app_font, height=35,
                                                   placeholder_text=_("例如: chr1:1000-5000 (与下方基因ID二选一)"))
        self.gff_query_region_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        gene_list_frame = ctk.CTkFrame(page)
        gene_list_frame.pack(fill="both", expand=True, padx=15, pady=10)
        gene_list_frame.grid_columnconfigure(0, weight=1)
        gene_list_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(gene_list_frame, text=_("或输入基因ID (每行一个):"), font=self.app_font).grid(row=0, column=0,
                                                                                                   padx=10, pady=5,
                                                                                                   sticky="w")

        self.gff_query_genes_entry = ctk.CTkTextbox(gene_list_frame, font=self.app_font, wrap="none")
        self.gff_query_genes_entry.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.gff_query_genes_entry.insert("0.0", _(self.placeholder_genes_gff_key))

        # 【修复】根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.gff_query_genes_entry.configure(text_color=placeholder_color_value)

        self.gff_query_genes_entry.bind("<FocusIn>",
                                        lambda e: self._handle_textbox_focus_in(e, self.gff_query_genes_entry,
                                                                                self.placeholder_genes_gff_key))
        self.gff_query_genes_entry.bind("<FocusOut>",
                                        lambda e: self._handle_textbox_focus_out(e, self.gff_query_genes_entry,
                                                                                 self.placeholder_genes_gff_key))

        output_frame = ctk.CTkFrame(page)
        output_frame.pack(fill="x", padx=15, pady=10)
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font).pack(padx=10, pady=5, anchor="w")
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font, height=35,
                                                       placeholder_text=_("可选, 默认自动生成"))
        self.gff_query_output_csv_entry.pack(padx=10, pady=5, fill="x")
        self.gff_query_start_button = ctk.CTkButton(page, text=_("开始基因查询"), height=40,
                                                    command=self.start_gff_query_task, font=self.app_font_bold)
        self.gff_query_start_button.pack(fill="x", padx=15, pady=15)


    def _load_initial_config(self):
        # 尝试在程序启动时自动加载位于同目录的 config.yml
        default_config_path = "config.yml"
        if os.path.exists(default_config_path):
            self.load_config_file(filepath=os.path.abspath(default_config_path), is_initial_load=True)
        else:
            self.show_info_message(_("欢迎"), _("未找到默认 config.yml。请点击“生成默认配置”或“加载配置文件”开始。"))

    def _populate_editor_tab_structure(self):  #
        page = self.tab_view.tab(self.editor_tab_internal_key)  #
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")  #
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)  #
        main_config_frame = ctk.CTkFrame(scrollable_frame)  #
        main_config_frame.pack(fill="x", expand=True, pady=10, padx=5)  #
        main_config_frame.grid_columnconfigure(1, weight=1)  #
        main_config_label = ctk.CTkLabel(main_config_frame, text=_("主配置文件 (config.yml)"),
                                         font=self.app_font_bold)  #
        self.translatable_widgets[main_config_label] = "主配置文件 (config.yml)"  #
        main_config_label.grid(row=0, column=0, columnspan=2, pady=(10, 15), padx=10, sticky="w")  #
        dl_output_dir_editor_label = ctk.CTkLabel(main_config_frame, text=_("下载器输出目录:"), font=self.app_font)  #
        self.translatable_widgets[dl_output_dir_editor_label] = "下载器输出目录:"  #
        dl_output_dir_editor_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_output_dir = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_dl_output_dir.grid(row=1, column=1, padx=10, pady=5, sticky="ew")  #
        dl_force_editor_label = ctk.CTkLabel(main_config_frame, text=_("强制下载:"), font=self.app_font)  #
        self.translatable_widgets[dl_force_editor_label] = "强制下载:"  #
        dl_force_editor_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_force_switch = ctk.CTkSwitch(main_config_frame, text="", variable=self.editor_dl_force_var)  #
        self.editor_dl_force_switch.grid(row=2, column=1, padx=10, pady=5, sticky="w")  #
        dl_proxy_http_label = ctk.CTkLabel(main_config_frame, text=_("HTTP 代理:"), font=self.app_font)  #
        self.translatable_widgets[dl_proxy_http_label] = "HTTP 代理:"  #
        dl_proxy_http_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_proxy_http = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.translatable_widgets[self.editor_dl_proxy_http] = "例如: http://user:pass@host:port"  #
        self.editor_dl_proxy_http.grid(row=3, column=1, padx=10, pady=5, sticky="ew")  #
        dl_proxy_https_label = ctk.CTkLabel(main_config_frame, text=_("HTTPS/SOCKS 代理:"), font=self.app_font)  #
        self.translatable_widgets[dl_proxy_https_label] = "HTTPS/SOCKS 代理:"  #
        dl_proxy_https_label.grid(row=4, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_proxy_https = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.translatable_widgets[self.editor_dl_proxy_https] = "例如: https://user:pass@host:port"  #
        self.editor_dl_proxy_https.grid(row=4, column=1, padx=10, pady=5, sticky="ew")  #
        pl_excel_editor_label = ctk.CTkLabel(main_config_frame, text=_("整合分析输入Excel:"), font=self.app_font)  #
        self.translatable_widgets[pl_excel_editor_label] = "整合分析输入Excel:"  #
        pl_excel_editor_label.grid(row=5, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_pl_excel_path = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_pl_excel_path.grid(row=5, column=1, padx=10, pady=5, sticky="ew")  #
        pl_sheet_editor_label = ctk.CTkLabel(main_config_frame, text=_("整合分析输出Sheet名:"), font=self.app_font)  #
        self.translatable_widgets[pl_sheet_editor_label] = "整合分析输出Sheet名:"  #
        pl_sheet_editor_label.grid(row=6, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_pl_output_sheet = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_pl_output_sheet.grid(row=6, column=1, padx=10, pady=5, sticky="ew")  #
        pl_gff_editor_label = ctk.CTkLabel(main_config_frame, text=_("GFF文件路径 (YAML格式):"), font=self.app_font)  #
        self.translatable_widgets[pl_gff_editor_label] = "GFF文件路径 (YAML格式):"  #
        pl_gff_editor_label.grid(row=7, column=0, padx=10, pady=5, sticky="nw")  #
        self.editor_pl_gff_files = ctk.CTkTextbox(main_config_frame, height=100, wrap="none", font=self.app_font)  #
        self.editor_pl_gff_files.grid(row=7, column=1, padx=10, pady=5, sticky="ew")  #
        self.editor_save_button = ctk.CTkButton(main_config_frame, text=_("保存主配置"), height=35,
                                                command=self._save_main_config, font=self.app_font)  #
        self.translatable_widgets[self.editor_save_button] = "保存主配置"  #
        self.editor_save_button.grid(row=8, column=1, pady=(15, 10), padx=10, sticky="e")  #
        gs_config_frame = ctk.CTkFrame(scrollable_frame)  #
        gs_config_frame.pack(fill="x", expand=True, pady=10, padx=5)  #
        gs_config_frame.grid_columnconfigure(0, weight=1)  #
        gs_config_frame.grid_rowconfigure(2, weight=1)  #
        gs_label = ctk.CTkLabel(gs_config_frame, text=_("基因组源文件 (genome_sources_list.yml)"),
                                font=self.app_font_bold)  #
        self.translatable_widgets[gs_label] = "基因组源文件 (genome_sources_list.yml)"  #
        gs_label.grid(row=0, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="w")  #
        gs_help_label = ctk.CTkLabel(gs_config_frame,
                                     text=_("可在此为每个版本添加 homology_id_slicer: \"_\" 用于剪切基因ID"),
                                     font=self.app_font, text_color="gray")  #
        self.translatable_widgets[gs_help_label] = "可在此为每个版本添加 homology_id_slicer: \"_\" 用于剪切基因ID"  #
        gs_help_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="w")  #
        self.editor_gs_raw_yaml = ctk.CTkTextbox(gs_config_frame, height=250, wrap="none", font=self.app_font)  #
        self.editor_gs_raw_yaml.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")  #
        gs_buttons_frame = ctk.CTkFrame(gs_config_frame, fg_color="transparent")  #
        gs_buttons_frame.grid(row=3, column=0, columnspan=2, pady=(10, 10), padx=10,
                              sticky="e")  # Modified columnspan and sticky
        self.editor_gs_load_button = ctk.CTkButton(gs_buttons_frame, text=_("重新加载"), height=35,
                                                   command=self._load_genome_sources_to_editor, font=self.app_font)  #
        self.translatable_widgets[self.editor_gs_load_button] = "重新加载"  #
        self.editor_gs_load_button.pack(side="left", padx=(0, 10))  #
        self.editor_gs_save_button = ctk.CTkButton(gs_buttons_frame, text=_("保存基因组源"), height=35,
                                                   command=self._save_genome_sources_config, font=self.app_font)  #
        self.translatable_widgets[self.editor_gs_save_button] = "保存基因组源"  #
        self.editor_gs_save_button.pack(side="left")  #

    def _setup_fonts(self):
        import tkinter.font
        available_fonts = tkinter.font.families()
        preferred_font_family = "Microsoft YaHei UI"
        font_family = preferred_font_family if preferred_font_family in available_fonts else None
        if font_family:
            logging.info(f"检测到并使用首选字体: {font_family}")
        else:
            logging.warning(f"首选字体 '{preferred_font_family}' 未在系统中找到，将使用系统默认UI字体。")
        self.app_font = ctk.CTkFont(family=font_family, size=14)
        self.app_font_bold = ctk.CTkFont(family=font_family, size=15, weight="bold")
        self.app_title_font = ctk.CTkFont(family=font_family, size=24, weight="bold")
        self.app_subtitle_font = ctk.CTkFont(family=font_family, size=16)

    def update_language_ui(self, lang_code_to_set=None):
        global _
        if not lang_code_to_set: lang_code_to_set = self.ui_settings.get('language', 'zh-hans')
        try:
            _ = setup_cli_i18n(language_code=lang_code_to_set, app_name="cotton_toolkit")
        except Exception as e:
            _ = lambda s: s
            logging.error(f"语言设置错误: {e}")

        # 1. 更新普通控件
        for widget, info in self.translatable_widgets.items():
            if not (widget and widget.winfo_exists()): continue
            if isinstance(info, tuple):
                op, data = info[0], info[1:]
                if op == "values": widget.configure(values=[_(v) for v in data[0]])
            elif isinstance(info, str):
                widget.configure(text=_(info))

        # 2. 更新下拉菜单的当前显示值
        display_lang_name = self.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        if hasattr(self, 'language_optionmenu'): self.language_optionmenu.set(display_lang_name)
        if hasattr(self, 'appearance_mode_optionemenu'):
            current_mode_value = self.ui_settings.get('appearance_mode', 'System')
            mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
            display_text = mode_map_to_display.get(current_mode_value, _("系统"))
            self.appearance_mode_optionemenu.set(display_text)

        # 3. 更新工具选项卡的显示文本
        if hasattr(self, 'tools_notebook') and hasattr(self.tools_notebook, '_segmented_button'):
            try:
                current_internal_name = self.tools_notebook.get()
                tab_display_names = {
                    "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
                    "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
                }
                new_display_values = [tab_display_names.get(key) for key in self.tab_keys]

                new_tab_dict = {}
                for i, (simple_key, internal_key) in enumerate(self.tab_keys.items()):
                    frame = self.tools_notebook.tab(internal_key)
                    new_display_name = new_display_values[i]
                    new_tab_dict[new_display_name] = frame

                self.tools_notebook._tab_dict = new_tab_dict
                self.tools_notebook._name_list = new_display_values
                self.tools_notebook._segmented_button.configure(values=new_display_values)

                new_selection_display_name = None
                for i, internal_key in enumerate(self.tab_keys.values()):
                    if internal_key == current_internal_name:
                        new_selection_display_name = new_display_values[i]
                        break

                if new_selection_display_name: self.tools_notebook.set(new_selection_display_name)
            except Exception as e:
                logging.error(f"动态更新TabView时发生严重错误: {e}")

        # 4. 更新窗口标题
        self.title(_(self.title_text_key))


    def _update_assembly_id_dropdowns(self):  #
        if not self.current_config:  #
            return  #
        self._log_to_viewer(_("正在更新基因组版本列表..."))  #
        genome_sources = get_genome_data_sources(self.current_config)  #
        if genome_sources and isinstance(genome_sources, dict):  #
            assembly_ids = list(genome_sources.keys())  #
            if not assembly_ids: assembly_ids = [_("无可用版本")]  #
        else:
            assembly_ids = [_("无法加载基因组源")]  #
            self._log_to_viewer(_("警告: 未能从配置文件或源文件中加载基因组列表。"), level="WARNING")  #
        dropdowns = [  #
            self.integrate_bsa_assembly_dropdown, self.integrate_hvg_assembly_dropdown,  #
            self.homology_map_source_assembly_dropdown, self.homology_map_target_assembly_dropdown,  #
            self.gff_query_assembly_dropdown  #
        ]
        for dropdown in dropdowns:  #
            if dropdown: dropdown.configure(values=assembly_ids)  #

    def _update_excel_sheet_dropdowns(self):  #
        excel_path = self.integrate_excel_entry.get()  #
        sheet_names_to_set = [_("请先指定有效的Excel文件")]  #
        valid_sheets_found = False  #
        if excel_path and os.path.exists(excel_path):  #
            try:
                xls = pd.ExcelFile(excel_path)  #
                sheet_names_from_file = xls.sheet_names  #
                if sheet_names_from_file:  #
                    sheet_names_to_set = sheet_names_from_file  #
                    valid_sheets_found = True  #
                    self._log_to_viewer(_("已成功读取Excel文件中的工作表列表。"))  #
                else:
                    sheet_names_to_set = [_("Excel文件中无工作表")]  #
            except Exception as e:  #
                sheet_names_to_set = [_("读取Excel失败")]  #
                self._log_to_viewer(f"{_('错误: 无法读取Excel文件')} '{excel_path}': {e}", level="ERROR")  #

        bsa_dropdown = self.integrate_bsa_sheet_dropdown  #
        hvg_dropdown = self.integrate_hvg_sheet_dropdown  #

        if bsa_dropdown: bsa_dropdown.configure(values=sheet_names_to_set)  #
        if hvg_dropdown: hvg_dropdown.configure(values=sheet_names_to_set)  #

        if valid_sheets_found and self.current_config:  #
            cfg_bsa_sheet = self.current_config.get("integration_pipeline", {}).get("bsa_sheet_name")  #
            cfg_hvg_sheet = self.current_config.get("integration_pipeline", {}).get("hvg_sheet_name")  #
            if cfg_bsa_sheet in sheet_names_to_set:
                self.selected_bsa_sheet.set(cfg_bsa_sheet)  #
            elif sheet_names_to_set:
                self.selected_bsa_sheet.set(sheet_names_to_set[0])  #
            if cfg_hvg_sheet in sheet_names_to_set:
                self.selected_hvg_sheet.set(cfg_hvg_sheet)  #
            elif sheet_names_to_set:
                self.selected_hvg_sheet.set(sheet_names_to_set[0])  #
        elif sheet_names_to_set:  #
            self.selected_bsa_sheet.set(sheet_names_to_set[0])  #
            self.selected_hvg_sheet.set(sheet_names_to_set[0])  #

    def browse_integrate_excel(self):  #
        filepath = filedialog.askopenfilename(title=_("选择输入Excel文件"),
                                              filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*")))  #
        if filepath:  #
            self.integrate_excel_entry.delete(0, tk.END)  #
            self.integrate_excel_entry.insert(0, filepath)  #
            self._update_excel_sheet_dropdowns()  #

    def _apply_config_to_ui(self):
        if not self.current_config: self._log_to_viewer(_("没有加载配置，无法应用到UI。"), level="WARNING"); return

        # 更新配置文件路径显示
        self.config_path_label.configure(text=_("当前配置: {}").format(os.path.basename(self.config_path)))

        # 更新下拉菜单
        self._update_assembly_id_dropdowns()

        # 下载页面
        downloader_cfg = self.current_config.get("downloader", {})
        self.download_output_dir_entry.delete(0, tk.END)
        self.download_output_dir_entry.insert(0, downloader_cfg.get("download_output_base_dir", ""))
        self.download_force_checkbox_var.set(bool(downloader_cfg.get("force_download", False)))

        # 整合分析页面
        integration_cfg = self.current_config.get("integration_pipeline", {})
        self.selected_bsa_assembly.set(integration_cfg.get("bsa_assembly_id", ""))
        self.selected_hvg_assembly.set(integration_cfg.get("hvg_assembly_id", ""))

        excel_path = integration_cfg.get("input_excel_path", "")
        self.integrate_excel_entry.delete(0, tk.END)
        self.integrate_excel_entry.insert(0, excel_path)
        self._update_excel_sheet_dropdowns()  # 这会根据配置和Excel路径设置工作表名称

        # 工具页面
        self.selected_homology_source_assembly.set(integration_cfg.get("bsa_assembly_id", ""))
        self.selected_homology_target_assembly.set(integration_cfg.get("hvg_assembly_id", ""))
        default_gff_assembly = integration_cfg.get("bsa_assembly_id") or integration_cfg.get("hvg_assembly_id", "")
        self.selected_gff_query_assembly.set(default_gff_assembly)

        self._log_to_viewer(_("配置已成功应用到所有UI字段。"))

    def start_integrate_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("整合分析")

        cfg_pipeline = self.current_config.setdefault('integration_pipeline', {})
        cfg_pipeline['bsa_assembly_id'] = self.selected_bsa_assembly.get()
        cfg_pipeline['hvg_assembly_id'] = self.selected_hvg_assembly.get()
        cfg_pipeline['bsa_sheet_name'] = self.selected_bsa_sheet.get()
        cfg_pipeline['hvg_sheet_name'] = self.selected_hvg_sheet.get()
        excel_override = self.integrate_excel_entry.get().strip() or None

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 【修复】使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=integrate_bsa_with_hvg, kwargs={
            "config": self.current_config,
            "input_excel_path_override": excel_override,
            "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name),
        }, daemon=True)
        thread.start()

    def start_homology_map_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因组转换")

        gene_ids_text = self.homology_map_genes_entry.get("1.0", tk.END).strip()
        placeholder_text = _(self.placeholder_genes_homology_key)
        source_gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if
                                line.strip() and line.strip() != placeholder_text] if gene_ids_text != placeholder_text else []
        if not source_gene_ids_list:
            self.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"));
            self._update_button_states(False);
            return

        source_assembly_id_override = self.selected_homology_source_assembly.get()
        target_assembly_id_override = self.selected_homology_target_assembly.get()
        s_to_b_homology_file_override = self.homology_map_sb_file_entry.get().strip() or None
        b_to_t_homology_file_override = self.homology_map_bt_file_entry.get().strip() or None
        output_csv_path = self.homology_map_output_csv_entry.get().strip() or None

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 【修复】使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_homology_mapping_standalone, kwargs={
            "config": self.current_config, "source_gene_ids_override": source_gene_ids_list,
            "source_assembly_id_override": source_assembly_id_override,
            "target_assembly_id_override": target_assembly_id_override,
            "s_to_b_homology_file_override": s_to_b_homology_file_override,
            "b_to_t_homology_file_override": b_to_t_homology_file_override,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

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
        # 【修复】使用 .grid() 而不是 .pack()
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
    def _browse_file(self, entry_widget, filetypes_list):  #
        filepath = filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list)  #
        if filepath and entry_widget:  #
            entry_widget.delete(0, tk.END);
            entry_widget.insert(0, filepath)  #


    def _browse_save_file(self, entry_widget, filetypes_list):  #
        filepath = filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                defaultextension=filetypes_list[0][1].replace("*", ""))  #
        if filepath and entry_widget:  #
            entry_widget.delete(0, tk.END);
            entry_widget.insert(0, filepath)  #


    # --- (其余所有方法，如日志、状态、配置加载/保存等，保持不变) ---
    def clear_log_viewer(self):  #
        self.log_textbox.configure(state="normal")  #
        self.log_textbox.delete("1.0", tk.END)  #
        self.log_textbox.configure(state="disabled")  #
        self._log_to_viewer(_("日志已清除。"))  #


    def _log_to_viewer(self, message, level="INFO"):  #
        if self.log_textbox and self.log_textbox.winfo_exists():  #
            self.log_textbox.configure(state="normal")  #
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())  #
            color_tag = "normal_log"  #
            if level == "ERROR":
                color_tag = "error_log"  #
            elif level == "WARNING":
                color_tag = "warning_log"  #
            self.log_textbox.insert(tk.END, f"[{timestamp}] {message}\n", color_tag)  #
            self.log_textbox.see(tk.END)  #
            self.log_textbox.configure(state="disabled")  #
            if not hasattr(self.log_textbox, '_tags_configured'):  #
                self.log_textbox.tag_config("error_log", foreground="red")  #
                self.log_textbox.tag_config("warning_log", foreground="orange")  #
                self.log_textbox._tags_configured = True  #
        else:
            print(f"[{level}] {message}")  #


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


    def gui_status_callback(self, message):
        self.message_queue.put(("status", message));
        self._log_to_viewer(str(message))  #


    def gui_progress_callback(self, percentage, message):
        self.message_queue.put(("progress", (percentage, message)))  #


    def task_done_callback(self, success=True, task_display_name="任务"):
        self.message_queue.put(("task_done", (success, task_display_name)))


    def check_queue_periodic(self):
        try:
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()
                if message_type == "status":
                    self.status_label.configure(text=str(data)[:150])
                elif message_type == "progress":
                    percentage, text = data
                    if not self.progress_bar.winfo_viewable(): self.progress_bar.grid()
                    self.progress_bar.set(percentage / 100.0)
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)")
                elif message_type == "task_done":
                    success, task_display_name = data
                    self.progress_bar.grid_remove()
                    final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))
                    self.status_label.configure(text=final_message, text_color=("green" if success else "red"))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
        except Exception:
            pass
        self.after(100, self.check_queue_periodic)


    def on_closing(self):
        if self._show_custom_dialog(_("退出"), _("您确定要退出吗?"), buttons=[_("确定"), _("取消")],
                                    icon_type="question") == _("确定"):
            self.destroy()


    def load_config_file(self, filepath: Optional[str] = None, is_initial_load: bool = False):
        if not filepath:
            filepath = filedialog.askopenfilename(title=_("选择配置文件"),
                                                  filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")))

        if filepath:
            self._log_to_viewer(f"{_('尝试加载配置文件:')} {filepath}")
            try:
                loaded_config = load_config(filepath)
                if loaded_config:
                    self.current_config = loaded_config
                    self.config_path = filepath
                    self._apply_config_to_ui()
                    self._update_button_states()
                    self._log_to_viewer(f"{_('配置文件加载成功:')} {filepath}")
                    if not is_initial_load:
                        self.show_info_message(_("加载成功"), _("配置文件已成功加载并应用到界面。"))
                else:
                    self.show_error_message(_("加载失败"), _("无法加载配置文件或配置文件内容为空。"))
            except Exception as e:
                self.show_error_message(_("加载错误"), f"{_('加载配置文件时发生错误:')} {e}")
        else:
            if not is_initial_load:
                self._log_to_viewer(_("取消加载配置文件。"))


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
                if save_config_to_yaml(config_data, save_path):
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
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if output_dir:
            self._log_to_viewer(f"{_('尝试在以下位置生成默认配置文件:')} {output_dir}")
            try:
                success, main_cfg_path, gs_cfg_path = generate_default_config_files(output_dir, overwrite=False)
                if success:
                    msg = f"{_('默认配置文件已成功生成到:')}\n{main_cfg_path}\n{gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"
                    if self._show_custom_dialog(_("生成成功"), msg, [_("是"), _("否")], "question") == _("是"):
                        self.load_config_file(filepath=main_cfg_path)
                else:
                    self.show_error_message(_("生成失败"), _("生成默认配置文件失败，可能文件已存在。请检查日志。"))
            except Exception as e:
                self.show_error_message(_("错误"), f"{_('生成默认配置文件时发生错误:')} {e}")


    def _apply_config_to_editor_ui(self):  #
        if not self.current_config: self._log_to_viewer(_("没有加载配置，无法填充编辑器UI。"), level="WARNING"); return  #
        main_config = self.current_config  #
        downloader_cfg = main_config.get("downloader", {})  #
        integration_cfg = main_config.get("integration_pipeline", {})  #
        if self.editor_dl_output_dir: self.editor_dl_output_dir.delete(0, tk.END); self.editor_dl_output_dir.insert(0,
                                                                                                                    downloader_cfg.get(
                                                                                                                        "download_output_base_dir",
                                                                                                                        ""))  #
        if self.editor_dl_force_var: self.editor_dl_force_var.set(bool(downloader_cfg.get("force_download", False)))  #
        proxies_cfg = downloader_cfg.get("proxies", {})  #
        if self.editor_dl_proxy_http: http_proxy = proxies_cfg.get("http", ""); self.editor_dl_proxy_http.delete(0,
                                                                                                                 tk.END); self.editor_dl_proxy_http.insert(
            0, http_proxy if http_proxy is not None else "")  #
        if self.editor_dl_proxy_https: https_proxy = proxies_cfg.get("https", ""); self.editor_dl_proxy_https.delete(0,
                                                                                                                     tk.END); self.editor_dl_proxy_https.insert(
            0, https_proxy if https_proxy is not None else "")  #
        if self.editor_pl_excel_path: self.editor_pl_excel_path.delete(0, tk.END); self.editor_pl_excel_path.insert(0,
                                                                                                                    integration_cfg.get(
                                                                                                                        "input_excel_path",
                                                                                                                        ""))  #
        if self.editor_pl_output_sheet: self.editor_pl_output_sheet.delete(0,
                                                                           tk.END); self.editor_pl_output_sheet.insert(
            0, integration_cfg.get("output_sheet_name", ""))  #
        if self.editor_pl_gff_files:  #
            gff_files_yaml = integration_cfg.get("gff_files", {})  #
            try:
                gff_yaml_str = yaml.dump(gff_files_yaml, default_flow_style=False, allow_unicode=True,
                                         sort_keys=False)  #
            except Exception as e:
                self._log_to_viewer(f"WARNING: 无法将GFF配置转换为YAML字符串: {e}",
                                    level="WARNING");
                gff_yaml_str = str(gff_files_yaml)  #
            self.editor_pl_gff_files.delete("1.0", tk.END);
            self.editor_pl_gff_files.insert("1.0", gff_yaml_str)  #
        self._load_genome_sources_to_editor()  #


    def _save_main_config(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("没有加载配置文件，无法保存。")); return  #
        if "downloader" not in self.current_config: self.current_config["downloader"] = {}  #
        self.current_config["downloader"]["download_output_base_dir"] = self.editor_dl_output_dir.get().strip()  #
        self.current_config["downloader"]["force_download"] = self.editor_dl_force_var.get()  #
        if "proxies" not in self.current_config["downloader"]: self.current_config["downloader"]["proxies"] = {}  #
        http_proxy_val = self.editor_dl_proxy_http.get().strip();
        self.current_config["downloader"]["proxies"]["http"] = http_proxy_val if http_proxy_val else None  #
        https_proxy_val = self.editor_dl_proxy_https.get().strip();
        self.current_config["downloader"]["proxies"]["https"] = https_proxy_val if https_proxy_val else None  #
        if "integration_pipeline" not in self.current_config: self.current_config["integration_pipeline"] = {}  #
        self.current_config["integration_pipeline"]["input_excel_path"] = self.editor_pl_excel_path.get().strip()  #
        self.current_config["integration_pipeline"]["output_sheet_name"] = self.editor_pl_output_sheet.get().strip()  #
        gff_yaml_str = self.editor_pl_gff_files.get("1.0", tk.END).strip()  #
        try:
            if gff_yaml_str:
                gff_dict = yaml.safe_load(gff_yaml_str);
                self.current_config["integration_pipeline"][
                    "gff_files"] = gff_dict if isinstance(gff_dict, dict) else self.show_error_message(_("保存错误"),
                                                                                                       _("GFF文件路径的YAML格式不正确。")) or {}  #
            else:
                self.current_config["integration_pipeline"]["gff_files"] = {}  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('GFF文件路径YAML解析错误:')} {e}");
            return  #
        if self.config_path:  #
            try:
                save_config_to_yaml(self.current_config, self.config_path);
                self._log_to_viewer(
                    f"{_('主配置文件已保存到:')} {self.config_path}");
                self.show_info_message(_("保存成功"),
                                       _("主配置文件已成功保存。"))  #
            except Exception as e:
                self.show_error_message(_("保存错误"), f"{_('保存主配置文件时发生错误:')} {e}");
                self._log_to_viewer(
                    f"ERROR: {_('保存主配置文件时发生错误:')} {e}", level="ERROR")  #
        else:
            self.show_warning_message(_("无法保存"), _("没有加载配置文件路径。"))  #


    def _load_genome_sources_to_editor(self):  #
        if not self.current_config: self._log_to_viewer(_("没有加载主配置文件，无法加载基因组源。"),
                                                        level="WARNING"); return  #
        gs_file_rel = self.current_config.get("downloader", {}).get("genome_sources_file")  #
        if not gs_file_rel: self._log_to_viewer(_("主配置文件中未指定基因组源文件路径。"),
                                                level="WARNING"); self.editor_gs_raw_yaml.delete("1.0",
                                                                                                 tk.END); self.editor_gs_raw_yaml.insert(
            "1.0", _("# 未指定基因组源文件路径。")); return  #
        abs_path = os.path.join(os.path.dirname(self.config_path), gs_file_rel) if not os.path.isabs(
            gs_file_rel) and self.config_path else gs_file_rel  #
        if not os.path.exists(abs_path): self._log_to_viewer(f"WARNING: {_('基因组源文件不存在:')} {abs_path}",
                                                             level="WARNING"); self.editor_gs_raw_yaml.delete("1.0",
                                                                                                              tk.END); self.editor_gs_raw_yaml.insert(
            "1.0", f"{_('# 文件不存在:')} {abs_path}"); return  #
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()  #
            self.editor_gs_raw_yaml.delete("1.0", tk.END);
            self.editor_gs_raw_yaml.insert("1.0", content)  #
            self._log_to_viewer(f"{_('基因组源文件已加载到编辑器:')} {abs_path}")  #
        except Exception as e:
            self._log_to_viewer(f"ERROR: {_('加载基因组源文件时发生错误:')} {e}",
                                level="ERROR");
            self.editor_gs_raw_yaml.delete("1.0",
                                           tk.END);
            self.editor_gs_raw_yaml.insert(
                "1.0", f"{_('# 加载错误:')} {e}")  #


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
        if hasattr(self, 'download_start_button'): self.download_start_button.configure(state=task_button_state)
        if hasattr(self, 'integrate_start_button'): self.integrate_start_button.configure(state=task_button_state)
        if hasattr(self, 'homology_map_start_button'): self.homology_map_start_button.configure(state=task_button_state)
        if hasattr(self, 'gff_query_start_button'): self.gff_query_start_button.configure(state=task_button_state)

        # 侧边栏和配置按钮
        if hasattr(self, 'navigation_frame'):
            for btn in [self.home_button, self.integrate_button, self.tools_button, self.load_config_button,
                        self.gen_config_button, self.edit_config_button]:
                if btn: btn.configure(state=action_state)

    def open_config_editor(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载一个配置文件才能进行编辑。"))
            return
        if self.config_editor_window is None or not self.config_editor_window.winfo_exists():
            self.config_editor_window = AdvancedConfigEditorWindow(self, self.current_config, self.config_path)
            self.config_editor_window.grab_set()
        else:
            self.config_editor_window.focus()

    def start_download_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("数据下载")

        genome_ids_str = self.download_genome_ids_entry.get() if self.download_genome_ids_entry else ""
        versions_to_download = [gid.strip() for gid in genome_ids_str.split(',') if gid.strip()]
        output_dir_override = self.download_output_dir_entry.get().strip() or None
        force_download_override = self.download_force_checkbox_var.get()

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 【修复】使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=download_genome_data, kwargs={
            "config": self.current_config,
            "genome_versions_to_download_override": versions_to_download if versions_to_download else None,
            "force_download_override": force_download_override,
            "output_base_dir_override": output_dir_override,
            "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

if __name__ == "__main__":  #
    #logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()  #
    app.mainloop()  #
