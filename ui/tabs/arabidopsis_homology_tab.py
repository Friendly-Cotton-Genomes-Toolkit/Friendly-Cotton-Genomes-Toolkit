import tkinter as tk
import re  # 导入正则表达式模块
from tkinter import ttk
from typing import TYPE_CHECKING, List, Callable, Any
import threading

import pandas as pd
import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_arabidopsis_homology_conversion
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class ArabidopsisHomologyConversionTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.app = app
        self.selected_cotton_assembly = tk.StringVar()
        self.conversion_direction_var = tk.StringVar()

        self.ath_pattern = re.compile(r"^(AT[1-5MC]G\d{5}(?:\.\d+)?)$", re.IGNORECASE)

        self.single_gene_mode_var = tk.BooleanVar(value=False)

        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.action_button.configure(text=self._("开始转换"), command=self.start_conversion_task)

        self._update_direction_options()
        self.update_from_config()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        ttkb.Label(parent, text=_("棉花-拟南芥同源基因转换"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="n")
        ttkb.Label(parent, text=_("基于预处理数据库中的同源注释表，快速进行ID批量转换。"), wraplength=700,
                   justify="center").grid(
            row=1, column=0, padx=10, pady=(0, 15))

        input_card = ttkb.LabelFrame(parent, text=_("输入参数"), bootstyle="secondary")
        input_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        input_card.grid_columnconfigure(1, weight=1)
        input_card.grid_rowconfigure(4, weight=1)

        self.single_gene_switch = ttkb.Checkbutton(input_card, text=_("单基因模式"),
                                                   variable=self.single_gene_mode_var, bootstyle="round-toggle",
                                                   command=self._toggle_single_gene_mode)
        self.single_gene_switch.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        ttkb.Label(input_card, text=_("转换方向:"), font=self.app.app_font_bold).grid(
            row=1, column=0, padx=(10, 5), pady=10, sticky="w")  # <-- 修改点：行号+1
        self.direction_dropdown = ttkb.OptionMenu(input_card, self.conversion_direction_var, bootstyle="info")
        self.direction_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")  # <-- 修改点：行号+1

        ttkb.Label(input_card, text=_("棉花基因组版本:"), font=self.app.app_font_bold).grid(
            row=2, column=0, padx=(10, 5), pady=10, sticky="w")  # <-- 修改点：行号+1
        self.cotton_assembly_dropdown = ttkb.OptionMenu(input_card, self.selected_cotton_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.cotton_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")  # <-- 修改点：行号+1

        self.gene_list_label = ttkb.Label(input_card, text=_("基因ID列表:"), font=self.app.app_font_bold)
        self.gene_list_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="nw")  # <-- 修改点：行号+1

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.gene_input_textbox = tk.Text(input_card, height=15, font=self.app.app_font_mono, wrap="word",
                                          relief="flat", background=text_bg, foreground=text_fg,
                                          insertbackground=text_fg)
        self.gene_input_textbox.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10),
                                     sticky="nsew")  # <-- 修改点：行号+1

        # --- 输出卡片 ---
        self.output_card = ttkb.LabelFrame(parent, text=_("输出文件"), bootstyle="secondary")
        self.output_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        self.output_card.grid_columnconfigure(1, weight=1)

        self.output_path_label = ttkb.Label(self.output_card, text=_("输出路径:"), font=self.app.app_font_bold)
        self.output_path_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        self.output_file_entry = ttkb.Entry(self.output_card, font=self.app.app_font_mono)
        self.output_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")

        # --- 用于单基因模式的文本输出框 ---
        self.output_text_results = tk.Text(self.output_card, font=self.app.app_font_mono, height=2,
                                           relief="flat", background=text_bg,
                                           wrap="none", state="disabled",
                                           insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.output_text_results.grid(row=0, column=1, padx=0, pady=10, sticky="ew")
        self.scrollbar = ttkb.Scrollbar(self.output_card, orient="vertical", command=self.output_text_results.yview,
                                        bootstyle="round")
        self.output_text_results.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.grid(row=0, column=2, sticky="ns", pady=10, padx=(0, 5))
        self.scrollbar.grid_remove()  # 默认隐藏
        self.output_text_results.grid_remove()

        self.browse_button = ttkb.Button(self.output_card, text=_("浏览..."), width=12,
                                         command=self._browse_output_file, bootstyle="info-outline")
        self.browse_button.grid(row=0, column=3, padx=(5, 10), pady=10)  # <-- 修改点：列号改为3

        self.copy_button = ttkb.Button(self.output_card, text=_("复制"), width=12,
                                       command=self._copy_output_to_clipboard, bootstyle="info-outline")

        self.copy_success_label = ttkb.Label(self.output_card, text="", bootstyle="success")
        self.copy_success_label.grid(row=1, column=1, columnspan=3, sticky="e", padx=(0, 10))  # <-- 修改点：列合并数改为3

        self.gene_input_textbox.bind("<FocusIn>",
                                     lambda e: self.app.ui_manager._handle_focus_in(e, self.gene_input_textbox,
                                                                                    "homology_genes"))
        self.gene_input_textbox.bind("<FocusOut>",
                                     lambda e: self.app.ui_manager._handle_focus_out(e, self.gene_input_textbox,
                                                                                     "homology_genes"))
        self.gene_input_textbox.bind("<KeyRelease>", self._on_input_change)

        # --- 初始化UI状态 ---
        self._toggle_single_gene_mode()

    def _copy_output_to_clipboard(self):
        text_to_copy = self.output_text_results.get("1.0", tk.END).strip()

        if not text_to_copy or text_to_copy == self._("正在查找..."):
            return

        self.app.clipboard_clear()
        self.app.clipboard_append(text_to_copy)

        self.copy_success_label.configure(text=self._("复制成功!"))
        self.copy_success_label.after(2000, lambda: self.copy_success_label.configure(text=""))

    # --- UI切换核心逻辑 ---
    def _toggle_single_gene_mode(self):
        is_single_mode = self.single_gene_mode_var.get()
        translator = self._
        self.copy_success_label.configure(text="")

        if is_single_mode:
            self.gene_list_label.configure(text=translator("单一基因ID:"))
            self.gene_input_textbox.configure(height=1)
            self.output_card.configure(text=translator("输出内容"))
            self.output_path_label.configure(text=translator("同源基因:"))

            self.output_file_entry.grid_remove()
            self.output_text_results.grid()
            self.output_text_results.configure(height=1, state="normal")
            self.output_text_results.delete("1.0", tk.END)
            self.output_text_results.configure(state="disabled")

            self.browse_button.grid_remove()
            self.copy_button.grid(row=0, column=3, padx=(5, 10), pady=10)
        else:
            self.gene_list_label.configure(text=translator("基因ID列表:"))
            self.gene_input_textbox.configure(height=15)
            self.output_card.configure(text=translator("输出文件"))
            self.output_path_label.configure(text=translator("输出路径:"))

            self.output_text_results.grid_remove()
            self.output_file_entry.grid()

            self.copy_button.grid_remove()
            self.browse_button.grid(row=0, column=3, padx=(5, 10), pady=10)

        self.gene_input_textbox.delete("1.0", tk.END)
        self.app.ui_manager.refresh_single_placeholder(self.gene_input_textbox, "homology_genes")

    # --- 更新单基因输出结果 ---
    def _update_single_gene_output(self, result_df: pd.DataFrame):
        output_widget = self.output_text_results
        output_widget.configure(state="normal")
        output_widget.delete("1.0", tk.END)

        if result_df is not None and not result_df.empty:
            num_hits = len(result_df)
            display_height = min(num_hits, 5)
            output_widget.configure(height=display_height)

            direction = self.conversion_direction_var.get()
            if direction == self._("棉花 -> 拟南芥"):
                output_col = 'Arabidopsis_ID'
            else:
                output_col = 'Cotton_ID'

            output_lines = result_df[output_col].tolist()
            final_text = "\n".join(output_lines)
            output_widget.insert("1.0", final_text)

            if num_hits > 5:
                self.scrollbar.grid()
            else:
                self.scrollbar.grid_remove()

            self.copy_success_label.configure(text=self._("查找成功!"))
            self.copy_success_label.after(2000, lambda: self.copy_success_label.configure(text=""))
        else:
            output_widget.configure(height=1)
            output_widget.insert("1.0", self._("未找到同源基因"))
            self.scrollbar.grid_remove()

        output_widget.configure(state="disabled")


    def _on_input_change(self, event=None):
        """
        当输入框内容改变时，自动识别ID类型并相应调整UI。
        """
        gene_ids_text = self.gene_input_textbox.get("1.0", "end-1c").strip()
        if not gene_ids_text or getattr(self.gene_input_textbox, 'is_placeholder', False):
            return

        # 1. 自动识别转换方向
        lines = gene_ids_text.splitlines()
        sample_lines = [line.strip() for line in lines[:10] if line.strip()]
        if not sample_lines: return

        ath_match_count = sum(1 for line in sample_lines if self.ath_pattern.match(line))

        # 如果超过80%的样本匹配拟南芥格式，则自动切换方向
        if (ath_match_count / len(sample_lines)) > 0.8:
            self.conversion_direction_var.set(_("拟南芥 -> 棉花"))
            # 如果是拟南芥ID，则不需要进行棉花基因组的自动识别，直接返回
            return

        # 2. 如果不是拟南芥ID，则假定为棉花ID，并触发棉花基因组的自动识别
        self.app.event_handler._auto_identify_genome_version(
            gene_input_textbox=self.gene_input_textbox,
            target_assembly_var=self.selected_cotton_assembly
        )
        self.conversion_direction_var.set(_("棉花 -> 拟南芥"))




    def _update_direction_options(self):
        directions = {_("棉花 -> 拟南芥"): "cotton_to_ath", _("拟南芥 -> 棉花"): "ath_to_cotton"}
        self.app.ui_manager.update_option_menu(self.direction_dropdown, self.conversion_direction_var,
                                               list(directions.keys()))
        self.conversion_direction_var.set(_("棉花 -> 拟南芥"))


    def _browse_output_file(self):
        self.app.event_handler._browse_save_file(self.output_file_entry,
                                                 [(_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")])

    def start_conversion_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.gene_input_textbox.get("1.0", tk.END).strip()
        if not gene_ids_text or getattr(self.gene_input_textbox, 'is_placeholder', False):
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要转换的基因ID。"))
            return

        # --- 根据模式决定如何处理输入和输出 ---
        is_single_mode = self.single_gene_mode_var.get()
        if is_single_mode:
            gene_ids = [gene_ids_text.splitlines()[0].strip()]
            if not gene_ids[0]:
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入有效的基因ID。"))
                return
            output_path = None
            success_callback = self._update_single_gene_output
            dialog_title = _("正在查找同源基因...")

            # 更新UI以显示正在查找
            output_widget = self.output_text_results
            output_widget.configure(height=1, state="normal")
            output_widget.delete("1.0", tk.END)
            output_widget.insert("1.0", _("正在查找..."))
            output_widget.configure(state="disabled")
        else:
            gene_ids = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if g.strip()]
            output_path = self.output_file_entry.get().strip()
            if not output_path:
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定输出文件路径。"))
                return
            success_callback = None
            dialog_title = _("同源基因批量转换中")

        if not gene_ids:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要转换的基因ID。"))
            return

        cotton_assembly_id = self.selected_cotton_assembly.get()
        if not cotton_assembly_id or _("加载中...") in cotton_assembly_id or _(
                "无可用棉花基因组") in cotton_assembly_id:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个有效的棉花基因组版本。"))
            return

        direction_map = {_("棉花 -> 拟南芥"): "cotton_to_ath", _("拟南芥 -> 棉花"): "ath_to_cotton"}
        direction_key = direction_map.get(self.conversion_direction_var.get())
        if not direction_key:
            self.app.ui_manager.show_error_message(_("错误"), _("无效的转换方向。"))
            return

        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(_("操作取消"), _("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=dialog_title,
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': cotton_assembly_id,
            'gene_ids': gene_ids,
            'conversion_direction': direction_key,
            'output_path': output_path,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        self.app.event_handler.start_task(
            task_name=_("同源基因转换"),
            target_func=run_arabidopsis_homology_conversion,
            kwargs=task_kwargs,
            on_success=success_callback
        )

    def update_from_config(self):
        # 定义此选项卡必需的字段
        required_field = 'homology_ath_url'

        filtered_cotton_genomes = []
        if self.app.genome_sources_data:
            # 筛选出是棉花基因组且包含必需的同源文件的条目
            for asm_id, info in self.app.genome_sources_data.items():
                if info.is_cotton() and getattr(info, required_field, None):
                    filtered_cotton_genomes.append(asm_id)

        # 使用过滤后的列表更新下拉框
        self.app.ui_manager.update_option_menu(
            self.cotton_assembly_dropdown,
            self.selected_cotton_assembly,
            filtered_cotton_genomes,
            _("无可用同源数据基因组")
        )

        if not self.output_file_entry.get():
            self.output_file_entry.insert(0, "homology_conversion_results.csv")
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

