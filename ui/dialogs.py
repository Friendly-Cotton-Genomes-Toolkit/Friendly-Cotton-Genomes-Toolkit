# 文件路径: ui/dialogs.py

import tkinter as tk
import time
import sys
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import Optional, List, Callable

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    # 如果在测试或独立运行此模块时，_ 可能未设置
    _ = lambda s: str(s)


class ConfirmationDialog(tk.Toplevel):
    """
    一个通用的确认对话框，可以自定义按钮文本和回调。
    """
    def __init__(self, parent, title: str, message: str,
                 button1_text: str = "OK", button2_text: Optional[str] = None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.result = None

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda event: self._on_close())

        main_frame = ttkb.Frame(self, padding=20)
        main_frame.pack(expand=True, fill="both")

        message_label = ttkb.Label(main_frame, text=message, wraplength=350, justify="left")
        message_label.pack(padx=10, pady=(0, 20))

        button_frame = ttkb.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        self.button1 = ttkb.Button(button_frame, text=button1_text, command=self._on_button1_click, bootstyle="primary")
        self.button1.pack(side="right", padx=5)

        if button2_text:
            self.button2 = ttkb.Button(button_frame, text=button2_text, command=self._on_button2_click,
                                       bootstyle="secondary")
            self.button2.pack(side="right", padx=5)

        self.update_idletasks()
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        dialog_width, dialog_height = self.winfo_width(), self.winfo_height()

        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        self.geometry(f"+{x}+{y}")

        self.wait_window(self)

    def _on_button1_click(self):
        self.result = True
        self.destroy()

    def _on_button2_click(self):
        self.result = False
        self.destroy()

    def _on_close(self):
        self.result = None
        self.destroy()


class MessageDialog(ttkb.Toplevel):
    """
    一个通用的、带主题的消息对话框。
    """
    def __init__(self, parent, title: str, message: str, icon_type: str = "info",
                 buttons: Optional[List[str]] = None, style=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.result = None
        self.resizable(False, False)

        if buttons is None:
            buttons = ["确定"]

        icon_map = {"info": "ℹ", "warning": "⚠", "error": "❌", "question": "❓"}
        icon_char = icon_map.get(icon_type, "ℹ")
        bootstyle_map = {"info": "info", "warning": "warning", "error": "danger", "question": "primary"}
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

        for i, text_key in enumerate(buttons):
            style = color_name if i == 0 else f"{color_name}-outline"
            btn = ttkb.Button(button_frame, text=_(text_key), bootstyle=style,
                              command=lambda t=text_key: self.on_button_click(_(t)))
            btn.pack(side=tk.LEFT, padx=(0, 10))

        self.bind("<Escape>", self._on_escape_close)

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

    def _on_escape_close(self, event=None):
        """当按下ESC键时调用。"""
        self.result = "esc_closed"  # 设置一个特定的结果
        self.destroy()


class ProgressDialog(ttkb.Toplevel):
    """任务进度弹窗。"""
    def __init__(self, parent, title: str, on_cancel: Optional[Callable] = None, style=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
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
        self.bind("<Escape>", lambda e: self.on_close_button() if on_cancel else None)

        self.update_idletasks()
        try:
            parent_x, parent_y, parent_w, parent_h = parent.winfo_x(), parent.winfo_y(), parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            x, y = parent_x + (parent_w - w) // 2, parent_y + (parent_h - h) // 2
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def update_progress(self, percentage: float, text: str):
        if self.winfo_exists():
            self.message_var.set(_(text))
            self.progress_bar['value'] = percentage
            self.update_idletasks()

    def on_close_button(self):
        if self.on_cancel_callback:
            self.on_cancel_callback()
        self.destroy()

    def close(self):
        if self.winfo_exists():
            self.destroy()