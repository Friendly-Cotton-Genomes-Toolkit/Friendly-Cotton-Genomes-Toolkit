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


# 文件路径: cotton_toolkit/core/data_access.py

def get_sequences_for_gene_ids(
        config: MainConfig,
        source_assembly_id: str,
        gene_ids: List[str],
        sequence_type: str = 'cds'  # 【修改】新增参数，默认为 'cds' 以保持向后兼容
) -> Tuple[Optional[str], List[str]]:
    """
    根据基因ID列表，从预处理的SQLite数据库中检索FASTA格式的CDS或蛋白质序列。
    它会智能地将用户ID解析为数据库中存在的规范ID（优先使用转录本ID），
    并在FASTA头中使用这些数据库中正确的ID。
    """
    if not gene_ids:
        return "", []

    # --- 根据 sequence_type 动态确定要查询的文件和表名 ---
    project_root = os.path.dirname(config.config_file_abs_path_)
    db_path = os.path.join(project_root, "genomes", "genomes.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(_("错误: 预处理数据库 'genomes.db' 未找到。"))

    genome_sources = get_genome_data_sources(config)
    source_genome_info = genome_sources.get(source_assembly_id)

    # 根据输入参数选择文件类型
    file_key = 'predicted_protein' if sequence_type == 'protein' else 'predicted_cds'

    seq_file_path = get_local_downloaded_file_path(config, source_genome_info, file_key)
    if not seq_file_path or not os.path.exists(seq_file_path):
        raise FileNotFoundError(
            _("错误: 未找到基因组 '{}' 的 '{}' 序列文件。请先下载并预处理数据。").format(source_assembly_id, file_key)
        )

    table_name = _sanitize_table_name(os.path.basename(seq_file_path), version_id=source_genome_info.version_id)

    # --- 后续的ID解析和序列提取逻辑无需修改，因为它们是通用的 ---

    # 1. Generate all possible ID variations for all unique user IDs.
    unique_user_ids = list(dict.fromkeys(gene_ids))
    id_variations = {}  # { user_id: [potential_id1, potential_id2, ...] }
    all_potential_ids = set()
    for user_id in unique_user_ids:
        variants = list(dict.fromkeys([_to_transcript_id(user_id), _to_gene_id(user_id), user_id]))
        id_variations[user_id] = variants
        all_potential_ids.update(variants)

    # 2. Find which of these potential IDs actually exist in the DB in one batched query.
    existing_db_ids = set()
    try:
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cursor.fetchone() is None:
                raise ValueError(_("错误: 在数据库中找不到表 '{}'。请确保对应的文件已预处理。").format(table_name))

            batch_size = 500
            potential_list = list(all_potential_ids)
            for i in range(0, len(potential_list), batch_size):
                batch = potential_list[i:i + batch_size]
                placeholders = ','.join('?' for _9 in batch)
                query = f'SELECT Gene FROM "{table_name}" WHERE Gene IN ({placeholders})'
                cursor.execute(query, batch)
                for row in cursor.fetchall():
                    existing_db_ids.add(row[0])

    except (sqlite3.Error, ValueError) as e:
        error_msg = _("查询序列时发生数据库错误: {}").format(e)
        logger.error(error_msg)
        raise sqlite3.Error(error_msg) from e

    # 3. Resolve which user ID maps to which existing DB ID based on the preferred order.
    resolved_map = {}  # { user_id: db_id }
    not_found_genes = []
    for user_id, variants in id_variations.items():
        match_found = False
        for pot_id in variants:
            if pot_id in existing_db_ids:
                resolved_map[user_id] = pot_id
                match_found = True
                break
        if not match_found:
            not_found_genes.append(user_id)

    if not_found_genes:
        logger.warning(_("警告: 在数据库中未能找到 {} 个基因的序列: {}").format(len(not_found_genes),
                                                                                ", ".join(not_found_genes[:5]) + (
                                                                                    '...' if len(
                                                                                        not_found_genes) > 5 else '')))

    # 4. Fetch all required sequences in a single query.
    db_ids_to_fetch = list(set(resolved_map.values()))
    if not db_ids_to_fetch:
        return "", not_found_genes

    fasta_sequences = {}  # { db_id: sequence }
    try:
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _c in db_ids_to_fetch)
            query = f'SELECT Gene, Seq FROM "{table_name}" WHERE Gene IN ({placeholders})'
            cursor.execute(query, db_ids_to_fetch)
            for gene, seq in cursor.fetchall():
                fasta_sequences[gene] = seq
    except sqlite3.Error as e:
        error_msg = _("批量获取序列时发生数据库错误: {}").format(e)
        logger.error(error_msg)
        raise sqlite3.Error(error_msg) from e

    # 5. Build the FASTA string, using the database ID for the header.
    # Iterate through the original gene_ids list to maintain user's order.
    fasta_parts = []
    emitted_db_ids = set()  # Ensure each sequence is only output once
    for user_id in gene_ids:
        db_id = resolved_map.get(user_id)
        if db_id and db_id not in emitted_db_ids:
            sequence = fasta_sequences.get(db_id)
            if sequence:
                fasta_parts.append(f">{db_id}\n{sequence}")
                emitted_db_ids.add(db_id)

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
        raise FileNotFoundError(_("Annotation file not found at: {}").format(file_path))

    try:
        df = pd.read_csv(file_path, header=0, sep=',')

        if df.empty:
            logger.warning(_("Annotation file '{}' is empty.").format(os.path.basename(file_path)))
            return pd.DataFrame()

        df.dropna(subset=['GeneID', 'TermID'], inplace=True)
        df['GeneID'] = df['GeneID'].astype(str)
        df['TermID'] = df['TermID'].astype(str)

        if 'Description' not in df.columns:
            df['Description'] = df['TermID']
        if 'Namespace' not in df.columns:
            df['Namespace'] = 'KEGG' if 'ko' in df['TermID'].iloc[0] else 'unknown'

        return df

    except Exception as e:
        error_msg = _("Failed to load and process standardized file {}. Reason: {}").format(file_path, e)
        logger.error(error_msg)
        raise IOError(error_msg) from e

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
        error_msg = _("查询同源数据库时出错: {}").format(e)
        logger.error(error_msg)
        raise sqlite3.Error(error_msg) from e


def resolve_arabidopsis_ids_from_homology_db(
        config: MainConfig,
        assembly_id: str,
        gene_ids: List[str]
) -> Tuple[List[str], Optional[str]]:

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
