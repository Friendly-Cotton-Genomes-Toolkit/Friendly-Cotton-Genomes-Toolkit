# cotton_toolkit/config/loader.py
import shutil
import yaml
import os
from typing import Dict, Any, Optional, Tuple

# 假设 _ 函数已由主程序设置
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


def load_config(config_path: str) -> Optional[Dict[str, Any]]:
    """
    加载并返回YAML配置文件内容。
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
    """
    downloader_cfg = main_config.get('downloader', {})
    if 'genome_sources' in downloader_cfg and isinstance(downloader_cfg['genome_sources'], dict):
        print(_("从主配置中直接加载内嵌的 'genome_sources'。"))
        return downloader_cfg['genome_sources']
    elif 'genome_sources_file' in downloader_cfg:
        gs_file_path_rel = downloader_cfg['genome_sources_file']
        main_config_abs_path = main_config.get('_config_file_abs_path_')
        if not main_config_abs_path:
            gs_file_path_abs = os.path.abspath(gs_file_path_rel)
            print(_("警告: 将尝试从当前工作目录解析 genome_sources_file: {}").format(gs_file_path_abs))
        else:
            main_config_dir = os.path.dirname(main_config_abs_path)
            gs_file_path_abs = os.path.join(main_config_dir, gs_file_path_rel) if not os.path.isabs(
                gs_file_path_rel) else gs_file_path_rel

        print(_("尝试从文件 '{}' 加载 'genome_sources'...").format(gs_file_path_abs))
        genome_sources_config_content = load_config(gs_file_path_abs)
        if genome_sources_config_content and 'genome_sources' in genome_sources_config_content and isinstance(
                genome_sources_config_content['genome_sources'], dict):
            print(_("从 '{}' 文件中成功加载 'genome_sources'。").format(gs_file_path_abs))
            return genome_sources_config_content['genome_sources']
        else:
            print(_("错误: 未能在 '{}' 文件中找到有效的 'genome_sources' 字典部分。").format(gs_file_path_abs))
            return None
    else:
        print(
            _("错误: 主配置的 'downloader' 部分缺少 'genome_sources' (直接定义) 或 'genome_sources_file' (文件路径) 定义。"))
        return None


def save_config_to_yaml(config_dict: Dict[str, Any], file_path: str) -> bool:
    """
    将字典内容保存为YAML文件。
    """
    try:
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


