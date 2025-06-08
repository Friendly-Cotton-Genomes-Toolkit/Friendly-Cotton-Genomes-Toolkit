# cotton_toolkit/config/models.py
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Dict, Any, Optional, List

# --------------------------------------------------------------------------
# 父类和基础数据单元
# --------------------------------------------------------------------------
class ConfigDataModel:
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
class HomologySelectionCriteria(ConfigDataModel):
    sort_by: List[str] = field(default_factory=lambda: ["Score", "Exp"])
    ascending: List[bool] = field(default_factory=lambda: [False, True])
    top_n: int = 1
    evalue_threshold: float = 1.0e-10
    pid_threshold: float = 30.0
    score_threshold: float = 50.0

# --------------------------------------------------------------------------
# 各主要配置区的数据模型
# --------------------------------------------------------------------------
@dataclass
class DownloaderConfig(ConfigDataModel):
    genome_sources_file: str = "genome_sources_list.yml"
    download_output_base_dir: str = "downloaded_cotton_data"
    force_download: bool = False
    max_workers: int = 3
    proxies: ProxyConfig = field(default_factory=ProxyConfig)

@dataclass
class AIServicesConfig(ConfigDataModel):
    default_provider: str = "google"
    providers: Dict[str, ProviderConfig] = field(default_factory=lambda: {
        "google": ProviderConfig(model="models/gemini-1.5-flash-latest", api_key="YOUR_GOOGLE_API_KEY", base_url="https://generativelanguage.googleapis.com/v1beta"),
        "openai": ProviderConfig(model="gpt-4o-mini", api_key="YOUR_OPENAI_API_KEY", base_url="https://api.openai.com/v1"),
        "deepseek": ProviderConfig(model="deepseek-chat", api_key="YOUR_DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1"),
        "qwen": ProviderConfig(model="qwen-turbo", api_key="YOUR_QWEN_API_KEY", base_url="https://dashscope.aliyuncs.com/api/v1"),
        "siliconflow": ProviderConfig(model="alibaba/Qwen2-7B-Instruct", api_key="YOUR_SILICONFLOW_API_KEY", base_url="https://api.siliconflow.cn/v1"),
        "openai_compatible": ProviderConfig(base_url="http://localhost:8000/v1", api_key="YOUR_CUSTOM_API_KEY", model="custom-model")
    })

@dataclass
class AIPromptsConfig(ConfigDataModel):
    translation_prompt: str = "请将以下生物学领域的文本翻译成中文：\\n\\n---\\n{text}\\n---\\n\\n请只返回翻译结果，不要包含任何额外的解释或说明。"
    analysis_prompt: str = "我正在研究植物雄性不育，请分析以下基因功能描述与我的研究方向有何关联，并提供一个简洁的总结。基因功能描述：\\n\\n---\\n{text}\\n---"

