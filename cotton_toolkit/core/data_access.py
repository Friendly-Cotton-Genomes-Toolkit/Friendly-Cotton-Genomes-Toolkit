import gzip
import io
import logging
import os
import sqlite3
import threading
from random import sample
from typing import List, Tuple, Optional, Callable
import logging
import pandas as pd

from cotton_toolkit import PREPROCESSED_DB_NAME
from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.convertXlsx2csv import _find_header_row
from cotton_toolkit.utils.file_utils import _sanitize_table_name
from cotton_toolkit.utils.gene_utils import logger, _, resolve_gene_ids, _to_gene_id, _to_transcript_id

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.data_access")


def get_sequences_for_gene_ids(
        config: MainConfig,
        source_assembly_id: str,
        gene_ids: List[str]
) -> Tuple[Optional[str], List[str]]:
    """
    根据基因ID列表，从预处理好的SQLite数据库中获取FASTA格式的CDS序列。
    【已更新】现在会先调用智能ID解析器来统一ID格式。
    """
    try:
        # --- 核心修改：在最开始调用ID解析器 ---
        logger.info(_("正在智能解析 {} 个输入基因ID...").format(len(gene_ids)))
        resolved_gene_ids = resolve_gene_ids(config, source_assembly_id, gene_ids)
        logger.info(_("ID解析完成，得到 {} 个标准化的ID用于查询。").format(len(resolved_gene_ids)))
    except (ValueError, FileNotFoundError) as e:
        logger.error(e)
        return None, gene_ids

    # --- 数据库和表名准备 (这部分代码在 resolve_gene_ids 中也存在，但在这里仍然需要) ---
    project_root = os.path.dirname(config.config_file_abs_path_)
    db_path = os.path.join(project_root, "genomes", "genomes.db")
    genome_sources = get_genome_data_sources(config)
    source_genome_info = genome_sources.get(source_assembly_id)
    cds_file_path = get_local_downloaded_file_path(config, source_genome_info, 'predicted_cds')
    table_name = _sanitize_table_name(os.path.basename(cds_file_path), version_id=source_genome_info.version_id)

    fasta_parts = []
    found_genes_map = {}

    try:
        logging.debug(db_path)
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
            cursor = conn.cursor()
            # --- 逻辑简化：现在只需进行一次批量查询 ---
            placeholders = ','.join('?' for _V in resolved_gene_ids)
            query = f'SELECT Gene, Seq FROM "{table_name}" WHERE Gene IN ({placeholders})'
            cursor.execute(query, resolved_gene_ids)

            for gene, seq in cursor.fetchall():
                # 因为ID已经标准化，我们只需将原始ID（未标准化的）映射到找到的序列上
                original_id = _to_gene_id(gene)  # 以基础ID为准进行反向映射
                if original_id in gene_ids or gene in gene_ids:
                    found_genes_map[original_id] = seq

    except sqlite3.Error as e:
        logger.error(_("查询序列时发生数据库错误: {}").format(e))
        return None, gene_ids

    # 构建FASTA字符串时，使用原始ID以保持用户输入的一致性
    for original_gid in gene_ids:
        base_gid = _to_gene_id(original_gid)
        if base_gid in found_genes_map:
            fasta_parts.append(f">{original_gid}\n{found_genes_map[base_gid]}")

    all_input_base_ids = set(_to_gene_id(gid) for gid in gene_ids)
    not_found_genes = [gid for gid in all_input_base_ids if gid not in found_genes_map]

    if not_found_genes:
        logger.warning(_("警告: 在数据库中未能找到 {} 个基因的序列。").format(len(not_found_genes)))

    fasta_string = "\n".join(fasta_parts)
    return fasta_string, not_found_genes


def load_annotation_data(
        file_path: str
) -> Optional[pd.DataFrame]:
    """
    加载一个标准化的注释CSV文件。
    此函数假定输入的CSV文件第一行是表头。
    """
    if not os.path.exists(file_path):
        # 修改: 使用 logger.error
        logger.error(_("Annotation file not found at: {}").format(file_path))
        return None

    try:
        df = pd.read_csv(file_path, header=0, sep=',')

        if df.empty:
            # 修改: 使用 logger.warning
            logger.warning(_("Annotation file '{}' is empty.").format(os.path.basename(file_path)))
            return None

        df.dropna(subset=['GeneID', 'TermID'], inplace=True)
        df['GeneID'] = df['GeneID'].astype(str)
        df['TermID'] = df['TermID'].astype(str)

        if 'Description' not in df.columns:
            df['Description'] = df['TermID']
        if 'Namespace' not in df.columns:
            df['Namespace'] = 'KEGG' if 'ko' in df['TermID'].iloc[0] else 'unknown'

        return df

    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Failed to load and process standardized file {}. Reason: {}").format(file_path, e))
        return None


