# cotton_toolkit/config/loader.py
import shutil
import yaml
import os
from typing import Dict, Any, Optional, Tuple
from .models import MainConfig, GenomeSourcesConfig
from dataclasses import asdict, is_dataclass

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class Dumper(yaml.Dumper):
    """自定义YAML Dumper，用于正确序列化dataclass"""

    def represent_data(self, data):
        if is_dataclass(data):
            return self.represent_dict(asdict(data))
        return super().represent_data(data)


def save_config(config_obj: Any, file_path: str) -> bool:
    """将配置对象 (dataclass) 保存为YAML文件。"""
    try:
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(_("已创建目录: {}").format(output_dir))

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(asdict(config_obj), f, Dumper=Dumper, allow_unicode=True, sort_keys=False, indent=2)

        print(_("配置文件已成功保存到 '{}'。").format(file_path))
        return True
    except Exception as e:
        print(_("错误: 保存配置文件 '{}' 失败: {}").format(file_path, e))
        return False


def load_config(config_path: str) -> Optional[MainConfig]:
    """加载YAML文件并返回一个MainConfig对象，包含版本校验。"""
    if not os.path.exists(config_path):
        print(_("错误: 配置文件 '{}' 未找到。").format(config_path))
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise TypeError(_("配置文件顶层结构必须是一个字典。"))

        if data.get('config_version') != 1:
            raise ValueError(_("配置文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(config_path))

        config_obj = MainConfig.from_dict(data)
        config_obj._config_file_abs_path_ = os.path.abspath(config_path)
        print(_("配置文件 '{}' 加载成功。").format(config_path))
        return config_obj
    except (TypeError, ValueError) as e:
        raise e
    except Exception as e:
        import traceback
        print(_("加载配置文件 '{}' 时发生未知错误: {}").format(config_path, e))
        traceback.print_exc()
        return None


def get_genome_data_sources(main_config: MainConfig) -> Optional[Dict[str, Any]]:
    """从主配置对象中获取或加载基因组数据源。"""

    downloader_cfg = main_config.get('downloader')
    if not downloader_cfg:
        print(_("错误: 配置对象不完整，缺少 'downloader' 部分。"))
        return None

    gs_file_rel = downloader_cfg.get('genome_sources_file')
    if not gs_file_rel:
        print(_("错误: 主配置的 'downloader' 部分缺少 'genome_sources_file' 定义。"))
        return None

    main_config_dir = os.path.dirname(
        main_config._config_file_abs_path_) if main_config._config_file_abs_path_ else os.getcwd()
    gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

    if not os.path.exists(gs_file_path_abs):
        print(_("错误: 基因组源文件 '{}' 未找到。").format(gs_file_path_abs))
        return None

    try:
        with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if data.get('list_version') != 1:
            print(_("错误: 基因组源文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(gs_file_path_abs))
            return None

        gs_config = GenomeSourcesConfig.from_dict(data)
        return {k: asdict(v) for k, v in gs_config.genome_sources.items()}
    except Exception as e:
        print(_("错误: 加载或解析基因组源文件 '{}' 失败: {}").format(gs_file_path_abs, e))
        return None


# cotton_toolkit/config/loader.py

def generate_default_config_files(
        output_dir: str,
        main_config_filename: str = "config.yml",
        genome_sources_filename: str = "genome_sources_list.yml",
        overwrite: bool = False
) -> Tuple[bool, str, str]:
    """
    通过实例化配置类并填充详细信息来生成默认的配置文件，并支持覆盖选项。
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    main_config_path = os.path.join(output_dir, main_config_filename)
    success_main = True

    # --- PART 1: 生成主配置文件 (config.yml) ---
    if os.path.exists(main_config_path) and not overwrite:
        print(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_path))
    else:
        # 实例化一个空的配置对象，然后手动填充所有期望的默认值
        main_conf_default = MainConfig()
        main_conf_default.downloader.genome_sources_file = genome_sources_filename

        # Downloader Config
        main_conf_default.downloader.download_output_base_dir = "downloaded_cotton_data"
        main_conf_default.downloader.force_download = False
        main_conf_default.downloader.max_workers = 3
        # 【修改】不再设置代理的默认值，将生成空的 proxies: {}
        # main_conf_default.downloader.proxies = {'http': '127.0.0.1:7890', 'https': '127.0.0.1:7890'}

        # AI Services Config
        main_conf_default.ai_services.default_provider = "google"
        # 【修改】不再为任何提供商设置API-KEY的默认值，将生成空的 api_key: ""
        # main_conf_default.ai_services.providers['google'].api_key = "YOUR_GOOGLE_API_KEY"
        main_conf_default.ai_services.providers['google'].model = "gemini-1.5-flash-latest"
        main_conf_default.ai_services.providers[
            'google'].base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        # AI Prompts Config
        main_conf_default.ai_prompts.translation_prompt = "请将以下生物学领域的文本翻译成中文：\\n\\n---\\n{text}\\n---\\n\\n请只返回翻译结果，不要包含任何额外的解释或说明。"
        main_conf_default.ai_prompts.analysis_prompt = "我正在研究植物雄性不育，请分析以下基因功能描述与我的研究方向有何关联，并提供一个简洁的总结。基因功能描述：\\n\\n---\\n{text}\\n---"

        # Annotation Tool Config
        main_conf_default.annotation_tool.database_root_dir = "annotation_databases"
        main_conf_default.annotation_tool.database_files = {
            'go': 'AD1_HAU_v1.0_genes2Go.csv', 'ipr': 'AD1_HAU_v1.0_genes2IPR.csv',
            'kegg_orthologs': 'AD1_HAU_v1.0_KEGG-orthologs.csv', 'kegg_pathways': 'AD1_HAU_v1.0_KEGG-pathways.csv'
        }
        main_conf_default.annotation_tool.database_columns = {'query': 'Query', 'match': 'Match',
                                                              'description': 'Description'}

        # Integration Pipeline Config
        main_conf_default.integration_pipeline.input_excel_path = "path/to/your/input_data.xlsx"
        main_conf_default.integration_pipeline.bsa_sheet_name = "BSA_Results"
        main_conf_default.integration_pipeline.hvg_sheet_name = "HVG_List"
        main_conf_default.integration_pipeline.output_sheet_name = "Combined_BSA_HVG_Analysis"
        main_conf_default.integration_pipeline.bsa_assembly_id = "NBI_v1.1"
        main_conf_default.integration_pipeline.hvg_assembly_id = "HAU_v2.0"
        main_conf_default.integration_pipeline.bridge_species_name = "Arabidopsis_thaliana"
        main_conf_default.integration_pipeline.gff_db_storage_dir = "gff_databases_cache"
        main_conf_default.integration_pipeline.force_gff_db_creation = False
        main_conf_default.integration_pipeline.gff_files = {'NBI_v1.1': None, 'HAU_v2.0': None}
        main_conf_default.integration_pipeline.homology_files = {'bsa_to_bridge_csv': None, 'bridge_to_hvg_csv': None}
        main_conf_default.integration_pipeline.bsa_columns = {'chr': 'chr', 'start': 'region.start',
                                                              'end': 'region.end'}
        main_conf_default.integration_pipeline.hvg_columns = {'gene_id': 'gene_id', 'category': 'hvg_category',
                                                              'log2fc': 'log2fc_WT_vs_Ms1'}
        main_conf_default.integration_pipeline.homology_columns = {'query': 'Query', 'match': 'Match', 'evalue': 'Exp',
                                                                   'score': 'Score', 'pid': 'PID'}
        main_conf_default.integration_pipeline.selection_criteria_source_to_bridge = {
            'sort_by': ['Score', 'Exp'], 'ascending': [False, True], 'top_n': 1,
            'evalue_threshold': 1.0e-10, 'pid_threshold': 30.0, 'score_threshold': 50.0
        }
        main_conf_default.integration_pipeline.selection_criteria_bridge_to_target = {
            'sort_by': ['Score', 'Exp'], 'ascending': [False, True], 'top_n': 1,
            'evalue_threshold': 1.0e-15, 'pid_threshold': 40.0, 'score_threshold': 80.0
        }
        main_conf_default.integration_pipeline.common_hvg_log2fc_threshold = 1.0

        success_main = save_config(main_conf_default, main_config_path)

    # --- PART 2: 生成物种来源文件 (genome_sources_list.yml) ---
    genome_sources_path = os.path.join(output_dir, genome_sources_filename)
    success_gs = True
    if os.path.exists(genome_sources_path) and not overwrite:
        print(_("警告: 物种来源文件 '{}' 已存在，跳过生成。").format(genome_sources_path))
    else:
        # 定义您期望的完整默认物种来源数据
        default_genome_sources = {
            'list_version': 1,
            'genome_sources': {
                'NBI_v1.1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2GO.txt.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2IPR.txt.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.pathways.txt.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.orthologs.txt.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                },
                'JGI_v1.1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome UTX-JGI-Interim-release_v1.1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/genes/Tx-JGI_G.hirsutum_v1.1.gene_exons.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2GO.txt.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2IPR.txt.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-pathways.txt.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-orthologs.txt.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_Tx-JGI_v1.1_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                },
                'HAU_v1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome HAU_v1 / v1.1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/genes/Ghirsutum_gene_model.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/homology/blastp_AD1_HAU_v1.0_vs_arabidopsis.xlsx.gz",
                    'homology_type': "tair10",
                    'homology_id_slicer': "_"
                },
                'ZJU_v2.1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome ZJU-improved_v2.1_a1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/genes/TM-1_V2.1.gene.gff.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/homology/blastp_G.hirsutum_ZJU-AD1_v2.1_vs_arabidopsis.xlsx.gz",
                    'homology_type': "tair10",
                    'homology_id_slicer': "_"
                },
                'CRI_v1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome CRI_v1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/genes/TM_1.Chr_genome_all_transcripts_final_gene.change.gff.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/homology/blastp_G.hirsutum_CRI_TM1-v1.0_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                },
                'WHU_v1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome WHU_v1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/homology/blastp_G.hirsutum_WHU_v1_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                },
                'UTX_v2.1': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                },
                'HAU_v2.0': {
                    'species_name': "Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0",
                    'gff3_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz",
                    'GO_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2Go.xlsx.gz",
                    'IPR_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2IPR.xlsx.gz",
                    'KEGG_pathways_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-pathways.xlsx.gz",
                    'KEGG_orthologs_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-orthologs.xlsx.gz",
                    'homology_ath_url': "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz",
                    'homology_type': "Araport11",
                    'homology_id_slicer': "_"
                }
            }
        }
        try:
            with open(genome_sources_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_genome_sources, f, Dumper=Dumper, allow_unicode=True, sort_keys=False, indent=2)
            print(_("成功生成默认物种来源文件: {}").format(genome_sources_path))
        except Exception as e:
            print(_("错误: 生成默认物种来源文件 '{}' 失败: {}").format(genome_sources_path, e))
            success_gs = False

    return success_main and success_gs, main_config_path, genome_sources_path


