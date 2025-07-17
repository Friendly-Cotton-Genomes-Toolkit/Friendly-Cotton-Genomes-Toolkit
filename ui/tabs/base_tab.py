# 文件路径: ui/tabs/base_tab.py
import sys
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Optional
import ttkbootstrap as ttkb

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp


class BaseTab(ttk.Frame):
    """
    所有选项卡的“基类”或“模板”。
    它定义了一个上下布局：上部为可滚动内容区，下部为固定的操作按钮区。
    """

    # 【修改】构造函数接收 translator
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        super().__init__(parent)
        self.app = app
        # 【修改】保存 translator 为实例属性
        self._ = translator
        self.scrollable_frame: Optional[ttk.Frame] = None
        self.action_button: Optional[ttkb.Button] = None

        self.pack(fill="both", expand=True, padx=0, pady=0)

        self._create_base_layout()
        self._create_widgets()

    def _create_base_layout(self):
        """创建基础的上下布局框架，并实现健壮的滚动逻辑。"""
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # 固定操作区高度
        self.grid_columnconfigure(0, weight=1)

        # --- 上部：可滚动内容区 ---
        # 容器包含了画布和滚动条
        scroll_container = ttk.Frame(self)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)

        # 画布，所有内容将绘制于此
        canvas = tk.Canvas(scroll_container, highlightthickness=0, bd=0,
                           background=self.app.style.lookup('TFrame', 'background'))

        # 滚动条
        scrollbar = ttkb.Scrollbar(scroll_container, orient="vertical", command=canvas.yview,
                                   bootstyle="round-secondary")

        canvas.configure(yscrollcommand=scrollbar.set)

        # 放置所有子页面组件的内部框架
        self.scrollable_frame = ttk.Frame(canvas)

        # 将内部框架放入画布中
        canvas_window_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # --- 滚轮事件处理优化 ---

        def _on_mousewheel(event):
            """统一处理不同平台的滚轮事件。"""
            # 根据事件类型判断滚动方向和幅度
            # Windows/macOS 使用 event.delta
            # Linux 使用 event.num
            if sys.platform.startswith('linux'):
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            else:
                # 调整滚动速度，可以修改 -1 和 1 来改变快慢
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            # 返回 "break" 阻止事件传播到父级窗口，避免意外滚动
            return "break"

        def _bind_mousewheel(widget):
            """递归地为组件及其所有子组件绑定滚轮事件。"""
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)  # For Linux scroll up
            widget.bind("<Button-5>", _on_mousewheel)  # For Linux scroll down
            for child in widget.winfo_children():
                _bind_mousewheel(child)

        # 【核心优化】
        # 在窗口内容发生变化时，不仅绑定 canvas 和 scrollable_frame，
        # 还递归绑定所有子孙组件的滚轮事件。
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 每当框架配置变化（例如添加新组件），重新绑定所有组件的滚轮事件
            _bind_mousewheel(self.scrollable_frame)

        def _on_canvas_configure(event):
            # 当画布大小变化时，调整内部框架的宽度以填充画布
            canvas.itemconfig(canvas_window_id, width=event.width)

        # 初始绑定
        _bind_mousewheel(self)
        self.scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # 将画布和滚动条布局到容器中
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # --- 下部：固定操作区 ---
        action_frame = ttkb.Frame(self)
        action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_rowconfigure(0, weight=1)

        self.action_button = ttkb.Button(action_frame, text=self._("执行操作"), bootstyle="success")
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