# 文件路径: ui/tabs/phylogenetics_tab.py

import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable
import ttkbootstrap as ttkb
from ttkbootstrap.tooltip import ToolTip

from .base_tab import BaseTab
from ..dialogs import CopyrightDialog, HelpDialogBox
from ..workflows.phylogenetics_workflow import PhylogeneticsWorkflow

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class PhylogeneticsTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            self.start_button = self.action_button
            self.start_button.configure(text=self._("开始构建"), command=self._start_phylo_task)

            # 获取父级框架 (action_frame)
            action_frame = self.start_button.master

            # 创建新的“版权信息”按钮
            self.copyright_button = ttkb.Button(
                action_frame,
                text=self._("版权信息"),
                command=self._show_copyright_info,
                bootstyle="info-outline"  # 使用次要样式，不那么突出
            )
            # 使用 grid 布局，将版权按钮放在第 0 列
            self.copyright_button.grid(row=0, column=0, sticky="se", padx=(0, 10), pady=10)

            # 将原始的“开始构建”按钮放在第 1 列
            self.start_button.grid(row=0, column=1, sticky="se", padx=(0, 15), pady=10)

    def _create_widgets(self):
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        # --- 标题与帮助按钮 ---
        title_frame = ttkb.Frame(parent)
        title_frame.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        self.title_label = ttkb.Label(title_frame, text=self._("系统发育分析"), font=self.app.app_title_font,
                                      bootstyle="primary")
        self.title_label.pack(side="left", anchor="center")

        self.help_button = ttkb.Button(
            title_frame,
            text="?",
            command=self._show_help_dialog,
            bootstyle="primary-outline",
            width=2
        )
        self.help_button.pack(side="left", anchor="center", padx=(10, 0))
        ToolTip(self.help_button, text=self._("显示帮助信息"))


        # --- 输入/输出卡片 ---
        io_card = ttkb.LabelFrame(parent, text=self._("文件路径"), bootstyle="secondary")
        io_card.grid(row=1, column=0, sticky="new", padx=10, pady=5)
        io_card.grid_columnconfigure(1, weight=1)

        # 输入文件
        self.input_file_label = ttkb.Label(io_card, text=self._("输入FASTA文件:"))
        self.input_file_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.input_file_entry = ttkb.Entry(io_card)
        self.input_file_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        self.browse_input_button = ttkb.Button(io_card, text=self._("浏览..."), width=12,
                                               command=self._browse_input_file, bootstyle="info-outline")
        self.browse_input_button.grid(row=0, column=2, padx=(0, 10), pady=10)

        # 输出目录
        self.output_file_label = ttkb.Label(io_card, text=self._("输出文件夹:"))
        self.output_file_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.output_file_entry = ttkb.Entry(io_card)
        self.output_file_entry.grid(row=1, column=1, padx=5, pady=10, sticky="ew")
        self.browse_output_button = ttkb.Button(io_card, text=self._("浏览..."), width=12,
                                                command=self._browse_output_directory, bootstyle="info-outline")
        self.browse_output_button.grid(row=1, column=2, padx=(0, 10), pady=10)

        # --- trimAl 参数卡片 ---
        trimal_card = ttkb.LabelFrame(parent, text=self._("trimAl 修剪参数 (可选步骤 2)"), bootstyle="secondary")
        trimal_card.grid(row=2, column=0, sticky="new", padx=10, pady=5)
        trimal_card.grid_columnconfigure(1, weight=1)

        self.use_trimming_var = tk.BooleanVar(value=True)
        self.trimming_check = ttkb.Checkbutton(trimal_card, text=self._("启用 trimAl 修剪序列"),
                                               variable=self.use_trimming_var, bootstyle="round-toggle",
                                               command=self._toggle_trimal_params)
        self.trimming_check.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        self.trim_gt_label = ttkb.Label(trimal_card, text=self._("Gap Threshold:"))
        self.trim_gt_label.grid(row=1, column=0, padx=(20, 5), pady=5, sticky="w")
        self.trim_gt_entry = ttkb.Entry(trimal_card)
        self.trim_gt_entry.insert(0, "0.8")
        self.trim_gt_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ToolTip(self.trim_gt_label,
                text=self._("trimAl参数(-gt): 保留比对后序列列中gap比例低于此值的列。范围0-1，值越小越严格。"))

        # --- IQ-TREE 参数卡片 ---
        iqtree_card = ttkb.LabelFrame(parent, text=self._("IQ-TREE 建树参数 (步骤 3)"), bootstyle="secondary")
        iqtree_card.grid(row=3, column=0, sticky="new", padx=10, pady=5)
        iqtree_card.grid_columnconfigure(1, weight=1)

        self.iqtree_model_label = ttkb.Label(iqtree_card, text=self._("替换模型 (-m):"))
        self.iqtree_model_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.iqtree_model_entry = ttkb.Entry(iqtree_card)
        self.iqtree_model_entry.insert(0, "MFP")
        self.iqtree_model_entry.grid(row=0, column=1, padx=5, pady=10, sticky="w")
        ToolTip(self.iqtree_model_label,
                text=self._("IQ-TREE的替换模型。'MFP' (ModelFinder Plus) 会自动测试并选择最佳模型。"))

        self.iqtree_bs_label = ttkb.Label(iqtree_card, text=self._("Bootstrap 次数 (-B):"))
        self.iqtree_bs_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.iqtree_bs_entry = ttkb.Entry(iqtree_card)
        self.iqtree_bs_entry.insert(0, "1000")
        self.iqtree_bs_entry.grid(row=1, column=1, padx=5, pady=10, sticky="w")
        ToolTip(self.iqtree_bs_label, text=self._("超快 bootstrap 的重复次数，用于评估分支的置信度。"))

        # --- 可视化参数卡片 ---
        vis_card = ttkb.LabelFrame(parent, text=self._("可视化参数"), bootstyle="secondary")
        vis_card.grid(row=4, column=0, sticky="new", padx=10, pady=5)
        vis_card.grid_columnconfigure((1, 3), weight=1)

        # 图片尺寸 (一行两列)
        size_label = ttkb.Label(vis_card, text=self._("图片尺寸 (英寸):"))
        size_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        size_frame = ttkb.Frame(vis_card)
        size_frame.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.fig_width_entry = ttkb.Entry(size_frame, width=8)
        self.fig_width_entry.insert(0, "10")  # 默认宽10英寸
        self.fig_width_entry.pack(side="left", fill="x", expand=True)
        size_x_label = ttkb.Label(size_frame, text=" x ")
        size_x_label.pack(side="left")
        self.fig_height_entry = ttkb.Entry(size_frame, width=8)
        self.fig_height_entry.insert(0, "8")  # 默认高8英寸
        self.fig_height_entry.pack(side="left", fill="x", expand=True)

        # 分辨率 DPI
        dpi_label = ttkb.Label(vis_card, text=self._("分辨率 (DPI):"))
        dpi_label.grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")
        self.dpi_entry = ttkb.Entry(vis_card)
        self.dpi_entry.insert(0, "300")  # 学术发表常用300DPI
        self.dpi_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # 标签字号
        font_label = ttkb.Label(vis_card, text=self._("标签字号:"))
        font_label.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="w")
        self.font_size_entry = ttkb.Entry(vis_card)
        self.font_size_entry.insert(0, "10")
        self.font_size_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # 线条宽度
        line_label = ttkb.Label(vis_card, text=self._("线条宽度:"))
        line_label.grid(row=1, column=2, padx=(20, 5), pady=5, sticky="w")
        self.line_width_entry = ttkb.Entry(vis_card)
        self.line_width_entry.insert(0, "1.5")
        self.line_width_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        # 显示分支长度
        self.show_branch_labels_var = tk.BooleanVar(value=False)  # 默认不显示，图片更简洁
        self.branch_labels_check = ttkb.Checkbutton(vis_card, text=self._("显示分支长度数值"),
                                                    variable=self.show_branch_labels_var, bootstyle="round-toggle")
        self.branch_labels_check.grid(row=2, column=0, padx=10, pady=10, sticky="w")

        # 输出格式
        format_label = ttkb.Label(vis_card, text=self._("输出格式:"))
        format_label.grid(row=2, column=2, padx=(20, 5), pady=5, sticky="w")
        self.output_format_var = tk.StringVar(value="png")
        self.output_format_menu = ttkb.OptionMenu(vis_card, self.output_format_var, "png", "png", "pdf", "svg")
        self.output_format_menu.grid(row=2, column=3, padx=5, pady=5, sticky="ew")

        self._toggle_trimal_params()

    def _toggle_trimal_params(self):
        """根据复选框状态，启用或禁用trimAl的参数控件。"""
        if self.use_trimming_var.get():
            self.trim_gt_label.configure(state="normal")
            self.trim_gt_entry.configure(state="normal")
        else:
            self.trim_gt_label.configure(state="disabled")
            self.trim_gt_entry.configure(state="disabled")

    def _browse_input_file(self):
        path = filedialog.askopenfilename(title=self._("选择输入的FASTA文件"),
                                          filetypes=[("FASTA files", "*.fasta *.fa"), ("All files", "*.*")])
        if path:
            self.input_file_entry.delete(0, tk.END)
            self.input_file_entry.insert(0, path)

    def _browse_output_directory(self):
        path = filedialog.askdirectory(title=self._("选择输出文件夹"))
        if path:
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, path)


    def _show_help_dialog(self):
        """显示功能帮助对话框。"""
        params_data = [
            (
                "Function Overview", self._("功能概述"),
                self._("本功能整合了多个生物信息学工具，提供一个从多序列比对到系统发育树构建和可视化的完整流程。"),
                self._("流程步骤: 1. MUSCLE多序列比对 -> 2. (可选) trimAl序列修剪 -> 3. IQ-TREE最大似然法建树 -> 4. 结果可视化与打包。")
            ),
            (
                "Input Data Requirements", self._("输入数据要求"),
                self._("1. 序列类型: 为了保证远源物种间比对的准确性，本功能目前仅接受蛋白质（氨基酸）序列的FASTA文件。\n"
                     "2. 同源性: 输入文件中的所有序列必须是同源的（即来自同一祖先基因），如同一个基因家族的成员。非同源序列将导致无意义的进化树。"),
                self._("注意: 请在开始分析前，通过BLAST等方法确认序列间的同源性。")
            ),
            (
                "Protein vs. Nucleotide", self._("蛋白质 vs. 核酸序列"),
                self._("本工作流被配置为使用蛋白质序列，因为：\n"
                     "• 蛋白质有20种氨基酸，而核酸只有4种碱基，前者在进化关系较远时能提供更多信息，减少随机相似性。\n"
                     "• 密码子具有简并性，核酸序列的某些位点突变可能不改变氨基酸，蛋白质序列更能反映功能上的选择压力。"),
                self._("然而，在分析亲缘关系非常近的物种或研究同义/非同义替换率(dN/dS)时，基于密码子的核酸序列比对（本自动化流程不支持）是更合适的选择。")
            ),
            (
                "Key Parameters", self._("核心参数解释"),
                self._("• Gap Threshold (trimAl): 用于移除比对后充满缺口（gap）的列。值越低（如0.7），修剪越严格，保留的列中允许的缺口比例越低。\n"
                     "• Bootstrap (IQ-TREE): 一种评估进化树分支可靠性的统计学方法。1000次重复是常用标准，结果（支持率）会标注在进化树的分支上。"),
                self._("建议: 如果比对结果的Gap比例很高（>20%），强烈建议执行trimAl修剪。程序会在比对后弹出窗口给出建议。")
            )
        ]
        HelpDialogBox(self.app, self._("系统发育分析帮助"), params_data)

    def _start_phylo_task(self):
        # --- 1. 验证输入 ---
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        tools = self.app.current_config.advanced_tools
        use_trimming = self.use_trimming_var.get()
        if not tools.muscle_path or not tools.iqtree_path or (use_trimming and not tools.trimal_path):
            self.app.ui_manager.show_error_message(_("配置缺失"),
                                                   _("请先在'配置编辑器'的'高级功能'中设置MUSCLE, IQ-TREE和trimAl的完整路径。"))
            return

        input_path = self.input_file_entry.get().strip()
        output_dir = self.output_file_entry.get().strip()
        if not input_path or not output_dir:
            self.app.ui_manager.show_error_message(_("输入缺失"),
                                                   _("请输入有效的输入文件和输出文件夹路径。"))  # <-- 修改这里的文本
            return

        try:
            trim_gt = float(self.trim_gt_entry.get())
            iqtree_bootstrap = int(self.iqtree_bs_entry.get())
            fig_width = float(self.fig_width_entry.get())
            fig_height = float(self.fig_height_entry.get())
            dpi = int(self.dpi_entry.get())
            font_size = int(self.font_size_entry.get())
            line_width = float(self.line_width_entry.get())
        except ValueError:
            self.app.ui_manager.show_error_message(_("参数错误"),
                                                   _("分析参数和可视化参数中的所有输入框都必须是有效数字。"))
            return

        # --- 2. 准备并启动任务 ---
        task_kwargs = {
            'config': self.app.current_config,
            'input_fasta_path': input_path,
            'output_dir': output_dir,
            'trim_gt': trim_gt,
            'iqtree_model': self.iqtree_model_entry.get().strip(),
            'iqtree_bootstrap': iqtree_bootstrap,
            'vis_figsize': (fig_width, fig_height),
            'vis_dpi': dpi,
            'vis_show_branch_labels': self.show_branch_labels_var.get(),
            'vis_label_font_size': font_size,
            'vis_branch_line_width': line_width,
            'vis_output_format': self.output_format_var.get(),
        }

        # 创建一个工作流实例并启动它
        workflow = PhylogeneticsWorkflow(self.app)
        workflow.start(task_kwargs)

    def update_from_config(self):
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)

    def _show_copyright_info(self):
        """显示一个包含版权和所用软件信息的对话框。"""
        CopyrightDialog(
            parent=self.app,
            title=self._("版权与软件信息"),
            software_list=["MUSCLE", "trimAl", "IQ-TREE"],
        )