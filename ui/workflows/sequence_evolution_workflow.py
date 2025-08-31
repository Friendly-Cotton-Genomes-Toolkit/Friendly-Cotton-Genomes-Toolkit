# 文件路径: ui/workflows/sequence_evolution_workflow.py

import logging
import os
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Dict, Callable

# 导入新的后端逻辑函数
from cotton_toolkit.external_functions.sequence_evolution import (
    run_pal2nal_back_translation,
    convert_fasta_to_phylip,
    run_paml_codeml,
    run_codonw_analysis, create_short_id_fasta_and_map
)
# 复用系统发育流程中的函数
from cotton_toolkit.external_functions.phylogenetics import (
    run_muscle_alignment,
    run_iqtree_inference
)
from cotton_toolkit.utils.gene_utils import translate_cds_to_protein, validate_cds_fasta

if TYPE_CHECKING:
    from ..gui_app import CottonToolkitApp

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("ui.workflow.sequence_evolution")


class SequenceEvolutionWorkflow:
    """封装序列演化分析多步骤流程的专用控制器。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.context: Dict[str, Any] = {}

    def start(self, task_kwargs: dict):
        """流程入口点"""
        try:
            # 验证输入是否为有效的CDS FASTA
            validate_cds_fasta(task_kwargs['input_fasta_path'])
        except ValueError as e:
            self.app.ui_manager.show_error_message(_("输入文件错误"), str(e))
            self._cleanup_after_error()
            return

        # 1. 初始化上下文和临时目录
        temp_dir = tempfile.TemporaryDirectory(prefix="seq_evo_")
        self.context = {
            "temp_dir": temp_dir,
            "original_kwargs": task_kwargs,
            "paths": {
                "original_cds": task_kwargs['input_fasta_path'],
                "protein": os.path.join(temp_dir.name, "protein.fasta"),
                "protein_aligned": os.path.join(temp_dir.name, "protein_aligned.fasta"),
                "codon_aligned_fasta": os.path.join(temp_dir.name, "codon_aligned.fasta"),
                "codon_aligned_short_id": os.path.join(temp_dir.name, "codon_aligned_short_id.fasta"),
                "codon_aligned_phylip": os.path.join(temp_dir.name, "codon_aligned.phy"),
                "iqtree_prefix": os.path.join(temp_dir.name, "iqtree_result"),
                "paml_output": os.path.join(temp_dir.name, "paml_output.txt"),
                "codonw_output": os.path.join(task_kwargs['output_dir'], "5_codonw_results.txt"),
            }
        }

        # 2. 启动流程的第一步：翻译
        self.app.event_handler.start_task(
            task_name=_("步骤1/6: 翻译CDS序列"),
            target_func=translate_cds_to_protein,
            kwargs={
                'input_cds_path': self.context['paths']['original_cds'],
                'output_protein_path': self.context['paths']['protein'],
            },
            on_success=self._handle_translation_done,
            is_workflow_step=True
        )

    # --- 流程中的每个步骤完成后的回调处理 ---

    def _handle_translation_done(self, _wdnmd=None):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        self.app.event_handler.start_task(
            task_name=_("步骤2/6: MUSCLE 蛋白质序列比对"),
            target_func=run_muscle_alignment,
            kwargs={
                'config': self.context['original_kwargs']['config'],
                'input_path': self.context['paths']['protein'],
                'output_path': self.context['paths']['protein_aligned'],
            },
            on_success=self._handle_muscle_done,
            is_workflow_step=True
        )

    def _handle_muscle_done(self, _wdnmd=None):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        self.app.event_handler.start_task(
            task_name=_("步骤3/6: PAL2NAL 密码子比对"),
            target_func=run_pal2nal_back_translation,
            kwargs={
                'config': self.context['original_kwargs']['config'],
                'protein_align_path': self.context['paths']['protein_aligned'],
                'original_cds_path': self.context['paths']['original_cds'],
                'output_codon_align_path': self.context['paths']['codon_aligned_fasta'],
            },
            on_success=self._handle_pal2nal_done,
            is_workflow_step=True
        )

    def _handle_pal2nal_done(self, _wdnmd=None):

        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None

        # 1. 创建带短ID的FASTA文件，并获取ID映射
        id_map = create_short_id_fasta_and_map(
            input_fasta_path=self.context['paths']['codon_aligned_fasta'],
            output_fasta_path=self.context['paths']['codon_aligned_short_id']
        )
        self.context['id_map'] = id_map

        # 2. 将带短ID的FASTA文件转换为PHYLIP
        convert_fasta_to_phylip(
            input_fasta_path=self.context['paths']['codon_aligned_short_id'],
            output_phylip_path=self.context['paths']['codon_aligned_phylip'],
            id_map=id_map  # <-- 传递ID map
        )

        # 3. 使用带短ID的FASTA文件启动IQ-TREE
        self.app.event_handler.start_task(
            task_name=_("步骤4/6: IQ-TREE 构建系统发育树"),
            target_func=run_iqtree_inference,
            kwargs={
                'config': self.context['original_kwargs']['config'],
                'input_path': self.context['paths']['codon_aligned_short_id'],  # <-- 使用 short_id 文件
                'output_prefix': self.context['paths']['iqtree_prefix'],
                'model': 'GTR+G',
                'bootstrap': 1000,
            },
            on_success=self._handle_iqtree_done,
            is_workflow_step=True
        )

    def _handle_iqtree_done(self, _wdnmd=None):

        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None

        self.app.event_handler.start_task(
            task_name=_("步骤5/6: PAML (codeml) 计算选择压力"),
            target_func=run_paml_codeml,
            kwargs={
                'config': self.context['original_kwargs']['config'],
                'alignment_phylip_path': self.context['paths']['codon_aligned_phylip'],
                'tree_path': self.context['paths']['iqtree_prefix'] + ".treefile",
                'output_path': self.context['paths']['paml_output'],
                'model': self.context['original_kwargs']['paml_model'],
                'ns_sites': self.context['original_kwargs']['paml_ns_sites'],
            },
            on_success=self._handle_paml_done,
            is_workflow_step=True
        )

    def _handle_paml_done(self, _wdnmd=None):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        self.app.event_handler.start_task(
            task_name=_("步骤6/6: CodonW 分析密码子偏好"),
            target_func=run_codonw_analysis,
            kwargs={
                'config': self.context['original_kwargs']['config'],
                'input_cds_path': self.context['paths']['original_cds'],
                'output_path': self.context['paths']['codonw_output'],
            },
            # 这是最后一个计算步骤，完成后启动最终的打包
            on_success=self._handle_codonw_done,
            is_workflow_step=True
        )

    def _handle_codonw_done(self, _wdnmd=None):
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        """所有计算步骤完成，启动最终的打包任务"""
        self.app.event_handler.start_task(
            task_name=_("最后一步: 打包结果文件"),
            target_func=self._package_results_worker,
            kwargs={'workflow_context': self.context},
            on_success=self._handle_final_packaging_done,
            task_key="seq_evo_package"  # 这是最后一个'普通'任务
        )

    def _package_results_worker(self, workflow_context: Dict[str, Any], progress_callback=None, **kwargs) -> str:
        """在后台线程中整理所有输出文件"""
        if progress_callback: progress_callback(10, _("正在创建输出目录..."))

        output_dir = workflow_context['original_kwargs']['output_dir']
        os.makedirs(output_dir, exist_ok=True)

        files_to_copy = {
            workflow_context['paths']['codon_aligned_phylip']: "1_codon_alignment.phy",
            workflow_context['paths']['iqtree_prefix'] + ".treefile": "2_phylogenetic_tree.treefile",
            workflow_context['paths']['paml_output']: "3_paml_codeml_results.txt",
        }

        if progress_callback: progress_callback(30, _("正在复制结果文件..."))

        for src, dest_name in files_to_copy.items():
            if os.path.exists(src):
                shutil.copy(src, os.path.join(output_dir, dest_name))

        codonw_dir = os.path.dirname(workflow_context['paths']['codonw_output'])
        base_codonw_out = os.path.splitext(os.path.basename(workflow_context['paths']['codonw_output']))[0]

        codonw_main_output = os.path.join(codonw_dir, base_codonw_out + ".out")
        if os.path.exists(codonw_main_output):
            shutil.move(codonw_main_output, os.path.join(output_dir, "4_codonw_main_indices.txt"))

        if progress_callback: progress_callback(100, _("打包完成。"))
        return output_dir

    def _handle_final_packaging_done(self, output_dir: str):
        """所有步骤完成后，显示最终成功信息并清理。"""
        final_message = _("序列演化分析流程已全部完成！\n\n所有结果已保存至以下文件夹:\n{}").format(output_dir)
        self.app.ui_manager.show_info_message(_("流程完成"), final_message)
        self._cleanup()

    def _cleanup_after_error(self):
        """在流程开始前发生错误时清理"""
        self.app.ui_manager._hide_progress_dialog()
        self.app.active_task_name = None
        self._cleanup()

    def _cleanup(self):
        """安全地清理临时目录"""
        if self.context and "temp_dir" in self.context:
            try:
                self.context['temp_dir'].cleanup()
                logger.info("Sequence evolution temporary directory cleaned up.")
            except Exception as e:
                logger.error(f"Failed to cleanup seq-evo temp directory: {e}")
        self.context = {} 