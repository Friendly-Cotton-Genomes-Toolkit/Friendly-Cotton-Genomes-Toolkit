# 文件路径: ui/tabs/base_tab.py
import sys
import tkinter as tk
import threading
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Optional, Dict, Tuple, Any

import ttkbootstrap as ttkb

# 确保能正确导入您的对话框模块
from ..dialogs import ProgressDialog, MessageDialog


if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp


class BaseTab(ttk.Frame):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        super().__init__(parent)
        self.app = app
        self._ = translator
        self.scrollable_frame: Optional[ttk.Frame] = None
        self.action_button: Optional[ttkb.Button] = None
        self.cancel_event: Optional[threading.Event] = None
        self.pack(fill="both", expand=True, padx=0, pady=0)
        self._create_base_layout()
        self._create_widgets()

    def _create_base_layout(self):
        # ... 此处代码与您原文件一致，为简洁省略 ...
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)
        scroll_container = ttk.Frame(self)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(scroll_container, highlightthickness=0, bd=0, background=self.app.style.lookup('TFrame', 'background'))
        scrollbar = ttkb.Scrollbar(scroll_container, orient="vertical", command=canvas.yview, bootstyle="round-secondary")
        canvas.configure(yscrollcommand=scrollbar.set)
        self.scrollable_frame = ttk.Frame(canvas)
        canvas_window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        def _on_mousewheel(event):
            if sys.platform.startswith('linux'):
                if event.num == 4: canvas.yview_scroll(-1, "units")
                elif event.num == 5: canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        def _bind_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children(): _bind_mousewheel(child)
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            _bind_mousewheel(self.scrollable_frame)
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window_id, width=event.width)
        _bind_mousewheel(self)
        self.scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        action_frame = ttkb.Frame(self)
        action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_rowconfigure(0, weight=1)
        self.action_button = ttkb.Button(action_frame, text=self._("执行操作"), bootstyle="success")
        self.action_button.grid(row=0, column=0, sticky="e", padx=15, pady=10)


    def get_primary_action(self) -> Optional[Callable]:
        if self.action_button and self.action_button.winfo_exists():
            command = self.action_button.cget('command')
            return lambda: command() if command else None
        return None

    def run_task_in_thread(
        self,
        task_function: Callable[..., Any],
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        dialog_title: str = "正在处理..."
    ):
        if kwargs is None: kwargs = {}
        self.cancel_event = threading.Event()
        progress_dialog = ProgressDialog(
            parent=self.app, title=self._(dialog_title), on_cancel=self.cancel_event.set
        )

        def _task_wrapper():
            kwargs['status_callback'] = self.app.log_message
            kwargs['progress_callback'] = progress_dialog.update_progress
            kwargs['cancel_event'] = self.cancel_event
            result = None
            try:
                result = task_function(*args, **kwargs)
            except Exception as e:
                error_msg = self._("后台任务发生严重错误: {}").format(e)
                self.app.log_message(error_msg, "ERROR")
                self.app.after(0, lambda: MessageDialog(self.app, title=self._("严重错误"), message=error_msg, icon_type="error"))
            finally:
                progress_dialog.close()
                if self.cancel_event.is_set():
                    self.app.log_message(self._("任务已被用户取消。"), "INFO")
                elif result:
                    success_msg = self._("任务成功完成！")
                    if isinstance(result, str): success_msg = result
                    self.app.log_message(success_msg, "INFO")
                    self.app.after(0, lambda: MessageDialog(self.app, title=self._("成功"), message=success_msg, icon_type="info"))
                else:
                    self.app.log_message(self._("任务执行完毕，但未返回成功状态或结果。"), "WARNING")

        task_thread = threading.Thread(target=_task_wrapper, daemon=True)
        task_thread.start()

    def _create_widgets(self):
        raise NotImplementedError("Each tab must implement _create_widgets")

    def retranslate_ui(self, translator: Callable[[str], str]):
        if self.action_button and self.action_button.winfo_exists():
            self.action_button.configure(text=translator("执行操作"))

    def update_assembly_dropdowns(self, assembly_ids: list):
        pass

    def update_from_config(self):
        pass

    def update_button_state(self, is_running: bool, has_config: bool):
        if not self.action_button or not self.action_button.winfo_exists(): return
        state = "disabled" if is_running or not has_config else "normal"
        self.action_button.configure(state=state)