# 文件路径: ui/tabs/base_tab.py

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING,  Callable, Optional
import ttkbootstrap as ttkb

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class BaseTab(ttk.Frame):
    """
    所有选项卡的“基类”或“模板”。
    它定义了一个上下布局：上部为可滚动内容区，下部为固定的操作按钮区。
    """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent)
        self.app = app
        self.scrollable_frame: Optional[ttk.Frame] = None
        self.action_button: Optional[ttkb.Button] = None

        self.pack(fill="both", expand=True, padx=0, pady=0)

        self._create_base_layout()
        self._create_widgets()

    def _create_base_layout(self):
        """创建基础的上下布局框架。"""
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # --- 上部：可滚动内容区 ---
        scroll_container = ttk.Frame(self)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(scroll_container, highlightthickness=0, bd=0,
                           background=self.app.style.lookup('TFrame', 'background'))
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttkb.Scrollbar(scroll_container, orient="vertical", command=canvas.yview,
                                   bootstyle="round-secondary")
        scrollbar.grid(row=0, column=1, sticky="ns")

        canvas.configure(yscrollcommand=scrollbar.set)

        self.scrollable_frame = ttk.Frame(canvas)
        canvas_window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw",
                                                width=self.winfo_width())

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window_id, width=event.width)

        def _on_mousewheel(event):
            if event.num == 5 or event.delta == -120:
                canvas.yview_scroll(1, "units")
            if event.num == 4 or event.delta == 120:
                canvas.yview_scroll(-1, "units")

        self.scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        self.bind_all("<Button-4>", _on_mousewheel, add="+")
        self.bind_all("<Button-5>", _on_mousewheel, add="+")

        # --- 下部：固定操作区 ---
        action_frame = ttkb.Frame(self)
        action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_rowconfigure(0, weight=1)

        # 【修复】将写死的中文按钮文本替换为可翻译的 key
        self.action_button = ttkb.Button(action_frame, text=_("执行操作"), bootstyle="success")
        self.action_button.grid(row=0, column=0, sticky="e", padx=15, pady=10)


    def get_primary_action(self) -> Optional[Callable]:
        """返回此选项卡的主要操作函数，用于绑定回车键。"""
        if self.action_button and self.action_button.winfo_exists():
            command = self.action_button.cget('command')
            return lambda: command() if command else None
        return None

    def _create_widgets(self):
        """此方法旨在被子类重写，以填充 scrollable_frame。"""
        raise NotImplementedError("Each tab must implement _create_widgets")

    def retranslate_ui(self, translator: Callable[[str], str]):
        """
        一个由子类重写的方法，用于在语言切换后更新其内部所有元件的文字。
        基类中只是一个占位符，真正的实作在每个子分页中。
        """
        raise NotImplementedError("Each tab must implement retranslate_ui")


    def update_assembly_dropdowns(self, assembly_ids: list):
        """子类可以重写此方法以更新其特有的下拉菜单。"""
        pass

    def update_from_config(self):
        """子类可以重写此方法以从加载的配置中更新UI。"""
        pass

    def update_button_state(self, is_running: bool, has_config: bool):
        """更新基类中操作按钮的状态。"""
        if not self.action_button or not self.action_button.winfo_exists(): return
        state = "disabled" if is_running or not has_config else "normal"
        self.action_button.configure(state=state)