# cotton_toolkit/core/gff_parser.py
import gzip
import logging
import os
from typing import List, Dict, Optional, Union, Iterator, Any, \
    Callable, Tuple  # Iterator for streaming results, Any for attributes

import gffutils  # 用于解析GFF3文件并创建数据库
import threading

# --- 国际化和日志设置 ---
# 假设 _ 函数已由主应用程序入口设置到 builtins
try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text
    # print("Warning (gff_parser.py): builtins._ not found for i18n. Using pass-through.")

logger = logging.getLogger("cotton_toolkit.gff_parser")

# --- 模块级 GFF 数据库缓存 ---
_GFF_DB_PATHS_CREATED: Dict[str, bool] = {} # 缓存已创建的数据库路径，键是 db_path，值是 True
_GFF_DB_LOCK = threading.Lock() # 用于同步对 _GFF_DB_PATHS_CREATED 的访问和数据库创建


def create_gff_database(
        gff_filepath: str,
        db_path: str,
        force_recreate: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    创建gffutils数据库。
    """
    log = status_callback if status_callback else logger.info
    _log_error = status_callback if status_callback else logger.error  # Ensure error logs go through status_callback

    with _GFF_DB_LOCK:
        log(f"DEBUG: {_('尝试创建/加载GFF数据库:')} {db_path} {_('从:')} {gff_filepath}", level="DEBUG")  # 调试日志

        if os.path.exists(db_path) and not force_recreate:
            try:
                # 尝试打开数据库检查其完整性，如果损坏则删除
                temp_db_check = gffutils.FeatureDB(db_path, keep_order=True)
                temp_db_check.conn.close()  # 关闭临时连接
                log(_("GFF数据库已存在: {} (无需重新创建)").format(db_path))
                _GFF_DB_PATHS_CREATED[db_path] = True
                return db_path
            except Exception as e:
                _log_error(_("警告: 无法加载现有GFF数据库 '{}'，尝试重新创建：{}").format(db_path, e))
                if os.path.exists(db_path):
                    try:
                        os.remove(db_path)
                        log(_("已删除损坏的GFF数据库文件。"))
                    except OSError as err:
                        _log_error(_("错误: 无法删除损坏的GFF数据库文件 '{}': {}").format(db_path, err))
                        return None

        if os.path.exists(db_path):  # 如果存在但需要强制重新创建
            _log_error(_("警告: 强制重新创建GFF数据库 '{}'。").format(db_path))
            try:
                os.remove(db_path)
                log(_("已删除旧的GFF数据库文件。"))
            except OSError as err:
                _log_error(_("错误: 无法删除旧的GFF数据库文件 '{}': {}").format(db_path, err))
                return None

        log(_("正在创建GFF数据库：{} 从 {}").format(db_path, gff_filepath))
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            # --- 核心修改：调整推理标志 ---
            # 设置 disable_infer_transcripts 和 disable_infer_genes 为 False，
            # 允许 gffutils 推理基因和转录本，这对于不显式标记 'gene' 的 GFF 文件很重要。
            db = gffutils.create_db(
                gff_filepath,
                db_path,
                force=True,  # 强制创建新数据库
                disable_infer_transcripts=False,  # <-- 修改为 False
                disable_infer_genes=False,  # <-- 修改为 False
                merge_strategy="create_new",  # 合并策略，根据数据调整
                keep_order=True,
                # 如果 GFF 文件中的基因 ID 位于 attributes 中，而不是直接作为 feature.id，
                # 并且你不希望 gffutils 自己定义 ID，可以尝试指定 id_spec
                # 例如: id_spec={'gene': ['ID', 'gene_id']}
                # 但通常默认行为在 disable_infer=False 时足够。
            )
            log(_("GFF数据库创建成功: {}").format(db_path))
            _GFF_DB_PATHS_CREATED[db_path] = True
            return db_path
        except Exception as e:
            _log_error(_("错误: 创建GFF数据库 '{}' 失败: {}").format(db_path, e))
            _GFF_DB_PATHS_CREATED[db_path] = False
            return None


# --- 新增函数：在线程中打开数据库连接 ---
def _open_gff_db_connection(db_path: str) -> Optional[gffutils.FeatureDB]:
    """
    在当前线程中打开一个新的gffutils数据库连接。
    """
    try:
        db = gffutils.FeatureDB(db_path, keep_order=True)
        logger.debug(f"DEBUG: {_('新的GFF数据库连接在线程')} {threading.get_ident()} {_('中打开:')} {db_path}")
        return db
    except Exception as e:
        logger.error(_("错误: 在线程 {} 中打开GFF数据库 '{}' 失败: {}").format(threading.get_ident(), db_path, e))
        return None


# --- 新增函数：根据区域查询基因 ---
def get_genes_in_region(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        region: Tuple[str, int, int],  # (chromosome, start, end)
        force_db_creation: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    log = status_callback if status_callback else logger.info
    genes_in_region_list = []

    chrom, start, end = region

    db_name = f"{assembly_id}_genes.db"
    db_path = os.path.join(db_storage_dir, db_name)

    db_created = False
    with _GFF_DB_LOCK:
        db_created = _GFF_DB_PATHS_CREATED.get(db_path, False)

    if not db_created:
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback)
        if not created_db_path:
            log(_("错误: 无法获取或创建GFF数据库，无法查询区域基因。"), level="ERROR")
            return []

    db = _open_gff_db_connection(db_path)
    if not db:
        log(_("错误: 无法在当前线程中打开GFF数据库连接，无法查询区域基因。"), level="ERROR")
        return []

    try:
        log(_("正在基因组 '{}' 的区域 '{}:{}-{}' 中查询基因...").format(assembly_id, chrom, start, end))

        # --- 新增调试：打印数据库中可用的 featuretypes ---
        available_featuretypes = list(db.featuretypes())
        log(f"DEBUG: {_('数据库中可用的 featuretypes:')} {available_featuretypes}", level="DEBUG")
        if 'gene' not in available_featuretypes:
            log(f"WARNING: {_('警告：数据库中没有找到 featuretype 为 \'gene\' 的特征。请检查GFF文件或调整 featuretype。可用类型:')} {available_featuretypes}",
                level="WARNING")

        # --- 修改查询 featuretype：尝试更通用的查询或根据日志调整 ---
        # 默认尝试 'gene'
        query_featuretype = 'gene'
        # 如果 'gene' 不在可用类型中，并且有其他常见的基因类型，可以尝试
        # 例如，如果 available_featuretypes 包含 'mRNA' 或 'transcript'，可以考虑用它们
        # 但最好是根据实际 GFF 文件来确定最准确的类型。

        # for ftype in ['mRNA', 'transcript', 'gene_feature', 'locus']: # 示例：可以遍历尝试
        #     if ftype in available_featuretypes:
        #         query_featuretype = ftype
        #         log(f"INFO: {_('将使用特征类型:')} '{query_featuretype}' {_('进行查询。')}")
        #         break

        features = db.region(
            region,  # 直接传递 (chrom, start, end) 元组
            featuretype=query_featuretype  # 使用确定的特征类型
        )

        found_features_count = 0
        for gene in features:  # 遍历查询结果
            found_features_count += 1
            gene_id = gene.attributes.get('ID', [gene.id])[0]
            if '#' in gene_id:
                gene_id = gene_id.split('#')[0]

            genes_in_region_list.append({
                "gene_id": gene_id,
                "seqid": gene.seqid,
                "start": gene.start,
                "end": gene.end,
                "strand": gene.strand,
                "featuretype": gene.featuretype
            })

        genes_in_region_list.sort(key=lambda x: x['start'])

        log(_("在区域中找到 {} 个基因。").format(len(genes_in_region_list)))
        if found_features_count == 0:
            log(f"WARNING: {_('虽然GFF查询没有报错，但在区域 {}:{}-{} 中没有找到任何指定类型的特征。请检查区域、染色体名称、以及GFF文件的内容。')}".format(
                chrom, start, end), level="WARNING")

        return genes_in_region_list

    except Exception as e:
        log(_("错误: 查询GFF数据库区域时发生错误: {}").format(e), level="ERROR")
        return []
    finally:
        if db:
            try:
                db.conn.close()
            except Exception as close_e:
                logger.warning(_("警告: 关闭GFF数据库连接 '{}' 失败: {}").format(db_path, close_e))


# --- 新增函数：根据基因ID列表查询基因信息 ---
def get_gene_info_by_ids(
        assembly_id: str,
        gff_filepath: str,
        db_storage_dir: str,
        gene_ids: List[str],
        force_db_creation: bool = False,
        status_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Dict[str, Any]]:
    log = status_callback if status_callback else logger.info
    gene_info_map = {}

    db_name = f"{assembly_id}_genes.db"
    db_path = os.path.join(db_storage_dir, db_name)

    db_created = False
    with _GFF_DB_LOCK:
        db_created = _GFF_DB_PATHS_CREATED.get(db_path, False)

    if not db_created:
        created_db_path = create_gff_database(gff_filepath, db_path, force_db_creation, status_callback)
        if not created_db_path:
            log(_("错误: 无法获取或创建GFF数据库，无法查询基因信息。"), level="ERROR")
            return {}

    db = _open_gff_db_connection(db_path)
    if not db:
        log(_("错误: 无法在当前线程中打开GFF数据库连接，无法查询基因信息。"), level="ERROR")
        return {}

    try:
        log(_("在基因组 '{}' 中查询 {} 个基因的详细信息...").format(assembly_id, len(gene_ids)))

        # --- 新增调试：打印数据库中可用的 featuretypes ---
        available_featuretypes = list(db.featuretypes())
        log(f"DEBUG: {_('数据库中可用的 featuretypes:')} {available_featuretypes}", level="DEBUG")
        if 'gene' not in available_featuretypes:
            log(f"WARNING: {_('警告：数据库中没有找到 featuretype 为 \'gene\' 的特征。请检查GFF文件或调整 featuretype。可用类型:')} {available_featuretypes}",
                level="WARNING")

        for gene_id in gene_ids:
            gene = None
            try:
                # 尝试通过 feature.id 查询（最有效率）
                gene = db[gene_id]
            except gffutils.exceptions.FeatureNotFoundError:
                # 如果直接查找失败，并且基因 ID 格式可能与 GFF 的 ID 属性不同，
                # 则尝试遍历并检查 attributes 中的 'ID'。
                # 注意：对于大型 GFF 文件，全表扫描效率极低，考虑在 db.create_db 时建立索引
                # 或者确保 gene_id 与 GFF features 的主 ID 匹配。
                log(f"DEBUG: {_('基因ID')} '{gene_id}' {_('未通过直接查找找到，尝试通过属性查找。')}", level="DEBUG")
                # 遍历所有 feature 检查 attributes
                # 这个操作非常耗时，如果基因数量很多，会严重影响性能
                # 更好的方法是在 create_db 时使用 id_spec 参数来指定如何从 attributes 中提取主 ID
                for f in db.all_features():
                    if 'ID' in f.attributes and gene_id in f.attributes['ID']:
                        gene = f
                        break

            if gene:
                effective_gene_id = gene.attributes.get('ID', [gene.id])[0]
                if '#' in effective_gene_id:
                    effective_gene_id = effective_gene_id.split('#')[0]

                gene_info_map[effective_gene_id] = {
                    "gene_id": effective_gene_id,
                    "seqid": gene.seqid,
                    "start": gene.start,
                    "end": gene.end,
                    "strand": gene.strand,
                    "featuretype": gene.featuretype
                }
            else:
                log(_("警告: 未在数据库中找到基因 '{}'。").format(gene_id), level="WARNING")

        log(_("成功查询到 {} 个基因的详细信息。").format(len(gene_info_map)))
        return gene_info_map
    finally:
        if db:
            try:
                db.conn.close()
            except Exception as close_e:
                logger.warning(_("警告: 关闭GFF数据库连接 '{}' 失败: {}").format(db_path, close_e))

def create_or_load_gff_db(
        gff_file_path: str,
        db_path: Optional[str] = None,
        force_create: bool = False,
        disable_infer_transcripts: bool = False,  # gffutils参数
        disable_infer_genes: bool = False,  # gffutils参数
        verbose: bool = True  # 控制本函数的日志输出，gffutils有自己的日志
) -> Optional[gffutils.FeatureDB]:
    """
    加载一个已存在的gffutils数据库，或者从GFF3文件创建一个新的数据库。
    GFF3文件可以是未压缩的 (.gff3) 或gzip压缩的 (.gff3.gz)。

    Args:
        gff_file_path (str): GFF3文件的路径。
        db_path (Optional[str]): gffutils数据库文件的期望路径。
            如果为None，则数据库将与GFF3文件同名（在同一目录），但后缀为 DB_SUFFIX。
        force_create (bool): 如果为True，即使数据库文件已存在，也强制重新创建。
        disable_infer_transcripts (bool): 传递给 gffutils.create_db，是否禁用转录本推断。
        disable_infer_genes (bool): 传递给 gffutils.create_db，是否禁用基因推断。
        verbose (bool): 是否打印本函数的处理信息到logger。

    Returns:
        Optional[gffutils.FeatureDB]: 一个gffutils.FeatureDB对象，如果失败则返回None。
    """
    if not os.path.exists(gff_file_path):
        if verbose: logger.error(_("GFF3文件未找到: {}").format(gff_file_path))
        return None

    if db_path is None:
        # 移除可能的 .gz 后缀，然后再移除 .gff3 或 .gff 后缀
        path_no_gz = os.path.splitext(gff_file_path)[0] if gff_file_path.lower().endswith(".gz") else gff_file_path
        base_name_no_ext = os.path.splitext(path_no_gz)[0]
        db_path = base_name_no_ext + 'DB_SUFFIX'

    # 确保db_path的目录存在
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            if verbose: logger.info(_("为GFF数据库创建了目录: {}").format(db_dir))
        except OSError as e:
            if verbose: logger.error(_("创建GFF数据库目录 '{}' 失败: {}").format(db_dir, e))
            return None

    if not force_create and os.path.exists(db_path) and os.path.getsize(db_path) > 0:  # 检查文件是否存在且非空
        try:
            if verbose: logger.info(_("正在加载已存在的GFF数据库: {}").format(db_path))
            db = gffutils.FeatureDB(db_path)  # 打开已存在的数据库
            if verbose: logger.info(_("GFF数据库 '{}' 加载成功。").format(db_path))
            return db
        except Exception as e:
            if verbose: logger.warning(_("加载已存在的数据库 '{}' 失败: {}. 将尝试重新创建。").format(db_path, e))
            force_create = True  # 强制重新创建

    # 如果数据库不存在，或加载失败，或需要强制重建
    if force_create or not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        try:
            if verbose:
                if force_create and os.path.exists(db_path):
                    logger.info(_("强制重新创建GFF数据库: {} (从 {})").format(db_path, gff_file_path))
                else:
                    logger.info(_("正在从 '{}' 创建新的GFF数据库到 '{}'... (这可能需要一些时间)").format(gff_file_path,
                                                                                                         db_path))

            # gffutils可以自动处理 .gz 文件
            db = gffutils.create_db(
                gff_file_path,
                dbfn=db_path,
                force=True,  # 如果db_path已存在，则覆盖
                keep_order=True,
                merge_strategy='merge',
                sort_attribute_values=True,  # 对属性值进行排序，有助于一致性
                disable_infer_transcripts=disable_infer_transcripts,
                disable_infer_genes=disable_infer_genes,
                # verbose=verbose # gffutils 自己的 verbose 参数，控制其内部打印
                # id_spec={'gene': 'ID', 'mRNA': 'ID', 'exon': 'ID', 'CDS': 'ID'} # 确保ID被正确解析
            )
            if verbose: logger.info(_("GFF数据库 '{}' 创建成功。").format(db_path))
            return db
        except Exception as e:
            if verbose: logger.error(_("从 '{}' 创建GFF数据库 '{}' 失败: {}").format(gff_file_path, db_path, e),
                                     exc_info=True)
            # 如果创建失败，删除可能不完整的数据库文件
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
            return None

    return None  # 理论上不应该执行到这里，除非逻辑有误


def get_feature_by_id(db: gffutils.FeatureDB, feature_id: str) -> Optional[gffutils.Feature]:
    """
    根据ID从数据库中获取一个特征 (如基因、mRNA等)。

    Args:
        db (gffutils.FeatureDB): gffutils数据库对象。
        feature_id (str): 要检索的特征的ID。

    Returns:
        Optional[gffutils.Feature]: 找到的特征对象，如果未找到则为None。
    """
    try:
        feature = db[feature_id]
        return feature
    except gffutils.exceptions.FeatureNotFoundError:
        logger.debug(_("在GFF数据库中未找到ID为 '{}' 的特征。").format(feature_id))
        return None
    except Exception as e:
        logger.error(_("检索特征 '{}' 时出错: {}").format(feature_id, e), exc_info=True)
        return None


def get_children_features(
        db: gffutils.FeatureDB,
        parent_feature_or_id: Union[str, gffutils.Feature],
        child_feature_type: Optional[str] = None,
        order_by: Optional[str] = 'start'
) -> Iterator[gffutils.Feature]:
    """
    获取指定父特征的所有子特征 (例如，一个基因的所有mRNA，或一个mRNA的所有外显子)。

    Args:
        db (gffutils.FeatureDB): gffutils数据库对象。
        parent_feature_or_id (Union[str, gffutils.Feature]): 父特征的ID或特征对象。
        child_feature_type (Optional[str]): 要检索的子特征的类型 (如 'mRNA', 'exon', 'CDS')。
                                         如果为None，则返回所有类型的子特征。
        order_by (Optional[str]): 子特征排序依据 (如 'start', 'end')。

    Returns:
        Iterator[gffutils.Feature]: 子特征对象的迭代器。
    """
    parent_feature = parent_feature_or_id
    if isinstance(parent_feature_or_id, str):
        parent_feature = get_feature_by_id(db, parent_feature_or_id)

    if parent_feature:  # 确保 parent_feature 是一个 Feature 对象
        try:
            for child in db.children(parent_feature, featuretype=child_feature_type, order_by=order_by):
                yield child
        except Exception as e:
            logger.error(_("获取父特征 '{}' 的子特征时出错: {}").format(
                parent_feature.id if hasattr(parent_feature, 'id') else parent_feature_or_id, e), exc_info=True)
    else:
        logger.debug(_("未找到父特征 '{}'，无法获取子特征。").format(parent_feature_or_id))


def get_features_in_region(
        db: gffutils.FeatureDB,
        chromosome: str,
        start: int,
        end: int,
        feature_type: Optional[Union[str, List[str]]] = None,
        strand: Optional[str] = None
) -> Iterator[gffutils.Feature]:
    """
    获取在指定基因组区域内、特定类型和链向的特征。

    Args:
        db (gffutils.FeatureDB): gffutils数据库对象。
        chromosome (str): 染色体名称。
        start (int): 区域起始位置 (1-based, gffutils内部处理)。
        end (int): 区域结束位置 (1-based, gffutils内部处理)。
        feature_type (Optional[Union[str, List[str]]]): 要检索的特征类型或类型列表。
        strand (Optional[str]): 链向 ('+' 或 '-')。

    Returns:
        Iterator[gffutils.Feature]: 区域内特征对象的迭代器。
    """
    try:
        # gffutils.FeatureDB.region 接受 start 和 end, 它们是 1-based inclusive
        for feature in db.region(seqid=chromosome, start=start, end=end, featuretype=feature_type, strand=strand):
            yield feature
    except ValueError as e:
        logger.warning(_("检索区域 {}:{}-{} (类型: {}, 链向: {}) 特征时出错: {}。可能染色体名不存在或区域无效。").format(
            chromosome, start, end, feature_type, strand, e))
        return iter([])
    except Exception as e:
        logger.error(_("检索区域 {}:{}-{} 特征时发生未知错误: {}").format(chromosome, start, end, e), exc_info=True)
        return iter([])


def extract_gene_details(db: gffutils.FeatureDB, gene_id: str) -> Optional[Dict[str, Any]]:
    """
    提取单个基因的详细信息，包括其转录本和每个转录本的外显子和CDS。

    Args:
        db (gffutils.FeatureDB): gffutils数据库对象。
        gene_id (str): 基因ID。

    Returns:
        Optional[Dict[str, Any]]: 包含基因详细信息的字典，如果基因未找到则为None。
    """
    gene = get_feature_by_id(db, gene_id)
    if not gene or gene.featuretype.lower() not in ['gene', 'pseudogene', 'ncRNA_gene']:  # 确保是基因类型
        logger.debug(_("ID '{}' 不是一个有效的基因特征或未找到。").format(gene_id))
        return None

    gene_details: Dict[str, Any] = {
        "gene_id": gene.id,
        "chr": gene.chrom,
        "start": gene.start,
        "end": gene.end,
        "strand": gene.strand,
        "attributes": dict(gene.attributes),  # 转换为普通字典
        "transcripts": []
    }

    # 常见的转录本类型
    transcript_types = ['mRNA', 'transcript', 'ncRNA', 'lnc_RNA', 'miRNA', 'tRNA', 'rRNA']

    for transcript in get_children_features(db, gene, child_feature_type=transcript_types):
        transcript_info: Dict[str, Any] = {
            "transcript_id": transcript.id,
            "type": transcript.featuretype,
            "start": transcript.start,
            "end": transcript.end,
            "strand": transcript.strand,
            "attributes": dict(transcript.attributes),
            "exons": [],
            "cds": []  # Coding DNA Sequence segments
        }
        for exon in get_children_features(db, transcript, child_feature_type='exon'):
            transcript_info["exons"].append({
                "exon_id": exon.id, "start": exon.start, "end": exon.end,
                "strand": exon.strand, "attributes": dict(exon.attributes)
            })
        for cds_segment in get_children_features(db, transcript, child_feature_type='CDS'):
            transcript_info["cds"].append({
                "cds_id": cds_segment.id, "start": cds_segment.start, "end": cds_segment.end,
                "strand": cds_segment.strand, "phase": cds_segment.frame,
                "attributes": dict(cds_segment.attributes)
            })
        gene_details["transcripts"].append(transcript_info)

    return gene_details


# --- 用于独立测试 gff_parser.py 的示例代码 ---
if __name__ == '__main__':
    # 设置基本的日志记录，以便在独立运行时能看到logger的输出
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info(_("--- 开始独立测试 gff_parser.py ---"))

    # 创建一个临时的测试GFF3文件 (可以是 .gff3 或 .gff3.gz)
    test_gff_content = """##gff-version 3
chrTest1\tSourceApp\tgene\t1000\t5000\t.\t+\t.\tID=geneX;Name=XylS;description=Transcriptional regulator XylS
chrTest1\tSourceApp\tmRNA\t1000\t5000\t.\t+\t.\tID=rnaX1;Parent=geneX;product=XylS mRNA
chrTest1\tSourceApp\texon\t1000\t1500\t.\t+\t.\tID=exonX1.1;Parent=rnaX1
chrTest1\tSourceApp\tCDS\t1050\t1450\t.\t+\t0\tID=cdsX1.1;Parent=rnaX1;product=XylS
chrTest1\tSourceApp\texon\t3000\t3800\t.\t+\t.\tID=exonX1.2;Parent=rnaX1
chrTest1\tSourceApp\tCDS\t3020\t3750\t.\t+\t1\tID=cdsX1.2;Parent=rnaX1;product=XylS
chrTest1\tSourceApp\tfive_prime_UTR\t1000\t1049\t.\t+\t.\tParent=rnaX1
chrTest1\tSourceApp\tthree_prime_UTR\t3751\t5000\t.\t+\t.\tParent=rnaX1
chrTest2\tSourceApp\tgene\t200\t800\t.\t-\t.\tID=geneY;locus_tag=GY001
"""
    test_gff_filename = "temp_test_annotations.gff3.gz"  # 测试压缩文件
    db_filename = "temp_test_annotations.gffutils.db"

    # 清理可能存在的旧测试文件
    if os.path.exists(test_gff_filename): os.remove(test_gff_filename)
    if os.path.exists(db_filename): os.remove(db_filename)

    with gzip.open(test_gff_filename, "wt", encoding="utf-8") as f:  # 'wt' for writing text to gzip
        f.write(test_gff_content)
    logger.info(f"创建了测试GFF文件: {test_gff_filename}")

    # 1. 测试创建和加载数据库
    logger.info("\n--- 测试 create_or_load_gff_db ---")
    gff_db = create_or_load_gff_db(test_gff_filename, db_path=db_filename, force_create=True)
    assert gff_db is not None, "数据库创建失败"

    # 再次加载（不强制创建）
    gff_db_loaded = create_or_load_gff_db(test_gff_filename, db_path=db_filename, force_create=False)
    assert gff_db_loaded is not None, "数据库加载失败"
    logger.info("数据库创建和加载测试通过。")

    # 2. 测试 get_feature_by_id
    logger.info("\n--- 测试 get_feature_by_id ---")
    gene_x = get_feature_by_id(gff_db, "geneX")  # type: ignore
    assert gene_x is not None and gene_x.id == "geneX", "get_feature_by_id 测试失败 (geneX)"
    logger.info(f"找到基因 geneX: {gene_x.start}-{gene_x.end}, 属性: {dict(gene_x.attributes)}")

    non_existent_gene = get_feature_by_id(gff_db, "geneZ")  # type: ignore
    assert non_existent_gene is None, "get_feature_by_id 测试失败 (geneZ 应为 None)"
    logger.info("get_feature_by_id 测试通过。")

    # 3. 测试 get_children_features
    logger.info("\n--- 测试 get_children_features (geneX的mRNA) ---")
    mrnas_of_geneX = list(get_children_features(gff_db, "geneX", child_feature_type="mRNA"))  # type: ignore
    assert len(mrnas_of_geneX) == 1 and mrnas_of_geneX[0].id == "rnaX1", "get_children_features (mRNA) 测试失败"
    logger.info(f"geneX 的 mRNA: {mrnas_of_geneX[0].id}")

    logger.info("\n--- 测试 get_children_features (rnaX1的exons) ---")
    exons_of_rnaX1 = list(get_children_features(gff_db, "rnaX1", child_feature_type="exon"))  # type: ignore
    assert len(exons_of_rnaX1) == 2, "get_children_features (exons) 测试失败"
    logger.info(f"rnaX1 的 Exons: {[exon.id for exon in exons_of_rnaX1]}")
    logger.info("get_children_features 测试通过。")

    # 4. 测试 get_features_in_region
    logger.info("\n--- 测试 get_features_in_region (chrTest1:1100-3500 内的基因) ---")
    genes_in_region = list(get_features_in_region(gff_db, "chrTest1", 1100, 3500, feature_type="gene"))  # type: ignore
    assert len(genes_in_region) == 1 and genes_in_region[0].id == "geneX", "get_features_in_region (gene) 测试失败"
    logger.info(f"区域 chrTest1:1100-3500 内的基因: {[g.id for g in genes_in_region]}")
    logger.info("get_features_in_region 测试通过。")

    # 5. 测试 extract_gene_details
    logger.info("\n--- 测试 extract_gene_details (geneX) ---")
    gene_x_details = extract_gene_details(gff_db, "geneX")  # type: ignore
    assert gene_x_details is not None and gene_x_details["gene_id"] == "geneX", "extract_gene_details (geneX) 基本信息失败"
    assert len(gene_x_details["transcripts"]) == 1, "extract_gene_details (geneX) 转录本数量失败"
    assert len(gene_x_details["transcripts"][0]["exons"]) == 2, "extract_gene_details (geneX) 外显子数量失败"
    assert len(gene_x_details["transcripts"][0]["cds"]) == 2, "extract_gene_details (geneX) CDS数量失败"
    logger.info(f"geneX 详细信息: 成功提取到 {len(gene_x_details['transcripts'])} 个转录本。")
    logger.info(
        f"  第一个转录本 ({gene_x_details['transcripts'][0]['transcript_id']}) 有 {len(gene_x_details['transcripts'][0]['exons'])} 个外显子和 {len(gene_x_details['transcripts'][0]['cds'])} 个CDS片段。")
    logger.info("extract_gene_details 测试通过。")

    # 清理测试文件
    # (可选) 显式删除对象引用，并尝试强制垃圾回收，但关闭连接是主要手段
    del gff_db
    del gff_db_loaded
    import gc

    gc.collect()
    # import time
    # time.sleep(0.1) # 有时在Windows上，文件句柄的释放可能需要极短的时间


    if os.path.exists(test_gff_filename): os.remove(test_gff_filename)
    if os.path.exists(db_filename): os.remove(db_filename)
    logger.info("\n测试文件已清理。")
    logger.info("--- gff_parser.py 测试结束 ---")