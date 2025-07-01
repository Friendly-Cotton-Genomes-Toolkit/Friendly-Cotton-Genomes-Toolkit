# ui/tabs/locus_conversion_tab.py
import os
import tkinter as tk
from tkinter import ttk, font as tkfont # 导入 ttk 和 tkfont
import ttkbootstrap as ttkb # 导入 ttkbootstrap
from ttkbootstrap.constants import * # 导入 ttkbootstrap 常量

from typing import TYPE_CHECKING, List

from cotton_toolkit.config.loader import get_local_downloaded_file_path
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class LocusConversionTab(BaseTab): # Assuming BaseTab is also converted to ttkbootstrap
    def __init__(self, parent, app: "CottonToolkitApp"):

        self.selected_source_assembly = tk.StringVar()
        self.selected_target_assembly = tk.StringVar()

        super().__init__(parent, app) # Pass app to BaseTab to access its style/fonts


    def _create_widgets(self):
        parent_frame = self.scrollable_frame
        parent_frame.grid_rowconfigure(2, weight=1)
        parent_frame.grid_columnconfigure(0, weight=1)

        # Access fonts directly from self.app
        font_regular = self.app.app_font
        font_bold = self.app.app_font_bold
        font_title = self.app.app_title_font
        font_mono = self.app.app_font_mono # Use the monospace font

        ttk.Label(parent_frame, text=_("位点坐标转换"), font=font_title,
                  foreground=self.app.style.colors.primary).grid(row=0, column=0, pady=(5, 10), padx=10, sticky="n")

        main_card = ttk.Frame(parent_frame, style='Card.TFrame') # Use a themed frame style for cards if desired
        main_card.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        main_card.grid_columnconfigure(1, weight=1)

        ttk.Label(main_card, text=_("源基因组:"), font=font_regular).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.source_assembly_dropdown = ttkb.OptionMenu(main_card, self.selected_source_assembly,
                                                        _("加载中..."),  # 默认值
                                                        *[_("加载中...")],  # 选项列表
                                                        bootstyle="info")
        self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ttk.Label(main_card, text=_("目标基因组:"), font=font_regular).grid(row=1, column=0, padx=15, pady=10, sticky="w")
        # 修复：ttkb.OptionMenu 不支持直接的 font 参数
        self.target_assembly_dropdown = ttkb.OptionMenu(main_card, self.selected_target_assembly,
                                                        _("加载中..."),  # 默认值
                                                        *[_("加载中...")],  # 选项列表
                                                        bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ttk.Label(main_card, text=_("输入区域 (Chr:Start-End):"), font=font_regular).grid(row=2, column=0, padx=15, pady=10, sticky="w")
        self.region_entry = ttk.Entry(main_card, font=font_regular)
        self.region_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # 修复：ttkb.Button 不支持直接的 font 参数
        self.start_button = ttkb.Button(main_card, text=_("开始转换"), command=self.start_locus_conversion_task,
                                        bootstyle="success")
        self.start_button.grid(row=3, column=0, columnspan=2, padx=10, pady=(15, 20), sticky="ew")

        result_card = ttk.Frame(parent_frame, style='Card.TFrame')
        result_card.grid(row=2, column=0, sticky="nsew", padx=5, pady=10)
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        ttk.Label(result_card, text=_("转换结果"), font=font_bold).grid(row=0, column=0, padx=10, pady=(10,5), sticky="w")

        # Use tk.Text for result display
        # 修复：tk.Text 的背景色和前景色通过 style.lookup 获取
        self.result_textbox = tk.Text(result_card, state="disabled", wrap="none", font=font_mono,
                                      background=self.app.style.lookup('TText', 'background'),
                                      foreground=self.app.style.lookup('TText', 'foreground'),
                                      relief="flat")
        self.result_textbox.grid(row=1, column=0, padx=10, pady=(5,10), sticky="nsew")


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        if not assembly_ids: assembly_ids = [_("无可用基因组")] # Changed from "加载中..." to "无可用基因组" for clarity

        # Auxiliary function: destroy and recreate OptionMenu
        def recreate_option_menu(old_dropdown, variable, new_values, default_row, default_column, **kwargs_for_grid_pack):
            # Check if old_dropdown exists and is a valid widget BEFORE trying to get info
            if old_dropdown is None or not old_dropdown.winfo_exists():
                # This is the initial creation or after a full destruction.
                # The dropdown needs to be created from scratch.
                parent_frame = self.scrollable_frame # Or direct parent if known
                new_dropdown = ttkb.OptionMenu(
                    parent_frame,
                    variable,
                    new_values[0] if new_values else "", # Set initial value safely
                    *new_values,
                    command=kwargs_for_grid_pack.pop('command', None), # Pass command explicitly
                    bootstyle="info", # Default bootstyle if not retrieved
                )
                new_dropdown.grid(row=default_row, column=default_column, **kwargs_for_grid_pack)
                return new_dropdown

            parent_frame = old_dropdown.master
            grid_info = {}
            pack_info = {}
            manager_type = None

            # Get layout info BEFORE destroying
            if hasattr(old_dropdown, 'winfo_manager'):
                manager_type = old_dropdown.winfo_manager()
                if manager_type == "grid":
                    grid_info = old_dropdown.grid_info()
                elif manager_type == "pack":
                    pack_info = old_dropdown.pack_info()

            # The command from ttkb.OptionMenu should be stored or known, not cgetted reliably
            command = old_dropdown.cget('command') if 'command' in old_dropdown.configure() else None
            bootstyle = old_dropdown.cget('bootstyle')

            old_dropdown.destroy()

            if variable.get() not in new_values:
                variable.set(new_values[0] if new_values else "") # Set initial value safely

            new_dropdown = ttkb.OptionMenu(
                parent_frame,
                variable,
                variable.get(),
                *new_values,
                command=command,
                bootstyle=bootstyle
            )

            # Reapply layout
            if manager_type == "grid" and grid_info:
                new_dropdown.grid(**{k: v for k, v in grid_info.items() if k != 'in'})
            elif manager_type == "pack" and pack_info:
                new_dropdown.pack(**{k: v for k, v in pack_info.items() if k != 'in'})
            else:
                # Fallback if no valid layout info was found (e.g., widget not yet laid out)
                new_dropdown.grid(row=default_row, column=default_column, sticky="ew", padx=10, pady=10)

            return new_dropdown

        # Ensure the initial dropdown creation in _create_widgets sets the correct values
        # For LocusConversionTab:
        # self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        # self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Recreate source assembly dropdown
        self.source_assembly_dropdown = recreate_option_menu(
            self.source_assembly_dropdown,
            self.selected_source_assembly,
            assembly_ids,
            default_row=0, default_column=1, # Default grid positions
            padx=10, pady=10, sticky="ew"
        )

        # Recreate target assembly dropdown
        self.target_assembly_dropdown = recreate_option_menu(
            self.target_assembly_dropdown,
            self.selected_target_assembly,
            assembly_ids,
            default_row=1, default_column=1, # Default grid positions
            padx=10, pady=10, sticky="ew"
        )

        # Ensure the StringVar is updated after recreation
        if assembly_ids:
            if self.selected_source_assembly.get() not in assembly_ids:
                self.selected_source_assembly.set(assembly_ids[0])
            if self.selected_target_assembly.get() not in assembly_ids:
                self.selected_target_assembly.set(assembly_ids[0])
        else:
            self.selected_source_assembly.set(_("无可用基因组"))
            self.selected_target_assembly.set(_("无可用基因组"))


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

        if not all([source_assembly, target_assembly, region_str]):
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择源/目标基因组并输入区域。"))
            return

        try:
            chrom, pos_range = region_str.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom.strip(), start, end)
        except ValueError:
            self.app.ui_manager.show_error_message(_("输入错误"), _("区域格式不正确，请使用 'Chr:Start-End' 格式。"))
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