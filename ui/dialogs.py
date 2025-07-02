# cotton_toolkit/ui/dialogs.py
import os
import sys
import time
import tkinter as tk
from tkinter import ttk, font as tkfont # 导入 ttk 和 tkfont
from typing import Optional, Callable, List

import ttkbootstrap as ttkb # 导入 ttkbootstrap
from ttkbootstrap.constants import * # 导入 ttkbootstrap 常量

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class BaseDialog(ttkb.Toplevel): # 继承 ttkbootstrap.Toplevel
    """所有自定义对话框的基类。"""

    def __init__(self, parent, title: str, style: Optional[ttkb.Style] = None):
        # The ttkb.Toplevel constructor should be called without explicitly passing 'style'
        # if 'style' is meant to be the *application's* style object that Toplevel automatically inherits/uses.
        # The 'self.style' property is already part of ttkb.Toplevel,
        # it's not meant to be reassigned directly.
        super().__init__(parent) # Removed 'style=style' as ttkb.Toplevel doesn't take it directly.
                                   # The Toplevel will automatically use the parent's style or the default app style.
        self.parent = parent
        self.result = None
        # Removed the problematic line: self.style = style if style else ttkb.Style()
        # The 'self.style' property is already provided by ttkb.Toplevel, it's a getter, not a setter.
        # If the 'style' object is needed for lookups within the dialog,
        # it should be accessed via self.style property provided by ttkb.Toplevel
        # or passed explicitly to internal widgets that need styling, not assigned to self.style.

        # 单独使用 .title() 方法来设置标题
        self.title(_(title))

        self.transient(parent)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.minsize(380, 180)

        try:
            # 确保在打包后也能找到图标
            if hasattr(sys, '_MEIPASS'):
                 icon_path = os.path.join(sys._MEIPASS, "icon.ico")
                 if os.path.exists(icon_path):
                     self.iconbitmap(icon_path)
            else:
                 # 尝试使用父窗口的图标
                 if hasattr(parent, 'iconbitmap') and parent.iconbitmap():
                     self.iconbitmap(parent.iconbitmap())
                 else:
                     pass # 忽略，不设置图标
        except Exception:
            pass # 如果找不到图标，则忽略

        self.after(20, self._center_window_and_grab_focus)


    def _center_window_and_grab_focus(self):
        """计算居中位置并捕获焦点。"""
        try:
            self.update_idletasks()
            parent_x, parent_y = self.parent.winfo_x(), self.parent.winfo_y()
            parent_w, parent_h = self.parent.winfo_width(), self.parent.winfo_height()
            dialog_w, dialog_h = self.winfo_width(), self.winfo_height()
            x = parent_x + (parent_w - dialog_w) // 2
            y = parent_y + (parent_h - dialog_h) // 2
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass # 父窗口可能已关闭
        self.grab_set()


    def on_cancel(self):
        """默认的关闭/取消行为。"""
        self.result = getattr(self, '_last_button_text', None)
        self.grab_release()
        self.destroy()


