# ui/tabs/ai_assistant_tab.py

import tkinter as tk
import customtkinter as ctk
import copy
import threading
from typing import TYPE_CHECKING

# 导入后台任务函数
from cotton_toolkit.pipelines import run_ai_task

# 避免循环导入，同时为IDE提供类型提示
if TYPE_CHECKING:
    from ui.gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AIAssistantTab(ctk.CTkFrame):
    """ “AI 助手”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)
        self.scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.scrollable_frame.grid_rowconfigure(1, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        parent_frame = self.scrollable_frame

        # 【核心修改】为所有作为卡片的 CTkFrame 添加了 border_width=0
        model_card = ctk.CTkFrame(parent_frame, border_width=0)
        model_card.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))
        model_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(model_card, text=_("AI模型设置"), font=self.app.app_font_bold).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")
        ctk.CTkLabel(model_card, text=_("AI服务商:"), font=self.app.app_font).grid(
            row=1, column=0, padx=15, pady=10, sticky="w")
        self.ai_selected_provider_var = tk.StringVar()
        self.provider_dropdown = ctk.CTkOptionMenu(
            model_card, variable=self.ai_selected_provider_var,
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.provider_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(model_card, text=_("模型名称:"), font=self.app.app_font).grid(
            row=2, column=0, padx=15, pady=10, sticky="w")
        self.ai_model_name_entry = ctk.CTkEntry(model_card, font=self.app.app_font)
        self.ai_model_name_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        chat_card = ctk.CTkFrame(parent_frame, border_width=0)
        chat_card.grid(row=1, column=0, sticky="nsew", padx=5, pady=10)
        chat_card.grid_columnconfigure(0, weight=1)
        chat_card.grid_rowconfigure(0, weight=1)
        self.chat_history_textbox = ctk.CTkTextbox(
            chat_card, state="disabled", wrap="word", font=self.app.app_font)
        self.chat_history_textbox.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        self.chat_input_entry = ctk.CTkEntry(
            chat_card, placeholder_text=_("在此输入您的问题..."), font=self.app.app_font)
        self.chat_input_entry.grid(row=1, column=0, sticky="ew", padx=(10, 5), pady=(5, 10))
        self.send_button = ctk.CTkButton(chat_card, text=_("发送"), width=100)
        self.send_button.grid(row=1, column=1, sticky="e", padx=(0, 10), pady=(5, 10))

        proxy_card = ctk.CTkFrame(parent_frame, border_width=0)
        proxy_card.grid(row=2, column=0, sticky="ew", padx=5, pady=10)
        self.ai_proxy_var = tk.BooleanVar(value=False)
        self.proxy_switch = ctk.CTkSwitch(
            proxy_card, text=_("使用网络代理（需在配置编辑器中设置地址）"),
            variable=self.ai_proxy_var, font=self.app.app_font
        )
        self.proxy_switch.pack(side="left", padx=15, pady=15)



    def update_from_config(self):
        if self.app.current_config:
            provider_names = [v['name'] for v in self.app.AI_PROVIDERS.values()]
            self.provider_dropdown.configure(values=provider_names)
            default_provider_key = self.app.current_config.ai_services.default_provider
            default_display_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', '')
            if default_display_name in provider_names:
                self.ai_selected_provider_var.set(default_display_name)

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.send_button.configure(state=state)


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

    def start_ai_task(self):
        """启动AI任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        input_file = self.ai_input_file_entry.get().strip()
        source_col = self.ai_source_col_entry.get().strip()
        new_col = self.ai_new_col_entry.get().strip()
        task_type_display = self.ai_task_type_var.get()
        cli_overrides = {"temperature": self.ai_temperature_var.get()}
        output_file = self.ai_output_file_entry.get().strip() or None

        selected_provider_name = self.ai_selected_provider_var.get()
        name_to_key_map = {v['name']: k for k, v in self.app.AI_PROVIDERS.items()}
        provider_key = name_to_key_map.get(selected_provider_name)
        model_name = self.ai_selected_model_var.get()

        task_type = "analyze" if task_type_display == _("分析") else "translate"
        prompt = self.ai_analyze_prompt_textbox.get("1.0",
                                                    tk.END).strip() if task_type == 'analyze' else self.ai_translate_prompt_textbox.get(
            "1.0", tk.END).strip()

        if not all([input_file, source_col, new_col]):
            self.app.show_error_message(_("输入缺失"), _("请输入文件路径、源列名和新列名。"))
            return
        if not provider_key or not model_name or "需先" in model_name or "未在" in model_name:
            self.app.show_error_message(_("配置缺失"), _("请选择一个有效的AI服务商和模型。"))
            return
        if not prompt or "{text}" not in prompt:
            self.app.show_error_message(_("Prompt格式错误"), _("Prompt指令不能为空，且必须包含占位符 '{text}'。"))
            return

        temp_config = copy.deepcopy(self.app.current_config)
        temp_config.ai_services.default_provider = provider_key
        if provider_key in temp_config.ai_services.providers:
            temp_config.ai_services.providers[provider_key].model = model_name

        if not self.ai_proxy_var.get():
            if temp_config.downloader:
                temp_config.downloader.proxies = None

        task_kwargs = {
            'config': temp_config,
            'input_file': input_file,
            'source_column': source_col,
            'new_column': new_col,
            'task_type': task_type,
            'custom_prompt_template': prompt,
            'cli_overrides': cli_overrides,
            'output_file': output_file
        }

        self.app._start_task(
            task_name=_("AI 助手任务"),
            target_func=run_ai_task,
            kwargs=task_kwargs
        )