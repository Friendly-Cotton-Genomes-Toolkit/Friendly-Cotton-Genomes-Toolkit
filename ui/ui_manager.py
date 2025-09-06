# 文件路径: ui/ui_manager.py

import builtins
import json
import os
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Optional, Callable, Any, List, Dict

import ttkbootstrap as ttkb
from PIL import Image, ImageTk

from cotton_toolkit import GENOME_SOURCE_FILE
from . import get_persistent_settings_path
from .dialogs import MessageDialog, ProgressDialog

if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

try:
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("ui.ui_manager")


def determine_initial_theme():
    """在主App完全初始化前，预先读取UI设置以确定初始主题。"""
    try:
        # 修正: 使用与应用程序其余部分一致的持久化设置路径
        settings_path = get_persistent_settings_path()
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            mode = settings.get('appearance_mode', 'System')
            if mode == 'Dark':
                return 'darkly'
            elif mode == 'Light':
                return 'flatly'
    except Exception as e:
        # 在启动早期阶段，日志记录器可能尚未完全配置，因此打印错误可能很有用
        print(f"Error reading initial theme: {e}")

    # 对于 'System' 模式或任何错误，默认使用亮色主题
    return 'flatly'


class UIManager:
    """负责所有UI控件的创建、布局和动态更新。"""

    def __init__(self, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.app = app
        self.translator_func = translator
        self.progress_dialog: Optional['ProgressDialog'] = None
        self.style = app.style
        self.icon_cache = {}
        # 修正: 仅定义自定义样式，颜色将在主题应用后动态设置
        self.style.configure('Sidebar.TFrame')
        self.placeholder_widgets: Dict[tk.Widget, str] = {}

    def load_settings(self):
        """仅从文件加载UI设置，并专注于外观模式。"""
        app = self.app
        _ = self.translator_func
        try:
            with open(self._get_settings_path(), 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {"appearance_mode": "System"}
        app.ui_settings = settings

        # 移除不应在此处的 language 键（如果存在）
        if 'language' in app.ui_settings:
            del app.ui_settings['language']

        # 根据加载的模式，设置外观模式下拉菜单的显示值
        mode_key = app.ui_settings.get("appearance_mode", "System")
        display_map = {"Light": _("浅色"), "Dark": _("深色"), "System": _("跟随系统")}
        app.selected_appearance_var.set(display_map.get(mode_key, mode_key))

    def apply_initial_theme(self):
        """ 根据加载的设置，应用初始主题。"""
        initial_mode = self.app.ui_settings.get("appearance_mode", "System")
        self.apply_theme_from_mode(initial_mode)

    def apply_theme_from_mode(self, mode: str):
        """
        根据外观模式计算主题名称，并调用App实例的中心方法来应用。
        """
        if mode == "Dark":
            theme_name = self.app.ui_settings.get("dark_mode_theme", "darkly")
        elif mode == "Light":
            theme_name = self.app.ui_settings.get("light_mode_theme", "flatly")
        else:
            theme_name = self.app.ui_settings.get("light_mode_theme", "flatly")

        self.app.apply_theme_and_update_dependencies(theme_name)

        self.app.after(20, self.refresh_all_placeholder_styles)

    def _retranslate_managed_widgets(self, new_translator: Callable[[str], str]):
        app = self.app
        _ = new_translator
        app.title(_(app.title_text_key))

        if hasattr(app, 'translatable_widgets'):
            for widget, text_key in app.translatable_widgets.items():
                if widget and widget.winfo_exists():
                    if isinstance(widget, (ttkb.LabelFrame, ttkb.Frame)):
                        widget.config(text=_(text_key))
                    else:
                        widget.configure(text=_(text_key))

        if hasattr(app, 'tools_notebook') and app.tools_notebook.tabs():
            for i, key in enumerate(app.TOOL_TAB_ORDER):
                if i < len(app.tools_notebook.tabs()):
                    tab_title_key = app.TAB_TITLE_KEYS.get(key, key)
                    app.tools_notebook.tab(i, text=_(tab_title_key))

        if hasattr(app, 'config_path_display_var') and app.config_path_display_var is not None:
            if app.config_path:
                app.config_path_display_var.set(_("当前配置: {}").format(os.path.basename(app.config_path)))
            else:
                app.config_path_display_var.set(_("未加载配置"))

    def refresh_single_placeholder(self, widget, key):
        if not widget or not widget.winfo_exists(): return

        is_placeholder_state = getattr(widget, 'is_placeholder', False)
        current_text = ""
        if isinstance(widget, tk.Text):
            current_text = widget.get("1.0", "end-1c").strip()
        elif isinstance(widget, (tk.Entry, ttkb.Entry)):
            current_text = widget.get().strip()

        if not current_text or is_placeholder_state:
            new_placeholder_text = self.app.placeholders.get(key, "...")
            self.add_placeholder(widget, new_placeholder_text)

    def add_placeholder(self, widget, text):
        if not widget or not widget.winfo_exists(): return

        widget.is_placeholder = True

        if isinstance(widget, (tk.Entry, ttkb.Entry)):
            widget.configure(state="normal")
            widget.delete(0, tk.END)
            widget.insert(0, text)
            widget.configure(style='Placeholder.TEntry')

        elif isinstance(widget, tk.Text):
            is_dark = self.style.theme.type == 'dark'
            ph_color = self.app.placeholder_color[1] if is_dark else self.app.placeholder_color[0]

            widget.tag_configure("placeholder", font=self.app.app_font_italic, foreground=ph_color)

            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert("1.0", text, "placeholder")

    def setup_initial_ui(self):
        self.app.navigation_frame = ttkb.Frame(self.app, style='Sidebar.TFrame')
        self.create_main_layout()
        self.init_pages()
        self._retranslate_managed_widgets(self.translator_func)
        self.update_ui_from_config()

    def _bind_mouse_wheel_to_scrollable(self, widget):
        if widget and hasattr(widget, 'focus_set'): widget.bind("<Enter>", lambda event, w=widget: w.focus_set())

    def create_main_layout(self):
        app = self.app
        app.status_bar_frame = ttkb.Frame(app, height=35)
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        app.log_viewer_frame = ttkb.Frame(app)
        app.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        app.log_separator = ttkb.Separator(app, orient='horizontal', bootstyle="secondary")
        app.log_separator.pack(side="bottom", fill="x", padx=10, pady=(5, 5))
        self._create_log_viewer_widgets()
        top_frame = ttkb.Frame(app)
        top_frame.pack(side="top", fill="both", expand=True)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_rowconfigure(0, weight=1)
        self._create_navigation_frame(parent=top_frame)
        app.main_content_frame = ttkb.Frame(top_frame)
        app.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        app.main_content_frame.grid_rowconfigure(0, weight=1)
        app.main_content_frame.grid_columnconfigure(0, weight=1)

    def init_pages(self):
        app = self.app
        app.home_frame = app._create_home_frame(app.main_content_frame)
        app.editor_frame = app._create_editor_frame(app.main_content_frame)
        app.tools_frame = app._create_tools_frame(app.main_content_frame)

        app._populate_tools_ui()

        if not app.editor_ui_built:
            app._create_editor_widgets(app.editor_scroll_frame)
            app.editor_ui_built = True
        app._handle_editor_ui_update()
        self.select_frame_by_name("home")

    def _create_log_viewer_widgets(self):
        app = self.app
        _ = self.translator_func
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)
        header_frame = ttkb.Frame(app.log_viewer_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        header_frame.grid_columnconfigure(0, weight=1)
        app.log_viewer_label_widget = ttkb.Label(header_frame, text=_("操作日志"), font=app.app_font_bold)
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")

        buttons_frame = ttkb.Frame(header_frame)
        buttons_frame.grid(row=0, column=1, sticky="e")
        app.toggle_log_button = ttkb.Button(buttons_frame, text=_("显示日志"), width=12,
                                            command=app.event_handler.toggle_log_viewer, bootstyle='info')
        app.toggle_log_button.pack(side="left", padx=(0, 10))

        app.clear_log_button = ttkb.Button(buttons_frame, text=_("清空日志"), width=10,
                                           command=app.event_handler.clear_log_viewer, bootstyle='danger')
        app.clear_log_button.pack(side="left")

        log_bg = self.style.lookup('TFrame', 'background')
        log_fg = self.style.lookup('TLabel', 'foreground')

        log_text_container = ttkb.Frame(app.log_viewer_frame)
        log_text_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_text_container.grid_rowconfigure(0, weight=1)
        log_text_container.grid_columnconfigure(0, weight=1)

        app.log_textbox = tk.Text(log_text_container, height=15, state="disabled", wrap="word", font=app.app_font,
                                  relief="flat", background=log_bg, foreground=log_fg)
        app.log_textbox.grid(row=0, column=0, sticky="nsew")

        # 创建并关联滚动条
        app.log_scrollbar = ttkb.Scrollbar(log_text_container, orient="vertical", command=app.log_textbox.yview,
                                           bootstyle="round")
        app.log_scrollbar.grid(row=0, column=1, sticky="ns")
        app.log_textbox['yscrollcommand'] = app.log_scrollbar.set

        # 将容器而不是文本框本身设为初始隐藏
        app.log_text_container = log_text_container
        if not app.log_viewer_visible:
            app.log_text_container.grid_remove()

        self._update_log_tag_colors()
        app.status_label = ttkb.Label(app.status_bar_frame, textvariable=app.latest_log_message_var, font=app.app_font,
                                      bootstyle="secondary")
        app.status_label.pack(side="left", padx=10, fill="x", expand=True)
        app.event_handler.clear_log_viewer = self.clear_log_viewer

    def clear_log_viewer(self):
        """专门用于清空日志文本框并重新准备接收新日志的UI方法"""
        if hasattr(self.app, 'log_textbox') and self.app.log_textbox.winfo_exists():
            self.app.log_textbox.configure(state="normal")
            self.app.log_textbox.delete("1.0", tk.END)
            self.app.log_textbox.configure(state="disabled")
            self.app.latest_log_message_var.set("")
            self.app.logger.info(self.translator_func(_("日志面板已清空。")))

    def display_log_message_in_ui(self, records: list[logging.LogRecord]):
        """
        接收一个日志记录列表，并安排一次UI批量更新。
        """
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            # 使用 after(0, ...) 调度UI更新，让界面响应更流畅
            app.after(0, self._update_ui_log_batch, records)

    def _update_ui_log_batch(self, records: list[logging.LogRecord]):
        """
        高效地处理一批日志记录，并一次性更新UI。
        """
        app = self.app
        if not records:
            return

        # 1. 一次性开启编辑模式
        app.log_textbox.configure(state="normal")
        try:
            # 2. 高效地处理行数限制
            num_lines_to_add = len(records)
            current_lines = int(app.log_textbox.index('end-1c').split('.')[0])

            if current_lines + num_lines_to_add > 500:
                lines_to_delete = (current_lines + num_lines_to_add) - 500
                app.log_textbox.delete("1.0", f"{lines_to_delete + 1}.0")

            # 3. 遍历批处理记录，一次性全部插入
            for record in records:
                message = record.getMessage()
                tag_name = record.levelname.lower() + "_log"
                formatted_log = f"[{record.levelname}] [{record.asctime}] <{record.name}> {message}\n"
                app.log_textbox.insert("end", formatted_log, tag_name)

            # 4. 所有内容插入完毕后，只滚动一次UI
            app.log_textbox.see("end")

            # 5. 更新状态栏为最后一条日志的状态
            last_record = records[-1]
            app.latest_log_message_var.set(last_record.getMessage())

            is_dark = self.style.theme.type == 'dark'
            color_map = {
                "error": "#e57373" if is_dark else "#d9534f",
                "warning": "#ffb74d" if is_dark else "#f0ad4e",
                "info": self.style.lookup('TLabel', 'foreground'),
                "debug": self.app.default_text_color,
                "critical": "#ff0000" if is_dark else "#8b0000"
            }
            display_color = color_map.get(last_record.levelname.lower(), self.style.lookup('TLabel', 'foreground'))
            app.status_label.configure(foreground=display_color)

        finally:
            # 6. 确保最后将文本框设为禁用状态
            app.log_textbox.configure(state="disabled")


    def _create_navigation_frame(self, parent):
        app = self.app
        _ = self.translator_func

        app.navigation_frame = ttkb.Frame(parent, style='Sidebar.TFrame')
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")
        app.navigation_frame.grid_rowconfigure(4, weight=1)

        header_frame = ttkb.Frame(app.navigation_frame, style='Sidebar.TFrame')
        header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

        if app.logo_image_path:
            try:
                img = Image.open(app.logo_image_path).resize((60, 60), Image.LANCZOS)
                self.icon_cache["logo"] = ImageTk.PhotoImage(img)
                logo_label = ttkb.Label(header_frame, image=self.icon_cache["logo"], style='Sidebar.TLabel')
                logo_label.pack(pady=(0, 10))
            except Exception as e:
                logger.error(f"加载Logo失败: {e}")

        title_label = ttkb.Label(header_frame, text=" FCGT", font=app.app_font_bold, style='Sidebar.TLabel')
        title_label.pack()

        def load_icon(name):
            try:
                img = Image.open(getattr(app, f"{name}_icon_path")).resize((20, 20), Image.LANCZOS)
                self.icon_cache[name] = ImageTk.PhotoImage(img)
                return self.icon_cache[name]
            except:
                return None

        button_defs = [("home", _("主页"), load_icon("home")), ("editor", _("配置编辑器"), load_icon("settings")),
                       ("tools", _("数据工具"), load_icon("tools"))]
        for i, (name, text, icon) in enumerate(button_defs):
            btn = ttkb.Button(app.navigation_frame, text=text,
                              command=lambda n=name: self.select_frame_by_name(n), image=icon, compound="left",
                              bootstyle="info-outline")
            btn.grid(row=i + 1, column=0, sticky="ew", padx=15, pady=5)
            setattr(app, f"{name}_button", btn)

        settings_frame = ttkb.Frame(app.navigation_frame, style='Sidebar.TFrame')
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        appearance_modes_display = [_("浅色"), _("深色"), _("跟随系统")]
        for i, (label, var, values, cmd) in enumerate(
                [(_("语言"), app.selected_language_var, list(app.LANG_CODE_TO_NAME.values()),
                  app.event_handler.on_language_change),
                 (_("外观模式"), app.selected_appearance_var, appearance_modes_display,
                  app.event_handler.change_appearance_mode_event)]):
            lbl = ttkb.Label(settings_frame, text=label, font=app.app_font, style='Sidebar.TLabel')
            lbl.grid(row=i * 2, column=0, padx=5, pady=(5, 0), sticky="w")
            setattr(app, f"{'language' if i == 0 else 'appearance_mode'}_label", lbl)
            menu = ttkb.OptionMenu(settings_frame, var, var.get(), *values, command=cmd, bootstyle="info-outline")
            menu.grid(row=i * 2 + 1, column=0, padx=5, pady=(0, 10), sticky="ew")
            setattr(app, f"{'language_optionmenu' if i == 0 else 'appearance_mode_optionmenu'}", menu)

    def _get_settings_path(self):
        # 修正: 使用辅助函数并确保目录存在
        path = get_persistent_settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def save_ui_settings(self):
        """保存UI设置，确保不包含 language 键。"""
        try:
            if 'language' in self.app.ui_settings:
                del self.app.ui_settings['language']

            with open(self._get_settings_path(), 'w', encoding='utf-8') as f:
                json.dump(self.app.ui_settings, f, indent=4)
        except IOError as e:
            logger.error(f"无法保存UI设置: {e}")

    def _update_log_tag_colors(self):
        """
        根据当前主题（深色/浅色）更新日志文本框中不同级别消息的颜色标签。
        """
        if hasattr(self.app, 'log_textbox') and self.app.log_textbox.winfo_exists():
            is_dark = self.style.theme.type == 'dark'

            self.app.log_textbox.tag_config("error_log", foreground="#e57373" if is_dark else "#d9534f")
            self.app.log_textbox.tag_config("warning_log", foreground="#ffb74d" if is_dark else "#f0ad4e")
            self.app.log_textbox.tag_config("critical_log", foreground="#ff0000" if is_dark else "#8b0000")

            self.app.log_textbox.tag_config("info_log", foreground=self.app.default_text_color)
            self.app.log_textbox.tag_config("debug_log", foreground=self.app.default_text_color)

    def select_frame_by_name(self, name):
        app = self.app
        for btn_name in ["home", "editor", "tools"]:
            if btn := getattr(app, f"{btn_name}_button", None):
                if btn_name == name:
                    btn.config(bootstyle="primary")
                else:
                    btn.config(bootstyle="info-outline")

        for frame_name in ["home_frame", "editor_frame", "tools_frame"]:
            if frame := getattr(app, frame_name, None):
                frame.grid_remove()
        if frame_to_show := getattr(app, f"{name}_frame", None):
            frame_to_show.grid(row=0, column=0, sticky="nsew")

    def show_info_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), self.translator_func(message),
                      icon_type="info").wait_window()
        logger.info(f"{title}: {message}")

    def show_error_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), message, icon_type="error").wait_window()
        logger.error(f"{title}: {message}")

    def show_warning_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), message, icon_type="warning").wait_window()
        logger.warning(f"{title}: {message}")

    def _show_progress_dialog(self, data: Dict[str, Any]):
        _ = self.translator_func
        title = data.get("title", "")
        message = data.get("message", "")
        on_cancel = data.get("on_cancel")
        if self.progress_dialog and self.progress_dialog.winfo_exists(): self.progress_dialog.close()
        self.progress_dialog = ProgressDialog(self.app, _(title), on_cancel)
        self.progress_dialog.update_progress(0, _(message))

    def _hide_progress_dialog(self):
        if self.progress_dialog and self.progress_dialog.winfo_exists(): self.progress_dialog.close()
        self.progress_dialog = None

    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        _ = self.translator_func

        self._hide_progress_dialog()
        self.update_button_states(is_task_running=False)
        self.app.active_task_name = None

        if isinstance(result_data, Exception):
            self.show_error_message(
                _("任务失败"),
                _("任务 '{}' 执行时发生错误:\n\n{}").format(_(task_display_name), str(result_data))
            )
        elif isinstance(result_data, str) and result_data == "CANCELLED":
            self.show_info_message(
                _("任务已取消"),
                _("任务 '{}' 已被用户取消。").format(_(task_display_name))
            )
        elif success:
            self.show_info_message(
                _("任务完成"),
                _("任务 '{}' 已成功完成。").format(_(task_display_name))
            )
        else:
            self.show_error_message(
                _("任务失败"),
                _("任务 '{}' 未能成功完成。").format(_(task_display_name))
            )

        final_status_text = ""
        if isinstance(result_data, str) and result_data == "CANCELLED":
            final_status_text = _("已取消")
        elif success:
            final_status_text = _("完成")
        else:
            final_status_text = _("失败")

        status_msg = f"{_(task_display_name)}: {final_status_text}"

        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.status_label.configure(text=status_msg)

    def update_button_states(self, is_task_running: bool = False):
        state = "disabled" if is_task_running else "normal"
        for btn_name in ['home_button', 'editor_button', 'tools_button']:
            if btn := getattr(self.app, btn_name, None):
                if btn.winfo_exists(): btn.configure(state=state)
        for tab in self.app.tool_tab_instances.values():
            if hasattr(tab, 'update_button_state'): tab.update_button_state(is_task_running,
                                                                            bool(self.app.current_config))

    def update_ui_from_config(self):
        app = self.app
        _ = self.translator_func
        if hasattr(app, 'config_path_display_var') and app.config_path_display_var is not None:
            if app.config_path and app.current_config:
                # 更新主配置文件路径显示
                app.config_path_display_var.set(
                    _("主配置文件: {}").format(os.path.basename(app.config_path)))

                # 基于主配置构建并更新基因组源文件路径显示
                sources_filename = GENOME_SOURCE_FILE
                config_dir = os.path.dirname(app.config_path)
                sources_path = os.path.join(config_dir, sources_filename)
                app.sources_path_display_var.set(
                    _("基因组源文件: {}").format(os.path.basename(sources_path)))
            else:
                # 如果未加载配置，则清空路径
                app.config_path_display_var.set(_("未加载配置"))
                app.sources_path_display_var.set("")
        else:
            logger.warning(
                _("无法设置 config_path_display_var：变量未就绪或为None。这通常发生在应用程序启动的早期阶段。"))


        app._handle_editor_ui_update()
        self._update_assembly_id_dropdowns(list(app.genome_sources_data.keys()) if app.genome_sources_data else [])
        for tab_key, tab_instance in app.tool_tab_instances.items():
            if hasattr(tab_instance, 'update_from_config'):
                tab_instance.update_from_config()
        if app.current_config: app.reconfigure_logging(app.current_config.log_level)
        self.update_button_states()
        logger.info(_("UI已根据当前配置刷新。"))

    def _clear_placeholder(self, widget, key):
        if not widget or not widget.winfo_exists(): return

        if getattr(widget, 'is_placeholder', False):
            if isinstance(widget, (tk.Entry, ttkb.Entry)):
                widget.delete(0, tk.END)
                widget.configure(style='TEntry')
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)

            widget.is_placeholder = False

    def _handle_focus_in(self, event, widget, key):
        if widget not in self.placeholder_widgets:
            self.placeholder_widgets[widget] = key

        self._clear_placeholder(widget, key)

    def refresh_all_placeholder_styles(self):
        is_dark = self.style.theme.type == 'dark'
        ph_color = self.app.placeholder_color[1] if is_dark else self.app.placeholder_color[0]
        self.style.configure('Placeholder.TEntry', foreground=ph_color)

        for widget, key in self.placeholder_widgets.items():
            if widget.winfo_exists() and isinstance(widget, tk.Text) and getattr(widget, 'is_placeholder', False):
                widget.tag_configure("placeholder", font=self.app.app_font_italic, foreground=ph_color)

    def _handle_focus_out(self, event, widget, key):
        _ = self.translator_func
        current_text = ""
        if isinstance(widget, (tk.Entry, ttkb.Entry)):
            current_text = widget.get().strip()
        elif isinstance(widget, tk.Text):
            if not getattr(widget, 'is_placeholder', False):
                current_text = widget.get("1.0", "end-1c").strip()
            else:
                current_text = ""

        if not current_text:
            placeholder_text = self.app.placeholders.get(key, self.app.placeholders.get("default_prompt_empty",
                                                                                        _("Default prompt is empty, please set it in the configuration editor.")))
            self.add_placeholder(widget, placeholder_text)

    def _update_assembly_id_dropdowns(self, ids: List[str]):
        _ = self.translator_func
        ids = ids or [_("无可用基因组")]
        for tab in self.app.tool_tab_instances.values():
            if hasattr(tab, 'update_assembly_dropdowns'): tab.update_assembly_dropdowns(ids)

    def update_ai_model_dropdown(self, provider_key: str, models: List[str]):
        _ = self.translator_func

        widget_path = f'ai_services.providers.{provider_key}.model'
        selector_info = self.app.editor_widgets.get(widget_path)

        if not selector_info:
            logger.error(f"无法在 editor_widgets 中找到路径为 '{widget_path}' 的模型选择器。")
            return

        dropdown = selector_info['dropdown']
        var = selector_info['widget']  # a tk.StringVar

        if not models:
            dropdown.configure(state="disabled")
            var.set(_("刷新失败或无可用模型"))
            menu = dropdown["menu"]
            menu.delete(0, "end")
            menu.add_command(label=var.get(), state="disabled")
            return

        dropdown.configure(state="normal")
        current_val = var.get()
        # 如果当前值无效或不存在于新列表中，则默认选择第一个
        new_val = models[0] if current_val not in models or "刷新" in current_val else current_val
        var.set(new_val)

        menu = dropdown["menu"]
        menu.delete(0, "end")
        for model in models:
            menu.add_command(label=model, command=lambda v=model: var.set(v))


    def update_option_menu(self, dropdown: ttkb.OptionMenu, string_var: tk.StringVar, new_values: List[str],
                           default_text: str = "无可用选项", command: Optional[Callable[[str], Any]] = None):
        if not (dropdown and dropdown.winfo_exists()): return
        final_values = new_values if new_values else [self.translator_func(default_text)]
        menu = dropdown['menu']
        menu.delete(0, 'end')
        for value in final_values:
            if command:
                menu.add_command(label=value, command=tk._setit(string_var, value, command))
            else:
                menu.add_command(label=value, command=tk._setit(string_var, value))
        current_val = string_var.get()
        if current_val not in final_values and final_values:
            string_var.set(final_values[0])
        elif not final_values:
            string_var.set(self.translator_func(default_text))
            if command:
                command(self.translator_func(default_text))

    def update_sidebar_style(self):
        """根据当前主题更新侧边栏的自定义样式。"""
        # 确定新主题下的正确背景颜色
        is_dark = self.app.style.theme.type == 'dark'
        background_color = self.app.style.colors.dark if is_dark else self.app.style.colors.light

        # 重新配置我们为侧边栏框架定义的自定义样式
        self.style.configure('Sidebar.TFrame', background=background_color)

        # 修正: 为侧边栏中的标签也应用正确的背景色，确保一致性
        self.style.configure('Sidebar.TLabel', background=background_color)

    def show_progress_dialog(self, title: str, on_cancel: Optional[Callable] = None) -> 'ProgressDialog':
        """
        一个供外部安全调用的公共方法，用于创建和显示进度对话框。
        它接收独立的参数，然后打包成字典去调用内部的 _show_progress_dialog 方法。
        """
        _ = self.translator_func

        # 将参数打包成字典
        dialog_data = {
            "title": title,
            "message": _("正在准备任务..."),  # 提供一个默认的初始消息
            "on_cancel": on_cancel
        }

        # 调用已有的内部方法，并返回创建的对话框实例
        self._show_progress_dialog(dialog_data)
        return self.progress_dialog
