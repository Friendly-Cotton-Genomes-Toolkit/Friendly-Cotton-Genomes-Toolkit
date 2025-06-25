# ui/tabs/locus_conversion_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

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

        app_font = self.app.app_font
        app_font_bold = self.app.app_font_bold

        assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [_("无可用版本")]

        # Part 1: 基因组选择
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(top_frame, text=_("源基因组:"), font=app_font).grid(row=0, column=0, padx=(10, 5), pady=5,
                                                                         sticky="w")
        self.locus_source_assembly_dropdown = ctk.CTkOptionMenu(
            top_frame, variable=self.selected_locus_source_assembly, values=assembly_ids,
            font=app_font, dropdown_font=app_font
        )
        self.locus_source_assembly_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(top_frame, text=_("目标基因组:"), font=app_font).grid(row=0, column=2, padx=(10, 5), pady=5,
                                                                           sticky="w")
        self.locus_target_assembly_dropdown = ctk.CTkOptionMenu(
            top_frame, variable=self.selected_locus_target_assembly, values=assembly_ids,
            font=app_font, dropdown_font=app_font
        )
        self.locus_target_assembly_dropdown.grid(row=0, column=3, padx=(5, 10), pady=5, sticky="ew")

        # Part 2: 输入区域
        input_card = ctk.CTkFrame(self, fg_color="transparent")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        input_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_card, text=_("输入染色体区域:"), font=app_font_bold).grid(row=0, column=0, sticky="w")
        self.locus_conversion_region_entry = ctk.CTkEntry(
            input_card,
            font=app_font,
            placeholder_text=_("例如: A03:1000-2000")
        )
        self.locus_conversion_region_entry.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        # Part 3: 高级选项 (严格模式开关)
        adv_options_frame = ctk.CTkFrame(self, fg_color="transparent")
        adv_options_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(10, 0))

        switch_frame = ctk.CTkFrame(adv_options_frame, fg_color="transparent")
        switch_frame.pack(side="left", anchor="w", padx=0)

        self.locus_strict_switch = ctk.CTkSwitch(
            switch_frame, text=_("仅匹配同亚组、同源染色体上的基因 (严格模式)"),
            variable=self.locus_strict_priority_var,
            font=app_font,
            command=self._toggle_locus_warning_label  # command指向本类的方法
        )
        self.locus_strict_switch.pack(side="left")

        self.locus_warning_label = ctk.CTkLabel(
            switch_frame, text=_("关闭后可能导致不同染色体的基因发生错配"),
            text_color=("#D32F2F", "#E57373"),
            font=app_font_bold
        )

        # Part 4: 输出路径选择
        output_frame = ctk.CTkFrame(self, fg_color="transparent")
        output_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(15, 0))
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(output_frame, text=_("选择输出CSV文件路径:"), font=app_font_bold).grid(row=0, column=0, sticky="w")

        output_entry_frame = ctk.CTkFrame(output_frame, fg_color="transparent")
        output_entry_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        output_entry_frame.grid_columnconfigure(0, weight=1)

        self.locus_conversion_output_entry = ctk.CTkEntry(output_entry_frame, font=app_font,
                                                          placeholder_text=_("点击“另存为”选择保存位置"))
        self.locus_conversion_output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # command 指向主应用的通用文件保存对话框方法
        ctk.CTkButton(output_entry_frame, text=_("另存为..."), width=100, font=app_font,
                      command=lambda: self.app._browse_save_file(self.locus_conversion_output_entry,
                                                                 [("CSV files", "*.csv")])).grid(row=0, column=1)

        # Part 5: 运行按钮
        ctk.CTkButton(self, text=_("开始转换"), font=app_font_bold, command=self.start_locus_conversion_task).grid(
            row=4, column=0, padx=10, pady=(20, 10), sticky="e")

    def update_from_config(self):
        """由主应用调用，在配置加载时更新本页面。"""
        self.app._log_to_viewer("DEBUG: LocusConversionTab received update_from_config call.", "DEBUG")
        # 目前此Tab没有需要从配置中直接更新的特殊内容，但保留此方法以符合设计模式。
        pass

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