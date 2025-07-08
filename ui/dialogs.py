# 文件: cotton_tool/ui/dialogs.py

import tkinter as tk
import time
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import Optional, List, Callable

# 全局翻译函数占位符，它会由主应用程式在启动时设定
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

        self.title(title) # title 在外部调用时已传入翻译好的文本，无需再次 _()

        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.result = None
        self.resizable(False, False)

        # 【修复】将默认按钮的中文文本改为可翻译的 key
        if buttons is None:
            # 确保这里传入的是需要翻译的字符串，而不是翻译后的结果
            buttons = ["确定"] # 使用英文或通用键，_() 会在按钮创建时应用

        icon_map = {"info": "ℹ", "warning": "⚠", "error": "❌", "question": "❓"}
        icon_char = icon_map.get(icon_type, "ℹ")

        bootstyle_map = {"info": "info", "warning": "warning", "error": "danger", "question": "primary"}
        color_name = bootstyle_map.get(icon_type, "info")

        main_frame = ttkb.Frame(self, padding=(30, 25))
        main_frame.pack(expand=True, fill=BOTH)
        main_frame.grid_columnconfigure(1, weight=1)

        icon_label = ttkb.Label(main_frame, text=icon_char, bootstyle=color_name, font=("-size", 28))
        icon_label.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 20), pady=5)

        # message 在外部调用时已传入翻译好的文本，无需再次 _()
        message_label = ttkb.Label(main_frame, text=message, wraplength=400, justify="left")
        message_label.grid(row=0, column=1, sticky="w")

        button_frame = ttkb.Frame(main_frame)
        button_frame.grid(row=1, column=1, sticky="e", pady=(20, 0))

        for i, text_key in enumerate(buttons): # 这里的 text_key 可能是 "确定"
            style = color_name if i == 0 else f"{color_name}-outline"
            # 对按钮文本进行翻译
            btn = ttkb.Button(button_frame, text=_(text_key), bootstyle=style, command=lambda t=text_key: self.on_button_click(_(t)))
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
        self.destroy()


class ProgressDialog(ttkb.Toplevel):
    """任务进度弹窗。"""

    def __init__(self, parent, title: str, on_cancel: Optional[Callable] = None, style=None):
        super().__init__(parent)

        self.title(title) # title 在外部调用时已传入翻译好的文本，无需再次 _()

        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(False, False)
        self.on_cancel_callback = on_cancel
        self.creation_time = time.time()

        main_frame = ttkb.Frame(self, padding=20)
        main_frame.pack(expand=True, fill=BOTH)
        main_frame.grid_columnconfigure(0, weight=1)

        # 【修复】将默认消息和按钮文本改为可翻译的中文 key
        self.message_var = tk.StringVar(value=_("正在准备任务...")) # 这里需要 _()
        ttkb.Label(main_frame, textvariable=self.message_var, wraplength=350, justify="center").grid(row=0, column=0,
                                                                                                     pady=10, padx=10)

        self.progress_bar = ttkb.Progressbar(main_frame, length=350, mode='determinate', bootstyle="info-striped")
        self.progress_bar.grid(row=1, column=0, pady=10, padx=10, sticky="ew")

        if on_cancel:
            cancel_button = ttkb.Button(main_frame, text=_("取消"), command=self.on_close_button, # 这里需要 _()
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
        """更新进度条和显示的讯息。"""
        try:
            if self.winfo_exists():
                # text 参数在外部调用时已经过 _() 处理，这里可能不需要再次 _()
                # 但为了安全起见，如果外部调用没有确保翻译，这里加上 _() 更稳妥
                # 假设外部调用 (如 UIManager.update_progress) 会传入已翻译的文本，
                # 所以这里可以不加 _()，以避免重复翻译或翻译一个已经翻译过的字符串。
                # 但如果 `text` 有可能是未翻译的原始字符串，那么 `_()` 是必须的。
                # 鉴于 UIManager._show_progress_dialog 传入的 message 没有 _()，这里应该加。
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
        if self.on_cancel_callback:
            self.on_close_button()

    def close(self):
        if self.winfo_exists():
            self.destroy()