def get_homology_by_gene_ids(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str],
        direction: str
) -> pd.DataFrame:
    """
    从数据库的同源表中查询棉花与拟南芥的对应关系。
    """
    if not gene_ids:
        return pd.DataFrame()

    project_root = os.path.dirname(config.config_file_abs_path_)
    db_path = os.path.join(project_root, "genomes", "genomes.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(_("错误: 预处理数据库 'genomes.db' 未找到。"))

    genome_sources = get_genome_data_sources(config)
    genome_info = genome_sources.get(assembly_id)
    homology_url = getattr(genome_info, 'homology_ath_url', None)
    if not homology_url:
        raise ValueError(_("错误: 基因组 '{}' 的配置中未定义 'homology_ath_url'。").format(assembly_id))

    table_name = _sanitize_table_name(os.path.basename(homology_url), version_id=assembly_id)
    logger.debug(f"[DataAccess] Determined table name: {table_name}")  # DEBUG

    try:
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cursor.fetchone() is None:
                raise ValueError(_("错误: 在数据库中找不到表 '{}'。").format(table_name))

            if direction == 'cotton_to_ath':
                placeholders = ','.join('?' for _f in gene_ids)
                query = f'SELECT Query, Match, Description FROM "{table_name}" WHERE Query IN ({placeholders})'
                params = gene_ids
            else:  # ath_to_cotton
                base_gene_ids = sorted(list(set(_to_gene_id(gid) for gid in gene_ids)))
                if not base_gene_ids: return pd.DataFrame()

                where_clauses = " OR ".join(['Match LIKE ?' for d_ in base_gene_ids])
                query = f'SELECT Query, Match, Description FROM "{table_name}" WHERE {where_clauses}'
                params = [f'{base_id}%' for base_id in base_gene_ids]

            logger.debug(f"[DataAccess] Executing SQL query: {query}")  # DEBUG
            logger.debug(f"[DataAccess] With {len(params)} parameters: {params[:20]}...")  # DEBUG (只显示前20个)

            df = pd.read_sql_query(query, conn, params=params)

            logger.debug(f"[DataAccess] Query returned {len(df)} rows.")  # DEBUG
            if not df.empty:
                logger.debug(f"[DataAccess] First 5 rows from DB:\n{df.head().to_string()}")  # DEBUG

            return df

    except Exception as e:
        logger.error(_("查询同源数据库时出错: {}").format(e))
        return pd.DataFrame()




def resolve_arabidopsis_ids_from_homology_db(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str]
) -> Tuple[List[str], Optional[str]]:
    """
    【新增】模仿 resolve_gene_ids 的逻辑，但专门用于从同源表中智能解析拟南芥ID。

    返回一个元组: (用于查询的ID列表, 探测到的处理模式)
    """
    if not gene_ids:
        return [], None

    project_root = os.path.dirname(config.config_file_abs_path_)
    db_path = os.path.join(project_root, "genomes", "genomes.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(_("错误: 预处理数据库 'genomes.db' 未找到。"))

    genome_sources = get_genome_data_sources(config)
    genome_info = genome_sources.get(assembly_id)
    homology_url = getattr(genome_info, 'homology_ath_url', None)
    if not homology_url:
        raise ValueError(_("错误: 基因组 '{}' 的配置中未定义 'homology_ath_url'。").format(assembly_id))
    table_name = _sanitize_table_name(os.path.basename(homology_url), version_id=assembly_id)

    processing_mode = None
    query_ids = []

    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if cursor.fetchone() is None:
            raise ValueError(_("错误: 在数据库中找不到表 '{}'。").format(table_name))

        def _check_ath_id_exists(gid):
            query = f'SELECT 1 FROM "{table_name}" WHERE Match = ? LIMIT 1'
            cursor.execute(query, (gid,))
            return cursor.fetchone() is not None

        # 探测逻辑：随机取样，判断输入是基因还是转录本格式
        samples = sample(gene_ids, min(len(gene_ids), 2))
        for sample_id in samples:
            if _check_ath_id_exists(_to_transcript_id(sample_id)):
                processing_mode = 'transcript';
                break
            elif _check_ath_id_exists(_to_gene_id(sample_id)):
                processing_mode = 'gene';
                break

        # 根据探测到的模式，格式化整个ID列表用于查询
        if not processing_mode:
            logger.warning(_("无法在数据库中匹配提供的拟南芥ID样本，将使用原始ID进行查询。"))
            query_ids = sorted(list(set(gene_ids)))
        elif processing_mode == 'transcript':
            logger.info(_("智能解析：探测到数据库匹配拟南芥转录本ID。"))
            query_ids = sorted(list(set([_to_transcript_id(gid) for gid in gene_ids])))
        elif processing_mode == 'gene':
            logger.info(_("智能解析：探测到数据库匹配拟南芥基础基因ID。"))
            query_ids = sorted(list(set([_to_gene_id(gid) for gid in gene_ids])))

    return query_ids, processing_mode