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

        # --- 【最终修正】 ---
        # 通过 self.action_button.master 安全地获取按钮的父容器
        if self.action_button:
            self.action_button.configure(text=self._("开始鉴定"), command=self.start_identification_task)

            # 1. 安全地获取 action_frame
            action_frame = self.action_button.master

            # 2. 对获取到的 frame 进行重新布局
            action_frame.grid_forget()  # 从BaseTab的默认位置移除
            action_frame.grid(row=3, column=0, columnspan=2, sticky="s", pady=(10, 0))  # 放到新布局的底部

            # 3. 配置按钮在 frame 内居中
            if not action_frame.winfo_manager() == 'pack':
                # 如果父容器不是pack布局，确保按钮在grid中正确配置
                action_frame.grid_columnconfigure(0, weight=1)
                self.action_button.grid(row=0, column=0, pady=5)
            else:
                self.action_button.pack(pady=5)  # 保持pack布局
        # --- 修正结束 ---

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

    def retranslate_ui(self, translator: Callable[[str], str]):
        self._ = translator
        self.title_label.configure(text=translator("基因组类别鉴定工具"))
        self.description_label.configure(
            text=translator("在此处粘贴一个或多个基因ID（每行一个），工具将逐一鉴定它们的归属。"))

        for child in self.scrollable_frame.winfo_children():
            if isinstance(child, ttkb.LabelFrame):
                if child.grid_info().get('column') == 0:
                    child.configure(text=translator("输入基因列表"))
                elif child.grid_info().get('column') == 1:
                    child.configure(text=translator("鉴定结果"))

        if self.action_button:
            self.action_button.configure(text=translator("开始鉴定"))
        self._reset_result_display()

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
        if not self.app.current_config or not self.app.genome_sources_data:
            self.app.ui_manager.show_error_message(self._("错误"), self._("请先加载配置文件。"))
            return

        gene_ids_text = self.gene_list_textbox.get("1.0", tk.END).strip()
        if not gene_ids_text:
            self.app.ui_manager.show_error_message(self._("输入缺失"), self._("请输入至少一个基因ID进行鉴定。"))
            return

        gene_ids = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        self.output_textbox.configure(state="normal", font=self.app.app_font_mono)
        self.output_textbox.delete("1.0", tk.END)
        self.output_textbox.insert("1.0", self._("正在批量鉴定中，请稍候..."), "secondary")
        self.output_textbox.configure(state="disabled")

        self.app.event_handler._start_task(
            task_name=self._("基因组批量鉴定"),
            target_func=self._batch_identify_worker,
            kwargs={'gene_ids': gene_ids},
            on_success=self.handle_batch_result
        )

    def _batch_identify_worker(self, gene_ids: List[str], **kwargs) -> Tuple[List[str], Set[str]]:
        genome_sources = self.app.genome_sources_data
        cancel_event = kwargs.get('cancel_event')
        results = []
        unique_warnings = set()
        for i, gene_id in enumerate(gene_ids):
            if cancel_event and cancel_event.is_set():
                break
            result_tuple = identify_genome_from_gene_ids(
                gene_ids=[gene_id],
                genome_sources=genome_sources
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