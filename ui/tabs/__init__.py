# 文件路径: D:\Python\cotton_tool\ui\tabs\__init__.py

from .ai_assistant_tab import AIAssistantTab
from .annotation_tab import AnnotationTab
from .base_tab import BaseTab
from .data_download_tab import DataDownloadTab
from .enrichment_tab import EnrichmentTab
from .genome_identifier_tab import GenomeIdentifierTab
from .gff_query_tab import GFFQueryTab
from .homology_tab import HomologyTab
from .locus_conversion_tab import LocusConversionTab
from .blast_tab import BlastTab
from .sequence_extraction_tab import SequenceExtractionTab
from .arabidopsis_homology_tab import ArabidopsisHomologyConversionTab
from .sequence_analysis_tab import SeqAnalysisTab
from .quantification_tab import QuantificationTab
from .phylogenetics_tab import PhylogeneticsTab
from .online_tools_tab import OnlineToolsTab

# 定义此包的公共API，当使用 from ui.tabs import * 时会导入这些
__all__ = [
    "AIAssistantTab",
    "AnnotationTab",
    "BaseTab",
    "DataDownloadTab",
    "EnrichmentTab",
    "GenomeIdentifierTab",
    "GFFQueryTab",
    "HomologyTab",
    "LocusConversionTab",
    "BlastTab",
    "SequenceExtractionTab",
    "ArabidopsisHomologyConversionTab",
    "SeqAnalysisTab",
    "QuantificationTab",
    "PhylogeneticsTab",
    "OnlineToolsTab"
]