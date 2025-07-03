import json
import os
import time
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import TYPE_CHECKING, Optional, Callable, Any, List
from PIL import Image, ImageTk

from cotton_toolkit.utils.localization import setup_localization
from .dialogs import MessageDialog, ProgressDialog

if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class UIManager:
    """负责所有UI控件的创建、布局和更新。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.progress_dialog: Optional['ProgressDialog'] = None
        self.style = app.style
        self.icon_cache = {}
        self._set_ttk_theme_from_app_mode(self.app.selected_appearance_var.get())

    def _set_ttk_theme_from_app_mode(self, mode: str):
        theme_name = "superhero" if mode in (_("深色"), "Dark") else "flatly"
        self.style.theme_use(theme_name)

    def setup_initial_ui(self):
        app = self.app
        self._load_ui_settings()
        self._set_ttk_theme_from_app_mode(app.selected_appearance_var.get())
        self.create_main_layout()
        self.init_pages()

    def _bind_mouse_wheel_to_scrollable(self, widget):
        if widget and hasattr(widget, 'focus_set'):
            widget.bind("<Enter>", lambda event, w=widget: w.focus_set())

    def create_main_layout(self):
        app = self.app
        app.status_bar_frame = ttkb.Frame(app, height=35)
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        app.log_viewer_frame = ttkb.Frame(app)
        app.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
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
        app._populate_tools_notebook()
        if not app.editor_ui_built:
            app._create_editor_widgets(app.editor_scroll_frame)
            app.editor_ui_built = True
        app._handle_editor_ui_update()
        self.select_frame_by_name("home")

    def _create_log_viewer_widgets(self):
        app = self.app
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)
        header_frame = ttkb.Frame(app.log_viewer_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        header_frame.grid_columnconfigure(0, weight=1)
        app.log_viewer_label_widget = ttkb.Label(header_frame, text=_("操作日志"), font=app.app_font_bold)
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        app.translatable_widgets[app.log_viewer_label_widget] = "操作日志"
        buttons_frame = ttkb.Frame(header_frame)
        buttons_frame.grid(row=0, column=1, sticky="e")
        app.toggle_log_button = ttkb.Button(buttons_frame, text=_("显示日志"), width=12,
                                            command=app.event_handler.toggle_log_viewer, bootstyle='info')
        app.toggle_log_button.pack(side="left", padx=(0, 10))
        app.translatable_widgets[app.toggle_log_button] = ("toggle_button", _("显示日志"), _("隐藏日志"))
        app.clear_log_button = ttkb.Button(buttons_frame, text=_("清除日志"), width=10,
                                           command=app.event_handler.clear_log_viewer, bootstyle='danger')
        app.clear_log_button.pack(side="left")
        app.translatable_widgets[app.clear_log_button] = "清除日志"
        log_bg = self.style.lookup('TFrame', 'background')
        log_fg = self.style.lookup('TLabel', 'foreground')
        app.log_textbox = tk.Text(app.log_viewer_frame, height=15, state="disabled", wrap="word", font=app.app_font,
                                  relief="flat", background=log_bg, foreground=log_fg)
        app.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        if not app.log_viewer_visible:
            app.log_textbox.grid_remove()
        self._update_log_tag_colors()

    def display_log_message_in_ui(self, message: str, level: str):
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            app.log_textbox.configure(state="normal")
            if int(app.log_textbox.index('end-1c').split('.')[0]) > 500:
                app.log_textbox.delete("1.0", "2.0")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            app.log_textbox.insert("end", f"[{timestamp}] {message}\n", f"{level.lower()}_log")
            app.log_textbox.see("end")
            app.log_textbox.configure(state="disabled")

    def _create_navigation_frame(self, parent):
        app = self.app
        app.navigation_frame = ttkb.Frame(parent)
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")

        app.navigation_frame.grid_rowconfigure(4, weight=1)

        nav_bg = self.style.lookup('TFrame', 'background')
        nav_fg = self.style.lookup('TLabel', 'foreground')
        self.style.configure('Transparent.TLabel', background=nav_bg, foreground=nav_fg)

        header_frame = ttkb.Frame(app.navigation_frame)
        header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        if app.logo_image_path:
            try:
                img = Image.open(app.logo_image_path).resize((60, 60), Image.LANCZOS)
                self.icon_cache["logo"] = ImageTk.PhotoImage(img)
                ttkb.Label(header_frame, image=self.icon_cache["logo"], style='Transparent.TLabel').pack(pady=(0, 10))
            except Exception as e:
                app.logger.error(f"加载Logo失败: {e}")
        ttkb.Label(header_frame, text=" FCGT", font=app.app_font_bold, style='Transparent.TLabel').pack()

        def load_icon(name):
            try:
                img = Image.open(getattr(app, f"{name}_icon_path")).resize((20, 20), Image.LANCZOS)
                self.icon_cache[name] = ImageTk.PhotoImage(img)
                return self.icon_cache[name]
            except:
                return None

        button_defs = [("home", _("主页"), load_icon("home")),
                       ("editor", _("配置编辑器"), load_icon("settings")),
                       ("tools", _("数据工具"), load_icon("tools"))]
        for i, (name, text, icon) in enumerate(button_defs):
            btn = ttkb.Button(app.navigation_frame, text=text, command=lambda n=name: self.select_frame_by_name(n),
                              image=icon, compound="left", bootstyle="outline")
            btn.grid(row=i + 1, column=0, sticky="ew", padx=15, pady=5)
            setattr(app, f"{name}_button", btn)

        self.style.configure('Selected.Outline.TButton', background=self.style.colors.primary,
                             foreground=self.style.colors.light)

        separator = ttkb.Separator(app.navigation_frame, orient='horizontal')
        separator.grid(row=3, column=0, sticky='ew', padx=15, pady=(15, 10))

        settings_frame = ttkb.Frame(app.navigation_frame)
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)
        for i, (label_key, var, values, cmd) in enumerate(
                [("语言", app.selected_language_var, list(app.LANG_CODE_TO_NAME.values()),
                  app.event_handler.on_language_change),
                 ("外观模式", app.selected_appearance_var, [_("浅色"), _("深色"), _("系统")],
                  app.event_handler.change_appearance_mode_event)]):
            lbl = ttkb.Label(settings_frame, text=_(label_key), font=app.app_font, style='Transparent.TLabel')
            lbl.grid(row=i * 2, column=0, padx=5, pady=(5, 0), sticky="w")
            setattr(app, f"{'language' if i == 0 else 'appearance_mode'}_label", lbl)

            # 【最终修改】使用 secondary-outline 样式，确保清晰可见
            menu = ttkb.OptionMenu(settings_frame, var, var.get(), *values, command=cmd,
                                   bootstyle="secondary-outline")

            menu.grid(row=i * 2 + 1, column=0, padx=5, pady=(0, 10), sticky="ew")
            setattr(app, f"{'language' if i == 0 else 'appearance_mode'}_optionmenu", menu)
            if i == 1: app.translatable_widgets[menu] = ("values", [_("浅色"), _("深色"), _("系统")])

    def _get_settings_path(self):
        return "ui_settings.json"

    def _load_ui_settings(self):
        app = self.app
        try:
            with open(self._get_settings_path(), 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {"appearance_mode": "System"}
        app.ui_settings = settings
        mode = app.ui_settings.get("appearance_mode", "System")
        app.selected_appearance_var.set({"Light": _("浅色"), "Dark": _("深色")}.get(mode, _("系统")))

    def _save_ui_settings(self):
        try:
            with open(self._get_settings_path(), 'w', encoding='utf-8') as f:
                json.dump(self.app.ui_settings, f, indent=4)
        except IOError as e:
            self.app.logger.error(f"无法保存UI设置: {e}")

    def _update_log_tag_colors(self):
        if hasattr(self.app, 'log_textbox') and self.app.log_textbox.winfo_exists():
            is_dark = self.style.theme.type == 'dark'
            self.app.log_textbox.tag_config("error_log", foreground="#e57373" if is_dark else "#d9534f")
            self.app.log_textbox.tag_config("warning_log", foreground="#ffb74d" if is_dark else "#f0ad4e")

    def select_frame_by_name(self, name):
        app = self.app
        for btn_name in ["home", "editor", "tools"]:
            if btn := getattr(app, f"{btn_name}_button", None): btn.config(bootstyle="outline")
        if btn_to_select := getattr(app, f"{name}_button", None): btn_to_select.config(bootstyle="Selected.Outline")
        for frame_name in ["home_frame", "editor_frame", "tools_frame"]:
            if frame := getattr(app, frame_name, None): frame.grid_remove()
        if frame_to_show := getattr(app, f"{name}_frame", None): frame_to_show.grid(row=0, column=0, sticky="nsew")

    def show_info_message(self, title: str, message: str):
        MessageDialog(self.app, _(title), _(message), icon_type="info").wait_window()

    def show_error_message(self, title: str, message: str):
        MessageDialog(self.app, _(title), message, icon_type="error").wait_window()

    def show_warning_message(self, title: str, message: str):
        MessageDialog(self.app, _(title), _(message), icon_type="warning").wait_window()

    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        if self.progress_dialog and self.progress_dialog.winfo_exists(): self.progress_dialog.close()
        self.progress_dialog = ProgressDialog(self.app, title, on_cancel)
        self.progress_dialog.update_progress(0, message)

    def _hide_progress_dialog(self):
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.close()
        self.progress_dialog = None

    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        self._hide_progress_dialog()
        self.update_button_states(is_task_running=False)
        self.app.active_task_name = None
        status_msg = f"{_(task_display_name)} {_('完成。') if success else ('失败。')}"
        if result_data == "CANCELLED": status_msg = f"{_(task_display_name)} {_('已被用户取消。')}"
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.status_label.configure(text=status_msg)

    def update_button_states(self, is_task_running: bool = False):
        state = "disabled" if is_task_running else "normal"
        for btn_name in ['home_button', 'editor_button', 'tools_button']:
            if btn := getattr(self.app, btn_name, None):
                if btn.winfo_exists(): btn.configure(state=state)
        for tab in self.app.tool_tab_instances.values():
            if hasattr(tab, 'update_button_state'):
                tab.update_button_state(is_task_running, bool(self.app.current_config))

    def update_ui_from_config(self):
        app = self.app
        app.config_path_display_var.set(
            _("当前配置: {}").format(os.path.basename(app.config_path)) if app.config_path else _("未加载配置"))
        app._handle_editor_ui_update()
        self._update_assembly_id_dropdowns(list(app.genome_sources_data.keys()) if app.genome_sources_data else [])
        for tab in app.tool_tab_instances.values():
            if hasattr(tab, 'update_from_config'): tab.update_from_config()
        if app.current_config: app.reconfigure_logging(app.current_config.log_level)
        self.update_button_states()
        app._log_to_viewer(_("UI已根据当前配置刷新。"))

    def update_language_ui(self, lang_code: str):
        app = self.app
        global _
        _ = setup_localization(language_code=lang_code)
        app.title(_(app.title_text_key))
        app.selected_language_var.set(app.LANG_CODE_TO_NAME.get(lang_code, "简体中文"))
        for i, key in enumerate(app.TOOL_TAB_ORDER):
            if i < len(app.tools_notebook.tabs()):
                app.tools_notebook.tab(i, text=_(app.TAB_TITLE_KEYS[key]))
        for widget, options in list(app.translatable_widgets.items()):
            if not (widget and widget.winfo_exists()): continue
            if isinstance(options, str):
                widget.configure(text=_(options))

    def add_placeholder(self, widget, key):
        if not widget.winfo_exists(): return
        placeholder_text = _(self.app.placeholders.get(key, ""))
        is_dark = self.style.theme.type == 'dark'
        ph_color = self.app.placeholder_color[1] if is_dark else self.app.placeholder_color[0]
        if isinstance(widget, (tk.Entry, ttkb.Entry)):
            widget.delete(0, tk.END);
            widget.insert(0, placeholder_text);
            widget.configure(foreground=ph_color)
        elif isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END);
            widget.insert("1.0", placeholder_text);
            widget.configure(font=self.app.app_font_italic, foreground=ph_color)

    def _remove_placeholder(self, widget):
        if not widget.winfo_exists(): return
        widget.config(foreground=self.app.style.lookup('TLabel', 'foreground'))

    def _clear_placeholder(self, widget, key):
        if not widget.winfo_exists(): return
        placeholder_text = _(self.app.placeholders.get(key, ""))
        current_text = widget.get() if isinstance(widget, (tk.Entry, ttkb.Entry)) else widget.get("1.0", tk.END).strip()
        if current_text == placeholder_text:
            if isinstance(widget, (tk.Entry, ttkb.Entry)):
                widget.delete(0, tk.END);
                widget.configure(foreground=self.app.default_text_color)
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END);
                widget.configure(font=self.app.app_font, foreground=self.app.default_text_color)

    def _handle_focus_in(self, event, widget, key):
        self._clear_placeholder(widget, key)

    def _handle_focus_out(self, event, widget, key):
        current_text = widget.get() if isinstance(widget, (tk.Entry, ttkb.Entry)) else widget.get("1.0", tk.END).strip()
        if not current_text: self.add_placeholder(widget, key)

    def _update_assembly_id_dropdowns(self, ids: List[str]):
        ids = ids or [_("无可用基因组")]
        for tab in self.app.tool_tab_instances.values():
            if hasattr(tab, 'update_assembly_dropdowns'): tab.update_assembly_dropdowns(ids)

    def update_ai_model_dropdown(self, provider_key: str, models: List[str]):
        selector = getattr(self.app, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
        if not selector: return
        dropdown, var = selector

        if not models:
            dropdown.configure(state="disabled")
            var.set(_("刷新失败或无模型"))
            menu = dropdown["menu"]
            menu.delete(0, "end")
            menu.add_command(label=var.get(), state="disabled")
            return

        dropdown.configure(state="normal")
        current_val = var.get()
        if current_val not in models or current_val == _("点击刷新获取列表"):
            new_val = models[0]
        else:
            new_val = current_val
        var.set(new_val)

        menu = dropdown["menu"]
        menu.delete(0, "end")
        for model in models:
            menu.add_command(label=model, command=lambda v=model: var.set(v))

    def update_option_menu(self, dropdown: ttkb.OptionMenu, string_var: tk.StringVar, new_values: List[str],
                           default_text: str = _("无可用选项")):
        if not (dropdown and dropdown.winfo_exists()): return
        final_values = new_values if new_values else [default_text]
        menu = dropdown['menu']
        menu.delete(0, 'end')
        for value in final_values:
            menu.add_command(label=value, command=tk._setit(string_var, value))
        current_val = string_var.get()
        if current_val not in final_values:
            string_var.set(final_values[0])