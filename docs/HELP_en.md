[中文（简体）](HELP.md) | [English](HELP_en.md) | [日本語](HELP_ja.md) | [繁體中文](HELP_zh-hant.md)

---

# Friendly Cotton Genomes Toolkit - Help Manual

This page provides a detailed guide on data preparation and configuration file settings required to use the toolkit.

## Table of Contents

- [1. Core Features](https://www.google.com/search?q=%231-core-features)
  - [1.1. Integration Analysis (Screening HVGs with BSA Regions)](https://www.google.com/search?q=%2311-integration-analysis-screening-hvgs-with-bsa-regions)
  - [1.2. Genome Conversion (Standalone Homology Mapping)](https://www.google.com/search?q=%2312-genome-conversion-standalone-homology-mapping)
  - [1.3. Gene Locus Lookup (GFF Query)](https://www.google.com/search?q=%2313-gene-locus-lookup-gff-query)
- [2. Data Preparation Guide](https://www.google.com/search?q=%232-data-preparation-guide)
  - [2.1. BSA Locus Region Table](https://www.google.com/search?q=%2321-bsa-locus-region-table)
  - [2.2. Highly Variable Genes (HVG) Data Table](https://www.google.com/search?q=%2322-highly-variable-genes-hvg-data-table)
- [3. Configuration File Guide](https://www.google.com/search?q=%233-configuration-file-guide)
  - [3.1. Main Configuration File (`config.yml`)](https://www.google.com/search?q=%2331-main-configuration-file-configyml)
  - [3.2. Genome Sources File (`genome_sources_list.yml`)](https://www.google.com/search?q=%2332-genome-sources-file-genome_sources_listyml)

------

## 1. Core Features

This toolkit offers three main core features, which you can access through different tabs in the GUI or by using different sub-commands in the CLI.

### 1.1. Integration Analysis (Screening HVGs with BSA Regions)

This is the core feature of the toolkit, designed to **use genomic regions identified by BSA to filter your list of Highly Variable Genes (HVGs)**. This significantly narrows down the pool of candidate genes and supports subsequent fine-mapping efforts.

**Workflow:**

1. **Input BSA Regions**: In the "BSA Sheet" of your Excel file, you need to provide the genomic **regions** associated with your target trait, which must include the `chr`, `region.start`, and `region.end` columns.
2. **Find All Genes in Regions**: Based on the genome version you specify in the configuration file (`bsa_assembly_id`), the tool will read the corresponding GFF annotation file and identify all genes located within the BSA regions.
3. **Intersect with HVG List**: The tool then reads the gene list you provide in the "HVG Sheet".
4. **Cross-Version Conversion (If Needed)**: If your BSA and HVG data are based on **different** genome versions, the tool will automatically perform "Genome Conversion" (homology mapping). It will convert the gene IDs found in Step 2 to their corresponding IDs on the HVG genome version before intersecting with your HVG list.
5. **Output Results**: Finally, a high-priority list of candidate genes—which are both located in the key mapping interval and are highly variable—will be written to a new sheet in your input Excel file.

### 1.2. Genome Conversion (Standalone Homology Mapping)

This feature allows you to independently convert a list of gene IDs from one genome version to homologous gene IDs in another version. This is very useful for a "Liftover" of gene lists between different genome assembly annotations.

- **Input**: A list of source gene IDs, a source genome version, a target genome version, and two homology relationship files (source -> bridge species, bridge species -> target).
- **Output**: A CSV file containing the source genes, bridge genes, successfully mapped target genes, and their relevant alignment scores.

### 1.3. Gene Locus Lookup (GFF Query)

This feature allows you to quickly extract detailed gene information from a GFF annotation file based on gene IDs or a genomic region.

- **Input**: A genome version ID, one or more gene IDs (comma-separated) **OR** a genomic region (e.g., `Scaffold_A1:1000-5000`).
- **Output**: A CSV file containing detailed information for the queried genes (such as locus, strand, transcripts, exon and CDS coordinates, etc.).

------

## 2. Data Preparation Guide

To ensure the analysis pipelines run smoothly, please prepare your input Excel file according to the following instructions.

### 2.1. BSA Locus Region Table

This table contains the candidate **regions** you have identified through BSA (Bulked Segregant Analysis).

- **Sheet Name**: The name of the sheet containing this table must match the value of `integration_pipeline.bsa_sheet_name` in your `config.yml` file (default: `BSA_Results`).
- **Required Columns**: The table must contain the following three columns, and their names must exactly match the `bsa_columns` configuration in `config.yml`.

| **Column Name (Default)** | **Type** | **Description**                                              | **Example** |
| ------------------------- | -------- | ------------------------------------------------------------ | ----------- |
| `chr`                     | Text     | The ID of the chromosome or scaffold. Must match the ID in the GFF file. | `Ghir_A03`  |
| `region.start`            | Integer  | The starting position of the candidate region (1-based).     | `10050`     |
| `region.end`              | Integer  | The ending position of the candidate region (1-based).       | `250000`    |

#### Example Table (`BSA_Results` Sheet):

```
chr				region.start   region.end   some_other_info
Ghir_A03	    10050          25000        0.98
Ghir_D04	    550000         780000       0.95
...          	...            ...          ...
```

------

### 2.2. Highly Variable Genes (HVG) Data Table

This table contains information on the Highly Variable Genes you have screened.

- **Sheet Name**: The name of the sheet containing this table must match the value of `integration_pipeline.hvg_sheet_name` in `config.yml` (default: `HVG_List`).
- **Required Columns**: The table must contain the following three columns, and their names must exactly match the `hvg_columns` configuration in `config.yml`.

| **Column Name (Default)** | **Type** | **Description**                                              | **Example**       |
| ------------------------- | -------- | ------------------------------------------------------------ | ----------------- |
| `gene_id`                 | Text     | The gene ID. Must match the gene IDs from the GFF file of the genome version the HVG data is based on. | `Ghir_A01G000100` |
| `hvg_category`            | Text     | The HVG category. Must be one of three values: "WT特有TopHVG", "Ms1特有TopHVG", "共同TopHVG". | `WT特有TopHVG`    |
| `log2fc_WT_vs_Ms1`        | Number   | The Log2 Fold Change (WT vs Ms1) value.                      | `2.58`            |

#### Example Table (`HVG_List` Sheet):

```
gene_id          hvg_category   log2fc_WT_vs_Ms1   p_value
Ghir_A01G000100  WT特有TopHVG   2.58               0.001
Ghir_A01G000200  共同TopHVG     -1.75              0.025
...              ...            ...                ...
```

------

## 3. Configuration File Guide

The toolkit's behavior is driven by two core YAML (`.yml`) configuration files. You can modify them in the "Configuration Editor" tab of the GUI.

### 3.1. Main Configuration File (`config.yml`)

This file is the control center for all operations.

#### General Settings

| **Parameter**   | **Description**                                              | **Example** |
| --------------- | ------------------------------------------------------------ | ----------- |
| `i18n_language` | Sets the interface language. Options include: `zh-hans`, `zh-hant`, `en`, etc. | `en`        |

#### Downloader Configuration (`downloader`)

This section controls the behavior of the data download feature.

| **Parameter**              | **Description**                                              | **Example**                      |
| -------------------------- | ------------------------------------------------------------ | -------------------------------- |
| `genome_sources_file`      | Points to the `genome_sources_list.yml` file, which contains genome download links. Can be a relative or absolute path. | `genome_sources_list.yml`        |
| `download_output_base_dir` | The base directory where all downloaded files will be stored. | `downloaded_cotton_data`         |
| `force_download`           | Whether to force re-downloading of existing files. `true` for yes, `false` for no. | `false`                          |
| `max_workers`              | The maximum number of threads to use for multi-threaded downloads. | `3`                              |
| `proxies`                  | Sets network proxies. If not needed, set both `http` and `https` to `null`. | `http: "http://your-proxy:port"` |

#### Integration Pipeline Configuration (`integration_pipeline`)

This section defines most of the parameters needed for the **Integration Analysis** and the **standalone feature modules**.

| **Parameter**                 | **Description**                                              | **Example**                                        |
| ----------------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `input_excel_path`            | 【Integration Analysis】Path to the input Excel file containing BSA and HVG data. | `data/my_analysis.xlsx`                            |
| `bsa_sheet_name`              | 【Integration Analysis】Name of the sheet containing BSA data in the input Excel. | `BSA_Results`                                      |
| `hvg_sheet_name`              | 【Integration Analysis】Name of the sheet containing HVG data in the input Excel. | `HVG_List`                                         |
| `output_sheet_name`           | 【Integration Analysis】The name for the new sheet where analysis results will be written in the input Excel. | `Combined_BSA_HVG_Analysis`                        |
| `bsa_assembly_id`             | The genome version ID on which your BSA data is based. This ID must match an ID in `genome_sources_list.yml`. | `NBI_v1.1`                                         |
| `hvg_assembly_id`             | The genome version ID on which your HVG data is based. If identical to `bsa_assembly_id`, homology mapping will be skipped. | `HAU_v2.0`                                         |
| `gff_files`                   | (Optional) Manually specify paths to GFF files. If set to `null`, the program will infer paths from the download directory and version ID. | `NBI_v1.1: local/NBI.gff3.gz`                      |
| `homology_files`              | (Optional) Manually specify paths to homology relationship CSV files. Required when BSA and HVG versions differ. | `bsa_to_bridge_csv: local/NBI_to_At.csv`           |
| `bridge_species_name`         | The name of the bridge species used for cross-version homology mapping. | `Arabidopsis_thaliana`                             |
| `gff_db_storage_dir`          | The cache directory for gffutils databases.                  | `gff_databases_cache`                              |
| `force_gff_db_creation`       | Whether to force recreation of GFF databases, even if a cache already exists. | `false`                                            |
| `bsa_columns`                 | Defines the column names for chromosome, start, and end positions in the BSA sheet. | `{chr: chr, start: region.start, end: region.end}` |
| `hvg_columns`                 | Defines the column names for gene ID, category, and Log2FC values in the HVG sheet. | `{gene_id: gene_id, category: hvg_category, ...}`  |
| `homology_columns`            | Defines the column names in the homology relationship CSV files. | `{query: Query, match: Match, evalue: Exp, ...}`   |
| `selection_criteria_...`      | Defines the detailed criteria for selecting the best matches in homology mapping (E-value, PID, Score thresholds, etc.). | `{top_n: 1, evalue_threshold: 1.0e-10, ...}`       |
| `common_hvg_log2fc_threshold` | The absolute Log2FC threshold for determining if expression differences are significant for genes in the "共同TopHVG" (Common TopHVG) category. | `1.0`                                              |

------

> ### **💡 Important Note: About Fuzzy Gene ID Matching**
>
> In the "Integration Analysis" and "Genome Conversion" workflows, the program automatically enables a **fuzzy matching** mechanism when searching for your provided gene IDs in the homology database.
>
> - **How it works**: If the gene ID you provide (e.g., `Ghir.A01G000300`) is not found as an exact match in the homology file, the program will automatically try to find all genes that start with this ID as a **prefix** (e.g., `Ghir.A01G000300.1`, `Ghir.A01G000300.2`, etc.).
>
> - How it's reflected in the results
>
>   :
>
>   - When a fuzzy match occurs, a warning message will be displayed in the **logs of the GUI and CLI**, notifying you that this type of match has happened.
>   - In the final output Excel or CSV file, there will be a column named **`Match_Note`**. For entries found via fuzzy matching, this column will be explicitly marked with **"Fuzzy Match on 'Original_ID'"** and related information, allowing you to trace and verify the results.
>
> This feature is designed to increase the success rate of matching, ensuring you don't miss important homologous relationships due to minor differences in gene ID suffixes (like transcript numbers).

------

### 3.2. Genome Sources File (`genome_sources_list.yml`)

This file is a catalog that defines the data download links for each cotton genome version.

- **Top-level key**: `genome_sources`.
- **Sub-keys**: Each sub-key is a unique **genome version ID** that you define (e.g., `NBI_v1.1`). This ID will be referenced in the `bsa_assembly_id` and `hvg_assembly_id` parameters of the main configuration file.

Each genome version ID contains the following parameters:

| **Parameter**        | **Description**                                              | **Example**                                             |
| -------------------- | ------------------------------------------------------------ | ------------------------------------------------------- |
| `gff3_url`           | The download link for the GFF3 annotation file of this genome version. | `"https://.../NBI_v1.1.gene.gff3.gz"`                   |
| `homology_ath_url`   | The download link for the homology relationship file between this version and Arabidopsis (or another bridge species). This is typically a BLAST result. | `"https://.../blastx_..._vs_arabidopsis.xlsx.gz"`       |
| `species_name`       | A detailed name for the species and version, mainly used to create easily identifiable download directory names. | `"Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"` |
| `homology_id_slicer` | (Optional) A delimiter used to trim gene IDs in the homology file. For example, if the ID is `gene.1_other` and the slicer is set to `_`, the program will use `gene.1` for matching. Set to `null` if no trimming is needed. | `_`                                                     |

#### Example File (`genome_sources_list.yml`):

YAML

```
genome_sources:
  NBI_v1.1:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/genes/NBI_Gossypium_hirsutum_v1.1.gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/NAU-NBI_G.hirsutum_AD1genome/protein_homology_2019/blastx_G.hirsutum_NAU-NBI_v1.1_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"
    homology_id_slicer: "_"
  
  HAU_v2.0:
    gff3_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/genes/TM-1_HAU_v2_gene.gff3.gz"
    homology_ath_url: "https://www.cottongen.org/cottongen_downloads/Gossypium_hirsutum/HAU-TM1_AD1genome_v2.0/homology/blastp_AD1_HAU_v2.0_vs_arabidopsis.xlsx.gz"
    species_name: "Gossypium hirsutum (AD1) 'TM-1' genome HAU_v2.0"
    homology_id_slicer: "_"
```