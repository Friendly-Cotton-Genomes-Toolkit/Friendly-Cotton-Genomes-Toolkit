# 文件: cotton_tool/ui/ui_manager.py
import os
import time
import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, Optional, Callable, Any

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

    def create_main_layout(self):
        """创建程序的主布局框架。"""
        app = self.app
        app.status_bar_frame = ctk.CTkFrame(app, height=35, corner_radius=0)
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self._create_status_bar_widgets()

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

        # 调用在主 app 中定义的页面创建方法
        app.home_frame = app._create_home_frame(app.main_content_frame)
        app.editor_frame = app._create_editor_frame(app.main_content_frame)
        app.tools_frame = app._create_tools_frame(app.main_content_frame)

        # 填充工具栏的 notebook
        app._populate_tools_notebook()

        # 确保编辑器UI已构建
        if not app.editor_ui_built:
            app._create_editor_widgets(app.editor_scroll_frame)
            app.editor_ui_built = True

        # 更新编辑器UI状态
        app._handle_editor_ui_update()

        # 默认显示主页
        self.select_frame_by_name("home")


    def _create_status_bar_widgets(self):
        """创建状态栏控件。"""
        app = self.app
        app.status_bar_frame.grid_columnconfigure(0, weight=1)
        app.status_label_base_key = "准备就绪"
        app.status_label = ctk.CTkLabel(app.status_bar_frame, text=_(app.status_label_base_key), anchor="w",
                                        font=app.app_font)
        app.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        app.progress_bar = ctk.CTkProgressBar(app.status_bar_frame, width=200)
        app.progress_bar.set(0)
        app.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        app.progress_bar.grid_remove()

    def _create_log_viewer_widgets(self):
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
        self.app.event_handler._bind_mouse_wheel_to_scrollable(app.log_textbox)

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
                                                    dropdown_font=app.app_font)
        app.language_optionmenu.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        app.appearance_mode_label = ctk.CTkLabel(settings_frame, text=_("外观模式"), font=app.app_font)
        app.appearance_mode_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")
        app.appearance_mode_optionemenu = ctk.CTkOptionMenu(settings_frame, variable=app.selected_appearance_var,
                                                            values=[_("浅色"), _("深色"), _("系统")], font=app.app_font,
                                                            dropdown_font=app.app_font,
                                                            command=app.event_handler.change_appearance_mode_event)
        app.appearance_mode_optionemenu.grid(row=3, column=0, padx=5, pady=(0, 10), sticky="ew")
        app.translatable_widgets[app.appearance_mode_optionemenu] = ("values", ["浅色", "深色", "系统"])

    def _update_log_tag_colors(self):
        """根据当前的外观模式更新日志文本框的标签颜色。"""
        # 由于此方法现在是 UIManager 的一部分，需要通过 self.app 访问主程序的控件
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            # 获取当前是 "Light" 还是 "Dark" 模式
            current_mode = ctk.get_appearance_mode()

            # 根据模式选择对应的单一颜色值
            error_color = "#d9534f" if current_mode == "Light" else "#e57373"
            warning_color = "#f0ad4e" if current_mode == "Light" else "#ffb74d"

            # 使用单一颜色值为 tag 进行配置
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
        self.app._log_to_viewer(f"INFO - {title}: {message}", "INFO")
        dialog = MessageDialog(parent=self.app, title=_(title), message=_(message), icon_type="info",
                               app_font=self.app.app_font)
        dialog.wait_window()

    def show_error_message(self, title: str, message: str):
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
        if app.progress_dialog and app.progress_dialog.winfo_exists():
            app.progress_dialog.close()
        app.progress_dialog = ProgressDialog(parent=app, title=title, on_cancel=on_cancel,
                                             app_font=app.app_font)
        app.progress_dialog.update_progress(0, message)

    def _hide_progress_dialog(self, data=None):
        """【最终健壮版】智能地、安全地隐藏并销毁进度弹窗。"""
        app = self.app
        MIN_DISPLAY_TIME = 0.4  # 弹窗最短显示时间（秒）

        # 检查弹窗是否存在
        if app.progress_dialog and app.progress_dialog.winfo_exists():

            # 计算弹窗已存在的时间
            elapsed = time.time() - app.progress_dialog.creation_time

            # 如果存在时间小于最短显示时间
            if elapsed < MIN_DISPLAY_TIME:
                # 计算还需要等待多久
                delay_ms = int((MIN_DISPLAY_TIME - elapsed) * 1000)
                # 安排自己在延迟后再次执行本方法
                app.after(delay_ms, self._hide_progress_dialog)
            else:
                # 如果时间足够长，则安全地关闭它
                app.progress_dialog.close()
                app.progress_dialog = None  # 清空引用
        else:
            # 如果弹窗已不存在，则清空引用
            app.progress_dialog = None


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
        action_state = "disabled" if is_task_running or not app.current_config else "normal"

        # 更新导航栏按钮
        if hasattr(app, 'navigation_frame'):
            app.home_button.configure(state="normal" if not is_task_running else "disabled")
            app.editor_button.configure(state="normal" if not is_task_running else "disabled")
            app.tools_button.configure(state="normal" if not is_task_running else "disabled")

        # 更新所有工具选项卡中的按钮
        for tab_instance in app.tool_tab_instances.values():
            if hasattr(tab_instance, 'update_button_state'):
                tab_instance.update_button_state(is_task_running, bool(app.current_config))


    def update_ui_from_config(self):
        """
        【最终稳定版】将 app.current_config 的所有设置应用到整个用户界面。
        此方法原名为 _apply_config_to_ui。
        """
        app = self.app
        app._log_to_viewer(_("正在应用配置到整个UI..."), "DEBUG")

        if app.config_path:
            path_text = _("当前配置: {}").format(os.path.basename(app.config_path))
            app.config_path_display_var.set(path_text)
        else:
            app.config_path_display_var.set(_("未加载配置"))

        app._handle_editor_ui_update()
        app._update_assembly_id_dropdowns()

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
        """
        【最终稳定版】动态更新整个UI的语言，处理所有控件类型。
        """
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



