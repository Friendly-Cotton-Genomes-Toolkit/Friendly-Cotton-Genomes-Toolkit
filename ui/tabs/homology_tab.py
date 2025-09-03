# 文件路径: ui/tabs/homology_tab.py

import tkinter as tk
from typing import TYPE_CHECKING, List, Callable, Any
import threading
import pandas as pd
import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_homology_mapping
from .base_tab import BaseTab
from .. import MessageDialog

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class HomologyTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.homology_strict_priority_var = tk.BooleanVar(value=True)
        self.single_gene_mode_var = tk.BooleanVar(value=False)

        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.action_button.configure(text=self._("开始转换"), command=self._start_homology_task)
        self.update_from_config()
        # 在单基因模式切换逻辑中处理复制按钮的可见性

    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        """
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        # --- 储存 UI 元件 ---
        self.title_label = ttkb.Label(parent, text=_("快速基因同源转换"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="n")

        self.description_label = ttkb.Label(parent, text=_(
            "该工具通过动态BLASTN搜索，快速查找一个或多个源基因在目标基因组中的同源基因。\n"
            "此工具旨在快速批量获取，如需要更高的精准度，请使用 “本地BLAST” 工具"),
                                            wraplength=700, justify="center")
        self.description_label.grid(row=1, column=0, padx=10, pady=(0, 15))

        self.input_card = ttkb.LabelFrame(parent, text=_("输入"), bootstyle="secondary")
        self.input_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        self.input_card.grid_columnconfigure(1, weight=1)
        self.input_card.grid_rowconfigure(3, weight=1)

        self.source_genome_label = ttkb.Label(self.input_card, text=_("源基因组:"), font=self.app.app_font_bold)
        self.source_genome_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.source_assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_homology_source_assembly,
                                                        _("加载中..."), bootstyle="info")
        self.source_assembly_dropdown.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")

        self.target_genome_label = ttkb.Label(self.input_card, text=_("目标基因组:"), font=self.app.app_font_bold)
        self.target_genome_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.target_assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_homology_target_assembly,
                                                        _("加载中..."), bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        self.gene_list_label = ttkb.Label(self.input_card, text=_("基因ID列表:"), font=self.app.app_font_bold)
        self.gene_list_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="nw")

        text_bg = self.app.style.lookup('TFrame', 'background')
        self.homology_map_genes_textbox = tk.Text(self.input_card, height=10, font=self.app.app_font_mono, wrap="word",
                                                  relief="flat", background=text_bg,
                                                  insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.homology_map_genes_textbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

        self.homology_map_genes_textbox.after(10, lambda: self.app.ui_manager.add_placeholder(
            self.homology_map_genes_textbox,
            self.app.placeholders.get("homology_genes", "...")
        ))

        self.homology_map_genes_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                         self.homology_map_genes_textbox,
                                                                                                         "homology_genes"))
        self.homology_map_genes_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                           self.homology_map_genes_textbox,
                                                                                                           "homology_genes"))
        self.homology_map_genes_textbox.bind("<KeyRelease>", self._on_homology_gene_input_change)

        self.params_card = ttkb.LabelFrame(parent, text=_("参数设置"), bootstyle="secondary")
        self.params_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        self.params_card.grid_columnconfigure((1, 3), weight=1)

        self.single_gene_switch = ttkb.Checkbutton(self.params_card, text=_("单基因模式"),
                                                   variable=self.single_gene_mode_var, bootstyle="round-toggle",
                                                   command=self._toggle_single_gene_mode)
        self.single_gene_switch.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        self.strict_switch = ttkb.Checkbutton(self.params_card, text=_("严格匹配模式 (同源亚组内优先)"),
                                              variable=self.homology_strict_priority_var, bootstyle="round-toggle")
        self.strict_switch.grid(row=0, column=2, columnspan=2, padx=10, pady=10, sticky="w")

        self.top_n_label = ttkb.Label(self.params_card, text=_("Top N:"), font=self.app.app_font_bold)
        self.pid_label = ttkb.Label(self.params_card, text=_("PID (%):"), font=self.app.app_font_bold)
        self.evalue_label = ttkb.Label(self.params_card, text=_("E-value:"), font=self.app.app_font_bold)
        self.score_label = ttkb.Label(self.params_card, text=_("Score:"), font=self.app.app_font_bold)

        def create_param_entry(p, label_widget, default_val, r, c):
            label_widget.grid(row=r, column=c * 2, padx=(10, 5), pady=5, sticky="w")
            entry = ttkb.Entry(p, width=15, font=self.app.app_font_mono)
            entry.insert(0, default_val)
            entry.grid(row=r, column=c * 2 + 1, padx=(0, 10), pady=5, sticky="ew")
            return entry

        self.homology_top_n_entry = create_param_entry(self.params_card, self.top_n_label, "10", 1, 0)
        self.homology_evalue_entry = create_param_entry(self.params_card, self.evalue_label, "1e-10", 1, 1)
        self.homology_pid_entry = create_param_entry(self.params_card, self.pid_label, "30.0", 2, 0)
        self.homology_score_entry = create_param_entry(self.params_card, self.score_label, "50.0", 2, 1)

        self.output_card = ttkb.LabelFrame(parent, text=_("输出文件 (可选)"), bootstyle="secondary")
        self.output_card.grid(row=4, column=0, sticky="new", padx=10, pady=5)
        self.output_card.grid_columnconfigure(1, weight=1)

        self.output_path_label = ttkb.Label(self.output_card, text=_("输出路径:"), font=self.app.app_font_bold)
        self.output_path_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        self.homology_output_file_entry = ttkb.Entry(self.output_card, font=self.app.app_font_mono)
        self.homology_output_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")

        self.homology_output_text_results = tk.Text(self.output_card, font=self.app.app_font_mono, height=2,
                                                    relief="flat", background=text_bg,
                                                    wrap="none", state="disabled",
                                                    insertbackground=self.app.style.lookup('TLabel', 'foreground'))
        self.homology_output_text_results.grid(row=0, column=1, padx=0, pady=10, sticky="ew")

        self.scrollbar = ttkb.Scrollbar(self.output_card, orient="vertical",
                                        command=self.homology_output_text_results.yview, bootstyle="round")
        self.homology_output_text_results.configure(yscrollcommand=self.scrollbar.set)

        # 将滚动条放置在文本框右侧，默认隐藏
        self.scrollbar.grid(row=0, column=2, sticky="ns", pady=10, padx=(0, 5))
        self.scrollbar.grid_remove()

        self.homology_output_text_results.grid_remove()  # 默认隐藏

        self.browse_button = ttkb.Button(self.output_card, text=_("浏览..."), width=12,
                                         command=self._browse_output_file, bootstyle="info-outline")
        self.browse_button.grid(row=0, column=2, padx=(5, 10), pady=10)

        self.copy_button = ttkb.Button(self.output_card, text=_("复制"), width=12,
                                       command=self._copy_output_to_clipboard, bootstyle="info-outline")

        self.copy_success_label = ttkb.Label(self.output_card, text="", bootstyle="success")
        self.copy_success_label.grid(row=1, column=1, columnspan=2, sticky="e", padx=(0, 10))

        self._toggle_single_gene_mode()

    def _copy_output_to_clipboard(self):
        is_single_mode = self.single_gene_mode_var.get()

        if is_single_mode:
            text_to_copy = self.homology_output_text_results.get("1.0", tk.END).strip()
        else:
            text_to_copy = self.homology_output_file_entry.get()

        if not text_to_copy or text_to_copy == self._("正在查找..."):
            return

        self.app.clipboard_clear()
        self.app.clipboard_append(text_to_copy)

        self.copy_success_label.configure(text=self._("复制成功!"))
        self.copy_success_label.after(2000, lambda: self.copy_success_label.configure(text=""))


    def _toggle_single_gene_mode(self):
        is_single_mode = self.single_gene_mode_var.get()
        translator = self._

        self.copy_success_label.configure(text="")

        # 这一部分会清空输入框并始终将其值设为 "10"，表示默认值
        self.homology_top_n_entry.delete(0, tk.END)
        self.homology_top_n_entry.insert(0, "10")

        if is_single_mode:
            # 确保此区域内没有其他设置 self.homology_top_n_entry 值的代码
            self.gene_list_label.configure(text=translator("单一基因ID:"))
            self.homology_map_genes_textbox.configure(height=1)
            self.output_card.configure(text=translator("输出内容"))
            self.output_path_label.configure(text=translator("同源基因:"))
            # 隐藏文件输入框，显示文本结果框
            self.homology_output_file_entry.grid_remove()
            self.homology_output_text_results.grid()
            self.homology_output_text_results.configure(height=1, state="normal")
            self.homology_output_text_results.delete("1.0", tk.END)
            self.homology_output_text_results.configure(state="disabled")

            self.browse_button.grid_remove()
            self.copy_button.grid(row=0, column=3, padx=(5, 10), pady=10)
        else:
            # 确保此区域内没有其他设置 self.homology_top_n_entry 值的代码
            self.gene_list_label.configure(text=translator("基因ID列表:"))
            self.homology_map_genes_textbox.configure(height=10)
            self.output_card.configure(text=translator("输出文件 (可选)"))
            self.output_path_label.configure(text=translator("输出路径:"))
            # 隐藏文本结果框，显示文件输入框
            self.homology_output_text_results.grid_remove()
            self.homology_output_file_entry.grid()
            self.homology_output_file_entry.configure(state="normal")
            self.homology_output_file_entry.delete(0, tk.END)
            if self.app.current_config:
                self.homology_output_file_entry.insert(0, "homology_results.xlsx")

            self.copy_button.grid_remove()
            self.browse_button.grid(row=0, column=3, padx=(5, 10), pady=10)

        self.homology_map_genes_textbox.delete("1.0", tk.END)
        self.app.ui_manager.refresh_single_placeholder(self.homology_map_genes_textbox, "homology_genes")

        if is_single_mode:
            self.homology_output_file_entry.configure(state="normal")
            self.homology_output_file_entry.delete(0, tk.END)
            self.homology_output_file_entry.configure(state="readonly")
        else:
            self.homology_output_file_entry.delete(0, tk.END)
            if self.app.current_config:
                self.homology_output_file_entry.insert(0, "homology_results.xlsx")


    def _browse_output_file(self):
        self.app.event_handler._browse_save_file(self.homology_output_file_entry,
                                                 [(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv"),
                                                  (_("所有文件"), "*.*")])

    def _update_single_gene_output(self, result_df: pd.DataFrame):
        """
        解析BLAST结果DataFrame，支持多行显示，并动态调整输出框高度和滚动条。
        """
        output_widget = self.homology_output_text_results
        output_widget.configure(state="normal")
        output_widget.delete("1.0", tk.END)

        if result_df is not None and not result_df.empty:
            num_hits = len(result_df)
            # 动态调整文本框高度，最多5行
            display_height = min(num_hits, 5)
            output_widget.configure(height=display_height)

            output_lines = []
            for index, row in result_df.iterrows():
                hit_gene = row.get('Hit_ID', 'N/A')
                try:
                    identity = float(row.get('Identity (%)', 0))
                except (ValueError, TypeError):
                    identity = 0.0
                e_value = row.get('E-value', 0)
                # 格式化每行结果
                line = f"{hit_gene} (PID: {identity:.2f}%, E-value: {e_value:.2e})"
                output_lines.append(line)

            # 将所有行合并为一个字符串，用换行符分隔
            final_text = "\n".join(output_lines)
            output_widget.insert("1.0", final_text)

            # 根据结果数量显示/隐藏滚动条
            if num_hits > 5:
                self.scrollbar.grid()
            else:
                self.scrollbar.grid_remove()

            self.copy_success_label.configure(text=self._("查找成功!"))
            self.copy_success_label.after(2000, lambda: self.copy_success_label.configure(text=""))
        else:
            output_widget.configure(height=1) # 未找到结果时，高度设为1
            output_widget.insert("1.0", self._("未找到同源基因"))
            self.scrollbar.grid_remove()
            MessageDialog(
                parent=self.app,
                title=self._("查询无结果"),
                message=self._("未能根据当前筛选条件找到任何匹配的同源基因。"),
                icon_type="info"
            )

        output_widget.configure(state="disabled") # 设置为只读



    def _start_homology_task(self):
        # --- 参数验证 ---
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        gene_ids_text = self.homology_map_genes_textbox.get("1.0", tk.END).strip()
        is_placeholder = getattr(self.homology_map_genes_textbox, 'is_placeholder', False)
        if not gene_ids_text or is_placeholder:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"))
            return

        is_single_mode = self.single_gene_mode_var.get()
        if is_single_mode:
            gene_ids = [gene_ids_text.splitlines()[0].strip()]
            if not gene_ids[0]:
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入有效的基因ID。"))
                return
        else:
            gene_ids = [g.strip() for g in gene_ids_text.replace(",", "\n").splitlines() if g.strip()]

        if not gene_ids:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"))
            return

        source_assembly = self.selected_homology_source_assembly.get()
        target_assembly = self.selected_homology_target_assembly.get()
        if not all([source_assembly, target_assembly]) or _("加载中...") in [source_assembly, target_assembly] or _(
                "无可用基因组") in [source_assembly, target_assembly]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择有效的源和目标基因组。"))
            return

        try:
            criteria = {
                "top_n": int(self.homology_top_n_entry.get()),
                "evalue_threshold": float(self.homology_evalue_entry.get()),
                "pid_threshold": float(self.homology_pid_entry.get()),
                "score_threshold": float(self.homology_score_entry.get()),
                "strict_subgenome_priority": self.homology_strict_priority_var.get()
            }
        except (ValueError, TypeError):
            self.app.ui_manager.show_error_message(_("输入错误"), _("参数设置中的阈值必须是有效的数字。"))
            return


        # 根据模式决定成功回调和对话框标题
        if is_single_mode:
            success_callback = self._update_single_gene_output
            dialog_title = _("正在查找同源基因...")
            output_path = None
            output_widget = self.homology_output_text_results
            output_widget.configure(height=1, state="normal")
            output_widget.delete("1.0", tk.END)
            output_widget.insert("1.0", _("正在查找..."))
            output_widget.configure(state="disabled")

        else:
            success_callback = None
            dialog_title = _("同源基因批量转换中")
            output_path = self.homology_output_file_entry.get().strip() or None


        task_kwargs = {
            'config': self.app.current_config,
            'source_assembly_id': source_assembly,
            'target_assembly_id': target_assembly,
            'gene_ids': gene_ids,
            'region': None,
            'output_csv_path': output_path,
            'criteria_overrides': criteria,
        }


        self._start_task(
            task_name=dialog_title,
            target_func=run_homology_mapping,
            kwargs=task_kwargs,
            on_success=success_callback
        )


    def update_from_config(self):
        if self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        # 定义此功能必需的字段（BLASTN基于CDS）
        required_fields = ['predicted_cds_url', 'predicted_protein_url']

        all_genomes_data = self.app.genome_sources_data
        filtered_ids = []

        if all_genomes_data:
            for assembly_id in assembly_ids:
                genome_item = all_genomes_data.get(assembly_id)
                if not genome_item:
                    continue

                # 检查是否包含所有必需的序列文件
                if all(getattr(genome_item, field, None) for field in required_fields):
                    filtered_ids.append(assembly_id)

        valid_ids = filtered_ids or [_("无可用基因组")]

        # 使用过滤后的列表更新源和目标两个下拉框
        self.app.ui_manager.update_option_menu(self.source_assembly_dropdown, self.selected_homology_source_assembly,
                                               valid_ids)
        self.app.ui_manager.update_option_menu(self.target_assembly_dropdown, self.selected_homology_target_assembly,
                                               valid_ids)


    def _on_homology_gene_input_change(self, event=None):
        self.app.event_handler._auto_identify_genome_version(self.homology_map_genes_textbox,
                                                             self.selected_homology_source_assembly)