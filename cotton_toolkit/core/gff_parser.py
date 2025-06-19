# cotton_toolkit/core/gff_parser.py
import gzip
import logging
import os
import re
import sqlite3
from typing import Dict, Any, Optional, Callable, List, Tuple, Iterator, Union

import gffutils
import pandas as pd
from diskcache import Cache

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.gff_parser")
db_cache = Cache("gff_databases_cache/db_objects")  # 使用 diskcache 缓存数据库对象


def _find_full_seqid(db: gffutils.FeatureDB, chrom_part: str, log: Callable) -> Optional[str]:
    """
    使用正则表达式在数据库中查找完整的序列ID (seqid)。
    例如，将用户输入的 'A01' 匹配到数据库中的 'Ghir_A01'。
    """
    all_seqids = list(db.seqids())
    log(f"数据库中所有可用的序列ID: {all_seqids[:10]}...", "DEBUG")

    # 优先进行精确匹配 (不区分大小写)
    for seqid in all_seqids:
        if seqid.lower() == chrom_part.lower():
            log(f"精确匹配成功: '{chrom_part}' -> '{seqid}'", "INFO")
            return seqid

    # 如果精确匹配失败，则使用正则表达式进行模糊匹配
    # 这个正则表达式会查找以用户输入结尾的seqid，例如 `..._A01`, `...-A01`, `...A01`
    pattern = re.compile(f".*[^a-zA-Z0-9]{re.escape(chrom_part)}$|^{re.escape(chrom_part)}$", re.IGNORECASE)

    matches = [seqid for seqid in all_seqids if pattern.match(seqid)]

    if len(matches) == 1:
        log(f"模糊匹配成功: '{chrom_part}' -> '{matches[0]}'", "INFO")
        return matches[0]

    if len(matches) > 1:
        log(f"警告: 发现多个可能的匹配项 for '{chrom_part}': {matches}。将使用第一个: {matches[0]}", "WARNING")
        return matches[0]

    log(f"错误: 无法在数据库中找到与 '{chrom_part}' 匹配的序列ID。", "ERROR")
    return None


def _gff_gene_filter(gff_filepath: str) -> Iterator[Union[gffutils.feature.Feature, str]]:
    """
    一个生成器函数，用于逐行读取GFF文件。
    现在此函数会直接将 feature 类型为 'gene' 的行解析为 gffutils.Feature 对象再 yield。
    注释行则作为字符串 yield。
    """
    is_gzipped = gff_filepath.endswith('.gz')
    opener = gzip.open if is_gzipped else open
    mode = 'rt' if is_gzipped else 'r'

    logger.debug(f"Opening {'gzipped ' if is_gzipped else ''}file for parsing: {gff_filepath}")

    with opener(gff_filepath, mode, encoding='utf-8', errors='ignore') as gff_file:
        for line in gff_file:
            # 直接跳过注释行，不再 yield 任何字符串
            if line.startswith('#'):
                continue

            columns = line.strip().split('\t')
            # 确保是有效的GFF行并且是我们需要的 'gene' 特征
            if len(columns) > 2 and columns[2] == 'gene':
                try:
                    # --- 核心修改 ---
                    # 将该行文本就地解析成一个 gffutils.Feature 对象
                    feature_obj = gffutils.feature.feature_from_line(line)
                    # 产出解析好的对象，而不是字符串
                    yield feature_obj
                except Exception as e:
                    # 如果某一行格式有问题，记录警告并跳过，避免整个流程中断
                    logger.warning(f"Skipping malformed GFF line: {line.strip()} | Error: {e}")


