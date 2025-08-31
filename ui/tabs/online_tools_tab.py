# 文件路径: ui/tabs/online_tools_tab.py

import tkinter as tk
from tkinter import ttk
import webbrowser
from typing import TYPE_CHECKING, List, Callable, Dict, Any

import ttkbootstrap as ttkb

from .base_tab import BaseTab
from ..dialogs import HelpDialogBox

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class OnlineToolsTab(BaseTab):
    """ “常用在线工具”选项卡 """

    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        """
        初始化选项卡。
        此选项卡主要用于展示信息和提供外部链接，因此结构相对简单。
        """
        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        # 此选项卡没有主要的“执行”按钮，可以禁用或隐藏它
        if self.action_button:
            self.action_button.pack_forget()

    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        """
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        # 1. 顶部标题
        title_label = ttkb.Label(parent, text=_("常用在线工具"), font=self.app.app_title_font,
                                 bootstyle="primary")
        title_label.pack(pady=(10, 20), fill="x", anchor="center")

        # 2. 数据驱动的UI生成，便于拓展
        # 在这里定义所有工具的信息。未来只需向此列表添加新字典即可。
        tools_data = [
            {
                "name": "MEME Suite",
                "url": "https://meme-suite.org/meme/",
                "description": _(
                    "MEME (Multiple EM for Motif Elicitation) 是一套用于在 DNA、RNA 或蛋白质序列数据中发现和分析基序（motif）的生物信息学工具集。它提供多种功能来识别、比较和扫描序列中的模式。"
                ),
                "features": [
                    {
                        "name": "MEME",
                        "description": _("从您提供的一组序列（DNA、RNA或蛋白质）中，自动找出反复出现的、重要的未知模式（基序）。"),
                        "url": "https://meme-suite.org/meme/tools/meme",
                        "help_params": [
                            ("Function", "功能", _("从未对齐的序列中发现新的、无间隙的基序。"), _("适用于寻找转录因子结合位点等未知模式。")),
                            ("Input", "输入", _("FASTA 格式的 DNA、RNA 或蛋白质序列。"), _("序列数量建议在合理范围内，太多或太少都可能影响结果。")),
                            ("Output", "输出", _("HTML 报告，包含发现的基序的 Logo、p-value、位置等信息。"), _("结果中的 E-value 是评估基序显著性的关键指标。"))
                        ]
                    },
                    {
                        "name": "Tomtom",
                        "description": _("将您找到的未知基序（比如用MEME发现的）与一个庞大的已知基序数据库进行比对，告诉您它可能是什么。"),
                        "url": "https://meme-suite.org/meme/tools/tomtom",
                        "help_params": [
                            ("Function", "功能", _("将一个或多个查询基序与已知基序数据库进行比较。"), _("用于注释和鉴定通过 MEME 等工具发现的未知基序。")),
                            ("Input", "输入", _("查询基序（MEME格式）和选择一个目标数据库。"), _("数据库的选择很关键，应选择与研究物种相关的数据库。")),
                            ("Output", "输出", _("一个匹配列表，按统计显著性排序，显示查询基序与数据库中哪个基序最相似。"), _("关注 q-value 和 p-value 来判断匹配的可靠性。"))
                        ]
                    },
                    {
                        "name": "FIMO",
                        "description": _("在一大段序列（比如整个基因组或基因启动子区域）中，精确地寻找一个“已知”基序出现的所有位置。"),
                        "url": "https://meme-suite.org/meme/tools/fimo",
                        "help_params": [
                            ("Function", "功能", _("在一个序列数据库中扫描与给定基序匹配的位点。"), _("当您有一个已知的基序（如特定的启动子元件）并想找到它在基因组中的所有实例时非常有用。")),
                            ("Input", "输入", _("一个或多个基序（MEME格式）和一个FASTA格式的序列数据库。"), _("可以调整 p-value 阈值来控制扫描的严格程度。")),
                            ("Output", "输出", _("一个报告，列出所有找到的匹配位点、它们的位置、得分和 p-value。"), "")
                        ]
                    },
                    {
                        "name": "CentriMo",
                        "description": _("分析一个已知基序是否集中出现在您序列的特定区域（最典型的是中央位置）。"),
                        "url": "https://meme-suite.org/meme/tools/centrimo",
                        "help_params": [
                            ("Function", "功能", _("在一个序列集合中，寻找相对于序列中心位置显著富集的基序。"), _("常用于 ChIP-seq 数据分析，以确定某个蛋白是否倾向于结合在序列片段的中心。")),
                            ("Input", "输入", _("一个基序文件和一个FASTA格式的序列文件。"), _("序列应预先对齐，例如都以峰值（peak）为中心。")),
                            ("Output", "输出", _("图形化展示基序在序列中的位置分布，并提供统计显著性。"), "")
                        ]
                    }
                ]
            },
            # --- 在这里添加下一个工具的字典 ---
            # {
            #     "name": "Next Tool",
            #     "url": "http://example.com",
            #     "description": _("..."),
            #     "features": [...]
            # }
        ]

        # 3. 循环创建每个工具的UI“卡片”
        for tool_data in tools_data:
            self._create_tool_card(parent, tool_data)

    def _create_tool_card(self, parent: ttk.Frame, tool_data: Dict[str, Any]):
        """为单个工具创建UI卡片，包含描述、功能列表、链接和帮助按钮。"""
        # 主容器
        card_frame = ttkb.LabelFrame(parent, text=tool_data["name"], bootstyle="info", padding=15)
        card_frame.pack(fill="x", padx=10, pady=10)
        card_frame.grid_columnconfigure(0, weight=1)

        # 工具描述
        desc_label = ttkb.Label(card_frame, text=tool_data["description"], wraplength=700, justify="left")
        desc_label.pack(fill="x", pady=(0, 10))

        # 功能标题
        features_header = ttkb.Label(card_frame, text=_("主要功能与链接"), font=self.app.app_font_bold)
        features_header.pack(fill="x", pady=(10, 5))

        # 循环创建每个功能的条目
        for feature in tool_data["features"]:
            feature_frame = ttkb.Frame(card_frame)
            feature_frame.pack(fill="x", pady=4)
            feature_frame.columnconfigure(1, weight=1) # 让链接部分可扩展

            # 功能名称
            name_label = ttkb.Label(feature_frame, text=f"{feature['name']}:", font=self.app.app_font_bold)
            name_label.grid(row=0, column=0, sticky="w", padx=(0, 8))

            # 功能描述和链接
            link_text = feature['description']
            link_label = ttkb.Label(feature_frame, text=link_text, wraplength=600, justify="left",
                                    bootstyle="primary", cursor="hand2")
            link_label.grid(row=0, column=1, sticky="w")
            link_label.bind("<Button-1>", lambda e, url=feature['url']: self._open_link(url))

            # 帮助按钮
            help_button = ttkb.Button(
                feature_frame, text="?", bootstyle="secondary-outline", width=3,
                command=lambda p=feature['help_params']: self._show_help_dialog(p)
            )
            help_button.grid(row=0, column=2, sticky="e", padx=(10, 0))

    def _open_link(self, url: str):
        """在新浏览器窗口中打开URL。"""
        try:
            webbrowser.open(url, new=2)
        except Exception as e:
            self.app.log_message(f"Error opening URL {url}: {e}", "error")
            self.app.ui_manager.show_error_message(
                _("打开链接失败"),
                f"{_('无法打开链接:')}\n{url}\n{_('错误:')} {e}"
            )

    def _show_help_dialog(self, params_data: List[tuple]):
        """
        显示一个帮助对话框，解释特定功能的参数。
        """
        HelpDialogBox(
            parent=self.app,
            title=_("使用帮助"),
            params_data=params_data
        )