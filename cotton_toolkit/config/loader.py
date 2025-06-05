# cotton_toolkit/config/loader.py
import shutil

import yaml
import os
from typing import Dict, Any, Optional, Tuple
import gettext

try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):  # builtins._ 未设置或导入builtins失败
    # 如果在测试或独立运行此模块时，_ 可能未设置
    def _(text: str) -> str:
        return text


def load_config(config_path: str) -> Optional[Dict[str, Any]]:
    """
    加载并返回YAML配置文件内容。

    Args:
        config_path (str): YAML配置文件的路径。

    Returns:
        Optional[Dict[str, Any]]: 配置字典，如果加载失败则返回None。
    """
    if not os.path.exists(config_path):
        print(_("错误: 配置文件 '{}' 未找到。").format(config_path))
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):
            print(_("错误: 配置文件 '{}' 的顶层结构必须是一个字典。").format(config_path))
            return None

        # 将配置文件的绝对路径存储到配置字典中，方便后续解析相对路径
        config['_config_file_abs_path_'] = os.path.abspath(config_path)
        print(_("配置文件 '{}' 加载成功。").format(config_path))
        return config
    except yaml.YAMLError as e:
        print(_("错误: 解析配置文件 '{}' 失败: {}").format(config_path, e))
        return None
    except Exception as e:
        print(_("加载配置文件 '{}' 时发生未知错误: {}").format(config_path, e))
        return None


