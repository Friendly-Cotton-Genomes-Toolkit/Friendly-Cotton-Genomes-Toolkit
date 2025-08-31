import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable
import threading
import ttkbootstrap as ttkb

from cotton_toolkit.pipelines.quantification import run_expression_normalization
from .base_tab import BaseTab
from ..dialogs import HelpDialogSheet

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 国际化函数 (i18n) 占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class QuantificationTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.selected_normalization_method = tk.StringVar(value="tpm")  # 默认选择 tpm
        self.counts_file_path = tk.StringVar()
        self.lengths_file_path = tk.StringVar()
        self.output_file_path = tk.StringVar()

        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            # 修改主操作按钮的文本和命令
            self.action_button.configure(text=self._("开始标准化"), command=self._start_quantification_task)

        # 从配置更新UI状态（例如按钮是否可用）
        self.update_from_config()

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        self.title_label = ttkb.Label(parent, text=_("表达量标准化"), font=self.app.app_title_font, bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="n")

        description_text = _(
            "本工具用于将基因的原始读数(Raw Counts)转换为标准化的表达量单位(TPM, FPKM, RPKM)。\n\n"
            "【适用范围】: 主要适用于标准的批量RNA测序(Bulk RNA-seq)数据。\n"
            "【不适用】: 该标准化方法不推荐直接用于单细胞RNA测序(scRNA-seq)，"
            "因其数据稀疏性需要更专门的算法(如SCTransform, Linnorm等)。"
        )
        self.description_label = ttkb.Label(parent, text=description_text, wraplength=700, justify="left",
                                            bootstyle="info")
        self.description_label.grid(row=1, column=0, padx=10, pady=(0, 15), sticky="ew")

        self.input_card = ttkb.LabelFrame(parent, text=_("输入与参数"), bootstyle="secondary")
        self.input_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        # 调整列权重以容纳新按钮
        self.input_card.grid_columnconfigure(1, weight=1)

        # 1. 原始计数文件
        self.counts_file_label = ttkb.Label(self.input_card, text=_("原始计数文件:"), font=self.app.app_font_bold)
        self.counts_file_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.counts_file_entry = ttkb.Entry(self.input_card, textvariable=self.counts_file_path,
                                            font=self.app.app_font_mono)
        self.counts_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")

        # 将浏览按钮和帮助按钮放在一个 Frame 中
        counts_buttons_frame = ttkb.Frame(self.input_card)
        counts_buttons_frame.grid(row=0, column=2, padx=(5, 10), pady=5)
        self.browse_counts_button = ttkb.Button(counts_buttons_frame, text=_("浏览..."), width=10,
                                                command=self._browse_counts_file, bootstyle="info-outline")
        self.browse_counts_button.pack(side="left", padx=(0, 5))
        # 帮助按钮
        self.help_counts_button = ttkb.Button(counts_buttons_frame, text="?", width=2,
                                              command=self._show_counts_help, bootstyle="secondary-outline")
        self.help_counts_button.pack(side="left")

        # 2. 基因长度文件
        self.lengths_file_label = ttkb.Label(self.input_card, text=_("基因长度文件:"), font=self.app.app_font_bold)
        self.lengths_file_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.lengths_file_entry = ttkb.Entry(self.input_card, textvariable=self.lengths_file_path,
                                             font=self.app.app_font_mono)
        self.lengths_file_entry.grid(row=1, column=1, padx=0, pady=10, sticky="ew")

        # 将浏览按钮和帮助按钮放在一个 Frame 中
        lengths_buttons_frame = ttkb.Frame(self.input_card)
        lengths_buttons_frame.grid(row=1, column=2, padx=(5, 10), pady=5)
        self.browse_lengths_button = ttkb.Button(lengths_buttons_frame, text=_("浏览..."), width=10,
                                                 command=self._browse_lengths_file, bootstyle="info-outline")
        self.browse_lengths_button.pack(side="left", padx=(0, 5))
        # 帮助按钮
        self.help_lengths_button = ttkb.Button(lengths_buttons_frame, text="?", width=2,
                                               command=self._show_lengths_help, bootstyle="secondary-outline")
        self.help_lengths_button.pack(side="left")

        # 3. 标准化方法选择
        self.method_label = ttkb.Label(self.input_card, text=_("标准化方法:"), font=self.app.app_font_bold)
        self.method_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")

        method_frame = ttkb.Frame(self.input_card)
        method_frame.grid(row=2, column=1, columnspan=2, padx=(0, 10), pady=5, sticky="w")

        tpm_radio = ttkb.Radiobutton(method_frame, text="TPM", variable=self.selected_normalization_method, value="tpm")
        tpm_radio.pack(side="left", padx=(0, 15))
        fpkm_radio = ttkb.Radiobutton(method_frame, text="FPKM", variable=self.selected_normalization_method,
                                      value="fpkm")
        fpkm_radio.pack(side="left", padx=(0, 15))
        rpkm_radio = ttkb.Radiobutton(method_frame, text="RPKM", variable=self.selected_normalization_method,
                                      value="rpkm")
        rpkm_radio.pack(side="left")

        # --- 输出卡片 ---
        self.output_card = ttkb.LabelFrame(parent, text=_("输出"), bootstyle="secondary")
        self.output_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        self.output_card.grid_columnconfigure(1, weight=1)

        self.output_path_label = ttkb.Label(self.output_card, text=_("输出路径:"), font=self.app.app_font_bold)
        self.output_path_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.output_file_entry = ttkb.Entry(self.output_card, textvariable=self.output_file_path,
                                            font=self.app.app_font_mono)
        self.output_file_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")
        self.browse_output_button = ttkb.Button(self.output_card, text=_("浏览..."), width=12,
                                                command=self._browse_output_file, bootstyle="info-outline")
        self.browse_output_button.grid(row=0, column=2, padx=(5, 10), pady=10)

    def _show_counts_help(self):
        title = _("原始计数文件格式说明")
        message = _("""这是一个CSV或制表符分隔的文本文件。\n
        •\u00A0第一列必须是基因ID。
        •\u00A0第一行必须是表头，包含 gene_id 和每个样本的名称。
        •\u00A0文件的分隔符（如逗号、制表符等）会被自动识别。""")

        headers = ["gene_id", "Sample_A", "Sample_B", "Sample_C"]
        data = [
            ["Gohir.A01G000100", "150", "205", "175"],
            ["Gohir.A01G000200", "0", "10", "5"],
            ["Gohir.A01G000300", "1200", "1543", "1380"],
            ["...", "...", "...", "..."]
        ]
        HelpDialogSheet(self, title, message, headers, data)

    # 显示基因长度文件帮助的函数
    def _show_lengths_help(self):
        title = _("基因长度文件格式说明")
        message = _("""这是一个包含两列的CSV或制表符分隔的文本文件，\n
        •\u00A0第一行是表头，固定为 gene_id 和 length。
        •\u00A0第一列是基因ID，必须与计数文件中的ID格式完全对应。
        •\u00A0第二列是该基因的长度，单位为碱基对(bp)。""")

        headers = ["gene_id", "length"]
        data = [
            ["Gohir.A01G000100", "2500"],
            ["Gohir.A01G000200", "1350"],
            ["Gohir.A01G000300", "4210"],
            ["...", "..."]
        ]
        HelpDialogSheet(self, title, message, headers, data)

    def _browse_counts_file(self):
        self._browse_input_file(self.counts_file_path, _("选择原始计数文件"))

    def _browse_lengths_file(self):
        self._browse_input_file(self.lengths_file_path, _("选择基因长度文件"))

    def _browse_input_file(self, string_var: tk.StringVar, title: str):
        file_types = [
            (_("文本文件 (CSV, TXT)"), "*.csv *.txt *.tsv"),
            (_("所有文件"), "*.*")
        ]
        file_path = filedialog.askopenfilename(title=title, filetypes=file_types)
        if file_path:
            string_var.set(file_path)

    def _browse_output_file(self):
        # 复用 app.event_handler 中的通用保存文件对话框
        self.app.event_handler._browse_save_file(
            self.output_file_entry,
            [(_("CSV 文件"), "*.csv"), (_("所有文件"), "*.*")]
        )

    def _start_quantification_task(self):
        """
        启动后端表达量标准化任务的函数。
        """
        # 1. 参数验证
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        counts_path = self.counts_file_path.get().strip()
        lengths_path = self.lengths_file_path.get().strip()
        output_path = self.output_file_path.get().strip()

        # 从UI的StringVar变量中获取用户当前选择的方法
        method = self.selected_normalization_method.get()

        if not all([counts_path, lengths_path, output_path]):
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请提供所有必需的文件路径。"))
            return

        # 2. 创建通信工具和对话框
        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(_("操作取消"), _("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=_("正在进行表达量标准化..."),
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        # 3. 准备传递给后台任务的参数
        task_kwargs = {
            'counts_file_path': counts_path,
            'gene_lengths_file_path': lengths_path,
            'output_path': output_path,
            'normalization_method': method,
            'max_workers': self.app.current_config.downloader.max_workers,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        # 4. 使用 event_handler 启动后台任务
        self.app.event_handler.start_task(
            task_name=_("表达量标准化"),
            target_func=run_expression_normalization,
            kwargs=task_kwargs
        )

    def update_from_config(self):
        """当配置加载或标签页激活时调用"""
        # 根据是否存在配置来更新按钮状态
        self.update_button_state(
            self.app.active_task_name is not None,
            self.app.current_config is not None
        )
        if self.app.current_config and not self.output_file_path.get():
            self.output_file_path.set("expression_results.csv")
