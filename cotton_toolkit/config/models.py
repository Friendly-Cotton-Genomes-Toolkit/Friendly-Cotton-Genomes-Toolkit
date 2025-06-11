# cotton_toolkit/config/models.py

from dataclasses import dataclass, field, fields, is_dataclass, asdict, MISSING
from typing import Dict, Any, Optional, List, Type, get_origin, \
    get_args  # Import get_origin, get_args for generic types


# --- 基类和辅助方法 ---
class ConfigDataModel:
    """基类，为所有配置数据模型提供字典式访问和 to_dict 方法。"""

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key): return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def items(self):
        class_fields = {f.name for f in fields(self) if f.init}
        return {k: v for k, v in vars(self).items() if k in class_fields}.items()

    def setdefault(self, key: str, default: Any = None) -> Any:
        """实现类似字典的 setdefault 方法，以兼容旧代码。"""
        if not hasattr(self, key):
            setattr(self, key, default)
        return getattr(self, key)

    def to_dict(self):
        """将 dataclass 实例及其嵌套的 dataclass 递归转换为字典。"""
        data = asdict(self)
        # 移除内部字段 (如果存在)
        data.pop('_config_file_abs_path_', None)
        return data

    @classmethod
    def from_dict(cls: Type, data: Dict[str, Any]) -> Any:
        """
        从字典创建 dataclass 实例。
        这个方法会确保所有字段（包括嵌套的 dataclass）都根据默认值正确填充。
        """
        instance_data = {}
        for f in fields(cls):
            if f.init:  # 只处理需要初始化的字段
                field_value = data.get(f.name)

                # Handling missing values and default values
                if field_value is None:
                    if f.default is not MISSING:
                        instance_data[f.name] = f.default
                    elif f.default_factory is not MISSING:
                        instance_data[f.name] = f.default_factory()
                    else:
                        # If value is None and no default/factory, and it's not Optional, this might be an issue
                        # For now, let dataclasses handle strictness or allow None for Optional
                        instance_data[f.name] = None  # Explicitly set to None if missing and no default
                    continue  # Skip to next field

                # Handling nested dataclasses (e.g., DownloaderConfig, ProxyConfig)
                if is_dataclass(f.type):
                    if isinstance(field_value, dict):
                        instance_data[f.name] = f.type.from_dict(field_value)
                    else:
                        # If it's a dataclass type but not a dict, keep it as is (e.g., already an instance)
                        instance_data[f.name] = field_value
                # Handling generic types like Dict[str, SomeDataclass] or List[SomeDataclass]
                else:
                    origin = get_origin(f.type)  # e.g., dict, list
                    args = get_args(f.type)  # e.g., (str, ProviderConfig) for Dict[str, ProviderConfig]

                    if origin is dict and len(args) == 2 and is_dataclass(args[1]):
                        # This is Dict[KeyType, ValueType] where ValueType is a dataclass
                        nested_dataclass_type = args[1]
                        converted_dict_values = {}
                        if isinstance(field_value, dict):
                            for key, val_dict in field_value.items():
                                if isinstance(val_dict, dict):
                                    converted_dict_values[key] = nested_dataclass_type.from_dict(val_dict)
                                else:
                                    # If value is not a dict, but expected dataclass, might be an issue.
                                    # For now, keep as is, but this might indicate malformed data.
                                    converted_dict_values[key] = val_dict
                        instance_data[f.name] = converted_dict_values
                    elif origin is list and len(args) == 1 and is_dataclass(args[0]):
                        # This is List[SomeDataclass]
                        nested_dataclass_type = args[0]
                        converted_list_values = []
                        if isinstance(field_value, list):
                            for item_dict in field_value:
                                if isinstance(item_dict, dict):
                                    converted_list_values.append(nested_dataclass_type.from_dict(item_dict))
                                else:
                                    converted_list_values.append(item_dict)
                        instance_data[f.name] = converted_list_values
                    else:
                        # For all other types (int, str, plain list, plain dict, etc.), use the value directly
                        instance_data[f.name] = field_value
        return cls(**instance_data)


