import logging
import os
import subprocess
import sys
from threading import Event
from typing import Callable, Optional, List, Dict

from Bio import AlignIO, SeqIO
from Bio.Align import MultipleSeqAlignment
from Bio.SeqRecord import SeqRecord

from cotton_toolkit.config.models import MainConfig

logger = logging.getLogger("cotton_toolkit.external.sequence_evolution")

try:
    from builtins import _
except ImportError:
    def _(text: str) -> str:
        return text


def _run_command(
        cmd: list,
        step_name: str,
        cwd: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """一个通用的、支持进度、取消和CWD的子进程执行函数"""

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError(_("任务 '{}' 已被用户取消。").format(step_name))

    if progress_callback:
        progress_callback(0, _("正在执行: {}...").format(step_name))

    logger.info(f"Executing command for step '{step_name}': {' '.join(cmd)}")
    check_cancel()

    kwargs = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace',
        'cwd': cwd
    }
    if sys.platform == "win32":
        # 使用 0x08000000 (CREATE_NO_WINDOW) 防止黑框闪烁
        kwargs['creationflags'] = 0x08000000

    process = subprocess.Popen(cmd, **kwargs)

    try:
        # Popen.communicate() 会等待进程结束，适合长时间运行的命令
        stdout_data, stderr_data = process.communicate()
    except InterruptedError:
        process.kill()
        process.wait()
        raise

    check_cancel()

    if process.returncode != 0:
        error_msg = stderr_data or stdout_data
        logger.error(f"Step '{step_name}' failed with return code {process.returncode}. Error: {error_msg}")
        raise RuntimeError(_("步骤 '{}' 执行失败: {}").format(step_name, error_msg))

    logger.info(f"Step '{step_name}' completed successfully.")
    if progress_callback:
        progress_callback(100, _("{} 已完成。").format(step_name))
    return stdout_data


def _validate_alignment_consistency(records: List[SeqRecord]):
    """检查一个比对中的所有序列是否具有相同的长度。"""
    if not records:
        return  # 如果没有序列，则无需检查

    first_len = len(records[0].seq)
    for record in records[1:]:
        if len(record.seq) != first_len:
            error_msg = _(
                "错误: PAL2NAL生成的比对文件长度不一致！\n"
                "序列 '{}' 的长度为 {}，而期望长度为 {}。\n"
                "这通常是由于原始CDS序列中包含非标准碱基或意外的终止密码子导致的。"
            ).format(record.id, len(record.seq), first_len)
            raise ValueError(error_msg)
    logger.info(_("比对文件一致性检查通过，所有序列长度均为 {}。").format(first_len))


