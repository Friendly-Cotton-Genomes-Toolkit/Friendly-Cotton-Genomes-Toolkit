# 文件路径: ui/dialogs.py
import re
import tkinter as tk
import time
import sys
import webbrowser

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from typing import Optional, List, Callable
from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    # 如果在测试或独立运行此模块时，_ 可能未设置
    _ = lambda s: str(s)


class BaseDialog(ttkb.Toplevel):
    """
    所有对话框的基类，提供通用功能。
    - 自动应用主程序主题
    - 模态化（出现时聚焦且父窗口无法点击）
    - 响应ESC键和窗口关闭按钮
    - 窗口居中显示
    """

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.app = parent

        self.title(title)
        self.transient(parent)  # 依附于父窗口
        self.resizable(False, False)
        self.result = None

        # --- 核心模态化和关闭逻辑 ---
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda event: self._on_close())

        # 创建一个主内容区，子类应在此添加组件
        self.main_frame = ttkb.Frame(self)
        self.main_frame.pack(expand=True, fill="both")

        # 在子类完成组件添加后，再执行grab_set和窗口居中
        self.after(10, self._finalize_setup)

    def _finalize_setup(self):
        """在UI更新后执行最终设置，确保尺寸计算准确。"""
        self.update_idletasks()
        self._center_window()
        self.grab_set()  # 锁定父窗口，发出系统提示音（如果系统支持）
        self.focus_set()

    def _center_window(self):
        """将窗口居中于父窗口。"""
        if not self.winfo_exists() or not self.app.winfo_exists():
            return
        self.update_idletasks()
        parent_x = self.app.winfo_x()
        parent_y = self.app.winfo_y()
        parent_w = self.app.winfo_width()
        parent_h = self.app.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        self.geometry(f"+{x}+{y}")

    def _on_close(self):
        """默认的关闭行为。"""
        self.result = None
        self.destroy()