def create_gff_database(
        gff_filepath: str,
        db_path: str,
        force: bool = False,
        status_callback: Optional[Callable[[str, str], None]] = None,
        id_regex: Optional[str] = None  # <<< 新增参数
):
    """
    从 GFF3 文件创建 gffutils 数据库。
    现在可以使用正则表达式来规范化数据库中的主键ID。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")

    if os.path.exists(db_path) and os.path.getsize(db_path) > 0 and not force:
        log(f"数据库 '{os.path.basename(db_path)}' 已存在且有效，直接使用。", "DEBUG")
        return db_path

    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    log(f"正在创建GFF数据库(仅包含基因)：{os.path.basename(db_path)} 从 {os.path.basename(gff_filepath)}", "INFO")

    try:
        # --- 核心修改：定义ID规范化函数 ---
        def id_spec_func(feature):
            # 如果提供了正则表达式，则用它来处理ID，否则返回原始ID
            original_id = feature.attributes.get('ID', [None])[0]
            if not original_id:
                return None  # 如果没有ID属性，则忽略此特征
            return _apply_regex_to_id(original_id, id_regex) if id_regex else original_id

        gene_iterator = _gff_gene_filter(gff_filepath)

        gffutils.create_db(
            gene_iterator,
            dbfn=db_path,
            force=force,
            id_spec=id_spec_func,
            keep_order=True,
            merge_strategy="merge",
            sort_attribute_values=True,
            disable_infer_transcripts=True,
            disable_infer_genes=True,
        )
        log(f"成功创建GFF数据库: {os.path.basename(db_path)}", "INFO")
        return db_path
    except Exception as e:
        log(f"错误: 创建GFF数据库 '{os.path.basename(db_path)}' 失败: {e}", "ERROR")
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass
        raise


def extract_gene_details(feature: gffutils.Feature) -> Dict[str, Any]:
    """从 gffutils.Feature 对象中提取关键基因信息。"""
    attributes = dict(feature.attributes)
    return {
        'gene_id': feature.id,
        'chrom': feature.chrom,
        'start': feature.start,
        'end': feature.end,
        'strand': feature.strand,
        'source': feature.source,
        'feature_type': feature.featuretype,
        'aliases': attributes.get('Alias', ['N/A'])[0],
        'description': attributes.get('description', ['N/A'])[0]
    }


def _apply_regex_to_id(gene_id: str, regex_pattern: Optional[str]) -> str:
    """
    使用正则表达式从一个字符串中提取基因ID，并清除首尾空白。
    """
    # [FIXED] 关键修正：在所有操作之前，先对原始ID进行strip()处理，去除首尾空格
    processed_id = str(gene_id).strip()

    if not regex_pattern:
        return processed_id  # 返回清理过的ID

    match = re.search(regex_pattern, processed_id)
    if match and match.groups():
        # 返回捕获组内容，它已经是干净的
        return match.group(1)

    # 如果正则不匹配，返回清理过的原始ID
    return processed_id


def get_genes_in_region(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        region: Tuple[str, int, int],
        force_db_creation: bool = False,
        status_callback: Optional[Callable[[str, str], None]] = None,
        gene_id_regex: Optional[str] = None  # <<< 新增参数
) -> List[Dict[str, Any]]:
    """
    从GFF文件中查找位于特定染色体区域内的所有基因。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")

    db_path = os.path.join(db_storage_dir, f"{assembly_id}_genes.db")
    user_chrom_part, start, end = region

    try:
        # 将正则表达式传递给数据库创建函数
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback,
                                              id_regex=gene_id_regex)
        if not created_db_path:
            raise RuntimeError("无法获取或创建GFF数据库，无法查询区域基因。")

        db = gffutils.FeatureDB(created_db_path, keep_order=True)
        full_seqid = _find_full_seqid(db, user_chrom_part, log)

        if not full_seqid:
            return []

        log(f"正在查询区域: {full_seqid}:{start}-{end} (用户输入: {user_chrom_part})", "INFO")
        genes_in_region = list(db.region(region=(full_seqid, start, end), featuretype='gene'))

        results = [extract_gene_details(gene) for gene in genes_in_region]
        log(f"在区域内共找到 {len(results)} 个基因。", "INFO")
        return results

    except Exception as e:
        log(f"查询GFF区域时发生错误: {e}", "ERROR")
        logger.exception("GFF区域查询失败的完整堆栈跟踪:")
        return []


def get_gene_info_by_ids(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        gene_ids: List[str],
        force_db_creation: bool = False,
        status_callback: Optional[Callable[[str, str], None]] = None,
        gene_id_regex: Optional[str] = None # <<< 新增参数
) -> pd.DataFrame:
    """
    根据基因ID列表，从GFF数据库中批量查询基因信息。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")
    db_path = os.path.join(db_storage_dir, f"{assembly_id}_genes.db")
    try:
        # 将正则表达式传递给数据库创建函数
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback, id_regex=gene_id_regex)
        if not created_db_path:
            raise RuntimeError("无法获取或创建GFF数据库，无法查询基因ID。")

        db = gffutils.FeatureDB(created_db_path, keep_order=True)

        log(f"正在根据 {len(gene_ids)} 个ID查询基因信息...", "INFO")
        found_genes = []
        not_found_ids = []

        # 由于数据库的键现在是标准化的，我们可以直接进行精确查找
        for gene_id in gene_ids:
            try:
                gene_feature = db[gene_id]
                found_genes.append(extract_gene_details(gene_feature))
            except gffutils.exceptions.FeatureNotFoundError:
                not_found_ids.append(gene_id)

        if not_found_ids:
            log(f"警告: {len(not_found_ids)} 个基因ID未在GFF数据库中找到: {', '.join(not_found_ids[:5])}{'...' if len(not_found_ids) > 5 else ''}", "WARNING")

        if not found_genes:
            return pd.DataFrame()

        result_df = pd.DataFrame(found_genes)
        log(f"成功查询到 {len(found_genes)} 个基因的详细信息。", "INFO")
        return result_df

    except Exception as e:
        log(f"根据ID查询GFF时发生错误: {e}", "ERROR")
        logger.exception("GFF ID查询失败的完整堆栈跟踪:")
        return pd.DataFrame()