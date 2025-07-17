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

try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class UIManager:
    """负责所有UI控件的创建、布局和动态更新。"""

    def __init__(self, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.app = app
        self.translator_func = translator
        self.progress_dialog: Optional['ProgressDialog'] = None
        self.style = app.style
        self.icon_cache = {}
        self.style.configure('Sidebar.TFrame', background=self.style.colors.secondary)

    # 【核心修改点 1】将加载设置和应用主题分开
    def load_settings(self):
        """仅从文件加载UI设置，不应用任何主题。"""
        app = self.app
        _ = self.translator_func
        try:
            with open(self._get_settings_path(), 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {"appearance_mode": "System", "language": "zh-hans"}
        app.ui_settings = settings

        # 设置下拉菜单的初始显示值
        lang_code = app.ui_settings.get("language", "zh-hans")
        app.selected_language_var.set(app.LANG_CODE_TO_NAME.get(lang_code, "简体中文"))

        mode_key = app.ui_settings.get("appearance_mode", "System")
        display_map = {"Light": _("浅色"), "Dark": _("深色"), "System": _("跟随系统")}
        app.selected_appearance_var.set(display_map.get(mode_key, mode_key))

    def apply_initial_theme(self):
        """【核心修改点 2】根据加载的设置，应用初始主题。"""
        initial_mode = self.app.ui_settings.get("appearance_mode", "System")
        self.apply_theme_from_mode(initial_mode)

    def apply_theme_from_mode(self, mode: str):
        """
        【核心修改点 3】根据外观模式计算主题名称，并调用App实例的中心方法来应用。
        """
        if mode == "Dark":
            theme_name = self.app.ui_settings.get("dark_mode_theme", "darkly")
        elif mode == "Light":
            theme_name = self.app.ui_settings.get("light_mode_theme", "flatly")
        else:
            # 此处可添加代码检测系统是深色还是浅色模式
            theme_name = self.app.ui_settings.get("light_mode_theme", "flatly")

        # 调用 app 实例上那个新的、统一的、健壮的方法
        self.app.apply_theme_and_update_dependencies(theme_name)

    # ... 以下是您文件中的其他方法，大部分保持不变 ...
    def update_language_ui(self, lang_code: str):
        app = self.app
        new_translator = setup_localization(language_code=lang_code)
        self.translator_func = new_translator
        app._ = new_translator

        self._update_placeholders_dictionary(new_translator)
        self._retranslate_all_tabs(new_translator)
        self._retranslate_managed_widgets(new_translator)

        app.logger.info(f"UI language updated to {lang_code}")

    def _retranslate_all_tabs(self, new_translator: Callable[[str], str]):
        for tab_instance in self.app.tool_tab_instances.values():
            if hasattr(tab_instance, 'retranslate_ui'):
                tab_instance.retranslate_ui(translator=new_translator)

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

    def _update_placeholders_dictionary(self, translator: Callable[[str], str]):
        _ = translator
        self.app.placeholders = {
            "homology_genes": _("粘贴基因ID，每行一个..."),
            "gff_genes": _("粘贴基因ID，每行一个..."),
            "gff_region": _("例如: A01:1-100000"),
            "genes_input": _("在此处粘贴要注释的基因ID，每行一个。"),
            "enrichment_genes_input": _(
                "在此处粘贴用于富集分析的基因ID，每行一个。\n如果包含Log2FC，格式为：基因ID\tLog2FC\n（注意：使用制表符分隔，从Excel直接复制的列即为制表符分隔）。"),
            "custom_prompt": _("在此处输入您的自定义提示词模板，必须包含 {text} 占位符..."),
            "default_prompt_empty": _("Default prompt is empty, please set it in the configuration editor.")
        }

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

    def setup_initial_ui(self):
        app = self.app
        self.app.navigation_frame = ttkb.Frame(self.app, style='Sidebar.TFrame')
        self.create_main_layout()
        self.init_pages()
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

        # 【重要修改】确保这里调用的是新的UI填充函数
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
        """
        在UI的日志文本框和状态栏中显示格式化的日志消息。
        此方法被设计为线程安全的，可以从任何线程调用。
        """
        app = self.app
        # 检查UI组件是否存在
        if hasattr(app, 'log_textbox') and app.log_textbox.winfo_exists():
            # 使用 after 方法确保在主UI线程中安全地更新组件
            #
            app.after(0, self._update_ui_log, message, level)

    def _update_ui_log(self, message: str, level: str):
        """这是一个在主线程中执行的回调函数，用于实际更新UI组件。"""
        app = self.app
        # 开启文本框编辑
        app.log_textbox.configure(state="normal")

        # 防止日志过多，自动清理旧日志
        if int(app.log_textbox.index('end-1c').split('.')[0]) > 500:  #
            app.log_textbox.delete("1.0", "2.0")

        # 格式化消息并插入
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())  #
        full_message = f"[{timestamp}] {message}"
        app.log_textbox.insert("end", f"{full_message}\n", f"{level.lower()}_log")  #
        app.log_textbox.see("end")  #

        # 重新禁用文本框编辑
        app.log_textbox.configure(state="disabled")

        # 更新底部状态栏的文本
        app.latest_log_message_var.set(full_message)

        # 根据当前主题（深色/浅色）和日志级别，设置状态栏文本颜色
        is_dark = self.style.theme.type == 'dark'

        # 定义颜色映射表，确保所有模式下都清晰可见
        color_map = {
            "error": "#e57373" if is_dark else "#d9534f",
            "warning": "#ffb74d" if is_dark else "#f0ad4e",
            # info 和 debug 直接使用主题中保证高对比度的标准文本颜色
            "info": self.style.lookup('TLabel', 'foreground'),
            "debug": self.app.default_text_color,  #
            "critical": "#ff0000" if is_dark else "#8b0000"
        }

        # 获取并应用颜色
        display_color = color_map.get(level.lower(), self.style.lookup('TLabel', 'foreground'))  #
        app.status_label.configure(foreground=display_color)

    def _create_navigation_frame(self, parent):
        """
        【最终修复版】创建侧边栏。
        此版本使用内置的、能自动适应主题的 'light' 样式，确保在所有模式下都清晰可见。
        """
        app = self.app
        _ = self.translator_func

        # 【修改点1】移除 bootstyle="light"，让框架背景色自动跟随主题
        app.navigation_frame = ttkb.Frame(parent)
        app.navigation_frame.grid(row=0, column=0, sticky="nsew")
        app.navigation_frame.grid_rowconfigure(4, weight=1)

        # 【修改点2】移除 header_frame 的 bootstyle
        header_frame = ttkb.Frame(app.navigation_frame)
        header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

        if app.logo_image_path:
            try:
                img = Image.open(app.logo_image_path).resize((60, 60), Image.LANCZOS)
                self.icon_cache["logo"] = ImageTk.PhotoImage(img)
                # 【修改点3】移除 Logo 标签的 bootstyle
                ttkb.Label(header_frame, image=self.icon_cache["logo"]).pack(pady=(0, 10))
            except Exception as e:
                app.logger.error(f"加载Logo失败: {e}")
        # 【修改点4】移除 FCGT 标题的 bootstyle
        ttkb.Label(header_frame, text=" FCGT", font=app.app_font_bold).pack()

        # 3. 创建导航按钮，未选中时使用 'light' 样式
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
            # 【修改点5】将按钮的 bootstyle 从 "light" 改为 "info-outline"
            # "outline" 样式能确保在亮色和暗色背景下都有很好的可见性
            btn = ttkb.Button(app.navigation_frame, text=text,
                              command=lambda n=name: self.select_frame_by_name(n), image=icon, compound="left",
                              bootstyle="info-outline")
            btn.grid(row=i + 1, column=0, sticky="ew", padx=15, pady=5)
            setattr(app, f"{name}_button", btn)

        # 4. 创建底部设置区域，也使用 'light' 样式
        settings_frame = ttkb.Frame(app.navigation_frame)
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        appearance_modes_display = [_("浅色"), _("深色"), _("跟随系统")]
        for i, (label, var, values, cmd) in enumerate(
                [(_("语言"), app.selected_language_var, list(app.LANG_CODE_TO_NAME.values()),
                  app.event_handler.on_language_change),
                 (_("外观模式"), app.selected_appearance_var, appearance_modes_display,
                  app.event_handler.change_appearance_mode_event)]):
            # 【修改点7】移除设置标签的 bootstyle
            lbl = ttkb.Label(settings_frame, text=label, font=app.app_font)
            lbl.grid(row=i * 2, column=0, padx=5, pady=(5, 0), sticky="w")
            setattr(app, f"{'language' if i == 0 else 'appearance_mode'}_label", lbl)
            # 【修改点8】将 OptionMenu 的 bootstyle 改为 "info-outline"
            menu = ttkb.OptionMenu(settings_frame, var, var.get(), *values, command=cmd, bootstyle="info-outline")
            menu.grid(row=i * 2 + 1, column=0, padx=5, pady=(0, 10), sticky="ew")
            setattr(app, f"{'language_optionmenu' if i == 0 else 'appearance_mode_optionmenu'}", menu)


    def _get_settings_path(self):
        home_dir = os.path.expanduser("~")
        settings_dir = os.path.join(home_dir, ".fcgt")
        os.makedirs(settings_dir, exist_ok=True)
        return os.path.join(settings_dir, "ui_settings.json")


    def save_ui_settings(self):
        try:
            with open(self._get_settings_path(), 'w', encoding='utf-8') as f:
                json.dump(self.app.ui_settings, f, indent=4)
        except IOError as e:
            self.app.logger.error(f"无法保存UI设置: {e}")


    def _update_log_tag_colors(self):
        """
        根据当前主题（深色/浅色）更新日志文本框中不同级别消息的颜色标签。
        """
        if hasattr(self.app, 'log_textbox') and self.app.log_textbox.winfo_exists():  #
            is_dark = self.style.theme.type == 'dark'

            # 为醒目级别（错误、警告、严重）设置自定义颜色
            self.app.log_textbox.tag_config("error_log", foreground="#e57373" if is_dark else "#d9534f")  #
            self.app.log_textbox.tag_config("warning_log", foreground="#ffb74d" if is_dark else "#f0ad4e")  #
            self.app.log_textbox.tag_config("critical_log", foreground="#ff0000" if is_dark else "#8b0000")  #

            # ✨ 关键优化：为常规级别（信息、调试）直接使用App中定义的、保证高对比度的标准颜色
            self.app.log_textbox.tag_config("info_log", foreground=self.app.default_text_color)  #
            self.app.log_textbox.tag_config("debug_log", foreground=self.app.secondary_text_color)  #


    def select_frame_by_name(self, name):
        """
        【最终修复版】根据名称选择并显示主内容区的框架。
        此版本使用内置样式来切换按钮状态，确保主题切换时正常工作。
        """
        app = self.app

        # 【核心修改】将被选中的按钮设置为 "primary" (实心)，
        # 将所有未被选中的按钮重置为 "info-outline" (轮廓) 样式
        for btn_name in ["home", "editor", "tools"]:
            if btn := getattr(app, f"{btn_name}_button", None):
                if btn_name == name:
                    # 这是被选中的按钮，使用醒目的实心样式
                    btn.config(bootstyle="primary")
                else:
                    # 这是未被选中的按钮，使用清晰的轮廓样式
                    btn.config(bootstyle="info-outline")

            # 2. 将被选中的按钮设置为醒目的 'primary' 实心样式
            if btn_to_select := getattr(app, f"{name}_button", None):
                btn_to_select.config(bootstyle="primary")

            # 3. 切换主页面内容 (这部分逻辑不变)
            for frame_name in ["home_frame", "editor_frame", "tools_frame"]:
                if frame := getattr(app, frame_name, None):
                    frame.grid_remove()
            if frame_to_show := getattr(app, f"{name}_frame", None):
                frame_to_show.grid(row=0, column=0, sticky="nsew")

    def show_info_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), self.translator_func(message),
                      icon_type="info").wait_window()
        # Log to the main log viewer
        self.app._log_to_viewer(f"{title}: {message}", "INFO")

    def show_error_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), message, icon_type="error").wait_window()
        # Log to the main log viewer
        self.app._log_to_viewer(f"{title}: {message}", "ERROR")

    def show_warning_message(self, title: str, message: str):
        MessageDialog(self.app, self.translator_func(title), message, icon_type="warning").wait_window()
        # Log to the main log viewer
        self.app._log_to_viewer(f"{title}: {message}", "WARNING")

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
        """
        【最终修复版】任务结束后，关闭进度条、恢复UI，并根据结果弹出最终提示对话框。
        """
        _ = self.translator_func

        # 1. 关闭进度弹窗 (这部分不变)
        self._hide_progress_dialog()
        # 2. 恢复所有按钮的状态 (这部分不变)
        self.update_button_states(is_task_running=False)
        self.app.active_task_name = None

        # 3. 【核心修正】根据任务结果，弹出相应的提示对话框
        if result_data == "CANCELLED":
            # 如果是用户取消
            self.show_info_message(
                _("任务已取消"),
                _("任务 '{}' 已被用户取消。").format(_(task_display_name))
            )
        elif isinstance(result_data, Exception):
            # 如果是执行失败
            self.show_error_message(
                _("任务失败"),
                _("任务 '{}' 执行时发生错误:\n\n{}").format(_(task_display_name), str(result_data))
            )
        elif success:
            # 如果是成功完成
            self.show_info_message(
                _("任务完成"),
                _("任务 '{}' 已成功完成。").format(_(task_display_name))
            )

        # 4. 更新底部状态栏的文本 (作为辅助提示，保留此功能)
        status_msg = f"{_(task_display_name)}: {result_data if result_data else (_('完成') if success else _('失败'))}"
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
            app.config_path_display_var.set(
                _("当前配置: {}").format(os.path.basename(app.config_path)) if app.config_path else _(
                    "未加载配置"))
        else:
            app.logger.warning(
                _("无法设置 config_path_display_var：变量未就绪或为None。这通常发生在应用程序启动的早期阶段。"))

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

    def update_sidebar_style(self):
        is_dark = self.app.style.theme.type == 'dark'
        # 根据亮暗模式选择不同的背景色
        background_color = self.style.colors.dark if is_dark else self.style.colors.light
        high_contrast_color = self.style.lookup('TLabel', 'foreground')

        # 【第3步 - 核心修正】通过修改样式来更新背景色
        self.style.configure('Sidebar.TFrame', background=background_color)

        # 【保留】对于那些不是 ttk 的子控件，或者需要单独处理的，可以保留 try-except 块
        for child in self.app.navigation_frame.winfo_children():
            try:
                # 这里依然可以尝试设置，因为它能处理非 ttk 控件
                child.configure(background=background_color)
                for grandchild in child.winfo_children():
                    grandchild.configure(background=background_color)
            except tk.TclError:
                # 忽略 ttk 控件的错误
                pass

        # 3. 【核心修正】彻底移除了所有针对按钮的 background 设置
        #    对于 ttk 按钮，不再尝试修改背景色，而是只修改前景色（文字颜色），
        #    因为 ttkbootstrap 会自动处理按钮在不同状态下的视觉效果。
        self.style.configure('sidebar.TButton', foreground=high_contrast_color)
        self.style.configure('sidebar.Selected.TButton', foreground=self.style.colors.primary)

        # 为标签可以安全地设置前景色和背景色
        self.style.configure('sidebar.TLabel', foreground=high_contrast_color, background=background_color)

        # 【核心修正】为“被选中”的按钮，只修改它的前景色，不再尝试修改背景色！
        # ttkbootstrap 会自动处理被选中时的视觉效果（例如边框变色）
        self.style.configure('sidebar.Selected.TButton', foreground=self.style.colors.primary)
