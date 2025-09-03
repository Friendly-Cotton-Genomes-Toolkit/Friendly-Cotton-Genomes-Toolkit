# 文件路径: ui/tabs/locus_conversion_tab.py

import tkinter as tk
import ttkbootstrap as ttkb
from typing import TYPE_CHECKING, List, Callable
import threading
from .base_tab import BaseTab
from cotton_toolkit.pipelines import run_locus_conversion

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


class LocusConversionTab(BaseTab):
    def __init__(self, parent, app: "CottonToolkitApp", translator: Callable[[str], str]):
        # --- 初始化 GUI 相关的 Tkinter 变量 ---
        self.selected_source_assembly = tk.StringVar()
        self.selected_target_assembly = tk.StringVar()
        self.region_entry_var = tk.StringVar()
        self.output_path_var = tk.StringVar()

        # 将 translator 传递给父类
        super().__init__(parent, app, translator=translator)

        if self.action_button:
            # self._ 属性在 super().__init__ 后才可用
            self.action_button.configure(text=self._("开始转换"), command=self.start_locus_conversion_task)
        self.update_from_config()

    def _create_widgets(self):
        """
        创建此选项卡内的所有 UI 元件。
        【修改】将所有需要翻译的元件都储存为 self 的属性。
        """
        parent = self.scrollable_frame
        parent.grid_columnconfigure(0, weight=1)

        # --- 储存 UI 元件 ---
        self.title_label = ttkb.Label(parent, text=_("位点坐标转换"), font=self.app.app_title_font, bootstyle="primary")
        self.title_label.grid(row=0, column=0, padx=10, pady=(10, 15), sticky="n")

        self.input_card = ttkb.LabelFrame(parent, text=_("输入参数"), bootstyle="secondary")
        self.input_card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.input_card.grid_columnconfigure(1, weight=1)

        self.source_genome_label = ttkb.Label(self.input_card, text=_("源基因组:"))
        self.source_genome_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.source_assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_source_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.source_assembly_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.target_genome_label = ttkb.Label(self.input_card, text=_("目标基因组:"))
        self.target_genome_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.target_assembly_dropdown = ttkb.OptionMenu(self.input_card, self.selected_target_assembly, _("加载中..."),
                                                        bootstyle="info")
        self.target_assembly_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        self.region_label = ttkb.Label(self.input_card, text=_("输入区域 (Chr:Start-End):"))
        self.region_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.region_entry = ttkb.Entry(self.input_card, textvariable=self.region_entry_var)
        self.region_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        self.output_card = ttkb.LabelFrame(parent, text=_("输出设置"), bootstyle="secondary")
        self.output_card.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        self.output_card.grid_columnconfigure(1, weight=1)

        self.output_label = ttkb.Label(self.output_card, text=_("结果输出CSV文件:"))
        self.output_label.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")
        self.output_entry = ttkb.Entry(self.output_card, textvariable=self.output_path_var)
        self.output_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

        self.browse_button = ttkb.Button(self.output_card, text=_("浏览..."), width=12, bootstyle="info-outline",
                                         command=lambda: self.app.event_handler._browse_save_file(self.output_entry,
                                                                                                  [("CSV 文件",
                                                                                                    "*.csv")]))
        self.browse_button.grid(row=0, column=2, padx=(5, 10))

    def retranslate_ui(self, translator: Callable[[str], str]):
        """
        【新增】当语言切换时，此方法被 UIManager 调用以更新 UI 文本。
        """
        self.title_label.configure(text=translator("位点坐标转换"))
        self.input_card.configure(text=translator("输入参数"))
        self.source_genome_label.configure(text=translator("源基因组:"))
        self.target_genome_label.configure(text=translator("目标基因组:"))
        self.region_label.configure(text=translator("输入区域 (Chr:Start-End):"))

        self.output_card.configure(text=translator("输出设置"))
        self.output_label.configure(text=translator("结果输出CSV文件:"))
        self.browse_button.configure(text=translator("浏览..."))

        if self.action_button:
            self.action_button.configure(text=translator("开始转换"))

    def update_from_config(self):
        self.update_assembly_dropdowns(
            list(self.app.genome_sources_data.keys()) if self.app.genome_sources_data else [])
        self.update_button_state(self.app.active_task_name is not None, self.app.current_config is not None)


    def update_assembly_dropdowns(self, assembly_ids: List[str]):
        # 定义此功能必需的字段
        required_fields = ['gff3_url', 'predicted_cds_url']

        all_genomes_data = self.app.genome_sources_data
        filtered_ids = []

        if all_genomes_data:
            for assembly_id in assembly_ids:
                genome_item = all_genomes_data.get(assembly_id)
                if not genome_item:
                    continue

                # 检查gff3和cds的URL是否存在
                if all(getattr(genome_item, field, None) for field in required_fields):
                    filtered_ids.append(assembly_id)

        valid_ids = filtered_ids or [_("无可用基因组")]

        # 更新源和目标两个下拉框
        self.app.ui_manager.update_option_menu(self.source_assembly_dropdown, self.selected_source_assembly, valid_ids)
        self.app.ui_manager.update_option_menu(self.target_assembly_dropdown, self.selected_target_assembly, valid_ids)



    def start_locus_conversion_task(self):
        # --- 参数验证  ---
        if not self.app.current_config:
            self.app.ui_manager.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        source_assembly = self.selected_source_assembly.get()
        target_assembly = self.selected_target_assembly.get()
        region_str = self.region_entry_var.get().strip()
        output_path = self.output_path_var.get().strip()

        if not all([source_assembly, target_assembly, region_str, output_path]) or _("加载中...") in [source_assembly,
                                                                                                      target_assembly] or _(
                "无可用基因组") in [source_assembly, target_assembly]:
            self.app.ui_manager.show_error_message(_("输入缺失"), _("请选择源/目标基因组、输入区域并指定输出文件路径。"))
            return

        try:
            from cotton_toolkit.utils.gene_utils import parse_region_string  # 导入解析函数
            region_tuple = parse_region_string(region_str)
            if not region_tuple:
                raise ValueError("Invalid region format")
        except (ValueError, ImportError):
            self.app.ui_manager.show_error_message(_("输入错误"), _("区域格式不正确，请使用 'Chr:Start-End' 格式。"))
            return

        # --- 创建通信工具和对话框 ---
        task_kwargs = {
            'config': self.app.current_config,
            'source_assembly_id':source_assembly,
            'target_assembly_id':target_assembly,
            'region': region_tuple,
            'output_path': output_path,
            'criteria_overrides': {},
        }

        # --- 使用基类方法启动任务 ---
        self._start_task(
            task_name=_("位点转换"),
            target_func=run_locus_conversion,
            kwargs=task_kwargs
        )


