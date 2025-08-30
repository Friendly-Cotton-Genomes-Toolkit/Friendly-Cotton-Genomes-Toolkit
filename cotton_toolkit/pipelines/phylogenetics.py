# 文件路径: cotton_toolkit/pipelines/phylogenetics_pipeline.py

import os
import subprocess
import sys
import logging
from typing import Callable, Optional, Tuple, Dict, Any
from threading import Event
from Bio import Phylo
import matplotlib
import matplotlib.pyplot as plt
from cotton_toolkit.config.models import MainConfig

logger = logging.getLogger("cotton_toolkit.pipeline.phylogenetics")

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


# 文件路径: cotton_toolkit/pipelines/phylogenetics_pipeline.py

def _run_command(
        cmd: list,
        step_name: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """一个通用的、支持进度和取消的子进程执行函数"""

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError(_("任务 '{}' 已被用户取消。").format(step_name))

    if progress_callback:
        progress_callback(0, _("正在执行: {}...（该过程进度不会更新）").format(step_name))

    logger.info(f"Executing command for step '{step_name}': {' '.join(cmd)}")
    check_cancel()

    kwargs = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace'  # 增加错误处理，防止因编码问题崩溃
    }
    if sys.platform == "win32":
        kwargs['creationflags'] = 0x08000000

    process = subprocess.Popen(cmd, **kwargs)

    try:
        # 使用 process.communicate() 来等待进程结束并获取输出。
        # 这是避免管道缓冲区满导致死锁的标准方法。
        stdout_data, stderr_data = process.communicate()
    except InterruptedError:
        # 如果在等待时发生中断（例如来自取消逻辑），则终止进程
        process.kill()
        # 等待进程实际终止
        process.wait()
        # 重新抛出中断异常
        raise

    # 在命令执行完毕后，最后检查一次是否需要取消
    check_cancel()

    if process.returncode != 0:
        # 使用 communicate() 返回的数据，而不是 .read()
        error_msg = stderr_data or stdout_data
        logger.error(f"Step '{step_name}' failed with return code {process.returncode}. Error: {error_msg}")
        raise RuntimeError(_("步骤 '{}' 执行失败: {}").format(step_name, error_msg))

    logger.info(f"Step '{step_name}' completed successfully.")
    if progress_callback:
        progress_callback(100, _("{} 已完成。").format(step_name))



