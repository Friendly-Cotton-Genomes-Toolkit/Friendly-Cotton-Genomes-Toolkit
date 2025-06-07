[中文（简体）](HELP.md) | [English](HELP_en.md) | [日本語](HELP_ja.md) | [繁體中文](HELP_zh-hant.md)

---

# 友好棉花基因组分析工具包 （FCGT） - 帮助文档

本页提供了工具包使用所需的数据准备和配置文件设置的详细指南。

## 目录

  * [1. 核心功能](https://www.google.com/search?q=%231-%E6%A0%B8%E5%BF%83%E5%8A%9F%E8%83%BD)
      * [1.1. 整合分析 (BSA区域筛选HVG)](https://www.google.com/search?q=%2311-%E6%95%B4%E5%90%88%E5%88%86%E6%9E%90-bsa%E5%8C%BA%E5%9F%9F%E7%AD%9B%E9%80%89hvg)
      * [1.2. 基因组转换 (独立同源映射)](https://www.google.com/search?q=%2312-%E5%9F%BA%E5%9B%A0%E7%BB%84%E8%BD%AC%E6%8D%A2-%E7%8B%AC%E7%AB%8B%E5%90%8C%E6%BA%90%E6%98%A0%E5%B0%84)
      * [1.3. 基因位点查询 (GFF查询)](https://www.google.com/search?q=%2313-%E5%9F%BA%E5%9B%A0%E4%BD%8D%E7%82%B9%E6%9F%A5%E8%AF%A2-gff%E6%9F%A5%E8%AF%A2)
  * [2. 数据准备指南](https://www.google.com/search?q=%232-%E6%95%B0%E6%8D%AE%E5%87%86%E5%A4%87%E6%8C%87%E5%8D%97)
      * [2.1. BSA 定位区域表](https://www.google.com/search?q=%2321-bsa-%E5%AE%9A%E4%BD%8D%E5%8C%BA%E5%9F%9F%E8%A1%A8)
      * [2.2. 高变异基因 (HVG) 数据表](https://www.google.com/search?q=%2322-%E9%AB%98%E5%8F%98%E5%BC%82%E5%9F%BA%E5%9B%A0-hvg-%E6%95%B0%E6%8D%AE%E8%A1%A8)
  * [3. 配置文件指南](https://www.google.com/search?q=%233-%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6%E6%8C%87%E5%8D%97)
      * [3.1. 主配置文件 (`config.yml`)](https://www.google.com/search?q=%2331-%E4%B8%BB%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6-configyml)
      * [3.2. 基因组源文件 (`genome_sources_list.yml`)](https://www.google.com/search?q=%2332-%E5%9F%BA%E5%9B%A0%E7%BB%84%E6%BA%90%E6%96%87%E4%BB%B6-genome_sources_listyml)

-----

## 1\. 核心功能

本工具包主要提供三大核心功能，您可以在GUI的不同选项卡或使用CLI的不同子命令来调用它们。

### 1.1. 整合分析 (BSA区域筛选HVG)

此功能是工具包的核心，旨在**利用BSA定位到的基因组区域，来筛选您提供的高变异基因（HVG）列表**，从而大大缩小候选基因的范围，为后续的精细定位提供支持。

**工作流程:**

1.  **输入BSA区域**: 您需要在Excel的“BSA工作表”中提供与目标性状关联的基因组**区域**，必须包含 `chr`, `region.start`, `region.end` 这三列。
2.  **查找区域内所有基因**: 工具会根据您在配置文件中指定的基因组版本（`bsa_assembly_id`），读取对应的GFF注释文件，并找出所有物理位置落在这个区间内的基因。
3.  **与HVG列表取交集**: 接着，工具会读取您在“HVG工作表”中提供的基因列表。
4.  **跨版本转换 (如果需要)**: 如果您的BSA数据和HVG数据基于**不同**的基因组版本，工具会自动执行“基因组转换”（同源映射），将第2步中找到的基因ID转换为HVG基因组版本上的对应ID，然后再与您的HVG列表取交集。
5.  **输出结果**: 最终，一个既位于关键定位区间、又属于高变异基因的、高优先级的候选基因列表，将被输出到输入Excel文件的一个新工作表中。

### 1.2. 基因组转换 (独立同源映射)

此功能允许您独立地将一个基因组版本上的基因ID列表，转换为另一个版本上的同源基因ID。这对于在不同版本的基因组注释之间进行基因列表的“Liftover”非常有用。

  * **输入**: 源基因ID列表、源基因组版本、目标基因组版本、以及两个同源关系文件（源-\>桥梁物种，桥梁物种-\>目标）。
  * **输出**: 一个包含源基因、桥梁基因和成功映射的目标基因及其相关比对分数的CSV文件。

### 1.3. 基因位点查询 (GFF查询)

此功能允许您根据基因ID或基因组区域，快速地从GFF注释文件中提取详细的基因信息。

  * **输入**: 基因组版本ID、一个或多个基因ID（逗号分隔） **或** 一个基因组区域（格式如 `Scaffold_A1:1000-5000`）。
  * **输出**: 一个包含所查询基因的详细信息（如位置、链向、转录本、外显子、CDS坐标等）的CSV文件。

-----

## 2\. 数据准备指南

为了确保分析流程能够顺利运行，请根据以下说明准备您的输入Excel文件。

### 2.1. BSA 定位区域表

这是包含您通过BSA (Bulked Segregant Analysis) 方法定位到的候选**区域**的表格。

  * **Sheet 名称**: 表格所在的 Sheet 名称必须与 `config.yml` 文件中 `integration_pipeline.bsa_sheet_name` 的值一致 (默认为: `BSA_Results`)。
  * **必需列**: 表格中必须包含以下三列，且列名必须与 `config.yml` 中 `bsa_columns` 的配置完全一致。

| 列名 (默认) | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `chr` | 文本 | 染色体或支架(Scaffold)的ID。必须与GFF文件中的ID匹配。 | `Ghir_A03` |
| `region.start`| 整数 | 候选区域的起始位置（1-based）。 | `10050` |
| `region.end` | 整数 | 候选区域的结束位置（1-based）。 | `250000` |

#### 示例表格 (`BSA_Results` Sheet):

```
chr				region.start   region.end   some_other_info
Ghir_A03	    10050          25000        0.98
Ghir_D04	    550000         780000       0.95
...          	...            ...          ...
```

-----

### 2.2. 高变异基因 (HVG) 数据表

这是包含您筛选出的高变异基因 (Highly Variable Genes) 信息的表格。

  * **Sheet 名称**: 表格所在的 Sheet 名称必须与 `config.yml` 文件中 `integration_pipeline.hvg_sheet_name` 的值一致 (默认为: `HVG_List`)。
  * **必需列**: 表格中必须包含以下三列，且列名必须与 `config.yml` 中 `hvg_columns` 的配置完全一致。

| 列名 (默认) | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `gene_id` | 文本 | 基因ID。必须与HVG数据所基于的基因组版本的GFF文件中的基因ID匹配。 | `Ghir_A01G000100` |
| `hvg_category` | 文本 | HVG 分类。必须为以下三个值之一："WT特有TopHVG", "Ms1特有TopHVG", "共同TopHVG" | `WT特有TopHVG` |
| `log2fc_WT_vs_Ms1`| 数字 | Log2 Fold Change (WT vs Ms1) 的值。 | `2.58` |

#### 示例表格 (`HVG_List` Sheet):

```
gene_id          hvg_category   log2fc_WT_vs_Ms1   p_value
Ghir_A01G000100  WT特有TopHVG   2.58               0.001
Ghir_A01G000200  共同TopHVG     -1.75              0.025
...              ...            ...                ...
```

-----

## 3\. 配置文件指南

工具包的行为由两个核心的 YAML (`.yml`) 配置文件驱动。您可以在GUI的“配置编辑”选项卡中修改它们。

### 3.1. 主配置文件 (`config.yml`)

这个文件是所有操作的控制中心。

#### 通用设置

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `i18n_language` | 设置程序界面的语言。可选值:`zh-hans` `zh-hant`, `en` 等。 | `zh-hans` |

#### 下载器配置 (`downloader`)

此部分控制数据下载功能的行为。

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `genome_sources_file` | 指向包含基因组下载链接的 `genome_sources_list.yml` 文件。可以是相对路径或绝对路径。 | `genome_sources_list.yml` |
| `download_output_base_dir` | 所有下载文件存放的基础目录。 | `downloaded_cotton_data` |
| `force_download` | 是否强制重新下载已存在的文件。`true` 为是, `false` 为否。 | `false` |
| `max_workers` | 多线程下载时使用的最大线程数。 | `3` |
| `proxies` | 设置网络代理。如果不需要，请将 `http` 和 `https` 都设为 `null`。 | `http: "http://your-proxy:port"` |

#### 整合流程配置 (`integration_pipeline`)

此部分定义了**整合分析**以及**独立功能模块**所需的大部分参数。

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `input_excel_path` | 【整合分析】包含BSA和HVG数据的输入Excel文件路径。 | `data/my_analysis.xlsx` |
| `bsa_sheet_name` | 【整合分析】输入Excel中BSA数据所在的工作表(Sheet)名称。 | `BSA_Results` |
| `hvg_sheet_name` | 【整合分析】输入Excel中HVG数据所在的工作表(Sheet)名称。 | `HVG_List` |
| `output_sheet_name` | 【整合分析】分析结果将被写入到输入Excel中的一个新工作表，这是该工作表的名称。 | `Combined_BSA_HVG_Analysis` |
| `bsa_assembly_id` | 您的BSA数据所基于的基因组版本ID。此ID必须与 `genome_sources_list.yml` 中的ID匹配。 | `NBI_v1.1` |
| `hvg_assembly_id` | 您的HVG数据所基于的基因组版本ID。如果与 `bsa_assembly_id` 相同，则跳过同源映射。 | `HAU_v2.0` |
| `gff_files` | (可选) 手动指定GFF文件的路径。如果设为 `null`，程序会根据下载目录和版本ID自动推断路径。 | `NBI_v1.1: local/NBI.gff3.gz` |
| `homology_files` | (可选) 手动指定同源关系CSV文件的路径。当BSA和HVG版本不同时需要。 | `bsa_to_bridge_csv: local/NBI_to_At.csv` |
| `bridge_species_name` | 用于跨版本同源映射的桥梁物种名称。 | `Arabidopsis_thaliana` |
| `gff_db_storage_dir` | gffutils数据库的缓存目录。 | `gff_databases_cache` |
| `force_gff_db_creation` | 是否强制重新创建GFF数据库，即使缓存已存在。 | `false` |
| `bsa_columns` | 定义BSA工作表中染色体、起始和结束位置的列名。 | `{chr: chr, start: region.start, end: region.end}` |
| `hvg_columns` | 定义HVG工作表中基因ID、分类和Log2FC值的列名。 | `{gene_id: gene_id, category: hvg_category, ...}` |
| `homology_columns` | 定义同源关系CSV文件中的列名。 | `{query: Query, match: Match, evalue: Exp, ...}` |
| `selection_criteria_...` | 定义同源映射中筛选最佳匹配的详细标准（E-value, PID, Score阈值等）。 | `{top_n: 1, evalue_threshold: 1.0e-10, ...}` |
| `common_hvg_log2fc_threshold` | 用于判断“共同TopHVG”类别基因表达差异是否显著的Log2FC绝对值阈值。 | `1.0` |

-----

> ### **💡 重要提示：关于基因ID的模糊匹配**
>
> 在“整合分析”和“基因组转换”流程中，当程序根据您提供的基因ID在同源数据库中进行查找时，会自动启用 **模糊匹配** 机制。
>
>   * **工作原理**: 如果您提供的基因ID（例如 `Ghir.A01G000300`）在同源文件中没有找到完全相同的结果，程序会自动尝试查找所有以此ID为 **前缀** 的基因（例如 `Ghir.A01G000300.1`, `Ghir.A01G000300.2` 等）。
>   * **结果体现**:
>       * 当模糊匹配发生时，**GUI界面和命令行(CLI)的日志**中会显示一条警告信息，提示您此种匹配已发生。
>       * 在最终生成的Excel或CSV结果文件中，会有一个名为 **`Match_Note`** 的列。对于通过模糊匹配找到的条目，该列会明确标注 **"模糊匹配 on '原始ID'"** 及相关信息，方便您溯源和核对。
>
> 这个功能旨在提高匹配的成功率，确保您不会因为基因ID后缀的微小差异（如转录本编号）而错失重要的同源关系。

-----

### 3.2. 基因组源文件 (`genome_sources_list.yml`)

这个文件是一个清单，定义了每个棉花基因组版本的数据下载链接。

  * **顶级键**: `genome_sources`。
  * **子键**: 每个子键都是一个您自定义的、唯一的**基因组版本ID**（例如 `NBI_v1.1`）。这个ID将在主配置文件的 `bsa_assembly_id` 和 `hvg_assembly_id` 中被引用。

每个基因组版本ID下包含以下参数：

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `gff3_url` | 该版本基因组GFF3注释文件的下载链接。 | `"https://.../NBI_v1.1.gene.gff3.gz"` |
| `homology_ath_url` | 该版本与拟南芥（或其他桥梁物种）的同源关系文件的下载链接。通常是BLAST结果。 | `"https://.../blastx_..._vs_arabidopsis.xlsx.gz"` |
| `species_name` | 物种和版本的详细名称，主要用于创建易于识别的下载目录名。 | `"Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"` |
| `homology_id_slicer` | (可选) 用于剪切同源文件中基因ID的分隔符。例如，如果ID是`gene.1_other`，slicer设为`_`，程序会使用`gene.1`进行匹配。如果不需要剪切，设为 `null`。 | `_` |

#### 示例文件 (`genome_sources_list.yml`):

```yaml
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