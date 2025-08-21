# cotton_toolkit/core/gff_parser.py
import gzip
import logging
import os
import re
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
from typing import Dict, Any, Optional, Callable, List, Tuple, Iterator, Union

import gffutils
import pandas as pd
from diskcache import Cache

from cotton_toolkit.config.models import MainConfig

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.gff_parser")


def _gff_lookup_worker(
        gene_ids_chunk: List[str],
        db_path: str
) -> List[Dict[str, Any]]:
    """
    多线程工作单元：为一小批基因ID查询GFF信息。
    每个线程创建自己的数据库连接以确保线程安全。
    """
    found_genes = []
    try:
        # 每个线程拥有独立的数据库连接
        db = gffutils.FeatureDB(db_path, keep_order=True)
        for gene_id in gene_ids_chunk:
            try:
                gene_feature = db[gene_id]
                found_genes.append(extract_gene_details(gene_feature))
            except gffutils.exceptions.FeatureNotFoundError:
                # 在工作线程中忽略未找到的ID，主线程会报告最终差异
                pass
    except Exception as e:
        logger.error(_("GFF查询工作线程发生错误: {}").format(e))
    return found_genes

def _line_counter_and_gff_iterator(gff_filepath: str, progress_callback: Callable) -> Tuple[int, Iterator]:
    """
    第一次迭代计算总行数，第二次迭代作为gffutils的输入并汇报进度。
    """
    is_gzipped = gff_filepath.endswith('.gz')
    opener = gzip.open if is_gzipped else open
    mode = 'rt' if is_gzipped else 'r'

    # 第一次迭代: 计数
    total_lines = 0
    with opener(gff_filepath, mode, encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.startswith('#'):
                total_lines += 1

    progress_callback(5, _("文件扫描完毕，共 {} 行。").format(total_lines))

    # 第二次迭代: 生成器，用于解析并汇报进度
    def generator():
        processed_lines = 0
        with opener(gff_filepath, mode, encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('#'):
                    continue

                columns = line.strip().split('\t')
                if len(columns) > 2 and columns[2] == 'gene':
                    try:
                        yield gffutils.feature.feature_from_line(line)
                    except Exception:
                        pass  # 跳过错误行

                processed_lines += 1
                if processed_lines % 5000 == 0 and total_lines > 0:  # 每处理5000行汇报一次
                    # 解析占总进度的 10% -> 90%
                    percent = 10 + int((processed_lines / total_lines) * 80)
                    progress_callback(percent, _("正在解析基因..."))

    return total_lines, generator()


def _find_full_seqid(db: gffutils.FeatureDB, chrom_part: str) -> Optional[str]:
    """
    使用正则表达式在数据库中查找完整的序列ID (seqid)。
    """
    all_seqids = list(db.seqids())
    logger.debug(f"数据库中所有可用的序列ID: {all_seqids[:10]}...")

    for seqid in all_seqids:
        if seqid.lower() == chrom_part.lower():
            logger.info(_("精确匹配成功: '{}' -> '{}'").format(chrom_part, seqid))
            return seqid

    pattern = re.compile(f".*[^a-zA-Z0-9]{re.escape(chrom_part)}$|^{re.escape(chrom_part)}$", re.IGNORECASE)
    matches = [seqid for seqid in all_seqids if pattern.match(seqid)]

    if len(matches) == 1:
        logger.info(_("模糊匹配成功: '{}' -> '{}'").format(chrom_part, matches[0]))
        return matches[0]

    if len(matches) > 1:
        logger.warning(
            _("警告: 发现多个可能的匹配项 for '{}': {}。将使用第一个: {}").format(chrom_part, matches, matches[0]))
        return matches[0]

    logger.error(_("错误: 无法在数据库中找到与 '{}' 匹配的序列ID。").format(chrom_part))
    return None


def _gff_gene_filter(gff_filepath: str) -> Iterator[Union[gffutils.feature.Feature, str]]:
    """
    一个生成器函数，用于逐行读取GFF文件并仅产出'gene'类型的特征。
    """
    is_gzipped = gff_filepath.endswith('.gz')
    opener = gzip.open if is_gzipped else open
    mode = 'rt' if is_gzipped else 'r'

    logger.debug(_("Opening {}{}file for parsing: {}").format('gzipped ' if is_gzipped else '', '', gff_filepath))

    with opener(gff_filepath, mode, encoding='utf-8', errors='ignore') as gff_file:
        for line in gff_file:
            if line.startswith('#'):
                continue
            columns = line.strip().split('\t')
            if len(columns) > 2 and columns[2] == 'gene':
                try:
                    feature_obj = gffutils.feature.feature_from_line(line)
                    yield feature_obj
                except Exception as e:
                    logger.warning(_("Skipping malformed GFF line: {} | Error: {}").format(line.strip(), e))


def create_gff_database(
        gff_filepath: str,
        db_path: str,
        force: bool = False,
        id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
):
    """
    从 GFF3 文件创建 gffutils 数据库，并使用正则表达式规范化ID。
    现在支持精细的进度回调。
    """
    progress = progress_callback if progress_callback else lambda p, m: None



    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
        if not force and os.path.getmtime(gff_filepath) <= os.path.getmtime(db_path):
            logger.debug(f"数据库 '{os.path.basename(db_path)}' 已是最新，直接使用。")
            progress(100, _("数据库已是最新。"))
            return db_path

    logger.info(_("正在创建或更新GFF数据库(仅包含基因)：{} 从 {}").format(os.path.basename(db_path),
                                                                         os.path.basename(gff_filepath)))
    progress(0, _("开始创建GFF数据库..."))

    try:
        def id_spec_func(feature):
            original_id = feature.attributes.get('ID', [None])[0]
            if not original_id:
                return None
            # _apply_regex_to_id 是您 gff_parser.py 中已有的函数，此处假设它存在
            base_id = _apply_regex_to_id(original_id, id_regex)
            return base_id

        # 使用新的带进度的迭代器
        total_lines, gene_iterator = _line_counter_and_gff_iterator(gff_filepath, progress)
        if total_lines == 0:
            logger.warning(f"GFF file {gff_filepath} contains no data lines.")
            # 创建一个空数据库
            gffutils.create_db("", dbfn=db_path, force=True)
            progress(100, _("警告：GFF文件为空。"))
            return db_path

        gffutils.create_db(
            gene_iterator,
            dbfn=db_path,
            force=True,
            id_spec=id_spec_func,
            keep_order=True,
            merge_strategy="merge",
            sort_attribute_values=True,
            disable_infer_transcripts=True,
            disable_infer_genes=True,
        )
        progress(95, _("数据库结构创建完毕..."))

        logger.info(_("成功创建GFF数据库: {}").format(os.path.basename(db_path)))
        progress(100, _("GFF数据库处理完成。"))
        return db_path

    except Exception as e:
        logger.error(_("错误: 创建GFF数据库 '{}' 失败: {}").format(os.path.basename(db_path), e))
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass
        progress(100, _("创建GFF数据库失败。"))
        raise


def extract_gene_details(feature: gffutils.Feature) -> Dict[str, Any]:
    """
    【已修改】从 gffutils.Feature 对象中提取所有数据库列。
    表头将与数据库列名完全一致。
    """
    return {
        'id': feature.id,
        'seqid': feature.seqid,
        'source': feature.source,
        'featuretype': feature.featuretype,
        'start': feature.start,
        'end': feature.end,
        'score': feature.score,
        'strand': feature.strand,
        'frame': feature.frame,
        'attributes': str(feature.attributes),
        'extra': str(feature.extra) if feature.extra else None
    }


def _apply_regex_to_id(gene_id: str, regex_pattern: Optional[str]) -> str:
    """
    使用正则表达式从一个字符串中提取基因ID，并清除首尾空白。
    """
    processed_id = str(gene_id).strip()
    if not regex_pattern:
        return processed_id
    match = re.search(regex_pattern, processed_id)
    return match.group(1) if match and match.groups() else processed_id


def get_genes_in_region(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        region: Tuple[str, int, int],
        force_db_creation: bool = False,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    从GFF文件中查找位于特定染色体区域内的所有基因，并报告进度。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    new_db_storage_path = os.path.join("genomes", "gff3")
    db_path = os.path.join(new_db_storage_path, f"{assembly_id}_genes.db")

    user_chrom_part, start, end = region

    try:
        progress(10, _("正在准备GFF数据库..."))
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, id_regex=gene_id_regex)
        if not created_db_path:
            logger.error(_("无法获取或创建GFF数据库，无法查询区域基因。"))
            raise RuntimeError(_("无法获取或创建GFF数据库，无法查询区域基因。"))

        progress(40, _("正在打开数据库并查找序列ID..."))
        db = gffutils.FeatureDB(created_db_path, keep_order=True)
        full_seqid = _find_full_seqid(db, user_chrom_part)

        if not full_seqid:
            progress(100, _("在数据库中未找到匹配的染色体/序列。"))
            return []

        progress(60, _("正在查询区域: {}...").format(f"{full_seqid}:{start}-{end}"))
        genes_in_region = list(db.region(region=(full_seqid, start, end), featuretype='gene'))

        progress(80, _("正在提取基因详细信息..."))
        results = [extract_gene_details(gene) for gene in genes_in_region]
        logger.info(_("在区域内共找到 {} 个基因。").format(len(results)))
        progress(100, _("区域基因提取完成。"))
        return results

    except Exception as e:
        logger.error(_("查询GFF区域时发生错误: {}").format(e))
        logger.exception(_("GFF区域查询失败的完整堆栈跟踪:"))
        progress(100, _("查询时发生错误。"))
        return []


def get_gene_info_by_ids(
        assembly_id: str,
        gff_filepath: str,
        gene_ids: List[str],
        force_db_creation: bool = False,
        gene_id_regex: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> pd.DataFrame:
    """
    根据基因ID列表，从GFF数据库中批量并行查询基因信息，并报告进度。
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    # 去重以减少不必要的查询
    unique_gene_ids = sorted(list(set(gene_ids)))
    total_ids = len(unique_gene_ids)

    new_db_storage_path = os.path.join("genomes", "gff3")
    db_path = os.path.join(new_db_storage_path, f"{assembly_id}_genes.db")

    try:
        progress(10, _("正在准备GFF数据库..."))
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, id_regex=gene_id_regex)
        if not created_db_path:
            raise RuntimeError(_("无法获取或创建GFF数据库，无法查询基因ID。"))

        progress(40, _("正在并行查询 {} 个基因...").format(total_ids))

        all_found_genes = []
        max_workers = 8 # 写死！太懒啦
        chunk_size = max(1, (total_ids + max_workers - 1) // max_workers)
        id_chunks = [unique_gene_ids[i:i + chunk_size] for i in range(0, total_ids, chunk_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {executor.submit(_gff_lookup_worker, chunk, created_db_path): chunk for chunk in
                               id_chunks}

            completed_count = 0
            for future in as_completed(future_to_chunk):
                completed_count += 1
                percentage = 40 + int((completed_count / len(id_chunks)) * 55)
                progress(percentage, f"{_('已完成')} {completed_count}/{len(id_chunks)} {_('个查询批次')}")

                result_chunk = future.result()
                if result_chunk:
                    all_found_genes.extend(result_chunk)

        found_ids = {gene['id'] for gene in all_found_genes}
        not_found_ids = [gid for gid in unique_gene_ids if gid not in found_ids]

        if not_found_ids:
            logger.warning(
                _("警告: {} 个基因ID未在GFF数据库中找到: {}{}").format(len(not_found_ids), ', '.join(not_found_ids[:5]),
                                                                       '...' if len(not_found_ids) > 5 else ''))

        if not all_found_genes:
            progress(100, _("查询完成，未找到任何基因。"))
            return pd.DataFrame()

        result_df = pd.DataFrame(all_found_genes)
        logger.info(_("成功并行查询到 {} 个基因的详细信息。").format(len(all_found_genes)))
        progress(100, _("基因查询完成。"))
        return result_df

    except Exception as e:
        logger.error(_("根据ID查询GFF时发生错误: {}").format(e))
        progress(100, _("查询时发生错误。"))
        return pd.DataFrame()