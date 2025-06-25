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
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        # 为所有子类创建一个可滚动的框架
        self.scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", border_width=0)
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        # 初始化所有UI控件
        self._create_widgets()

        # 从主应用加载配置来更新UI
        self.update_from_config()

    def _create_widgets(self):
        """
        创建该选项卡特有的UI控件。
        这个方法应该在每个子类中被“重写”（override）。
        """
        # 在基类中，我们只放置一个占位符标签
        ctk.CTkLabel(self.scrollable_frame,
                     text="This is the base tab. Subclasses should override _create_widgets.").pack()

    def update_from_config(self):
        """
        当主应用的配置加载或更新时，此方法会被调用。
        子类可以“重写”此方法来更新自己特有的UI。
        """
        # 默认实现是更新基因组下拉菜单（如果存在）
        if hasattr(self, 'update_assembly_dropdowns') and self.app.genome_sources_data:
            self.update_assembly_dropdowns(list(self.app.genome_sources_data.keys()))

    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        """
        更新所有名为 assembly_dropdown 的下拉菜单。
        这是一个通用方法，适用于大多数有基因组选择的选项卡。
        """
        if not assembly_ids:
            assembly_ids = [_("加载中...")]

        # 查找所有需要更新的下拉菜单
        widgets = self.__dict__
        for widget_name, widget in widgets.items():
            if isinstance(widget, ctk.CTkOptionMenu) and 'assembly_dropdown' in widget_name:
                var_name = widget.cget("variable")
                variable = self.setvar(var_name)  # 获取关联的StringVar

                widget.configure(values=assembly_ids)

                # 如果列表有效，设置默认值
                is_valid_list = bool(assembly_ids and "加载中" not in assembly_ids[0])
                if is_valid_list and variable.get() not in assembly_ids:
                    variable.set(assembly_ids[0])

    def update_button_state(self, is_running: bool, has_config: bool):
        """
        根据任务运行状态和配置加载状态，更新所有“开始”按钮的可点击状态。
        """
        state = "disabled" if is_running or not has_config else "normal"

        # 查找所有名为 start_button 的按钮并更新状态
        if hasattr(self, 'start_button'):
            self.start_button.configure(state=state)