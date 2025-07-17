# 文件路径: ui/tabs/ai_assistant_tab.py

import copy
import os
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, List, Optional, Callable

import pandas as pd
import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_ai_task
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class AIAssistantTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.ai_proxy_var = tk.BooleanVar(value=False)
        self.ai_selected_provider_var = tk.StringVar()
        self.ai_selected_model_var = tk.StringVar()
        self.prompt_type_var = tk.StringVar()
        self.source_column_var = tk.StringVar()
        self.save_as_new_var = tk.BooleanVar(value=True)
        self._prompt_save_timer = None

        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            # self._ 属性在 super().__init__ 后才可用
            self.action_button.configure(text=self._("开始处理CSV文件"), command=self.start_ai_csv_processing_task)

        self.update_from_config()


    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        【修改】将所有需要翻译的元件都储存为 self 的属性。
        """
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 储存 UI 元件 ---
        self.title_label = ttkb.Label(parent_frame, text=_("AI 助手"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        self.provider_card = ttkb.LabelFrame(parent_frame, text=_("AI服务与模型"), bootstyle="secondary")
        self.provider_card.grid(row=1, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.provider_card.grid_columnconfigure((1, 3), weight=1)

        self.provider_label = ttk.Label(self.provider_card, text=_("AI服务商:"), font=self.app.app_font_bold)
        self.provider_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        provider_names = [v['name'] for v in self.app.AI_PROVIDERS.values()]
        initial_provider = provider_names[0] if provider_names else ""
        self.provider_dropdown = ttkb.OptionMenu(self.provider_card, self.ai_selected_provider_var, initial_provider,
                                                 *provider_names, command=self._on_provider_change, bootstyle="info")
        self.provider_dropdown.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.model_label = ttk.Label(self.provider_card, text=_("选择模型:"), font=self.app.app_font_bold)
        self.model_label.grid(row=0, column=2, padx=(15, 5), pady=10, sticky="w")
        self.model_dropdown = ttkb.OptionMenu(self.provider_card, self.ai_selected_model_var, _("请先选择服务商"),
                                              *[_("请先选择服务商")], bootstyle="info")
        self.model_dropdown.grid(row=0, column=3, padx=(5, 10), pady=10, sticky="ew")

        self.prompt_card = ttkb.LabelFrame(parent_frame, text=_("处理任务与提示词"), bootstyle="secondary")
        self.prompt_card.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        self.prompt_card.grid_columnconfigure(0, weight=1)
        self.prompt_card.grid_rowconfigure(2, weight=1)

        task_header_frame = ttk.Frame(self.prompt_card)
        task_header_frame.grid(row=0, column=0, sticky="ew", pady=5, padx=5)
        self.task_label = ttk.Label(task_header_frame, text=_("处理任务:"), font=self.app.app_font_bold)
        self.task_label.pack(side="left", padx=(5, 10))

        # 将 Radiobutton 也存为属性
        # 注意：这里 Radiobutton 的 value 应该使用英文键，方便内部逻辑判断
        self.translation_radio = ttkb.Radiobutton(task_header_frame, text=_("翻译"), variable=self.prompt_type_var,
                                                  value="translate", command=self._on_task_type_change,
                                                  bootstyle="toolbutton-success")
        self.translation_radio.pack(side="left", padx=5)
        self.analysis_radio = ttkb.Radiobutton(task_header_frame, text=_("分析"), variable=self.prompt_type_var,
                                               value="analyze", command=self._on_task_type_change,
                                               bootstyle="toolbutton-success")
        self.analysis_radio.pack(side="left", padx=5)
        self.custom_radio = ttkb.Radiobutton(task_header_frame, text=_("自定义"), variable=self.prompt_type_var,
                                             value="custom", command=self._on_task_type_change,
                                             bootstyle="toolbutton-success")
        self.custom_radio.pack(side="left", padx=5)
        self.prompt_type_var.set("translate")  # 设定初始值，使用英文键

        self.prompt_template_label = ttk.Label(self.prompt_card, text=_("提示词模板:"), font=self.app.app_font_bold)
        self.prompt_template_label.grid(row=1, column=0, padx=10, pady=(5, 0), sticky="w")
        self.prompt_textbox = tk.Text(self.prompt_card, height=8, font=self.app.app_font, wrap="word", relief="flat",
                                      background=self.app.style.lookup('TFrame', 'background'),
                                      foreground=self.app.style.lookup('TLabel', 'foreground'),
                                      insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.prompt_textbox.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        self.prompt_textbox.bind("<KeyRelease>", self._on_prompt_change_debounced)
        # 绑定焦点事件，以便 UIManager 管理占位符
        self.prompt_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.prompt_textbox,
                                                                                             self.prompt_type_var.get()))
        self.prompt_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.prompt_textbox,
                                                                                               self.prompt_type_var.get()))

        self.csv_card = ttkb.LabelFrame(parent_frame, text=_("CSV文件处理"), bootstyle="secondary")
        self.csv_card.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        self.csv_card.grid_columnconfigure(1, weight=1)

        self.csv_path_label = ttk.Label(self.csv_card, text=_("CSV文件路径:"), font=self.app.app_font_bold)
        self.csv_path_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.csv_path_entry = ttk.Entry(self.csv_card)
        self.csv_path_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        self.csv_browse_button = ttkb.Button(self.csv_card, text=_("浏览..."), width=12, command=self._browse_csv_file,
                                             bootstyle="info-outline")
        self.csv_browse_button.grid(row=0, column=2, padx=(5, 10), pady=10)

        self.source_column_label = ttk.Label(self.csv_card, text=_("待处理列:"), font=self.app.app_font_bold)
        self.source_column_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.source_column_dropdown = ttkb.OptionMenu(self.csv_card, self.source_column_var, _("请先选择CSV文件"),
                                                      *[_("请先选择CSV文件")], bootstyle="info")
        self.source_column_dropdown.grid(row=1, column=1, padx=5, pady=10, sticky="ew")

        self.new_column_label = ttk.Label(self.csv_card, text=_("新列名称:"), font=self.app.app_font_bold)
        self.new_column_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.new_column_entry = ttk.Entry(self.csv_card)
        self.new_column_entry.grid(row=2, column=1, padx=5, pady=10, sticky="ew")

        options_frame = ttk.Frame(self.csv_card)
        options_frame.grid(row=3, column=1, columnspan=2, padx=5, pady=10, sticky="w")
        self.save_as_new_check = ttkb.Checkbutton(options_frame, text=_("另存为新文件 (否则在原文件上修改)"),
                                                  variable=self.save_as_new_var, bootstyle="round-toggle")
        self.save_as_new_check.pack(side='left', anchor='w')
        self.use_proxy_check = ttkb.Checkbutton(options_frame, text=_("为AI服务使用HTTP/HTTPS代理"),
                                                variable=self.ai_proxy_var, bootstyle="round-toggle")
        self.use_proxy_check.pack(side='left', anchor='w', padx=(20, 0))

    def retranslate_ui(self, translator: Callable[[str], str]):
        """
        【新增】当语言切换时，此方法被 UIManager 调用以更新 UI 文本。
        """
        self.title_label.configure(text=translator("AI 助手"))

        self.provider_card.configure(text=translator("AI服务与模型"))
        self.provider_label.configure(text=translator("AI服务商:"))
        self.model_label.configure(text=translator("选择模型:"))

        self.prompt_card.configure(text=translator("处理任务与提示词"))
        self.task_label.configure(text=translator("处理任务:"))

        # Radiobutton 的 text 需要更新，value 保持英文键不变
        self.translation_radio.configure(text=translator("翻译"))
        self.analysis_radio.configure(text=translator("分析"))
        self.custom_radio.configure(text=translator("自定义"))

        self.prompt_template_label.configure(text=translator("提示词模板:"))

        self.csv_card.configure(text=translator("CSV文件处理"))
        self.csv_path_label.configure(text=translator("CSV文件路径:"))
        self.csv_browse_button.configure(text=translator("浏览..."))
        self.source_column_label.configure(text=translator("待处理列:"))
        self.new_column_label.configure(text=translator("新列名称:"))

        self.save_as_new_check.configure(text=translator("另存为新文件 (否则在原文件上修改)"))
        self.use_proxy_check.configure(text=translator("为AI服务使用HTTP/HTTPS代理"))

        if self.action_button:
            self.action_button.configure(text=translator("开始处理CSV文件"))

        # 更新 OptionMenu 中的占位符
        self.app.ui_manager.update_option_menu(self.model_dropdown, self.ai_selected_model_var, [],
                                               translator("请先选择服务商"))
        self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [],
                                               translator("请先选择CSV文件"))

        # 强制刷新当前显示的提示词，确保其翻译正确
        self._on_task_type_change()

    def _on_prompt_change_debounced(self, event=None):
        if self._prompt_save_timer is not None: self.after_cancel(self._prompt_save_timer)
        self._prompt_save_timer = self.after(500, self._save_prompt_to_config)

    def _save_prompt_to_config(self):
        if not self.app.current_config or not self.app.config_path: return

        # 获取当前 prompt_type_var 的英文值
        current_task_key = self.prompt_type_var.get()
        current_prompt = self.prompt_textbox.get("1.0", tk.END).strip()

        # 检查是否是占位符文本，如果是则不保存
        # 这里的判断逻辑需要更精确，因为 _on_task_type_change 可能会直接设置 config 中的值
        # 最好是判断 widget.is_placeholder 标志
        if getattr(self.prompt_textbox, 'is_placeholder', False) or not current_prompt:
            return

        config_changed = False
        prompts_cfg = self.app.current_config.ai_prompts

        if current_task_key == "translate" and prompts_cfg.translation_prompt != current_prompt:
            prompts_cfg.translation_prompt = current_prompt
            config_changed = True
        elif current_task_key == "analyze" and prompts_cfg.analysis_prompt != current_prompt:
            prompts_cfg.analysis_prompt = current_prompt
            config_changed = True
        elif current_task_key == "custom" and hasattr(prompts_cfg,
                                                      'custom_prompt') and prompts_cfg.custom_prompt != current_prompt:
            prompts_cfg.custom_prompt = current_prompt
            config_changed = True

        if config_changed:
            self.app._log_to_viewer(_("提示词已更新，正在后台保存配置..."), "DEBUG")
            config_to_save = copy.deepcopy(self.app.current_config)
            # 假设您有一个非阻塞的保存方法
            # threading.Thread(target=self.app.event_handler.save_config_file_non_blocking, args=(config_to_save, self.app.config_path), daemon=True).start()

    def _on_task_type_change(self, choice=None):
        """
        【修改】直接从配置对象读取提示词，而不是从编辑器UI组件。
        并确保清除旧的占位符状态或设置新的占位符。
        """
        task_type = self.prompt_type_var.get()  # 获取英文键 (translate, analyze, custom)
        prompt_text = ""

        # 确保 config 已经加载并且存在 ai_prompts 属性
        if self.app.current_config and hasattr(self.app.current_config, 'ai_prompts'):
            ai_prompts = self.app.current_config.ai_prompts
            if task_type == "translate":  # 使用英文键进行比较
                prompt_text = ai_prompts.translation_prompt
            elif task_type == "analyze":  # 使用英文键进行比较
                prompt_text = ai_prompts.analysis_prompt
            elif task_type == "custom":  # 使用英文键进行比较
                # 确保 custom_prompt 属性存在，兼容旧配置
                prompt_text = getattr(ai_prompts, 'custom_prompt', '')

        # 清空当前提示框的内容和占位符状态
        self.app.ui_manager._clear_placeholder(self.prompt_textbox, task_type)  # clear_placeholder 现在会检查 is_placeholder
        self.prompt_textbox.delete("1.0", tk.END)  # 彻底清空

        if prompt_text:
            self.prompt_textbox.insert("1.0", prompt_text)
            # 确保恢复到正常字体和颜色，并清除占位符标志
            self.prompt_textbox.configure(font=self.app.app_font_mono, foreground=self.app.default_text_color)
            setattr(self.prompt_textbox, 'is_placeholder', False)
        else:
            # 如果配置中没有对应提示词，则显示占位符
            # 根据当前选择的任务类型确定占位符文本
            placeholder_text_key = "default_prompt_empty"
            if task_type == "custom":
                placeholder_text_key = "custom_prompt"  # 使用 UIManager 中已翻译的 custom_prompt 键

            # 从 UIManager 维护的 placeholers 字典中获取翻译后的文本
            placeholder_text = self.app.placeholders.get(placeholder_text_key,
                                                         _("Default prompt is empty, please set it in the configuration editor."))
            self.app.ui_manager.add_placeholder(self.prompt_textbox, placeholder_text)

    def _on_provider_change(self, provider_display_name: str):
        self.update_model_dropdown()

    def _browse_csv_file(self):
        # ... (此方法逻辑保持不变) ...
        filepath = filedialog.askopenfilename(filetypes=(("CSV files", "*.csv"), ("All files", "*.*")))
        if filepath:
            self.csv_path_entry.delete(0, tk.END)
            self.csv_path_entry.insert(0, filepath)
            self._update_column_dropdown()

    def _update_column_dropdown(self):
        """
        当用户选择一个新的CSV文件后，此函数被调用。
        它会启动一个后台线程来安全地读取文件的列名，避免UI卡顿。
        """
        filepath = self.csv_path_entry.get().strip()
        _ = self._  # 使用实例的翻译函数

        if not filepath or not os.path.exists(filepath):
            # 如果路径无效，直接更新UI并返回
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [],
                                                   _("请先选择有效的CSV文件"))
            return

        # 先在UI上显示“读取中...”，提供即时反馈
        self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [],
                                               _("读取中..."))

        # 定义将在后台线程中运行的函数
        def load_columns_thread():
            try:
                # 只读取第一行来获取列名，效率最高
                df = pd.read_csv(filepath, nrows=0)
                columns = df.columns.tolist()
                # 【核心修改】使用 after() 方法将UI更新任务安全地调度回主线程
                self.app.after(0, self.update_column_dropdown_ui, columns, None)
            except Exception as e:
                # 发生任何错误，同样将错误信息安全地调度回主线程
                error_msg = f"{_('无法读取CSV列名')}:\n{e}"
                self.app.after(0, self.update_column_dropdown_ui, [], error_msg)

        # 启动后台线程
        threading.Thread(target=load_columns_thread, daemon=True).start()

    def update_column_dropdown_ui(self, columns: List[str], error_msg: Optional[str]):
        """
        【这是一个UI更新函数】
        此函数总是在主UI线程中被安全地调用，负责将获取到的列名更新到下拉菜单中。
        """
        _ = self._  # 使用实例的翻译函数

        if error_msg:
            self.app.ui_manager.show_error_message(_("读取失败"), error_msg)
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [],
                                                   _("读取失败"))
        else:
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, columns,
                                                   _("无可用列"))

    def update_model_dropdown(self):
        """根据当前选定的服务商，从配置的 available_models 字段更新模型列表。"""
        provider_name = self.ai_selected_provider_var.get()
        provider_key = next((k for k, v in self.app.AI_PROVIDERS.items() if v['name'] == provider_name), None)

        models = []
        if self.app.current_config and provider_key:
            provider_cfg = self.app.current_config.ai_services.providers.get(provider_key)
            # --- 【核心修正】从新的 available_models 字段读取列表 ---
            if provider_cfg and provider_cfg.available_models:
                # 如果 available_models 有内容，则用它作为选项
                models = [m.strip() for m in provider_cfg.available_models.split(',') if m.strip()]
            elif provider_cfg and provider_cfg.model:
                # 否则，作为备用方案，使用旧的 model 字段
                models = [m.strip() for m in provider_cfg.model.split(',') if m.strip()]

        # 使用获取到的模型列表更新UI下拉菜单
        self.app.ui_manager.update_option_menu(self.model_dropdown, self.ai_selected_model_var, models, _("无可用模型"))

    def update_from_config(self):
        """当主配置加载或更新后，刷新此选项卡的状态。"""
        if not self.app.current_config:
            return

        self.ai_proxy_var.set(self.app.current_config.ai_services.use_proxy_for_ai)

        default_provider_key = self.app.current_config.ai_services.default_provider
        default_provider_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', '')
        if default_provider_name:
            self.ai_selected_provider_var.set(default_provider_name)

        # 这会使用新的逻辑从 available_models 更新选项列表
        self.update_model_dropdown()

        # --- 【核心修正】---
        # 从配置的 model 字段读取“当前选定”的模型并设置
        provider_key_for_model = next(
            (k for k, v in self.app.AI_PROVIDERS.items() if v['name'] == self.ai_selected_provider_var.get()), None)
        if provider_key_for_model:
            provider_cfg = self.app.current_config.ai_services.providers.get(provider_key_for_model)
            # 确保 model 字段的值在可选列表中
            if provider_cfg and provider_cfg.model and provider_cfg.model in self.ai_selected_model_var.get().split(
                    ','):
                self.ai_selected_model_var.set(provider_cfg.model)
            elif self.model_dropdown['menu'].index('end') is not None:
                # 如果已保存的模型不在列表中，则默认选择列表中的第一个
                first_option = self.model_dropdown['menu'].entrycget(0, "label")
                self.ai_selected_model_var.set(first_option)

        self._on_task_type_change()
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)


    def start_ai_csv_processing_task(self):
        if not self.app.current_config: self.app.ui_manager.show_error_message(_("错误"),
                                                                               _("请先加载配置文件。")); return
        try:
            self._save_prompt_to_config()
            provider_name = self.ai_selected_provider_var.get()
            model = self.ai_selected_model_var.get()
            csv_path = self.csv_path_entry.get().strip()
            source_column = self.source_column_var.get()
            new_column_name = self.new_column_entry.get().strip()
            prompt_template = self.prompt_textbox.get("1.0", tk.END).strip()

            if not all([provider_name, model, csv_path, source_column, new_column_name, prompt_template]):
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请确保所有必填项都已填写。"))
                return
            if source_column in [_("请先选择CSV文件"), _("读取中..."), _("读取失败"), _("无可用列")]:
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个有效的“待处理列”。"))
                return
            if not os.path.exists(csv_path):
                self.app.ui_manager.show_error_message(_("文件错误"), _("指定的CSV文件不存在。"))
                return
            if "{text}" not in prompt_template:
                self.app.ui_manager.show_error_message(_("模板错误"), _("提示词模板必须包含 {text} 占位符。"))
                return

            config_for_task = copy.deepcopy(self.app.current_config)
            config_for_task.ai_services.use_proxy_for_ai = self.ai_proxy_var.get()
            provider_key = next((k for k, v in self.app.AI_PROVIDERS.items() if v['name'] == provider_name), None)

            cli_overrides = {"ai_provider": provider_key, "ai_model": model}
            output_file = None
            if not self.save_as_new_var.get():
                output_file = csv_path

            self.app.event_handler._start_task(
                task_name=_("AI批量处理CSV"),
                target_func=run_ai_task,
                kwargs={
                    'config': config_for_task, 'input_file': csv_path,
                    'source_column': source_column, 'new_column': new_column_name,
                    'task_type': 'custom', 'custom_prompt_template': prompt_template,
                    'cli_overrides': cli_overrides, 'output_file': output_file
                }
            )
        except Exception as e:
            self.app.ui_manager.show_error_message(_("任务启动失败"),
                                                   f"{_('准备AI处理任务时发生错误:')}\n{traceback.format_exc()}")