def get_genome_data_sources(main_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从主配置中获取或加载 GENOME_DATA_SOURCES。
    它可以直接在主配置中，或通过 'genome_sources_file' 键指向另一个YAML文件。

    Args:
        main_config (Dict[str, Any]): 已加载的主配置字典。
                                     期望包含 '_config_file_abs_path_' 键。

    Returns:
        Optional[Dict[str, Any]]: 基因组数据源字典，如果失败则为None。
    """
    downloader_cfg = main_config.get('downloader', {})

    if 'genome_sources' in downloader_cfg and isinstance(downloader_cfg['genome_sources'], dict):
        print(_("从主配置中直接加载内嵌的 'genome_sources'。"))
        return downloader_cfg['genome_sources']
    elif 'genome_sources_file' in downloader_cfg:
        gs_file_path_rel = downloader_cfg['genome_sources_file']

        main_config_abs_path = main_config.get('_config_file_abs_path_')
        if not main_config_abs_path:
            print(_("错误: 主配置文件对象缺少 '_config_file_abs_path_' 键，无法解析相对路径。"))
            # 尝试将 gs_file_path_rel 视为相对于当前工作目录的路径
            gs_file_path_abs = os.path.abspath(gs_file_path_rel)
            print(_("警告: 将尝试从当前工作目录解析 genome_sources_file: {}").format(gs_file_path_abs))
        else:
            main_config_dir = os.path.dirname(main_config_abs_path)
            gs_file_path_abs = gs_file_path_rel
            if not os.path.isabs(gs_file_path_rel):  # 如果是相对路径
                gs_file_path_abs = os.path.join(main_config_dir, gs_file_path_rel)

        print(_("尝试从文件 '{}' 加载 'genome_sources'...").format(gs_file_path_abs))
        # 调用 load_config (不传递 _config_file_abs_path_ 给子配置，因为它自己会设置)
        genome_sources_config_content = load_config(gs_file_path_abs)

        if genome_sources_config_content and \
                'genome_sources' in genome_sources_config_content and \
                isinstance(genome_sources_config_content['genome_sources'], dict):
            print(_("从 '{}' 文件中成功加载 'genome_sources'。").format(gs_file_path_abs))
            return genome_sources_config_content['genome_sources']
        else:
            print(_("错误: 未能在 '{}' 文件中找到有效的 'genome_sources' 字典部分。").format(gs_file_path_abs))
            return None
    else:
        print(
            _("错误: 主配置的 'downloader' 部分缺少 'genome_sources' (直接定义) 或 'genome_sources_file' (文件路径) 定义。"))
        return None


# --- 新增功能：保存配置到YAML文件 ---
def save_config_to_yaml(config_dict: Dict[str, Any], file_path: str) -> bool:
    """
    将字典内容保存为YAML文件。

    Args:
        config_dict (Dict[str, Any]): 要保存的配置字典。
        file_path (str): YAML文件的保存路径。

    Returns:
        bool: 保存成功返回True，否则返回False。
    """
    try:
        # 确保目录存在
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(_("已创建目录: {}").format(output_dir))

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, allow_unicode=True, sort_keys=False, indent=2)
        print(_("配置文件已成功保存到 '{}'。").format(file_path))
        return True
    except Exception as e:
        print(_("错误: 保存配置文件 '{}' 失败: {}").format(file_path, e))
        return False

# --- 生成默认配置文件 ---
DEFAULT_MAIN_CONFIG_CONTENT = """
# config.yml
# 棉花基因组分析工具包 - 主配置文件

# --- 通用设置 ---
i18n_language: "zh-hans"
 # CLI的 --lang 参数可以覆盖此设置

# output_base_directory: "MyCottonAnalysisOutput" # (可选) 一个顶层的总输出目录，
                                               # downloader和pipeline的输出目录可以基于此设置相对路径。
                                               # 如果不设置，则各模块使用各自的默认输出目录或配置的绝对路径。

# --- 下载器配置 (downloader.py 使用) ---
downloader:
  # genome_sources_file 字段指向包含基因组版本具体下载链接的YAML文件。
  # 如果此路径是相对路径，它将被解析为相对于这个主 config.yaml 文件所在的目录。
  genome_sources_file: "genome_sources_list.yml"

  # 下载文件保存的基础目录。每个基因组版本的数据将在此目录下创建一个子目录。
  download_output_base_dir: "downloaded_cotton_data"

  force_download: false # false: 如果文件已存在则跳过下载; true: 强制重新下载
  max_workers: 3        # 多线程下载时使用的最大线程数

  proxies: # 网络代理设置 (如果不需要，则都设为 null 或删除整个 proxies 键)
    http: null  # 例如: "http://your-proxy-server:port"
    https: null # 例如: "http://your-proxy-server:port" or "socks5://user:pass@host:port"

# --- BSA与HVG整合流程配置 (pipelines.py 中的 integrate_bsa_with_hvg 函数使用) ---
integration_pipeline:
  # 1. 输入/输出 Excel 文件和 Sheet 名称
  input_excel_path: "path/to/your/input_data.xlsx" # 【请用户替换】您的包含BSA和HVG数据的Excel文件路径
  bsa_sheet_name: "BSA_Results"                   # 【请用户替换】BSA结果所在的Sheet名
  hvg_sheet_name: "HVG_List"                      # 【请用户替换】HVG数据所在的Sheet名
  output_sheet_name: "Combined_BSA_HVG_Analysis"  # 分析结果将写入此名称的新Sheet (在input_excel_path文件中)

  # 2. 基因组版本ID (这些ID必须与 genome_sources_list.yaml 中的键名匹配)
  bsa_assembly_id: "NBI_v1.1"     # 【请用户替换】您的BSA数据基于哪个棉花基因组版本
  hvg_assembly_id: "HAU_v2.0"     # 【请用户替换】您的HVG数据基于哪个棉花基因组版本
                                  # 如果两者相同，同源映射步骤将被跳过。

  # 3. GFF和同源CSV文件的路径
  #    脚本会尝试根据 downloader.download_output_base_dir 和上面的 assembly_id 动态构建这些路径。
  #    如果直接在此处指定了路径，则优先使用这里指定的路径。
  #    通常，您只需确保 downloader 下载了相应版本的数据，路径让脚本自动推断即可。
  #    推断逻辑： downloader_output_base_dir / <species_name_from_genome_sources> / <original_filename_from_url or default>
  #    例如, 对于NBI_v1.1的GFF，可能会推断为: downloaded_cotton_data/Gossypium_hirsutum_AD1_TM-1_NAU-NBI_v1.1/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz
  #    同源文件在下载后会被转换为 .csv，例如: downloaded_cotton_data/Gossypium_hirsutum_AD1_TM-1_NAU-NBI_v1.1/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.csv
  gff_files: # (可选) 如果您想覆盖自动推断的路径，或使用本地已有的GFF文件
    NBI_v1.1: null # 设置为 null 或不提供此键，则脚本会尝试自动推断路径
    HAU_v2.0: null # 例如: "local_data/HAU_v2.0_custom.gff3.gz"

  homology_files: # (可选, 仅当 bsa_assembly_id != hvg_assembly_id 时需要)
                  # 如果为 null 或不提供，脚本会尝试自动推断路径。
                  # 注意：路径应指向 downloader 转换后的 .csv 文件
    bsa_to_bridge_csv: null # 例如: "local_data/NBI_v1.1_to_At.csv" (源A -> 桥梁)
    bridge_to_hvg_csv: null # 例如: "local_data/At_to_HAU_v2.0.csv" (桥梁 -> 目标B)
                            # **重要**: 如果您只有一个 "棉花某版本 vs 拟南芥" 的同源文件，
                            # 您可能需要准备两份，或者确保 homology_mapper 能处理方向。
                            # 通常，bsa_to_bridge 是 [BSA版本基因Query, At基因Match]
                            # bridge_to_hvg 是 [At基因Query, HVG版本基因Match]

  bridge_species_name: "Arabidopsis_thaliana" # 同源映射的桥梁物种
  gff_db_storage_dir: "gff_databases_cache"   # gffutils数据库的存放目录 (可相对或绝对路径)
                                            # 如果为null，数据库会创建在GFF文件旁边
  force_gff_db_creation: false # 是否强制重新创建GFF数据库，即使已存在

  # 4. BSA表中的列名配置
  bsa_columns:
    chr: 'chr'
    start: 'region.start'
    end: 'region.end'
    # fine_mapping_potential: 'Potential_Score' # (可选) 如果您有用于筛选BSA区域的列

  # 5. HVG表中的列名配置
  hvg_columns:
    gene_id: 'gene_id' # HVG表中的基因ID列
    category: 'hvg_category' # HVG分类列 ("WT特有TopHVG", "Ms1特有TopHVG", "共同TopHVG")
    log2fc: 'log2fc_WT_vs_Ms1' # Log2FC (WT vs Ms1) 列
    # (可选) HVG表中基因自己的坐标列，主要用于验证或额外信息展示
    # chr: 'hvg_chr'
    # start: 'hvg_gene_start'
    # end: 'hvg_gene_end'

  # 6. 同源表中的列名配置 (假设两张同源表 Query, Match, Exp, Score, PID 列名一致)
  homology_columns:
    query: "Query"   # 源基因ID列
    match: "Match"   # 匹配到的同源基因ID列
    evalue: "Exp"    # E-value列
    score: "Score"   # 比对打分列
    pid: "PID"       # 百分比一致性列

  # 7. 同源映射的“裁剪方法”/选择标准
  selection_criteria_source_to_bridge: # 源棉花基因组 -> 桥梁物种 (拟南芥)
    sort_by: ["Score", "Exp"]      # 排序依据：先按Score，再按Exp。可选 "Score", "Exp", "PID"
    ascending: [false, true]       # Score降序 (越大越好), Exp升序 (越小越好)
    top_n: 1                       # 每个源基因只选1个最佳桥梁同源
    evalue_threshold: 1.0e-10      # E-value 必须 <= 1e-10
    pid_threshold: 30.0            # PID 必须 >= 30.0
    score_threshold: 50.0          # Score 必须 >= 50.0

  selection_criteria_bridge_to_target: # 桥梁物种 (拟南芥) -> 目标棉花基因组
    sort_by: ["Score", "PID"]      # 先按Score，再按PID
    ascending: [false, false]      # Score降序, PID降序
    top_n: 1                       # 每个桥梁基因只选1个最佳目标同源
    evalue_threshold: 1.0e-15
    pid_threshold: 40.0
    score_threshold: 80.0

  # 8. "共同TopHVG" 类别判断 Log2FC 是否显著的阈值 (绝对值)
  common_hvg_log2fc_threshold: 1.0
"""

DEFAULT_GENOME_SOURCES_CONTENT = """
genome_sources:
  BGI_v1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CGP-BGI_G.hirsutum_AD1genome/genes/BGI_Gossypium_hirsutum_v1.0.cds.gff.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CGP-BGI_G.hirsutum_AD1genome/protein_homology_2019/blastp_G.hirsutum_CGP-BGI_v1.0_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome CGP-BGI_v1"
    # 如果不需要剪切，请设为 null
    homology_id_slicer: "_"

  NBI_v1.1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"
    # 如果不需要剪切，请设为 null
    homology_id_slicer: "_"

  UTX_v2.1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1"
    # 如果不需要剪切，请设为 null
    homology_id_slicer: "_"

  WHU_v1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/homology/blastp_G.hirsutum_WHU_v1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome WHU_v1"
    # 如果不需要剪切，请设为 null
    homology_id_slicer: "_"

  HAU_v2.0:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0"
    # 如果不需要剪切，请设为 null
    homology_id_slicer: "_"
"""


def generate_default_config_files(
        output_dir: str,
        main_config_filename: str = "config.yml",
        genome_sources_filename: str = "genome_sources_list.yml",
        overwrite: bool = False
) -> Tuple[bool, str, str]:
    """
    生成默认的 config.yml 和 genome_sources_list.yml 文件。

    Args:
        output_dir (str): 文件保存的目录。
        main_config_filename (str): 主配置文件的文件名。
        genome_sources_filename (str): 基因组源配置文件的文件名。
        overwrite (bool): 如果文件已存在，是否覆盖。

    Returns:
        Tuple[bool, str, str]: (是否成功, 生成的主配置文件路径, 生成的基因组源文件路径)
    """
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            print(_("已创建目录: {}").format(output_dir))
        except OSError as e:
            print(_("错误: 创建目录 '{}' 失败: {}").format(output_dir, e))
            return False, "", ""

    main_config_path = os.path.join(output_dir, main_config_filename)
    genome_sources_path = os.path.join(output_dir, genome_sources_filename)

    success_main = False
    success_gs = False
    messages = []

    # 保存主配置文件
    if os.path.exists(main_config_path) and not overwrite:
        messages.append(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_filename))
        success_main = True # 标记为成功，因为没生成是故意的
    else:
        try:
            # 将默认字符串内容解析为字典，再保存，确保格式一致
            main_config_dict = yaml.safe_load(DEFAULT_MAIN_CONFIG_CONTENT)
            if save_config_to_yaml(main_config_dict, main_config_path):
                messages.append(_("默认主配置文件已生成到 '{}'。").format(main_config_path))
                success_main = True
            else:
                messages.append(_("错误: 无法生成默认主配置文件 '{}'。").format(main_config_filename))
        except yaml.YAMLError as e:
            messages.append(_("错误: 默认主配置文件内容解析失败: {}").format(e))
        except Exception as e:
            messages.append(_("错误: 生成默认主配置文件时发生未知错误: {}").format(e))

    # 保存基因组源文件
    if os.path.exists(genome_sources_path) and not overwrite:
        messages.append(_("警告: 基因组源文件 '{}' 已存在，跳过生成。").format(genome_sources_filename))
        success_gs = True # 标记为成功，因为没生成是故意的
    else:
        try:
            gs_config_dict = yaml.safe_load(DEFAULT_GENOME_SOURCES_CONTENT)
            if save_config_to_yaml(gs_config_dict, genome_sources_path):
                messages.append(_("默认基因组源文件已生成到 '{}'。").format(genome_sources_path))
                success_gs = True
            else:
                messages.append(_("错误: 无法生成默认基因组源文件 '{}'。").format(genome_sources_filename))
        except yaml.YAMLError as e:
            messages.append(_("错误: 默认基因组源文件内容解析失败: {}").format(e))
        except Exception as e:
            messages.append(_("错误: 生成默认基因组源文件时发生未知错误: {}").format(e))

    for msg in messages:
        print(msg)

    return success_main and success_gs, main_config_path, genome_sources_path


if __name__ == '__main__':
    # --- 用于独立测试 loader.py 的示例代码 ---
    print("--- 测试 config_loader.py ---")

    # 为了测试，我们需要一个临时的i18n设置
    if '_' not in globals() or _("test") == "test":  # 检查 _ 是否是有效的gettext函数
        def _(text): return f"LANG_STR({text})"  # 模拟翻译函数，方便看出是否被调用


        print("loader.py __main__: Applied MOCK _ function for testing.")

    # 1. 创建临时的测试配置文件
    temp_dir = "temp_config_test_dir"
    os.makedirs(temp_dir, exist_ok=True)

    main_cfg_filename = "main_test_config.yaml"
    sources_cfg_filename = "sources_test_list.yaml"

    main_cfg_path = os.path.join(temp_dir, main_cfg_filename)
    sources_cfg_path = os.path.join(temp_dir, sources_cfg_filename)

    # 2. 写入 genome_sources_list.yaml 的内容
    genome_sources_data_for_yaml = {
        "genome_sources": {
            "NBI_v1.1_loader_test": {
                "gff3_url": "http://test.com/nbi/ann.gff3.gz",
                "homology_ath_url": "http://test.com/nbi/hom.xlsx.gz",
                "species_name": "G_hirsutum_NBI_v1.1_loader_test"
            }
        }
    }
    with open(sources_cfg_path, 'w', encoding='utf-8') as f:
        yaml.dump(genome_sources_data_for_yaml, f, allow_unicode=True, sort_keys=False)
    print(f"\n创建了临时的基因组源文件: {sources_cfg_path}")

    # 3. 写入主 config.yaml 的内容 (引用上面的文件)
    main_config_data_for_yaml = {
        "i18n_language": "zh_CN",
        "downloader": {
            "genome_sources_file": sources_cfg_filename,  # 使用相对路径测试
            "download_output_base_dir": "test_loader_downloads",
        },
        "integration_pipeline": {
            "input_excel_path": "test_data_for_loader.xlsx"
        }
    }
    with open(main_cfg_path, 'w', encoding='utf-8') as f:
        yaml.dump(main_config_data_for_yaml, f, allow_unicode=True, sort_keys=False)
    print(f"创建了临时的主要配置文件: {main_cfg_path}")

    # 4. 测试加载主配置
    print("\n--- 测试 load_config ---")
    loaded_main_config = load_config(main_cfg_path)
    if loaded_main_config:
        print("主配置加载内容:")
        import json

        print(json.dumps(loaded_main_config, indent=2, ensure_ascii=False))  # 用json打印更易读
        assert loaded_main_config['_config_file_abs_path_'] == os.path.abspath(main_cfg_path)

        # 5. 测试从主配置中获取 genome_sources
        print("\n--- 测试 get_genome_data_sources ---")
        genome_sources = get_genome_data_sources(loaded_main_config)
        if genome_sources:
            print("从主配置中间接加载的 Genome Sources 内容:")
            print(json.dumps(genome_sources, indent=2, ensure_ascii=False))
            assert "NBI_v1.1_loader_test" in genome_sources
        else:
            print("未能通过 get_genome_data_sources 加载 Genome Sources。")
    else:
        print("主配置文件加载失败。")

    # 6. 测试直接在主配置中内嵌 genome_sources
    main_config_embedded_sources = {
        "_config_file_abs_path_": os.path.abspath(main_cfg_path),  # 模拟
        "downloader": {
            "genome_sources": {
                "EMBEDDED_V1": {"species_name": "Embedded_Species_V1"}
            }
        }
    }
    print("\n--- 测试 get_genome_data_sources (内嵌式) ---")
    embedded_gs = get_genome_data_sources(main_config_embedded_sources)
    if embedded_gs:
        print("内嵌式 Genome Sources 内容:")
        print(json.dumps(embedded_gs, indent=2, ensure_ascii=False))
        assert "EMBEDDED_V1" in embedded_gs
    else:
        print("内嵌式 Genome Sources 加载失败。")

    # --- 新增测试：保存配置 ---
    print("\n--- 测试 save_config_to_yaml ---")
    test_save_config_path = os.path.join(temp_dir, "test_saved_config.yaml")
    test_data_to_save = {"key1": "value1", "nested_key": {"sub_key": 123}}
    save_success = save_config_to_yaml(test_data_to_save, test_save_config_path)
    assert save_success, "保存配置文件测试失败"
    loaded_saved_config = load_config(test_save_config_path)
    assert loaded_saved_config and loaded_saved_config['key1'] == 'value1', "加载保存的配置文件失败"
    print("save_config_to_yaml 测试通过。")

    # --- 新增测试：生成默认配置文件 ---
    print("\n--- 测试 generate_default_config_files ---")
    default_output_dir = os.path.join(temp_dir, "default_configs")
    gen_success, gen_main_path, gen_gs_path = generate_default_config_files(default_output_dir, overwrite=True)
    assert gen_success, "生成默认配置文件测试失败"
    assert os.path.exists(gen_main_path) and os.path.exists(gen_gs_path), "默认文件未创建"
    print(f"默认配置文件生成测试通过，文件位于: {default_output_dir}")

    # 清理测试文件和目录
    try:
        shutil.rmtree(temp_dir)
        print(f"\n已清理临时测试目录: {temp_dir}")
    except Exception as e_clean:
        print(f"清理临时目录 {temp_dir} 时出错: {e_clean}")

    print("\n--- config_loader.py 测试结束 ---")