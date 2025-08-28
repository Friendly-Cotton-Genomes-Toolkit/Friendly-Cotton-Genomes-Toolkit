import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, Callable, List, Any

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines import run_sequence_extraction
from .base_tab import BaseTab
from ..dialogs import MessageDialog

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class SequenceExtractionTab(BaseTab):
    """
    负责提取基因CDS序列的UI界面。
    支持单基因（直接输出）和多基因（文件输出）两种模式。
    """

    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        """
        遵循标准初始化流程：
        1. 定义所有Tkinter变量和实例属性。
        2. 调用父类 `super().__init__` 来构建基础布局。
        3. 在父类初始化完成后，安全地配置由父类创建的 action_button。
        4. 调用 update_from_config 以同步初始状态。
        """
        # 步骤1：定义所有实例变量
        self.app = app
        self.assembly_id_var = tk.StringVar()
        self.single_gene_mode_var = tk.BooleanVar(value=True)  # 默认设置为单基因模式
        self.sequence_type_var = tk.StringVar(value='cds')

        # --- 为序列分析功能定义变量 ---
        self.perform_analysis_var = tk.BooleanVar(value=False)
        self.organelle_type_var = tk.StringVar(value='nucleus')

        self.analysis_output_frame = None
        self.analysis_output_text = None
        self.copy_analysis_button = None
        self.copy_analysis_status_label = None

        # 步骤2：调用父类构造函数
        super().__init__(parent, app, translator=translator)

        # 步骤3：配置按钮
        if self.action_button:
            self.action_button.configure(text=self._("开始提取序列"), command=self.start_extraction_task)

        # --- 步骤4：刷新初始状态 ---
        self.update_from_config()
        self._toggle_analysis_options_state()
        self._toggle_analysis_output_visibility()  # 确保分析框初始状态正确

    def _create_widgets(self):
        """创建此选项卡独有的所有UI控件。"""
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 标题 ---
        ttkb.Label(parent_frame, text=_("序列提取与分析"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        # --- 输入卡片 ---
        input_card = ttkb.LabelFrame(parent_frame, text=_("输入数据"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        input_card.grid_columnconfigure(1, weight=1)

        ttkb.Label(input_card, text=_("基因组版本:"), font=self.app.app_font_bold).grid(
            row=0, column=0, sticky="w", padx=(10, 5), pady=10)
        self.assembly_dropdown = ttkb.OptionMenu(input_card, self.assembly_id_var, _("加载中..."), bootstyle="info")
        self.assembly_dropdown.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

        ttkb.Label(input_card, text=_("序列类型:"), font=self.app.app_font_bold).grid(
            row=1, column=0, sticky="w", padx=(10, 5), pady=10)

        seq_type_frame = ttkb.Frame(input_card)
        seq_type_frame.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        cds_radio = ttkb.Radiobutton(seq_type_frame, text="CDS", variable=self.sequence_type_var, value='cds',
                                     bootstyle="primary", command=self._toggle_analysis_options_state)
        cds_radio.pack(side="left", padx=(0, 15))
        protein_radio = ttkb.Radiobutton(seq_type_frame, text=_("蛋白质"), variable=self.sequence_type_var,
                                         value='protein', bootstyle="primary",
                                         command=self._toggle_analysis_options_state)
        protein_radio.pack(side="left")

        ttkb.Label(input_card, text=_("基因ID列表:"), font=self.app.app_font_bold).grid(
            row=2, column=0, sticky="nw", padx=(10, 5), pady=10)

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        self.gene_input_text = tk.Text(input_card, height=10, font=self.app.app_font_mono, wrap="word",
                                       relief="flat", background=text_bg, foreground=text_fg, insertbackground=text_fg)
        self.gene_input_text.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))

        # --- 模式选择 ---
        mode_card = ttkb.LabelFrame(parent_frame, text=_("模式选择"), bootstyle="secondary")
        mode_card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.single_gene_check = ttkb.Checkbutton(mode_card, text=_("单基因模式 (直接显示结果)"),
                                                  variable=self.single_gene_mode_var, bootstyle="round-toggle",
                                                  command=self._toggle_mode)
        self.single_gene_check.pack(side="left", padx=15, pady=10)

        # --- 分析设置卡片 ---
        self.analysis_card = ttkb.LabelFrame(parent_frame, text=_("分析设置"), bootstyle="secondary")
        self.analysis_card.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        self.analysis_card.grid_columnconfigure(1, weight=1)

        self.analysis_check = ttkb.Checkbutton(
            self.analysis_card, text=_("开启序列分析"),
            variable=self.perform_analysis_var,
            bootstyle="success-round-toggle",
            command=self._toggle_analysis_output_visibility
        )
        self.analysis_check.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        organelle_frame = ttkb.Frame(self.analysis_card)
        organelle_frame.grid(row=0, column=1, sticky="e", padx=10, pady=5)
        ttkb.Label(organelle_frame, text=_("密码子表:")).pack(side="left", padx=(0, 10))
        self.radio_nucleus = ttkb.Radiobutton(organelle_frame, text=_("细胞核 (标准)"),
                                              variable=self.organelle_type_var, value='nucleus', bootstyle="info")
        self.radio_nucleus.pack(side="left", padx=5)
        self.radio_chloro = ttkb.Radiobutton(organelle_frame, text=_("叶绿体 (质体)"), variable=self.organelle_type_var,
                                             value='chloroplast', bootstyle="info")
        self.radio_chloro.pack(side="left", padx=5)
        self.radio_mito = ttkb.Radiobutton(organelle_frame, text=_("线粒体 (标准)"), variable=self.organelle_type_var,
                                           value='mitochondria', bootstyle="info")
        self.radio_mito.pack(side="left", padx=5)

        # --- 输出卡片 ---
        self.output_card = ttkb.LabelFrame(parent_frame, text=_("输出结果"), bootstyle="secondary")
        self.output_card.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
        self.output_card.grid_columnconfigure(0, weight=1)

        # 多基因模式的输出控件
        self.multi_gene_output_frame = ttk.Frame(self.output_card)
        self.multi_gene_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.multi_gene_output_frame.grid_columnconfigure(1, weight=1)
        ttkb.Label(self.multi_gene_output_frame, text=_("输出CSV文件:"), font=self.app.app_font_bold).grid(
            row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.output_file_entry = ttk.Entry(self.multi_gene_output_frame)
        self.output_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=5)
        ttkb.Button(self.multi_gene_output_frame, text=_("另存为..."), width=12,
                    command=self._browse_save_file, bootstyle="info-outline").grid(
            row=0, column=2, padx=(0, 5), pady=5)

        # --- 单基因模式的输出控件 (分为序列和分析两个部分) ---
        self.single_gene_output_frame = ttk.Frame(self.output_card)
        self.single_gene_output_frame.grid_columnconfigure(0, weight=1)

        # --- 1. 序列结果框 ---
        seq_output_frame = ttkb.LabelFrame(self.single_gene_output_frame, text=_("序列"), bootstyle="info")
        seq_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        seq_output_frame.grid_columnconfigure(0, weight=1)

        output_text_bg = self.app.style.colors.light
        self.output_text = tk.Text(seq_output_frame, height=10, font=self.app.app_font_mono, wrap="word",
                                   state="disabled", relief="solid", bd=1, background=output_text_bg)
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        output_scrollbar = ttkb.Scrollbar(seq_output_frame, orient="vertical", command=self.output_text.yview,
                                          bootstyle="round-secondary")
        output_scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=output_scrollbar.set)

        copy_seq_frame = ttk.Frame(seq_output_frame)
        copy_seq_frame.grid(row=1, column=0, columnspan=2, sticky="e", padx=5, pady=(0, 5))
        self.copy_status_label = ttkb.Label(copy_seq_frame, text="", bootstyle="success")
        self.copy_status_label.pack(side="left", padx=(0, 10))
        self.copy_button = ttkb.Button(copy_seq_frame, text=_("复制序列"), command=self._copy_sequence_to_clipboard,
                                       bootstyle="success-outline")
        self.copy_button.pack(side="left")

        # --- 2. 分析结果框 ---
        self.analysis_output_frame = ttkb.LabelFrame(self.single_gene_output_frame, text=_("分析结果"),
                                                     bootstyle="info")
        self.analysis_output_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.analysis_output_frame.grid_columnconfigure(0, weight=1)

        self.analysis_output_text = tk.Text(self.analysis_output_frame, height=10, font=self.app.app_font_mono,
                                            wrap="word", state="disabled", relief="solid", bd=1,
                                            background=output_text_bg)
        self.analysis_output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        analysis_scrollbar = ttkb.Scrollbar(self.analysis_output_frame, orient="vertical",
                                            command=self.analysis_output_text.yview, bootstyle="round-secondary")
        analysis_scrollbar.grid(row=0, column=1, sticky="ns")
        self.analysis_output_text.configure(yscrollcommand=analysis_scrollbar.set)

        copy_analysis_frame = ttk.Frame(self.analysis_output_frame)
        copy_analysis_frame.grid(row=1, column=0, columnspan=2, sticky="e", padx=5, pady=(0, 5))
        self.copy_analysis_status_label = ttkb.Label(copy_analysis_frame, text="", bootstyle="success")
        self.copy_analysis_status_label.pack(side="left", padx=(0, 10))

        help_button = ttkb.Button(copy_analysis_frame, text=_("参数帮助"), command=self._show_parameter_help,
                                  bootstyle="info-outline")
        help_button.pack(side="left", padx=(0, 5))

        self.copy_analysis_button = ttkb.Button(copy_analysis_frame, text=_("复制分析"),
                                                command=self._copy_analysis_to_clipboard, bootstyle="success-outline")
        self.copy_analysis_button.pack(side="left")

        # --- 绑定事件和设置初始状态 ---
        self.gene_input_text.bind("<KeyRelease>", self._on_gene_input_change)
        self.gene_input_text.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.gene_input_text,
                                                                                              self._get_current_placeholder_key()))
        self.gene_input_text.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.gene_input_text,
                                                                                                self._get_current_placeholder_key()))
        self._toggle_mode()

    def _show_parameter_help(self):
        """ 显示分析参数的帮助信息弹窗。 """
        help_dialog = tk.Toplevel(self.app)
        help_dialog.title(_("分析参数说明"))
        help_dialog.transient(self.app)
        help_dialog.grab_set()
        help_dialog.resizable(False, False)

        main_frame = ttkb.Frame(help_dialog, padding=20)
        main_frame.pack(expand=True, fill="both")

        # 创建左右两个容器
        left_column = ttkb.Frame(main_frame)
        left_column.pack(side="left", fill="y", expand=True, padx=(0, 15), anchor="n")
        right_column = ttkb.Frame(main_frame)
        right_column.pack(side="left", fill="y", expand=True, padx=(15, 0), anchor="n")

        # 定义所有参数信息
        params = [
            ("GC Content (%)", self._('GC含量'), self._('指序列中G和C碱基所占的百分比。'),
             self._('【注】仅当序列类型为 CDS 时可用。')),
            ("Molecular Weight (Da)", self._('分子量'), self._('蛋白质的分子质量，单位为道尔顿(Dalton)。'),
             self._('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Isoelectric Point (pI)", self._('等电点'), self._('指蛋白质在特定pH值下净电荷为零的点。'),
             self._('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Aromaticity", self._('芳香性'), self._('蛋白质中芳香族氨基酸（Phe, Trp, Tyr）的相对频率。'),
             self._('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Instability Index", self._('不稳定性指数'),
             self._('预测蛋白质在体外的稳定性。值 > 40 通常被认为是不稳定的。'),
             self._('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("GRAVY", self._('亲疏水性总平均值'),
             self._('蛋白质中所有氨基酸残基的疏水性值的总和除以序列长度。正值表示疏水，负值表示亲水。'),
             self._('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("RSCU_Values", self._('相对同义密码子使用度'),
             self._('指一个密码子的实际使用频率与其期望频率的比值，用于衡量密码子使用的偏好性。'),
             self._('【注】仅当序列类型为 CDS 时可用。'))
        ]

        # 动态将参数分配到左右两列
        num_left = (len(params) + 1) // 2  # 计算左侧应放置的数量
        for i, (title_en, title_local, desc, note) in enumerate(params):
            target_column = left_column if i < num_left else right_column

            # 使用LabelFrame作为每个参数的容器，标题更清晰
            lf = ttkb.LabelFrame(target_column, text=f"{title_en}: {title_local}", bootstyle="info", padding=10)
            lf.pack(fill="x", pady=(0, 15), expand=True)

            # 将描述和注释合并，并设置自动换行
            full_text = f"{desc}\n{note}"
            lbl = ttkb.Label(lf, text=full_text, wraplength=320)  # 设置一个合适的换行宽度
            lbl.pack(fill="x", expand=True)

        # OK 按钮
        button_frame = ttkb.Frame(main_frame)
        button_frame.pack(fill="x", side="bottom", pady=(20, 0))
        ok_button = ttkb.Button(button_frame, text="OK", command=help_dialog.destroy, bootstyle="primary")
        ok_button.pack()

        # 居中显示窗口
        help_dialog.update_idletasks()
        screen_width = help_dialog.winfo_screenwidth()
        screen_height = help_dialog.winfo_screenheight()
        w, h = help_dialog.winfo_width(), help_dialog.winfo_height()
        x = (screen_width - w) // 2
        y = (screen_height - h) // 2
        help_dialog.geometry(f"+{x}+{y}")


    def _toggle_analysis_options_state(self):
        """ 根据序列类型（CDS或蛋白质）动态更新分析选项的状态和文本。"""
        # 对于CDS，所有分析选项均可用
        if self.sequence_type_var.get() == 'cds':
            self.analysis_check.configure(state="normal")
            self.radio_nucleus.configure(state="normal")
            self.radio_chloro.configure(state="normal")
            self.radio_mito.configure(state="normal")
            self.analysis_card.configure(text=_("分析设置"))
        # 对于蛋白质，只有“开启分析”可用，密码子表选项禁用
        else:  # protein
            self.analysis_check.configure(state="normal")
            self.radio_nucleus.configure(state="disabled")
            self.radio_chloro.configure(state="disabled")
            self.radio_mito.configure(state="disabled")
            self.analysis_card.configure(text=_("分析设置 (仅理化性质分析)"))
        # 联动更新分析结果框的可见性
        self._toggle_analysis_output_visibility()

    def _toggle_analysis_output_visibility(self):
        """ 根据模式和分析选项，显示或隐藏分析结果框。"""
        if self.analysis_output_frame:
            is_single_mode = self.single_gene_mode_var.get()
            is_analysis_on = self.perform_analysis_var.get()

            if is_single_mode and is_analysis_on:
                self.analysis_output_frame.grid()
            else:
                self.analysis_output_frame.grid_remove()

    def _toggle_mode(self):
        """根据模式切换UI，并更新占位符。"""
        # 清空所有输出
        for widget, label in [(self.output_text, self.copy_status_label),
                              (self.analysis_output_text, self.copy_analysis_status_label)]:
            if widget:
                widget.configure(state="normal")
                widget.delete("1.0", tk.END)
                widget.configure(state="disabled")
            if label:
                label.configure(text="")

        self.gene_input_text.delete("1.0", tk.END)

        if self.single_gene_mode_var.get():
            self.multi_gene_output_frame.grid_remove()
            self.single_gene_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            self.gene_input_text.configure(height=1, wrap="none")
        else:
            self.single_gene_output_frame.grid_remove()
            self.multi_gene_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            self.gene_input_text.configure(height=10, wrap="word")

        # 联动更新分析结果框的可见性
        self._toggle_analysis_output_visibility()
        key = self._get_current_placeholder_key()
        self.app.ui_manager._handle_focus_out(None, self.gene_input_text, key)
        self.app.update_idletasks()

    def _get_current_placeholder_key(self) -> str:
        """根据当前模式返回正确的占位符键。"""
        return "extract_seq_single" if self.single_gene_mode_var.get() else "extract_seq_multi"

    def _on_gene_input_change(self, event=None):
        """当基因输入框内容改变时，调用事件处理器中的自动识别函数。"""
        if not getattr(self.gene_input_text, 'is_placeholder', False):
            self.app.event_handler._auto_identify_genome_version(
                self.gene_input_text, self.assembly_id_var)

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """由主程序调用，用于更新基因组版本下拉菜单。"""
        self.app.ui_manager.update_option_menu(self.assembly_dropdown, self.assembly_id_var, assembly_ids,
                                               _("无可用基因组"))

    def _browse_save_file(self):
        """打开文件对话框以选择CSV保存位置。"""
        filepath = filedialog.asksaveasfilename(
            title=_("选择CSV文件保存位置"),
            defaultextension=".csv",
            filetypes=[(_("CSV文件"), "*.csv"), (_("所有文件"), "*.*")]
        )
        if filepath:
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, filepath)

    def _copy_to_clipboard(self, text_widget: tk.Text, status_label: ttk.Label):
        """ 通用的复制函数。"""
        content = text_widget.get("1.0", tk.END).strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            status_label.configure(text=_("复制成功!"))
            self.after(2500, lambda: status_label.configure(text=""))

    def _display_single_gene_result(self, result: Any):
        """
        在单基因模式下，将提取和分析结果显示在UI的文本框中。
        能够处理包含分析数据的新字典结构。
        """
        # 清空
        self.output_text.configure(state="normal")
        self.analysis_output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.analysis_output_text.delete("1.0", tk.END)
        self.copy_status_label.configure(text="")
        self.copy_analysis_status_label.configure(text="")

        sequence_content = ""
        analysis_content = ""

        if isinstance(result, dict) and result:
            gene_id = list(result.keys())[0]
            data = result[gene_id]

            # Case 1: 结果是包含分析的复杂字典
            if isinstance(data, dict) and 'Sequence' in data:
                # 填充序列内容
                sequence = data['Sequence']
                sequence_content += f"> {gene_id}\n"
                sequence_content += "\n".join([sequence[i:i + 80] for i in range(0, len(sequence), 80)])

                # 填充分析内容
                has_analysis = False
                for key, value in data.items():
                    if key not in ['Sequence', 'GeneID']:
                        has_analysis = True
                        if key != 'RSCU_Values':
                            analysis_content += f"{key}: {value}\n"
                # 单独处理RSCU，放在最后
                if 'RSCU_Values' in data and data['RSCU_Values']:
                    analysis_content += f"RSCU_Values: {data['RSCU_Values']}\n"

                if not has_analysis:
                    analysis_content = _("未执行分析或无分析结果。")

            # Case 2: 结果是只包含序列的简单字典 (未开启分析)
            elif isinstance(data, str):
                sequence = data
                sequence_content += f"> {gene_id}\n"
                sequence_content += "\n".join([sequence[i:i + 80] for i in range(0, len(sequence), 80)])
                analysis_content = _("分析功能未开启。")

        elif isinstance(result, str):
            sequence_content = f"{_('错误')}:\n\n{result}"
        else:
            sequence_content = _("未提取到任何序列或发生未知错误。")

        # 插入内容
        self.output_text.insert(tk.END, sequence_content.strip())
        self.analysis_output_text.insert(tk.END, analysis_content.strip())

        # 设为只读
        self.output_text.configure(state="disabled")
        self.analysis_output_text.configure(state="disabled")

    def _copy_sequence_to_clipboard(self):
        """ 只复制序列结果。"""
        self._copy_to_clipboard(self.output_text, self.copy_status_label)

    def _copy_analysis_to_clipboard(self):
        """ 只复制分析结果。"""
        self._copy_to_clipboard(self.analysis_output_text, self.copy_analysis_status_label)

    def update_from_config(self):
        """当配置重载或标签页被选中时，由主程序调用以刷新UI状态。"""
        all_assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else []
        self.update_assembly_dropdowns(all_assembly_ids)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def start_extraction_task(self):
        """点击“开始提取序列”按钮后执行的主函数。"""

        # --- 参数验证 ---
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        if getattr(self.gene_input_text, 'is_placeholder', False):
            gene_ids = []
        else:
            gene_ids_text = self.gene_input_text.get("1.0", tk.END).strip()
            gene_ids = [line.strip() for line in gene_ids_text.replace(",", "\n").splitlines() if line.strip()]

        if not gene_ids:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请输入至少一个基因ID。"))
            return

        assembly_id = self.assembly_id_var.get()
        if not assembly_id or assembly_id in [_("加载中..."), _("无可用基因组")]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择一个基因组版本。"))
            return

        is_single_mode = self.single_gene_mode_var.get()
        output_path = None

        if is_single_mode and len(gene_ids) > 1:
            self.app.ui_manager.show_warning_message(_("提示"), _("单基因模式下建议只输入一个基因ID，将只处理第一个ID。"))
            gene_ids = [gene_ids[0]]

        if not is_single_mode:
            output_path = self.output_file_entry.get().strip()
            if not output_path:
                self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定输出CSV文件的路径。"))
                return

        # --- 获取用户选择的序列类型和分析选项 ---
        sequence_type_selected = self.sequence_type_var.get()
        perform_analysis_selected = self.perform_analysis_var.get()
        organelle_type_selected = self.organelle_type_var.get()

        # --- 创建通信工具和对话框 ---
        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(_("操作取消"), _("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        dialog_title = self._("{}序列提取中").format(sequence_type_selected.upper())
        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=dialog_title,
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        # --- 准备任务参数 ---
        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids,
            'sequence_type': sequence_type_selected,
            'output_path': output_path,
            'perform_analysis': perform_analysis_selected,
            'organelle_type': organelle_type_selected,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        # --- 任务封装与启动 ---
        def task_wrapper(**kwargs):
            # 在单基因模式下，后端返回字典；在多基因模式下，返回成功或失败的消息字符串
            result = run_sequence_extraction(**kwargs)

            # 仅在单基因模式下需要更新UI文本框
            if is_single_mode:
                # 使用 self.app.after 确保UI更新在主线程中执行
                self.app.after(0, self._display_single_gene_result, result)

                # 根据结果类型判断并返回最终消息给任务处理器
                if isinstance(result, dict) and result:
                    if perform_analysis_selected:
                        return _("序列提取与分析已成功完成，结果已显示。")
                    else:
                        return _("序列已成功提取并显示在输出框中。")
                elif isinstance(result, str):  # 可能是错误消息
                    return result

            # 对于多基因模式，直接返回后端的消息字符串
            return result

        task_name_str = self._("{}序列提取").format(sequence_type_selected.upper())
        if perform_analysis_selected:
            task_name_str += self._("与分析")

        self.app.event_handler.start_task(
            task_name=task_name_str,
            target_func=task_wrapper,
            kwargs=task_kwargs
        )