class MessageDialog(BaseDialog):
    """可滚动的消息弹窗。"""

    def __init__(self, parent, title: str, message: str, icon_type: str = "info", buttons: List[str] = None,
                 style: Optional[ttkb.Style] = None): # app_font removed
        super().__init__(parent, title, style) # Pass style to BaseDialog

        if buttons is None:
            buttons = [_("确定")]
        self._last_button_text = buttons[-1] if buttons else None

        icon_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "question": "❓"}
        icon = icon_map.get(icon_type, "")

        # Use 'secondary' bootstyle for frame background, better for both light/dark themes
        main_frame = ttkb.Frame(self, bootstyle="secondary")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # Style for icon label
        # Access style via self.style property from ttkb.Toplevel
        self.style.configure("Icon.TLabel", font=("Segoe UI Emoji", 28))
        if icon:
            ttk.Label(main_frame, text=icon, style="Icon.TLabel").pack(pady=(10, 5))

        # Use tk.Text for scrollable message content
        # Set background/foreground based on current theme's input/text colors
        # 修复：tk.Text 的背景色和前景色通过 style.lookup 获取
        text_bg = self.style.lookup('TText', 'background')
        text_fg = self.style.lookup('TText', 'foreground')

        # Get font from parent.app.app_font if available, otherwise fallback
        msg_font = getattr(parent, 'app_font', ("TkDefaultFont", 14))


        textbox = tk.Text(
            main_frame,
            wrap="word",
            font=msg_font, # Use the font from app or fallback
            relief="flat", # Flat border for modern look
            borderwidth=1,
            background=text_bg,
            foreground=text_fg,
            height=6 # Adjust initial height
        )
        textbox.pack(fill="both", expand=True, padx=15, pady=5)
        textbox.insert("1.0", message)
        textbox.configure(state="disabled")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(15, 10))

        for button_text in buttons:
            btn_style = "info" if icon_type == "info" else "primary" # Example style
            if icon_type == "error":
                btn_style = "danger"
            elif icon_type == "warning":
                btn_style = "warning"
            elif icon_type == "question":
                btn_style = "secondary"

            # 修复：ttkb.Button 不支持直接的 font 参数
            btn = ttkb.Button(button_frame, text=_(button_text),
                                command=lambda bt=button_text: self._on_button_click(bt), width=15,
                                bootstyle=btn_style)
            btn.pack(side="left", padx=5)

    def _on_button_click(self, button_text: str):
        self.result = button_text
        self.grab_release()
        self.destroy()


class ProgressDialog(BaseDialog):
    """任务进度弹窗。"""

    def __init__(self, parent, title: str = "任务进行中", on_cancel: Optional[Callable] = None,
                 style: Optional[ttkb.Style] = None): # app_font removed
        super().__init__(parent, title, style)
        self.on_cancel_callback = on_cancel
        self.resizable(False, False)

        self.creation_time = time.time()

        # Use 'secondary' bootstyle for frame background, better for both light/dark themes
        main_frame = ttkb.Frame(self, bootstyle="secondary")
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # Get font from parent.app.app_font if available, otherwise fallback
        prog_font = getattr(parent, 'app_font', ("TkDefaultFont", 14))

        self.message_var = tk.StringVar(value=_("正在准备任务..."))
        ttk.Label(main_frame, textvariable=self.message_var, wraplength=300, justify="center", font=prog_font).pack(pady=10, padx=10)

        # 修复：ttkb.Progressbar 不支持直接的 font 参数
        self.progress_bar = ttkb.Progressbar(main_frame, length=300, mode='determinate', bootstyle="info")
        # Fixed line: Use configure(value=0) instead of set(0)
        self.progress_bar.configure(value=0)
        self.progress_bar.pack(pady=10, padx=10, fill="x", expand=True)

        if self.on_cancel_callback:
            # 修复：ttkb.Button 不支持直接的 font 参数
            cancel_button = ttkb.Button(main_frame, text=_("取消"), command=self.on_close_button,
                                        bootstyle="danger")
            cancel_button.pack(pady=(10, 0), anchor="center")

        self.protocol("WM_DELETE_WINDOW", self.on_close_button)

    def update_progress(self, percentage: float, text: str): # percentage can be float
        try:
            if self.winfo_exists():
                self.message_var.set(_(text))
                self.progress_bar.configure(value=percentage) # ttkb.Progressbar expects value directly
                self.update_idletasks()
        except tk.TclError:
            pass


    def on_close_button(self):
        """当用户点击取消或关闭按钮时调用。"""
        if self.on_cancel_callback:
            self.on_cancel_callback()


    def close(self):
        """一个简单的、用于被外部调用的销毁方法。"""
        if self.winfo_exists():
            self.destroy()

    def on_cancel(self):
        """重写基类的 on_cancel，确保总是调用安全的 close 方法。"""
        self.close()