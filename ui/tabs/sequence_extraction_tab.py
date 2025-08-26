import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, Callable, List, Any

import ttkbootstrap as ttkb

from cotton_toolkit.pipelines.seqence_query import run_sequence_extraction
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    # Fallback for environments where the translator is not globally set
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

        # 步骤2：调用父类构造函数
        super().__init__(parent, app, translator=translator)

        # 步骤3：配置按钮
        if self.action_button:
            self.action_button.configure(text=self._("开始提取序列"), command=self.start_extraction_task)

        # 步骤4：刷新初始状态
        self.update_from_config()

    def _create_widgets(self):
        """创建此选项卡独有的所有UI控件。"""
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)

        # --- 标题 ---
        ttkb.Label(parent_frame, text=_("序列提取"), font=self.app.app_title_font, bootstyle="primary").grid(
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
                                     bootstyle="primary")
        cds_radio.pack(side="left", padx=(0, 15))
        protein_radio = ttkb.Radiobutton(seq_type_frame, text=_("蛋白质"), variable=self.sequence_type_var,
                                         value='protein', bootstyle="primary")
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
        self.single_gene_check = ttkb.Checkbutton(mode_card, text=_("单基因模式 (直接显示FASTA结果)"),
                                                  variable=self.single_gene_mode_var, bootstyle="round-toggle",
                                                  command=self._toggle_mode)
        self.single_gene_check.pack(side="left", padx=15, pady=10)

        # --- 输出卡片 ---
        self.output_card = ttkb.LabelFrame(parent_frame, text=_("输出设置"), bootstyle="secondary")
        self.output_card.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
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

        # --- 单基因模式的输出控件 (核心修改区域) ---
        self.single_gene_output_frame = ttk.Frame(self.output_card)
        self.single_gene_output_frame.grid_columnconfigure(0, weight=1)
        self.single_gene_output_frame.grid_rowconfigure(0, weight=1)

        # 1. 为结果文本框和滚动条创建一个容器
        output_text_frame = ttk.Frame(self.single_gene_output_frame)
        output_text_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        output_text_frame.grid_columnconfigure(0, weight=1)
        output_text_frame.grid_rowconfigure(0, weight=1)

        # 2. 创建结果文本框，并设置淡灰色背景
        # 使用 self.app.style.colors.light 来获取当前主题下的浅灰色，确保深色模式下也能适配
        output_text_bg = self.app.style.colors.light
        self.output_text = tk.Text(output_text_frame, height=10, font=self.app.app_font_mono, wrap="word",
                                   state="disabled", relief="solid", bd=1, background=output_text_bg)
        self.output_text.grid(row=0, column=0, sticky="nsew")

        # 3. 创建滚动条并与文本框关联
        output_scrollbar = ttkb.Scrollbar(output_text_frame, orient="vertical", command=self.output_text.yview,
                                          bootstyle="round-secondary")
        output_scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=output_scrollbar.set)

        # 4. 创建复制按钮和状态标签的容器
        copy_frame = ttk.Frame(self.single_gene_output_frame)
        copy_frame.grid(row=1, column=0, sticky="e", padx=5, pady=(0, 5))

        # 5. 创建用于显示“复制成功”的标签，初始为空
        self.copy_status_label = ttkb.Label(copy_frame, text="", bootstyle="success")
        self.copy_status_label.pack(side="left", padx=(0, 10))

        # 6. 创建复制按钮
        self.copy_button = ttkb.Button(copy_frame, text=_("复制结果"),
                                       command=self._copy_to_clipboard, bootstyle="success-outline")
        self.copy_button.pack(side="left")

        # --- 绑定事件和设置初始状态 ---
        self.gene_input_text.bind("<KeyRelease>", self._on_gene_input_change)
        self.gene_input_text.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.gene_input_text,
                                                                                              self._get_current_placeholder_key()))
        self.gene_input_text.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.gene_input_text,
                                                                                                self._get_current_placeholder_key()))

        self._toggle_mode()

    def _toggle_mode(self):
        """根据模式切换UI，并更新占位符。"""
        self.gene_input_text.delete("1.0", tk.END)
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.configure(state="disabled")
        self.copy_status_label.configure(text="")  # 切换模式时清空状态

        if self.single_gene_mode_var.get():
            self.multi_gene_output_frame.grid_remove()
            self.single_gene_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            self.gene_input_text.configure(height=1, wrap="none")
        else:
            self.single_gene_output_frame.grid_remove()
            self.multi_gene_output_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            self.gene_input_text.configure(height=10, wrap="word")

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

    def _copy_to_clipboard(self):
        """将单基因模式下的FASTA结果复制到剪贴板，并显示临时状态。"""
        content = self.output_text.get("1.0", tk.END).strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)

            # --- 核心修改：不再弹窗，而是更新标签文本 ---
            self.copy_status_label.configure(text=_("复制成功!"))
            # 2.5秒后自动清除提示文字
            self.after(2500, lambda: self.copy_status_label.configure(text=""))

    def _display_single_gene_result(self, result: Any):
        """在单基因模式下，将提取结果显示在UI的文本框中。"""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.copy_status_label.configure(text="")  # 新结果显示时清空状态

        if isinstance(result, dict) and result:
            fasta_str = ""
            for gene_id, sequence in result.items():
                fasta_str += f">{gene_id}\n"
                fasta_str += "\n".join([sequence[i:i + 80] for i in range(0, len(sequence), 80)])
                fasta_str += "\n\n"
            self.output_text.insert(tk.END, fasta_str.strip())
        elif isinstance(result, str):
            self.output_text.insert(tk.END, f"{_('错误')}:\n\n{result}")
        else:
            self.output_text.insert(tk.END, _("未提取到任何序列或发生未知错误。"))

        self.output_text.configure(state="disabled")

    def update_from_config(self):
        """当配置重载或标签页被选中时，由主程序调用以刷新UI状态。"""
        all_assembly_ids = list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else []
        self.update_assembly_dropdowns(all_assembly_ids)
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def start_extraction_task(self):
        """点击“开始提取序列”按钮后执行的主函数。"""

        # --- 参数验证---
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

        # 获取用户选择的序列类型
        sequence_type_selected = self.sequence_type_var.get()

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

        # --- 准备任务参数 (加入通信工具) ---
        task_kwargs = {
            'config': self.app.current_config,
            'assembly_id': assembly_id,
            'gene_ids': gene_ids,
            'sequence_type': sequence_type_selected,
            'output_path': output_path,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        def task_wrapper(**kwargs):
            result = run_sequence_extraction(**kwargs)
            if is_single_mode:
                self.app.after(0, self._display_single_gene_result, result)
                if isinstance(result, dict) and result:
                    return _("序列已成功提取并显示在输出框中。")
                elif isinstance(result, str):
                    return result
            return result

        task_name_str = self._("{}序列提取").format(sequence_type_selected.upper())
        self.app.event_handler.start_task(
            task_name=task_name_str,
            target_func=task_wrapper,
            kwargs=task_kwargs
        )