# --- 配置子模型 (所有都继承 ConfigDataModel) ---

@dataclass
class ProxyConfig(ConfigDataModel):
    http: Optional[str] = None
    https: Optional[str] = None


@dataclass
class ProviderConfig(ConfigDataModel):
    api_key: str = "YOUR_API_KEY_HERE"
    model: str = "default-model"
    base_url: Optional[str] = None


@dataclass
class DownloaderConfig(ConfigDataModel):
    max_workers: int = 8
    genome_sources_file: str = "genome_sources_list.yml"
    download_output_base_dir: str = "genomes"
    force_download: bool = False
    proxies: ProxyConfig = field(default_factory=ProxyConfig)  # Use default_factory for mutable defaults


@dataclass
class LocusConversionConfig(ConfigDataModel):
    # 位点转换的默认输出目录
    output_dir_name: str = "locus_conversion_results"
    # GFF 数据库缓存目录 (与 integration_pipeline 可共享或独立)
    gff_db_storage_dir: str = "gff_databases_cache"
    # 是否强制重新创建 GFF 数据库 (即使已存在)
    force_gff_db_creation: bool = False
    # 如果需要，可以添加同源映射的筛选标准，但目前我们复用 HomologySelectionCriteria
    # selection_criteria: HomologySelectionCriteria = field(default_factory=HomologySelectionCriteria)


