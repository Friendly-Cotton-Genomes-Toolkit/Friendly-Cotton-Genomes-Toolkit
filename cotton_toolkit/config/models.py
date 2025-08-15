# cotton_toolkit/config/models.py

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from gettext import gettext as _

# --- 配置子模型 (所有都继承 BaseModel) ---

class ProxyConfig(BaseModel):
    http: Optional[str] = None
    https: Optional[str] = None

class ProviderConfig(BaseModel):
    api_key: str = "YOUR_API_KEY_HERE"
    model: str = "default-model"
    base_url: Optional[str] = None
    available_models: Optional[str] = None


class DownloaderConfig(BaseModel):
    max_workers: int = 8
    genome_sources_file: str = "genome_sources_list.yml"
    download_output_base_dir: str = "genomes"
    force_download :bool = False
    use_proxy_for_download :bool = False

class LocusConversionConfig(BaseModel):
    output_dir_name: str = "locus_conversion_results"
    gff_db_storage_dir: str = "gff_databases_cache"


class AIServicesConfig(BaseModel):
    default_provider: str = "google"
    use_proxy_for_ai: bool = False
    providers: Dict[str, ProviderConfig] = Field(default_factory=lambda: AIServicesConfig._default_providers())

    @staticmethod
    def _default_providers() -> Dict[str, ProviderConfig]:
        return {
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
        }

class AIPromptsConfig(BaseModel):
    translation_prompt: str = \
        """
        Please translate the following biology-related text into Chinese:

        {text}

        Please only return the translation result without any additional explanations or notes.
        """

    analysis_prompt: str = \
        """
        I am studying a topic in the field of biology. 

        Please analyze how the following gene function description relates to my research direction and provide a concise summary. 

        target description:

        {text}
        """
    custom_prompt: str = ""

class AnnotationToolConfig(BaseModel):
    max_workers: int = 8
    output_dir_name: str = "annotation_results"
    go_db_path: str = "go.obo"
    go_slim_db_path: str = "goslim_generic.obo"
    database_root_dir: str = "annotation_databases"
    database_files: Dict[str, str] = Field(default_factory=lambda: AnnotationToolConfig._default_database_files())
    database_columns: Dict[str, str] = Field(default_factory=lambda: AnnotationToolConfig._default_database_columns())

    @staticmethod
    def _default_database_files() -> Dict[str, str]:
        return {"go": "AD1_HAU_v1.0_genes2Go.xlsx.gz", "ipr": "AD1_HAU_v1.0_genes2IPR.xlsx.gz",
                "kegg_orthologs": "AD1_HAU_v1.0_KEGG-orthologs.xlsx.gz",
                "kegg_pathways": "AD1_HAU_v1.0_KEGG-pathways.xlsx.gz"}

    @staticmethod
    def _default_database_columns() -> Dict[str, str]:
        return {"query": "Query", "match": "Match", "description": "Description"}


class ArabidopsisAnalyzerConfig(BaseModel):
    output_dir_name: str = "arabidopsis_homology_results"
    id_column_name: str = "Gene ID"

