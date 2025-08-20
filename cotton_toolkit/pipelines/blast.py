import gzip
import os
import subprocess
import tempfile
import threading
import traceback
from typing import Optional, Callable
import logging
import pandas as pd
from Bio import SeqIO
from Bio.Blast.Applications import NcbiblastnCommandline, NcbiblastpCommandline, NcbiblastxCommandline, \
    NcbitblastnCommandline
from Bio.SearchIO import parse as blast_parse

from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipeline.blast")


def run_blast_pipeline(
        config: MainConfig,
        blast_type: str,
        target_assembly_id: str,
        query_file_path: Optional[str],
        query_text: Optional[str],
        output_path: Optional[str],
        evalue: float,
        word_size: int,
        max_target_seqs: int,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
) -> Optional[pd.DataFrame]:
    # 修改: 移除 status_callback 参数
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel(message: str = "任务已取消。"):
        if cancel_event and cancel_event.is_set():
            logger.info(message)
            return True
        return False

    tmp_query_file_to_clean = None
    try:
        progress(0, _("BLAST 流程启动..."))
        if check_cancel(): return _("任务已取消。")

        progress(5, _("正在验证目标基因组数据库..."))
        logger.info(_("步骤 1: 准备目标数据库 '{}'...").format(target_assembly_id))

        # 修改: get_genome_data_sources 不再需要 logger_func
        genome_sources = get_genome_data_sources(config)
        target_genome_info = genome_sources.get(target_assembly_id)
        if not target_genome_info:
            logger.error(_("错误: 无法找到目标基因组 '{}' 的配置。").format(target_assembly_id))
            return None

        db_type = 'prot' if blast_type in ['blastp', 'blastx'] else 'nucl'
        seq_file_key = 'predicted_protein' if db_type == 'prot' else 'predicted_cds'

        logger.info(_("为 {} 需要 {} 类型的数据库，将使用 '{}' 文件。").format(blast_type, db_type, seq_file_key))

        compressed_seq_file = get_local_downloaded_file_path(config, target_genome_info, seq_file_key)
        if not compressed_seq_file or not os.path.exists(compressed_seq_file):
            logger.error(_("错误: 未找到目标基因组的 '{}' 序列文件。请先下载数据。").format(seq_file_key))
            return None

        db_fasta_path = compressed_seq_file
        logger.debug(_("BLAST 数据库序列源文件: {}").format(db_fasta_path))

        if compressed_seq_file.endswith('.gz'):
            decompressed_path = compressed_seq_file.removesuffix('.gz')
            db_fasta_path = decompressed_path
            if not os.path.exists(decompressed_path) or os.path.getmtime(compressed_seq_file) > os.path.getmtime(
                    decompressed_path):
                progress(8, _("文件为gz压缩格式，正在解压..."))
                logger.info(_("正在解压 {} 到 {}...").format(os.path.basename(compressed_seq_file),
                                                             os.path.basename(decompressed_path)))
                try:
                    with gzip.open(compressed_seq_file, 'rb') as f_in, open(decompressed_path, 'wb') as f_out:
                        while True:
                            if check_cancel(_("解压过程被取消。")): return None
                            chunk = f_in.read(1024 * 1024)
                            if not chunk:
                                break
                            f_out.write(chunk)
                    logger.info(_("解压成功。"))
                except Exception as e:
                    logger.error(_("解压文件时出错: {}").format(e))
                    return None

        if check_cancel(): return _("任务已取消。")

        db_check_ext = '.phr' if db_type == 'prot' else '.nhr'
        logger.debug(_("检查是否存在BLAST索引文件，例如: {}").format(db_fasta_path + db_check_ext))
        if not os.path.exists(db_fasta_path + db_check_ext):
            progress(10, _("正在创建BLAST数据库... (可能需要一些时间)"))
            logger.info(
                _("未找到现有的BLAST数据库，正在为 '{}' 创建一个新的 {} 库...").format(os.path.basename(db_fasta_path),
                                                                                      db_type))

            makeblastdb_cmd = ["makeblastdb", "-in", db_fasta_path, "-dbtype", db_type, "-out", db_fasta_path, "-title",
                               f"{target_assembly_id} {db_type} DB"]
            try:
                if check_cancel(_("数据库创建过程在开始前被取消。")): return None
                result = subprocess.run(makeblastdb_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                if result.returncode != 0:
                    # 如果返回码非0，我们检查索引文件是否实际已创建
                    if not os.path.exists(db_fasta_path + db_check_ext):
                        # 如果索引文件不存在，说明真的失败了
                        logger.error(_("创建BLAST数据库失败: {} \nStderror: {}").format(result.stdout, result.stderr))
                        return None
                    else:
                        # 如果索引文件存在，说明只是退出码有问题，可以继续
                        logger.warning(_("makeblastdb命令返回了非零退出码，但数据库索引文件已成功创建。将继续执行..."))
                        logger.debug(f"makeblastdb stdout:\n{result.stdout}")
                        logger.debug(f"makeblastdb stderr:\n{result.stderr}")

                logger.info(_("BLAST数据库创建成功。"))

            except FileNotFoundError:
                logger.error(_(
                    "错误: 'makeblastdb' 命令未找到。请确保 BLAST+ 已被正确安装并添加到了系统的 PATH 环境变量中。\n\n官方下载地址:\nhttps://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"))
                return False
            except subprocess.CalledProcessError as e:
                logger.error(_("创建BLAST数据库失败: {} \nStderror: {}").format(e.stdout, e.stderr))
                return None

        if check_cancel(): return _("任务已取消。")

        progress(25, _("正在准备查询序列..."))
        tmp_query_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".fasta")
        tmp_query_file_to_clean = tmp_query_file.name
        with tmp_query_file:
            query_fasta_path = tmp_query_file.name
            if query_file_path:
                if check_cancel(): return _("任务已取消。")
                logger.info(_("正在处理输入文件: {}").format(query_file_path))
                file_format = "fasta"
                try:
                    with open(query_file_path, "r") as f:
                        if f.read(1) == '@': file_format = "fastq"
                except:
                    pass
                if file_format == "fastq":
                    logger.info(_("检测到FASTQ格式，正在转换为FASTA..."))
                    SeqIO.convert(query_file_path, "fastq", query_fasta_path, "fasta")
                else:
                    logger.info(_("将输入文件作为FASTA格式处理..."))
                    with open(query_file_path, 'r') as infile:
                        tmp_query_file.write(infile.read())
            elif query_text:
                if check_cancel(): return _("任务已取消。")
                logger.info(_("正在处理文本输入..."))
                logger.debug(_("--- Received query_text in pipeline (first 1000 chars) ---\n{}\n-------------------------------------------------").format(query_text[:1000]))
                tmp_query_file.write(query_text)

        logger.debug(_("查询序列已写入临时文件: {}").format(query_fasta_path))
        if check_cancel(): return _("任务已取消。")

        progress(40, _("正在执行 {} ...").format(blast_type))
        logger.info(_("步骤 2: 执行 {} ...").format(blast_type.upper()))

        output_xml_path = query_fasta_path + ".xml"

        blast_map = {'blastn': NcbiblastnCommandline, 'blastp': NcbiblastpCommandline, 'blastx': NcbiblastxCommandline,
                     'tblastn': NcbitblastnCommandline}
        blast_cline = blast_map[blast_type](query=query_fasta_path, db=db_fasta_path, out=output_xml_path, outfmt=5,
                                            evalue=evalue, word_size=word_size, max_target_seqs=max_target_seqs,
                                            num_threads=config.downloader.max_workers)

        logger.info(_("BLAST命令: {}").format(str(blast_cline)))
        if check_cancel(_("BLAST在执行前被取消。")): return None
        stdout, stderr = blast_cline()
        if stderr:
            stderr_lower = stderr.lower()
            if "error:" in stderr_lower or "fatal:" in stderr_lower or "command not found" in stderr_lower:
                logger.error(_("BLAST运行时发生致命错误: {}").format(stderr))
                return None  # 中止流程
            else:
                logger.warning(_("BLAST运行时产生警告或提示信息: {}").format(stderr.strip()))

        if check_cancel(): return _("任务已取消。")

        progress(80, _("正在解析BLAST结果..."))
        logger.info(_("步骤 3: 解析结果并保存到 {} ...").format(output_path))

        all_hits = []
        if not os.path.exists(output_xml_path) or os.path.getsize(output_xml_path) == 0:
            logger.warning(_("BLAST运行完毕，但未产生任何结果。"))
        else:
            blast_results = blast_parse(output_xml_path, "blast-xml")
            for query_result in blast_results:
                if check_cancel(_("BLAST结果解析过程被取消。")): break
                for hit in query_result:
                    for hsp in hit:
                        hit_data = {
                            "Query_ID": query_result.id, "Query_Length": query_result.seq_len,
                            "Hit_ID": hit.id, "Hit_Description": hit.description, "Hit_Length": hit.seq_len,
                            "E-value": hsp.evalue, "Bit_Score": hsp.bitscore,
                            "Identity (%)": (hsp.ident_num / hsp.aln_span) * 100 if hsp.aln_span > 0 else 0,
                            "Positives (%)": (hsp.pos_num / hsp.aln_span) * 100 if hsp.aln_span > 0 else 0,
                            "Gaps": hsp.gap_num, "Alignment_Length": hsp.aln_span,
                            "Query_Start": hsp.query_start, "Query_End": hsp.query_end,
                            "Hit_Start": hsp.hit_start, "Hit_End": hsp.hit_end,
                            "Query_Strand": hsp.query_strand, "Hit_Strand": hsp.hit_strand,
                            "Query_Sequence": str(hsp.query.seq), "Hit_Sequence": str(hsp.hit.seq),
                            "Alignment_Midline": hsp.aln_annotation.get('homology', '')
                        }
                        all_hits.append(hit_data)

        if check_cancel(): return _("任务已取消。")

        if not all_hits:
            logger.info(_("未找到任何显著的BLAST匹配项。"))
        else:
            results_df = pd.DataFrame()  # 默认返回一个空的DataFrame
            if not all_hits:
                logger.info(_("未找到任何显著的BLAST匹配项。"))
            else:
                results_df = pd.DataFrame(all_hits)
                results_df['Identity (%)'] = results_df['Identity (%)'].map('{:.2f}'.format)
                results_df['Positives (%)'] = results_df['Positives (%)'].map('{:.2f}'.format)
                logger.info(_("成功找到 {} 条匹配记录。").format(len(results_df)))

            if output_path:
                progress(95, _("正在保存到文件..."))
                if output_path.lower().endswith('.csv'):
                    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                elif output_path.lower().endswith('.xlsx'):
                    results_df.to_excel(output_path, index=False, engine='openpyxl')
                logger.info(_("BLAST 任务完成！结果已保存到 {}").format(output_path))

            progress(100, _("BLAST流程完成。"))
            return results_df  # 总是返回DataFrame对象

    except Exception as e:
        logger.error(_("BLAST流水线执行过程中发生意外错误: {}").format(e))
        logger.debug(traceback.format_exc())
        return None  # 失败时返回 None
    finally:
        if tmp_query_file_to_clean and os.path.exists(tmp_query_file_to_clean):
            os.remove(tmp_query_file_to_clean)
            output_xml_path = tmp_query_file_to_clean + ".xml"
            if os.path.exists(output_xml_path):
                os.remove(output_xml_path)