def convert_fasta_to_phylip(
        input_fasta_path: str,
        output_phylip_path: str,
        id_map: Dict[str, str],
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """
    【已修复】使用传入的 id_map 来确保ID一致性。
    """
    step_name = _("转换比对格式为PHYLIP")
    if progress_callback: progress_callback(10, step_name)
    if cancel_event and cancel_event.is_set(): raise InterruptedError

    # 读取的是带短ID的FASTA
    records = list(SeqIO.parse(input_fasta_path, "fasta"))

    alignment = MultipleSeqAlignment(records)

    num_sequences = len(alignment)
    seq_length = alignment.get_alignment_length()

    with open(output_phylip_path, "w", encoding='utf-8', newline="\n") as handle:
        handle.write(f" {num_sequences} {seq_length}\n")
        for record in alignment:
            line = f"{record.id:<10}  {str(record.seq)}\n"
            handle.write(line)

    map_file_path = os.path.splitext(output_phylip_path)[0] + "_id_map.txt"
    with open(map_file_path, 'w', encoding='utf-8', newline="\n") as f:
        f.write("New_ID\tOriginal_ID\n")
        for new, original in id_map.items():
            f.write(f"{new}\t{original}\n")

    logger.info(_("已成功将FASTA手动转换为PHYLIP格式，并创建了ID映射文件。"))

    if progress_callback: progress_callback(100, _("格式转换完成。"))


def create_short_id_fasta_and_map(
        input_fasta_path: str,
        output_fasta_path: str
) -> Dict[str, str]:
    """
    读取一个FASTA文件，为其序列创建唯一的短ID，写入新的FASTA文件，并返回ID映射字典。
    """
    records = list(SeqIO.parse(input_fasta_path, "fasta"))
    _validate_alignment_consistency(records)

    id_map = {}
    new_records = []

    for i, record in enumerate(records):
        original_id = record.id
        prefix = original_id[:6]
        new_id = f"{prefix}_{i + 1:03}"

        # 创建一个新的记录，而不是修改旧的
        new_record = SeqRecord(record.seq, id=new_id, description="")
        new_records.append(new_record)
        id_map[new_id] = original_id

    SeqIO.write(new_records, output_fasta_path, "fasta")
    return id_map


def run_pal2nal_back_translation(
        config: MainConfig,
        protein_align_path: str,
        original_cds_path: str,
        output_codon_align_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """使用 PAL2NAL 将蛋白质比对反向翻译为密码子比对"""
    perl_path = config.advanced_tools.perl_path or "perl"
    pal2nal_path = config.advanced_tools.pal2nal_path
    if not pal2nal_path: raise ValueError(_("PAL2NAL 路径未在配置中设置。"))

    cmd = [
        perl_path, pal2nal_path,
        protein_align_path, original_cds_path,
        "-output", "fasta"
    ]

    # PAL2NAL 将结果输出到 stdout，我们需要重定向它
    stdout = _run_command(cmd, "PAL2NAL 反向翻译", None, progress_callback, cancel_event)
    with open(output_codon_align_path, 'w', encoding='utf-8') as f:
        f.write(stdout)


def run_paml_codeml(
        config: MainConfig,
        alignment_phylip_path: str,
        tree_path: str,
        output_path: str,
        model: int,
        ns_sites: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """动态生成codeml.ctl并执行PAML (codeml)"""
    paml_path = config.advanced_tools.paml_path
    if not paml_path: raise ValueError(_("PAML (codeml) 路径未在配置中设置。"))

    paml_dir = os.path.dirname(paml_path)
    ctl_path = os.path.join(paml_dir, "codeml.ctl")

    # 动态创建 codeml.ctl 控制文件
    ctl_content = f"""
      seqfile = {os.path.abspath(alignment_phylip_path)}
     treefile = {os.path.abspath(tree_path)}
      outfile = {os.path.abspath(output_path)}

        noisy = 3   * 0,1,2,3,9: how much rubbish on the screen
      verbose = 1   * 0: concise; 1: detailed, 2: too much
      runmode = 0   * 0: user tree; 1: semi-automatic; 2: automatic
                    * 3: StepwiseAddition; (4,5): pairwise run w user tree

      seqtype = 1   * 1:codons; 2:AAs; 3:codons-->AAs
    CodonFreq = 2   * 0:1/61; 1:F1X4; 2:F3X4; 3:codon table

        model = {model}   * models for codons:
                    * 0:one, 1:b, 2:2 or more dN/dS ratios for branches

      NSsites = {ns_sites}  * 0:one w;1:neutral;2:selection; 3:discrete;4:freqs;
                    * 5:gamma;6:2gamma;7:beta;8:beta&w;9:beta&gamma;
                    * 10:beta&gamma+1; 11:beta&normal>1; 12:0&2normal>1;
                    * 13:3normal>0

        icode = 0   * 0:universal code; 1:mammalian mt; 2-10:several mt codes
    fix_alpha = 1   * 0: estimate alpha; 1: fix alpha at 0
        alpha = 0.  * initial or fixed alpha
    fix_kappa = 0   * 0: estimate kappa; 1: fix kappa at value
        kappa = 2   * initial or fixed kappa
    """
    with open(ctl_path, 'w', encoding='utf-8') as f:
        f.write(ctl_content)

    cmd = [paml_path]
    # PAML必须在它自己的目录中运行
    _run_command(cmd, "PAML (codeml) 选择压力分析", paml_dir, progress_callback, cancel_event)


def run_codonw_analysis(
        config: MainConfig,
        input_cds_path: str,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[Event] = None
):
    """以非交互式模式运行 CodonW"""
    codonw_path = config.advanced_tools.codonw_path
    if not codonw_path: raise ValueError(_("CodonW 路径未在配置中设置。"))

    # CodonW 的输出文件名由 -outfile 参数决定，但它会创建多个文件。
    # 我们让它在自己的目录中运行，以避免文件混乱。
    output_dir = os.path.dirname(output_path)
    output_filename = os.path.basename(output_path)

    cmd = [
        codonw_path,
        "-infile", os.path.abspath(input_cds_path),
        "-outfile", output_filename,
        "-nomenu",  # 强制非交互模式
        "-all_indices",  # 计算所有指标
        "-silent"  # 不在屏幕上显示进度
    ]
    _run_command(cmd, "CodonW 密码子偏好性分析", output_dir, progress_callback, cancel_event)