class BaseScrollableDialog(BaseDialog):
    """
    可滚动对话框的基类。
    - 继承自 BaseDialog
    - 当内容超出最大高度时，自动添加垂直滚动条
    - 支持鼠标滚轮滚动
    - 智能调整窗口尺寸
    """

    def __init__(self, parent, title: str):
        # 不直接调用BaseDialog的__init__，而是手动实现类似逻辑以控制组件创建顺序
        super(BaseDialog, self).__init__(parent)
        self.app = parent

        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda event: self._on_close())

        # --- 创建滚动布局 ---
        # 外部容器，允许放置固定的页脚（如按钮栏）
        self.container = ttkb.Frame(self)
        self.container.pack(expand=True, fill='both')

        canvas_frame = ttkb.Frame(self.container)
        canvas_frame.pack(expand=True, fill='both')
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, highlightthickness=0, bd=0)
        self.scrollbar = ttkb.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview,
                                        bootstyle="round-primary")

        # 子类应在此Frame中添加内容
        self.scrollable_frame = ttkb.Frame(self.canvas)

        self.canvas_frame_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # --- 绑定事件 ---
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._resize_canvas_content)
        self._bind_mousewheel(self)  # 绑定到所有相关组件

        # 在子类完成组件添加后，再执行grab_set和窗口居中与尺寸调整
        self.after(10, self._finalize_scrollable_setup)

    def _finalize_scrollable_setup(self):
        self.update_idletasks()
        self._center_and_resize_window()
        self.grab_set()
        self.focus_set()

    def _on_frame_configure(self, event=None):
        if self.canvas.winfo_exists():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas_content(self, event):
        if self.canvas.winfo_exists():
            canvas_width = event.width
            self.canvas.itemconfig(self.canvas_frame_id, width=canvas_width)

    def _bind_mousewheel(self, widget):
        # bind_all 确保在对话框内的任何组件上滚动都有效
        widget.bind_all("<MouseWheel>", self._on_mousewheel)
        widget.bind_all("<Button-4>", self._on_mousewheel)  # For Linux
        widget.bind_all("<Button-5>", self._on_mousewheel)  # For Linux

    def _on_mousewheel(self, event):
        """统一处理各平台下的鼠标滚轮事件，更稳定。"""
        if not self.canvas.winfo_exists():
            return

        scroll_units = 0
        # For Windows and macOS
        if event.delta:
            scroll_units = -1 * (event.delta / abs(event.delta)) # -1 for up, 1 for down
        # For Linux
        elif event.num == 4: # Scroll up
            scroll_units = -1
        elif event.num == 5: # Scroll down
            scroll_units = 1

        if scroll_units != 0:
            self.canvas.yview_scroll(int(scroll_units), "units")

    def _center_and_resize_window(self):
        """智能计算并设置窗口尺寸和位置，并根据需要显示/隐藏滚动条。"""
        self.update_idletasks()

        # 根据内容决定最终宽度，同时设定一个合理的最小宽度
        req_w = max(self.scrollable_frame.winfo_reqwidth() + self.scrollbar.winfo_reqwidth() + 40, 500)

        # 页脚（如按钮栏）的高度
        footer_h = 0
        for child in self.container.winfo_children():
            # 确保只计算 canvas_frame 之外的组件
            if child.winfo_manager() == 'pack' and child != self.canvas.master:
                footer_h += child.winfo_reqheight()

        # 计算内容所需高度和屏幕最大可用高度
        content_h = self.scrollable_frame.winfo_reqheight()
        req_h = content_h + footer_h + 40 # Add some padding
        max_h = int(self.app.winfo_height() * 0.85)

        final_w = req_w
        final_h = min(req_h, max_h)

        # --- 决定是否显示滚动条 ---
        if content_h + 20 <= final_h - footer_h:
            self.scrollbar.grid_remove()
            # 移除滚动条后，调整右侧内边距，使内容居中
            self.scrollable_frame.configure(padding=(20, 20, 20, 20))
        else:
            self.scrollbar.grid()
            # 恢复为滚动条留出空间的内边距
            self.scrollable_frame.configure(padding=(20, 20, 30, 20))


        self.geometry(f'{final_w}x{final_h}')
        self._center_window()


