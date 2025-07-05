# 文件: cotton_tool/ui/dialogs.py

import tkinter as tk
import time
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import Optional, List, Callable

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class MessageDialog(ttkb.Toplevel):
    """
    一个通用的、带主题的消息对话框。
    """

    def __init__(self, parent, title: str, message: str, icon_type: str = "info",
                 buttons: Optional[List[str]] = None, style=None):
        super().__init__(parent)
        self.title(_(title))
        self.transient(parent)
        self.grab_set()
        self.focus_set()  # <-- 核心修改：立即获取焦点
        self.result = None
        self.resizable(False, False)

        if buttons is None:
            buttons = [_("确定")]

        icon_map = {"info": "ℹ", "warning": "⚠", "error": "❌", "question": "❓"}
        icon_char = icon_map.get(icon_type, "ℹ")

        bootstyle_map = {
            "info": "info",
            "warning": "warning",
            "error": "danger",
            "question": "primary"
        }
        color_name = bootstyle_map.get(icon_type, "info")

        main_frame = ttkb.Frame(self, padding=(30, 25))
        main_frame.pack(expand=True, fill=BOTH)
        main_frame.grid_columnconfigure(1, weight=1)

        icon_label = ttkb.Label(main_frame, text=icon_char, bootstyle=color_name, font=("-size", 28))
        icon_label.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 20), pady=5)

        message_label = ttkb.Label(main_frame, text=message, wraplength=400, justify="left")
        message_label.grid(row=0, column=1, sticky="w")

        button_frame = ttkb.Frame(main_frame)
        button_frame.grid(row=1, column=1, sticky="e", pady=(20, 0))

        for i, text in enumerate(buttons):
            style = color_name if i == 0 else f"{color_name}-outline"
            btn = ttkb.Button(button_frame, text=text, bootstyle=style, command=lambda t=text: self.on_button_click(t))
            btn.pack(side=LEFT, padx=(0, 10))

        self.bind("<Escape>", self._on_escape)

        self.update_idletasks()
        try:
            parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
            parent_w, parent_h = parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            x, y = parent_x + (parent_w - w) // 2, parent_y + (parent_h - h) // 2
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def on_button_click(self, result: str):
        self.result = result
        self.destroy()

    def _on_escape(self, event=None):
        """响应ESC键，直接关闭窗口。"""
        self.destroy()


class ProgressDialog(ttkb.Toplevel):
    """任务进度弹窗。"""

    def __init__(self, parent, title: str, on_cancel: Optional[Callable] = None, style=None):
        super().__init__(parent)
        self.title(_(title))
        self.transient(parent)
        self.grab_set()
        self.focus_set()  # <-- 核心修改：立即获取焦点
        self.resizable(False, False)
        self.on_cancel_callback = on_cancel
        self.creation_time = time.time()

        main_frame = ttkb.Frame(self, padding=20)
        main_frame.pack(expand=True, fill=BOTH)
        main_frame.grid_columnconfigure(0, weight=1)

        self.message_var = tk.StringVar(value=_("正在准备任务..."))
        ttkb.Label(main_frame, textvariable=self.message_var, wraplength=350, justify="center").grid(row=0, column=0,
                                                                                                     pady=10, padx=10)

        self.progress_bar = ttkb.Progressbar(main_frame, length=350, mode='determinate', bootstyle="info-striped")
        self.progress_bar.grid(row=1, column=0, pady=10, padx=10, sticky="ew")

        if on_cancel:
            cancel_button = ttkb.Button(main_frame, text=_("取消"), command=self.on_close_button,
                                        bootstyle="danger-outline")
            cancel_button.grid(row=2, column=0, pady=(10, 0))

        self.protocol("WM_DELETE_WINDOW", self.on_close_button)

        self.bind("<Escape>", self._on_escape)

        self.update_idletasks()
        try:
            parent_x, parent_y, parent_w, parent_h = parent.winfo_x(), parent.winfo_y(), parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            x, y = parent_x + (parent_w - w) // 2, parent_y + (parent_h - h) // 2
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def update_progress(self, percentage: float, text: str):
        try:
            if self.winfo_exists():
                self.message_var.set(_(text))
                self.progress_bar['value'] = percentage
                self.update_idletasks()
        except tk.TclError:
            pass

    def on_close_button(self):
        if self.on_cancel_callback:
            self.on_cancel_callback()
            self.destroy()

    def _on_escape(self, event=None):
        """响应ESC键，仅当窗口可取消时才关闭。"""
        if self.on_cancel_callback:
            self.on_close_button()

    def close(self):
        if self.winfo_exists():
            self.destroy()