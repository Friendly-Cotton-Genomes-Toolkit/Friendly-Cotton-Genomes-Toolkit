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
        self.canvas: Optional[tk.Canvas] = None
        self.scrollbar: Optional[ttkb.Scrollbar] = None
        self.cancel_event: Optional[threading.Event] = None

        self.pack(fill="both", expand=True, padx=0, pady=0)

        # --- 优化后的调用流程 ---
        self._create_base_layout()
        self._create_widgets()
        # 在所有子控件创建完毕后，为本Tab及其所有子控件递归绑定滚轮事件
        self._bind_recursive_mousewheel(self)
        self.after(50, self._update_scrollbar_visibility)

    def _create_base_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        scroll_container = ttk.Frame(self)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(scroll_container, highlightthickness=0, bd=0,
                                background=self.app.style.lookup('TFrame', 'background'))
        self.scrollbar = ttkb.Scrollbar(scroll_container, orient="vertical", command=self.canvas.yview,
                                        bootstyle="round-secondary")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas, padding=15)
        self.canvas_window_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.scrollable_frame.bind("<Configure>", self._on_frame_or_tab_configure)
        self.bind("<Configure>", self._on_frame_or_tab_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        action_frame = ttkb.Frame(self)
        action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        action_frame.grid_columnconfigure(0, weight=1)

        self.action_button = ttkb.Button(action_frame, text=self._("执行操作"), bootstyle="success")
        self.action_button.grid(row=0, column=0, sticky="e", padx=15, pady=10)

    # --- 核心修改：稳定、独立的递归滚轮事件绑定 ---
    def _on_mousewheel(self, event: tk.Event):
        """统一处理鼠标滚轮事件，滚动当前Tab的画布。"""
        if not (self.canvas and self.canvas.winfo_exists()):
            return

        scroll_units = 0
        if sys.platform.startswith('linux'):
            if event.num == 4:
                scroll_units = -1
            elif event.num == 5:
                scroll_units = 1
        else:
            # 标准化不同鼠标的滚动增量 (Windows/macOS)
            delta = event.delta
            if abs(delta) > 0:
                scroll_units = -1 * (delta / 120) if "win" in sys.platform else -1 * delta

        if scroll_units:
            self.canvas.yview_scroll(int(scroll_units), "units")

        # 返回 "break" 阻止事件冒泡，防止父级组件或其他绑定也处理此事件
        return "break"

    def _bind_recursive_mousewheel(self, widget: tk.Widget):
        """递归地为控件及其所有子控件绑定鼠标滚轮事件。"""
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

        for child in widget.winfo_children():
            self._bind_recursive_mousewheel(child)

    # --- 智能显示/隐藏滚动条 ---
    def _update_scrollbar_visibility(self, event: Optional[tk.Event] = None):
        """检查是否需要滚动条，并相应地显示或隐藏它。"""
        if not (self.canvas and self.scrollable_frame and self.scrollbar and self.scrollable_frame.winfo_exists()):
            return

        self.canvas.update_idletasks()
        self.scrollable_frame.update_idletasks()

        content_height = self.scrollable_frame.winfo_reqheight()
        viewport_height = self.canvas.winfo_height()

        if content_height <= viewport_height:
            self.scrollbar.grid_remove()
            self.scrollable_frame.configure(padding=15)
        else:
            self.scrollbar.grid()
            self.scrollable_frame.configure(padding=(15, 15, 5, 15))

    # --- 布局配置方法 ---
    def _on_frame_or_tab_configure(self, event: tk.Event):
        if self.canvas:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event: tk.Event):
        if self.canvas:
            self.canvas.itemconfig(self.canvas_window_id, width=event.width)

    # --- 保持不变的公共方法 ---
    def get_primary_action(self) -> Optional[Callable]:
        if self.action_button and self.action_button.winfo_exists():
            command_str = self.action_button.cget('command')
            if command_str:
                return self.action_button.tk.globalgetvar(command_str)
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
                self.app.after(0, lambda: MessageDialog(self.app, title=self._("严重错误"), message=error_msg,
                                                        icon_type="error"))
            finally:
                if progress_dialog.winfo_exists():
                    progress_dialog.destroy()
                if self.cancel_event.is_set():
                    self.app.log_message(self._("任务已被用户取消。"), "INFO")
                elif result:
                    success_msg = self._("任务成功完成！")
                    if isinstance(result, str): success_msg = result
                    self.app.log_message(success_msg, "INFO")
                    self.app.after(0, lambda: MessageDialog(self.app, title=self._("成功"), message=success_msg,
                                                            icon_type="info"))
                elif result is None and not self.cancel_event.is_set():
                    self.app.log_message(self._("任务执行完毕，但未返回成功状态或结果。"), "WARNING")

        task_thread = threading.Thread(target=_task_wrapper, daemon=True)
        task_thread.start()

    def _create_widgets(self):
        raise NotImplementedError("Each tab must implement _create_widgets")

    def update_assembly_dropdowns(self, assembly_ids: list):
        pass

    def update_from_config(self):
        pass

    def update_button_state(self, is_running: bool, has_config: bool):
        if not self.action_button or not self.action_button.winfo_exists(): return
        state = "disabled" if is_running or not has_config else "normal"
        self.action_button.configure(state=state)