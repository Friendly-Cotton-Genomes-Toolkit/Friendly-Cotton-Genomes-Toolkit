from os import  path

PUBLISH_URL = 'https://github.com/Friendly-Cotton-Genomes-Toolkit/Friendly-Cotton-Genomes-Toolkit'
HELP_URL = 'https://github.com/Friendly-Cotton-Genomes-Toolkit/Friendly-Cotton-Genomes-Toolkit/blob/master/docs/HELP.md'
VERSION = '1.1.4'

GENOME_SOURCE_FILE: str = "genome_sources_list.yml"
DOWNLOAD_OUTPUT_BASE_DIR: str = "genomes"
PREPROCESSED_DB_NAME = path.join(DOWNLOAD_OUTPUT_BASE_DIR,"genomes.db")
GFF3_DB_DIR = path.join(DOWNLOAD_OUTPUT_BASE_DIR, 'gff3')
