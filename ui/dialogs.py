# cotton_toolkit/ui/dialogs.py
import os
import sys
import time
import tkinter as tk
from typing import Optional, Callable, List
import customtkinter as ctk

try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class BaseDialog(ctk.CTkToplevel):
    """所有自定义对话框的基类（无动画版）。"""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.parent = parent
        self.result = None

        # 单独使用 .title() 方法来设置标题
        self.title(_(title))

        self.transient(parent)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.minsize(380, 180) # 稍微调整大小

        try:
            # 确保在打包后也能找到图标
            if hasattr(sys, '_MEIPASS'):
                 icon_path = os.path.join(sys._MEIPASS, "icon.ico")
                 if os.path.exists(icon_path):
                     self.iconbitmap(icon_path)
            else:
                 self.iconbitmap(parent.iconbitmap())
        except Exception:
            pass # 如果找不到图标，则忽略

        self.after(20, self._center_window_and_grab_focus)


    def _mark_as_ready_for_destruction(self):
        """内部方法，用于在延迟后更新标志位。"""
        if self.winfo_exists():
            self._is_ready_for_destruction = True

    def update_progress(self, percentage: int, message: str):
        """安全地更新进度条和消息。"""
        try:
            if self.winfo_exists():
                self.message_var.set(_(message))
                self.progress_bar.set(percentage / 100.0)  # 使用浮点数除法
                self.update_idletasks()
        except tk.TclError:
            pass


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
                 app_font: ctk.CTkFont = None):
        super().__init__(parent, title)

        if buttons is None:
            buttons = [_("确定")]
        self._last_button_text = buttons[-1] if buttons else None

        icon_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "question": "❓"}
        icon = icon_map.get(icon_type, "")

        main_frame = ctk.CTkFrame(self, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        if icon:
            ctk.CTkLabel(main_frame, text=icon, font=("Segoe UI Emoji", 28)).pack(pady=(10, 5))

        textbox = ctk.CTkTextbox(
            main_frame,
            wrap="word",
            font=app_font or ("Microsoft YaHei UI", 14),
            corner_radius=8,
            border_width=1
        )
        textbox.pack(fill="both", expand=True, padx=15, pady=5)
        textbox.insert("1.0", message)
        textbox.configure(state="disabled")

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=(15, 10))

        for button_text in buttons:
            btn = ctk.CTkButton(button_frame, text=_(button_text),
                                command=lambda bt=button_text: self._on_button_click(bt), width=120, font=app_font)
            btn.pack(side="left", padx=5)

    def _on_button_click(self, button_text: str):
        self.result = button_text
        self.grab_release()
        self.destroy()


# 在 dialogs.py 文件中

class ProgressDialog(BaseDialog):
    """【最终健壮版】任务进度弹窗。"""

    def __init__(self, parent, title: str = "任务进行中", on_cancel: Optional[Callable] = None,
                 app_font: ctk.CTkFont = None):
        super().__init__(parent, title)
        self.on_cancel_callback = on_cancel
        self.resizable(False, False)

        self.creation_time = time.time()

        main_frame = ctk.CTkFrame(self, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.message_var = tk.StringVar(value=_("正在准备任务..."))
        ctk.CTkLabel(main_frame, textvariable=self.message_var, wraplength=300, justify="center", font=app_font).pack(pady=10, padx=10)

        self.progress_bar = ctk.CTkProgressBar(main_frame, width=300, mode='determinate')
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10, padx=10, fill="x", expand=True)

        if self.on_cancel_callback:
            cancel_button = ctk.CTkButton(main_frame, text=_("取消"), command=self.on_close_button, font=app_font)
            cancel_button.pack(pady=(10, 0), anchor="center")

        self.protocol("WM_DELETE_WINDOW", self.on_close_button)



    def _mark_as_ready_for_destruction(self):
        if self.winfo_exists():
            self._is_ready_for_destruction = True

    def update_progress(self, percentage: int, text: str):
        try:
            if self.winfo_exists():
                self.message_var.set(_(text))
                self.progress_bar.set(percentage / 100.0)
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
