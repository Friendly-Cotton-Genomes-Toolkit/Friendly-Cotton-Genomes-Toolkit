# 文件路径: ui/ui_manager.py

import builtins
import json
import os
import time
import tkinter as tk
from typing import TYPE_CHECKING, Optional, Callable, Any, List, Dict

import ttkbootstrap as ttkb
from PIL import Image, ImageTk

from cotton_toolkit.utils.localization import setup_localization
from .dialogs import MessageDialog, ProgressDialog

if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp


class UIManager:
    """负责所有UI控件的创建、布局和更新。"""

    # 【修改】__init__ 接收 translator 参数
    def __init__(self, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.app = app
        # 【修改】直接使用传入的 translator
        self.translator_func = translator
        self.progress_dialog: Optional['ProgressDialog'] = None
        self.style = app.style
        self.icon_cache = {}

        # 【修改】初始化逻辑简化，不再自行设置翻译器
        self._load_ui_settings()
        self._set_ttk_theme_from_app_mode(self.app.ui_settings.get("appearance_mode", "System"))

    def update_language_ui(self, lang_code: str):
        app = self.app
        # setup_localization 现在由外部主程序在切换语言时调用，
        # UIManager 只接收新的 translator 函数来更新UI
        new_translator = setup_localization(language_code=lang_code)
        self.translator_func = new_translator
        # builtins._ 也应该由主程序逻辑或 setup_localization 自身更新
        # 这里我们确保 UIManager 内部的 translator_func 是最新的

        self._update_placeholders_dictionary(new_translator)

        for component_name, component_instance in app.tool_tab_instances.items():
            if hasattr(component_instance, 'retranslate_ui'):
                component_instance.retranslate_ui(translator=new_translator)

        self._retranslate_managed_widgets(new_translator)

        app.logger.info(f"UI language updated to {lang_code}")

    def _retranslate_managed_widgets(self, new_translator: Callable[[str], str]):
        """更新由 UIManager 直接管理的、非 Tab 内的 UI 组件。"""
        app = self.app
        _ = new_translator  # 在这个方法作用域内，用 _ 指代新的翻译函数

        # --- 1. 更新主窗口标题 ---
        if hasattr(app, 'title_text_key'):
            app.title(_(app.title_text_key))

        # --- 2. 更新左侧导航栏和底部设置 ---
        if hasattr(app, 'home_button'): app.home_button.config(text=_("主页"))
        if hasattr(app, 'editor_button'): app.editor_button.config(text=_("配置编辑器"))
        if hasattr(app, 'tools_button'): app.tools_button.config(text=_("数据工具"))
        if hasattr(app, 'language_label'): app.language_label.config(text=_("语言"))
        if hasattr(app, 'appearance_mode_label'): app.appearance_mode_label.config(text=_("外观模式"))
        if hasattr(app, 'log_viewer_label_widget'): app.log_viewer_label_widget.config(text=_("操作日志"))
        if hasattr(app, 'clear_log_button'): app.clear_log_button.config(text=_("清空日志"))

        # --- 3. 更新日志切换按钮 ---
        if hasattr(app, 'toggle_log_button'):
            toggle_log_text = _("隐藏日志") if app.log_viewer_visible else _("显示日志")
            app.toggle_log_button.config(text=toggle_log_text)

        # --- 4. 更新配置路径显示 ---
        if hasattr(app, 'config_path_display_var') and app.config_path_display_var is not None:
            if app.config_path:
                app.config_path_display_var.set(_("当前配置: {}").format(os.path.basename(app.config_path)))
            else:
                app.config_path_display_var.set(_("未加载配置"))
        else:
            app.logger.warning(
                self.translator_func("config_path_display_var 在 _retranslate_managed_widgets 中未就绪。"))

        # --- 5. 更新外观模式下拉菜单 ---
        if hasattr(app, 'appearance_mode_optionmenu'):
            appearance_menu = getattr(app, 'appearance_mode_optionmenu', None)
            if appearance_menu:
                menu = appearance_menu['menu']
                menu.delete(0, 'end')
                translated_values = [_("浅色"), _("深色"), _("跟随系统")]
                display_to_key = {_("浅色"): "Light", _("深色"): "Dark", _("跟随系统"): "System"}
                for display_val in translated_values:
                    key_val = display_to_key.get(display_val, "System")
                    menu.add_command(label=display_val,
                                     command=lambda v=key_val: app.event_handler.change_appearance_mode_event(v))
                current_mode_key = app.ui_settings.get("appearance_mode", "System")
                key_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("跟随系统")}
                if app.selected_appearance_var is not None:
                    app.selected_appearance_var.set(key_to_display.get(current_mode_key))
                else:
                    app.logger.warning(
                        self.translator_func("selected_appearance_var 在 _retranslate_managed_widgets 中未就绪。"))


        # --- 7. 【新增】更新主页上通过字典追踪的组件 ---
        if hasattr(app, 'translatable_widgets'):
            for widget, text_key in app.translatable_widgets.items():
                if widget and widget.winfo_exists():
                    widget.configure(text=_(text_key))

        # --- 8. 【新增】更新工具栏 Notebook 的标签页标题 ---
        if hasattr(app, 'tools_notebook') and app.tools_notebook.tabs():
            for i, key in enumerate(app.TOOL_TAB_ORDER):
                if i < len(app.tools_notebook.tabs()):
                    tab_title = _(app.TAB_TITLE_KEYS.get(key, key))
                    app.tools_notebook.tab(i, text=tab_title)

    def _update_placeholders_dictionary(self, translator: Callable[[str], str]):
        self.app.placeholders = {
            "homology_genes": translator("粘贴基因ID，每行一个..."),
            "gff_genes": translator("粘贴基因ID，每行一个..."),
            "gff_region": translator("例如: A01:1-100000"),
            "genes_input": translator("在此处粘贴要注释的基因ID，每行一个。"),
            "enrichment_genes_input": translator(
                "在此处粘贴用于富集分析的基因ID，每行一个。\n如果包含Log2FC，格式为：基因ID\tLog2FC\n（注意：使用制表符分隔，从Excel直接复制的列即为制表符分隔）。"),
            "custom_prompt": translator(
                "在此处输入您的自定义提示词模板，必须包含 {text} 占位符..."),
            "default_prompt_empty": translator("Default prompt is empty, please set it in the configuration editor.")
        }

    def add_placeholder(self, widget, text):
        if not widget or not widget.winfo_exists(): return
        is_dark = self.style.theme.type == 'dark'
        ph_color = self.app.placeholder_color[1] if is_dark else self.app.placeholder_color[0]
        widget.configure(state="normal")
        if isinstance(widget, (tk.Entry, ttkb.Entry)):
            widget.delete(0, tk.END)
            widget.insert(0, text)
            widget.configure(foreground=ph_color)
        elif isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", text)
            widget.configure(font=self.app.app_font_italic, foreground=ph_color)
        widget.is_placeholder = True

    def refresh_single_placeholder(self, widget, key):
        if not widget or not widget.winfo_exists(): return
        current_text = ""
        if isinstance(widget, tk.Text):
            current_text = widget.get("1.0", "end-1c").strip()
        elif isinstance(widget, (tk.Entry, ttkb.Entry)):
            current_text = widget.get().strip()
        is_placeholder_state = str(widget.cget("foreground")) in [str(c) for c in self.app.placeholder_color]
        if not current_text or is_placeholder_state:
            self.add_placeholder(widget, key)

    def _set_ttk_theme_from_app_mode(self, mode: str):
        if mode == "Dark":
            theme_name = self.app.ui_settings.get("dark_mode_theme", "darkly")
        else:
            theme_name = self.app.ui_settings.get("light_mode_theme", "flatly")
        self.style.theme_use(theme_name)
        self.app._setup_fonts()
        self.app.default_text_color = self.style.lookup('TLabel', 'foreground')
        self._update_log_tag_colors()

    def setup_initial_ui(self):
        app = self.app
        self.create_main_layout()
        self.init_pages()
        # 【修改】调用 retranslate_ui 替代 update_language_ui
        # 因为 translator 已经从外部注入，我们只需用它来翻译UI
        self._retranslate_managed_widgets(self.translator_func)
        self.update_ui_from_config()

    def _bind_mouse_wheel_to_scrollable(self, widget):
        if widget and hasattr(widget, 'focus_set'): widget.bind("<Enter>", lambda event, w=widget: w.focus_set())

    def create_main_layout(self):
        app = self.app
        app.status_bar_frame = ttkb.Frame(app, height=35);
        app.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        app.log_viewer_frame = ttkb.Frame(app);
        app.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        app.log_separator = ttkb.Separator(app, orient='horizontal', bootstyle="secondary");
        app.log_separator.pack(side="bottom", fill="x", padx=10, pady=(5, 5))
        self._create_log_viewer_widgets()
        top_frame = ttkb.Frame(app);
        top_frame.pack(side="top", fill="both", expand=True)
        top_frame.grid_columnconfigure(1, weight=1);
        top_frame.grid_rowconfigure(0, weight=1)
        self._create_navigation_frame(parent=top_frame)
        app.main_content_frame = ttkb.Frame(top_frame);
        app.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        app.main_content_frame.grid_rowconfigure(0, weight=1);
        app.main_content_frame.grid_columnconfigure(0, weight=1)

    def init_pages(self):
        app = self.app
        app.home_frame = app._create_home_frame(app.main_content_frame)
        app.editor_frame = app._create_editor_frame(app.main_content_frame)
        app.tools_frame = app._create_tools_frame(app.main_content_frame)
        app._populate_tools_notebook()
        if not app.editor_ui_built: app._create_editor_widgets(app.editor_scroll_frame); app.editor_ui_built = True
        app._handle_editor_ui_update()
        self.select_frame_by_name("home")

    def _create_log_viewer_widgets(self):
        app = self.app
        _ = self.translator_func
        app.log_viewer_frame.grid_columnconfigure(0, weight=1)
        header_frame = ttkb.Frame(app.log_viewer_frame);
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5));
        header_frame.grid_columnconfigure(0, weight=1)
        app.log_viewer_label_widget = ttkb.Label(header_frame, text=_("操作日志"), font=app.app_font_bold);
        app.log_viewer_label_widget.grid(row=0, column=0, sticky="w")

        buttons_frame = ttkb.Frame(header_frame);
        buttons_frame.grid(row=0, column=1, sticky="e")
        app.toggle_log_button = ttkb.Button(buttons_frame, text=_("显示日志"), width=12,
                                            command=app.event_handler.toggle_log_viewer, bootstyle='info');
        app.toggle_log_button.pack(side="left", padx=(0, 10))

        app.clear_log_button = ttkb.Button(buttons_frame, text=_("清空日志"), width=10,
                                           command=app.event_handler.clear_log_viewer, bootstyle='danger');
        app.clear_log_button.pack(side="left")

        log_bg = self.style.lookup('TFrame', 'background');
        log_fg = self.style.lookup('TLabel', 'foreground')
        app.log_textbox = tk.Text(app.log_viewer_frame, height=15, state="disabled", wrap="word", font=app.app_font,
                                  relief="flat", background=log_bg, foreground=log_fg)
        app.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        if not app.log_viewer_visible: app.log_textbox.grid_remove()
        self._update_log_tag_colors()
        app.status_label = ttkb.Label(app.status_bar_frame, textvariable=app.latest_log_message_var, font=app.app_font,
                                      bootstyle="secondary")
        app.status_label.pack(side="left", padx=10, fill="x", expand=True)

    def display_log_message_in_ui(self, message: str, level: str):
        app = self.app
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            app.log_textbox.configure(state="normal")
            if int(app.log_textbox.index('end-1c').split('.')[0]) > 500: app.log_textbox.delete("1.0", "2.0")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            full_message = f"[{timestamp}] {message}"
            app.log_textbox.insert("end", f"{full_message}\n", f"{level.lower()}_log");
            app.log_textbox.see("end")
            app.log_textbox.configure(state="disabled")
            app.latest_log_message_var.set(full_message)
            is_dark = self.style.theme.type == 'dark'
            color_map = {"error": "#e57373" if is_dark else "#d9534f", "warning": "#ffb74d" if is_dark else "#f0ad4e",
                         "info": self.style.lookup('TLabel', 'foreground')}
            display_color = color_map.get(level.lower(), self.style.lookup('TLabel', 'foreground'))
            app.status_label.configure(foreground=display_color)

    def _create_navigation_frame(self, parent):
        app = self.app
        _ = self.translator_func
        app.navigation_frame = ttkb.Frame(parent);
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")
        app.navigation_frame.grid_rowconfigure(4, weight=1)
        nav_bg = self.style.lookup('TFrame', 'background');
        nav_fg = self.style.lookup('TLabel', 'foreground')
        self.style.configure('Transparent.TLabel', background=nav_bg, foreground=nav_fg)
        header_frame = ttkb.Frame(app.navigation_frame);
        header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        if app.logo_image_path:
            try:
                img = Image.open(app.logo_image_path).resize((60, 60), Image.LANCZOS);
                self.icon_cache["logo"] = ImageTk.PhotoImage(img)
                ttkb.Label(header_frame, image=self.icon_cache["logo"], style='Transparent.TLabel').pack(pady=(0, 10))
            except Exception as e:
                app.logger.error(f"加载Logo失败: {e}")
        ttkb.Label(header_frame, text=" FCGT", font=app.app_font_bold, style='Transparent.TLabel').pack()

        def load_icon(name):
            try:
                img = Image.open(getattr(app, f"{name}_icon_path")).resize((20, 20), Image.LANCZOS);
                self.icon_cache[name] = ImageTk.PhotoImage(img)
                return self.icon_cache[name]
            except:
                return None

        button_defs = [("home", "主页", load_icon("home")), ("editor", "配置编辑器", load_icon("settings")),
                       ("tools", "数据工具", load_icon("tools"))]
        for i, (name, text_key, icon) in enumerate(button_defs):
            btn = ttkb.Button(app.navigation_frame, text=_(text_key),
                              command=lambda n=name: self.select_frame_by_name(n), image=icon, compound="left",
                              bootstyle="primary-outline")
            btn.grid(row=i + 1, column=0, sticky="ew", padx=15, pady=5);
            setattr(app, f"{name}_button", btn)
        self.style.configure('Selected.Outline.TButton', background=self.style.colors.primary,
                             foreground=self.style.colors.light)
        settings_frame = ttkb.Frame(app.navigation_frame);
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s");
        settings_frame.grid_columnconfigure(0, weight=1)

        appearance_modes_display = [_("浅色"), _("深色"), _("跟随系统")]
        for i, (label_key, var, values, cmd) in enumerate(
                [
                    ("语言", app.selected_language_var, list(app.LANG_CODE_TO_NAME.values()),
                     app.event_handler.on_language_change),
                    ("外观模式", app.selected_appearance_var, appearance_modes_display,
                     app.event_handler.change_appearance_mode_event)
                ]):
            lbl = ttkb.Label(settings_frame, text=_(label_key), font=app.app_font, style='Transparent.TLabel');
            lbl.grid(row=i * 2, column=0, padx=5, pady=(5, 0), sticky="w")
            setattr(app, f"{'language' if i == 0 else 'appearance_mode'}_label", lbl)
            menu = ttkb.OptionMenu(settings_frame, var, var.get(), *values, command=cmd, bootstyle="primary-outline");
            menu.grid(row=i * 2 + 1, column=0, padx=5, pady=(0, 10), sticky="ew")
            setattr(app, f"{'language_optionmenu' if i == 0 else 'appearance_mode_optionmenu'}", menu)

    def _get_settings_path(self):
        # 修正路径问题，确保 .fcgt 目录在用户主目录下创建
        home_dir = os.path.expanduser("~")
        settings_dir = os.path.join(home_dir, ".fcgt")
        os.makedirs(settings_dir, exist_ok=True)
        return os.path.join(settings_dir, "ui_settings.json")


    def _load_ui_settings(self):
        app = self.app
        try:
            with open(self._get_settings_path(), 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {"appearance_mode": "System", "language": "zh-hans"}
        app.ui_settings = settings

        lang_code = app.ui_settings.get("language", "zh-hans")
        app.selected_language_var.set(app.LANG_CODE_TO_NAME.get(lang_code, "简体中文"))

        mode_key = app.ui_settings.get("appearance_mode", "System")
        key_to_display = {"Light": "浅色", "Dark": "深色", "System": "跟随系统"}
        app.selected_appearance_var.set(key_to_display.get(mode_key, "跟随系统"))


    def _save_ui_settings(self):
        try:
            with open(self._get_settings_path(), 'w', encoding='utf-8') as f:
                json.dump(self.app.ui_settings, f, indent=4)
        except IOError as e:
            self.app.logger.error(f"无法保存UI设置: {e}")

    def _update_log_tag_colors(self):
        if hasattr(self.app, 'log_textbox') and self.app.log_textbox.winfo_exists():
            is_dark = self.style.theme.type == 'dark'
            self.app.log_textbox.tag_config("error_log", foreground="#e57373" if is_dark else "#d9534f");
            self.app.log_textbox.tag_config("warning_log", foreground="#ffb74d" if is_dark else "#f0ad4e")

    def select_frame_by_name(self, name):
        app = self.app
        for btn_name in ["home", "editor", "tools"]:
            if btn := getattr(app, f"{btn_name}_button", None): btn.config(bootstyle="primary-outline")
        if btn_to_select := getattr(app, f"{name}_button", None): btn_to_select.config(bootstyle="Selected.Outline")
        for frame_name in ["home_frame", "editor_frame", "tools_frame"]:
            if frame := getattr(app, frame_name, None): frame.grid_remove()
        if frame_to_show := getattr(app, f"{name}_frame", None): frame_to_show.grid(row=0, column=0, sticky="nsew")

    def show_info_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), self.translator_func(message), icon_type="info").wait_window()

    def show_error_message(self, title: str, message: str):
        # 注意: 传入的 message 可能已经包含格式化内容，不应再次翻译
        MessageDialog(self.app, self.translator_func(title), message, icon_type="error").wait_window()

    def show_warning_message(self, title: str, message: str):
        # 注意: 传入的 message 可能已经包含格式化内容，不应再次翻译
        MessageDialog(self.app, self.translator_func(title), message, icon_type="warning").wait_window()

    def _show_progress_dialog(self, data: Dict[str, Any]):
        _ = self.translator_func
        title = data.get("title", "")
        message = data.get("message", "")
        on_cancel = data.get("on_cancel")
        if self.progress_dialog and self.progress_dialog.winfo_exists(): self.progress_dialog.close()
        self.progress_dialog = ProgressDialog(self.app, _(title), on_cancel);
        self.progress_dialog.update_progress(0, _(message))

    def _hide_progress_dialog(self):
        if self.progress_dialog and self.progress_dialog.winfo_exists(): self.progress_dialog.close()
        self.progress_dialog = None

    def _finalize_task_ui(self, task_display_name: str, success: bool, result_data: Any = None):
        _ = self.translator_func
        self._hide_progress_dialog();
        self.update_button_states(is_task_running=False);
        self.app.active_task_name = None
        if result_data == "CANCELLED":
            status_msg = _("{} 已被用户取消。").format(_(task_display_name))
        else:
            status_text = _('完成。') if success else _('失败。')
            status_msg = "{} {}".format(_(task_display_name), status_text)

        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists(): self.app.status_label.configure(
            text=status_msg)

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
            app.config_path_display_var.set(
                _("当前配置: {}").format(os.path.basename(app.config_path)) if app.config_path else _(
                    "未加载配置"))
        else:
            app.logger.warning(_("无法设置 config_path_display_var：变量未就绪或为None。这通常发生在应用程序启动的早期阶段。"))

        app._handle_editor_ui_update()
        self._update_assembly_id_dropdowns(list(app.genome_sources_data.keys()) if app.genome_sources_data else [])
        for tab_key, tab_instance in app.tool_tab_instances.items():
            if hasattr(tab_instance, 'update_from_config'):
                tab_instance.update_from_config()
            if hasattr(tab_instance, 'retranslate_ui'):
                tab_instance.retranslate_ui(translator=self.translator_func)
        if app.current_config: app.reconfigure_logging(app.current_config.log_level)
        self.update_button_states()
        app._log_to_viewer(_("UI已根据当前配置刷新。"))

    def _remove_placeholder(self, widget):
        if not widget.winfo_exists(): return
        widget.config(foreground=self.app.style.lookup('TLabel', 'foreground'))

    def _clear_placeholder(self, widget, key):
        if not widget or not widget.winfo_exists(): return
        if getattr(widget, 'is_placeholder', False):
            if isinstance(widget, (tk.Entry, ttkb.Entry)):
                widget.delete(0, tk.END)
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
            widget.configure(foreground=self.app.default_text_color)
            if isinstance(widget, tk.Text):
                widget.configure(font=self.app.app_font_mono)
            widget.is_placeholder = False

    def _handle_focus_in(self, event, widget, key):
        self._clear_placeholder(widget, key)

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
            placeholder_text = self.app.placeholders.get(key, self.app.placeholders.get("default_prompt_empty", _("Default prompt is empty, please set it in the configuration editor.")))
            self.add_placeholder(widget, placeholder_text)

    def _update_assembly_id_dropdowns(self, ids: List[str]):
        _ = self.translator_func
        ids = ids or [_("无可用基因组")]
        for tab in self.app.tool_tab_instances.values():
            if hasattr(tab, 'update_assembly_dropdowns'): tab.update_assembly_dropdowns(ids)

    def update_ai_model_dropdown(self, provider_key: str, models: List[str]):
        _ = self.translator_func
        selector = getattr(self.app, f'ai_{provider_key.replace("-", "_")}_model_selector', None)
        if not selector: return
        dropdown, var = selector
        if not models:
            dropdown.configure(state="disabled");
            var.set(_("刷新失败或无可用模型"))
            menu = dropdown["menu"];
            menu.delete(0, "end");
            menu.add_command(label=var.get(), state="disabled")
            return
        dropdown.configure(state="normal")
        current_val = var.get()
        new_val = models[0] if current_val not in models or current_val == _(
            "点击刷新获取列表") else current_val
        var.set(new_val)
        menu = dropdown["menu"];
        menu.delete(0, "end")
        for model in models: menu.add_command(label=model, command=lambda v=model: var.set(v))

    def update_option_menu(self, dropdown: ttkb.OptionMenu, string_var: tk.StringVar, new_values: List[str],
                           default_text: str = "无可用选项", command: Optional[Callable[[str], Any]] = None):
        if not (dropdown and dropdown.winfo_exists()): return
        final_values = new_values if new_values else [self.translator_func(default_text)]
        menu = dropdown['menu'];
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