# --- 【更新】默认配置文件内容，增加了 ai_services 和 annotation_tool ---
DEFAULT_MAIN_CONFIG_CONTENT = """
# config.yml
# 棉花基因组分析工具包 - 主配置文件

# --- 通用设置 ---
i18n_language: "zh-hans"

# --- 下载器配置 (downloader) ---
downloader:
  genome_sources_file: "genome_sources_list.yml"
  download_output_base_dir: "downloaded_cotton_data"
  force_download: false
  max_workers: 3
  proxies:
    http: null  # 例如: "http://127.0.0.1:7890"
    https: null # 例如: "http://127.0.0.1:7890"

# --- 【新增】AI 服务配置 (ai_services) ---
ai_services:
  # 当前使用的服务提供商，从下面的 providers 中选择一个
  default_provider: "google"

  providers:
    # 谷歌 Gemini API 配置
    google:
      # 在 https://aistudio.google.com/app/apikey 获取
      api_key: "YOUR_GOOGLE_API_KEY"
      # 通常无需修改
      base_url: "https://generativelanguage.googleapis.com/v1beta"
      # 默认使用的模型
      model: "models/gemini-1.5-flash-latest"

    # OpenAI API 配置
    openai:
      # 在 https://platform.openai.com/api-keys 获取
      api_key: "YOUR_OPENAI_API_KEY"
      # 官方API地址，如果使用第三方代理则修改
      base_url: "https://api.openai.com/v1"
      # 默认使用的模型
      model: "gpt-4o-mini"

    # Groq API 配置 (或其他兼容OpenAI格式的第三方服务)
    groq:
      api_key: "YOUR_GROQ_API_KEY"
      base_url: "https://api.groq.com/openai/v1"
      model: "llama3-8b-8192"

# --- 【新增】功能注释工具配置 (annotation_tool) ---
annotation_tool:
  # 本地功能注释数据库文件的根目录
  database_root_dir: "annotation_databases"
  # 数据库文件名映射
  database_files:
    go: "AD1_HAU_v1.0_genes2Go.csv"
    ipr: "AD1_HAU_v1.0_genes2IPR.csv"
    kegg_orthologs: "AD1_HAU_v1.0_KEGG-orthologs.csv"
    kegg_pathways: "AD1_HAU_v1.0_KEGG-pathways.csv"
  # 数据库文件中列名的配置
  database_columns:
    query: "Query"
    match: "Match"
    description: "Description"

# --- 整合流程配置 (integration_pipeline) ---
integration_pipeline:
  input_excel_path: "path/to/your/input_data.xlsx"
  bsa_sheet_name: "BSA_Results"
  hvg_sheet_name: "HVG_List"
  output_sheet_name: "Combined_BSA_HVG_Analysis"
  bsa_assembly_id: "NBI_v1.1"
  hvg_assembly_id: "HAU_v2.0"
  bridge_species_name: "Arabidopsis_thaliana"
  gff_db_storage_dir: "gff_databases_cache"
  force_gff_db_creation: false

  # 文件路径 (gff_files, homology_files)
  # 设为 null 则程序会自动根据下载目录和版本ID推断路径
  gff_files:
    NBI_v1.1: null
    HAU_v2.0: null
  homology_files:
    bsa_to_bridge_csv: null
    bridge_to_hvg_csv: null

  # 列名配置
  bsa_columns:
    chr: 'chr'
    start: 'region.start'
    end: 'region.end'
  hvg_columns:
    gene_id: 'gene_id'
    category: 'hvg_category'
    log2fc: 'log2fc_WT_vs_Ms1'
  homology_columns:
    query: "Query"
    match: "Match"
    evalue: "Exp"
    score: "Score"
    pid: "PID"

  # 同源筛选标准
  selection_criteria_source_to_bridge:
    sort_by: ["Score", "Exp"]
    ascending: [false, true]
    top_n: 1
    evalue_threshold: 1.0e-10
    pid_threshold: 30.0
    score_threshold: 50.0
  selection_criteria_bridge_to_target:
    sort_by: ["Score", "PID"]
    ascending: [false, false]
    top_n: 1
    evalue_threshold: 1.0e-15
    pid_threshold: 40.0
    score_threshold: 80.0

  common_hvg_log2fc_threshold: 1.0
"""

# 默认基因组源文件内容保持不变
DEFAULT_GENOME_SOURCES_CONTENT = """
genome_sources:
  BGI_v1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CGP-BGI_G.hirsutum_AD1genome/genes/BGI_Gossypium_hirsutum_v1.0.cds.gff.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CGP-BGI_G.hirsutum_AD1genome/protein_homology_2019/blastp_G.hirsutum_CGP-BGI_v1.0_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome CGP-BGI_v1"
    homology_id_slicer: "_"
  NBI_v1.1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"
    homology_id_slicer: "_"
  UTX_v2.1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1"
    homology_id_slicer: "_"
  WHU_v1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/homology/blastp_G.hirsutum_WHU_v1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome WHU_v1"
    homology_id_slicer: "_"
  HAU_v2.0:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0"
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

    # 保存主配置文件
    if os.path.exists(main_config_path) and not overwrite:
        print(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_path))
        success_main = True
    else:
        try:
            main_config_dict = yaml.safe_load(DEFAULT_MAIN_CONFIG_CONTENT)
            if save_config_to_yaml(main_config_dict, main_config_path):
                success_main = True
        except Exception as e:
            print(_("错误: 生成默认主配置文件时发生未知错误: {}").format(e))

    # 保存基因组源文件
    if os.path.exists(genome_sources_path) and not overwrite:
        print(_("警告: 基因组源文件 '{}' 已存在，跳过生成。").format(genome_sources_path))
        success_gs = True
    else:
        try:
            gs_config_dict = yaml.safe_load(DEFAULT_GENOME_SOURCES_CONTENT)
            if save_config_to_yaml(gs_config_dict, genome_sources_path):
                success_gs = True
        except Exception as e:
            print(_("错误: 生成默认基因组源文件时发生未知错误: {}").format(e))

    return success_main and success_gs, main_config_path, genome_sources_path