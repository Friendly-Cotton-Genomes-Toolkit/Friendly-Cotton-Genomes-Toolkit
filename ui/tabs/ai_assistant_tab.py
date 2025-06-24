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
    from gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AIAssistantTab(ctk.CTkFrame):
    """ “AI 助手”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        """
        AIAssistantTab的构造函数。

        Args:
            parent: 父级控件，即放置此选项卡的 CTkTabview 的内部框架。
            app (CottonToolkitApp): 主应用程序的实例。
        """
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 1. 将所有 AI 相关的 Tkinter 变量从 gui_app.py 移到这里
        self.ai_task_type_var = tk.StringVar(value=_("翻译"))
        self.ai_proxy_var = tk.BooleanVar(value=self.app.ai_proxy_var.get())  # 从主App获取初始值
        self.ai_temperature_var = tk.DoubleVar(value=0.7)
        self.ai_selected_provider_var = tk.StringVar()
        self.ai_selected_model_var = tk.StringVar()

        # 2. 调用UI创建和初始化方法
        self._create_widgets()
        self.update_from_config()

    def _create_widgets(self):
        """创建AI助手选项卡的全部UI控件。"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold
        app_title_font = self.app.app_title_font

        # --- 1. 顶部标题 ---
        ctk.CTkLabel(self, text=_("使用AI批量处理表格数据"), font=app_title_font, wraplength=500).grid(
            row=0, column=0, pady=(20, 10), padx=20, sticky="n")

        # --- 2. AI模型选择卡片 ---
        model_card = ctk.CTkFrame(self)
        model_card.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        model_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(model_card, text=_("AI服务商:"), font=app_font_bold).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        provider_display_names = [v['name'] for v in self.app.AI_PROVIDERS.values()]
        self.ai_provider_dropdown = ctk.CTkOptionMenu(
            model_card, variable=self.ai_selected_provider_var,
            values=provider_display_names, font=app_font,
            dropdown_font=app_font, command=self._on_ai_provider_selected
        )
        self.ai_provider_dropdown.grid(row=0, column=1, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        ctk.CTkLabel(model_card, text=_("模型:"), font=app_font_bold).grid(
            row=1, column=0, padx=10, pady=(5, 10), sticky="w")

        model_selector_frame = ctk.CTkFrame(model_card, fg_color="transparent")
        model_selector_frame.grid(row=1, column=1, columnspan=2, padx=10, pady=(5, 10), sticky="ew")
        model_selector_frame.grid_columnconfigure(0, weight=1)

        self.ai_model_dropdown = ctk.CTkOptionMenu(
            model_selector_frame, variable=self.ai_selected_model_var,
            values=[_("需先加载配置")], font=app_font, dropdown_font=app_font,
            command=self._on_ai_model_selected
        )
        self.ai_model_dropdown.grid(row=0, column=0, sticky="ew")

        self.ai_test_button = ctk.CTkButton(model_selector_frame, text=_("测试连接"), width=80, font=app_font,
                                            command=self.start_ai_test_on_tab)
        self.ai_test_button.grid(row=0, column=1, padx=(10, 0))

        # --- 3. 任务参数卡片 ---
        main_card = ctk.CTkFrame(self)
        main_card.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        main_card.grid_columnconfigure(1, weight=1)
        main_card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(main_card, text=_("输入CSV文件:"), font=app_font).grid(row=0, column=0, padx=10, pady=10,
                                                                            sticky="w")
        self.ai_input_file_entry = ctk.CTkEntry(main_card, placeholder_text=_("选择一个CSV文件"), height=35,
                                                font=app_font)
        self.ai_input_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ctk.CTkButton(main_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self.app._browse_file(self.ai_input_file_entry, [("CSV files", "*.csv")]),
                      font=app_font).grid(row=0, column=2, padx=(0, 10))

        ctk.CTkLabel(main_card, text=_("选择任务类型:"), font=app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                             sticky="w")
        self.ai_task_type_menu = ctk.CTkOptionMenu(main_card, variable=self.ai_task_type_var,
                                                   values=[_("翻译"), _("分析")], command=self._on_ai_task_type_change,
                                                   height=35, font=app_font, dropdown_font=app_font)
        self.ai_task_type_menu.grid(row=1, column=1, columnspan=2, padx=(0, 10), sticky="ew")

        ctk.CTkLabel(main_card, text=_("Prompt 指令 (用 {text} 代表单元格内容):"), font=app_font).grid(row=2, column=0,
                                                                                                       columnspan=3,
                                                                                                       padx=10,
                                                                                                       pady=(10, 0),
                                                                                                       sticky="w")

        self.ai_translate_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=app_font)
        self.ai_translate_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")
        self.app._bind_mouse_wheel_to_scrollable(self.ai_translate_prompt_textbox)

        self.ai_analyze_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=app_font)
        self.ai_analyze_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")
        self.app._bind_mouse_wheel_to_scrollable(self.ai_analyze_prompt_textbox)

        param_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        param_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        param_frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(param_frame, text=_("源列名:"), font=app_font).grid(row=0, column=0, padx=5)
        self.ai_source_col_entry = ctk.CTkEntry(param_frame, placeholder_text="Description", height=35, font=app_font)
        self.ai_source_col_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(param_frame, text=_("新列名:"), font=app_font).grid(row=0, column=2, padx=5)
        self.ai_new_col_entry = ctk.CTkEntry(param_frame, placeholder_text=_("描述/解释"), height=35, font=app_font)
        self.ai_new_col_entry.grid(row=0, column=3, sticky="ew")

        ctk.CTkLabel(main_card, text=_("输出文件路径 (可选):"), font=app_font).grid(row=5, column=0, padx=10, pady=10,
                                                                                    sticky="w")
        output_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        output_frame.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=5)
        output_frame.grid_columnconfigure(0, weight=1)
        self.ai_output_file_entry = ctk.CTkEntry(output_frame,
                                                 placeholder_text=_("不填则自动在 ai_results/ 目录中生成"), height=35,
                                                 font=app_font)
        self.ai_output_file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(output_frame, text=_("另存为..."), width=100, height=35,
                      command=lambda: self.app._browse_save_file(self.ai_output_file_entry, [("CSV files", "*.csv")]),
                      font=app_font).grid(row=0, column=1)

        ai_proxy_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        ai_proxy_frame.grid(row=6, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        self.ai_proxy_switch = ctk.CTkSwitch(ai_proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.ai_proxy_var, font=app_font)
        self.ai_proxy_switch.pack(side="left")

        temp_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        temp_frame.grid(row=7, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        temp_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(temp_frame, text=_("Temperature:"), font=app_font).grid(row=0, column=0, padx=5)
        self.ai_temp_slider = ctk.CTkSlider(temp_frame, from_=0, to=1, variable=self.ai_temperature_var)
        self.ai_temp_slider.grid(row=0, column=1, padx=(10, 5), sticky="ew")
        temp_value_label = ctk.CTkLabel(temp_frame, textvariable=self.ai_temperature_var, width=40)
        temp_value_label.configure(textvariable=tk.StringVar(value=f"{self.ai_temperature_var.get():.2f}"))
        self.ai_temperature_var.trace_add("write", lambda *args: temp_value_label.configure(
            text=f"{self.ai_temperature_var.get():.2f}"))
        temp_value_label.grid(row=0, column=2)

        # --- 4. 开始按钮 ---
        self.ai_start_button = ctk.CTkButton(self, text=_("开始AI任务"), height=40, command=self.start_ai_task,
                                             font=app_font_bold)
        self.ai_start_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))

        # --- 5. 初始状态设置 ---
        self._on_ai_task_type_change(self.ai_task_type_var.get())

    def update_from_config(self):
        """根据主应用的配置来更新这个选项卡的UI状态。"""
        if not self.app.current_config:
            return

        ai_cfg = self.app.current_config.ai_services
        default_provider_key = ai_cfg.default_provider
        provider_display_name = self.app.AI_PROVIDERS.get(default_provider_key, {}).get('name', default_provider_key)
        self.ai_selected_provider_var.set(provider_display_name)

        self._update_ai_model_dropdown_from_config()
        self._load_prompts_to_ai_tab()

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