@dataclass
class AnnotationToolConfig(ConfigDataModel):
    database_root_dir: str = "annotation_databases"
    database_files: Dict[str, str] = field(default_factory=lambda: {"go": "AD1_HAU_v1.0_genes2Go.csv", "ipr": "AD1_HAU_v1.0_genes2IPR.csv", "kegg_orthologs": "AD1_HAU_v1.0_KEGG-orthologs.csv", "kegg_pathways": "AD1_HAU_v1.0_KEGG-pathways.csv"})
    database_columns: Dict[str, str] = field(default_factory=lambda: {"query": "Query", "match": "Match", "description": "Description"})

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
    gff_files: Dict[str, Optional[str]] = field(default_factory=lambda: {"NBI_v1.1": None, "HAU_v2.0": None})
    homology_files: Dict[str, Optional[str]] = field(default_factory=lambda: {"bsa_to_bridge_csv": None, "bridge_to_hvg_csv": None})
    bsa_columns: Dict[str, str] = field(default_factory=lambda: {"chr": "chr", "start": "region.start", "end": "region.end"})
    hvg_columns: Dict[str, str] = field(default_factory=lambda: {"gene_id": "gene_id", "category": "hvg_category", "log2fc": "log2fc_WT_vs_Ms1"})
    homology_columns: Dict[str, str] = field(default_factory=lambda: {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score", "pid": "PID"})
    selection_criteria_source_to_bridge: HomologySelectionCriteria = field(default_factory=HomologySelectionCriteria)
    selection_criteria_bridge_to_target: HomologySelectionCriteria = field(default_factory=lambda: HomologySelectionCriteria(evalue_threshold=1.0e-15, pid_threshold=40.0, score_threshold=80.0))
    common_hvg_log2fc_threshold: float = 1.0


@dataclass
class MainConfig(ConfigDataModel):
    config_version: int = 1
    i18n_language: str = "zh-hans"
    downloader: DownloaderConfig = field(default_factory=DownloaderConfig)
    ai_services: AIServicesConfig = field(default_factory=AIServicesConfig)
    ai_prompts: AIPromptsConfig = field(default_factory=AIPromptsConfig)
    annotation_tool: AnnotationToolConfig = field(default_factory=AnnotationToolConfig)
    integration_pipeline: IntegrationPipelineConfig = field(default_factory=IntegrationPipelineConfig)
    _config_file_abs_path_: Optional[str] = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MainConfig':
        # ... (from_dict 方法的实现，确保它能处理 i18n_language 字段) ...
        # 通常，如果 i18n_language 是一个简单类型，data.get('i18n_language') 就能正确处理。

        # 确保 i18n_language 被正确传递，如果 from_dict 是手动构造的
        # 如果是 MainConfig(**data) 这种方式，默认也会包含
        # 如果是像 from_dict 中那样分步构造，需要确保这一步：
        # i18n_language=data.get('i18n_language'),
        # ...

        # 对于 MainConfig 的 from_dict，确保 i18n_language 被正确处理
        # 完整的 from_dict 应该像这样：
        downloader_data = data.get('downloader', {})
        proxies_data = downloader_data.get('proxies', {})
        downloader_obj = DownloaderConfig(
            genome_sources_file=downloader_data.get('genome_sources_file'),
            download_output_base_dir=downloader_data.get('download_output_base_dir'),
            force_download=downloader_data.get('force_download'),
            max_workers=downloader_data.get('max_workers'),
            proxies=ProxyConfig(**proxies_data) if proxies_data else ProxyConfig()
        )

        ai_services_data = data.get('ai_services', {})
        providers_data = ai_services_data.get('providers', {})
        providers_obj = {k: ProviderConfig(**v) for k, v in providers_data.items()} if providers_data else {}
        ai_services_obj = AIServicesConfig(
            default_provider=ai_services_data.get('default_provider'),
            providers=providers_obj
        )

        ai_prompts_obj = AIPromptsConfig(**data.get('ai_prompts', {}))
        annotation_tool_obj = AnnotationToolConfig(**data.get('annotation_tool', {}))

        pipeline_data = data.get('integration_pipeline', {})
        s_to_b_data = pipeline_data.get('selection_criteria_source_to_bridge', {})
        b_to_t_data = pipeline_data.get('selection_criteria_bridge_to_target', {})
        pipeline_kwargs = {k: v for k, v in pipeline_data.items() if
                           k not in ['selection_criteria_source_to_bridge', 'selection_criteria_bridge_to_target']}
        pipeline_obj = IntegrationPipelineConfig(
            **pipeline_kwargs,
            selection_criteria_source_to_bridge=HomologySelectionCriteria(**s_to_b_data),
            selection_criteria_bridge_to_target=HomologySelectionCriteria(**b_to_t_data)
        )

        return cls(
            config_version=data.get('config_version'),
            i18n_language=data.get('i18n_language'),  # **确保这里也传递 i18n_language**
            downloader=downloader_obj,
            ai_services=ai_services_obj,
            ai_prompts=ai_prompts_obj,
            annotation_tool=annotation_tool_obj,
            integration_pipeline=pipeline_obj
        )

# --- 为基因组源列表提供实用的默认值 ---
@dataclass
class GenomeSourceItem(ConfigDataModel):
    gff3_url: str
    homology_ath_url: str
    species_name: str
    homology_id_slicer: Optional[str] = None

@dataclass
class GenomeSourcesConfig(ConfigDataModel):
    list_version: int = 1
    genome_sources: Dict[str, GenomeSourceItem] = field(default_factory=lambda: {
        "NBI_v1.1": GenomeSourceItem(
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz",
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1",
            homology_id_slicer="_"
        ),
        "HAU_v2.0": GenomeSourceItem(
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz",
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0",
            homology_id_slicer="_"
        ),
        "UTX_v2.1": GenomeSourceItem(
            gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz",
            homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz",
            species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1",
            homology_id_slicer="_"
        )
    })

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GenomeSourcesConfig':
        gs_data = data.get('genome_sources', {})
        # 确保从字典加载时，值也能被正确转换为GenomeSourceItem对象
        processed_gs = {k: (v if isinstance(v, GenomeSourceItem) else GenomeSourceItem(**v)) for k, v in gs_data.items()}
        return cls(list_version=data.get('list_version', 1), genome_sources=processed_gs)