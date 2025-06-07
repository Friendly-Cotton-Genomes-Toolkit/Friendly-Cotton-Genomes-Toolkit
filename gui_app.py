# gui_app.py
import sys
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
from queue import Queue
import os
import time
import yaml
import shutil
import webbrowser
import pandas as pd

try:
    from cotton_toolkit.config.loader import load_config, save_config_to_yaml, get_genome_data_sources, \
        generate_default_config_files
    from cotton_toolkit.core.downloader import download_genome_data
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg, run_homology_mapping_standalone, \
        run_gff_gene_lookup_standalone
    from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text
    from cotton_toolkit import VERSION as pkg_version, HELP_URL as PKG_HELP_URL

    COTTON_TOOLKIT_LOADED = True
    print("INFO: gui_app.py - Successfully imported COTTON_TOOLKIT modules.")  #
except ImportError as e:
    print(f"错误：无法导入 cotton_toolkit 模块 (gui_app.py): {e}")  #
    COTTON_TOOLKIT_LOADED = False  #
    pkg_version = "DEV"
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


    def get_about_text(translator):  #
        return "Mock About Text"  #

_ = lambda s: str(s)  #


class CottonToolkitApp(ctk.CTk):  #
    DOWNLOAD_TASK_KEY = "DOWNLOAD_TASK"  #
    INTEGRATE_TASK_KEY = "INTEGRATE_TASK"  #
    HOMOLOGY_MAP_TASK_KEY = "HOMOLOGY_MAP_TASK"  #
    GFF_QUERY_TASK_KEY = "GFF_QUERY_TASK"  #
    EDITOR_TAB_KEY = "EDITOR_TAB_INTERNAL"  #

    LANG_CODE_TO_NAME = {  #
        "zh-hans": "简体中文",  #
        "zh-hant": "繁體中文",  #
        "en": "English",  #
        "ja": "日本語"  #
    }
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}  #

    def __init__(self):  #
        super().__init__()  #

        self.app_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14)
        self.placeholder_color = "gray50"  # 定义一个占位符颜色
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"][
            "text_color"] if "CTkTextbox" in ctk.ThemeManager.theme else ("#000000", "#DCE4EE")

        # 定义占位符文本键，方便翻译和引用
        self.placeholder_genes_homology_key = "例如:\nGhir.A01G000100\nGhir.A01G000200\n(必填)"
        self.placeholder_genes_gff_key = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(与下方区域查询二选一)"
        self.translatable_widgets = {}  #

        default_lang_code = "zh-hans"  #
        self.selected_language_var = tk.StringVar(value=self.LANG_CODE_TO_NAME.get(default_lang_code, "English"))  #

        self.title_text_key = "友好棉花基因组工具包 - FCGT"  #
        self.title(_(self.title_text_key))  #
        self.geometry("950x700")  #
        self.minsize(950, 700)  #
        ctk.set_appearance_mode("System")  #
        ctk.set_default_color_theme("blue")  #

        self.current_config = None  #
        self.config_path = None  #
        self.message_queue = Queue()  #

        try:
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]  #
        except Exception:  #
            self.default_label_text_color = ("#000000", "#FFFFFF")  #

        self.app_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14)  #
        self.app_font_bold = ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold")  #
        self.menu_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14)  #

        # UI属性初始化
        self.config_path_label = None  #
        self.language_label = None  #
        self.language_optionmenu = None  #

        # StringVars for dropdowns
        self.selected_bsa_assembly = tk.StringVar()
        self.selected_hvg_assembly = tk.StringVar()
        self.selected_bsa_sheet = tk.StringVar()
        self.selected_hvg_sheet = tk.StringVar()
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.selected_gff_query_assembly = tk.StringVar()

        self.integrate_bsa_assembly_dropdown = None  #
        self.integrate_hvg_assembly_dropdown = None  #
        self.integrate_bsa_sheet_dropdown = None  #
        self.integrate_hvg_sheet_dropdown = None  #
        self.homology_map_source_assembly_dropdown = None  #
        self.homology_map_target_assembly_dropdown = None  #
        self.gff_query_assembly_dropdown = None  #

        self.download_genome_ids_entry = None  #
        self.download_output_dir_entry = None  #
        self.dl_browse_button = None  #
        self.download_force_checkbox_var = tk.BooleanVar()  #
        self.dl_force_checkbox = None  #
        self.download_start_button = None  #
        self.integrate_excel_entry = None  #
        self.int_excel_browse_button = None  #
        # self.integrate_output_sheet_entry = None # This was removed if it's not needed anymore
        self.integrate_start_button = None  #
        self.homology_map_genes_entry = None  #
        self.homology_map_sb_file_entry = None  #
        self.homology_map_bt_file_entry = None  #
        self.homology_map_sb_browse_button = None  #
        self.homology_map_bt_browse_button = None  #
        self.homology_map_output_csv_entry = None  #
        self.homology_map_output_browse_button = None  #
        self.homology_map_start_button = None  #
        self.gff_query_genes_entry = None  #
        self.gff_query_region_entry = None  #
        self.gff_query_output_csv_entry = None  #
        self.gff_query_output_browse_button = None  #
        self.gff_query_start_button = None  #
        self.editor_dl_output_dir = None  #
        self.editor_dl_force_var = tk.BooleanVar()  #
        self.editor_dl_force_switch = None  #
        self.editor_dl_proxy_http = None  #
        self.editor_dl_proxy_https = None  #
        self.editor_pl_excel_path = None  #
        self.editor_pl_output_sheet = None  #
        self.editor_pl_gff_files = None  #
        self.editor_save_button = None  #
        self.editor_gs_raw_yaml = None  #
        self.editor_gs_save_button = None  #
        self.editor_gs_load_button = None  #
        self.log_viewer_label_widget = None  #
        self.clear_log_button = None  #
        self.log_textbox = None  #
        self.status_label = None  #
        self.progress_bar = None  #
        self.menubar = None  #
        self.file_menu = None  #
        self.help_menu = None  #
        self.about_window = None  #

        self._create_menu_bar()  #
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")  #
        self.main_container.pack(fill="both", expand=True, padx=10, pady=(5, 10))  #

        self._create_config_widgets_structure()  #
        self._create_status_widgets_structure()  #
        self._create_log_viewer_structure()  #
        self._create_tab_view_structure()  #

        self.update_language_ui()  #
        self._update_button_states()  #
        self.check_queue_periodic()  #
        self.protocol("WM_DELETE_WINDOW", self.on_closing)  #

        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")  #
            icon_path = os.path.join(base_path, "icon.ico")  #
            if os.path.exists(icon_path):  #
                self.iconbitmap(icon_path)  #
                print(f"INFO: 图标加载成功: {icon_path}")  #
        except Exception as e:  #
            print(f"警告: 加载图标失败: {e}。")  #

    def _handle_textbox_focus_in(self, event, textbox_widget, placeholder_text_key):
        """当Textbox获得焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        placeholder = _(placeholder_text_key)  # 获取当前语言的占位符
        if current_text == placeholder:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(text_color=self.default_text_color)

    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(placeholder_text_key)  # 获取当前语言的占位符
            textbox_widget.configure(text_color=self.placeholder_color)
            textbox_widget.insert("0.0", placeholder)

    def _create_menu_bar(self):  #
        if hasattr(self, 'menubar') and isinstance(self.menubar, tk.Menu) and self.menubar.winfo_exists():  #
            self.menubar.destroy()  #

        self.menubar = tk.Menu(self)  #
        self.configure(menu=self.menubar)  #

        self.file_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)  #
        self.menubar.add_cascade(label=_("文件"), menu=self.file_menu, font=self.menu_font)  #
        self.file_menu.add_command(label=_("加载配置..."), command=self.load_config_file)  #
        self.file_menu.add_command(label=_("生成默认配置..."), command=self._generate_default_configs_gui)  #
        self.file_menu.add_separator()  #
        self.file_menu.add_command(label=_("退出"), command=self.on_closing)  #

        self.help_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)  #
        self.menubar.add_cascade(label=_("帮助"), menu=self.help_menu, font=self.menu_font)  #
        self.help_menu.add_command(label=_("在线帮助文档..."), command=self._open_online_help)  #
        self.help_menu.add_command(label=_("关于..."), command=self.show_about_dialog)  #

    def _open_online_help(self):  #
        try:
            self._log_to_viewer(_("正在浏览器中打开在线帮助文档..."))  #
            webbrowser.open(PKG_HELP_URL)  #
        except Exception as e:  #
            self.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))  #

    def show_about_dialog(self):  #
        if hasattr(self, 'about_window') and self.about_window.winfo_exists():  #
            self.about_window.focus_set()  #
            return  #

        self.about_window = ctk.CTkToplevel(self)  #
        self.about_window.title(_("关于"))  #
        self.about_window.transient(self)  #
        self.about_window.grab_set()  #
        self.about_window.resizable(False, False)  #

        about_frame = ctk.CTkFrame(self.about_window)  #
        about_frame.pack(fill="both", expand=True, padx=20, pady=20)  #

        about_content = get_about_text(translator=_)  #

        about_label = ctk.CTkLabel(about_frame,  #
                                   text=about_content,  #
                                   font=self.app_font,  #
                                   justify="left")  #
        about_label.pack(pady=10, padx=10)  #

        close_button = ctk.CTkButton(about_frame, text=_("关闭"), command=self.about_window.destroy,
                                     font=self.app_font)  #
        self.translatable_widgets[close_button] = "关闭"  #
        close_button.pack(pady=(5, 10))  #

        self.about_window.update_idletasks()  #
        x = self.winfo_x() + (self.winfo_width() - self.about_window.winfo_width()) // 2  #
        y = self.winfo_y() + (self.winfo_height() - self.about_window.winfo_height()) // 2  #
        self.about_window.geometry(f"+{x}+{y}")  #
        self.about_window.wait_window()  #

    def _create_config_widgets_structure(self):  #
        self.config_frame = ctk.CTkFrame(self.main_container)  #
        self.config_frame.pack(side="top", pady=(5, 10), padx=0, fill="x")  #
        self.config_frame.grid_columnconfigure(0, weight=1)  #

        self.config_path_label_base_key = "配置文件"  #
        self.config_path_display_part = lambda: os.path.basename(self.config_path) if self.config_path else _(
            "未加载 (请从“文件”菜单加载)")  #
        self.config_path_label = ctk.CTkLabel(self.config_frame,  #
                                              text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}",
                                              #
                                              font=self.app_font, anchor="w")  #
        self.translatable_widgets[self.config_path_label] = ("label_with_dynamic_part", self.config_path_label_base_key,
                                                             self.config_path_display_part)  #
        self.config_path_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")  #

        self.language_label = ctk.CTkLabel(self.config_frame, text=_("语言:"), font=self.app_font)  #
        self.translatable_widgets[self.language_label] = "语言:"  #
        self.language_label.grid(row=0, column=1, padx=(10, 5), pady=10)  #

        self.language_optionmenu = ctk.CTkOptionMenu(self.config_frame, variable=self.selected_language_var,  #
                                                     values=list(self.LANG_CODE_TO_NAME.values()),  #
                                                     command=self.on_language_change,  #
                                                     font=self.app_font, dropdown_font=self.app_font)  #
        self.language_optionmenu.grid(row=0, column=2, padx=(0, 10), pady=10)  #

    def on_language_change(self, selected_display_name: str):  #
        new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "en")  #
        self._log_to_viewer(f"{_('语言已更改为:')} {selected_display_name}")  #
        if self.current_config:  #
            self.current_config["i18n_language"] = new_language_code  #
            self._log_to_viewer(_("新语言设置已更新到当前配置中，但尚未保存到文件。"))  #
        self.update_language_ui(new_language_code)  #
        self.show_info_message(_("语言更新"), _("界面语言已更新。"))  #

    def _create_status_widgets_structure(self):  #
        self.status_bar_frame = ctk.CTkFrame(self.main_container, height=35, corner_radius=0)  #
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)  #
        self.status_bar_frame.grid_columnconfigure(0, weight=1)  #
        self.status_label_base_key = "准备就绪"  #
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)  #
        self.translatable_widgets[self.status_label] = ("label_with_dynamic_part", self.status_label_base_key,
                                                        lambda: "")  #
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")  #
        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)  #
        self.progress_bar.set(0)  #
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")  #
        self.progress_bar.grid_remove()  #

    def _create_log_viewer_structure(self):  #
        log_frame = ctk.CTkFrame(self.main_container)  #
        log_frame.pack(side="bottom", fill="x", padx=0, pady=(0, 5))  #
        log_frame.grid_columnconfigure(0, weight=1)  #
        log_header_frame = ctk.CTkFrame(log_frame, fg_color="transparent")  #
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))  #
        log_header_frame.grid_columnconfigure(0, weight=1)  #
        self.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold)  #
        self.translatable_widgets[self.log_viewer_label_widget] = "操作日志"  #
        self.log_viewer_label_widget.grid(row=0, column=0, sticky="w")  #
        self.clear_log_button = ctk.CTkButton(log_header_frame, text=_("清除日志"), width=80, height=28,
                                              command=self.clear_log_viewer, font=self.app_font)  #
        self.translatable_widgets[self.clear_log_button] = "清除日志"  #
        self.clear_log_button.grid(row=0, column=1, sticky="e")  #
        self.log_textbox = ctk.CTkTextbox(log_frame, height=140, state="disabled", wrap="word", font=self.app_font)  #
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))  #

    def _create_tab_view_structure(self):
        self.tab_view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_view_frame.pack(side="top", fill="both", expand=True, pady=0, padx=0)
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

    def _populate_download_tab_structure(self):
        page = self.tab_view.tab(self.download_tab_internal_key)
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Card 1: Download Targets
        target_frame = ctk.CTkFrame(scrollable_frame)
        target_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        target_frame.grid_columnconfigure(1, weight=1)

        target_label = ctk.CTkLabel(target_frame, text=_("下载目标"), font=self.app_font_bold)
        self.translatable_widgets[target_label] = "下载目标"
        target_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        genome_ids_label = ctk.CTkLabel(target_frame, text=_("基因组版本ID:"), font=self.app_font)
        self.translatable_widgets[genome_ids_label] = "基因组版本ID:"
        genome_ids_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.download_genome_ids_entry = ctk.CTkEntry(target_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.download_genome_ids_entry] = "例如: NBI_v1.1, HAU_v2.0 (留空则下载所有)"
        self.download_genome_ids_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        # Card 2: Download Options
        options_frame = ctk.CTkFrame(scrollable_frame)
        options_frame.pack(fill="x", expand=True, pady=10, padx=5)
        options_frame.grid_columnconfigure(1, weight=1)

        options_label = ctk.CTkLabel(options_frame, text=_("下载选项"), font=self.app_font_bold)
        self.translatable_widgets[options_label] = "下载选项"
        options_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        output_dir_label = ctk.CTkLabel(options_frame, text=_("下载输出目录:"), font=self.app_font)
        self.translatable_widgets[output_dir_label] = "下载输出目录:"
        output_dir_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.download_output_dir_entry = ctk.CTkEntry(options_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.download_output_dir_entry] = "可选, 覆盖配置"
        self.download_output_dir_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.dl_browse_button = ctk.CTkButton(options_frame, text=_("浏览..."), width=100, height=35,
                                              command=self.browse_download_output_dir, font=self.app_font)
        self.translatable_widgets[self.dl_browse_button] = "浏览..."
        self.dl_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)

        self.dl_force_checkbox = ctk.CTkCheckBox(options_frame, variable=self.download_force_checkbox_var,
                                                 font=self.app_font)
        self.translatable_widgets[self.dl_force_checkbox] = "强制重新下载已存在的文件"
        self.dl_force_checkbox.grid(row=2, column=1, padx=0, pady=15, sticky="w")

        # Start Button
        self.download_start_button = ctk.CTkButton(scrollable_frame, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.translatable_widgets[self.download_start_button] = "开始下载"
        self.download_start_button.pack(fill="x", padx=5, pady=(10, 5))

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

    def _populate_homology_map_tab_structure(self):
        page = self.tab_view.tab(self.homology_map_tab_internal_key)
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Card 1: Input Genes & Versions
        input_frame = ctk.CTkFrame(scrollable_frame)
        input_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        input_frame.grid_columnconfigure(1, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)

        input_label = ctk.CTkLabel(input_frame, text=_("输入基因与版本"), font=self.app_font_bold)
        self.translatable_widgets[input_label] = "输入基因与版本"
        input_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        gene_ids_label = ctk.CTkLabel(input_frame, text=_("源基因ID (每行一个):"), font=self.app_font)
        self.translatable_widgets[gene_ids_label] = "源基因ID (每行一个):"
        gene_ids_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="nw")
        self.homology_map_genes_entry = ctk.CTkTextbox(input_frame, font=self.app_font, height=120, wrap="none")
        self.homology_map_genes_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="nsew")

        src_assem_label = ctk.CTkLabel(input_frame, text=_("源基因组版本:"), font=self.app_font)
        self.translatable_widgets[src_assem_label] = "源基因组版本:"
        src_assem_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_source_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_source_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        tgt_assem_label = ctk.CTkLabel(input_frame, text=_("目标基因组版本:"), font=self.app_font)
        self.translatable_widgets[tgt_assem_label] = "目标基因组版本:"
        tgt_assem_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_target_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_target_assembly_dropdown.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="ew")

        # Card 2: Homology & Output Files
        file_frame = ctk.CTkFrame(scrollable_frame)
        file_frame.pack(fill="x", expand=True, pady=10, padx=5)
        file_frame.grid_columnconfigure(1, weight=1)

        file_label = ctk.CTkLabel(file_frame, text=_("同源与输出文件"), font=self.app_font_bold)
        self.translatable_widgets[file_label] = "同源与输出文件"
        file_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        sb_file_label = ctk.CTkLabel(file_frame, text=_("源到桥梁文件:"), font=self.app_font)
        self.translatable_widgets[sb_file_label] = "源到桥梁文件:"
        sb_file_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_map_sb_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.homology_map_sb_file_entry] = "从配置加载或在此覆盖"
        self.homology_map_sb_file_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.homology_map_sb_browse_button = ctk.CTkButton(file_frame, text=_("浏览..."), width=100, height=35,
                                                           command=lambda: self._browse_file(
                                                               self.homology_map_sb_file_entry,
                                                               [("CSV files", "*.csv")]), font=self.app_font)
        self.translatable_widgets[self.homology_map_sb_browse_button] = "浏览..."
        self.homology_map_sb_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)

        bt_file_label = ctk.CTkLabel(file_frame, text=_("桥梁到目标文件:"), font=self.app_font)
        self.translatable_widgets[bt_file_label] = "桥梁到目标文件:"
        bt_file_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_map_bt_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.homology_map_bt_file_entry] = "从配置加载或在此覆盖"
        self.homology_map_bt_file_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.homology_map_bt_browse_button = ctk.CTkButton(file_frame, text=_("浏览..."), width=100, height=35,
                                                           command=lambda: self._browse_file(
                                                               self.homology_map_bt_file_entry,
                                                               [("CSV files", "*.csv")]), font=self.app_font)
        self.translatable_widgets[self.homology_map_bt_browse_button] = "浏览..."
        self.homology_map_bt_browse_button.grid(row=2, column=2, padx=(0, 10), pady=10)

        output_csv_label = ctk.CTkLabel(file_frame, text=_("结果输出CSV文件:"), font=self.app_font)
        self.translatable_widgets[output_csv_label] = "结果输出CSV文件:"
        output_csv_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="w")
        self.homology_map_output_csv_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.homology_map_output_csv_entry] = "可选, 默认自动生成"
        self.homology_map_output_csv_entry.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.homology_map_output_browse_button = ctk.CTkButton(file_frame, text=_("浏览..."), width=100, height=35,
                                                               command=lambda: self._browse_save_file(
                                                                   self.homology_map_output_csv_entry,
                                                                   [("CSV files", "*.csv")]), font=self.app_font)
        self.translatable_widgets[self.homology_map_output_browse_button] = "浏览..."
        self.homology_map_output_browse_button.grid(row=3, column=2, padx=(0, 10), pady=10)

        self.homology_map_start_button = ctk.CTkButton(scrollable_frame, text=_("开始同源映射"), height=40,
                                                       command=self.start_homology_map_task, font=self.app_font_bold)
        self.translatable_widgets[self.homology_map_start_button] = "开始同源映射"
        self.homology_map_start_button.pack(fill="x", padx=5, pady=(10, 5))

    def _populate_gff_query_tab_structure(self):
        page = self.tab_view.tab(self.gff_query_tab_internal_key)
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        query_frame = ctk.CTkFrame(scrollable_frame)
        query_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        query_frame.grid_columnconfigure(1, weight=1)
        query_frame.grid_rowconfigure(2, weight=1)

        query_label = ctk.CTkLabel(query_frame, text=_("查询条件"), font=self.app_font_bold)
        self.translatable_widgets[query_label] = "查询条件"
        query_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        assem_id_label = ctk.CTkLabel(query_frame, text=_("基因组版本ID:"), font=self.app_font)
        self.translatable_widgets[assem_id_label] = "基因组版本ID:"
        assem_id_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(query_frame, font=self.app_font, height=35,
                                                             variable=self.selected_gff_query_assembly,
                                                             values=[_("加载中...")], dropdown_font=self.app_font)
        self.gff_query_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        gene_ids_label = ctk.CTkLabel(query_frame, text=_("基因ID (每行一个):"), font=self.app_font)
        self.translatable_widgets[gene_ids_label] = "基因ID (每行一个):"
        gene_ids_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="nw")
        self.gff_query_genes_entry = ctk.CTkTextbox(query_frame, font=self.app_font, height=120, wrap="none")
        self.translatable_widgets[self.gff_query_genes_entry] = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(与下方区域查询二选一)"
        self.gff_query_genes_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="nsew")

        region_label = ctk.CTkLabel(query_frame, text=_("染色体区域:"), font=self.app_font)
        self.translatable_widgets[region_label] = "染色体区域:"
        region_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="w")
        self.gff_query_region_entry = ctk.CTkEntry(query_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.gff_query_region_entry] = "例如: chr1:1000-5000 (与上方基因ID二选一)"
        self.gff_query_region_entry.grid(row=3, column=1, padx=(0, 10), pady=10, sticky="ew")

        output_frame = ctk.CTkFrame(scrollable_frame)
        output_frame.pack(fill="x", expand=True, pady=10, padx=5)
        output_frame.grid_columnconfigure(1, weight=1)

        output_label = ctk.CTkLabel(output_frame, text=_("输出设置"), font=self.app_font_bold)
        self.translatable_widgets[output_label] = "输出设置"
        output_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        output_csv_label = ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font)
        self.translatable_widgets[output_csv_label] = "结果输出CSV文件:"
        output_csv_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.gff_query_output_csv_entry] = "可选, 默认自动生成"
        self.gff_query_output_csv_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.gff_query_output_browse_button = ctk.CTkButton(output_frame, text=_("浏览..."), width=100, height=35,
                                                            command=lambda: self._browse_save_file(
                                                                self.gff_query_output_csv_entry,
                                                                [("CSV files", "*.csv")]), font=self.app_font)
        self.translatable_widgets[self.gff_query_output_browse_button] = "浏览..."
        self.gff_query_output_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)

        self.gff_query_start_button = ctk.CTkButton(scrollable_frame, text=_("开始基因查询"), height=40,
                                                    command=self.start_gff_query_task, font=self.app_font_bold)
        self.translatable_widgets[self.gff_query_start_button] = "开始基因查询"
        self.gff_query_start_button.pack(fill="x", padx=5, pady=(10, 5))


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

    def update_language_ui(self, lang_code_to_set=None):  #
        global _  #
        if not lang_code_to_set:  #
            selected_display_name = self.selected_language_var.get()  #
            lang_code_to_set = self.LANG_NAME_TO_CODE.get(selected_display_name, "en")  #
        try:
            new_translator = setup_cli_i18n(language_code=lang_code_to_set, app_name=APP_NAME_FOR_I18N)  #
            _ = new_translator if callable(new_translator) else (lambda s: s)  #
        except Exception as e:  #
            _ = lambda s: s  #
            print(f"语言设置错误: {e}")  #
        if hasattr(self, 'tab_view') and hasattr(self.tab_view, '_segmented_button'):  #
            try:
                new_display_names = [  #
                    _(self.download_tab_display_key),  #
                    _(self.integrate_tab_display_key),  #
                    _(self.homology_map_tab_display_key),  #
                    _(self.gff_query_tab_display_key),  #
                    _(self.editor_tab_display_key)  #
                ]
                self.tab_view._segmented_button.configure(values=new_display_names, font=self.app_font)  #
                self.tab_view._name_list = new_display_names  #
                internal_keys_order = [  #
                    self.download_tab_internal_key, self.integrate_tab_internal_key,  #
                    self.homology_map_tab_internal_key, self.gff_query_tab_internal_key,  #
                    self.editor_tab_internal_key  #
                ]
                new_tab_dict = {}  #
                for i, internal_key in enumerate(internal_keys_order):  #
                    if internal_key in self.tab_view._tab_dict:  #
                        tab_frame = self.tab_view._tab_dict[internal_key]  #
                        new_tab_dict[new_display_names[i]] = tab_frame  #
                self.tab_view._tab_dict = new_tab_dict  #
                current_tab_name = self.tab_view._current_name  #
                if current_tab_name in internal_keys_order:  #
                    idx = internal_keys_order.index(current_tab_name)  #
                    self.tab_view._current_name = new_display_names[idx]  #
                    self.tab_view._segmented_button.set(new_display_names[idx])  #
            except Exception as e_tab_update:  #
                print(f"警告: Tab按钮文本或字体更新时发生意外错误: {e_tab_update}")  #
        if hasattr(self, 'title_text_key'): self.title(_(self.title_text_key))  #
        if hasattr(self, 'menubar'): self._create_menu_bar()  #
        for widget, text_info in self.translatable_widgets.items():  #
            if widget and hasattr(widget, 'configure') and widget.winfo_exists():  #
                try:
                    if isinstance(text_info, tuple) and text_info[0] == "label_with_dynamic_part":  #
                        base_key, dynamic_part_func = text_info[1], text_info[2]  #
                        widget.configure(text=f"{_(base_key)}: {dynamic_part_func()}")  #
                    elif isinstance(text_info, str):  #
                        if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):  #
                            # Check if it's one of the multi-line textboxes for gene input
                            if widget in [self.homology_map_genes_entry, self.gff_query_genes_entry]:
                                # For multi-line text boxes, we manage placeholder by inserting text
                                # So, update the inserted text if it's a placeholder
                                current_text = widget.get("1.0", tk.END).strip()
                                old_placeholder = self.translatable_widgets.get(widget, "")  # Get original key
                                if old_placeholder and current_text == _(
                                        old_placeholder):  # If current is translated old
                                    widget.delete("1.0", tk.END)
                                    widget.insert("0.0", _(text_info))  # Insert new translated placeholder
                                elif not current_text:  # If empty, insert new placeholder
                                    widget.insert("0.0", _(text_info))
                            else:  # For single line CTkEntry
                                widget.configure(placeholder_text=_(text_info))  #
                        else:  # For CTkLabel, CTkButton etc.
                            widget.configure(text=_(text_info))  #
                except Exception as e_widget_update:  #
                    print(f"控件文本更新失败 {widget}: {e_widget_update}")  #

            # 特别处理 Textbox 的占位符更新
        textboxes_with_placeholders = [
            (self.homology_map_genes_entry, self.placeholder_genes_homology_key),
            (self.gff_query_genes_entry, self.placeholder_genes_gff_key)
        ]

        for textbox, placeholder_key in textboxes_with_placeholders:
            if textbox and textbox.winfo_exists():
                current_text = textbox.get("1.0", tk.END).strip()
                # 如果是空的，或者内容是旧的占位符，则更新
                is_placeholder_or_empty = not current_text  # 检查是否为空
                if not is_placeholder_or_empty:  # 如果不为空，检查是否是任何语言的占位符
                    for key_text in [self.placeholder_genes_homology_key, self.placeholder_genes_gff_key]:
                        for lang in self.LANG_CODE_TO_NAME.keys():
                            # 模拟获取其他语言的占位符
                            temp_trans = setup_cli_i18n(language_code=lang, app_name=APP_NAME_FOR_I18N)
                            if current_text == temp_trans(key_text):
                                is_placeholder_or_empty = True
                                break
                        if is_placeholder_or_empty: break

                if is_placeholder_or_empty:
                    textbox.delete("1.0", tk.END)
                    textbox.configure(text_color=self.placeholder_color)
                    textbox.insert("0.0", _(placeholder_key))

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

    def _apply_config_to_ui(self):  #
        if not self.current_config: self._log_to_viewer(_("没有加载配置，无法应用到UI。"), level="WARNING"); return  #
        config_lang_code = self.current_config.get("i18n_language", "zh-hans")  #
        display_name = self.LANG_CODE_TO_NAME.get(config_lang_code, "English")  #
        self.selected_language_var.set(display_name)  #
        self.update_language_ui(config_lang_code)  #
        self._update_assembly_id_dropdowns()  #
        downloader_cfg = self.current_config.get("downloader", {})  #
        if self.download_genome_ids_entry: self.download_genome_ids_entry.delete(0, tk.END)  #
        if self.download_output_dir_entry:  #
            self.download_output_dir_entry.delete(0, tk.END)  #
            self.download_output_dir_entry.insert(0, downloader_cfg.get("download_output_base_dir", ""))  #
        if self.download_force_checkbox_var: self.download_force_checkbox_var.set(
            bool(downloader_cfg.get("force_download", False)))  #
        integration_cfg = self.current_config.get("integration_pipeline", {})  #
        self.selected_bsa_assembly.set(integration_cfg.get("bsa_assembly_id", ""))  #
        self.selected_hvg_assembly.set(integration_cfg.get("hvg_assembly_id", ""))  #
        self.selected_homology_source_assembly.set(integration_cfg.get("bsa_assembly_id", ""))  #
        self.selected_homology_target_assembly.set(integration_cfg.get("hvg_assembly_id", ""))  #
        default_gff_assembly = integration_cfg.get("bsa_assembly_id") or integration_cfg.get("hvg_assembly_id", "")  #
        self.selected_gff_query_assembly.set(default_gff_assembly)  #
        excel_path = integration_cfg.get("input_excel_path", "")  #
        if self.integrate_excel_entry:  #
            self.integrate_excel_entry.delete(0, tk.END)  #
            self.integrate_excel_entry.insert(0, excel_path)  #
        self._update_excel_sheet_dropdowns()  # This will set sheet names based on config and excel_path
        self._apply_config_to_editor_ui()  #
        self._log_to_viewer(_("配置已成功应用到所有UI字段。"))  #

    def start_integrate_task(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return  #
        self._update_button_states(is_task_running=True)  #
        # Update config with values from UI before starting task
        cfg_pipeline = self.current_config.setdefault('integration_pipeline', {})  #
        cfg_pipeline['bsa_assembly_id'] = self.selected_bsa_assembly.get()  #
        cfg_pipeline['hvg_assembly_id'] = self.selected_hvg_assembly.get()  #
        cfg_pipeline['bsa_sheet_name'] = self.selected_bsa_sheet.get()  #
        cfg_pipeline['hvg_sheet_name'] = self.selected_hvg_sheet.get()  #
        excel_override = self.integrate_excel_entry.get().strip() or None  #
        # ... (rest of the start_integrate_task logic)
        task_display_name = _("整合分析")  #
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")  #
        self.progress_bar.pack(side="right", padx=10, pady=5);
        self.progress_bar.set(0)  #
        task_internal_key = self.INTEGRATE_TASK_KEY  #
        thread_kwargs = {  #
            "config": self.current_config,  #
            "input_excel_path_override": excel_override,  #
            "status_callback": self.gui_status_callback,  #
            "progress_callback": self.gui_progress_callback,  #
            "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                          task_display_name),  #
        }
        if not COTTON_TOOLKIT_LOADED:  #
            if "input_excel_path_override" in thread_kwargs: del thread_kwargs["input_excel_path_override"];  #
            if "output_sheet_name_override" in thread_kwargs: del thread_kwargs["output_sheet_name_override"]  #
        thread = threading.Thread(target=integrate_bsa_with_hvg, kwargs=thread_kwargs, daemon=True)  #
        thread.start()  #

    def start_homology_map_task(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return  #
        self._update_button_states(is_task_running=True)  #
        gene_ids_text = self.homology_map_genes_entry.get("1.0", tk.END).strip()  #
        placeholder_text = _("例如:\nGhir.A01G000100\nGhir.A01G000200\n(必填)")  #
        source_gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if
                                line.strip() and line.strip() != placeholder_text] if gene_ids_text != placeholder_text else []  #
        if not source_gene_ids_list:  #
            self.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"));
            self._update_button_states(False);
            return  #
        source_assembly_id_override = self.selected_homology_source_assembly.get()  #
        target_assembly_id_override = self.selected_homology_target_assembly.get()  #
        s_to_b_homology_file_override = self.homology_map_sb_file_entry.get().strip() or None  #
        b_to_t_homology_file_override = self.homology_map_bt_file_entry.get().strip() or None  #
        output_csv_path = self.homology_map_output_csv_entry.get().strip() or None  #
        task_display_name = _("同源映射")  #
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")  #
        self.progress_bar.pack(side="right", padx=10, pady=5);
        self.progress_bar.set(0)  #
        task_internal_key = self.HOMOLOGY_MAP_TASK_KEY  #
        thread_kwargs = {"config": self.current_config, "source_gene_ids_override": source_gene_ids_list,
                         "source_assembly_id_override": source_assembly_id_override,
                         "target_assembly_id_override": target_assembly_id_override,
                         "s_to_b_homology_file_override": s_to_b_homology_file_override,
                         "b_to_t_homology_file_override": b_to_t_homology_file_override,
                         "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
                         "progress_callback": self.gui_progress_callback,
                         "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                                       task_display_name)}  #
        thread = threading.Thread(target=run_homology_mapping_standalone, kwargs=thread_kwargs, daemon=True)  #
        thread.start()  #

    def start_gff_query_task(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return  #
        self._update_button_states(is_task_running=True)  #
        assembly_id_override = self.selected_gff_query_assembly.get()  #
        gene_ids_text = self.gff_query_genes_entry.get("1.0", tk.END).strip()  #
        current_placeholder = _(self.placeholder_genes_gff_key)  # 获取当前语言的占位符

        if gene_ids_text == current_placeholder or not gene_ids_text:
            gene_ids_list = None
        else:
            gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        region_str = self.gff_query_region_entry.get().strip()  #
        output_csv_path = self.gff_query_output_csv_entry.get().strip() or None  #
        region_tuple = None  #
        if region_str:  #
            try:
                parts = region_str.split(':')  #
                if len(parts) == 2 and '-' in parts[1]:  #
                    chrom = parts[0]  #
                    start_end = parts[1].split('-')  #
                    start = int(start_end[0])  #
                    end = int(start_end[1])  #
                    region_tuple = (chrom, start, end)  #
                else:
                    raise ValueError("Format error")  #
            except Exception:
                self.show_error_message(_("输入错误"),
                                        _("染色体区域格式不正确。请使用 'chr:start-end' 格式。")); self._update_button_states(
                    False); return  #
        if not assembly_id_override or assembly_id_override == _("加载中..."): self.show_error_message(_("输入缺失"),
                                                                                                       _("请选择一个基因组版本ID。")); self._update_button_states(
            False); return  #
        if not gene_ids_list and not region_tuple: self.show_error_message(_("输入缺失"),
                                                                           _("必须提供基因ID列表或染色体区域进行查询。")); self._update_button_states(
            False); return  #
        task_display_name = _("GFF基因查询")  #
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")  #
        self.progress_bar.pack(side="right", padx=10, pady=5);
        self.progress_bar.set(0)  #
        task_internal_key = self.GFF_QUERY_TASK_KEY  #
        thread_kwargs = {"config": self.current_config, "assembly_id_override": assembly_id_override,
                         "gene_ids_override": gene_ids_list, "region_override": region_tuple,
                         "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
                         "progress_callback": self.gui_progress_callback,
                         "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                                       task_display_name)}  #
        thread = threading.Thread(target=run_gff_gene_lookup_standalone, kwargs=thread_kwargs, daemon=True)  #
        thread.start()  #

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

    def show_info_message(self, title, message):  #
        self._log_to_viewer(f"{title}: {message}", level="INFO")  #
        if self.status_label and self.status_label.winfo_exists():  #
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color=self.default_label_text_color)  #

    def show_error_message(self, title, message):  #
        self._log_to_viewer(f"ERROR - {title}: {message}", level="ERROR")  #
        if self.status_label and self.status_label.winfo_exists():  #
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="red")  #
        messagebox.showerror(title, message)  #

    def show_warning_message(self, title, message):  #
        self._log_to_viewer(f"WARNING - {title}: {message}", level="WARNING")  #
        if self.status_label and self.status_label.winfo_exists():  #
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="orange")  #
        messagebox.showwarning(title, message)  #

    def gui_status_callback(self, message):
        self.message_queue.put(("status", message)); self._log_to_viewer(str(message))  #

    def gui_progress_callback(self, percentage, message):
        self.message_queue.put(("progress", (percentage, message)))  #

    def task_done_callback(self, task_internal_key, success=True, task_display_name="任务"):
        self.message_queue.put(("task_done", (task_internal_key, success, task_display_name)))  #

    def check_queue_periodic(self):  #
        try:
            while not self.message_queue.empty():  #
                message_type, data = self.message_queue.get_nowait()  #
                if message_type == "status":  #
                    self.status_label.configure(text=str(data)[:150], text_color=self.default_label_text_color)  #
                elif message_type == "progress":  #
                    percentage, text = data  #
                    if not self.progress_bar.winfo_ismapped(): self.progress_bar.grid()  # Use grid() if it was removed by grid_remove()
                    self.progress_bar.set(percentage / 100.0)  #
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)",
                                                text_color=self.default_label_text_color)  #
                elif message_type == "task_done":  #
                    task_internal_key, success, task_display_name = data  #
                    self.progress_bar.grid_remove()  # Use grid_remove()
                    final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))  #
                    self.status_label.configure(text=final_message, text_color=("green" if success else "red"))  #
                    self._log_to_viewer(final_message)  #
                    self._update_button_states(is_task_running=False)  #
        except Exception:
            pass  #
        self.after(100, self.check_queue_periodic)  #

    def on_closing(self):  #
        if messagebox.askokcancel(_("退出"), _("您确定要退出吗?")): self.destroy()  #

    def load_config_file(self):  #
        filepath = filedialog.askopenfilename(title=_("选择配置文件"),
                                              filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")))  #
        if filepath:  #
            self._log_to_viewer(f"{_('尝试加载配置文件:')} {filepath}")  #
            try:
                loaded_config = load_config(filepath)  #
                if loaded_config:  #
                    self.current_config = loaded_config  #
                    self.config_path = filepath  #
                    if self.config_path_label: self.config_path_label.configure(
                        text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}")  #
                    self._apply_config_to_ui()  #
                    self._update_button_states()  #
                    self._log_to_viewer(f"{_('配置文件加载成功:')} {filepath}")  #
                else:
                    self.show_error_message(_("加载失败"), _("无法加载配置文件或配置文件内容为空。"))  #
            except Exception as e:
                self.show_error_message(_("加载错误"), f"{_('加载配置文件时发生错误:')} {e}"); self._log_to_viewer(
                    f"ERROR: {_('加载配置文件时发生错误:')} {e}", level="ERROR")  #
        else:
            self._log_to_viewer(_("取消加载配置文件。"))  #

    def _generate_default_configs_gui(self):  #
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))  #
        if output_dir:  #
            self._log_to_viewer(f"{_('尝试在以下位置生成默认配置文件:')} {output_dir}")  #
            try:
                success, main_cfg_path, gs_cfg_path = generate_default_config_files(output_dir, overwrite=False)  #
                if success:
                    messagebox.showinfo(_("生成成功"),
                                        f"{_('默认配置文件已成功生成到:')}\n{main_cfg_path}\n{gs_cfg_path}\n{_('请加载 config.yml 文件以开始使用。')}"); self._log_to_viewer(
                        f"{_('默认配置文件生成成功。')} Main: {main_cfg_path}, Genome Sources: {gs_cfg_path}")  #
                else:
                    messagebox.showerror(_("生成失败"), _("生成默认配置文件失败，请检查日志。")); self._log_to_viewer(
                        _("生成默认配置文件失败。"), level="ERROR")  #
            except Exception as e:
                messagebox.showerror(_("错误"), f"{_('生成默认配置文件时发生错误:')} {e}"); self._log_to_viewer(
                    f"ERROR: {_('生成默认配置文件时发生错误:')} {e}", level="ERROR")  #
        else:
            self._log_to_viewer(_("取消生成默认配置文件。"))  #

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
                                    level="WARNING"); gff_yaml_str = str(gff_files_yaml)  #
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
                gff_dict = yaml.safe_load(gff_yaml_str); self.current_config["integration_pipeline"][
                    "gff_files"] = gff_dict if isinstance(gff_dict, dict) else self.show_error_message(_("保存错误"),
                                                                                                       _("GFF文件路径的YAML格式不正确。")) or {}  #
            else:
                self.current_config["integration_pipeline"]["gff_files"] = {}  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('GFF文件路径YAML解析错误:')} {e}"); return  #
        if self.config_path:  #
            try:
                save_config_to_yaml(self.current_config, self.config_path); self._log_to_viewer(
                    f"{_('主配置文件已保存到:')} {self.config_path}"); self.show_info_message(_("保存成功"),
                                                                                              _("主配置文件已成功保存。"))  #
            except Exception as e:
                self.show_error_message(_("保存错误"), f"{_('保存主配置文件时发生错误:')} {e}"); self._log_to_viewer(
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
                                level="ERROR"); self.editor_gs_raw_yaml.delete("1.0",
                                                                               tk.END); self.editor_gs_raw_yaml.insert(
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
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}"); self._log_to_viewer(
                f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")  #
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}"); self._log_to_viewer(
                f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")  #

    def _update_button_states(self, is_task_running=False):  #
        action_state = "disabled" if is_task_running else "normal"  #
        task_button_state = "normal" if self.current_config and not is_task_running else "disabled"  #
        if self.download_start_button: self.download_start_button.configure(state=task_button_state)  #
        if self.integrate_start_button: self.integrate_start_button.configure(state=task_button_state)  #
        if self.homology_map_start_button: self.homology_map_start_button.configure(state=task_button_state)  #
        if self.gff_query_start_button: self.gff_query_start_button.configure(state=task_button_state)  #
        if self.language_optionmenu: self.language_optionmenu.configure(state=action_state)  #
        if self.editor_save_button: self.editor_save_button.configure(
            state="normal" if self.current_config and not is_task_running else "disabled")  #
        if self.editor_gs_save_button: self.editor_gs_save_button.configure(
            state="normal" if self.current_config and not is_task_running else "disabled")  #
        if self.editor_gs_load_button: self.editor_gs_load_button.configure(
            state="normal" if self.current_config and not is_task_running else "disabled")  #

    def start_download_task(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return  #
        self._update_button_states(is_task_running=True)  #
        genome_ids_str = self.download_genome_ids_entry.get() if self.download_genome_ids_entry else ""  #
        versions_to_download = [gid.strip() for gid in genome_ids_str.split(',') if gid.strip()]  #
        output_dir_override = self.download_output_dir_entry.get().strip() or None  #
        force_download_override = self.download_force_checkbox_var.get()  #
        downloader_cfg = self.current_config.get('downloader', {})  #
        if not versions_to_download and not downloader_cfg.get("genome_sources_file") and not downloader_cfg.get(
                "genome_sources"):  #
            self.show_warning_message(_("输入缺失"), _("请输入要下载的基因组版本ID。"));
            self._update_button_states(False);
            return  #
        task_display_name = _("下载")  #
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")  #
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e");
        self.progress_bar.set(0)  # Use grid() to show
        task_internal_key = self.DOWNLOAD_TASK_KEY  #
        thread_kwargs = {"config": self.current_config,
                         "genome_versions_to_download_override": versions_to_download if versions_to_download else None,
                         "force_download_override": force_download_override,
                         "output_base_dir_override": output_dir_override, "status_callback": self.gui_status_callback,
                         "progress_callback": self.gui_progress_callback,
                         "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                                       task_display_name)}  #
        thread = threading.Thread(target=download_genome_data, kwargs=thread_kwargs, daemon=True)  #
        thread.start()  #


if __name__ == "__main__":  #
    app = CottonToolkitApp()  #
    app.mainloop()  #