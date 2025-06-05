# gui_app.py
import sys #
import customtkinter as ctk #
import tkinter as tk #
from tkinter import filedialog, messagebox #
import threading #
from queue import Queue #
import os #
import time #
import yaml #
import shutil #
import webbrowser #

try:
    # 导入后端模块和全局变量
    from cotton_toolkit.config.loader import load_config, save_config_to_yaml, get_genome_data_sources, \
        generate_default_config_files #
    from cotton_toolkit.core.downloader import download_genome_data #
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg #
    from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text  # 导入 get_about_text #
    from cotton_toolkit import VERSION as pkg_version, HELP_URL as PKG_HELP_URL  # 导入版本和帮助URL #

    COTTON_TOOLKIT_LOADED = True #
    print("INFO: gui_app.py - Successfully imported COTTON_TOOLKIT modules.") #
except ImportError as e: #
    print(f"错误：无法导入 cotton_toolkit 模块 (gui_app.py): {e}") #
    COTTON_TOOLKIT_LOADED = False #
    pkg_version = "DEV" #
    PKG_HELP_URL = "https://github.com/PureAmaya/friendly_cotton_toolkit/blob/master/HELP.md"  # Fallback URL #


    # --- MOCK 函数：现在将 get_about_text 的 MOCK 定义移到这里 ---
    def load_config(path): #
        print(f"MOCK (gui_app.py): load_config({path})") #
        return {"mock_config": True, "i18n_language": "zh-hans", "_config_file_abs_path_": os.path.abspath(path), #
                "downloader": {"download_output_base_dir": "mock_gui_downloads_from_config/", "force_download": True, #
                               "genome_sources_file": "mock_genome_sources.yml"}, #
                "integration_pipeline": {"input_excel_path": "mock_gui_integration_input_from_config.xlsx", #
                                         "output_sheet_name": "MockGUIOutputSheetFromConfig"}} #


    def save_config_to_yaml(config_dict, file_path): #
        print(f"MOCK (gui_app.py): save_config_to_yaml({file_path})") #
        with open(file_path, 'w', encoding='utf-8') as f: yaml.dump(config_dict, f) #
        return True #


    def get_genome_data_sources(main_config): #
        print(f"MOCK (gui_app.py): get_genome_data_sources called") #
        return {"MOCK_GS_1": {"species_name": "Mock Genome 1"}} #


    def generate_default_config_files(output_dir, overwrite=False, main_config_filename="config.yml", #
                                      genome_sources_filename="genome_sources_list.yml"): #
        print(f"MOCK (gui_app.py): generate_default_config_files called for {output_dir}") #
        os.makedirs(output_dir, exist_ok=True) #
        with open(os.path.join(output_dir, main_config_filename), 'w') as f: f.write("mock_config: true\n") #
        with open(os.path.join(output_dir, genome_sources_filename), 'w') as f: f.write("mock_gs: true\n") #
        return True, os.path.join(output_dir, main_config_filename), os.path.join(output_dir, genome_sources_filename) #


    def download_genome_data(**kwargs): #
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get( #
            'progress_callback'), kwargs.get('task_done_callback') #
        task_display_name = _("下载") #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...") #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%") #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!"); #
        if task_done_cb: task_done_cb(CottonToolkitApp.DOWNLOAD_TASK_KEY, True, task_display_name) #


    def integrate_bsa_with_hvg(**kwargs): #
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get( #
            'progress_callback'), kwargs.get('task_done_callback') #
        task_display_name = _("整合分析") #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...") #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%") #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!"); #
        if task_done_cb: task_done_cb(CottonToolkitApp.INTEGRATE_TASK_KEY, True, task_display_name) #
        return True #


    def setup_cli_i18n(language_code='en', app_name='cotton_toolkit'): #
        return lambda s: str(s) + f" (mock_{language_code})" #


    # MOCK for get_about_text
    def get_about_text(translator): #
        return "Mock About Text" #

_ = lambda s: str(s) #

APP_VERSION = pkg_version #
HELP_URL = PKG_HELP_URL #


