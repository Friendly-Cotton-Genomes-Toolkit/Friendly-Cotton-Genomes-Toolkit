# cotton_toolkit/ui/dialogs.py

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

        self.title(_(title))
        self.transient(parent)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.minsize(400, 220)

        try:
            self.iconbitmap(parent.iconbitmap())
        except tk.TclError:
            pass

        self.after(20, self._center_window_and_grab_focus)

    def _center_window_and_grab_focus(self):
        """计算居中位置并捕获焦点。"""
        self.update_idletasks()
        parent_x, parent_y = self.parent.winfo_x(), self.parent.winfo_y()
        parent_w, parent_h = self.parent.winfo_width(), self.parent.winfo_height()
        dialog_w, dialog_h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")
        self.grab_set()

    def on_cancel(self):
        """默认的关闭/取消行为。"""
        self.result = getattr(self, '_last_button_text', None)
        self.grab_release()
        self.destroy()


class MessageDialog(BaseDialog):
    """可滚动的消息弹窗（无动画，统一使用pack布局）。"""

    def __init__(self, parent, title: str, message: str, icon_type: str = "info", buttons: List[str] = None,
                 app_font: ctk.CTkFont = None):
        super().__init__(parent, title)

        if buttons is None:
            buttons = [_("确定")]
        self._last_button_text = buttons[-1] if buttons else None


        icon_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "question": "❓"}
        icon = icon_map.get(icon_type, "")

        # --- 【核心修正】统一使用 .pack() 布局 ---
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
        # 使用 pack 并让文本框填充可用空间
        textbox.pack(fill="both", expand=True, padx=15, pady=5)
        textbox.insert("1.0", message)
        textbox.configure(state="disabled")

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=(15, 10))

        for button_text in buttons:
            btn = ctk.CTkButton(button_frame, text=button_text,
                                command=lambda bt=button_text: self._on_button_click(bt), width=120, font=app_font)
            btn.pack(side="left", padx=5)

    def _on_button_click(self, button_text: str):
        self.result = button_text
        self.grab_release()
        self.destroy()


# 在 dialogs.py 文件中

class ProgressDialog(BaseDialog):
    """【修正版】任务进度弹窗，解决了生命周期竞态条件问题。"""

    def __init__(self, parent, title: str = "任务进行中", on_cancel: Optional[Callable] = None,
                 app_font: ctk.CTkFont = None):
        super().__init__(parent, title)
        self.on_cancel_callback = on_cancel
        self.resizable(False, False)

        main_frame = ctk.CTkFrame(self, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.message_var = tk.StringVar(value=_("正在准备任务..."))
        ctk.CTkLabel(main_frame, textvariable=self.message_var, wraplength=300, justify="center", font=app_font).pack(
            pady=10, padx=10)

        self.progress_bar = ctk.CTkProgressBar(main_frame, width=300, mode='determinate')
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10, padx=10, fill="x", expand=True)

        if self.on_cancel_callback:
            # 【修改点】取消按钮现在调用 self.close()
            cancel_button = ctk.CTkButton(main_frame, text=_("取消"), command=self.close, font=app_font)
            cancel_button.pack(pady=(10, 0), anchor="center")

        # 窗口的 "X" 按钮也应该调用 self.close
        self.protocol("WM_DELETE_WINDOW", self.close)

    def update_progress(self, percentage: int, message: str):
        if self.winfo_exists():
            self.message_var.set(message)
            self.progress_bar.set(percentage / 100)

    def _safe_destroy(self):
        """一个安全的销毁方法，确保在winfo_exists时才执行。"""
        if self.winfo_exists():
            self.grab_release()
            self.destroy()

    def close(self):
        """
        【新增】公共的、安全的关闭方法。
        它会触发取消回调，并延迟销毁窗口，以避免竞态条件。
        """
        if self.on_cancel_callback:
            # 触发传递进来的取消事件，让后台线程知道任务被取消了
            self.on_cancel_callback()

        # 使用 after() 方法，将销毁操作推迟10毫秒执行
        # 这给了Tkinter事件循环足够的时间来处理任何待办的UI事件
        self.after(10, self._safe_destroy)