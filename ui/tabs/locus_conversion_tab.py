# ui/tabs/locus_conversion_tab.py
import os
import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

from cotton_toolkit.config.loader import get_local_downloaded_file_path
# 导入后台任务函数
from cotton_toolkit.pipelines import run_locus_conversion

# 避免循环导入
if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class LocusConversionTab(ctk.CTkFrame):
    """ “位点转换”选项卡的主界面类 """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 1. 将所有 locus_conversion 相关的 Tkinter 变量移到这里
        self.s2b_file_path_var = tk.StringVar(value=_("..."))
        self.b2t_file_path_var = tk.StringVar(value=_("..."))
        self.selected_locus_source_assembly = tk.StringVar()
        self.selected_locus_target_assembly = tk.StringVar()
        self.locus_strict_priority_var = tk.BooleanVar(value=True)

        # 2. 调用UI创建和初始化方法
        self._create_widgets()
        self.update_from_config()
        self._toggle_locus_warning_label()  # 设置警告标签的初始状态

    def _create_widgets(self):
        """创建位点转换选项卡的全部UI控件。"""
        self.grid_columnconfigure(0, weight=1)
        # 将第1行配置为权重1，允许滚动框架填充空间
        self.grid_rowconfigure(1, weight=1)

        # 创建一个可滚动的框架来容纳所有内容
        scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        scrollable_frame.grid_columnconfigure(0, weight=1)

        # --- 卡片1: 输入与选择 ---
        input_frame = ctk.CTkFrame(scrollable_frame)
        input_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        input_frame.grid_columnconfigure(1, weight=1)

        input_label = ctk.CTkLabel(input_frame, text=_("基因组版本与输入"), font=self.app.app_font_bold)
        input_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        # 源基因组版本下拉菜单
        source_assembly_label = ctk.CTkLabel(input_frame, text=_("源基因组版本:"), font=self.app.app_font)
        source_assembly_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.source_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame,
            variable=self.app.selected_locus_source_assembly,
            values=[_("加载中...")],
            font=self.app.app_font,
            height=35,
            dropdown_font=self.app.app_font,
            command=lambda _: self._update_homology_file_display()
        )
        self.source_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        # 目标基因组版本下拉菜单
        target_assembly_label = ctk.CTkLabel(input_frame, text=_("目标基因组版本:"), font=self.app.app_font)
        target_assembly_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.target_assembly_dropdown = ctk.CTkOptionMenu(
            input_frame,
            variable=self.app.selected_locus_target_assembly,
            values=[_("加载中...")],
            font=self.app.app_font,
            height=35,
            dropdown_font=self.app.app_font,
            command=lambda _: self._update_homology_file_display()
        )
        self.target_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        # 位点输入框
        locus_input_label = ctk.CTkLabel(input_frame, text=_("输入位点:"), font=self.app.app_font)
        locus_input_label.grid(row=3, column=0, padx=(10, 5), pady=(10, 15), sticky="nw")
        self.locus_input_textbox = ctk.CTkTextbox(input_frame, height=120, font=self.app.app_font, wrap="word")
        self.locus_input_textbox.grid(row=3, column=1, padx=(0, 10), pady=(10, 15), sticky="ew")
        self.app._bind_mouse_wheel_to_scrollable(self.locus_input_textbox)

        # --- 卡片2: 同源文件状态 ---
        path_display_frame = ctk.CTkFrame(scrollable_frame)
        path_display_frame.pack(fill="x", expand=True, pady=10, padx=5)

        path_label = ctk.CTkLabel(path_display_frame, text=_("同源文件状态"), font=self.app.app_font_bold)
        path_label.pack(anchor="w", padx=10, pady=(10, 5))

        # 源到桥梁文件路径显示
        s2b_frame = ctk.CTkFrame(path_display_frame, fg_color="transparent")
        s2b_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(s2b_frame, text=_("源->桥梁 同源文件:"), font=self.app.app_font).pack(side="left")
        self.s2b_file_label = ctk.CTkLabel(s2b_frame, textvariable=self.s2b_file_path_var, font=self.app.app_font, text_color="gray")
        self.s2b_file_label.pack(side="left", padx=10)

        # 桥梁到目标文件路径显示
        b2t_frame = ctk.CTkFrame(path_display_frame, fg_color="transparent")
        b2t_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(b2t_frame, text=_("桥梁->目标 同源文件:"), font=self.app.app_font).pack(side="left")
        self.b2t_file_label = ctk.CTkLabel(b2t_frame, textvariable=self.b2t_file_path_var, font=self.app.app_font, text_color="gray")
        self.b2t_file_label.pack(side="left", padx=10)

        # --- 卡片3: 结果输出 ---
        output_frame = ctk.CTkFrame(scrollable_frame)
        output_frame.pack(fill="both", expand=True, pady=10, padx=5)
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(1, weight=1) # 让文本框填充

        output_label = ctk.CTkLabel(output_frame, text=_("转换结果"), font=self.app.app_font_bold)
        output_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        self.result_textbox = ctk.CTkTextbox(output_frame, state="disabled", wrap="none", font=self.app.app_font_mono)
        self.result_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.app._bind_mouse_wheel_to_scrollable(self.result_textbox)

        # --- 底部开始按钮 ---
        self.start_button = ctk.CTkButton(
            self,
            text=_("开始转换"),
            height=40,
            font=self.app.app_font_bold,
            command=self.start_locus_conversion_task
        )
        self.start_button.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 15))


    def update_from_config(self):
        """由主应用调用，在配置加载时更新本页面。"""
        self.app._log_to_viewer("DEBUG: LocusConversionTab received update_from_config call.", "DEBUG")
        # 目前此Tab没有需要从配置中直接更新的特殊内容，但保留此方法以符合设计模式。
        pass

    def _update_homology_file_display(self):
        """
        根据当前选择的源和目标基因组，更新同源文件路径的显示。
        这个方法现在是 LocusConversionTab 的一部分，实现了自管理。
        """
        source_id = self.app.selected_locus_source_assembly.get()
        target_id = self.app.selected_locus_target_assembly.get()

        if not self.app.current_config or not self.app.genome_sources_data:
            self.s2b_file_path_var.set(_("请先加载配置"))
            self.b2t_file_path_var.set(_("请先加载配置"))
            return

        ok_color = self.app.default_label_text_color
        warn_color = ("#D84315", "#FF7043")  # Orange
        error_color = ("#D32F2F", "#E57373")  # Red

        # --- 处理源到桥梁文件 (Source to Bridge) ---
        source_info = self.app.genome_sources_data.get(source_id)
        if source_info and hasattr(source_info, 'homology_ath_url') and source_info.homology_ath_url:
            s2b_path = get_local_downloaded_file_path(self.app.current_config, source_info, 'homology_ath')
            if s2b_path and os.path.exists(s2b_path):
                self.s2b_file_path_var.set(os.path.basename(s2b_path))
                self.s2b_file_label.configure(text_color=ok_color)
            else:
                self.s2b_file_path_var.set(_("文件未找到，请先下载"))
                self.s2b_file_label.configure(text_color=error_color)
        else:
            self.s2b_file_path_var.set(_("源基因组未配置同源文件"))
            self.s2b_file_label.configure(text_color=warn_color)

        # --- 处理桥梁到目标文件 (Bridge to Target) ---
        target_info = self.app.genome_sources_data.get(target_id)
        if target_info and hasattr(target_info, 'homology_ath_url') and target_info.homology_ath_url:
            b2t_path = get_local_downloaded_file_path(self.app.current_config, target_info, 'homology_ath')
            if b2t_path and os.path.exists(b2t_path):
                self.b2t_file_path_var.set(os.path.basename(b2t_path))
                self.b2t_file_label.configure(text_color=ok_color)
            else:
                self.b2t_file_path_var.set(_("文件未找到，请先下载"))
                self.b2t_file_label.configure(text_color=error_color)
        else:
            self.b2t_file_path_var.set(_("目标基因组未配置同源文件"))
            self.b2t_file_label.configure(text_color=warn_color)


    def update_assembly_dropdowns(self, assembly_ids: list):
        if self.source_assembly_dropdown and self.source_assembly_dropdown.winfo_exists():
            self.source_assembly_dropdown.configure(values=assembly_ids)
        if self.target_assembly_dropdown and self.target_assembly_dropdown.winfo_exists():
            self.target_assembly_dropdown.configure(values=assembly_ids)
        # 更新后，手动调用一次文件显示更新
        self._update_homology_file_display()


    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """由主应用调用，用于更新本选项卡内的基因组下拉菜单。"""
        current_source = self.selected_locus_source_assembly.get()
        if current_source not in assembly_ids:
            self.selected_locus_source_assembly.set(assembly_ids[0] if "无可用" not in assembly_ids[0] else "")

        current_target = self.selected_locus_target_assembly.get()
        if current_target not in assembly_ids:
            self.selected_locus_target_assembly.set(assembly_ids[0] if "无可用" not in assembly_ids[0] else "")

        self.locus_source_assembly_dropdown.configure(values=assembly_ids)
        self.locus_target_assembly_dropdown.configure(values=assembly_ids)

    def _toggle_locus_warning_label(self):
        """根据严格模式开关，显示或隐藏警告标签。"""
        if self.locus_strict_priority_var.get():
            self.locus_warning_label.pack_forget()
        else:
            self.locus_warning_label.pack(side="left", padx=15, pady=0)

    def start_locus_conversion_task(self):
        """启动位点转换任务。"""
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        source_assembly = self.selected_locus_source_assembly.get()
        target_assembly = self.selected_locus_target_assembly.get()
        region_str = self.locus_conversion_region_entry.get().strip()
        output_path = self.locus_conversion_output_entry.get().strip()
        is_strict = self.locus_strict_priority_var.get()

        if not all([source_assembly, target_assembly, region_str, output_path]):
            self.app.show_error_message(_("输入缺失"), _("请选择基因组、输入区域并指定输出文件路径。"))
            return

        if source_assembly == target_assembly:
            self.app.show_warning_message(_("警告"), _("源基因组和目标基因组相同，转换可能没有意义。"))

        try:
            chrom, pos_range = region_str.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom.strip(), start, end)
        except ValueError:
            self.app.show_error_message(_("输入错误"), _("区域格式不正确，请使用 'Chr:Start-End' 格式。"))
            return

        self.app._start_task(
            task_name=_("位点转换"),
            target_func=run_locus_conversion,
            kwargs={
                'config': self.app.current_config,
                'source_assembly_id': source_assembly,
                'target_assembly_id': target_assembly,
                'region': region_tuple,
                'output_path': output_path,
                'strict': is_strict
            }
        )