class CottonToolkitApp(ctk.CTk): #
    DOWNLOAD_TASK_KEY = "DOWNLOAD_TASK" #
    INTEGRATE_TASK_KEY = "INTEGRATE_TASK" #
    EDITOR_TAB_KEY = "EDITOR_TAB_INTERNAL" #

    def __init__(self): #
        super().__init__() #
        self.translatable_widgets = {} #
        self.selected_language = tk.StringVar(value="zh-hans") #
        self.title_text_key = "Cotton Toolkit GUI" #
        self.title(_(self.title_text_key)) #
        self.geometry("950x650") #
        self.minsize(950, 650) #
        ctk.set_appearance_mode("System") #
        ctk.set_default_color_theme("blue") #

        self.current_config = None #
        self.config_path = None #
        self.message_queue = Queue() #

        try:
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"] #
        except Exception: #
            self.default_label_text_color = ("#000000", "#FFFFFF") #

        self.app_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14) #
        self.app_font_bold = ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold") #
        self.menu_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14) #

        # --- FIX: 初始化所有UI相关属性为 None，以消除Linter警告 ---
        self.config_path_label = None #
        self.language_label = None #
        self.language_optionmenu = None #

        self.download_genome_ids_entry = None #
        self.download_output_dir_entry = None #
        self.dl_browse_button = None #
        self.download_force_checkbox_var = tk.BooleanVar()  # Tkinter变量直接初始化 #
        self.dl_force_checkbox = None #
        self.download_start_button = None #

        self.integrate_excel_entry = None #
        self.int_excel_browse_button = None #
        self.integrate_output_sheet_entry = None #
        self.integrate_start_button = None #

        self.editor_dl_output_dir = None #
        self.editor_dl_force_var = tk.BooleanVar()  # Tkinter变量直接初始化 #
        self.editor_dl_force_switch = None #
        # 添加新的代理输入字段的属性初始化
        self.editor_dl_proxy_http = None #
        self.editor_dl_proxy_https = None #

        self.editor_pl_excel_path = None #
        self.editor_pl_output_sheet = None #
        self.editor_pl_gff_files = None #
        self.editor_save_button = None #
        self.editor_gs_raw_yaml = None #
        self.editor_gs_save_button = None #
        self.editor_gs_load_button = None #

        self.log_viewer_label_widget = None #
        self.clear_log_button = None #
        self.log_textbox = None #

        self.status_label = None #
        self.progress_bar = None #

        self.menubar = None #
        self.file_menu = None #
        self.help_menu = None #
        self.about_window = None  # Toplevel window #

        self._create_menu_bar() #
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent") #
        self.main_container.pack(fill="both", expand=True, padx=10, pady=(5, 10)) #

        self._create_config_widgets_structure() #
        self._create_status_widgets_structure() #
        self._create_log_viewer_structure() #
        self._create_tab_view_structure() #

        self.update_language_ui() #
        self._update_button_states() #
        self.check_queue_periodic() #
        self.protocol("WM_DELETE_WINDOW", self.on_closing) #

        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".") #
            icon_path = os.path.join(base_path, "icon.ico") #
            if os.path.exists(icon_path): #
                self.iconbitmap(icon_path) #
                print(f"INFO: 图标加载成功: {icon_path}") #
        except Exception as e: #
            print(f"警告: 加载图标失败: {e}。") #
    def _create_menu_bar(self):
        # 首次创建时，self.menubar 为 None，不需要销毁。
        # 只有当菜单栏已经存在且是一个tk.Menu对象时，才尝试销毁它。
        if hasattr(self, 'menubar') and isinstance(self.menubar, tk.Menu) and self.menubar.winfo_exists():
            self.menubar.destroy()

        self.menubar = tk.Menu(self)
        self.configure(menu=self.menubar)

        self.file_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)
        self.menubar.add_cascade(label=_("文件"), menu=self.file_menu, font=self.menu_font)
        self.file_menu.add_command(label=_("加载配置..."), command=self.load_config_file)
        self.file_menu.add_command(label=_("生成默认配置..."), command=self._generate_default_configs_gui)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=_("退出"), command=self.on_closing)

        self.help_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)
        self.menubar.add_cascade(label=_("帮助"), menu=self.help_menu, font=self.menu_font)
        self.help_menu.add_command(label=_("在线帮助文档..."), command=self._open_online_help)
        self.help_menu.add_command(label=_("关于..."), command=self.show_about_dialog)

    def _open_online_help(self):
        try:
            self._log_to_viewer(_("正在浏览器中打开在线帮助文档..."))
            webbrowser.open(HELP_URL)
        except Exception as e:
            self.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))

    def show_about_dialog(self):
        """显示“关于”对话框，内容支持国际化。"""
        if hasattr(self, 'about_window') and self.about_window.winfo_exists():
            self.about_window.focus_set()
            return

        self.about_window = ctk.CTkToplevel(self)
        self.about_window.title(_("关于"))
        self.about_window.transient(self)
        self.about_window.grab_set()
        self.about_window.resizable(False, False)

        about_frame = ctk.CTkFrame(self.about_window)
        about_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 调用通用函数获取文本，并将当前GUI的翻译函数 _ 传递给通用函数
        about_content = get_about_text(translator=_)

        about_label = ctk.CTkLabel(about_frame,
                                   text=about_content,
                                   font=self.app_font,
                                   justify="left")
        about_label.pack(pady=10, padx=10)

        close_button = ctk.CTkButton(about_frame, text=_("关闭"), command=self.about_window.destroy, font=self.app_font)
        self.translatable_widgets[close_button] = "关闭"
        close_button.pack(pady=(5, 10))

        self.about_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - self.about_window.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - self.about_window.winfo_height()) // 2
        self.about_window.geometry(f"+{x}+{y}")
        self.about_window.wait_window()

    def _create_config_widgets_structure(self):
        self.config_frame = ctk.CTkFrame(self.main_container)
        self.config_frame.pack(side="top", pady=(5, 10), padx=0, fill="x")
        self.config_frame.grid_columnconfigure(0, weight=1)

        self.config_path_label_base_key = "配置文件"
        self.config_path_display_part = lambda: os.path.basename(self.config_path) if self.config_path else _(
            "未加载 (请从“文件”菜单加载)")
        self.config_path_label = ctk.CTkLabel(self.config_frame,
                                              text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}",
                                              font=self.app_font, anchor="w")
        self.translatable_widgets[self.config_path_label] = ("label_with_dynamic_part", self.config_path_label_base_key,
                                                             self.config_path_display_part)
        self.config_path_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.language_label = ctk.CTkLabel(self.config_frame, text=_("语言:"), font=self.app_font)
        self.translatable_widgets[self.language_label] = "语言:"
        self.language_label.grid(row=0, column=1, padx=(10, 5), pady=10)

        self.language_optionmenu = ctk.CTkOptionMenu(self.config_frame, variable=self.selected_language,
                                                     values=["zh-hans", "zh-hant", "en", "ja"],
                                                     command=self.on_language_change,
                                                     font=self.app_font, dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=0, column=2, padx=(0, 10), pady=10)

    def on_language_change(self, new_language_code):
        """
        当用户通过下拉菜单更改语言时调用。
        更新翻译函数并重新渲染UI。
        """
        self._log_to_viewer(f"{_('语言已更改为:')} {new_language_code}")
        # 保存新的语言设置到配置（可选，但推荐）
        if self.current_config:
            self.current_config["i18n_language"] = new_language_code
            # 考虑在这里调用 _save_main_config() 或者提供一个“保存配置”按钮
            # 为了避免频繁写入文件，这里不立即保存，而是让用户手动保存或在退出时保存
            self._log_to_viewer(_("新语言设置已更新到当前配置中，但尚未保存到文件。"))

        self.update_language_ui()
        self.show_info_message(_("语言更新"), _("界面语言已更新。"))

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

    def _create_log_viewer_structure(self):
        log_frame = ctk.CTkFrame(self.main_container)
        log_frame.pack(side="bottom", fill="x", padx=0, pady=(0, 5))
        log_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        self.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold)
        self.translatable_widgets[self.log_viewer_label_widget] = "操作日志"
        self.log_viewer_label_widget.grid(row=0, column=0, sticky="w")

        self.clear_log_button = ctk.CTkButton(log_header_frame, text=_("清除日志"), width=80, height=28,
                                              command=self.clear_log_viewer, font=self.app_font)
        self.translatable_widgets[self.clear_log_button] = "清除日志"
        self.clear_log_button.grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(log_frame, height=140, state="disabled", wrap="word", font=self.app_font)
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

    def _create_tab_view_structure(self):
        self.tab_view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_view_frame.pack(side="top", fill="both", expand=True, pady=0, padx=0)
        self.tab_view = ctk.CTkTabview(self.tab_view_frame, corner_radius=8)
        self.tab_view.pack(fill="both", expand=True, padx=0, pady=0)

        self.download_tab_internal_key = "DOWNLOAD_TAB_INTERNAL"
        self.integrate_tab_internal_key = "INTEGRATE_TAB_INTERNAL"
        self.editor_tab_internal_key = "EDITOR_TAB_INTERNAL"

        self.download_tab_display_key = "数据下载"
        self.integrate_tab_display_key = "整合分析"
        self.editor_tab_display_key = "配置编辑"

        self.tab_view.add(self.download_tab_internal_key)
        self.tab_view.add(self.integrate_tab_internal_key)
        self.tab_view.add(self.editor_tab_internal_key)

        self.download_page = self.tab_view.tab(self.download_tab_internal_key)
        self.integrate_page = self.tab_view.tab(self.integrate_tab_internal_key)
        self.editor_page = self.tab_view.tab(self.editor_tab_internal_key)

        self._populate_download_tab_structure()
        self._populate_integrate_tab_structure()
        self._populate_editor_tab_structure()

    def _populate_download_tab_structure(self):
        content_frame = ctk.CTkFrame(self.download_page, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)

        self.download_genome_ids_entry = ctk.CTkEntry(content_frame, font=self.app_font, height=35,
                                                      placeholder_text=_("例如: NBI_v1.1, HAU_v2.0 (留空则下载所有)"))
        self.download_genome_ids_entry.grid(row=0, column=0, columnspan=2, padx=0, pady=(0, 15), sticky="ew")

        self.download_output_dir_entry = ctk.CTkEntry(content_frame, font=self.app_font, height=35,
                                                      placeholder_text=_("下载输出目录 (可选, 覆盖配置)"))
        self.download_output_dir_entry.grid(row=1, column=0, padx=0, pady=(0, 15), sticky="ew")
        self.dl_browse_button = ctk.CTkButton(content_frame, text=_("浏览..."), width=100, height=35,
                                              command=self.browse_download_output_dir, font=self.app_font)
        self.translatable_widgets[self.dl_browse_button] = "浏览..."
        self.dl_browse_button.grid(row=1, column=1, padx=(10, 0), pady=(0, 15))

        self.download_force_checkbox_var = tk.BooleanVar()
        self.dl_force_checkbox = ctk.CTkCheckBox(content_frame, text=_("强制重新下载已存在的文件"),
                                                 variable=self.download_force_checkbox_var, font=self.app_font)
        self.translatable_widgets[self.dl_force_checkbox] = "强制重新下载已存在的文件"
        self.dl_force_checkbox.grid(row=2, column=0, columnspan=2, padx=0, pady=15, sticky="w")

        self.download_start_button = ctk.CTkButton(content_frame, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.translatable_widgets[self.download_start_button] = "开始下载"
        self.download_start_button.grid(row=3, column=0, columnspan=2, padx=0, pady=(20, 0), sticky="ew")

    def _populate_integrate_tab_structure(self):
        content_frame = ctk.CTkFrame(self.integrate_page, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)

        self.integrate_excel_entry = ctk.CTkEntry(content_frame, font=self.app_font, height=35,
                                                  placeholder_text=_("输入Excel文件路径 (可选, 覆盖配置)"))
        self.integrate_excel_entry.grid(row=0, column=0, padx=0, pady=(0, 15), sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(content_frame, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=0, column=1, padx=(10, 0), pady=(0, 15))

        self.integrate_output_sheet_entry = ctk.CTkEntry(content_frame, font=self.app_font, height=35,
                                                         placeholder_text=_("输出工作表名称 (可选, 覆盖配置)"))
        self.integrate_output_sheet_entry.grid(row=1, column=0, columnspan=2, padx=0, pady=(0, 15), sticky="ew")

        self.integrate_start_button = ctk.CTkButton(content_frame, text=_("开始整合分析"), height=40,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始整合分析"
        self.integrate_start_button.grid(row=2, column=0, columnspan=2, padx=0, pady=(20, 0), sticky="ew")

    def _populate_editor_tab_structure(self):  #
        scrollable_frame = ctk.CTkScrollableFrame(self.editor_page, fg_color="transparent")  #
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)  #

        main_config_frame = ctk.CTkFrame(scrollable_frame)  #
        main_config_frame.pack(fill="x", expand=True, pady=10, padx=5)  #
        main_config_frame.grid_columnconfigure(1, weight=1)  #

        main_config_label = ctk.CTkLabel(main_config_frame, text=_("主配置文件 (config.yml)"),
                                         font=self.app_font_bold)  #
        self.translatable_widgets[main_config_label] = "主配置文件 (config.yml)"  #
        main_config_label.grid(row=0, column=0, columnspan=2, pady=(10, 15), padx=10, sticky="w")  #

        # Downloader Output Dir Base
        dl_output_dir_editor_label = ctk.CTkLabel(main_config_frame, text=_("下载器输出目录:"), font=self.app_font)  #
        self.translatable_widgets[dl_output_dir_editor_label] = "下载器输出目录:"  #
        dl_output_dir_editor_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_output_dir = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_dl_output_dir.grid(row=1, column=1, padx=10, pady=5, sticky="ew")  #

        # Force Download
        dl_force_editor_label = ctk.CTkLabel(main_config_frame, text=_("强制下载:"), font=self.app_font)  #
        self.translatable_widgets[dl_force_editor_label] = "强制下载:"  #
        dl_force_editor_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_force_switch = ctk.CTkSwitch(main_config_frame, text="", variable=self.editor_dl_force_var)  #
        self.editor_dl_force_switch.grid(row=2, column=1, padx=10, pady=5, sticky="w")  #

        # 新增：HTTP 代理设置
        dl_proxy_http_label = ctk.CTkLabel(main_config_frame, text=_("HTTP 代理:"), font=self.app_font)  #
        self.translatable_widgets[dl_proxy_http_label] = "HTTP 代理:"  #
        dl_proxy_http_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_proxy_http = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30,
                                                 placeholder_text=_("例如: http://user:pass@host:port"))  #
        self.editor_dl_proxy_http.grid(row=3, column=1, padx=10, pady=5, sticky="ew")  #

        # 新增：HTTPS 代理设置
        dl_proxy_https_label = ctk.CTkLabel(main_config_frame, text=_("HTTPS/SOCKS 代理:"), font=self.app_font)  #
        self.translatable_widgets[dl_proxy_https_label] = "HTTPS/SOCKS 代理:"  #
        dl_proxy_https_label.grid(row=4, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_dl_proxy_https = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30,
                                                  placeholder_text=_("例如: https://user:pass@host:port"))  #
        self.editor_dl_proxy_https.grid(row=4, column=1, padx=10, pady=5, sticky="ew")  #

        # Integration Input Excel Path
        pl_excel_editor_label = ctk.CTkLabel(main_config_frame, text=_("整合分析输入Excel:"), font=self.app_font)  #
        self.translatable_widgets[pl_excel_editor_label] = "整合分析输入Excel:"  #
        pl_excel_editor_label.grid(row=5, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_pl_excel_path = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_pl_excel_path.grid(row=5, column=1, padx=10, pady=5, sticky="ew")  #

        # Integration Output Sheet Name
        pl_sheet_editor_label = ctk.CTkLabel(main_config_frame, text=_("整合分析输出Sheet名:"), font=self.app_font)  #
        self.translatable_widgets[pl_sheet_editor_label] = "整合分析输出Sheet名:"  #
        pl_sheet_editor_label.grid(row=6, column=0, padx=10, pady=5, sticky="w")  #
        self.editor_pl_output_sheet = ctk.CTkEntry(main_config_frame, font=self.app_font, height=30)  #
        self.editor_pl_output_sheet.grid(row=6, column=1, padx=10, pady=5, sticky="ew")  #

        # GFF Files (YAML format)
        pl_gff_editor_label = ctk.CTkLabel(main_config_frame, text=_("GFF文件路径 (YAML格式):"), font=self.app_font)  #
        self.translatable_widgets[pl_gff_editor_label] = "GFF文件路径 (YAML格式):"  #
        pl_gff_editor_label.grid(row=7, column=0, padx=10, pady=5, sticky="nw")  #
        self.editor_pl_gff_files = ctk.CTkTextbox(main_config_frame, height=100, wrap="none", font=self.app_font)  #
        self.editor_pl_gff_files.grid(row=7, column=1, padx=10, pady=5, sticky="ew")  #

        # Save Main Config Button
        self.editor_save_button = ctk.CTkButton(main_config_frame, text=_("保存主配置"), height=35,  #
                                                command=self._save_main_config, font=self.app_font)  #
        self.translatable_widgets[self.editor_save_button] = "保存主配置"  #
        self.editor_save_button.grid(row=8, column=1, pady=(15, 10), padx=10, sticky="e")  #

        # --- 卡片2: 基因组源 (genome_sources_list.yml) ---
        gs_config_frame = ctk.CTkFrame(scrollable_frame)  #
        gs_config_frame.pack(fill="x", expand=True, pady=10, padx=5)  #
        gs_config_frame.grid_columnconfigure(0, weight=1)  #
        gs_config_frame.grid_rowconfigure(2, weight=1)  # 让 Textbox 可以扩展

        gs_label = ctk.CTkLabel(gs_config_frame, text=_("基因组源文件 (genome_sources_list.yml)"),  #
                                font=self.app_font_bold)  #
        self.translatable_widgets[gs_label] = "基因组源文件 (genome_sources_list.yml)"  #
        gs_label.grid(row=0, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="w")  #

        # 帮助标签，用于提示新参数
        gs_help_label = ctk.CTkLabel(gs_config_frame,
                                     text=_("可在此为每个版本添加 homology_id_slicer: \"_\" 用于剪切基因ID"),
                                     font=self.app_font, text_color="gray")  #
        self.translatable_widgets[gs_help_label] = "可在此为每个版本添加 homology_id_slicer: \"_\" 用于剪切基因ID"  #
        gs_help_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="w")  #

        self.editor_gs_raw_yaml = ctk.CTkTextbox(gs_config_frame, height=250, wrap="none", font=self.app_font)  #
        self.editor_gs_raw_yaml.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")  #

        gs_buttons_frame = ctk.CTkFrame(gs_config_frame, fg_color="transparent")  #
        gs_buttons_frame.grid(row=3, column=1, pady=(10, 10), padx=10, sticky="e")  #

        self.editor_gs_load_button = ctk.CTkButton(gs_buttons_frame, text=_("重新加载"), height=35,  #
                                                   command=self._load_genome_sources_to_editor, font=self.app_font)  #
        self.translatable_widgets[self.editor_gs_load_button] = "重新加载"  #
        self.editor_gs_load_button.pack(side="left", padx=(0, 10))  #

        self.editor_gs_save_button = ctk.CTkButton(gs_buttons_frame, text=_("保存基因组源"), height=35,  #
                                                   command=self._save_genome_sources_config, font=self.app_font)  #
        self.translatable_widgets[self.editor_gs_save_button] = "保存基因组源"  #
        self.editor_gs_save_button.pack(side="left")  #

    def update_language_ui(self):
        global _
        try:
            new_translator = setup_cli_i18n(language_code=self.selected_language.get(), app_name=APP_NAME_FOR_I18N)
            if callable(new_translator):
                _ = new_translator
            else:
                _ = lambda s: str(s) + f" (fallback_{self.selected_language.get()})"
        except Exception as e:
            _ = lambda s: str(s) + f" (exception_fallback_{self.selected_language.get()})";
            print(f"语言设置错误: {e}")

        if hasattr(self, 'title_text_key'): self.title(_(self.title_text_key))
        if hasattr(self, 'menubar'): self._create_menu_bar()

        for widget, text_info in self.translatable_widgets.items():
            if widget and hasattr(widget, 'configure') and widget.winfo_exists():
                try:
                    if isinstance(text_info, tuple) and text_info[0] == "label_with_dynamic_part":
                        base_key, dynamic_part_func = text_info[1], text_info[2]
                        widget.configure(text=f"{_(base_key)}: {dynamic_part_func()}")
                    elif isinstance(text_info, str):
                        if isinstance(widget, ctk.CTkEntry):
                            widget.configure(placeholder_text=_(text_info))
                        else:
                            widget.configure(text=_(text_info))
                except Exception as e_widget_update:
                    print(f"控件文本更新失败 {widget}: {e_widget_update}")

        if hasattr(self, 'tab_view') and hasattr(self.tab_view, '_segmented_button'):
            try:
                old_names = list(self.tab_view._tab_dict.keys())
                new_names_map = {
                    self.download_tab_internal_key: _(self.download_tab_display_key),
                    self.integrate_tab_internal_key: _(self.integrate_tab_display_key),
                    self.editor_tab_internal_key: _(self.editor_tab_display_key),
                }
                new_names_ordered = [new_names_map[key] for key in old_names]

                new_tab_dict = {}
                for i in range(len(old_names)):
                    new_tab_dict[new_names_ordered[i]] = self.tab_view._tab_dict[old_names[i]]

                self.tab_view._tab_dict = new_tab_dict
                self.tab_view._name_list = new_names_ordered
                self.tab_view._segmented_button.configure(values=new_names_ordered, font=self.app_font)

                if self.tab_view._current_name in old_names:
                    idx = old_names.index(self.tab_view._current_name)
                    new_current_name = new_names_ordered[idx]
                    self.tab_view.set(new_current_name)
            except Exception as e_tab_update:
                print(f"警告: Tab按钮文本或字体更新失败: {e_tab_update}。")

    def _create_about_dialog_button(self):  # Keeping for completeness, though not used in current layout
        pass  # The about button is now in menu, so this function is likely unused

    def show_about_dialog(self):
        """显示“关于”对话框，内容支持国际化。"""
        if hasattr(self, 'about_window') and self.about_window.winfo_exists():
            self.about_window.focus_set()
            return

        self.about_window = ctk.CTkToplevel(self)
        self.about_window.title(_("关于"))
        self.about_window.transient(self)
        self.about_window.grab_set()
        self.about_window.resizable(False, False)

        about_frame = ctk.CTkFrame(self.about_window)
        about_frame.pack(fill="both", expand=True, padx=20, pady=20)

        about_content = get_about_text(translator=_)

        about_label = ctk.CTkLabel(about_frame,
                                   text=about_content,
                                   font=self.app_font,
                                   justify="left")
        about_label.pack(pady=10, padx=10)

        close_button = ctk.CTkButton(about_frame, text=_("关闭"), command=self.about_window.destroy, font=self.app_font)
        self.translatable_widgets[close_button] = "关闭"
        close_button.pack(pady=(5, 10))

        self.about_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - self.about_window.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - self.about_window.winfo_height()) // 2
        self.about_window.geometry(f"+{x}+{y}")
        self.about_window.wait_window()

    def _update_button_states(self, is_task_running=False):
        """根据应用状态更新按钮的可用性"""
        if is_task_running:
            action_state = "disabled"
        else:
            action_state = "normal"

        task_button_state = "normal" if self.current_config and not is_task_running else "disabled"

        # Check if attributes exist before configuring
        if self.download_start_button:
            self.download_start_button.configure(state=task_button_state)
        if self.integrate_start_button:
            self.integrate_start_button.configure(state=task_button_state)

        # Global action buttons
        # config_load_button is not defined in _create_config_widgets_structure
        # if self.config_load_button: # This seems to be a remnant, no such button created
        #    self.config_load_button.configure(state=action_state)

        if self.language_optionmenu:
            self.language_optionmenu.configure(state=action_state)

        # Editor page save buttons
        if self.editor_save_button:
            self.editor_save_button.configure(
                state="normal" if self.current_config and not is_task_running else "disabled")
        if self.editor_gs_save_button:
            self.editor_gs_save_button.configure(
                state="normal" if self.current_config and not is_task_running else "disabled")
        if self.editor_gs_load_button:
            self.editor_gs_load_button.configure(
                state="normal" if self.current_config and not is_task_running else "disabled")

    def _apply_config_to_ui(self):
        """
        将加载的配置中的值应用到所有相关的UI控件上，
        包括“数据下载”、“整合分析”和“配置编辑”选项卡。
        """
        if not self.current_config:
            self._log_to_viewer(_("没有加载配置，无法应用到UI。"), level="WARNING")
            return

        # --- 1. 填充“数据下载”选项卡 ---
        downloader_cfg = self.current_config.get("downloader", {})

        # “基因组版本ID”输入框是用于用户手动覆盖的，所以我们清空它，等待用户输入。
        if self.download_genome_ids_entry:  # Use initialized attribute
            self.download_genome_ids_entry.delete(0, tk.END)

        # 填充下载输出目录
        if self.download_output_dir_entry:  # Use initialized attribute
            output_dir = downloader_cfg.get("download_output_base_dir", "")
            self.download_output_dir_entry.delete(0, tk.END)
            if output_dir:
                self.download_output_dir_entry.insert(0, output_dir)

        # 填充强制下载复选框
        # self.download_force_checkbox_var is already initialized as tk.BooleanVar()
        if self.download_force_checkbox_var:
            force_dl = downloader_cfg.get("force_download", False)
            self.download_force_checkbox_var.set(bool(force_dl))

        # --- 2. 填充“整合分析”选项卡 ---
        integration_cfg = self.current_config.get("integration_pipeline", {})

        # 填充输入Excel路径
        if self.integrate_excel_entry:  # Use initialized attribute
            excel_path = integration_cfg.get("input_excel_path", "")
            self.integrate_excel_entry.delete(0, tk.END)
            if excel_path:
                self.integrate_excel_entry.insert(0, excel_path)

        # 填充输出工作表名称
        if self.integrate_output_sheet_entry:  # Use initialized attribute
            sheet_name = integration_cfg.get("output_sheet_name", "")
            self.integrate_output_sheet_entry.delete(0, tk.END)
            if sheet_name:
                self.integrate_output_sheet_entry.insert(0, sheet_name)

        # --- 3. 填充“配置编辑”选项卡 ---
        self._apply_config_to_editor_ui()

        self._log_to_viewer(_("配置已成功应用到所有UI字段。"))

    def browse_download_output_dir(self):
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory: self.download_output_dir_entry.delete(0, tk.END); self.download_output_dir_entry.insert(0,
                                                                                                              directory)

    def start_download_task(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        self._update_button_states(is_task_running=True)

        genome_ids_str = self.download_genome_ids_entry.get() if self.download_genome_ids_entry else ""
        versions_to_download = [gid.strip() for gid in genome_ids_str.split(',') if gid.strip()]
        output_dir_override = self.download_output_dir_entry.get().strip() if self.download_output_dir_entry else ""
        output_dir_override = output_dir_override if output_dir_override else None
        force_download_override = self.download_force_checkbox_var.get() if self.download_force_checkbox_var else False

        downloader_cfg = self.current_config.get('downloader', {})
        if not versions_to_download and not downloader_cfg.get("genome_sources_file") and not downloader_cfg.get(
                "genome_sources"):
            self.show_warning_message(_("输入缺失"), _("请输入要下载的基因组版本ID，或确保配置文件中定义了基因组源。"))
            self._update_button_states(is_task_running=False)  # Restore buttons
            return

        if output_dir_override and not os.path.isdir(os.path.dirname(os.path.abspath(output_dir_override))):
            pass

        self.download_start_button.configure(state="disabled")
        task_display_name = _("下载")
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")
        self.progress_bar.pack(side="right", padx=10, pady=5);
        self.progress_bar.set(0)

        task_internal_key = self.DOWNLOAD_TASK_KEY

        thread_kwargs = {
            "config": self.current_config,
            "genome_versions_to_download_override": versions_to_download if versions_to_download else None,
            "force_download_override": force_download_override,
            "output_base_dir_override": output_dir_override,
            "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                          task_display_name),
            "task_display_name_for_cb": task_display_name
        }
        if not COTTON_TOOLKIT_LOADED:
            del thread_kwargs["config"];
            del thread_kwargs["genome_versions_to_download_override"]
            del thread_kwargs["force_download_override"];
            del thread_kwargs["output_base_dir_override"]

        thread = threading.Thread(target=download_genome_data, kwargs=thread_kwargs, daemon=True)
        thread.start()

    def browse_integrate_excel(self):
        filepath = filedialog.askopenfilename(title=_("选择输入Excel文件"),
                                              filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*")))
        if filepath: self.integrate_excel_entry.delete(0, tk.END); self.integrate_excel_entry.insert(0, filepath)

    def start_integrate_task(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        self._update_button_states(is_task_running=True)

        input_excel_override = self.integrate_excel_entry.get().strip() if self.integrate_excel_entry else ""
        input_excel_override = input_excel_override if input_excel_override else None
        output_sheet_override = self.integrate_output_sheet_entry.get().strip() if self.integrate_output_sheet_entry else ""
        output_sheet_override = output_sheet_override if output_sheet_override else None

        actual_excel_path = input_excel_override
        if not actual_excel_path:
            pipeline_cfg = self.current_config.get('integration_pipeline', {})
            actual_excel_path = pipeline_cfg.get('input_excel_path')

        if not actual_excel_path:
            self.show_error_message(_("输入缺失"), _("未指定输入Excel文件路径 (UI或配置中均未提供)。"))
            self._update_button_states(is_task_running=False)  # Restore buttons
            return
        if not os.path.isfile(actual_excel_path):
            config_dir = os.path.dirname(self.current_config.get('_config_file_abs_path_', "."))
            potential_path = os.path.join(config_dir, actual_excel_path)
            if not os.path.isfile(potential_path):
                self.show_error_message(_("文件错误"), _("输入Excel文件 '{}' 未找到或无效。").format(actual_excel_path))
                self._update_button_states(is_task_running=False)  # Restore buttons
                return
            actual_excel_path = potential_path
            self.integrate_excel_entry.delete(0, tk.END)
            self.integrate_excel_entry.insert(0, actual_excel_path)

        actual_output_sheet = output_sheet_override
        if not actual_output_sheet:
            pipeline_cfg = self.current_config.get('integration_pipeline', {})
            actual_output_sheet = pipeline_cfg.get('output_sheet_name')

        if not actual_output_sheet:
            self.show_warning_message(_("输入缺失"), _("未指定输出工作表名称，将使用默认名称或流程内部逻辑处理。"))

        self.integrate_start_button.configure(state="disabled")
        task_display_name = _("整合分析")
        self._log_to_viewer(f"{task_display_name} {_('任务开始...')}")
        self.progress_bar.pack(side="right", padx=10, pady=5);
        self.progress_bar.set(0)

        task_internal_key = self.INTEGRATE_TASK_KEY

        thread_kwargs = {
            "config": self.current_config,
            "input_excel_path_override": actual_excel_path,
            "output_sheet_name_override": output_sheet_override,
            "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(task_internal_key, success,
                                                                          task_display_name),
            "task_display_name_for_cb": task_display_name
        }
        if not COTTON_TOOLKIT_LOADED:
            del thread_kwargs["input_excel_path_override"];
            del thread_kwargs["output_sheet_name_override"]

        thread = threading.Thread(target=integrate_bsa_with_hvg, kwargs=thread_kwargs, daemon=True)
        thread.start()

    def clear_log_viewer(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self._log_to_viewer(_("日志已清除。"))

    def _log_to_viewer(self, message, level="INFO"):
        if self.log_textbox and self.log_textbox.winfo_exists():
            self.log_textbox.configure(state="normal")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            color_tag = "normal_log"
            if level == "ERROR":
                color_tag = "error_log"
            elif level == "WARNING":
                color_tag = "warning_log"
            self.log_textbox.insert(tk.END, f"[{timestamp}] {message}\n", color_tag)
            self.log_textbox.see(tk.END)
            self.log_textbox.configure(state="disabled")
            if not hasattr(self.log_textbox, '_tags_configured'):
                self.log_textbox.tag_config("error_log", foreground="red")
                self.log_textbox.tag_config("warning_log", foreground="orange")
                self.log_textbox._tags_configured = True
        else:
            print(f"[{level}] {message}")

    def show_info_message(self, title, message):
        self._log_to_viewer(f"{title}: {message}", level="INFO")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color=self.default_label_text_color)

    def show_error_message(self, title, message):
        self._log_to_viewer(f"ERROR - {title}: {message}", level="ERROR")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="red")
        messagebox.showerror(title, message)

    def show_warning_message(self, title, message):
        self._log_to_viewer(f"WARNING - {title}: {message}", level="WARNING")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="orange")
        messagebox.showwarning(title, message)

    def gui_status_callback(self, message):
        self.message_queue.put(("status", message))
        self._log_to_viewer(str(message))

    def gui_progress_callback(self, percentage, message):
        self.message_queue.put(("progress", (percentage, message)))

    def task_done_callback(self, task_internal_key, success=True, task_display_name="任务"):
        self.message_queue.put(("task_done", (task_internal_key, success, task_display_name)))

    def check_queue_periodic(self):
        try:
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()
                if message_type == "status":
                    self.status_label.configure(text=str(data)[:150], text_color=self.default_label_text_color)
                elif message_type == "progress":
                    percentage, text = data
                    if not self.progress_bar.winfo_viewable():
                        self.progress_bar.pack(side="right", padx=10, pady=5)
                    self.progress_bar.set(percentage / 100.0)
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)",
                                                text_color=self.default_label_text_color)
                elif message_type == "task_done":
                    task_internal_key, success, task_display_name = data
                    self.progress_bar.pack_forget()
                    final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))
                    self.status_label.configure(text=final_message, text_color=("green" if success else "red"))
                    self._log_to_viewer(final_message)
                    self._update_button_states(is_task_running=False)
        except Exception as e:
            pass
        self.after(100, self.check_queue_periodic)

    def on_closing(self):
        if messagebox.askokcancel(_("退出"), _("您确定要退出吗?")): self.destroy()

    # Add the missing methods here:
    def load_config_file(self):
        """
        打开文件对话框，让用户选择配置文件，然后加载它。
        """
        filepath = filedialog.askopenfilename(
            title=_("选择配置文件"),
            filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*"))
        )
        if filepath:
            self._log_to_viewer(f"{_('尝试加载配置文件:')} {filepath}")
            try:
                # 调用后端模块的加载函数
                loaded_config = load_config(filepath)
                if loaded_config:
                    self.current_config = loaded_config
                    self.config_path = filepath
                    # 更新UI显示
                    # 确保config_path_label在调用此方法时已创建
                    if self.config_path_label:  #
                        self.config_path_label.configure(
                            text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}")  #
                    self._apply_config_to_ui()  # 将配置应用到UI
                    self._update_button_states()  # 更新按钮状态
                    self._log_to_viewer(f"{_('配置文件加载成功:')} {filepath}")  #
                else:
                    self.show_error_message(_("加载失败"), _("无法加载配置文件或配置文件内容为空。"))  #
            except Exception as e:
                self.show_error_message(_("加载错误"), f"{_('加载配置文件时发生错误:')} {e}")  #
                self._log_to_viewer(f"ERROR: {_('加载配置文件时发生错误:')} {e}", level="ERROR")  #
        else:
            self._log_to_viewer(_("取消加载配置文件。"))  #

    def _generate_default_configs_gui(self):
        """
        通过GUI让用户选择目录，然后生成默认配置文件。
        """
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))  #
        if output_dir:
            self._log_to_viewer(f"{_('尝试在以下位置生成默认配置文件:')} {output_dir}")  #
            try:
                # 使用 mock 函数来生成默认文件
                success, main_cfg_path, gs_cfg_path = generate_default_config_files(output_dir, overwrite=False)  #
                if success:
                    messagebox.showinfo(_("生成成功"),  #
                                        f"{_('默认配置文件已成功生成到:')}\n{main_cfg_path}\n{gs_cfg_path}\n{_('请加载 config.yml 文件以开始使用。')}")  #
                    self._log_to_viewer(
                        f"{_('默认配置文件生成成功。')} Main: {main_cfg_path}, Genome Sources: {gs_cfg_path}")  #
                else:
                    messagebox.showerror(_("生成失败"), _("生成默认配置文件失败，请检查日志。"))  #
                    self._log_to_viewer(_("生成默认配置文件失败。"), level="ERROR")  #
            except Exception as e:
                messagebox.showerror(_("错误"), f"{_('生成默认配置文件时发生错误:')} {e}")  #
                self._log_to_viewer(f"ERROR: {_('生成默认配置文件时发生错误:')} {e}", level="ERROR")  #
        else:
            self._log_to_viewer(_("取消生成默认配置文件。"))  #

    def _apply_config_to_editor_ui(self): #
        """
        将 current_config 中的值填充到“配置编辑”选项卡的所有相关UI控件上。
        """
        if not self.current_config: #
            self._log_to_viewer(_("没有加载配置，无法填充编辑器UI。"), level="WARNING") #
            return #

        main_config = self.current_config #
        downloader_cfg = main_config.get("downloader", {}) #
        integration_cfg = main_config.get("integration_pipeline", {}) #

        # 填充下载器输出目录
        if self.editor_dl_output_dir: #
            self.editor_dl_output_dir.delete(0, tk.END) #
            self.editor_dl_output_dir.insert(0, downloader_cfg.get("download_output_base_dir", "")) #

        # 填充强制下载开关
        if self.editor_dl_force_var: #
            self.editor_dl_force_var.set(bool(downloader_cfg.get("force_download", False))) #

        # 新增：填充代理设置
        proxies_cfg = downloader_cfg.get("proxies", {}) #
        if self.editor_dl_proxy_http: #
            http_proxy = proxies_cfg.get("http", "") #
            self.editor_dl_proxy_http.delete(0, tk.END) #
            self.editor_dl_proxy_http.insert(0, http_proxy if http_proxy is not None else "") #
        if self.editor_dl_proxy_https: #
            https_proxy = proxies_cfg.get("https", "") #
            self.editor_dl_proxy_https.delete(0, tk.END) #
            self.editor_dl_proxy_https.insert(0, https_proxy if https_proxy is not None else "") #

        # 填充整合分析输入Excel路径
        if self.editor_pl_excel_path: #
            self.editor_pl_excel_path.delete(0, tk.END) #
            self.editor_pl_excel_path.insert(0, integration_cfg.get("input_excel_path", "")) #

        # 填充整合分析输出工作表名称
        if self.editor_pl_output_sheet: #
            self.editor_pl_output_sheet.delete(0, tk.END) #
            self.editor_pl_output_sheet.insert(0, integration_cfg.get("output_sheet_name", "")) #

        # 填充GFF文件路径 (YAML格式)
        if self.editor_pl_gff_files: #
            gff_files_yaml = integration_cfg.get("gff_files", {}) #
            # 将字典转换为YAML字符串
            try:
                gff_yaml_str = yaml.dump(gff_files_yaml, default_flow_style=False, allow_unicode=True, #
                                         sort_keys=False) #
            except Exception as e: #
                self._log_to_viewer(f"WARNING: 无法将GFF配置转换为YAML字符串: {e}", level="WARNING") #
                gff_yaml_str = str(gff_files_yaml)  # fallback to string representation #

            self.editor_pl_gff_files.delete("1.0", tk.END) #
            self.editor_pl_gff_files.insert("1.0", gff_yaml_str) #

        # 填充基因组源的原始YAML
        self._load_genome_sources_to_editor() #


    def _save_main_config(self): #
        """
        从“配置编辑”选项卡收集主配置信息并保存到文件。
        """
        if not self.current_config: #
            self.show_error_message(_("错误"), _("没有加载配置文件，无法保存。")) #
            return #

        # 收集下载器配置
        if "downloader" not in self.current_config: #
            self.current_config["downloader"] = {} #
        self.current_config["downloader"]["download_output_base_dir"] = self.editor_dl_output_dir.get().strip() #
        self.current_config["downloader"]["force_download"] = self.editor_dl_force_var.get() #

        # 新增：收集代理设置
        if "proxies" not in self.current_config["downloader"]: #
            self.current_config["downloader"]["proxies"] = {} #
        # 如果输入为空字符串，则保存为 None，以符合YAML中 null 的表示
        http_proxy_val = self.editor_dl_proxy_http.get().strip() #
        self.current_config["downloader"]["proxies"]["http"] = http_proxy_val if http_proxy_val != "" else None #
        https_proxy_val = self.editor_dl_proxy_https.get().strip() #
        self.current_config["downloader"]["proxies"]["https"] = https_proxy_val if https_proxy_val != "" else None #

        # 收集整合分析配置
        if "integration_pipeline" not in self.current_config: #
            self.current_config["integration_pipeline"] = {} #
        self.current_config["integration_pipeline"]["input_excel_path"] = self.editor_pl_excel_path.get().strip() #
        self.current_config["integration_pipeline"]["output_sheet_name"] = self.editor_pl_output_sheet.get().strip() #

        # 收集GFF文件路径 (YAML格式)
        gff_yaml_str = self.editor_pl_gff_files.get("1.0", tk.END).strip() #
        try:
            if gff_yaml_str: #
                gff_dict = yaml.safe_load(gff_yaml_str) #
                if isinstance(gff_dict, dict): #
                    self.current_config["integration_pipeline"]["gff_files"] = gff_dict #
                else: #
                    self.show_error_message(_("保存错误"), _("GFF文件路径的YAML格式不正确，应为字典。")) #
                    return #
            else: #
                # 如果输入框为空，则移除或清空gff_files
                if "gff_files" in self.current_config["integration_pipeline"]: #
                    del self.current_config["integration_pipeline"]["gff_files"] #
        except yaml.YAMLError as e: #
            self.show_error_message(_("保存错误"), f"{_('GFF文件路径YAML解析错误:')} {e}") #
            return #

        # 保存主配置文件
        if self.config_path: #
            try:
                save_config_to_yaml(self.current_config, self.config_path) #
                self._log_to_viewer(f"{_('主配置文件已保存到:')} {self.config_path}") #
                self.show_info_message(_("保存成功"), _("主配置文件已成功保存。")) #
            except Exception as e: #
                self.show_error_message(_("保存错误"), f"{_('保存主配置文件时发生错误:')} {e}") #
                self._log_to_viewer(f"ERROR: {_('保存主配置文件时发生错误:')} {e}", level="ERROR") #
        else: #
            self.show_warning_message(_("无法保存"), _("没有加载配置文件路径，请先加载或生成配置文件。")) #

    def _load_genome_sources_to_editor(self):
        """
        加载基因组源文件内容到编辑器的文本框。
        """
        if not self.current_config:
            self._log_to_viewer(_("没有加载主配置文件，无法加载基因组源。"), level="WARNING")  #
            return

        genome_sources_file_path = self.current_config.get("downloader", {}).get("genome_sources_file")  #
        if not genome_sources_file_path:
            self._log_to_viewer(_("主配置文件中未指定基因组源文件路径。"), level="WARNING")  #
            self.editor_gs_raw_yaml.delete("1.0", tk.END)  #
            self.editor_gs_raw_yaml.insert("1.0",
                                           _("# 基因组源文件路径未在主配置中指定或文件不存在。\n# 请编辑主配置文件 (config.yml) 中的 downloader -> genome_sources_file。"))  #
            return

        # 尝试解析相对路径
        if not os.path.isabs(genome_sources_file_path) and self.config_path:  #
            config_dir = os.path.dirname(self.config_path)  #
            abs_path = os.path.join(config_dir, genome_sources_file_path)  #
        else:
            abs_path = genome_sources_file_path  #

        if not os.path.exists(abs_path):
            self._log_to_viewer(f"WARNING: {_('基因组源文件不存在:')} {abs_path}", level="WARNING")  #
            self.editor_gs_raw_yaml.delete("1.0", tk.END)  #
            self.editor_gs_raw_yaml.insert("1.0",
                                           f"{_('# 基因组源文件不存在或路径不正确:')} {abs_path}\n{_('# 请确保文件存在且路径正确。')}")  #
            return

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:  #
                content = f.read()  #
            self.editor_gs_raw_yaml.delete("1.0", tk.END)  #
            self.editor_gs_raw_yaml.insert("1.0", content)  #
            self._log_to_viewer(f"{_('基因组源文件已加载到编辑器:')} {abs_path}")  #
        except Exception as e:
            self._log_to_viewer(f"ERROR: {_('加载基因组源文件时发生错误:')} {e}", level="ERROR")  #
            self.editor_gs_raw_yaml.delete("1.0", tk.END)  #
            self.editor_gs_raw_yaml.insert("1.0",
                                           f"{_('# 无法加载基因组源文件:')} {e}\n{_('# 请检查文件权限或格式。')}")  #

    def _save_genome_sources_config(self):
        """
        保存编辑器中基因组源文本框的内容到基因组源文件。
        """
        if not self.current_config:
            self.show_error_message(_("错误"), _("没有加载主配置文件，无法保存基因组源。"))  #
            return

        genome_sources_file_path = self.current_config.get("downloader", {}).get("genome_sources_file")  #
        if not genome_sources_file_path:
            self.show_warning_message(_("无法保存"), _("主配置文件中未指定基因组源文件路径。"))  #
            return

        # 尝试解析相对路径
        if not os.path.isabs(genome_sources_file_path) and self.config_path:  #
            config_dir = os.path.dirname(self.config_path)  #
            abs_path = os.path.join(config_dir, genome_sources_file_path)  #
        else:
            abs_path = genome_sources_file_path  #

        content_to_save = self.editor_gs_raw_yaml.get("1.0", tk.END).strip()  #

        try:
            # 尝试解析YAML内容，确保格式正确
            parsed_yaml = yaml.safe_load(content_to_save)  #
            if not isinstance(parsed_yaml, dict):
                self.show_error_message(_("保存错误"), _("基因组源内容的YAML格式不正确，应为字典。"))  #
                return

            with open(abs_path, 'w', encoding='utf-8') as f:  #
                f.write(content_to_save)  #
            self._log_to_viewer(f"{_('基因组源文件已保存到:')} {abs_path}")  #
            self.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}")  #
            self._log_to_viewer(f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")  #
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}")  #
            self._log_to_viewer(f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")  #


if __name__ == "__main__":
    app = CottonToolkitApp()
    app.mainloop()