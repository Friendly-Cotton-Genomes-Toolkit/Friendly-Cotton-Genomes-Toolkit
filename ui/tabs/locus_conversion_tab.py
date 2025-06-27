# ui/tabs/locus_conversion_tab.py
import os
import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

from cotton_toolkit.config.loader import get_local_downloaded_file_path
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class LocusConversionTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):

        self.selected_source_assembly = tk.StringVar()
        self.selected_target_assembly = tk.StringVar()

        super().__init__(parent, app)
        self._create_base_widgets()


    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_rowconfigure(2, weight=1)
        parent_frame.grid_columnconfigure(0, weight=1)

        safe_text_color = ("gray10", "#DCE4EE")
        font_regular = (self.app.font_family, 14)
        font_bold = (self.app.font_family, 15, "bold")
        font_title = (self.app.font_family, 24, "bold")
        font_mono = (self.app.mono_font_family, 12)

        ctk.CTkLabel(parent_frame, text=_("位点坐标转换"), font=font_title, text_color=safe_text_color).grid(row=0, column=0, pady=(5, 10), padx=10, sticky="n")

        main_card = ctk.CTkFrame(parent_frame, fg_color="transparent")
        main_card.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        main_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(main_card, text=_("源基因组:"), font=font_regular, text_color=safe_text_color).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.source_assembly_dropdown = ctk.CTkOptionMenu(main_card, variable=self.selected_source_assembly, values=[_("加载中...")], font=font_regular, dropdown_font=font_regular)
        self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(main_card, text=_("目标基因组:"), font=font_regular, text_color=safe_text_color).grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.target_assembly_dropdown = ctk.CTkOptionMenu(main_card, variable=self.selected_target_assembly, values=[_("加载中...")], font=font_regular, dropdown_font=font_regular)
        self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(main_card, text=_("输入区域 (Chr:Start-End):"), font=font_regular, text_color=safe_text_color).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.region_entry = ctk.CTkEntry(main_card, font=font_regular)
        self.region_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        self.start_button = ctk.CTkButton(main_card, text=_("开始转换"), command=self.start_locus_conversion_task, font=font_bold)
        self.start_button.grid(row=3, column=0, columnspan=2, padx=10, pady=(15, 20), sticky="ew")

        result_card = ctk.CTkFrame(parent_frame, fg_color="transparent")
        result_card.grid(row=2, column=0, sticky="nsew", padx=5, pady=10)
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(result_card, text=_("转换结果"), font=font_bold, text_color=safe_text_color).grid(row=0, column=0, padx=10, pady=(10,5), sticky="w")
        self.result_textbox = ctk.CTkTextbox(result_card, state="disabled", wrap="none", font=font_mono)
        self.result_textbox.grid(row=1, column=0, padx=10, pady=(5,10), sticky="nsew")


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))



    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        if not assembly_ids: assembly_ids = [_("加载中...")]

        # 配置源下拉菜单
        self.source_assembly_dropdown.configure(values=assembly_ids)
        if assembly_ids and "加载中" not in assembly_ids[0]:
            if self.selected_source_assembly.get() not in assembly_ids:
                self.selected_source_assembly.set(assembly_ids[0])

        # 配置目标下拉菜单
        self.target_assembly_dropdown.configure(values=assembly_ids)
        if assembly_ids and "加载中" not in assembly_ids[0]:
            if self.selected_target_assembly.get() not in assembly_ids:
                self.selected_target_assembly.set(assembly_ids[0])



    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        self.start_button.configure(state=state)


    def start_locus_conversion_task(self):
        if not self.app.current_config:
            self.app.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        source_assembly = self.selected_source_assembly.get()
        target_assembly = self.selected_target_assembly.get()
        region_str = self.region_entry.get().strip()

        if not all([source_assembly, target_assembly, region_str]):
            self.app.show_error_message(_("输入缺失"), _("请选择源/目标基因组并输入区域。"))
            return

        try:
            chrom, pos_range = region_str.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom.strip(), start, end)
        except ValueError:
            self.app.show_error_message(_("输入错误"), _("区域格式不正确，请使用 'Chr:Start-End' 格式。"))
            return

        # 假设后端函数叫 run_locus_conversion
        from cotton_toolkit.pipelines import run_locus_conversion
        task_kwargs = {
            'config': self.app.current_config,
            'source_assembly_id': source_assembly,
            'target_assembly_id': target_assembly,
            'region': region_tuple,
        }
        self.app.event_handler._start_task(  # 委托给 EventHandler
            task_name=_("位点转换"),
            target_func=run_locus_conversion,
            kwargs=task_kwargs
        )