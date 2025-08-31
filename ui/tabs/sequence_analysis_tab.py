import threading
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Any

import ttkbootstrap as ttkb

from .base_tab import BaseTab
from cotton_toolkit.pipelines import run_seq_analysis

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)




class SeqAnalysisTab(BaseTab):
    """
    A tab for directly analyzing FASTA sequences provided via text or file.
    The UI is modeled after the BlastTab for a consistent user experience.
    """

    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        self.input_mode_var = tk.StringVar(value="text")
        self.sequence_type_var = tk.StringVar(value='cds')
        self.perform_analysis_var = tk.BooleanVar(value=True)  # Default to ON
        self.organelle_type_var = tk.StringVar(value='nucleus')

        super().__init__(parent, app, translator)

        if self.action_button:
            self.action_button.configure(text=self._("开始分析"), command=self.start_analysis_task)

        # Initial UI state setup
        self._toggle_input_mode()
        self._toggle_analysis_options_state()

    def _show_parameter_help(self):
        """ 显示分析参数的帮助信息弹窗。 """
        help_dialog = tk.Toplevel(self.app)
        help_dialog.title(_("分析参数说明"))
        help_dialog.transient(self.app)
        help_dialog.grab_set()
        help_dialog.resizable(False, False)

        # --- 绑定ESC键到关闭窗口的函数 ---
        help_dialog.bind('<Escape>', lambda e: help_dialog.destroy())

        main_frame = ttkb.Frame(help_dialog, padding=20)
        main_frame.pack(expand=True, fill="both")

        # --- 创建一个容器专门放参数说明，以便按钮可以独立布局 ---
        content_frame = ttkb.Frame(main_frame)
        content_frame.pack(side="top", fill="both", expand=True)

        # 创建左右两个容器
        left_column = ttkb.Frame(content_frame)
        left_column.pack(side="left", fill="y", expand=True, padx=(0, 15), anchor="n")
        right_column = ttkb.Frame(content_frame)
        right_column.pack(side="left", fill="y", expand=True, padx=(15, 0), anchor="n")

        # 定义所有参数信息
        params = [
            ("GC Content (%)", _('GC含量'), _('指序列中G和C碱基所占的百分比。'),
             _('【注】仅当序列类型为 CDS 时可用。')),
            ("Molecular Weight (Da)", _('分子量'), _('蛋白质的分子质量，单位为道尔顿(Dalton)。'),
             _('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Isoelectric Point (pI)", _('等电点'), _('指蛋白质在特定pH值下净电荷为零的点。'),
             _('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Aromaticity", _('芳香性'), _('蛋白质中芳香族氨基酸（Phe, Trp, Tyr）的相对频率。'),
             _('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("Instability Index", _('不稳定性指数'),
             _('预测蛋白质在体外的稳定性。值 > 40 通常被认为是不稳定的。此指标可用于比较同源基因在环境适应性上的差异。'),
             _('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("GRAVY", _('亲疏水性总平均值'),
             _('蛋白质中所有氨基酸残基的疏水性值的总和除以序列长度。正值表示疏水（可能为膜蛋白），负值表示亲水。'),
             _('【注】CDS序列会先翻译成蛋白质再计算。')),
            ("RSCU_Values", _('相对同义密码子使用度'),
             _('指一个密码子的实际使用频率与其期望频率的比值，用于衡量密码子使用的偏好性，这与基因在宿主中的表达效率有关。'),
             _('【注】仅当序列类型为 CDS 时可用。'))
        ]

        # 动态将参数分配到左右两列
        num_left = (len(params) + 1) // 2
        for i, (title_en, title_local, desc, note) in enumerate(params):
            target_column = left_column if i < num_left else right_column

            lf = ttkb.LabelFrame(target_column, text=f"{title_en}: {title_local}", bootstyle="info", padding=10)
            lf.pack(fill="x", pady=(0, 15), expand=True)

            full_text = f"{desc}\n{note}"
            lbl = ttkb.Label(lf, text=full_text, wraplength=320)
            lbl.pack(fill="x", expand=True)

        ok_button = ttkb.Button(main_frame, text="OK", command=help_dialog.destroy, bootstyle="primary")
        ok_button.pack(side="bottom", pady=(20, 0))  # pack 在底部，它会自动水平居中

        # 居中显示窗口
        help_dialog.update_idletasks()
        screen_width = help_dialog.winfo_screenwidth()
        screen_height = help_dialog.winfo_screenheight()
        w, h = help_dialog.winfo_width(), help_dialog.winfo_height()
        x = (screen_width - w) // 2
        y = (screen_height - h) // 2
        help_dialog.geometry(f"+{x}+{y}")

        # 让窗口成为焦点，以便接收键盘事件
        help_dialog.focus_set()


    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        # --- Title ---
        ttkb.Label(parent, text=_("序列分析"), font=self.app.app_title_font, bootstyle="primary").grid(
            row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        # --- Input Card (like BlastTab) ---
        input_card = ttkb.LabelFrame(parent, text=_("输入数据"), bootstyle="secondary")
        input_card.grid(row=1, column=0, sticky="new", padx=10, pady=5)
        input_card.grid_columnconfigure(0, weight=1)

        input_mode_frame = ttkb.Frame(input_card)
        input_mode_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky='w')
        ttkb.Radiobutton(input_mode_frame, text=_("粘贴序列"), variable=self.input_mode_var,
                         value="text", command=self._toggle_input_mode).pack(side="left", padx=(0, 10))
        ttkb.Radiobutton(input_mode_frame, text=_("文件输入"), variable=self.input_mode_var,
                         value="file", command=self._toggle_input_mode).pack(side="left")

        # Text input frame
        self.text_input_frame = ttkb.Frame(input_card)
        self.text_input_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.text_input_frame.grid_columnconfigure(0, weight=1)
        self.query_textbox = tk.Text(self.text_input_frame, height=10, font=self.app.app_font_mono, wrap="word")
        self.query_textbox.grid(row=0, column=0, sticky="nsew")
        self.query_textbox.bind("<FocusIn>", lambda e: self.app.ui_manager._handle_focus_in(e, self.query_textbox,
                                                                                            "seq_analysis_placeholder"))

        self.query_textbox.bind("<FocusOut>", lambda e: self.app.ui_manager._handle_focus_out(e, self.query_textbox,
                                                                                              "seq_analysis_placeholder"))

        # File input frame
        self.file_input_frame = ttkb.Frame(input_card)
        self.file_input_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.file_input_frame.grid_columnconfigure(0, weight=1)
        self.query_file_entry = ttkb.Entry(self.file_input_frame, font=self.app.app_font_mono)
        self.query_file_entry.grid(row=0, column=0, padx=0, pady=5, sticky="ew")
        ttkb.Button(self.file_input_frame, text=_("浏览..."), width=12,
                    command=self._browse_query_file, bootstyle="info-outline").grid(row=0, column=1, padx=(5, 0),
                                                                                    pady=5)

        # --- Analysis Settings Card ---
        self.analysis_card = ttkb.LabelFrame(parent, text=_("分析设置"), bootstyle="secondary")
        self.analysis_card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.analysis_card.grid_columnconfigure(1, weight=1)

        help_button = ttkb.Button(self.analysis_card, text="?", command=self._show_parameter_help,
                                  bootstyle="info-outline", width=2)
        help_button.place(relx=1.0, x=-5, y=-8, anchor="ne")

        # Sequence Type Selection
        seq_type_frame = ttkb.Frame(self.analysis_card)
        seq_type_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ttkb.Label(seq_type_frame, text=_("序列类型:"), font=self.app.app_font_bold).pack(side="left", padx=(0, 10))
        ttkb.Radiobutton(seq_type_frame, text="CDS", variable=self.sequence_type_var, value='cds',
                         bootstyle="primary", command=self._toggle_analysis_options_state).pack(side="left", padx=5)
        ttkb.Radiobutton(seq_type_frame, text=_("蛋白质"), variable=self.sequence_type_var, value='protein',
                         bootstyle="primary", command=self._toggle_analysis_options_state).pack(side="left", padx=5)

        # Codon Table Selection
        self.organelle_frame = ttkb.Frame(self.analysis_card)
        self.organelle_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ttkb.Label(self.organelle_frame, text=_("密码子表:"), font=self.app.app_font_bold).pack(side="left",
                                                                                                padx=(0, 10))
        self.radio_nucleus = ttkb.Radiobutton(self.organelle_frame, text=_("细胞核 (标准)"),
                                              variable=self.organelle_type_var, value='nucleus', bootstyle="info")
        self.radio_nucleus.pack(side="left", padx=5)
        self.radio_chloro = ttkb.Radiobutton(self.organelle_frame, text=_("叶绿体 (质体)"),
                                             variable=self.organelle_type_var, value='chloroplast', bootstyle="info")
        self.radio_chloro.pack(side="left", padx=5)
        self.radio_mito = ttkb.Radiobutton(self.organelle_frame, text=_("线粒体 (标准)"),
                                           variable=self.organelle_type_var, value='mitochondria', bootstyle="info")
        self.radio_mito.pack(side="left", padx=5)

        # --- Output Card ---
        output_card = ttkb.LabelFrame(parent, text=_("输出文件"), bootstyle="secondary")
        output_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        output_card.grid_columnconfigure(0, weight=1)

        file_output_frame = ttkb.Frame(output_card)
        file_output_frame.pack(fill="x", padx=10, pady=10)
        file_output_frame.grid_columnconfigure(1, weight=1)
        ttkb.Label(file_output_frame, text=_("输出文件路径:")).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.output_entry = ttkb.Entry(file_output_frame, font=self.app.app_font_mono)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        ttkb.Button(file_output_frame, text=_("浏览..."), width=12,
                    command=lambda: self.app.event_handler._browse_save_file(self.output_entry,
                                                                             [(_("Excel 文件"), "*.xlsx")]),
                    bootstyle="info-outline").grid(row=0, column=2, padx=(5, 0))



    def _toggle_input_mode(self):
        if self.input_mode_var.get() == "text":
            self.file_input_frame.grid_remove()
            self.text_input_frame.grid()
        else:
            self.text_input_frame.grid_remove()
            self.file_input_frame.grid()

    def _browse_query_file(self):
        path = filedialog.askopenfilename(title=_("选择FASTA文件"),
                                          filetypes=[("FASTA", "*.fasta *.fa *.txt"), ("All files", "*.*")])
        if path:
            self.query_file_entry.delete(0, tk.END)
            self.query_file_entry.insert(0, path)

    def _toggle_analysis_options_state(self):
        if self.sequence_type_var.get() == 'cds':
            for child in self.organelle_frame.winfo_children():
                child.configure(state="normal")
        else:  # protein
            for child in self.organelle_frame.winfo_children():
                child.configure(state="disabled")

    def start_analysis_task(self):
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("配置文件未加载。"))
            return

        fasta_text, fasta_file = None, None
        if self.input_mode_var.get() == 'text':
            if not getattr(self.query_textbox, 'is_placeholder', False):
                fasta_text = self.query_textbox.get("1.0", tk.END).strip()
        else:  # file
            fasta_file = self.query_file_entry.get().strip()

        if not fasta_text and not fasta_file:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请粘贴FASTA序列或选择一个文件。"))
            return

        output_path = self.output_entry.get().strip()
        if not output_path:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请指定输出文件的路径。"))
            return


        cancel_event = threading.Event()
        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=_("序列分析中"),
            on_cancel=lambda: cancel_event.set()
        )

        def ui_progress_updater(p, m):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(p, m))

        task_kwargs = {
            'config': self.app.current_config,
            'fasta_text': fasta_text,
            'fasta_file_path': fasta_file,
            'sequence_type': self.sequence_type_var.get(),
            'organelle_type': self.organelle_type_var.get(),
            'perform_analysis': self.perform_analysis_var.get(),
            'output_path': output_path,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        def task_wrapper(**kwargs):
            return run_seq_analysis(**kwargs)


        self.app.event_handler.start_task(
            task_name=_("FASTA序列分析"),
            target_func=task_wrapper,
            kwargs=task_kwargs
        )



    # This can be inherited, but defining it explicitly is fine too.
    def update_from_config(self):
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)
        self.app.ui_manager.refresh_all_placeholder_styles()
        self.app.ui_manager.refresh_single_placeholder(self.query_textbox, "seq_analysis_placeholder")

