# 文件: cotton_tool/ui/ui_manager.py
import json
import os
import time
import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, Optional, Callable, Any, List

from PIL import Image

from cotton_toolkit.utils.localization import setup_localization
from . import MessageDialog, ProgressDialog

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

    def setup_initial_ui(self):
        """
        统一初始UI设置
        """
        app = self.app
        # 这些方法现在由 UIManager 负责创建和管理
        self.create_main_layout()
        self.init_pages()

        # 加载UI设置并应用外观模式
        self._load_ui_settings()


    def _bind_mouse_wheel_to_scrollable(self, widget):
        """
        将鼠标滚轮事件绑定到可滚动控件。
        """
        if widget and hasattr(widget, 'focus_set'):
            widget.bind("<Enter>", lambda event, w=widget: w.focus_set())


    def create_main_layout(self):
        """创建程序的主布局框架。"""
        app = self.app
        app.status_bar_frame = ctk.CTkFrame(app, height=35, corner_radius=0)
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)

        app.log_viewer_frame = ctk.CTkFrame(app)
        app.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self._create_log_viewer_widgets()

        top_frame = ctk.CTkFrame(app, fg_color="transparent")
        top_frame.pack(side="top", fill="both", expand=True)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_rowconfigure(0, weight=1)

        self._create_navigation_frame(parent=top_frame)

        app.main_content_frame = ctk.CTkFrame(top_frame, corner_radius=0, fg_color="transparent")
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

    def create_log_viewer_widgets(self):
        """【布局优化版】创建日志查看器控件，让文本框填满宽度。"""
        app = self.app
        # --- 核心修改 1: 让父容器的列填满 ---
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)

        # --- 核心修改 2: 重新设计标题和按钮的布局 ---
        # 创建一个包含标题和按钮的顶部框架
        log_header_frame = ctk.CTkFrame(app.log_viewer_frame, fg_color="transparent")
        # 让这个框架在自己的行中横向填满
        log_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        # 配置此框架的网格，让标题可以占据所有可用空间
        log_header_frame.grid_columnconfigure(0, weight=1)

        # 标题标签放在左侧
        app.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=app.app_font_bold)
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        app.translatable_widgets[app.log_viewer_label_widget] = "操作日志"

        # 创建一个单独的框架来容纳右侧的按钮
        buttons_sub_frame = ctk.CTkFrame(log_header_frame, fg_color="transparent")
        buttons_sub_frame.grid(row=0, column=1, sticky="e")  # 按钮框架放在右侧

        app.toggle_log_button = ctk.CTkButton(buttons_sub_frame, text=_("显示日志"), width=90, height=28,
                                              command=app.event_handler.toggle_log_viewer, font=app.app_font)
        app.toggle_log_button.pack(side="left", padx=(0, 10))
        app.translatable_widgets[app.toggle_log_button] = ("toggle_button", "显示日志", "隐藏日志")

        app.clear_log_button = ctk.CTkButton(buttons_sub_frame, text=_("清除日志"), width=80, height=28,
                                             command=app.event_handler.clear_log_viewer, font=app.app_font)
        app.clear_log_button.pack(side="left")
        app.translatable_widgets[app.clear_log_button] = "清除日志"

        # --- 核心修改 3: 创建日志文本框，并让它横向填满 ---
        app.log_textbox = ctk.CTkTextbox(app.log_viewer_frame, height=240, state="disabled", wrap="word",
                                         font=app.app_font)
        # 让文本框在自己的行中横向填满 (sticky="ew")
        app.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        # 【修正】直接调用自己的方法，而不是通过 event_handler
        self._bind_mouse_wheel_to_scrollable(app.log_textbox)

        # 如果日志默认是隐藏的，则在创建后立即隐藏它
        if not app.log_viewer_visible:
            app.log_textbox.grid_remove()

    def display_log_message_in_ui(self, message: str, level: str):
        """
        实际更新日志文本框的UI，只在主线程中调用。
        并限制日志行数以提高性能。
        """
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            app.log_textbox.configure(state="normal")

            max_lines = 500
            # A more robust way to get line count
            current_lines = int(app.log_textbox.index('end-1c').split('.')[0])
            if current_lines > max_lines:
                app.log_textbox.delete("1.0", f"{current_lines - max_lines + 1}.0")

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            color_tag = f"{level.lower()}_log"
            app.log_textbox.insert("end", f"[{timestamp}] {message}\n", color_tag)
            app.log_textbox.see("end")
            app.log_textbox.configure(state="disabled")

            if not hasattr(app.log_textbox, '_tags_configured'):
                self._update_log_tag_colors()
                app.log_textbox._tags_configured = True


    def _create_log_viewer_widgets(self):
        """创建日志查看器控件，让文本框填满宽度。"""
        app = self.app
        # --- 核心修改 1: 让父容器的列填满 ---
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)

        # --- 核心修改 2: 重新设计标题和按钮的布局 ---
        # 创建一个包含标题和按钮的顶部框架
        log_header_frame = ctk.CTkFrame(app.log_viewer_frame, fg_color="transparent")
        # 让这个框架在自己的行中横向填满
        log_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        # 配置此框架的网格，让标题可以占据所有可用空间
        log_header_frame.grid_columnconfigure(0, weight=1)

        # 标题标签放在左侧
        app.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=app.app_font_bold)
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        app.translatable_widgets[app.log_viewer_label_widget] = "操作日志"

        # 创建一个单独的框架来容纳右侧的按钮
        buttons_sub_frame = ctk.CTkFrame(log_header_frame, fg_color="transparent")
        buttons_sub_frame.grid(row=0, column=1, sticky="e") # 按钮框架放在右侧

        app.toggle_log_button = ctk.CTkButton(buttons_sub_frame, text=_("显示日志"), width=90, height=28,
                                              command=app.event_handler.toggle_log_viewer, font=app.app_font)
        app.toggle_log_button.pack(side="left", padx=(0, 10))
        app.translatable_widgets[app.toggle_log_button] = ("toggle_button", "显示日志", "隐藏日志")

        app.clear_log_button = ctk.CTkButton(buttons_sub_frame, text=_("清除日志"), width=80, height=28,
                                             command=app.event_handler.clear_log_viewer, font=app.app_font)
        app.clear_log_button.pack(side="left")
        app.translatable_widgets[app.clear_log_button] = "清除日志"

        # --- 核心修改 3: 创建日志文本框，并让它横向填满 ---
        app.log_textbox = ctk.CTkTextbox(app.log_viewer_frame, height=240, state="disabled", wrap="word",
                                         font=app.app_font)
        # 让文本框在自己的行中横向填满 (sticky="ew")
        app.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        # 如果日志默认是隐藏的，则在创建后立即隐藏它
        if not app.log_viewer_visible:
            app.log_textbox.grid_remove()

    def _create_navigation_frame(self, parent):
        """创建左侧导航栏。"""
        app = self.app
        app.navigation_frame = ctk.CTkFrame(parent, corner_radius=0)
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")
        app.navigation_frame.grid_rowconfigure(4, weight=1)
        nav_header_frame = ctk.CTkFrame(app.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)
        ctk.CTkLabel(nav_header_frame, text="", image=app.logo_image).pack(pady=(0, 10))
        ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold")).pack()

        app.home_button = ctk.CTkButton(app.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                        text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                        anchor="w", image=app.home_icon, font=app.app_font_bold,
                                        command=lambda: self.select_frame_by_name("home"))
        app.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        app.editor_button = ctk.CTkButton(app.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("配置编辑器"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=app.settings_icon, font=app.app_font_bold,
                                          command=lambda: self.select_frame_by_name("editor"))
        app.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        app.tools_button = ctk.CTkButton(app.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=app.tools_icon, font=app.app_font_bold,
                                         command=lambda: self.select_frame_by_name("tools"))
        app.tools_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        settings_frame = ctk.CTkFrame(app.navigation_frame, corner_radius=0, fg_color="transparent")
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        app.language_label = ctk.CTkLabel(settings_frame, text=_("语言"), font=app.app_font)
        app.language_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")
        app.language_optionmenu = ctk.CTkOptionMenu(settings_frame, variable=app.selected_language_var,
                                                    values=list(app.LANG_CODE_TO_NAME.values()),
                                                    command=app.event_handler.on_language_change, font=app.app_font,
                                                    # 委托给 EventHandler
                                                    dropdown_font=app.app_font)
        app.language_optionmenu.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        app.appearance_mode_label = ctk.CTkLabel(settings_frame, text=_("外观模式"), font=app.app_font)
        app.appearance_mode_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")
        app.appearance_mode_optionemenu = ctk.CTkOptionMenu(settings_frame, variable=app.selected_appearance_var,
                                                            values=[_("浅色"), _("深色"), _("系统")], font=app.app_font,
                                                            dropdown_font=app.app_font,
                                                            command=app.event_handler.change_appearance_mode_event)  # 委托给 EventHandler
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
        ctk.set_appearance_mode(appearance_mode)

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
            current_mode = ctk.get_appearance_mode()
            error_color = "#d9534f" if current_mode == "Light" else "#e57373"
            warning_color = "#f0ad4e" if current_mode == "Light" else "#ffb74d"
            app.log_textbox.tag_config("error_log", foreground=error_color)
            app.log_textbox.tag_config("warning_log", foreground=warning_color)

    def select_frame_by_name(self, name):
        """切换主显示页面。"""
        app = self.app
        app.home_button.configure(fg_color=app.home_button.cget("hover_color") if name == "home" else "transparent")
        app.editor_button.configure(
            fg_color=app.editor_button.cget("hover_color") if name == "editor" else "transparent")
        app.tools_button.configure(fg_color=app.tools_button.cget("hover_color") if name == "tools" else "transparent")

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
        dialog = MessageDialog(parent=self.app, title=_(title), message=_(message), icon_type="info",
                               app_font=self.app.app_font)
        dialog.wait_window()

    def show_error_message(self, title: str, message: str):
        """显示错误消息对话框"""
        self.app._log_to_viewer(f"ERROR - {title}: {message}", "ERROR")
        dialog = MessageDialog(parent=self.app, title=_(title), message=message, icon_type="error",
                               app_font=self.app.app_font)
        dialog.wait_window()


    def show_warning_message(self, title: str, message: str):
        self.app._log_to_viewer(f"WARNING - {title}: {message}", "WARNING")
        dialog = MessageDialog(parent=self.app, title=_(title), message=_(message), icon_type="warning",
                               app_font=self.app.app_font)
        dialog.wait_window()


    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        app = self.app
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close()
        self.progress_dialog = ProgressDialog(parent=app, title=title, on_cancel=on_cancel,
                                              app_font=app.app_font)
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

        app._handle_editor_ui_update()  # gui_app 自己的方法

        # 现在由 ui_manager 统一管理更新下拉菜单
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
                new_tab_titles = [_(app.TAB_TITLE_KEYS[key]) for key in app.TOOL_TAB_ORDER]
                if hasattr(app.tools_notebook, '_segmented_button'):
                    app.tools_notebook._segmented_button.configure(values=new_tab_titles)
            except Exception as e:
                app.logger.warning(f"动态更新TabView标题时出错: {e}")

        if hasattr(app, 'translatable_widgets'):
            for widget, key_or_options in app.translatable_widgets.items():
                if not (widget and widget.winfo_exists()):
                    continue
                try:
                    if isinstance(key_or_options, str):
                        if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkSwitch)):
                            widget.configure(text=_(key_or_options))
                    elif isinstance(key_or_options, tuple):
                        widget_type = key_or_options[0]
                        if widget_type == "values" and isinstance(widget, ctk.CTkOptionMenu):
                            original_values = key_or_options[1]
                            translated_values = [_(v) for v in original_values]
                            widget.configure(values=translated_values)
                            if widget is app.appearance_mode_optionemenu:
                                current_mode_key = app.ui_settings.get("appearance_mode", "System")
                                mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
                                app.selected_appearance_var.set(mode_map_to_display.get(current_mode_key, _("系统")))
                        elif widget_type == "toggle_button":
                            current_state_text = key_or_options[2] if app.log_viewer_visible else key_or_options[1]
                            widget.configure(text=_(current_state_text))
                except Exception as e:
                    app.logger.warning(f"更新控件 {widget} 文本时出错: {e} (控件类型: {type(widget).__name__})")

        app._log_to_viewer(_("界面语言已更新。"), "INFO")

        # 刷新占位符文本（如果它们当前正显示的话）
        if hasattr(app, 'homology_map_genes_textbox'): # 确保 hom_tab 存在
            self._add_placeholder(app.tool_tab_instances['homology'].homology_map_genes_textbox, "homology_genes", force=True)
        if hasattr(app, 'gff_query_genes_textbox'): # 确保 gff_tab 存在
            self._add_placeholder(app.tool_tab_instances['gff_query'].gff_query_genes_textbox, "gff_genes", force=True)

    def _add_placeholder(self, textbox_widget, placeholder_key, force=False):
        """如果文本框为空，则向其添加占位符文本和样式。(从 gui_app.py 移动)"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        placeholder_text = _(self.app.placeholders.get(placeholder_key, ""))

        if not current_text or force:
            if force and current_text == placeholder_text: return
            if force: textbox_widget.delete("1.0", tk.END)

            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.app.placeholder_color[0] if current_mode == "Light" else \
            self.app.placeholder_color[1]

            textbox_widget.configure(font=self.app.app_font_italic, text_color=placeholder_color_value)
            textbox_widget.insert("1.0", placeholder_text)

    def _clear_placeholder(self, textbox_widget, placeholder_key):
        """如果文本框中的内容是占位符，则清除它，并恢复正常字体和颜色。(从 gui_app.py 移动)"""
        if not textbox_widget.winfo_exists(): return
        current_text = textbox_widget.get("1.0", tk.END).strip()

        placeholder_text = _(self.app.placeholders.get(placeholder_key, ""))

        if current_text == placeholder_text:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(font=self.app.app_font, text_color=self.app.default_text_color)


    def _handle_textbox_focus_in(self, event, textbox_widget, placeholder_text_key):
        """当Textbox获得焦点时的处理函数。(从 gui_app.py 移动)"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        placeholder = _(placeholder_text_key)

        current_ph_color_tuple = self.app.placeholder_color
        current_mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0

        is_placeholder = False
        if current_text == placeholder:
            try:
                if textbox_widget.cget("text_color") == current_ph_color_tuple[current_mode_idx]:
                    is_placeholder = True
            except (AttributeError, IndexError):
                is_placeholder = True

        if is_placeholder:
            textbox_widget.delete("1.0", tk.END)
            textbox_widget.configure(text_color=self.app.default_text_color)

    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数。(从 gui_app.py 移动)"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(placeholder_text_key)

            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.app.placeholder_color[0] if current_mode == "Light" else self.app.placeholder_color[
                1]
            textbox_widget.configure(text_color=placeholder_color_value)

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

    def _show_plot_results(self, image_paths: List[str]):
        """在一个新窗口中显示生成的图表。(从 gui_app.py 移动)"""
        if not image_paths:
            self.show_info_message(_("无结果"), _("没有生成任何图表文件。"))
            return

        window = ctk.CTkToplevel(self.app)
        window.title(_("富集分析结果"))
        window.geometry("800x650")
        window.transient(self.app)
        window.grab_set()

        def _on_window_close():
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_window_close)

        if len(image_paths) == 1:
            img = ctk.CTkImage(Image.open(image_paths[0]), size=(780, 600))
            label = ctk.CTkLabel(window, text="", image=img)
            label.pack(expand=True, fill="both", padx=10, pady=10)
        else:
            scroll_frame = ctk.CTkScrollableFrame(window)
            scroll_frame.pack(expand=True, fill="both")
            for i, path in enumerate(image_paths):
                try:
                    ctk.CTkLabel(scroll_frame, text=os.path.basename(path), font=self.app.app_font_bold).pack(
                        pady=(15, 5))
                    img = ctk.CTkImage(Image.open(path), size=(750, 580))
                    label = ctk.CTkLabel(scroll_frame, text="", image=img)
                    label.pack(pady=(0, 10))
                except Exception as e:
                    ctk.CTkLabel(scroll_frame, text=f"{_('加载图片失败:')} {os.path.basename(path)}\n{e}").pack()



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

        # 通过Tab实例来更新按钮状态
        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_button_state'):
                tab_instance.update_button_state(is_task_running, has_config)