class BatchAIProcessorConfig(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 4096
    max_workers: int = 4
    max_retries: int = 3
    output_dir_name: str = "ai_processed_results"
    prompt_template_file: str = "prompt_template.txt"

class HomologySelectionCriteria(BaseModel):
    sort_by: List[str] = Field(default_factory=lambda: HomologySelectionCriteria._default_sort_by())
    ascending: List[bool] = Field(default_factory=lambda: HomologySelectionCriteria._default_ascending())
    top_n: int = 1
    evalue_threshold: float = 1.0e-10
    pid_threshold: float = 30.0
    score_threshold: float = 50.0
    prioritize_subgenome: bool = True
    strict_subgenome_priority: bool = True

    @staticmethod
    def _default_sort_by() -> List[str]:
        return ["Score", "Exp"]

    @staticmethod
    def _default_ascending() -> List[bool]:
        return [False, True]


class MainConfig(BaseModel):
    config_version: int = 2
    log_level: str = "INFO"
    i18n_language: str = "en"
    proxies: ProxyConfig = Field(default_factory=ProxyConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    ai_services: AIServicesConfig = Field(default_factory=AIServicesConfig)
    ai_prompts: AIPromptsConfig = Field(default_factory=AIPromptsConfig)
    annotation_tool: AnnotationToolConfig = Field(default_factory=AnnotationToolConfig)
    arabidopsis_analyzer: ArabidopsisAnalyzerConfig = Field(default_factory=ArabidopsisAnalyzerConfig)
    batch_ai_processor: BatchAIProcessorConfig = Field(default_factory=BatchAIProcessorConfig)
    locus_conversion: LocusConversionConfig = Field(default_factory=LocusConversionConfig)
    config_file_abs_path_: Optional[str] = Field(default=None, exclude=True)


    def to_dict(self):
        return self.model_dump(exclude_none=True, exclude_defaults=False)

class GenomeSourceItem(BaseModel):
    species_name: str
    genome_type: str = "cotton"
    gff3_url: Optional[str] = None
    predicted_cds_url: Optional[str] = None
    predicted_protein_url: Optional[str] = None
    GO_url: Optional[str] = None
    IPR_url: Optional[str] = None
    KEGG_pathways_url: Optional[str] = None
    KEGG_orthologs_url: Optional[str] = None
    homology_ath_url: Optional[str] = None
    gene_id_regex: Optional[str] = None
    bridge_version: Optional[str] = "Araport11"
    version_id: Optional[str] = Field(default=None)


    def is_cotton(self) -> bool:
        return self.genome_type.lower() == 'cotton'

class GenomeSourcesConfig(BaseModel):
    list_version: int = 2
    genome_sources: Dict[str, GenomeSourceItem] = Field(default_factory=lambda: GenomeSourcesConfig._default_genome_sources())

    @staticmethod
    def _default_genome_sources() -> Dict[str, GenomeSourceItem]:
        return {
            "NBI_v1.1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.pep.fa.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2GO.txt.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_genes2IPR.txt.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.pathways.txt.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/functional/G.hirsutum_NBI_v1.1_KEGG.orthologs.txt.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Gh_[AD]\d{2}G\d{4})",
                bridge_version="Araport11"
            ),
            "JGI_v1.1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX-JGI-Interim-release_v1.1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/genes/Tx-JGI_G.hirsutum_v1.1.gene_exons.gff3.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/genes/Tx-JGI_G.hirsutum_v1.1.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/genes/Tx-JGI_G.hirsutum_v1.1.protein.fa.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2GO.txt.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_genes2IPR.txt.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-pathways.txt.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/functional/G.hirsutum_Tx-JGI_v1.1_KEGG-orthologs.txt.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/Tx-JGI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_Tx-JGI_v1.1_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Gohir\.[AD]\d{2}G\d{6})",
                bridge_version="Araport11"
            ),
            "HAU_v1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome HAU_v1 (v1.1)",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/genes/Ghirsutum_gene_model.gff3.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/genes/Ghirsutum_gene_CDS.fasta.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/genes/Ghirsutum_gene_peptide.fasta.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/functional/AD1_HAU_v1.0_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU_G.hirsutum_AD1genome/homology/blastp_AD1_HAU_v1.0_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Ghir_[AD]\d{2}G\d{6})",
                bridge_version="TAIR10"
            ),
            "ZJU_v2.1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome ZJU-improved_v2.1_a1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/genes/TM-1_V2.1.gene.gff.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/genes/TM-1_V2.1.gene.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/genes/TM-1_V2.1.gene.pep.fa.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/functional/AD1_ZJU_v2.1_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU_G.hirsutum_AD1genome_v2.1/homology/blastp_G.hirsutum_ZJU-AD1_v2.1_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(GH_[AD]\d{2}G\d{4})",
                bridge_version="TAIR10"
            ),
            "CRI_v1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome CRI_v1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/genes/TM_1.Chr_genome_all_transcripts_final_gene.change.gff.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/genes/TM_1.Chr_genome_all_transcripts_final_gene.change.gff.cds.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/genes/TM_1.Chr_genome_all_transcripts_final_gene.change.gff.pep.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypi_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/functional/AD1_CRI_TM1-v1.0_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/CRI-TM1_G.hirsutum_AD1genome/homology/blastp_G.hirsutum_CRI_TM1-v1.0_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Gh_[AD]\d{2}G\d{6})",
                bridge_version="Araport11"
            ),
            "WHU_v1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome WHU_v1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.gff3.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/genes/Ghirsutum_TM-1_WHU_standard.gene.pep.fa.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/functional/Gh_TM1_WHU_v1_a1_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/WHU-TM1_AD1_Updated/homology/blastp_G.hirsutum_WHU_v1_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Ghi_[AD]\d{2}G\d{5})",
                bridge_version="Araport11"
            ),
            "UTX_v2.1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX_v2.1",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.gene_exons.gff3.gz",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/genes/Ghirsutum_527_v2.1.protein.fa.gz", # <-- 已更新
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/functional/Gh_TM1_UTX_v2.1_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v2.1/homology/blastp_G.hirsutum_UTX_v2.1_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Gohir\.[AD]\d{2}G\d{6})",
                bridge_version="Araport11"
            ),
            "HAU_v2.0": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0",
                genome_type="cotton",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz",
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/functional/AD1_HAU_v2_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Ghir_[AD]\d{2}G\d{5})",
                bridge_version="Araport11"
            ),
            "AD1_T2T_JZU": GenomeSourceItem(
                species_name="AD1_T2T_JZU",
                genome_type="cotton",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/genes/GhChr.cds.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/genes/GhChr.pep.gz",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/genes/GhChr.gff3.gz",
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/functional/AD1_TM1_T2T_ZJU_v1_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/functional/AD1_TM1_T2T_ZJU_v1_genes2IPR.xlsx.gz",
                KEGG_pathways_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/functional/AD1_TM1_T2T_ZJU_v1_KEGG-pathways.xlsx.gz",
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/functional/AD1_TM1_T2T_ZJU_v1_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/ZJU-TM1_T2T/homology/blastp_AD1_TM1_T2T_ZJU_v1.0_vs_arabidopsis.xlsx",
                gene_id_regex=r"(GhChr[AD]\d{2}G\d{4})",
                bridge_version="Araport11"
            ),
            "UTX_v3.1": GenomeSourceItem(
                species_name="Gossypium hirsutum (AD1) 'TM-1' genome UTX_v3.1",
                genome_type="cotton",
                predicted_cds_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/genes/Ghirsutum_578_v3.1.cds.fa.gz",
                predicted_protein_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/genes/Ghirsutum_578_v3.1.protein.fa.gz",
                gff3_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/genes/Ghirsutum_578_v3.1.gene_exons.gff3.gz",
                GO_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/functional/AD1_UTX_v3.1_genes2Go.xlsx.gz",
                IPR_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/functional/AD1_UTX_v3.1_genes2IPR.xlsx.gz",
                KEGG_pathways_url=None,
                KEGG_orthologs_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/functional/AD1_UTX_v3.1_KEGG-orthologs.xlsx.gz",
                homology_ath_url="https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/UTX-TM1_v3.1/homology/blastp_AD1_UTX_v3.1.0_vs_arabidopsis.xlsx.gz",
                gene_id_regex=r"(Gohir\.[AD]\d{2}G\d{6})",
                bridge_version="Araport11"
            ),
            "Arabidopsis_thaliana": GenomeSourceItem(
                species_name="Arabidopsis thaliana",
                genome_type="arabidopsis",
                gene_id_regex=r"(AT[1-5MC]G\d{5})",
                bridge_version=None
            )
        }