# 文件: cotton_tool/ui/ui_manager.py
import json
import os
import time
import tkinter as tk
from tkinter import ttk  # 导入tkinter的ttk模块
import ttkbootstrap as ttkb  # 导入ttkbootstrap
from ttkbootstrap.constants import *  # 导入 ttkbootstrap 常量
from typing import TYPE_CHECKING, Optional, Callable, Any, List

from PIL import Image, ImageTk  # 导入 ImageTk

from cotton_toolkit.utils.localization import setup_localization
from .dialogs import MessageDialog, ProgressDialog

# 避免循环导入，同时为IDE提供类型提示
if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class UIManager:
    """负责所有UI控件的创建、布局和更新。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        # UIManager 管理进度弹窗实例
        self.progress_dialog: Optional['ProgressDialog'] = None

        # 初始化 ttkbootstrap 样式
        self.style = app.style  # 引用 app 实例的 style

        # 根据应用外观模式设置初始主题
        self._set_ttk_theme_from_app_mode(self.app.selected_appearance_var.get())

        # 缓存图标，避免被垃圾回收
        self.icon_cache = {}

    def _set_ttk_theme_from_app_mode(self, mode: str):
        """根据CustomTkinter的外观模式设置ttkbootstrap主题。"""
        if mode == _("深色") or mode == "Dark":
            self.style.theme_use("darkly")  # 或 "superhero", "solar", "cyborg"
        elif mode == _("浅色") or mode == "Light":
            self.style.theme_use("litera")  # 或 "flatly", "cosmo", "journal"
        else:  # System
            # 尝试根据系统判断，或者设置一个默认的
            # ttkbootstrap 没有直接的“系统”模式，这里根据实际情况选择一个通用主题
            # 简单起见，如果系统是深色模式，用深色主题，否则用浅色主题
            self.style.theme_use("litera")  # 默认浅色
            # 可以在此处添加更复杂的逻辑来判断系统颜色模式，但超出了GUI库转换的直接范畴

    def setup_initial_ui(self):
        """
        统一初始UI设置
        """
        app = self.app
        # 加载UI设置并应用外观模式 (需要在创建UI前，因为它决定主题)
        self._load_ui_settings()
        # 确保在创建控件前主题已设置
        self._set_ttk_theme_from_app_mode(app.selected_appearance_var.get())

        self.create_main_layout()
        self.init_pages()

    def _bind_mouse_wheel_to_scrollable(self, widget):
        """
        将鼠标滚轮事件绑定到可滚动控件。
        """
        if widget and hasattr(widget, 'focus_set'):
            # 对于 tk.Text，通常不需要手动绑定滚轮，它自带。
            # 如果是 Frame 内的滚动，需要 Canvas + Scrollbar 组合。
            # 这里为 Text 组件添加焦点设置，确保滚轮事件可以被捕获。
            widget.bind("<Enter>", lambda event, w=widget: w.focus_set())
            # For Text widgets, actual scrolling is handled by yscrollcommand/xscrollcommand
            # It's generally not necessary to bind mousewheel directly to a Text widget unless custom scroll behavior is needed.

    def create_main_layout(self):
        """创建程序的主布局框架。"""
        app = self.app
        app.status_bar_frame = ttk.Frame(app, height=35, style='TFrame')
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)

        app.log_viewer_frame = ttk.Frame(app, style='TFrame')
        app.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self._create_log_viewer_widgets()

        top_frame = ttk.Frame(app, style='TFrame')
        top_frame.pack(side="top", fill="both", expand=True)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_rowconfigure(0, weight=1)

        self._create_navigation_frame(parent=top_frame)

        app.main_content_frame = ttk.Frame(top_frame, style='TFrame')
        app.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        app.main_content_frame.grid_rowconfigure(0, weight=1)
        app.main_content_frame.grid_columnconfigure(0, weight=1)

    def init_pages(self):
        """创建所有主内容页面 (Home, Editor, Tools) 并进行初始设置。"""
        app = self.app

        app.home_frame = app._create_home_frame(app.main_content_frame)
        app.editor_frame = app._create_editor_frame(app.main_content_frame)
        app.tools_frame = app._create_tools_frame(app.main_content_frame)

        app._populate_tools_notebook()

        if not app.editor_ui_built:
            app._create_editor_widgets(app.editor_scroll_frame)
            app.editor_ui_built = True

        app._handle_editor_ui_update()

        self.select_frame_by_name("home")

    def _create_log_viewer_widgets(self):
        """【布局优化版】创建日志查看器控件，让文本框填满宽度。"""
        app = self.app
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ttk.Frame(app.log_viewer_frame, style='TFrame')
        log_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        app.log_viewer_label_widget = ttk.Label(log_header_frame, text=_("操作日志"), font=app.app_font_bold)
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        app.translatable_widgets[app.log_viewer_label_widget] = "操作日志"

        buttons_sub_frame = ttk.Frame(log_header_frame, style='TFrame')
        buttons_sub_frame.grid(row=0, column=1, sticky="e")

        # 修复：ttkb.Button 不支持直接的 font 参数
        app.toggle_log_button = ttkb.Button(buttons_sub_frame, text=_("显示日志"), width=12,
                                            command=app.event_handler.toggle_log_viewer,
                                            style='info.TButton')
        app.toggle_log_button.pack(side="left", padx=(0, 10))
        app.translatable_widgets[app.toggle_log_button] = ("toggle_button", "显示日志", "隐藏日志")

        # 修复：ttkb.Button 不支持直接的 font 参数
        app.clear_log_button = ttkb.Button(buttons_sub_frame, text=_("清除日志"), width=10,
                                           command=app.event_handler.clear_log_viewer,
                                           style='danger.TButton')
        app.clear_log_button.pack(side="left")
        app.translatable_widgets[app.clear_log_button] = "清除日志"

        # 修复：使用 style.lookup 获取日志文本框的背景色和前景色
        log_bg = self.style.lookup('TText', 'background') or '#FFFFFF'  # Fallback to a default hex color
        log_fg = self.style.lookup('TText', 'foreground') or '#000000'  # Fallback to a default hex color

        app.log_textbox = tk.Text(app.log_viewer_frame, height=15, state="disabled", wrap="word",
                                  font=app.app_font, relief="flat", background=log_bg,
                                  foreground=log_fg)
        app.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        if not app.log_viewer_visible:
            app.log_textbox.grid_remove()

        self._update_log_tag_colors()
        app.log_textbox._tags_configured = True

    def display_log_message_in_ui(self, message: str, level: str):
        """
        实际更新日志文本框的UI，只在主线程中调用。
        并限制日志行数以提高性能。
        """
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            app.log_textbox.configure(state="normal")

            max_lines = 500
            current_lines = int(app.log_textbox.index('end-1c').split('.')[0])
            if current_lines > max_lines:
                app.log_textbox.delete("1.0", f"{current_lines - max_lines + 1}.0")

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            color_tag = f"{level.lower()}_log"
            app.log_textbox.insert("end", f"[{timestamp}] {message}\n", color_tag)
            app.log_textbox.see("end")
            app.log_textbox.configure(state="disabled")

    def _create_navigation_frame(self, parent):
        """创建左侧导航栏。"""
        app = self.app
        app.navigation_frame = ttk.Frame(parent, style='primary.TFrame')
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")
        app.navigation_frame.grid_rowconfigure(4, weight=1)

        nav_header_frame = ttk.Frame(app.navigation_frame, style='primary.TFrame')
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        # 加载并显示图片
        if app.logo_image_path:
            try:
                original_image = Image.open(app.logo_image_path)
                resized_image = original_image.resize((60, 60), Image.LANCZOS)
                self.app.logo_tk_image = ImageTk.PhotoImage(resized_image)
                ttk.Label(nav_header_frame, image=self.app.logo_tk_image).pack(pady=(0, 10))
            except Exception as e:
                app._log_to_viewer(f"Error loading logo image: {e}", "ERROR")
                ttk.Label(nav_header_frame, text="Logo Missing").pack(pady=(0, 10))
        else:
            ttk.Label(nav_header_frame, text="Logo Missing").pack(pady=(0, 10))

        ttk.Label(nav_header_frame, text=" FCGT", font=(app.app_font_bold.cget("family"), 20, "bold"),
                  foreground=self.style.colors.light).pack()

        # 图标处理：ttk.Label 或 ttk.Button 不直接支持 CustomTkinter 的 CTkImage
        # 需将图像转换为 ImageTk.PhotoImage
        def load_icon_for_ttk(path, size=(24, 24)):
            if path in self.icon_cache:
                return self.icon_cache[path]
            try:
                img = Image.open(path)
                img = img.resize(size, Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                self.icon_cache[path] = tk_img
                return tk_img
            except Exception as e:
                app._log_to_viewer(f"Error loading icon {path}: {e}", "ERROR")
                return None

        app.home_tk_icon = load_icon_for_ttk(app.home_icon_path) if app.home_icon_path else None
        app.settings_tk_icon = load_icon_for_ttk(app.settings_icon_path) if app.settings_icon_path else None
        app.tools_tk_icon = load_icon_for_ttk(app.tools_icon_path) if app.tools_icon_path else None

        # 按钮创建 - 修复：ttkb.Button 不支持直接的 font 参数
        app.home_button = ttkb.Button(app.navigation_frame, text=_("主页"),
                                      command=lambda: self.select_frame_by_name("home"),
                                      image=app.home_tk_icon, compound="left",
                                      style='Outline.TButton')
        app.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        # 为高亮添加样式
        self.style.configure('Selected.Outline.TButton', background=self.style.colors.primary,
                             foreground=self.style.colors.light)

        app.editor_button = ttkb.Button(app.navigation_frame, text=_("配置编辑器"),
                                        command=lambda: self.select_frame_by_name("editor"),
                                        image=app.settings_tk_icon, compound="left",
                                        style='Outline.TButton')
        app.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        app.tools_button = ttkb.Button(app.navigation_frame, text=_("数据工具"),
                                       command=lambda: self.select_frame_by_name("tools"),
                                       image=app.tools_tk_icon, compound="left",
                                       style='Outline.TButton')
        app.tools_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        settings_frame = ttk.Frame(app.navigation_frame, style='primary.TFrame')
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        app.language_label = ttk.Label(settings_frame, text=_("语言"), font=app.app_font)
        app.language_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        app.language_optionmenu = ttkb.OptionMenu(settings_frame, app.selected_language_var,
                                                  app.selected_language_var.get(),
                                                  *list(app.LANG_CODE_TO_NAME.values()),
                                                  command=app.event_handler.on_language_change,
                                                  style='info.TButton')
        app.language_optionmenu.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        app.appearance_mode_label = ttk.Label(settings_frame, text=_("外观模式"), font=app.app_font)
        app.appearance_mode_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")

        appearance_modes_display = [_("浅色"), _("深色"), _("系统")]
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        app.appearance_mode_optionemenu = ttkb.OptionMenu(settings_frame, app.selected_appearance_var,
                                                          app.selected_appearance_var.get(),
                                                          *appearance_modes_display,
                                                          command=app.event_handler.change_appearance_mode_event,
                                                          style='info.TButton')
        app.appearance_mode_optionemenu.grid(row=3, column=0, padx=5, pady=(0, 10), sticky="ew")
        app.translatable_widgets[app.appearance_mode_optionemenu] = ("values", ["浅色", "深色", "系统"])

    def _get_settings_path(self):
        """获取UI设置文件的路径。"""
        return "ui_settings.json"

    def _load_ui_settings(self):
        """加载UI设置，现在只处理外观模式"""
        app = self.app
        settings_path = self._get_settings_path()
        defaults = {"appearance_mode": "System"}

        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    app.ui_settings = json.load(f)
            else:
                app.ui_settings = defaults
        except (json.JSONDecodeError, IOError):
            app.ui_settings = defaults

        appearance_mode = app.ui_settings.get("appearance_mode", "System")

        self._set_ttk_theme_from_app_mode(appearance_mode)

        mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
        app.selected_appearance_var.set(mode_map_to_display.get(appearance_mode, _("系统")))

    def _save_ui_settings(self):
        """保存UI设置，现在只处理外观模式。"""
        app = self.app
        settings_path = self._get_settings_path()
        try:
            data_to_save = {"appearance_mode": app.ui_settings.get("appearance_mode", "System")}
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            app._log_to_viewer(_("外观模式设置已保存。"), "DEBUG")
        except IOError as e:
            app._log_to_viewer(f"{_('错误: 无法保存外观设置:')} {e}", "ERROR")

    def _update_log_tag_colors(self):
        """根据当前的外观模式更新日志文本框的标签颜色。"""
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            current_theme = self.style.theme.name
            is_dark_theme = "dark" in current_theme.lower()

            error_color = "#d9534f" if not is_dark_theme else "#e57373"
            warning_color = "#f0ad4e" if not is_dark_theme else "#ffb74d"

            app.log_textbox.tag_config("error_log", foreground=error_color)
            app.log_textbox.tag_config("warning_log", foreground=warning_color)

    def select_frame_by_name(self, name):
        """切换主显示页面。"""
        app = self.app

        # 重置所有按钮样式
        for btn in [app.home_button, app.editor_button, app.tools_button]:
            btn.config(style='Outline.TButton')

        # 设置当前选中按钮的样式
        if name == "home":
            app.home_button.config(style='Selected.Outline.TButton')
        elif name == "editor":
            app.editor_button.config(style='Selected.Outline.TButton')
        elif name == "tools":
            app.tools_button.config(style='Selected.Outline.TButton')

        if hasattr(app, 'home_frame'): app.home_frame.grid_forget()
        if hasattr(app, 'editor_frame'): app.editor_frame.grid_forget()
        if hasattr(app, 'tools_frame'): app.tools_frame.grid_forget()

        if name == "home":
            if hasattr(app, 'home_frame'): app.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "editor":
            if hasattr(app, 'editor_frame'): app.editor_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "tools":
            if hasattr(app, 'tools_frame'): app.tools_frame.grid(row=0, column=0, sticky="nsew")

    def show_info_message(self, title: str, message: str):
        """显示信息消息对话框。"""
        self.app._log_to_viewer(f"INFO - {title}: {message}", "INFO")
        # 修复：MessageDialog 不需要 app_font
        dialog = MessageDialog(parent=self.app, title=_(title), message=_(message), icon_type="info",
                               style=self.style)
        dialog.wait_window()

    def show_error_message(self, title: str, message: str):
        """显示错误消息对话框"""
        self.app._log_to_viewer(f"ERROR - {title}: {message}", "ERROR")
        # 修复：MessageDialog 不需要 app_font
        dialog = MessageDialog(parent=self.app, title=_(title), message=message, icon_type="error",
                               style=self.style)
        dialog.wait_window()

    def show_warning_message(self, title: str, message: str):
        self.app._log_to_viewer(f"WARNING - {title}: {message}", "WARNING")
        # 修复：MessageDialog 不需要 app_font
        dialog = MessageDialog(parent=self.app, title=_(title), message=_(message), icon_type="warning",
                               style=self.style)
        dialog.wait_window()

    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        app = self.app
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close()
        # 修复：ProgressDialog 不需要 app_font
        self.progress_dialog = ProgressDialog(parent=app, title=title, on_cancel=on_cancel,
                                              style=self.style)
        self.progress_dialog.update_progress(0, message)

    def _hide_progress_dialog(self, data=None):
        """安全地隐藏并销毁进度弹窗"""
        app = self.app
        MIN_DISPLAY_TIME = 0.4

        if self.progress_dialog and self.progress_dialog.winfo_exists():
            elapsed = time.time() - self.progress_dialog.creation_time
            if elapsed < MIN_DISPLAY_TIME:
                delay_ms = int((MIN_DISPLAY_TIME - elapsed) * 1000)
                app.after(delay_ms, self._hide_progress_dialog)
            else:
                self.progress_dialog.close()
                self.progress_dialog = None
        else:
            self.progress_dialog = None

    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        """任务结束时统一处理UI更新的辅助函数。"""
        app = self.app
        self._hide_progress_dialog()
        self.update_button_states(is_task_running=False)
        app.active_task_name = None

        if result_data == "CANCELLED":
            status_msg = f"{_(task_display_name)} {_('已被用户取消。')}"
        else:
            status_msg = f"{_(task_display_name)} {_('完成。')}" if success else f"{_(task_display_name)} {_('失败。')}"

        if hasattr(app, 'status_label') and app.status_label.winfo_exists():
            app.status_label.configure(text=status_msg)

    def update_button_states(self, is_task_running: bool = False):
        """根据程序状态更新所有按钮的可点击性。"""
        app = self.app
        has_config = bool(app.current_config)
        action_state = "disabled" if is_task_running else "normal"

        if hasattr(app, 'navigation_frame'):
            for btn_name in ['home_button', 'editor_button', 'tools_button']:
                if hasattr(app, btn_name):
                    btn = getattr(app, btn_name)
                    if btn.winfo_exists():
                        btn.configure(state=action_state)

        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_button_state'):
                tab_instance.update_button_state(is_task_running, has_config)

    def update_ui_from_config(self):
        """
        将 app.current_config 的所有设置应用到整个用户界面
        """
        app = self.app
        app._log_to_viewer(_("正在应用配置到整个UI..."), "DEBUG")

        if app.config_path:
            path_text = _("当前配置: {}").format(os.path.basename(app.config_path))
            app.config_path_display_var.set(path_text)
        else:
            app.config_path_display_var.set(_("未加载配置"))

        app._handle_editor_ui_update()

        self._update_assembly_id_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])

        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_from_config'):
                try:
                    tab_instance.update_from_config()
                except Exception as e:
                    app._log_to_viewer(f"Error updating tab {tab_instance.__class__.__name__}: {e}", "ERROR")

        if app.current_config and hasattr(app.current_config, 'log_level'):
            app.reconfigure_logging(app.current_config.log_level)

        self.update_button_states()
        app._log_to_viewer(_("UI已根据当前配置刷新。"))

    def update_language_ui(self, lang_code_to_set: Optional[str] = None):
        """动态更新整个UI的语言，处理所有控件类型。"""
        app = self.app
        global _

        if not lang_code_to_set:
            if app.current_config and hasattr(app.current_config, 'i18n_language'):
                lang_code_to_set = app.current_config.i18n_language
            else:
                lang_code_to_set = 'zh-hans'

        _ = setup_localization(language_code=lang_code_to_set)

        app.title(_(app.title_text_key))
        display_lang_name = app.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        app.selected_language_var.set(display_lang_name)

        if hasattr(app, 'tools_notebook') and hasattr(app, 'TOOL_TAB_ORDER'):
            try:
                for i, title_key in enumerate(app.TOOL_TAB_ORDER):
                    tab_widget_id = app.tools_notebook.tabs()[i]
                    app.tools_notebook.tab(tab_widget_id, text=_(app.TAB_TITLE_KEYS[title_key]))
            except Exception as e:
                app.logger.warning(f"动态更新TabView标题时出错: {e}")

        if hasattr(app, 'translatable_widgets'):
            widgets_to_process = list(self.app.translatable_widgets.items())
            widgets_to_remove = []

            for widget, key_or_options in widgets_to_process:
                if not (widget and widget.winfo_exists()):
                    continue
                try:
                    if isinstance(key_or_options, str):
                        if isinstance(widget, (ttk.Label, ttk.Button, ttk.Checkbutton)):
                            widget.configure(text=_(key_or_options))
                    elif isinstance(key_or_options, tuple):
                        widget_type = key_or_options[0]
                        if widget_type == "values" and isinstance(widget, ttkb.OptionMenu):
                            original_values = key_or_options[1]
                            translated_values = [_(v) for v in original_values]

                            widget_master = widget.master
                            # Corrected: Use 'variable' instead of 'textvariable'
                            current_selected_var_obj = widget.cget('variable')

                            # Ensure it's a StringVar object
                            if not isinstance(current_selected_var_obj, tk.StringVar):
                                app.logger.error(
                                    f"OptionMenu variable is not a StringVar object: {type(current_selected_var_obj)}. Attempting fallback for {widget}.")
                                # Fallback to known app-level variables
                                if widget is self.app.language_optionmenu:
                                    current_selected_var_obj = self.app.selected_language_var
                                elif widget is self.app.appearance_mode_optionemenu:
                                    current_selected_var_obj = self.app.selected_appearance_var
                                else:
                                    app.logger.error(
                                        f"Could not find a valid StringVar for OptionMenu: {widget}. Skipping update.")
                                    continue  # Skip this widget to avoid further errors

                            current_selected_value = current_selected_var_obj.get()
                            command = widget.cget('command')
                            style_name = widget.cget('style')
                            width = widget.cget('width')

                            new_initial_value = current_selected_value
                            if new_initial_value not in translated_values and translated_values:
                                new_initial_value = translated_values[0]
                            current_selected_var_obj.set(
                                new_initial_value)  # Update StringVar to new_initial_value before recreating

                            layout_info = {}
                            if widget.winfo_manager() == 'grid':
                                layout_info = widget.grid_info()
                            elif widget.winfo_manager() == 'pack':
                                layout_info = widget.pack_info()

                            widget.destroy()
                            widgets_to_remove.append(widget)

                            new_widget = ttkb.OptionMenu(widget_master, current_selected_var_obj,
                                                         current_selected_var_obj.get(),
                                                         *translated_values, command=command, style=style_name,
                                                         width=width)

                            if layout_info:
                                if 'row' in layout_info:  # It's a grid widget
                                    new_widget.grid(**{k: v for k, v in layout_info.items() if k != 'in'})
                                elif 'side' in layout_info:  # It's a pack widget
                                    new_widget.pack(**{k: v for k, v in layout_info.items() if k != 'in'})

                            self.app.translatable_widgets[new_widget] = ("values", original_values)

                            if widget is app.appearance_mode_optionemenu:
                                app.appearance_mode_optionemenu = new_widget
                            elif widget is app.language_optionmenu:
                                app.language_optionmenu = new_widget

                        elif widget_type == "toggle_button":
                            current_state_text = key_or_options[2] if app.log_viewer_visible else key_or_options[1]
                            widget.configure(text=_(current_state_text))
                except Exception as e:
                    app.logger.warning(f"更新控件 {widget} 文本时出错: {e} (控件类型: {type(widget).__name__})")

            for old_widget in widgets_to_remove:
                if old_widget in self.app.translatable_widgets:  # double check if it's still there
                    del self.app.translatable_widgets[old_widget]

        app._log_to_viewer(_("界面语言已更新。"), "INFO")

        # Refresh placeholder texts (if they are currently displayed)
        if hasattr(app, 'tool_tab_instances') and 'homology' in app.tool_tab_instances:
            hom_tab = app.tool_tab_instances['homology']
            if hasattr(hom_tab, 'homology_map_genes_textbox'):
                self._add_placeholder(hom_tab.homology_map_genes_textbox, "homology_genes", force=True)

        if hasattr(app, 'tool_tab_instances') and 'gff_query' in app.tool_tab_instances:
            gff_tab = app.tool_tab_instances.get('gff_query')
            if gff_tab and hasattr(gff_tab, 'gff_query_genes_textbox'):
                self._add_placeholder(gff_tab.gff_query_genes_textbox, "gff_genes", force=True)
            if gff_tab and hasattr(gff_tab, 'gff_query_region_entry'):
                current_entry_text = gff_tab.gff_query_region_entry.get().strip()
                placeholder_text_for_entry = _(self.app.placeholders.get("gff_region", ""))
                if not current_entry_text or current_entry_text == placeholder_text_for_entry:
                    gff_tab.gff_query_region_entry.delete(0, tk.END)
                    gff_tab.gff_query_region_entry.insert(0, placeholder_text_for_entry)
                    gff_tab.gff_query_region_entry.configure(
                        foreground=self.app.placeholder_color[1] if self.style.theme.name.lower().startswith(
                            'dark') else self.app.placeholder_color[0])

        if hasattr(app, 'tool_tab_instances') and 'ai_assistant' in app.tool_tab_instances:
            ai_tab = app.tool_tab_instances.get('ai_assistant')
            if ai_tab and hasattr(ai_tab, 'prompt_textbox'):
                ai_tab._on_task_type_change()

    def _add_placeholder(self, textbox_widget, placeholder_key, force=False):
        """如果文本框为空，则向其添加占位符文本和样式。(从 gui_app.py 移动)"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        placeholder_text = _(self.app.placeholders.get(placeholder_key, ""))

        if not current_text or force:
            if force and current_text == placeholder_text: return
            if force: textbox_widget.delete("1.0", tk.END)

            current_theme = self.style.theme.name
            is_dark_theme = "dark" in current_theme.lower()
            placeholder_color_value = self.app.placeholder_color[1] if is_dark_theme else self.app.placeholder_color[0]

            textbox_widget.configure(font=self.app.app_font_italic,
                                     foreground=placeholder_color_value)
            textbox_widget.insert("1.0", placeholder_text)

    def _clear_placeholder(self, textbox_widget, placeholder_key):
        """如果文本框中的内容是占位符，则清除它，并恢复正常字体和颜色。(从 gui_app.py 移动)"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        placeholder_text = _(self.app.placeholders.get(placeholder_key, ""))

        if current_text == placeholder_text:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(font=self.app.app_font,
                                     foreground=self.app.default_text_color)

    def _handle_textbox_focus_in(self, event, textbox_widget, placeholder_text_key):
        """当Textbox获得焦点时的处理函数。(从 gui_app.py 移动)"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        placeholder = _(self.app.placeholders.get(placeholder_text_key, ""))

        current_ph_color_tuple = self.app.placeholder_color
        current_theme = self.style.theme.name
        is_dark_theme = "dark" in current_theme.lower()
        current_mode_idx = 1 if is_dark_theme else 0

        is_placeholder = False
        if current_text == placeholder:
            try:
                # 修复：直接比较颜色值，而不是通过 cget("foreground") 的字符串表示
                current_fg_color = textbox_widget.cget("foreground")
                if current_fg_color == str(current_ph_color_tuple[current_mode_idx]):  # Compare string representation
                    is_placeholder = True
                # Fallback to check if it's the placeholder text
                elif current_fg_color == self.app.style.lookup('TLabel',
                                                               'foreground') or current_fg_color == self.app.default_text_color:
                    # If it's default text color, but it's placeholder text, it might be a bug
                    # So also treat as placeholder to clear it
                    is_placeholder = True
            except (tk.TclError, IndexError):
                is_placeholder = True  # Assume it's placeholder if cget fails

        if is_placeholder:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(foreground=self.app.default_text_color,
                                     font=self.app.app_font)

    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数。(从 gui_app.py 移动)"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(self.app.placeholders.get(placeholder_text_key, ""))

            current_theme = self.style.theme.name
            is_dark_theme = "dark" in current_theme.lower()
            placeholder_color_value = self.app.placeholder_color[1] if is_dark_theme else self.app.placeholder_color[0]

            textbox_widget.configure(foreground=placeholder_color_value,
                                     font=self.app.app_font_italic)
            textbox_widget.insert("0.0", placeholder)

    def _update_assembly_id_dropdowns(self, assembly_ids: List[str]):
        """
        更新所有工具选项卡中的基因组版本下拉菜单。
        """
        app = self.app
        if not assembly_ids:
            assembly_ids = [_("无可用基因组")]

        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_assembly_dropdowns'):
                try:
                    tab_instance.update_assembly_dropdowns(assembly_ids)
                except Exception as e:
                    app._log_to_viewer(f"Error updating assembly dropdowns for {tab_instance.__class__.__name__}: {e}",
                                       "ERROR")

    def update_ai_model_dropdown(self, provider_key: str, models: List[str], error: bool = False):
        """
        更新AI模型下拉菜单，处理模型获取成功或失败的情况。
        """
        app = self.app
        model_selector_tuple = getattr(app, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
        if model_selector_tuple:
            _frame, entry, dropdown, dropdown_var, _button = model_selector_tuple
            if error:
                dropdown.grid_remove()
                entry.grid()
            else:
                original_grid_info = dropdown.grid_info()
                original_pack_info = dropdown.pack_info()

                var = dropdown_var
                cmd = dropdown.cget('command')
                style_name = dropdown.cget('style')

                current_val = entry.get()
                if models and current_val in models:
                    var.set(current_val)
                elif models:
                    var.set(models[0])
                else:
                    var.set(_("无可用模型"))

                dropdown.destroy()

                if models:
                    new_dropdown = ttkb.OptionMenu(_frame, var, var.get(), *models, command=cmd, style=style_name)
                else:
                    new_dropdown = ttkb.OptionMenu(_frame, var, var.get(), *[_("无可用模型")], command=cmd,
                                                   style=style_name)

                entry.grid_remove()
                if original_grid_info:
                    new_dropdown.grid(**{k: v for k, v in original_grid_info.items() if k != 'in'})
                elif original_pack_info:
                    new_dropdown.pack(**{k: v for k, v in original_pack_info.items() if k != 'in'})

                setattr(app, f'ai_{provider_key.replace("-", "_")}_model_selector',
                        (_frame, entry, new_dropdown, var, _button))

    def _show_plot_results(self, image_paths: List[str]):
        """在一个新窗口中显示生成的图表。(从 gui_app.py 移动)"""
        if not image_paths:
            self.show_info_message(_("无结果"), _("没有生成任何图表文件。"))
            return

        window = ttkb.Toplevel(self.app)
        window.title(_("富集分析结果"))
        window.geometry("800x650")
        window.transient(self.app)
        window.grab_set()

        def _on_window_close():
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_window_close)

        if len(image_paths) == 1:
            try:
                original_image = Image.open(image_paths[0])
                img_width, img_height = original_image.size
                target_width, target_height = 780, 600
                ratio = min(target_width / img_width, target_height / img_height)
                resized_image = original_image.resize((int(img_width * ratio), int(img_height * ratio)), Image.LANCZOS)
                img = ImageTk.PhotoImage(resized_image)
                window.image_ref = img
                label = ttk.Label(window, image=img)
                label.pack(expand=True, fill="both", padx=10, pady=10)
            except Exception as e:
                ttk.Label(window, text=f"{_('加载图片失败:')} {os.path.basename(image_paths[0])}\n{e}",
                          wraplength=750).pack(padx=10, pady=10)
        else:
            canvas = tk.Canvas(window, highlightthickness=0)
            canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)

            scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

            inner_frame = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=inner_frame, anchor="nw")

            def _on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner_frame.bind("<Configure>", _on_frame_configure)

            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            canvas.bind("<MouseWheel>", _on_mousewheel)

            self.image_refs = []

            for i, path in enumerate(image_paths):
                try:
                    ttk.Label(inner_frame, text=os.path.basename(path), font=self.app.app_font_bold).pack(
                        pady=(15, 5))
                    original_image = Image.open(path)
                    img_width, img_height = original_image.size
                    target_width, target_height = 750, 580
                    ratio = min(target_width / img_width, target_height / img_height)
                    resized_image = original_image.resize((int(img_width * ratio), int(img_height * ratio)),
                                                          Image.LANCZOS)
                    img = ImageTk.PhotoImage(resized_image)
                    self.image_refs.append(img)
                    label = ttk.Label(inner_frame, image=img)
                    label.pack(pady=(0, 10))
                except Exception as e:
                    ttk.Label(inner_frame, text=f"{_('加载图片失败:')} {os.path.basename(path)}\n{e}",
                              wraplength=700).pack(pady=(15, 5))

    def update_button_states(self, is_task_running: bool = False):
        """
        根据程序状态更新所有按钮的可点击性。
        此方法原名为 _update_button_states。
        """
        app = self.app
        has_config = bool(app.current_config)
        action_state = "disabled" if is_task_running else "normal"

        if hasattr(app, 'navigation_frame'):
            for btn_name in ['home_button', 'editor_button', 'tools_button']:
                if hasattr(app, btn_name):
                    btn = getattr(app, btn_name)
                    if btn.winfo_exists():
                        btn.configure(state=action_state)

        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_button_state'):
                tab_instance.update_button_state(is_task_running, has_config)