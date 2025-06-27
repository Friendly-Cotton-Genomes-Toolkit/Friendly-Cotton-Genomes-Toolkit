# 文件路径: ui/tabs/base_tab.py

import tkinter as tk
import customtkinter as ctk
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class BaseTab(ctk.CTkFrame):
    """
    所有选项卡的“基类”或“模板”。
    它包含了所有选项卡共有的初始化逻辑和方法。
    """

    def __init__(self, parent, app: "CottonToolkitApp"):
        self.parent = parent
        self.app = app
        self.scrollable_frame = None

    def _create_base_widgets(self):
        """
        创建所有标签页共有的基础控件（一个可滚动的框架）。
        此方法现在由子类显式调用。
        """
        self.scrollable_frame = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        self.scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)
        self.app.ui_manager._bind_mouse_wheel_to_scrollable(self.scrollable_frame)
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



