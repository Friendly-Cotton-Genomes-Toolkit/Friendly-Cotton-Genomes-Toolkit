# 文件路径: ui/tabs/base_tab.py

import tkinter as tk
from tkinter import ttk # Import ttk module
import ttkbootstrap as ttkb # Import ttkbootstrap
from ttkbootstrap.constants import * # Import ttkbootstrap constants

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class BaseTab(ttk.Frame): # Changed from ctk.CTkFrame to ttk.Frame
    """
    所有选项卡的“基类”或“模板”。
    它包含了所有选项卡共有的初始化逻辑和方法。
    """

    def __init__(self, parent, app: "CottonToolkitApp"):
        super().__init__(parent) # No fg_color for ttk.Frame
        self.parent = parent
        self.app = app
        self.scrollable_frame = None # This will be the inner frame within the canvas

    def _create_base_widgets(self):
        """
        创建所有标签页共有的基础控件（一个可滚动的框架）。
        此方法现在由子类显式调用。
        """
        # Create a Canvas for the scrollable area
        # Use parent as the container for the canvas, then pack the canvas to fill the parent
        # 修复：self.app.style.colors 对象没有 'background' 属性，应使用 style.lookup
        canvas = tk.Canvas(self.parent, highlightthickness=0, background=self.app.style.lookup('TCanvas', 'background'))
        canvas.pack(side="left", fill="both", expand=True)

        # Create a Scrollbar and link it to the Canvas
        scrollbar = ttkb.Scrollbar(self.parent, orient="vertical", command=canvas.yview, bootstyle="round")
        scrollbar.pack(side="right", fill="y")

        canvas.configure(yscrollcommand=scrollbar.set)

        # Create an inner Frame inside the Canvas to hold the actual widgets
        self.scrollable_frame = ttk.Frame(canvas)
        # Create a window in the canvas to contain the inner frame
        canvas_window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # Bind the inner frame's Configure event to update the canvas's scrollregion
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Also update the window width to match canvas width when canvas resizes
            canvas.itemconfig(canvas_window_id, width=event.width)

        self.scrollable_frame.bind("<Configure>", _on_frame_configure)

        # Bind mouse wheel to the canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # 修复：由于 canvas.bind_all 会导致整个应用程序捕获鼠标滚轮事件，影响其他滚动区域，
        # 建议仅绑定到 canvas 本身，或者在需要时动态绑定/解绑。
        # 这里将其改为 canvas.bind，只影响当前的Canvas
        canvas.bind("<MouseWheel>", _on_mousewheel)

        # Ensure the inner frame (self.scrollable_frame) can expand horizontally
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        self._create_widgets()  # 调用应由子类重写的方法

    def _create_widgets(self):
        """
        此方法旨在被子类重写，以填充具体的UI控件。
        """
        pass

    def update_assembly_dropdowns(self, assembly_ids: list):
        """此方法旨在被子类重写。"""
        pass

    def update_from_config(self):
        """此方法旨在被子类重写。"""
        pass

    def update_button_state(self, is_running, has_config):
        """此方法旨在被子类重写。"""
        pass