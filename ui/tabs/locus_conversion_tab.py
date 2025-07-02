# ui/tabs/locus_conversion_tab.py
import os
import tkinter as tk
from tkinter import font as tkfont
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import TYPE_CHECKING, List

from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class LocusConversionTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp"):
        # 保存主程序的 style 对象，以备后用
        self.style = app.style

        # 初始化特定于此选项卡的变量
        self.selected_source_assembly = tk.StringVar()
        self.selected_target_assembly = tk.StringVar()

        super().__init__(parent, app)

        # 修复：在初始化时就创建所有控件
        self._create_base_widgets()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        ttkb.Label(parent, text=_("位点坐标转换"), font=self.app.app_title_font, bootstyle="primary").grid(row=0,
                                                                                                           column=0,
                                                                                                           pady=(10,
                                                                                                                 15),
                                                                                                           padx=10)

        # 卡片1: 输入区域
        main_card = ttkb.Frame(parent, bootstyle="secondary")
        main_card.grid(row=1, column=0, sticky="ew", padx=0, pady=5)
        main_card.grid_columnconfigure(1, weight=1)

        ttkb.Label(main_card, text=_("源基因组:")).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.source_assembly_dropdown = ttkb.OptionMenu(main_card, self.selected_source_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ttkb.Label(main_card, text=_("目标基因组:")).grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.target_assembly_dropdown = ttkb.OptionMenu(main_card, self.selected_target_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ttkb.Label(main_card, text=_("输入区域 (Chr:Start-End):")).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.region_entry = ttkb.Entry(main_card)
        self.region_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        self.start_button = ttkb.Button(main_card, text=_("开始转换"), command=self.start_locus_conversion_task,
                                        bootstyle="success")
        self.start_button.grid(row=3, column=0, columnspan=2, padx=10, pady=(15, 20), sticky="ew")

        # 卡片2: 结果区域
        result_card = ttkb.Frame(parent, bootstyle="secondary")
        result_card.grid(row=2, column=0, sticky="nsew", padx=0, pady=10)
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        ttkb.Label(result_card, text=_("转换结果"), font=self.app.app_font_bold).grid(row=0, column=0, padx=10,
                                                                                      pady=(10, 5), sticky="w")

        # 修正 tk.Text 控件的样式获取
        text_bg = self.style.lookup('TFrame', 'background')
        text_fg = self.style.lookup('TLabel', 'foreground')
        self.result_textbox = tk.Text(result_card, state="disabled", wrap="none", font=self.app.app_font_mono,
                                      background=text_bg, foreground=text_fg, relief="flat")
        self.result_textbox.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")

    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """健壮地更新下拉菜单的值，避免销毁和重建控件。"""
        valid_ids = assembly_ids or [_("无可用基因组")]

        def update_menu(dropdown, string_var, values):
            if not (dropdown and dropdown.winfo_exists()):
                self.app.logger.warning("尝试更新一个不存在的下拉菜单。")
                return

            menu = dropdown['menu']
            menu.delete(0, 'end')

            for value in values:
                menu.add_command(label=value, command=lambda v=value, sv=string_var: sv.set(v))

            if string_var.get() not in values:
                string_var.set(values[0])

        if hasattr(self, 'source_assembly_dropdown'):
            update_menu(self.source_assembly_dropdown, self.selected_source_assembly, valid_ids)
        if hasattr(self, 'target_assembly_dropdown'):
            update_menu(self.target_assembly_dropdown, self.selected_target_assembly, valid_ids)

    def update_button_state(self, is_running, has_config):
        state = "disabled" if is_running or not has_config else "normal"
        if hasattr(self, 'start_button'):
            self.start_button.configure(state=state)

    def start_locus_conversion_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        source_assembly = self.selected_source_assembly.get()
        target_assembly = self.selected_target_assembly.get()
        region_str = self.region_entry.get().strip()

        if not all([source_assembly, target_assembly, region_str]) or _("无可用基因组") in [source_assembly,
                                                                                            target_assembly]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择源/目标基因组并输入区域。"))
            return

        try:
            chrom, pos_range = region_str.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom.strip(), start, end)
        except ValueError:
            self.app.ui_manager.show_error_message(_("输入错误"), _("区域格式不正确，请使用 'Chr:Start-End' 格式。"))
            return

        # 动态导入后端函数以避免循环依赖
        from cotton_toolkit.pipelines import run_locus_conversion
        self.app.event_handler._start_task(
            task_name=_("位点转换"),
            target_func=run_locus_conversion,
            kwargs={
                'config': self.app.current_config,
                'source_assembly_id': source_assembly,
                'target_assembly_id': target_assembly,
                'region': region_tuple,
            }
        )