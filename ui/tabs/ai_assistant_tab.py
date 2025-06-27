# ui/tabs/ai_assistant_tab.py
import os
import tkinter as tk
import traceback
from tkinter import filedialog

import customtkinter as ctk
import copy
import threading
from typing import TYPE_CHECKING, List, Optional

import pandas as pd

from cotton_toolkit.core.ai_wrapper import AIWrapper
# 导入后台任务函数
from cotton_toolkit.pipelines import run_ai_task
from cotton_toolkit.tools.batch_ai_processor import process_single_csv_file
from ui.tabs.base_tab import BaseTab

# 避免循环导入，同时为IDE提供类型提示
if TYPE_CHECKING:
    from ui.gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AIAssistantTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, app)
        self.ai_proxy_var = tk.BooleanVar(value=False)
        self._create_base_widgets()

        # 为自定义提示词添加占位符
        self.app.placeholders["custom_prompt"] = _("在此处输入您的自定义提示词模板，必须包含 {text} 占位符...")

        # 用于保存提示词的防抖计时器
        self._prompt_save_timer = None


    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        safe_text_color = ("gray10", "#DCE4EE")
        font_regular = (self.app.font_family, 14)
        font_mono = (self.app.mono_font_family, 12)

        # --- 第0行: 服务商和模型选择 ---
        provider_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        provider_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        provider_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(provider_frame, text=_("AI服务商:"), font=font_regular, text_color=safe_text_color).grid(row=0, column=0, padx=(15, 5), pady=10)
        provider_names = [v['name'] for v in self.app.AI_PROVIDERS.values()]
        self.ai_selected_provider_var = tk.StringVar()
        self.provider_dropdown = ctk.CTkOptionMenu(provider_frame, variable=self.ai_selected_provider_var, values=provider_names, font=font_regular, dropdown_font=font_regular, command=self._on_provider_change)
        self.provider_dropdown.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        ctk.CTkLabel(provider_frame, text=_("选择模型:"), font=font_regular, text_color=safe_text_color).grid(row=0, column=2, padx=(15, 5), pady=10)
        self.ai_selected_model_var = tk.StringVar()
        self.model_dropdown = ctk.CTkOptionMenu(provider_frame, variable=self.ai_selected_model_var, values=[_("请先选择服务商")], font=font_regular, dropdown_font=font_regular)
        self.model_dropdown.grid(row=0, column=3, padx=5, pady=10, sticky="ew")

        # --- 第1行: 任务类型和提示词模板 ---
        prompt_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        prompt_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5,0))
        prompt_frame.grid_columnconfigure(0, weight=1)

        task_header_frame = ctk.CTkFrame(prompt_frame, fg_color="transparent")
        task_header_frame.grid(row=0, column=0, sticky="ew", pady=(0,5), padx=5)

        ctk.CTkLabel(task_header_frame, text=_("处理任务:"), font=font_regular, text_color=safe_text_color).pack(side="left", padx=(10, 5))
        self.prompt_type_var = tk.StringVar(value=_("翻译"))
        self.prompt_selector = ctk.CTkSegmentedButton(
            task_header_frame,
            values=[_("翻译"), _("分析"), _("自定义")],
            variable=self.prompt_type_var,
            font=font_regular,
            command=self._on_task_type_change
        )
        self.prompt_selector.pack(side="left", padx=5)

        ctk.CTkLabel(prompt_frame, text=_("提示词模板:"), font=font_regular, text_color=safe_text_color).grid(row=1, column=0, padx=(15,5), pady=(5,0), sticky="w")
        self.prompt_textbox = ctk.CTkTextbox(prompt_frame, height=120, font=font_mono, wrap="word")
        self.prompt_textbox.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 10))
        # 绑定 KeyRelease 事件以通过防抖机制触发保存
        self.prompt_textbox.bind("<KeyRelease>", self._on_prompt_change_debounced)

        # --- 第2行: CSV文件处理 ---
        csv_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        csv_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        csv_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(csv_frame, text=_("CSV文件路径:"), font=font_regular, text_color=safe_text_color).grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")
        self.csv_path_entry = ctk.CTkEntry(csv_frame, font=font_regular)
        self.csv_path_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        ctk.CTkButton(csv_frame, text=_("浏览..."), width=100, command=self._browse_csv_file, font=font_regular).grid(row=0, column=2, padx=5, pady=10)

        ctk.CTkLabel(csv_frame, text=_("待处理列:"), font=font_regular, text_color=safe_text_color).grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.source_column_var = tk.StringVar()
        self.source_column_dropdown = ctk.CTkOptionMenu(csv_frame, variable=self.source_column_var, values=[_("请先选择CSV文件")], font=font_regular, dropdown_font=font_regular)
        self.source_column_dropdown.grid(row=1, column=1, padx=5, pady=10, sticky="ew")

        ctk.CTkLabel(csv_frame, text=_("新列名称:"), font=font_regular, text_color=safe_text_color).grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.new_column_entry = ctk.CTkEntry(csv_frame, font=font_regular)
        self.new_column_entry.grid(row=2, column=1, padx=5, pady=10, sticky="ew")

        self.save_as_new_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(csv_frame, text=_("另存为新文件 (否则在原文件上修改)"), variable=self.save_as_new_var, font=font_regular, text_color=safe_text_color).grid(row=3, column=1, padx=5, pady=10, sticky="w")
        ctk.CTkCheckBox(csv_frame, text=_("为AI服务使用HTTP/HTTPS代理 (请在配置编辑器中设置代理地址)"), variable=self.ai_proxy_var, font=font_regular, text_color=safe_text_color).grid(row=4, column=1, columnspan=2, padx=5, pady=(5, 15), sticky="w")

        # --- 第3行: 开始按钮 ---
        self.start_button = ctk.CTkButton(parent_frame, text=_("开始处理CSV文件"), command=self.start_ai_csv_processing_task, height=40, font=(self.app.font_family, 15, "bold"))
        self.start_button.grid(row=3, column=0, sticky="ew", padx=10, pady=(10,15))


    def _on_prompt_change_debounced(self, event=None):
        """在短暂延迟后保存提示词到配置，以避免在每次按键时都保存。"""
        # 如果存在旧的计时器，则取消它
        if self._prompt_save_timer is not None:
            self.after_cancel(self._prompt_save_timer)

        # 设置一个新的计时器
        self._prompt_save_timer = self.after(500, self._save_prompt_to_config)  # 500毫秒延迟

    def _save_prompt_to_config(self):
        """将文本框中当前的提示词保存到配置文件。"""
        if not self.app.current_config or not self.app.config_path:
            return

        current_task = self.prompt_type_var.get()
        current_prompt = self.prompt_textbox.get("1.0", tk.END).strip()

        # 避免保存占位符文本
        is_placeholder = any(current_prompt == _(ph) for ph in self.app.placeholders.values())
        if is_placeholder:
            return

        config_changed = False
        prompts_cfg = self.app.current_config.ai_prompts

        if current_task == _("翻译") and prompts_cfg.translation_prompt != current_prompt:
            prompts_cfg.translation_prompt = current_prompt
            config_changed = True
        elif current_task == _("分析") and prompts_cfg.analysis_prompt != current_prompt:
            prompts_cfg.analysis_prompt = current_prompt
            config_changed = True
        elif current_task == _("自定义") and prompts_cfg.custom_prompt != current_prompt:
            prompts_cfg.custom_prompt = current_prompt
            config_changed = True

        if config_changed:
            self.app._log_to_viewer(_("提示词已更新，正在保存配置..."), "DEBUG")
            # 创建一个深拷贝以传递给线程，避免竞态条件
            config_to_save = copy.deepcopy(self.app.current_config)
            # 在后台线程中运行保存，以免UI冻结
            threading.Thread(
                target=self.app.event_handler.save_config_file,
                args=(config_to_save, False),
                daemon=True
            ).start()

    def _on_task_type_change(self, choice=None):
        """当任务类型改变时，更新提示词文本框。"""
        if not self.app.current_config:
            self.prompt_textbox.delete("1.0", tk.END)
            self.prompt_textbox.insert("1.0", _("请先加载配置文件。"))
            return

        # 在切换内容之前，确保上一个修改已保存
        if self._prompt_save_timer is not None:
            self.after_cancel(self._prompt_save_timer)
            self._save_prompt_to_config()  # 立即保存

        if choice is None:
            choice = self.prompt_type_var.get()

        prompts_cfg = self.app.current_config.ai_prompts
        self.app.ui_manager._clear_placeholder(self.prompt_textbox, "custom_prompt")
        self.prompt_textbox.delete("1.0", tk.END)

        if choice == _("翻译"):
            self.prompt_textbox.insert("1.0", prompts_cfg.translation_prompt or "")
        elif choice == _("分析"):
            self.prompt_textbox.insert("1.0", prompts_cfg.analysis_prompt or "")
        elif choice == _("自定义"):
            custom_prompt_text = prompts_cfg.custom_prompt or ""
            self.prompt_textbox.insert("1.0", custom_prompt_text)
            if not custom_prompt_text:
                self.app.ui_manager._add_placeholder(self.prompt_textbox, "custom_prompt", force=True)

        # 更改内容后将焦点设置到文本框
        self.prompt_textbox.focus_set()



    def _on_provider_change(self, provider_display_name: str):
        self.update_model_dropdown()

    def _browse_csv_file(self):
        filepath = self.app.event_handler._browse_file(None, filetypes=(("CSV files", "*.csv"),
                                                                        ("All files", "*.*")))  # 委托给 EventHandler
        if filepath:
            self.csv_path_entry.delete(0, tk.END)
            self.csv_path_entry.insert(0, filepath)
            self._update_column_dropdown()
        else:  # 如果用户取消了选择
            self.csv_path_entry.delete(0, tk.END)  # 清空输入框
            self.csv_path_entry.insert(0, "")  # 或者设置一个默认文本
            self._update_column_dropdown()  # 刷新列下拉菜单以反映空路径

    def _update_column_dropdown(self):
        """### --- 核心修改: 异步读取CSV列名 --- ###"""
        filepath = self.csv_path_entry.get().strip()
        if not filepath or not os.path.exists(filepath):
            self.source_column_dropdown.configure(values=[_("请先选择有效的CSV文件")])
            self.source_column_var.set("")
            return

        # 立即更新UI，显示加载状态
        self.source_column_dropdown.configure(values=[_("读取中...")])
        self.source_column_var.set(_("读取中..."))

        def load_columns_thread():
            try:
                # 只读取文件的前几行来推断列名，性能更高
                df = pd.read_csv(filepath, nrows=0)
                columns = df.columns.tolist()
                # 将结果放入主消息队列，由主线程安全地更新UI
                self.app.message_queue.put(("csv_columns_fetched", (columns, None)))
            except Exception as e:
                error_msg = f"{_('无法读取CSV列名')}:\n{e}"
                self.app.message_queue.put(("csv_columns_fetched", ([], error_msg)))

        threading.Thread(target=load_columns_thread, daemon=True).start()

    def update_model_dropdown(self):
        if not self.app.current_config:
            self.model_dropdown.configure(values=[_("配置未加载")])
            return

        provider_display_name = self.ai_selected_provider_var.get()
        provider_key = self.app.LANG_NAME_TO_CODE.get(provider_display_name)
        if not provider_key:
            for key, info in self.app.AI_PROVIDERS.items():
                if info['name'] == provider_display_name:
                    provider_key = key
                    break

        if provider_key and provider_key in self.app.current_config.ai_services.providers:
            model_str = self.app.current_config.ai_services.providers[provider_key].model
            if model_str:
                models = [m.strip() for m in model_str.split(',')]
                self.model_dropdown.configure(values=models)
                self.ai_selected_model_var.set(models[0])
            else:
                self.model_dropdown.configure(values=[_("配置中无模型")])
                self.ai_selected_model_var.set("")
        else:
            self.model_dropdown.configure(values=[_("请选择服务商")])
            self.ai_selected_model_var.set("")

    def update_column_dropdown_ui(self, columns: List[str], error_msg: Optional[str]):
        """
        实际更新CSV列下拉菜单UI的方法。此方法应由 EventHandler 调用。
        此方法应在 AIAssistantTab 内部实现。
        """
        if error_msg:
            self.app.ui_manager.show_error_message(_("读取错误"), error_msg)
            self.source_column_dropdown.configure(values=[_("读取失败")])
            self.source_column_var.set(_("读取失败"))
        elif columns:
            self.source_column_dropdown.configure(values=columns)
            if self.source_column_var.get() not in columns:
                self.source_column_var.set(columns[0])
        else:
            self.source_column_dropdown.configure(values=[_("无可用列")])
            self.source_column_var.set(_("无可用列"))

    def update_from_config(self):
        if not self.app.current_config:
            return

        # 更新代理复选框
        self.ai_proxy_var.set(self.app.current_config.ai_services.use_proxy_for_ai)

        # 更新服务商和模型下拉菜单
        default_provider_key = self.app.current_config.ai_services.default_provider
        default_provider_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', '')
        if default_provider_name:
            self.ai_selected_provider_var.set(default_provider_name)
        self.update_model_dropdown()

        # 更新提示词文本框以反映当前配置
        self._on_task_type_change()



    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'):
            self.start_button.configure(state=state)

    def _load_prompts_to_ai_tab(self):
        """将配置中的Prompt模板加载到AI助手页面的输入框中。"""
        if not self.app.current_config: return
        prompts_cfg = self.app.current_config.ai_prompts
        trans_prompt = prompts_cfg.translation_prompt
        analy_prompt = prompts_cfg.analysis_prompt

        self.ai_translate_prompt_textbox.delete("1.0", tk.END)
        self.ai_translate_prompt_textbox.insert("1.0", trans_prompt)

        self.ai_analyze_prompt_textbox.delete("1.0", tk.END)
        self.ai_analyze_prompt_textbox.insert("1.0", analy_prompt)

    def _update_ai_model_dropdown_from_config(self):
        """根据当前配置，更新AI助手的模型下拉菜单。"""
        if not self.app.current_config:
            self.ai_model_dropdown.configure(values=[_("需先加载配置")])
            self.ai_selected_model_var.set(_("需先加载配置"))
            return

        selected_provider_name = self.ai_selected_provider_var.get()
        name_to_key_map = {v['name']: k for k, v in self.app.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_provider_name)

        if not provider_key:
            self.ai_model_dropdown.configure(values=[_("无效的服务商")])
            self.ai_selected_model_var.set(_("无效的服务商"))
            return

        provider_config = self.app.current_config.ai_services.providers.get(provider_key)
        if not provider_config or not provider_config.model:
            self.ai_model_dropdown.configure(values=[_("未在配置中指定模型")])
            self.ai_selected_model_var.set(_("未在配置中指定模型"))
            return

        model_list_str = provider_config.model
        available_models = [m.strip() for m in model_list_str.split(',') if m.strip()]

        if not available_models:
            self.ai_model_dropdown.configure(values=[_("模型列表为空")])
            self.ai_selected_model_var.set(_("模型列表为空"))
            return

        self.ai_model_dropdown.configure(values=available_models)
        self.ai_selected_model_var.set(available_models[0])

    def _on_ai_task_type_change(self, choice):
        """根据AI任务类型切换显示的Prompt输入框。"""
        if choice == _("分析"):
            self.ai_analyze_prompt_textbox.grid()
            self.ai_translate_prompt_textbox.grid_remove()
        else:
            self.ai_translate_prompt_textbox.grid()
            self.ai_analyze_prompt_textbox.grid_remove()

    def _on_ai_provider_selected(self, selected_display_name: str):
        """当服务商下拉菜单变化时触发。"""
        self.app._log_to_viewer(f"INFO: AI provider changed to '{selected_display_name}'")
        self._update_ai_model_dropdown_from_config()

        # 异步自动保存用户的服务商选择到主配置文件
        name_to_key_map = {v['name']: k for k, v in self.app.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_display_name)
        if self.app.current_config and provider_key:
            self.app.current_config.ai_services.default_provider = provider_key
            threading.Thread(target=self.app._save_config_from_ui, daemon=True).start()

    def _on_ai_model_selected(self, selected_model: str):
        """当模型下拉菜单被用户选择时触发。"""
        if not self.app.current_config: return
        selected_provider_name = self.ai_selected_provider_var.get()
        name_to_key_map = {v['name']: k for k, v in self.app.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_provider_name)

        if provider_key:
            self.app.current_config.ai_services.providers[provider_key].model = selected_model
            threading.Thread(target=self.app._save_config_from_ui, daemon=True).start()

    def start_ai_test_on_tab(self):
        """从AI助手页面触发连接测试。"""
        selected_display_name = self.ai_selected_provider_var.get()
        name_to_key_map = {v['name']: k for k, v in self.app.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_display_name)
        if provider_key:
            self.app._gui_start_ai_connection_test(provider_key)

    def start_ai_csv_processing_task(self):
        """启动一个后台任务来使用AI处理指定的CSV文件列。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        try:
            # 首先，确保任何待处理的提示词修改都已保存
            self._save_prompt_to_config()

            provider_name = self.ai_selected_provider_var.get()
            model = self.ai_selected_model_var.get()
            prompt_type = self.prompt_type_var.get()
            csv_path = self.csv_path_entry.get().strip()
            source_column = self.source_column_var.get()
            new_column_name = self.new_column_entry.get().strip()
            save_as_new = self.save_as_new_var.get()

            # 直接从文本框获取提示词模板
            prompt_template = self.prompt_textbox.get("1.0", tk.END).strip()

            # --- 验证 ---
            if not all([provider_name, model, csv_path, source_column, new_column_name]):
                self.app.show_error_message(_("输入缺失"), _("请确保所有必填项都已填写。"))
                return
            if not os.path.exists(csv_path):
                self.app.show_error_message(_("文件错误"), _("指定的CSV文件不存在。"))
                return
            if prompt_type == _("自定义") and not prompt_template:
                self.app.show_error_message(_("输入缺失"), _("使用“自定义”任务时，提示词模板不能为空。"))
                return

            provider_key = ""
            for key, info in self.app.AI_PROVIDERS.items():
                if info['name'] == provider_name: provider_key = key; break

            provider_config = self.app.current_config.ai_services.providers.get(provider_key)
            if not provider_config:
                self.app.show_error_message(_("配置错误"), f"{_('找不到服务商')} '{provider_key}' {_('的配置。')}")
                return

            # 在启动任务前，从UI更新配置中的代理设置
            self.app.current_config.ai_services.use_proxy_for_ai = self.ai_proxy_var.get()
            proxies = None
            if self.ai_proxy_var.get():
                if self.app.current_config.proxies and (self.app.current_config.proxies.http or self.app.current_config.proxies.https):
                    proxies = self.app.current_config.proxies.to_dict()
                else:
                    self.app.show_warning_message(_("代理警告"), _("AI代理开关已打开，但未在配置编辑器中设置代理地址。"))

            output_path_for_task = None
            if not save_as_new:
                 output_path_for_task = csv_path

            # 将配置深拷贝以传递给线程
            config_for_task = copy.deepcopy(self.app.current_config)

            self.app.event_handler._start_task(
                task_name=_("AI批量处理CSV"),
                target_func=run_ai_task,
                kwargs={
                    'config': config_for_task,
                    'input_file': csv_path,
                    'source_column': source_column,
                    'new_column': new_column_name,
                    'task_type': prompt_type, # 传递任务类型以用于缓存标识符
                    'custom_prompt_template': prompt_template, # 传递文本框中的实际提示词
                    'cli_overrides': None,
                    'output_file': output_path_for_task
                }
            )

        except Exception as e:
            self.app.show_error_message(_("任务启动失败"),
                                        f"{_('准备AI处理任务时发生错误:')}\n{traceback.format_exc()}")
