# 文件路径: ui/tabs/base_tab.py

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, List, Callable, Optional
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

        # 应用 fill="both" 和 expand=True 使 BaseTab 自身填满 Notebook 的空间
        # 移除左右的 padding/margin
        self.pack(fill="both", expand=True, padx=0, pady=0)

        # 创建基础布局
        self._create_base_layout()
        # 调用子类的方法来填充滚动区域
        self._create_widgets()

    def _create_base_layout(self):
        """创建基础的上下布局框架。"""
        self.grid_rowconfigure(0, weight=1)  # 可滚动内容区占据大部分空间
        self.grid_rowconfigure(1, weight=0)  # 操作按钮区高度固定
        self.grid_columnconfigure(0, weight=1)  # 整体列可拉伸

        # --- 上部：可滚动内容区 ---
        # 使用一个 Frame 包裹 Canvas 和 Scrollbar
        scroll_container = ttk.Frame(self)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(scroll_container, highlightthickness=0, bd=0,
                           background=self.app.style.lookup('TFrame', 'background'))
        canvas.grid(row=0, column=0, sticky="nsew")

        # 使用 ttkbootstrap 的 Scrollbar
        scrollbar = ttkb.Scrollbar(scroll_container, orient="vertical", command=canvas.yview,
                                   bootstyle="round-secondary")
        scrollbar.grid(row=0, column=1, sticky="ns")

        canvas.configure(yscrollcommand=scrollbar.set)

        # 创建可滚动框架
        self.scrollable_frame = ttk.Frame(canvas)
        # 将可滚动框架的宽度与Canvas同步
        canvas_window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw",
                                                width=self.winfo_width())

        def _on_frame_configure(event):
            # 更新滚动区域以包含所有内容
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            # 当Canvas大小改变时，更新其中窗口的宽度
            canvas.itemconfig(canvas_window_id, width=event.width)

        def _on_mousewheel(event):
            # 统一不同平台的滚轮事件
            if event.num == 5 or event.delta == -120:
                canvas.yview_scroll(1, "units")
            if event.num == 4 or event.delta == 120:
                canvas.yview_scroll(-1, "units")

        self.scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # 绑定滚轮事件
        self.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        self.bind_all("<Button-4>", _on_mousewheel, add="+")
        self.bind_all("<Button-5>", _on_mousewheel, add="+")

        # --- 下部：固定操作区 ---
        action_frame = ttkb.Frame(self, bootstyle="light")  # 使用一个有背景色的Frame
        action_frame.grid(row=1, column=0, sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_rowconfigure(0, weight=1)

        self.action_button = ttkb.Button(action_frame, text=_("执行操作"), bootstyle="success")
        self.action_button.grid(row=0, column=0, sticky="se", padx=15, pady=10)

    def get_primary_action(self) -> Optional[Callable]:
        """返回此选项卡的主要操作函数，用于绑定回车键。"""
        if self.action_button and self.action_button.winfo_exists():
            # 返回一个无参数的 lambda，因为它可能被绑定到需要可调用对象的事件
            command = self.action_button.cget('command')
            return lambda: command() if command else None
        return None

    def _create_widgets(self):
        """
        此方法旨在被子类重写，以填充 scrollable_frame。
        """
        raise NotImplementedError("Each tab must implement _create_widgets")

    def update_assembly_dropdowns(self, assembly_ids: list):
        """子类可以重写此方法以更新其特有的下拉菜单。"""
        pass

    def update_from_config(self):
        """子类可以重写此方法以从加载的配置中更新UI。"""
        pass

    def update_button_state(self, is_running: bool, has_config: bool):
        """更新基类中操作按钮的状态。"""
        if not self.action_button or not self.action_button.winfo_exists(): return

        # 按钮在没有配置时也应该禁用
        state = "disabled" if is_running or not has_config else "normal"
        self.action_button.configure(state=state)