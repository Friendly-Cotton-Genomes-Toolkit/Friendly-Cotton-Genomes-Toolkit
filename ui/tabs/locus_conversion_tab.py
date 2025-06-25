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

    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(parent_frame, text=_("位点坐标转换"), font=self.app.app_title_font).grid(
            row=0, column=0, pady=(5, 10), padx=10, sticky="n")

        main_card = ctk.CTkFrame(parent_frame, border_width=0)
        main_card.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        main_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(main_card, text=_("源基因组:"), font=self.app.app_font).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.source_assembly_dropdown = ctk.CTkOptionMenu(
            main_card, variable=self.selected_source_assembly, values=[_("加载中...")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(main_card, text=_("目标基因组:"), font=self.app.app_font).grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.target_assembly_dropdown = ctk.CTkOptionMenu(
            main_card, variable=self.selected_target_assembly, values=[_("加载中...")],
            font=self.app.app_font, dropdown_font=self.app.app_font
        )
        self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(main_card, text=_("输入区域 (Chr:Start-End):"), font=self.app.app_font).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.region_entry = ctk.CTkEntry(main_card, font=self.app.app_font)
        self.region_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        self.start_button = ctk.CTkButton(
            main_card, text=_("开始转换"),
            command=self.start_locus_conversion_task, font=self.app.app_font_bold
        )
        self.start_button.grid(row=3, column=0, columnspan=2, padx=10, pady=(15, 20), sticky="ew")

        result_card = ctk.CTkFrame(parent_frame, border_width=0)
        result_card.grid(row=2, column=0, sticky="nsew", padx=5, pady=10)
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(result_card, text=_("转换结果"), font=self.app.app_font_bold).grid(row=0, column=0, padx=10, pady=(10,5), sticky="w")
        self.result_textbox = ctk.CTkTextbox(result_card, state="disabled", wrap="none", font=self.app.app_font_mono)
        self.result_textbox.grid(row=1, column=0, padx=10, pady=(5,10), sticky="nsew")



    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))


    def _update_homology_file_display(self):
        source_id = self.selected_locus_source_assembly.get()
        target_id = self.selected_locus_target_assembly.get()

        if not self.app.current_config or not self.app.genome_sources_data:
            self.s2b_file_path_var.set(_("请先加载配置"))
            self.b2t_file_path_var.set(_("请先加载配置"))
            return

        ok_color, warn_color, error_color = self.app.default_label_text_color, ("#D84315", "#FF7043"), ("#D32F2F",
                                                                                                        "#E57373")

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
        self.app._start_task(
            task_name=_("位点转换"),
            target_func=run_locus_conversion,
            kwargs=task_kwargs
        )