class ConfirmationDialog(BaseDialog):
    def __init__(self, parent, title: str, message: str,
                 button1_text: str = "OK", button2_text: Optional[str] = None):
        super().__init__(parent, title)

        # 设置内边距
        self.main_frame.configure(padding=(30, 25))

        message_label = ttkb.Label(self.main_frame, text=message, wraplength=400, justify="left")
        message_label.pack(padx=10, pady=(0, 20))

        button_frame = ttkb.Frame(self.main_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        self.button1 = ttkb.Button(button_frame, text=button1_text, command=self._on_button1_click, bootstyle="primary")
        self.button1.pack(side="right", padx=5)

        if button2_text:
            self.button2 = ttkb.Button(button_frame, text=button2_text, command=self._on_button2_click,
                                       bootstyle="secondary")
            self.button2.pack(side="right", padx=5)

        self.wait_window(self)

    def _on_button1_click(self):
        self.result = True
        self.destroy()

    def _on_button2_click(self):
        self.result = False
        self._on_close()

    def _on_close(self):
        if not hasattr(self, 'result') or self.result is None:
             self.result = False
        self.destroy()


class MessageDialog(BaseDialog):
    """
    一个通用的、带主题的消息对话框。
    宽度能自适应短文本，同时支持自动识别并点击URL。
    """

    def __init__(self, parent, title: str, message: str, icon_type: str = "info",
                 buttons: Optional[List[str]] = None):
        super().__init__(parent, title)

        self.main_frame.configure(padding=(40, 30))

        if buttons is None:
            buttons = [_("确定")]

        icon_map = {"info": "ℹ", "warning": "⚠", "error": "❌", "question": "❓"}
        bootstyle_map = {"info": "info", "warning": "warning", "error": "danger", "question": "primary"}
        icon_char = icon_map.get(icon_type, "ℹ")
        color_name = bootstyle_map.get(icon_type, "info")

        # 图标
        ttkb.Label(self.main_frame, text=icon_char, bootstyle=color_name, font=("-size", 28)).pack(side="left",
                                                                                                   fill="y",
                                                                                                   padx=(0, 20))

        # 内容区
        content_frame = ttkb.Frame(self.main_frame)
        content_frame.pack(side="left", fill="both", expand=True)

        # 消息文本 (此处为简化，移除了URL点击功能，如有需要可以加回)
        ttkb.Label(content_frame, text=message, wraplength=450, justify="left").pack(fill="x", expand=True)

        # 按钮区
        button_frame = ttkb.Frame(content_frame)
        button_frame.pack(anchor="se", pady=(20, 0))
        for i, text_key in enumerate(buttons):
            style = color_name if i == 0 else f"{color_name}-outline"
            btn = ttkb.Button(button_frame, text=_(text_key), bootstyle=style,
                              command=lambda t=text_key: self.on_button_click(_(t)))
            btn.pack(side=tk.LEFT, padx=(0, 10))

        self.wait_window(self)

    def on_button_click(self, result: str):
        self.result = result
        self.destroy()


class ProgressDialog(BaseDialog):
    """任务进度弹窗。"""

    def __init__(self, parent, title: str,on_cancel: Optional[Callable] = None):
        super().__init__(parent, title)

        self.on_cancel_callback = on_cancel
        self.main_frame.configure(padding=(30, 25))
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.message_var = tk.StringVar(value=_("正在准备任务..."))
        ttkb.Label(self.main_frame, textvariable=self.message_var, wraplength=400, justify="center").grid(row=0,
                                                                                                          column=0,
                                                                                                          pady=10,
                                                                                                          padx=10)

        self.progress_bar = ttkb.Progressbar(self.main_frame, length=400, mode='determinate', bootstyle="info-striped")
        self.progress_bar.grid(row=1, column=0, pady=10, padx=10, sticky="ew")

        if on_cancel:
            cancel_button = ttkb.Button(self.main_frame, text=_("取消"), command=self._on_close,
                                        bootstyle="danger-outline")
            cancel_button.grid(row=2, column=0, pady=(10, 0))

        # 注意：进度条窗口通常不使用 wait_window，因为它不阻塞主线程

    def update_progress(self, percentage: float, text: str):
        if self.winfo_exists():
            self.message_var.set(_(text))
            self.progress_bar['value'] = percentage
            self.update_idletasks()

    def _on_close(self):
        """重写基类的关闭方法以处理取消回调。"""
        if self.on_cancel_callback:
            self.on_cancel_callback()
        self.destroy()



class FirstLaunchDialog(BaseScrollableDialog):
    """
    Welcome and information dialog shown on first launch.
    (Inherits from BaseScrollableDialog for consistent behavior)
    """

    def __init__(self, parent: tk.Tk, title: str):
        super().__init__(parent, title)

        self.resizable(False, False)
        # 初始尺寸可以给一个参考值，基类会自动调整
        self.geometry("780x700")

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.wait_window(self)

    def _create_widgets(self):
        # 直接使用基类提供的 self.scrollable_frame 和 self.container
        content_frame = self.scrollable_frame
        content_frame.grid_columnconfigure(0, weight=1)

        title_label = ttkb.Label(
            content_frame,
            text="Welcome to Friendly Cotton Genome Toolkit (FCGT)",
            font=("", 16, "bold"),
            bootstyle="primary"
        )
        title_label.pack(pady=(0, 15), fill="x", anchor="center")

        license_frame = ttkb.LabelFrame(content_frame, text="License and Disclaimer", bootstyle="secondary", padding=10)
        license_frame.pack(fill="x", pady=10)
        license_text = (
            "This program adheres to the Apache-2.0 license. You are free to use, modify, and distribute the code. "
            "However, no contributors (including the original authors and their affiliations) provide any warranty "
            "and are not liable for any issues arising from the use of this software."
        )
        ttkb.Label(license_frame, text=license_text, wraplength=650, justify="left").pack(fill="x")

        config_frame = ttkb.LabelFrame(content_frame, text="Custom Configuration", bootstyle="info", padding=10)
        config_frame.pack(fill="x", pady=10)
        config_text = (
            "The default download data for this program is all from upland cotton (Gossypium hirsutum L.) TM-1.\n",
            "If other species are needed, you can adjust the genome_sources_list.yml file yourself.\n"
            "For more information, please visit the About page"
        )
        ttkb.Label(config_frame, text=config_text, wraplength=650, justify="left").pack(fill="x")

        notes_frame = ttkb.LabelFrame(content_frame, text="Special Notice", bootstyle="warning", padding=10)
        notes_frame.pack(fill="x", expand=True, pady=10)

        points = [
            ("Please monitor the log system promptly. "
             "When the output results are unsatisfactory, there may be useful information in the logs that requires attention or handling."),
            ("Typically, this program supports both gene (e.g., Gohir.A12G149800) and transcript "
             "(e.g., Gohir.A12G149800.2) inputs. However, in some cases, one type of input may not work. "
             "See the following points for details."),
            ("If the input is a gene ID and the data is stored in transcript format, the gene will be converted to the "
             "default first transcript (e.g., Gohir.A12G149800.1) for searching. If the data is stored in gene format, "
             "the search proceeds normally."),
            ("Conversely, if the input is a transcript ID but the data is stored in gene format, the transcript suffix "
             "(e.g., .1, .2) will be removed, and the search will be performed using the gene ID "
             "(e.g., Gohir.A12G149800). If the data is stored in transcript format, the search proceeds normally."),
            ("In summary, for high-precision data requirements, it is recommended to use transcript IDs for input "
             "and to try multiple transcripts, not just the first one.")
        ]

        for i, point in enumerate(points, 1):
            point_frame = ttkb.Frame(notes_frame)
            point_frame.pack(fill="x", pady=5)
            num_label = ttkb.Label(point_frame, text=f"{i}.", font=("", 10, "bold"), bootstyle="warning")
            num_label.pack(side="left", anchor="n", padx=(0, 5))
            text_label = ttkb.Label(point_frame, text=point, wraplength=650, justify="left")
            text_label.pack(side="left", fill="x", expand=True)

        # 将按钮放置在 self.container 中，使其固定在底部
        button_frame = ttkb.Frame(self.container, padding=(0, 15, 0, 20))
        button_frame.pack(side="bottom", fill="x")

        ok_button = ttkb.Button(
            button_frame,
            text="I have read and agree",
            command=self._on_close,
            bootstyle="success"
        )
        ok_button.pack(anchor="center")

    def _on_close(self):
        self.destroy()


class HelpDialogBox(BaseScrollableDialog):
    def __init__(self, parent: tk.Tk, title: str, params_data: List[tuple]):
        super().__init__(parent, title)

        content_frame = self.scrollable_frame

        # 移除默认padding，使用自己的布局
        content_frame.configure(padding=20)

        left_column = ttkb.Frame(content_frame)
        left_column.pack(side="left", fill="y", expand=True, padx=(0, 15), anchor="n")
        right_column = ttkb.Frame(content_frame)
        right_column.pack(side="left", fill="y", expand=True, padx=(15, 0), anchor="n")

        num_left = (len(params_data) + 1) // 2
        for i, (title_en, title_local, desc, note) in enumerate(params_data):
            target_column = left_column if i < num_left else right_column

            lf = ttkb.LabelFrame(target_column, text=f"{title_en}: {title_local}", bootstyle="info", padding=10)
            lf.pack(fill="x", pady=(0, 15), expand=True)

            full_text = f"{desc}\n{note}"
            lbl = ttkb.Label(lf, text=full_text, wraplength=380)
            lbl.pack(fill="x", expand=True)

        # 添加页脚按钮
        button_frame = ttkb.Frame(self.container, padding=(0, 10, 0, 10))
        button_frame.pack(side="bottom", fill="x")
        ok_button = ttkb.Button(button_frame, text="OK", command=self.destroy, bootstyle="primary")
        ok_button.pack()

        self.wait_window(self)


class HelpDialogSheet(BaseScrollableDialog):
    """
    一个专门用于显示帮助信息和数据格式示例的对话框 (表格样式)。
    """

    def __init__(self, parent, title: str, message: str, headers: List[str], data: List[List[str]]):
        super().__init__(parent, title)

        # 在可滚动区域添加内容
        self.scrollable_frame.configure(padding=(20, 20))

        message_label = ttkb.Label(self.scrollable_frame, text=message, wraplength=550, justify="left")
        message_label.pack(pady=(0, 15), fill="x")

        table_frame = ttkb.Frame(self.scrollable_frame)
        table_frame.pack(fill="x", expand=True)

        tree = ttkb.Treeview(table_frame, columns=headers, show="headings", bootstyle="primary")
        for header in headers:
            tree.heading(header, text=header)
            tree.column(header, anchor="w", width=120)
        for row_data in data:
            tree.insert("", "end", values=row_data)
        tree.pack(side="left", fill="x", expand=True)

        scrollbar = ttkb.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # 在固定页脚区域添加按钮
        button_frame = ttkb.Frame(self.container, padding=(0, 15, 0, 15))
        button_frame.pack(side="bottom", fill="x")
        ok_button = ttkb.Button(button_frame, text=_("确定"), command=self.destroy, bootstyle="primary")
        ok_button.pack()

        self.wait_window(self)


class TrimmingDecisionDialog(BaseDialog):
    """一个用于决定是否执行trimAl的交互式对话框。"""

    def __init__(self, parent, title: str, stats: dict):
        super().__init__(parent, title)

        self.result = "cancel"  # 默认结果为取消

        # 直接配置基类提供的 main_frame
        self.main_frame.configure(padding=20)

        # --- 显示统计信息 ---
        stats_frame = ttkb.LabelFrame(self.main_frame, text=_("比对结果统计"), bootstyle="primary")
        stats_frame.pack(fill="x", pady=(0, 15))

        stats_text = (
            f"{_('序列数量')}: {stats.get('sequences', 'N/A')}\n"
            f"{_('比对长度')}: {stats.get('length', 'N/A')}\n"
            f"{_('总缺口(Gaps)比例')}: {stats.get('gap_percentage', 0.0):.2f}%"
        )
        ttkb.Label(stats_frame, text=stats_text, justify="left").pack(padx=10, pady=10, anchor="w")

        # --- 显示程序建议 ---
        reco_frame = ttkb.LabelFrame(self.main_frame, text=_("程序建议"), bootstyle="info")
        reco_frame.pack(fill="x", pady=(0, 20))

        reco_label = ttkb.Label(reco_frame, text=stats.get('recommendation', _("无建议")), wraplength=450,
                                justify="left")
        reco_label.pack(padx=10, pady=10, anchor="w")

        # --- 创建按钮 ---
        button_frame = ttkb.Frame(self.main_frame)
        button_frame.pack(fill="x")
        button_frame.columnconfigure((0, 1, 2), weight=1)

        self.trim_button = ttkb.Button(button_frame, text=_("执行修建 (推荐)"), command=self._on_trim,
                                       bootstyle="success")
        self.trim_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.skip_button = ttkb.Button(button_frame, text=_("跳过修建"), command=self._on_skip,
                                       bootstyle="warning-outline")
        self.skip_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.cancel_button = ttkb.Button(button_frame, text=_("取消任务"), command=self._on_cancel,
                                         bootstyle="danger")
        self.cancel_button.grid(row=0, column=2, padx=5, sticky="ew")

        # 居中和模态化由 BaseDialog._finalize_setup() 自动处理
        self.wait_window(self)

    def _on_trim(self):
        self.result = "trim"
        self.destroy()

    def _on_skip(self):
        self.result = "skip"
        self.destroy()

    def _on_cancel(self):
        self.result = "cancel"
        self.destroy()


class CopyrightDialog(BaseDialog):
    """
    一个通用的对话框，用于显示版权、所用软件和免责声明。
    """

    def __init__(self, parent, title: str, software_list: List[str]):
        super().__init__(parent, title)

        # 基类已处理 resizable, protocol, bind, transient, grab_set

        # 直接使用和配置 self.main_frame
        self.main_frame.configure(padding=(30, 25))

        # --- Message Section ---
        message_frame = ttkb.LabelFrame(self.main_frame, text=_("使用的核心工具"), bootstyle="info", padding=15)
        message_frame.pack(fill="x", pady=(0, 15))

        software_text = "\n".join([f"  • {name}" for name in software_list])
        main_message = _(
            "本分析流程依赖以下核心开源软件：\n\n"
            "{software_list}\n\n"
            "请在发表学术成果时恰当引用这些工具。\n"
            "详细的引用信息和许可证请参阅主程序的“关于”页面。"
        ).format(software_list=software_text)

        ttkb.Label(message_frame, text=main_message, wraplength=450, justify="left").pack(fill="x")

        # --- Disclaimer Section ---
        disclaimer_frame = ttkb.LabelFrame(self.main_frame, text=_("免责声明"), bootstyle="warning", padding=15)
        disclaimer_frame.pack(fill="x", pady=(0, 20))

        disclaimer_text = _(
            "上述工具均为用户自行下载、安装与使用，本程序不涉及分发、修改等内容。 "
            "本程序遵循 Apache-2.0 许可证，旨在合法调用和使用上述工具，用户需自行确保对各工具许可证的遵循。"
        )
        ttkb.Label(disclaimer_frame, text=disclaimer_text, wraplength=450, justify="left").pack(fill="x")

        # --- Button ---
        button_frame = ttkb.Frame(self.main_frame)
        button_frame.pack(fill="x")
        ok_button = ttkb.Button(button_frame, text=_("确定"), command=self.destroy, bootstyle="primary")
        ok_button.pack()

        # 窗口居中由基类自动完成
        self.wait_window(self)


class AboutDialog(BaseScrollableDialog):
    def __init__(self, parent, title: str):
        super().__init__(parent, title)

        self._labels_to_wrap = []
        self._populate_content(self.scrollable_frame)

        # 添加一个固定的页脚按钮栏
        self.button_frame = ttkb.Frame(self.container, padding=(0, 10, 0, 10))
        self.button_frame.pack(side="bottom", fill="x")
        ok_button = ttkb.Button(self.button_frame, text=_("确定"), command=self.destroy, bootstyle="primary")
        ok_button.pack()

        # 绑定内容动态换行
        self.canvas.bind("<Configure>", self._resize_wrapping_labels)

        self.wait_window(self)

    def _resize_wrapping_labels(self, event):
        super()._resize_canvas_content(event)  # 调用父类的方法
        canvas_width = event.width
        for lbl in self._labels_to_wrap:
            if lbl.winfo_exists():
                lbl.configure(wraplength=canvas_width - 30)


    def _populate_content(self, parent):
        header_font = self.app.app_font_bold
        content_font = self.app.app_font
        link_font = self.app.app_font.copy()
        link_font.configure(underline=True)

        def add_label(text, font, justify="left", wrappable=True, **kwargs):
            lbl = ttkb.Label(parent, text=text, font=font, justify=justify, **kwargs)
            lbl.pack(fill="x", anchor="w", pady=(0, 2), padx=5)
            if wrappable:
                self._labels_to_wrap.append(lbl)
            return lbl

        def add_separator():
            ttkb.Separator(parent).pack(fill="x", anchor="w", pady=10)

        add_label(_("程序名称") + ": Friendly Cotton Genomes Toolkit (FCGT)", content_font)
        add_label(_("版本") + f": {PKG_VERSION}", content_font)
        add_label(_("项目地址") + ":", content_font, wrappable=False)
        gh_link = add_label(PKG_PUBLISH_URL, link_font, wrappable=False, bootstyle="info", cursor="hand2")
        gh_link.bind("<Button-1>", lambda e: webbrowser.open(PKG_PUBLISH_URL))
        add_separator()
        add_label(_("致谢与引用"), header_font)
        add_label(_("本工具依赖 CottonGen 提供的权威数据，感谢其团队持续的开放和维护。"), content_font)

        add_label("CottonGen " + _("文章:"), header_font).pack(pady=(10, 5))
        add_label("• Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. Plants 10(12), 2805.", content_font)
        add_label("• Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. Nucleic Acids Research 42(D1), D1229-D1236.", content_font)

        add_label("BLAST+ " + _("文章:"), header_font).pack(pady=(10, 5))
        add_label("• Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. BLAST+: architecture and applications. BMC Bioinformatics. 2009 Dec 15;10:421. doi: 10.1186/1471-2105-10-421. PMID: 20003500; PMCID: PMC2803857.", content_font)

        add_label(_("基因组引用文献:"), header_font).pack(pady=(10, 5))
        citations = [
            "• NAU-NBI_v1.1: Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015",
            "• UTX-JGI-Interim-release_v1.1:",
            "  Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].",
            "  Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .",
            "  Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.",
            "  Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.",
            "• HAU_v1 / v1.1: Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03",
            "• ZJU-improved_v2.1_a1: Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. Nature genetics. 2019 Jan;51(1):164.",
            "• CRI_v1: Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.",
            "• WHU_v1: Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4",
            "• UTX_v2.1: Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.",
            "• UTX_v3.1: Chen et al. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement Nat Genet 20 April 2020."
        ]
        for cit in citations: add_label(cit, content_font)
        add_separator()
        add_label(_("许可证"), header_font)
        add_label(_("本软件使用 Apache License 2.0。您可以自由地使用、修改和分发代码，但任何贡献者（包括原始作者及其所属单位）均不提供任何担保，且不对使用该软件产生的任何问题承担责任。"), content_font)
        add_separator()
        add_label(_("免责声明"), header_font)
        add_label("1.\u00A0" + _("工具角色：本软件仅提供技术框架服务，自身不托管或分发任何基因组数据。"), content_font)
        add_label("2.\u00A0" + _("用户责任：所有基因组数据的下载、处理和分析均由用户独立执行。用户有责任确保其行为遵守原始数据提供方设定的所有许可、使用条款和发表限制。"), content_font)
        add_label("3.\u00A0" + _("无担保声明：本工具及其生成的分析结果仅供科研目的“按原样”提供，我们对其准确性或特定用途的适用性不作任何保证。"), content_font)

        # Bind scroll events to all newly created child widgets
        for child in parent.winfo_children():
            # This is a simplification; a more robust solution might be needed if there are nested frames
            child.bind("<MouseWheel>", lambda e: parent.master.yview_scroll(int(-1 * (e.delta / 120)), "units"))
            child.bind("<Button-4>", lambda e: parent.master.yview_scroll(-1, "units"))
            child.bind("<Button-5>", lambda e: parent.master.yview_scroll(1, "units"))


    def _center_and_resize(self):
        self.update_idletasks()
        final_w = 1000
        self.geometry(f'{final_w}x1')
        self.update_idletasks()
        req_h = self.scrollable_frame.winfo_reqheight() + self.button_frame.winfo_reqheight() + 45
        max_h = int(self.app.winfo_height() * 0.85)
        final_h = min(req_h, max_h)
        parent_x, parent_y = self.app.winfo_x(), self.app.winfo_y()
        parent_w, parent_h = self.app.winfo_width(), self.app.winfo_height()
        x = parent_x + (parent_w - final_w) // 2
        y = parent_y + (parent_h - final_h) // 2
        self.geometry(f"{final_w}x{final_h}+{x}+{y}")