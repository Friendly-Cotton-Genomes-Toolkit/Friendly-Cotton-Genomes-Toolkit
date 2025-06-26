# ui/tabs/ai_assistant_tab.py
import os
import tkinter as tk
import traceback
from tkinter import filedialog

import customtkinter as ctk
import copy
import threading
from typing import TYPE_CHECKING

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

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 服务商与模型选择 ---
        provider_frame = ctk.CTkFrame(parent_frame)  # 父容器是 parent_frame
        provider_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(10, 5))
        provider_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(provider_frame, text=_("AI服务商:"), font=self.app.app_font).grid(row=0, column=0, padx=(15, 5),
                                                                                       pady=10)

        provider_names = [v['name'] for v in self.app.AI_PROVIDERS.values()]
        self.ai_selected_provider_var = tk.StringVar()
        self.provider_dropdown = ctk.CTkOptionMenu(
            provider_frame, variable=self.ai_selected_provider_var, values=provider_names,
            font=self.app.app_font, dropdown_font=self.app.app_font, command=self._on_provider_change
        )
        self.provider_dropdown.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        ctk.CTkLabel(provider_frame, text=_("选择模型:"), font=self.app.app_font).grid(row=0, column=2, padx=(15, 5),
                                                                                       pady=10)
        self.ai_selected_model_var = tk.StringVar()
        self.model_dropdown = ctk.CTkOptionMenu(
            provider_frame, variable=self.ai_selected_model_var, values=[_("请先选择服务商")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.model_dropdown.grid(row=0, column=3, padx=5, pady=10, sticky="ew")

        # --- 提示词选择 ---
        prompt_frame = ctk.CTkFrame(parent_frame)  # 父容器是 parent_frame
        prompt_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=5)
        ctk.CTkLabel(prompt_frame, text=_("处理任务:"), font=self.app.app_font).grid(row=0, column=0, padx=(15, 5),
                                                                                     pady=10)
        self.prompt_type_var = tk.StringVar(value=_("翻译"))
        self.prompt_selector = ctk.CTkSegmentedButton(
            prompt_frame, values=[_("翻译"), _("分析")], variable=self.prompt_type_var, font=self.app.app_font
        )
        self.prompt_selector.grid(row=0, column=1, padx=5, pady=10, sticky="w")

        # --- CSV文件处理 ---
        csv_frame = ctk.CTkFrame(parent_frame)  # 父容器是 parent_frame
        csv_frame.grid(row=2, column=0, sticky="nsew", padx=0, pady=5)
        csv_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(csv_frame, text=_("CSV文件路径:"), font=self.app.app_font).grid(row=0, column=0, padx=(15, 5),
                                                                                     pady=10, sticky="w")
        self.csv_path_entry = ctk.CTkEntry(csv_frame, font=self.app.app_font)
        self.csv_path_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        ctk.CTkButton(csv_frame, text=_("浏览..."), width=100, command=self._browse_csv_file).grid(row=0, column=2,
                                                                                                   padx=5, pady=10)

        ctk.CTkLabel(csv_frame, text=_("待处理列:"), font=self.app.app_font).grid(row=1, column=0, padx=(15, 5),
                                                                                  pady=10, sticky="w")
        self.source_column_var = tk.StringVar()
        self.source_column_dropdown = ctk.CTkOptionMenu(
            csv_frame, variable=self.source_column_var, values=[_("请先选择CSV文件")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.source_column_dropdown.grid(row=1, column=1, padx=5, pady=10, sticky="ew")

        ctk.CTkLabel(csv_frame, text=_("新列名称:"), font=self.app.app_font).grid(row=2, column=0, padx=(15, 5),
                                                                                  pady=10, sticky="w")
        self.new_column_entry = ctk.CTkEntry(csv_frame, font=self.app.app_font)
        self.new_column_entry.grid(row=2, column=1, padx=5, pady=10, sticky="ew")

        self.save_as_new_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(csv_frame, text=_("另存为新文件 (否则在原文件上修改)"), variable=self.save_as_new_var,
                        font=self.app.app_font).grid(row=3, column=1, padx=5, pady=10, sticky="w")

        self.ai_proxy_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(csv_frame, text=_("为AI服务使用HTTP/HTTPS代理 (请在配置编辑器中设置代理地址)"),
                        variable=self.ai_proxy_var, font=self.app.app_font).grid(row=4, column=1, padx=5, pady=(5, 15),
                                                                                 sticky="w")

        # --- 执行按钮 ---
        self.start_button = ctk.CTkButton(parent_frame, text=_("开始处理CSV文件"),
                                          command=self.start_ai_csv_processing_task, height=40)  # 父容器是 parent_frame
        self.start_button.grid(row=3, column=0, sticky="ew", padx=0, pady=10)


    def _on_provider_change(self, provider_display_name: str):
        self.update_model_dropdown()

    def _browse_csv_file(self):
        filepath = filedialog.askopenfilename(
            title=_("选择CSV文件"),
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*"))
        )
        if filepath:
            self.csv_path_entry.delete(0, tk.END)
            self.csv_path_entry.insert(0, filepath)
            self._update_column_dropdown()

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
        if not provider_key:  # Fallback for display name to key mapping
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

    def update_from_config(self):
        if not self.app.current_config:
            return

        default_provider_key = self.app.current_config.ai_services.default_provider
        default_provider_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', '')
        if default_provider_name:
            self.ai_selected_provider_var.set(default_provider_name)

        self.update_model_dropdown()


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
            self.app.start_ai_connection_test(provider_key)

    def start_ai_csv_processing_task(self):
        """启动一个后台任务来使用AI处理指定的CSV文件列。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        try:
            provider_name = self.ai_selected_provider_var.get()
            model = self.ai_selected_model_var.get()
            prompt_type = self.prompt_type_var.get()
            csv_path = self.csv_path_entry.get().strip()
            source_column = self.source_column_var.get()
            new_column_name = self.new_column_entry.get().strip()
            save_as_new = self.save_as_new_var.get()
            use_proxy = self.ai_proxy_var.get()

            if not all([provider_name, model, csv_path, source_column, new_column_name]):
                self.app.show_error_message(_("输入缺失"), _("请确保所有必填项都已填写。"));
                return
            if not os.path.exists(csv_path):
                self.app.show_error_message(_("文件错误"), _("指定的CSV文件不存在。"));
                return

            provider_key = ""
            for key, info in self.app.AI_PROVIDERS.items():
                if info['name'] == provider_name: provider_key = key; break

            provider_config = self.app.current_config.ai_services.providers.get(provider_key)
            if not provider_config:
                self.app.show_error_message(_("配置错误"), f"{_('找不到服务商')} '{provider_key}' {_('的配置。')}");
                return

            prompt_template = self.app.current_config.ai_prompts.translation_prompt if prompt_type == _(
                "翻译") else self.app.current_config.ai_prompts.analysis_prompt

            proxies = None
            if use_proxy:
                proxies = {'http': self.app.current_config.downloader.proxies.http,
                           'https': self.app.current_config.downloader.proxies.https}

            output_path_for_task = None if save_as_new else csv_path

            ai_client = AIWrapper(
                provider=provider_key, api_key=provider_config.api_key, model=model,
                base_url=provider_config.base_url, proxies=proxies
            )

            task_kwargs = {
                'client': ai_client, 'input_csv_path': csv_path,
                'output_csv_directory': os.path.dirname(csv_path),
                'source_column_name': source_column, 'new_column_name': new_column_name,
                'user_prompt_template': prompt_template,
                'task_identifier': f"{os.path.basename(csv_path)}_{prompt_type}",
                'max_row_workers': self.app.current_config.batch_ai_processor.max_workers,
                'output_csv_path': output_path_for_task
            }

            self.app._start_task(
                task_name=_("AI批量处理CSV"),
                target_func=process_single_csv_file,
                kwargs=task_kwargs
            )
        except Exception as e:
            self.app.show_error_message(_("任务启动失败"),
                                        f"{_('准备AI处理任务时发生错误:')}\n{traceback.format_exc()}")