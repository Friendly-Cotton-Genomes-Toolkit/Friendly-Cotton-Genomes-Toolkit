import os
import tempfile
from typing import Dict, Optional
from Bio import SeqIO

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)


def parse_fasta_text(fasta_text: str) -> Dict[str, str]:
    """
    将FASTA格式的字符串解析成一个字典。
    键是序列的头部信息（去掉'>'），值是序列本身。
    支持多行序列。
    """
    sequences = {}
    current_header = None
    current_sequence = []

    for line in fasta_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('>'):
            if current_header:
                sequences[current_header] = "".join(current_sequence)
            current_header = line[1:].strip()
            current_sequence = []
        elif current_header:
            current_sequence.append(line)

    if current_header:
        sequences[current_header] = "".join(current_sequence)

    return sequences


def prepare_fasta_query_file(
        query_text: Optional[str],
        query_file_path: Optional[str]
) -> str:
    """
    准备一个用于查询的FASTA临时文件。

    该函数会处理两种输入情况：
    1. 如果提供了 query_file_path，它会读取该文件。如果文件是FASTQ格式，则自动转换为FASTA。
    2. 如果提供了 query_text，它会直接将文本内容写入。

    Args:
        query_text: 包含FASTA序列的原始字符串。
        query_file_path: 查询序列文件的路径。

    Returns:
        创建的临时FASTA文件的绝对路径。调用者有责任在使用后清理此文件。
    """
    try:
        # 创建一个临时文件，delete=False确保我们可以在关闭后依然使用它的路径
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".fasta", encoding='utf-8') as tmp_query_file:
            temp_file_path = tmp_query_file.name

            if query_file_path:
                # 检查输入文件是否为FASTQ格式
                file_format = "fasta"
                try:
                    with open(query_file_path, "r", encoding='utf-8') as f:
                        # 简单通过第一个字符判断
                        if f.read(1) == '@':
                            file_format = "fastq"
                except Exception:
                    # 如果读取失败，按fasta处理
                    pass

                if file_format == "fastq":
                    # 如果是FASTQ，使用Bio.SeqIO进行转换
                    SeqIO.convert(query_file_path, "fastq", temp_file_path, "fasta")
                else:
                    # 如果是FASTA，直接复制内容
                    with open(query_file_path, 'r', encoding='utf-8') as infile:
                        tmp_query_file.write(infile.read())

            elif query_text:
                # 如果是文本输入，直接写入
                tmp_query_file.write(query_text)

            else:
                raise ValueError(_("必须提供查询序列文本或文件路径之一。"))

        return temp_file_path

    except Exception as e:
        raise IOError(_("准备查询序列临时文件时出错: {}").format(e))