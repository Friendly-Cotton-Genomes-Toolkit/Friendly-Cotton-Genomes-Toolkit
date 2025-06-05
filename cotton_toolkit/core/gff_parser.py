# cotton_toolkit/core/gff_parser.py
import gzip
import logging
import os
from typing import List, Dict, Optional, Union, Iterator, Any  # Iterator for streaming results, Any for attributes

import gffutils  # 用于解析GFF3文件并创建数据库

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

# 默认的gffutils数据库文件名后缀
DB_SUFFIX = ".gffutils.db"


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
        db_path = base_name_no_ext + DB_SUFFIX

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