@dataclass
class AIServicesConfig(ConfigDataModel):
    default_provider: str = "google"
    providers: Dict[str, ProviderConfig] = field(default_factory=lambda: {
        "google": ProviderConfig(model="gemini-1.5-flash", api_key="YOUR_GOOGLE_API_KEY", base_url='https://generativelanguage.googleapis.com/v1beta/openai/'),
        "openai": ProviderConfig(model="gpt-4o", api_key="YOUR_OPENAI_API_KEY", base_url='https://api.openai.com/v1'),
        "deepseek": ProviderConfig(model="deepseek-chat", api_key="YOUR_DEEPSEEK_API_KEY",
                                   base_url="https://api.deepseek.com/v1"),
        "qwen": ProviderConfig(model="qwen-turbo", api_key="YOUR_QWEN_API_KEY",
                               base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "siliconflow": ProviderConfig(model="alibaba/Qwen2-7B-Instruct", api_key="YOUR_SILICONFLOW_API_KEY",
                                      base_url="https://api.siliconflow.cn/v1"),
        "grok": ProviderConfig(model="grok-1.0", api_key="YOUR_GROK_API_KEY", base_url="https://api.x.ai/v1"),
        "openai_compatible": ProviderConfig(model="custom-model", api_key="YOUR_CUSTOM_API_KEY",
                                            base_url="http://localhost:8000/v1")
    })


@dataclass
class AIPromptsConfig(ConfigDataModel):
    translation_prompt: str = "请将以下生物学领域的文本翻译成中文：\n\n{text}\n\n请只返回翻译结果，不要包含任何额外的解释或说明。"
    analysis_prompt: str = "我正在研究生物学领域的课题，请分析以下基因功能描述与我的研究方向有何关联，并提供一个简洁的总结。基因功能描述：\n\n{text}\n"


@dataclass
class AnnotationToolConfig(ConfigDataModel):
    max_workers: int = 8
    output_dir_name: str = "annotation_results"
    go_db_path: str = "go.obo"
    go_slim_db_path: str = "goslim_generic.obo"
    database_root_dir: str = "annotation_databases"
    database_files: Dict[str, str] = field(
        default_factory=lambda: {"go": "AD1_HAU_v1.0_genes2Go.xlsx.gz", "ipr": "AD1_HAU_v1.0_genes2IPR.xlsx.gz",
                                 "kegg_orthologs": "AD1_HAU_v1.0_KEGG-orthologs.xlsx.gz",
                                 "kegg_pathways": "AD1_HAU_v1.0_KEGG-pathways.xlsx.gz"})
    database_columns: Dict[str, str] = field(
        default_factory=lambda: {"query": "Query", "match": "Match", "description": "Description"})


@dataclass
class BSAAnalyzerConfig(ConfigDataModel):
    max_workers: int = 8
    output_dir_name: str = "bsa_analysis_results"
    window_size: int = 1000000
    step_size: int = 100000
    min_depth: int = 5
    min_snp_ratio: float = 0.8


@dataclass
class ArabidopsisAnalyzerConfig(ConfigDataModel):
    output_dir_name: str = "arabidopsis_homology_results"
    id_column_name: str = "Gene ID"


@dataclass
class BatchAIProcessorConfig(ConfigDataModel):
    temperature: float = 0.7
    max_tokens: int = 4096
    max_workers: int = 4
    max_retries: int = 3
    output_dir_name: str = "ai_processed_results"
    prompt_template_file: str = "prompt_template.txt"


@dataclass
class HomologySelectionCriteria(ConfigDataModel):
    sort_by: List[str] = field(default_factory=lambda: ["Score", "Exp"])
    ascending: List[bool] = field(default_factory=lambda: [False, True])
    top_n: int = 1
    evalue_threshold: float = 1.0e-10
    pid_threshold: float = 30.0
    score_threshold: float = 50.0


@dataclass
class IntegrationPipelineConfig(ConfigDataModel):
    input_excel_path: str = "path/to/your/input_data.xlsx"
    bsa_sheet_name: str = "BSA_Results"
    hvg_sheet_name: str = "HVG_List"
    output_sheet_name: str = "Combined_BSA_HVG_Analysis"
    bsa_assembly_id: str = "NBI_v1.1"
    hvg_assembly_id: str = "HAU_v2.0"
    bridge_species_name: str = "Arabidopsis_thaliana"
    gff_db_storage_dir: str = "gff_databases_cache"
    force_gff_db_creation: bool = False
    gff_files: Dict[str, Optional[str]] = field(default_factory=dict)
    homology_files: Dict[str, Optional[str]] = field(default_factory=dict)
    bsa_columns: Dict[str, str] = field(
        default_factory=lambda: {"chr": "chr", "start": "region.start", "end": "region.end"})
    hvg_columns: Dict[str, str] = field(
        default_factory=lambda: {"gene_id": "gene_id", "category": "hvg_category", "log2fc": "log2fc_WT_vs_Ms1"})
    homology_columns: Dict[str, str] = field(
        default_factory=lambda: {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"})
    selection_criteria_source_to_bridge: HomologySelectionCriteria = field(default_factory=HomologySelectionCriteria)
    selection_criteria_bridge_to_target: HomologySelectionCriteria = field(
        default_factory=lambda: HomologySelectionCriteria(evalue_threshold=1.0e-15, pid_threshold=40.0,
                                                          score_threshold=80.0))
    common_hvg_log2fc_threshold: float = 1.0


@dataclass
class MainConfig(ConfigDataModel):
    config_version: int = 1
    i18n_language: str = "zh-hans"
    downloader: DownloaderConfig = field(default_factory=DownloaderConfig)
    ai_services: AIServicesConfig = field(default_factory=AIServicesConfig)
    ai_prompts: AIPromptsConfig = field(default_factory=AIPromptsConfig)
    annotation_tool: AnnotationToolConfig = field(default_factory=AnnotationToolConfig)
    bsa_analyzer: BSAAnalyzerConfig = field(default_factory=BSAAnalyzerConfig)
    arabidopsis_analyzer: ArabidopsisAnalyzerConfig = field(default_factory=ArabidopsisAnalyzerConfig)
    batch_ai_processor: BatchAIProcessorConfig = field(default_factory=BatchAIProcessorConfig)
    integration_pipeline: IntegrationPipelineConfig = field(default_factory=IntegrationPipelineConfig)
    locus_conversion: LocusConversionConfig = field(default_factory=LocusConversionConfig)
    _config_file_abs_path_: Optional[str] = field(default=None, repr=False, compare=False)

    # Ensure to_dict is also handled by ConfigDataModel, or specifically override for cleaning
    def to_dict(self):
        # Use ConfigDataModel's to_dict to get the base dict
        data = super().to_dict()

        # Custom cleaning logic for MainConfig
        def _clean_dict_recursively(d: dict):
            if not isinstance(d, dict):
                return d
            cleaned_d = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    cleaned_v = _clean_dict_recursively(v)
                    if cleaned_v:  # Only keep if nested dict is not empty after cleaning
                        cleaned_d[k] = cleaned_v
                elif isinstance(v, list):
                    cleaned_list = [_clean_dict_recursively(item) if isinstance(item, dict) else item for item in v]
                    if cleaned_list:
                        cleaned_d[k] = cleaned_list
                # Remove None, empty strings, and default API key placeholders
                elif v is not None and v != "" and v not in ("YOUR_API_KEY_HERE", "YOUR_GOOGLE_API_KEY", \
                                                             "YOUR_OPENAI_API_KEY", "YOUR_DEEPSEEK_API_KEY",
                                                             "YOUR_QWEN_API_KEY", \
                                                             "YOUR_SILICONFLOW_API_KEY", "YOUR_GROK_API_KEY",
                                                             "YOUR_CUSTOM_API_KEY"):
                    cleaned_d[k] = v
            return cleaned_d

        cleaned_data = _clean_dict_recursively(data)

        # Ensure specific empty dicts are kept if they should represent a section
        if 'ai_services' in cleaned_data and 'providers' not in cleaned_data['ai_services']:
            cleaned_data['ai_services']['providers'] = {}

        return cleaned_data


# --- GenomeSourceItem 和 GenomeSourcesConfig (也继承 ConfigDataModel) ---
@dataclass
class GenomeSourceItem(ConfigDataModel):
    species_name: str
    gff3_url: str
    GO_url: str
    IPR_url: str
    KEGG_pathways_url: str
    KEGG_orthologs_url: str
    homology_ath_url: str
    homology_type: str
    homology_id_slicer: Optional[str] = None


@dataclass
class GenomeSourcesConfig(ConfigDataModel):
    list_version: int = 1
    genome_sources: Dict[str, GenomeSourceItem] = field(default_factory=lambda: {
        "NBI_v1.1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2GO.txt.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2IPR.txt.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.pathways.txt.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.orthologs.txt.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        ),
        "JGI_v1.1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX-JGI-Interim-release_v1.1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/genes/Tx-JGI_G.hirsutum_v1.1.gene_exons.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2GO.txt.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2IPR.txt.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-pathways.txt.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-orthologs.txt.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_Tx-JGI_v1.1_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        ),
        "HAU_v1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome HAU_v1 / v1.1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/genes/Ghirsutum_gene_model.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/homology/blastp_AD1_HAU_v1.0_vs_arabidopsis.xlsx.gz",
            homology_type="tair10",
            homology_id_slicer="_"
        ),
        "ZJU_v2.1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome ZJU-improved_v2.1_a1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/genes/TM-1_V2.1.gene.gff.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/homology/blastp_G.hirsutum_ZJU-AD1_v2.1_vs_arabidopsis.xlsx.gz",
            homology_type="tair10",
            homology_id_slicer="_"
        ),
        "CRI_v1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome CRI_v1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/genes/TM_1.Chr_genome_all_transcripts_final_gene.change.gff.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/homology/blastp_G.hirsutum_CRI_TM1-v1.0_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        ),
        "WHU_v1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome WHU_v1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/homology/blastp_G.hirsutum_WHU_v1_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        ),
        "UTX_v2.1": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        ),
        "HAU_v2.0": GenomeSourceItem(
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0",
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz",
            GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2Go.xlsx.gz",
            IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2IPR.xlsx.gz",
            KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_KEGG-pathways.xlsx.gz",
            KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome/functional/AD1_HAU_v2_KEGG-orthologs.xlsx.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz",
            homology_type="Araport11",
            homology_id_slicer="_"
        )
    })