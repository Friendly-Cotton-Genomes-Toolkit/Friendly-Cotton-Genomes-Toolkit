# 文件路径: ui/tabs/genome_identifier_tab.py

import tkinter as tk
import threading
from typing import TYPE_CHECKING, Callable, Optional, Tuple, List, Set

import ttkbootstrap as ttkb

from ..dialogs import MessageDialog
from cotton_toolkit.utils.gene_utils import identify_genome_from_gene_ids
from .base_tab import BaseTab

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class GenomeIdentifierTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.action_button.configure(text=self._("开始鉴定"), command=self.start_identification_task)

        self.update_from_config()

    def _create_widgets(self):
        """
        创建支持同步滚动的UI布局。
        """
        parent_frame = self.scrollable_frame
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1, minsize=350)
        parent_frame.grid_rowconfigure(2, weight=1)

        self.title_label = ttkb.Label(parent_frame, text=_("基因组类别鉴定工具"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="n")

        self.description_label = ttkb.Label(parent_frame,
                                            text=_("在此处粘贴一个或多个基因ID（每行一个），工具将逐一鉴定它们的基因组类别。"),
                                            wraplength=700, justify='center')
        self.description_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10))

        left_frame = ttkb.LabelFrame(parent_frame, text=_("输入基因列表"), bootstyle="secondary")
        left_frame.grid(row=2, column=0, sticky="nsew", padx=(10, 0), pady=10)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        right_frame = ttkb.LabelFrame(parent_frame, text=_("鉴定结果"), bootstyle="secondary")
        right_frame.grid(row=2, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        self.scrollbar = ttkb.Scrollbar(right_frame, orient="vertical", command=self._on_scrollbar_scroll,
                                        bootstyle="round")
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=5)

        text_bg = self.app.style.lookup('TFrame', 'background')
        text_fg = self.app.style.lookup('TLabel', 'foreground')
        text_options = {
            "wrap": "word", "relief": "flat", "background": text_bg,
            "foreground": text_fg, "font": self.app.app_font_mono,
            "spacing3": 8, "yscrollcommand": self.scrollbar.set
        }

        self.gene_list_textbox = tk.Text(left_frame, **text_options)
        self.gene_list_textbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.output_textbox = tk.Text(right_frame, **text_options)
        self.output_textbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.output_textbox.configure(state="disabled")

        self.gene_list_textbox.bind("<MouseWheel>", self._on_mousewheel_scroll)
        self.output_textbox.bind("<MouseWheel>", self._on_mousewheel_scroll)

    def _on_scrollbar_scroll(self, *args):
        self.gene_list_textbox.yview(*args)
        self.output_textbox.yview(*args)

    def _on_mousewheel_scroll(self, event):
        delta = -1 if event.num == 5 or event.delta < 0 else 1
        self.gene_list_textbox.yview_scroll(delta, "units")
        self.output_textbox.yview_scroll(delta, "units")
        return "break"

    def _reset_result_display(self):
        if not hasattr(self, 'output_textbox') or not self.output_textbox.winfo_exists():
            return

        self.output_textbox.configure(state="normal")
        self.output_textbox.delete("1.0", tk.END)
        self.output_textbox.insert("1.0", self._("鉴定结果将显示在这里..."))
        self.output_textbox.configure(state="disabled", font=self.app.app_font_italic)

        if hasattr(self.app, 'style'):
            colors = self.app.style.colors
            self.output_textbox.tag_configure("success", foreground=colors.get("success"))
            self.output_textbox.tag_configure("danger", foreground=colors.get("danger"))
            self.output_textbox.tag_configure("secondary", foreground=colors.get("secondary"))

    def update_from_config(self):
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)
        if hasattr(self, 'output_textbox'):
            self._reset_result_display()

    def start_identification_task(self):
        # --- 参数验证  ---
        if not self.app.current_config or not self.app.genome_sources_data:
            self.app.ui_manager.show_error_message(self._("错误"), self._("请先加载配置文件。"))
            return

        gene_ids_text = self.gene_list_textbox.get("1.0", tk.END).strip()
        if not gene_ids_text:
            self.app.ui_manager.show_error_message(self._("输入缺失"), self._("请输入至少一个基因ID进行鉴定。"))
            return

        gene_ids = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        # --- 创建通信工具和对话框 ---
        cancel_event = threading.Event()

        def on_cancel_action():
            self.app.ui_manager.show_info_message(self._("操作取消"), self._("已发送取消请求，任务将尽快停止。"))
            cancel_event.set()

        progress_dialog = self.app.ui_manager.show_progress_dialog(
            title=self._("基因组鉴定中"),
            on_cancel=on_cancel_action
        )

        def ui_progress_updater(percentage, message):
            if progress_dialog and progress_dialog.winfo_exists():
                self.app.after(0, lambda: progress_dialog.update_progress(percentage, message))

        # --- 启动任务，并传入通信工具 ---
        task_kwargs = {
            'gene_ids': gene_ids,
            'cancel_event': cancel_event,
            'progress_callback': ui_progress_updater
        }

        self.app.event_handler.start_task(
            task_name=self._("基因组批量鉴定"),
            target_func=self._batch_identify_worker,
            kwargs=task_kwargs,
            on_success=self.handle_batch_result
        )


    def _batch_identify_worker(self, gene_ids: List[str], **kwargs) -> Tuple[List[str], Set[str]]:
        progress_callback = kwargs.get('progress_callback', lambda p, m: None)
        cancel_event = kwargs.get('cancel_event')

        genome_sources = self.app.genome_sources_data
        results = []
        unique_warnings = set()
        total_genes = len(gene_ids)

        for i, gene_id in enumerate(gene_ids):
            if cancel_event and cancel_event.is_set():
                progress_callback(100, self._("任务已取消。"))
                break

            # --- 在循环中报告进度 ---
            progress_percent = int(((i + 1) / total_genes) * 100)
            progress_callback(progress_percent, self._("正在鉴定 {}/{}...").format(i + 1, total_genes))

            result_tuple = identify_genome_from_gene_ids(
                gene_ids=[gene_id],
                genome_sources=genome_sources,
                cancel_event=cancel_event
            )

            if result_tuple:
                assembly_id, warning, score = result_tuple
                result_line = f"{gene_id}\t→\t{assembly_id} ({score:.1f}%)"
                results.append(result_line)
                if warning:
                    unique_warnings.add(warning)
            else:
                result_line = f"{gene_id}\t→\t{self._('未能识别')}"
                results.append(result_line)

        return results, unique_warnings


    def handle_batch_result(self, result_data: Tuple[List[str], Set[str]]):
        result_lines, warnings = result_data
        self.output_textbox.configure(state="normal")
        self.output_textbox.delete("1.0", tk.END)
        for line in result_lines:
            if self._("未能识别") in line:
                self.output_textbox.insert(tk.END, line, "danger")
            else:
                self.output_textbox.insert(tk.END, line, "success")
            self.output_textbox.insert(tk.END, "\n")
        self.output_textbox.configure(state="disabled")
        if warnings:
            warning_message = list(warnings)[0]
            MessageDialog(
                parent=self.app,
                title=self._("注意：检测到歧义"),
                message=self._(warning_message),
                icon_type="warning"
            )