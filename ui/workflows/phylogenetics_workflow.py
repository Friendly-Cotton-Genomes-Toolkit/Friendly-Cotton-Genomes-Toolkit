# 文件路径: ui/workflows/phylogenetics_workflow.py

import os
import tempfile
import logging
import shutil
from typing import TYPE_CHECKING, Dict, Any

from ui.dialogs import TrimmingDecisionDialog
from cotton_toolkit.external_functions import (
    get_alignment_statistics, run_muscle_alignment, run_trimal_trimming,
    run_iqtree_inference, visualize_tree
)
from cotton_toolkit.utils.gene_utils import validate_protein_fasta

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("ui.workflow.phylogenetics")


class PhylogeneticsWorkflow:
    """封装系统发育分析多步骤流程的专用控制器。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.context: Dict[str, Any] = {}

    def start(self, task_kwargs: dict):

        try:
            validate_protein_fasta(task_kwargs['input_fasta_path'])
        except ValueError as e:
            # 如果验证失败，直接显示错误并终止流程
            self.app.ui_manager.show_error_message(_("输入文件错误"), str(e))
            self.app.ui_manager._hide_progress_dialog()
            self.app.active_task_name = None
            return  # 停止执行

        temp_dir = tempfile.TemporaryDirectory()
        self.context = {
            "temp_dir": temp_dir,
            "aligned_path": os.path.join(temp_dir.name, "aligned.fasta"),
            "original_kwargs": task_kwargs
        }

        muscle_kwargs = {
            'config': task_kwargs['config'],
            'input_path': task_kwargs['input_fasta_path'],
            'output_path': self.context['aligned_path'],
        }

        self.app.event_handler.start_task(
            task_name=_("步骤1: MUSCLE 多序列比对"),
            target_func=run_muscle_alignment,
            kwargs=muscle_kwargs,
            on_success=lambda res: self.app.message_queue.put(("phylo_step_muscle_done", self)),
            task_key="phylo_muscle",
            is_workflow_step=True
        )

    def _handle_muscle_done(self):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None

        stats = get_alignment_statistics(self.context['aligned_path'])
        dialog = TrimmingDecisionDialog(self.app, _("比对完成 - 修建决策"), stats)
        user_choice = dialog.result

        if user_choice == "cancel":
            self.app.ui_manager.show_info_message(_("任务取消"), _("系统发育分析流程已被用户取消。"))
            self._cleanup()
            return

        self.context['user_choice'] = user_choice

        if user_choice == "trim":
            self._start_trim_step()
        else:  # user_choice == "skip"
            self._start_iqtree_step()

    def _start_trim_step(self):
        trimmed_path = os.path.join(self.context['temp_dir'].name, "trimmed.fasta")
        self.context['trimmed_path'] = trimmed_path

        trim_kwargs = {
            'config': self.context['original_kwargs']['config'],
            'input_path': self.context['aligned_path'],
            'output_path': trimmed_path,
            'gap_threshold': self.context['original_kwargs']['trim_gt'],
        }
        self.app.event_handler.start_task(
            task_name=_("步骤2: trimAl 序列修建"),
            target_func=run_trimal_trimming,
            kwargs=trim_kwargs,
            on_success=lambda res: self.app.message_queue.put(("phylo_step_trim_done", self)),
            task_key="phylo_trim",
            is_workflow_step=True
        )

    def _handle_trim_done(self):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        self._start_iqtree_step()

    def _start_iqtree_step(self):
        if self.context['user_choice'] == "trim":
            iqtree_input_path = self.context['trimmed_path']
        else:
            iqtree_input_path = self.context['aligned_path']

        # IQ-TREE的输出前缀也放在临时目录中
        self.context['iqtree_prefix'] = os.path.join(self.context['temp_dir'].name, "iqtree_result")

        iqtree_kwargs = {
            'config': self.context['original_kwargs']['config'],
            'input_path': iqtree_input_path,
            'output_prefix': self.context['iqtree_prefix'],
            'model': self.context['original_kwargs']['iqtree_model'],
            'bootstrap': self.context['original_kwargs']['iqtree_bootstrap'],
        }

        self.app.event_handler.start_task(
            task_name=_("步骤3: IQ-TREE 构建发育树"),
            target_func=run_iqtree_inference,
            kwargs=iqtree_kwargs,
            on_success=lambda res: self.app.message_queue.put(("phylo_step_iqtree_done", self)),
            task_key="phylo_iqtree",
            is_workflow_step=True
        )

    def _handle_iqtree_done(self):
        """IQ-TREE步骤完成后，启动最终的打包和可视化步骤。"""
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None

        packaging_kwargs = {'workflow_context': self.context}

        self.app.event_handler.start_task(
            task_name=_("最后一步: 打包与可视化"),
            target_func=self._package_and_visualize_worker,
            kwargs=packaging_kwargs,
            on_success=self._handle_final_packaging_done,
            task_key="phylo_package",
        )

    def _package_and_visualize_worker(self, workflow_context: Dict[str, Any], cancel_event=None,
                                      progress_callback=None) -> str:
        """在后台线程中整理所有输出文件并生成可视化结果。"""
        if progress_callback:
            progress_callback(5, _("正在整理输出文件..."))

        output_dir = workflow_context['original_kwargs']['output_dir']
        vis_kwargs = workflow_context['original_kwargs']  # 获取所有原始参数
        os.makedirs(output_dir, exist_ok=True)

        # 1. 复制 Muscle 结果
        shutil.copy(workflow_context['aligned_path'], os.path.join(output_dir, "1_muscle_aligned.fasta"))

        # 2. 复制 trimAl 结果 (如有)
        if workflow_context['user_choice'] == "trim":
            shutil.copy(workflow_context['trimmed_path'], os.path.join(output_dir, "2_trimal_trimmed.fasta"))

        if progress_callback:
            progress_callback(25, _("正在复制 IQ-TREE 结果..."))

        # 3. 复制所有 IQ-TREE 结果
        iqtree_prefix = workflow_context['iqtree_prefix']
        final_tree_file_path = ""
        for filename in os.listdir(workflow_context['temp_dir'].name):
            if filename.startswith(os.path.basename(iqtree_prefix)):
                new_name = "3_iqtree_" + filename.split(os.path.basename(iqtree_prefix), 1)[1].lstrip('.')
                shutil.copy(os.path.join(workflow_context['temp_dir'].name, filename),
                            os.path.join(output_dir, new_name))
                if filename.endswith(".treefile"):
                    final_tree_file_path = os.path.join(output_dir, new_name)

        # 4. 可视化树文件
        if final_tree_file_path:
            if progress_callback:
                progress_callback(50, _("正在生成系统发育树图片..."))

            output_format = vis_kwargs['vis_output_format']
            image_name = f"4_phylogenetic_tree.{output_format}"
            image_path = os.path.join(output_dir, image_name)

            # 将所有参数（包括 cancel_event 和 progress_callback）传递给后端函数
            visualize_tree(
                tree_file_path=final_tree_file_path,
                output_image_path=image_path,
                figsize=vis_kwargs['vis_figsize'],
                dpi=vis_kwargs['vis_dpi'],
                show_branch_labels=vis_kwargs['vis_show_branch_labels'],
                label_font_size=vis_kwargs['vis_label_font_size'],
                branch_line_width=vis_kwargs['vis_branch_line_width'],
                output_format=output_format,
                cancel_event=cancel_event,
                progress_callback=progress_callback
            )

        if progress_callback:
            progress_callback(100, _("打包完成。"))

        return output_dir

    def _handle_final_packaging_done(self, output_dir: str):
        """所有步骤完成后，显示最终成功信息并清理。"""
        final_message = _("流程已全部完成！\n\n所有结果已保存至以下文件夹:\n{}").format(output_dir)
        self.app.ui_manager.show_info_message(_("流程完成"), final_message)
        # 手动清理，因为通用处理器现在只会在最后一步运行
        self.app.active_task_name = None
        self._cleanup()

    def _cleanup(self):
        if self.context and "temp_dir" in self.context:
            try:
                self.context['temp_dir'].cleanup()
                logger.info("Phylogenetics temporary directory cleaned up.")
            except Exception as e:
                logger.error(f"Failed to cleanup phylo temp directory: {e}")
        self.context = {}