def run_muscle_alignment(
        config: MainConfig,
        input_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """执行 MUSCLE 多序列比对。"""
    muscle_path = config.advanced_tools.muscle_path
    if not muscle_path:
        raise ValueError(_("MUSCLE 路径未在配置中设置。"))

    muscle_cmd = [muscle_path, "-align", input_path, "-output", output_path]
    _run_command(muscle_cmd, "MUSCLE 多序列比对", progress_callback, cancel_event)


def run_trimal_trimming(
        config: MainConfig,
        input_path: str,
        output_path: str,
        gap_threshold: float,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """执行 trimAl 序列修建。"""
    trimal_path = config.advanced_tools.trimal_path
    if not trimal_path:
        raise ValueError(_("trimAl 路径未在配置中设置。"))

    trimal_cmd = [trimal_path, "-in", input_path, "-out", output_path, "-gt", str(gap_threshold)]
    _run_command(trimal_cmd, "trimAl 序列修建", progress_callback, cancel_event)


def run_iqtree_inference(
        config: MainConfig,
        input_path: str,
        output_prefix: str,
        model: str,
        bootstrap: int,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """执行 IQ-TREE 构建系统发育树。"""
    iqtree_path = config.advanced_tools.iqtree_path
    if not iqtree_path:
        raise ValueError(_("IQ-TREE 路径未在配置中设置。"))

    iqtree_cmd = [
        iqtree_path, "-s", input_path, "-m", model, "-B", str(bootstrap),
        "--prefix", output_prefix, "-nt","AUTO"
    ]
    _run_command(iqtree_cmd, "IQ-TREE 构建发育树", progress_callback, cancel_event)



def get_alignment_statistics(aligned_fasta_path: str) -> Dict[str, Any]:
    """
    从比对后的FASTA文件中计算关键统计数据，并给出是否需要trim的建议。
    """
    stats = {
        "sequences": 0,
        "length": 0,
        "total_chars": 0,
        "total_gaps": 0,
        "gap_percentage": 0.0,
        "recommendation": ""
    }
    try:
        with open(aligned_fasta_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 简单高效地解析FASTA
        entries = content.strip().split('>')[1:]
        if not entries:
            return stats

        stats["sequences"] = len(entries)

        # 假设所有序列比对后长度相同，取第一个的长度
        first_seq_lines = entries[0].split('\n', 1)
        if len(first_seq_lines) > 1:
            sequence_data = first_seq_lines[1].replace('\n', '')
            stats["length"] = len(sequence_data)

        # 计算gap
        total_gaps = content.count('-')
        stats["total_gaps"] = total_gaps
        total_chars = stats["sequences"] * stats["length"]
        stats["total_chars"] = total_chars

        if total_chars > 0:
            stats["gap_percentage"] = (total_gaps / total_chars) * 100

        # 生成建议
        if stats["gap_percentage"] > 20:
            stats["recommendation"] = _(
                "建议进行修建。比对结果中包含大量缺口({:.1f}%)，这可能会严重影响建树的准确性。").format(
                stats["gap_percentage"])
        elif stats["gap_percentage"] > 5:
            stats["recommendation"] = _(
                "可以考虑进行修建。比对结果中包含少量缺口({:.1f}%)，修建可能有助于提升结果质量。").format(
                stats["gap_percentage"])
        else:
            stats["recommendation"] = _("不一定需要修建。比对结果质量较好，缺口比例低({:.1f}%)，可以直接用于建树。").format(
                stats["gap_percentage"])

    except Exception as e:
        logger.error(f"Failed to calculate alignment statistics: {e}")
        stats["recommendation"] = _("无法计算统计数据: {}").format(e)

    return stats


def visualize_tree(
        tree_file_path: str,
        output_image_path: str,
        figsize: Tuple[float, float] = (10, 8),
        dpi: int = 300,
        show_branch_labels: bool = False,
        label_font_size: int = 10,
        branch_line_width: float = 1.5,
        output_format: str = 'png',
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """
    使用 Bio.Phylo 和 matplotlib 可视化 Newick 格式的树文件，支持详细的学术绘图参数。
    """
    step_name = _("树文件可视化")

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError(_("任务 '{}' 已被用户取消。").format(step_name))

    if progress_callback:
        progress_callback(20, _("正在读取树文件..."))
    check_cancel()

    try:
        tree = Phylo.read(tree_file_path, "newick")
    except Exception as e:
        error_msg = _("无法解析树文件 '{}'。请确保它是一个有效的Newick格式文件。错误: {}").format(tree_file_path, e)
        logger.error(error_msg)
        raise ValueError(error_msg)

    if progress_callback:
        progress_callback(50, _("正在根据参数绘制树图..."))
    check_cancel()

    # 设置全局绘图参数以获得更好的学术外观
    plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'sans-serif']
    plt.rcParams['lines.linewidth'] = branch_line_width

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    ax.tick_params(axis='both', which='major', labelsize=label_font_size)

    # --- 核心修改 ---
    # Bio.Phylo.draw 使用 'branch_labels' 参数（而非 'show_branch_labels'）
    # 并且需要一个函数来指定显示什么内容。
    draw_kwargs = {
        'axes': ax,
        'do_show': False
    }
    if show_branch_labels:
        # 这个lambda函数会检查每个进化枝(clade)的置信度(confidence)属性
        # IQ-TREE 将自举值存储在这里。我们只显示大于0的值。
        draw_kwargs['branch_labels'] = lambda c: f"{int(c.confidence)}" if c.confidence is not None and c.confidence > 0 else None

    Phylo.draw(tree, **draw_kwargs)
    # --- 修改结束 ---

    ax.set_title("Phylogenetic Tree", fontsize=label_font_size + 2)
    ax.set_ylabel("")
    ax.set_yticklabels([])

    plt.tight_layout()

    if progress_callback:
        progress_callback(80, _("正在保存图片..."))
    check_cancel()

    final_output_path = f"{os.path.splitext(output_image_path)[0]}.{output_format}"
    plt.savefig(final_output_path, format=output_format, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"Tree visualization saved to {final_output_path}")
