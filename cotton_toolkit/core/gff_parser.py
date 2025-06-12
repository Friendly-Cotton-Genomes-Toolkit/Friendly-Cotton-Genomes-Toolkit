# cotton_toolkit/core/gff_parser.py

import logging
import os
import sqlite3
from typing import Dict, Any, Optional, Callable, List, Tuple

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


def create_gff_database(gff_filepath: str, db_path: str, force: bool = False,
                        status_callback: Optional[Callable[[str, str], None]] = None):
    """
    从 GFF3 文件创建 gffutils 数据库。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")


    # --- 不仅检查文件是否存在，还检查文件大小是否大于0 ---
    # 这可以防止因之前创建失败而留下的0字节文件导致后续错误。
    if os.path.exists(db_path) and os.path.getsize(db_path) > 0 and not force:
        log(f"数据库 '{os.path.basename(db_path)}' 已存在且有效，直接使用。", "DEBUG")
        return db_path

    # 如果文件存在但为空，或者需要强制重建，则打印相应信息
    if os.path.exists(db_path) and not force:
        log(f"数据库 '{os.path.basename(db_path)}' 已存在，直接使用。", "DEBUG")
        return db_path

    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    log(f"正在创建GFF数据库：{os.path.basename(db_path)} 从 {os.path.basename(gff_filepath)}", "INFO")

    try:
        gffutils.create_db(
            gff_filepath,
            dbfn=db_path,
            force=force,
            keep_order=True,
            merge_strategy="merge",
            sort_attribute_values=True,
            disable_infer_transcripts=True,
            disable_infer_genes=True
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


def get_genes_in_region(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        region: Tuple[str, int, int],
        force_db_creation: bool = False,
        status_callback: Optional[Callable[[str, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    【全新实现】从GFF文件中查找位于特定染色体区域内的所有基因。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")

    db_path = os.path.join(db_storage_dir, f"{assembly_id}_genes.db")
    chrom, start, end = region

    try:
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback)
        if not created_db_path:
            raise RuntimeError("无法获取或创建GFF数据库，无法查询区域基因。")

        db = gffutils.FeatureDB(created_db_path, keep_order=True)

        log(f"正在查询区域: {chrom}:{start}-{end}", "INFO")
        genes_in_region = list(db.region(region=(chrom, start, end), featuretype='gene'))

        if not genes_in_region:
            log(f"在区域 {chrom}:{start}-{end} 未找到 'gene' 类型的特征。", "WARNING")
            return []

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
        status_callback: Optional[Callable[[str, str], None]] = None
) -> pd.DataFrame:
    """
    【全新实现】根据基因ID列表，从GFF数据库中批量查询基因信息。
    """
    log = status_callback if status_callback else lambda msg, level: print(f"[{level}] {msg}")

    db_path = os.path.join(db_storage_dir, f"{assembly_id}_genes.db")

    try:
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback)
        if not created_db_path:
            raise RuntimeError("无法获取或创建GFF数据库，无法查询基因ID。")

        db = gffutils.FeatureDB(created_db_path, keep_order=True)

        log(f"正在根据 {len(gene_ids)} 个ID查询基因信息...", "INFO")
        found_genes = []
        not_found_ids = []

        for gene_id in gene_ids:
            try:
                gene_feature = db[gene_id]
                found_genes.append(extract_gene_details(gene_feature))
            except gffutils.exceptions.FeatureNotFoundError:
                not_found_ids.append(gene_id)

        if not_found_ids:
            log(f"警告: {len(not_found_ids)} 个基因ID未在GFF数据库中找到: {', '.join(not_found_ids[:5])}{'...' if len(not_found_ids) > 5 else ''}",
                "WARNING")

        if not found_genes:
            log("未找到任何匹配的基因信息。", "INFO")
            return pd.DataFrame()

        result_df = pd.DataFrame(found_genes)
        log(f"成功查询到 {len(found_genes)} 个基因的详细信息。", "INFO")
        return result_df

    except Exception as e:
        log(f"根据ID查询GFF时发生错误: {e}", "ERROR")
        logger.exception("GFF ID查询失败的完整堆栈跟踪:")
        return pd.DataFrame()