# 文件路径: ui/tabs/blast_tab.py
# 【已优化和注释版】
import os
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, List, Callable, Any

import ttkbootstrap as ttkb
from ttkbootstrap.tooltip import ToolTip

from cotton_toolkit.config.loader import get_local_downloaded_file_path
from cotton_toolkit.pipelines import run_blast_pipeline
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class BlastTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.selected_blast_type = tk.StringVar(value="blastn")
        self.selected_target_assembly = tk.StringVar()
        self.input_mode_var = tk.StringVar(value="text")

        # 【新增】添加一个跟踪事件，当 blast 类型改变时调用新方法
        self.selected_blast_type.trace_add("write", self._on_blast_type_change)

        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.action_button.configure(text=self._("执行 BLAST"), command=self._start_blast_task)

        self._toggle_input_mode()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        self.title_label = ttkb.Label(parent, text=_("本地 BLAST"), font=self.app.app_title_font, bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        self.input_card = ttkb.LabelFrame(parent, text=_("输入与参数"), bootstyle="secondary")
        self.input_card.grid(row=1, column=0, sticky="new", padx=10, pady=5)
        self.input_card.grid_columnconfigure(1, weight=1)

        self.blast_type_label = ttkb.Label(self.input_card, text=_("BLAST 类型:"), font=self.app.app_font_bold)
        self.blast_type_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.blast_type_dropdown = ttkb.OptionMenu(self.input_card, self.selected_blast_type, "blastn",
                                                   "blastn", "blastp", "blastx", "tblastn", bootstyle="info")
        self.blast_type_dropdown.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")

        self.target_genome_label = ttkb.Label(self.input_card, text=_("目标棉花基因组:"),
                                              font=self.app.app_font_bold)  # 文本已修改
        self.target_genome_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.target_assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_target_assembly,
                                                        _("加载中..."), bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        input_mode_frame = ttkb.Frame(self.input_card)
        input_mode_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky='w')
        self.text_input_radio = ttkb.Radiobutton(input_mode_frame, text=_("粘贴序列"), variable=self.input_mode_var,
                                                 value="text", command=self._toggle_input_mode)
        self.text_input_radio.pack(side="left", padx=(0, 10))
        self.file_input_radio = ttkb.Radiobutton(input_mode_frame, text=_("文件输入"), variable=self.input_mode_var,
                                                 value="file", command=self._toggle_input_mode)
        self.file_input_radio.pack(side="left")

        self.text_input_frame = ttkb.Frame(self.input_card)
        self.text_input_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")
        self.text_input_frame.grid_columnconfigure(0, weight=1)
        self.text_input_frame.grid_rowconfigure(0, weight=1)

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.query_textbox = tk.Text(self.text_input_frame, height=10, font=self.app.app_font_mono, wrap="word",
                                     relief="flat", background=text_bg, foreground=text_fg, insertbackground=text_fg)
        self.query_textbox.grid(row=0, column=0, sticky="nsew")
        self.app.ui_manager.add_placeholder(self.query_textbox, self.app.placeholders.get('blast',''))
        self.query_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e,
                                                                                                      self.query_textbox,
                                                                                                      "blast"))
        self.query_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e,
                                                                                                        self.query_textbox,
                                                                                                        "blast"))


        self.file_input_frame = ttkb.Frame(self.input_card)
        self.file_input_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.file_input_frame.grid_columnconfigure(0, weight=1)

        self.query_file_entry = ttkb.Entry(self.file_input_frame, font=self.app.app_font_mono)
        self.query_file_entry.grid(row=0, column=0, padx=0, pady=5, sticky="ew")
        self.browse_query_button = ttkb.Button(self.file_input_frame, text=_("浏览..."), width=12,
                                               command=self._browse_query_file, bootstyle="info-outline")
        self.browse_query_button.grid(row=0, column=1, padx=(5, 0), pady=5)

        # --- 其他参数 ---
        params_frame = ttkb.Frame(self.input_card)
        params_frame.grid(row=4, column=0, columnspan=2, sticky='ew')
        params_frame.grid_columnconfigure((1, 3, 5), weight=1)

        # --- E-value ---
        self.evalue_label = ttkb.Label(params_frame, text=_("E-value:"), font=self.app.app_font_bold)
        self.evalue_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky='w')
        self.evalue_entry = ttkb.Entry(params_frame, width=12)
        self.evalue_entry.insert(0, "1e-5")
        self.evalue_entry.grid(row=0, column=1, padx=(0, 10), pady=5, sticky='ew')
        # 【新增】为 E-value 添加悬浮注释
        ToolTip(self.evalue_label, text=_(
            "期望值(E-value)衡量匹配的统计显著性。\n值越小，匹配结果越有意义，偶然匹配的可能性越低。\n例如: 1e-10 比 1e-5 更严格。"))
        ToolTip(self.evalue_entry, text=_(
            "期望值(E-value)衡量匹配的统计显著性。\n值越小，匹配结果越有意义，偶然匹配的可能性越低。\n例如: 1e-10 比 1e-5 更严格。"))

        # --- Word Size ---
        self.word_size_label = ttkb.Label(params_frame, text=_("Word Size:"), font=self.app.app_font_bold)
        self.word_size_label.grid(row=0, column=2, padx=(10, 5), pady=5, sticky='w')
        self.word_size_entry = ttkb.Entry(params_frame, width=12)
        self.word_size_entry.insert(0, "11")
        self.word_size_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky='ew')
        # 【新增】为 Word Size 添加悬浮注释
        ToolTip(self.word_size_label, text=_(
            "初始匹配的种子序列长度。\n对于核酸(blastn)，增大此值可加快速度但可能降低灵敏度。\n对于蛋白(blastp)，默认值通常为3。"))
        ToolTip(self.word_size_entry, text=_(
            "初始匹配的种子序列长度。\n对于核酸(blastn)，增大此值可加快速度但可能降低灵敏度。\n对于蛋白(blastp)，默认值通常为3。"))

        # --- Max Hits ---
        self.max_seqs_label = ttkb.Label(params_frame, text=_("Max Hits:"), font=self.app.app_font_bold)
        self.max_seqs_label.grid(row=0, column=4, padx=(10, 5), pady=5, sticky='w')
        self.max_seqs_entry = ttkb.Entry(params_frame, width=12)
        self.max_seqs_entry.insert(0, "500")
        self.max_seqs_entry.grid(row=0, column=5, padx=(0, 10), pady=5, sticky='ew')
        # 【新增】为 Max Hits 添加悬浮注释
        ToolTip(self.max_seqs_label, text=_(
            "在最终结果中显示的最大匹配序列数量。\n用于控制输出结果的大小，防止因匹配项过多而导致结果文件过大。"))
        ToolTip(self.max_seqs_entry, text=_(
            "在最终结果中显示的最大匹配序列数量。\n用于控制输出结果的大小，防止因匹配项过多而导致结果文件过大。"))


        self.output_card = ttkb.LabelFrame(parent, text=_("输出"), bootstyle="secondary")
        self.output_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        self.output_card.grid_columnconfigure(0, weight=1)

        self.output_entry = ttkb.Entry(self.output_card, font=self.app.app_font_mono)
        self.output_entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.browse_output_button = ttkb.Button(self.output_card, text=_("浏览..."), width=12,
                                                command=self._browse_output_file, bootstyle="info-outline")
        self.browse_output_button.grid(row=0, column=1, padx=(0, 10), pady=10)

    def _toggle_input_mode(self):
        if self.input_mode_var.get() == "text":
            self.file_input_frame.grid_remove()
            self.text_input_frame.grid()
        else:
            self.text_input_frame.grid_remove()
            self.file_input_frame.grid()

    def _browse_query_file(self):
        file_types = [
            (_("序列文件"), "*.fasta *.fa *.fastq *.fq *.txt"),
            (_("所有文件"), "*.*")
        ]
        file_path = filedialog.askopenfilename(title=_("选择查询序列文件"), filetypes=file_types)
        if file_path:
            self.query_file_entry.delete(0, tk.END)
            self.query_file_entry.insert(0, file_path)

    def _browse_output_file(self):
        self.app.event_handler._browse_save_file(self.output_entry,
                                                 [(_("Excel 文件"), "*.xlsx"), (_("CSV 文件"), "*.csv")])

    def _start_blast_task(self):
        # --- 【修改】添加文件可用性检查 ---
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        target_assembly = self.selected_target_assembly.get()
        blast_type = self.selected_blast_type.get()

        if not target_assembly or _("加载中...") in target_assembly or _("无可用基因组") in target_assembly or _(
                "无可用棉花基因组") in target_assembly:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个有效的目标棉花基因组。"))
            return

        # 1. 确定需要哪种序列文件 (CDS 或 Protein)
        db_type = 'prot' if blast_type in ['blastp', 'blastx'] else 'nucl'
        required_key = 'predicted_protein' if db_type == 'prot' else 'predicted_cds'

        # 2. 检查该基因组版本是否提供此文件
        genome_info = self.app.genome_sources_data.get(target_assembly)
        url_attr = f"{required_key}_url"

        if not genome_info or not hasattr(genome_info, url_attr) or not getattr(genome_info, url_attr):
            msg = self._("基因组版本 '{}' 不支持 '{}'，因为它缺少必需的 '{}' 数据源。").format(
                target_assembly, blast_type, required_key
            )
            self.app.ui_manager.show_error_message(_("数据不支持"), msg)
            return

        # 3. 检查文件是否已下载
        required_file_path = get_local_downloaded_file_path(self.app.current_config, genome_info, required_key)
        if not required_file_path or not os.path.exists(required_file_path):
            msg = self._("执行 '{}' 所需的文件 '{}' 尚未下载。\n\n请前往“数据下载”选项卡下载该文件。").format(
                blast_type, os.path.basename(getattr(genome_info, url_attr))
            )
            self.app.ui_manager.show_warning_message(_("缺少文件"), msg)
            return

        query_file = self.query_file_entry.get().strip()
        query_text = self.query_textbox.get("1.0", tk.END).strip()

        if self.input_mode_var.get() == 'file' and not query_file:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个查询文件。"))
            return
        if self.input_mode_var.get() == 'text' and not query_text:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请粘贴查询序列。"))
            return
        if self.input_mode_var.get() == 'file' and query_text:  # 只在文件模式下检查双重输入
            self.app.ui_manager.show_error_message(_("输入冲突"), _("检测到文件输入和文本输入同时存在，请清除其中一个。"))
            return

        output_path = self.output_entry.get().strip()
        if not output_path:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定输出文件路径。"))
            return

        try:
            params = {
                "evalue": float(self.evalue_entry.get()),
                "word_size": int(self.word_size_entry.get()),
                "max_target_seqs": int(self.max_seqs_entry.get()),
            }
        except (ValueError, TypeError):
            self.app.ui_manager.show_error_message(_("输入错误"), _("参数设置中的值必须是有效的数字。"))
            return

        self.app.event_handler._start_task(
            task_name=_("本地 BLAST"),
            target_func=run_blast_pipeline,
            kwargs={
                'config': self.app.current_config,
                'blast_type': self.selected_blast_type.get(),
                'target_assembly_id': target_assembly,
                'query_file_path': query_file if self.input_mode_var.get() == 'file' else None,
                'query_text': query_text if self.input_mode_var.get() == 'text' else None,
                'output_path': output_path,
                **params
            }
        )

    def _on_blast_type_change(self, *args):
        blast_type = self.selected_blast_type.get()
        # blastn 的推荐默认值为 11
        if blast_type == 'blastn':
            new_word_size = "11"
        # blastp, blastx, tblastn 的推荐默认值为 3
        else:
            new_word_size = "3"

        # 检查输入框是否存在
        if hasattr(self, 'word_size_entry') and self.word_size_entry.winfo_exists():
            self.word_size_entry.delete(0, tk.END)
            self.word_size_entry.insert(0, new_word_size)


    def retranslate_ui(self, translator: Callable[[str], str]):
        self._ = translator
        self.title_label.configure(text=translator("本地 BLAST"))
        if self.action_button:
            self.action_button.configure(text=translator("执行 BLAST"))
        self.input_card.configure(text=translator("输入与参数"))
        self.blast_type_label.configure(text=translator("BLAST 类型:"))
        self.target_genome_label.configure(text=translator("目标棉花基因组:"))
        self.text_input_radio.configure(text=translator("粘贴序列"))
        self.file_input_radio.configure(text=translator("文件输入"))
        self.browse_query_button.configure(text=translator("浏览..."))
        self.evalue_label.configure(text=translator("E-value:"))
        self.word_size_label.configure(text=translator("Word Size:"))
        self.max_seqs_label.configure(text=translator("Max Hits:"))
        self.output_card.configure(text=translator("输出"))
        self.browse_output_button.configure(text=translator("浏览..."))

        all_assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else []
        self.update_assembly_dropdowns(all_assembly_ids)

    def update_from_config(self):
        """当标签页被选中或配置重载时调用，负责刷新此标签页的UI状态。"""

        # 【同步修正】: 在调用时，传递一个符合约定的参数
        all_assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else []
        self.update_assembly_dropdowns(all_assembly_ids)

        # 以下逻辑保持不变
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

        if self.app.current_config and not self.output_entry.get():
            self.output_entry.insert(0, "blast_results.xlsx")


    # 【核心修改】 重写此方法以实现棉花基因组的筛选
    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """
        从主程序获取所有基因组源，筛选出棉花基因组，并更新目标数据库下拉菜单。
        注意：此方法会忽略传入的 assembly_ids 参数，执行自己独立的筛选逻辑。
        """
        genome_data = self.app.genome_sources_data

        if not genome_data:
            valid_ids = [self._("无可用基因组")]
        else:
            # 筛选出 genome_type 为 'cotton' 的条目（此逻辑不变）
            cotton_genome_ids = [
                assembly_id
                for assembly_id, source_item in genome_data.items()
                if source_item.is_cotton()
            ]
            valid_ids = cotton_genome_ids or [self._("无可用棉花基因组")]

        # 使用UI管理器的通用函数来更新OptionMenu（此逻辑不变）
        self.app.ui_manager.update_option_menu(
            dropdown=self.target_assembly_dropdown,
            string_var=self.selected_target_assembly,
            new_values=valid_ids
        )