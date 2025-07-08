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
    def __init__(self, parent, app: "CottonToolkitApp"):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.ai_proxy_var = tk.BooleanVar(value=False)
        self.ai_selected_provider_var = tk.StringVar()
        self.ai_selected_model_var = tk.StringVar()
        self.prompt_type_var = tk.StringVar()
        self.source_column_var = tk.StringVar()
        self.save_as_new_var = tk.BooleanVar(value=True)
        self._prompt_save_timer = None

        super().__init__(parent, app)
        if self.action_button:
            self.action_button.configure(text=_("开始处理CSV文件"), command=self.start_ai_csv_processing_task)

        self.app.placeholders["custom_prompt"] = _("在此处输入您的自定义提示词模板，必须包含 {text} 占位符...")
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
        self.translation_radio = ttkb.Radiobutton(task_header_frame, text=_("翻译"), variable=self.prompt_type_var,
                                                  value=_("翻译"), command=self._on_task_type_change,
                                                  bootstyle="toolbutton-success")
        self.translation_radio.pack(side="left", padx=5)
        self.analysis_radio = ttkb.Radiobutton(task_header_frame, text=_("分析"), variable=self.prompt_type_var,
                                               value=_("分析"), command=self._on_task_type_change,
                                               bootstyle="toolbutton-success")
        self.analysis_radio.pack(side="left", padx=5)
        self.custom_radio = ttkb.Radiobutton(task_header_frame, text=_("自定义"), variable=self.prompt_type_var,
                                             value=_("自定义"), command=self._on_task_type_change,
                                             bootstyle="toolbutton-success")
        self.custom_radio.pack(side="left", padx=5)
        self.prompt_type_var.set(_("翻译"))  # 设定初始值

        self.prompt_template_label = ttk.Label(self.prompt_card, text=_("提示词模板:"), font=self.app.app_font_bold)
        self.prompt_template_label.grid(row=1, column=0, padx=10, pady=(5, 0), sticky="w")
        self.prompt_textbox = tk.Text(self.prompt_card, height=8, font=self.app.app_font, wrap="word", relief="flat",
                                      background=self.app.style.lookup('TFrame', 'background'),
                                      foreground=self.app.style.lookup('TLabel', 'foreground'),
                                      insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.prompt_textbox.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        self.prompt_textbox.bind("<KeyRelease>", self._on_prompt_change_debounced)

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

        # Radiobutton 的 text 和 value 都需要更新，以确保逻辑正确
        # 先储存旧的值
        old_value = self.prompt_type_var.get()

        # 更新每个 Radiobutton 的文字和它代表的值
        self.translation_radio.configure(text=translator("翻译"), value=translator("翻译"))
        self.analysis_radio.configure(text=translator("分析"), value=translator("分析"))
        self.custom_radio.configure(text=translator("自定义"), value=translator("自定义"))

        # 根据旧的值，设定新的翻译后的值
        if old_value in [_("翻译"), _("Translation")]:
            self.prompt_type_var.set(translator("翻译"))
        elif old_value in [_("分析"), _("Analysis")]:
            self.prompt_type_var.set(translator("分析"))
        elif old_value in [_("自定义"), _("Custom")]:
            self.prompt_type_var.set(translator("自定义"))
        else:
            self.prompt_type_var.set(translator("翻译"))  # 默认值

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

        # 更新 placeholder 文本
        self.app.placeholders["custom_prompt"] = translator("在此处输入您的自定义提示词模板，必须包含 {text} 占位符...")
        # 强制刷新当前显示的提示词
        self._on_task_type_change()

    def _on_prompt_change_debounced(self, event=None):
        if self._prompt_save_timer is not None: self.after_cancel(self._prompt_save_timer)
        self._prompt_save_timer = self.after(500, self._save_prompt_to_config)

    def _save_prompt_to_config(self):
        if not self.app.current_config or not self.app.config_path: return
        current_task = self.prompt_type_var.get()
        current_prompt = self.prompt_textbox.get("1.0", tk.END).strip()
        is_placeholder = (current_prompt == self.app.placeholders.get("custom_prompt", ""))
        if not current_prompt or is_placeholder: return
        config_changed = False
        prompts_cfg = self.app.current_config.ai_prompts
        if current_task == _("翻译") and prompts_cfg.translation_prompt != current_prompt:
            prompts_cfg.translation_prompt = current_prompt;
            config_changed = True
        elif current_task == _("分析") and prompts_cfg.analysis_prompt != current_prompt:
            prompts_cfg.analysis_prompt = current_prompt;
            config_changed = True
        elif current_task == _("自定义") and hasattr(prompts_cfg,
                                                     'custom_prompt') and prompts_cfg.custom_prompt != current_prompt:
            prompts_cfg.custom_prompt = current_prompt;
            config_changed = True
        if config_changed:
            self.app._log_to_viewer(_("提示词已更新，正在后台保存配置..."), "DEBUG")
            config_to_save = copy.deepcopy(self.app.current_config)
            # 假设您有一个非阻塞的保存方法
            # threading.Thread(target=self.app.event_handler.save_config_file_non_blocking, args=(config_to_save, self.app.config_path), daemon=True).start()

    def _on_task_type_change(self, choice=None):
        current_choice = self.prompt_type_var.get()
        if not self.app.current_config:
            self.prompt_textbox.delete("1.0", tk.END)
            self.prompt_textbox.insert("1.0", _("请先加载配置文件。"))
            return

        if self._prompt_save_timer is not None:
            self.after_cancel(self._prompt_save_timer)
            self._save_prompt_to_config()

        prompts_cfg = self.app.current_config.ai_prompts
        self.prompt_textbox.delete("1.0", tk.END)
        prompt_text = ""

        if current_choice == _("翻译"):
            prompt_text = prompts_cfg.translation_prompt
        elif current_choice == _("分析"):
            prompt_text = prompts_cfg.analysis_prompt
        elif current_choice == _("自定义"):
            custom_prompt_text = getattr(prompts_cfg, 'custom_prompt', '') or ""
            if not custom_prompt_text:
                self.app.ui_manager.add_placeholder(self.prompt_textbox, "custom_prompt")
            else:
                prompt_text = custom_prompt_text

        if prompt_text:
            self.prompt_textbox.insert("1.0", prompt_text)

        if current_choice != _("自定义") or prompt_text:
            self.app.ui_manager._remove_placeholder(self.prompt_textbox)

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
        filepath = self.csv_path_entry.get().strip()
        if not filepath or not os.path.exists(filepath):
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var,
                                                   [_("请先选择有效的CSV文件")])
            return
        self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [_("读取中...")])

        def load_columns_thread():
            try:
                df = pd.read_csv(filepath, nrows=0)
                columns = df.columns.tolist()
                self.app.message_queue.put(("csv_columns_fetched", (columns, None)))
            except Exception as e:
                error_msg = f"{_('无法读取CSV列名')}:\n{e}"
                self.app.message_queue.put(("csv_columns_fetched", ([], error_msg)))

        threading.Thread(target=load_columns_thread, daemon=True).start()

    def update_column_dropdown_ui(self, columns: List[str], error_msg: Optional[str]):
        if error_msg:
            self.app.ui_manager.show_error_message(_("读取失败"), error_msg)
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, [_("读取失败")])
        else:
            self.app.ui_manager.update_option_menu(self.source_column_dropdown, self.source_column_var, columns,
                                                   _("无可用列"))

    def update_model_dropdown(self):
        provider_name = self.ai_selected_provider_var.get()
        provider_key = next((k for k, v in self.app.AI_PROVIDERS.items() if v['name'] == provider_name), None)
        models = []
        if self.app.current_config and provider_key:
            provider_cfg = self.app.current_config.ai_services.providers.get(provider_key)
            if provider_cfg and provider_cfg.model:
                models = [m.strip() for m in provider_cfg.model.split(',') if m.strip()]
        self.app.ui_manager.update_option_menu(self.model_dropdown, self.ai_selected_model_var, models, _("无可用模型"))

    def update_from_config(self):
        if not self.app.current_config: return
        self.ai_proxy_var.set(self.app.current_config.ai_services.use_proxy_for_ai)
        default_provider_key = self.app.current_config.ai_services.default_provider
        default_provider_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', '')
        if default_provider_name: self.ai_selected_provider_var.set(default_provider_name)
        self.update_model_dropdown()
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