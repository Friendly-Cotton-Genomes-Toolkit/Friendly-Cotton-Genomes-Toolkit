[中文（简体）](HELP.md) | [English](HELP_en.md) | [日本語](HELP_ja.md) | [繁體中文](HELP_zh-hant.md)

---

# 友好棉花基因組分析工具包 (FCGT) - 幫助文檔

本頁提供了工具包使用所需的數據準備和配置文件設置的詳細指南。

## 目錄

  * [1. 核心功能](https://www.google.com/search?q=%231-%E6%A0%B8%E5%BF%83%E5%8A%9F%E8%83%BD)
      * [1.1. 整合分析 (BSA區域篩選HVG)](https://www.google.com/search?q=%2311-%E6%95%B4%E5%90%88%E5%88%86%E6%9E%90-bsa%E5%8D%80%E5%9F%9F%E7%AF%A9%E9%81%B8hvg)
      * [1.2. 基因組轉換 (獨立同源映射)](https://www.google.com/search?q=%2312-%E5%9F%BA%E5%9B%A0%E7%B5%84%E8%BD%89%E6%8F%9B-%E7%8D%A8%E7%AB%8B%E5%90%8C%E6%BA%90%E6%98%A0%E5%B0%84)
      * [1.3. 基因位點查詢 (GFF查詢)](https://www.google.com/search?q=%2313-%E5%9F%BA%E5%9B%A0%E4%BD%8D%E9%BB%9E%E6%9F%A5%E8%A9%A2-gff%E6%9F%A5%E8%A9%A2)
  * [2. 數據準備指南](https://www.google.com/search?q=%232-%E6%95%B8%E6%93%9A%E6%BA%96%E5%82%99%E6%8C%87%E5%8D%97)
      * [2.1. BSA 定位區域表](https://www.google.com/search?q=%2321-bsa-%E5%AE%9A%E4%BD%8D%E5%8D%80%E5%9F%9F%E8%A1%A8)
      * [2.2. 高變異基因 (HVG) 數據表](https://www.google.com/search?q=%2322-%E9%AB%98%E8%AE%8A%E7%95%B0%E5%9F%BA%E5%9B%A0-hvg-%E6%95%B8%E6%93%9A%E8%A1%A8)
  * [3. 配置文件指南](https://www.google.com/search?q=%233-%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6%E6%8C%87%E5%8D%97)
      * [3.1. 主配置文件 (`config.yml`)](https://www.google.com/search?q=%2331-%E4%B8%BB%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6-configyml)
      * [3.2. 基因組源文件 (`genome_sources_list.yml`)](https://www.google.com/search?q=%2332-%E5%9F%BA%E5%9B%A0%E7%B5%84%E6%BA%90%E6%96%87%E4%BB%B6-genome_sources_listyml)

-----

## 1\. 核心功能

本工具包主要提供三大核心功能，您可以在GUI的不同選項卡或使用CLI的不同子命令來調用它們。

### 1.1. 整合分析 (BSA區域篩選HVG)

此功能是工具包的核心，旨在**利用BSA定位到的基因組區域，來篩選您提供的高變異基因（HVG）列表**，從而大大縮小候選基因的範圍，為後續的精細定位提供支持。

**工作流程:**

1.  **輸入BSA區域**: 您需要在Excel的「BSA工作表」中提供與目標性狀關聯的基因組**區域**，必須包含 `chr`, `region.start`, `region.end` 這三列。
2.  **查找區域內所有基因**: 工具會根據您在配置文件中指定的基因組版本（`bsa_assembly_id`），讀取對應的GFF註釋文件，並找出所有完整包含在上述BSA區域內的基因。
3.  **與HVG列表取交集**: 接著，工具會讀取您在「HVG工作表」中提供的基因列表。
4.  **跨版本轉換 (如果需要)**: 如果您的BSA數據和HVG數據基於**不同**的基因組版本，工具會自動執行「基因組轉換」（同源映射），將第2步中找到的基因ID轉換為HVG基因組版本上的對應ID，然後再與您的HVG列表取交集。
5.  **輸出結果**: 最終，一個既位於關鍵定位區間、又屬於高變異基因的、高優先級的候選基因列表，將被輸出到輸入Excel文件的一個新工作表中。

### 1.2. 基因組轉換 (獨立同源映射)

此功能允許您獨立地將一個基因組版本上的基因ID列表，轉換為另一個版本上的同源基因ID。這對於在不同版本的基因組註釋之間進行基因列表的「Liftover」非常有用。

  * **輸入**: 源基因ID列表、源基因組版本、目標基因組版本、以及兩個同源關係文件（源-\>橋樑物種，橋樑物種-\>目標）。
  * **輸出**: 一個包含源基因、橋樑基因和成功映射的目標基因及其相關比對分數的CSV文件。

### 1.3. 基因位點查詢 (GFF查詢)

此功能允許您根據基因ID或基因組區域，快速地從GFF註釋文件中提取詳細的基因信息。

  * **輸入**: 基因組版本ID、一個或多個基因ID（逗號分隔） **或** 一個基因組區域（格式如 `Scaffold_A1:1000-5000`）。
  * **輸出**: 一個包含所查詢基因的詳細信息（如位置、鏈向、轉錄本、外顯子、CDS座標等）的CSV文件。

-----

## 2\. 數據準備指南

為了確保分析流程能夠順利運行，請根據以下說明準備您的輸入Excel文件。

### 2.1. BSA 定位區域表

這是包含您通過BSA (Bulked Segregant Analysis) 方法定位到的候選**區域**的表格。

  * **Sheet 名稱**: 表格所在的 Sheet 名稱必須與 `config.yml` 文件中 `integration_pipeline.bsa_sheet_name` 的值一致 (默認為: `BSA_Results`)。
  * **必需列**: 表格中必須包含以下三列，且列名必須與 `config.yml` 中 `bsa_columns` 的配置完全一致。

| 欄位名 (默認)  | 類型 | 說明                                                  | 範例       |
| :------------- | :--- | :---------------------------------------------------- | :--------- |
| `chr`          | 文本 | 染色體或支架(Scaffold)的ID。必須與GFF文件中的ID匹配。 | `Ghir_A03` |
| `region.start` | 整數 | 候選區域的起始位置（1-based）。                       | `10050`    |
| `region.end`   | 整數 | 候選區域的結束位置（1-based）。                       | `250000`   |

#### 範例表格 (`BSA_Results` Sheet):

```
chr				region.start   region.end   some_other_info
Ghir_A03	    10050          25000        0.98
Ghir_D04	    550000         780000       0.95
...          	...            ...          ...
```

-----

### 2.2. 高變異基因 (HVG) 數據表

這是包含您篩選出的高變異基因 (Highly Variable Genes) 信息的表格。

  * **Sheet 名稱**: 表格所在的 Sheet 名稱必須与 `config.yml` 文件中 `integration_pipeline.hvg_sheet_name` 的值一致 (默认为: `HVG_List`)。
  * **必需列**: 表格中必须包含以下三列，且列名必须与 `config.yml` 中 `hvg_columns` 的配置完全一致。

| 欄位名 (默認)      | 類型 | 說明                                                         | 範例              |
| :----------------- | :--- | :----------------------------------------------------------- | :---------------- |
| `gene_id`          | 文本 | 基因ID。必須與HVG數據所基於的基因組版本的GFF文件中的基因ID匹配。 | `Ghir_A01G000100` |
| `hvg_category`     | 文本 | HVG 分類。必須為以下三個值之一："WT特有TopHVG", "Ms1特有TopHVG", "共同TopHVG" | `WT特有TopHVG`    |
| `log2fc_WT_vs_Ms1` | 數字 | Log2 Fold Change (WT vs Ms1) 的值。                          | `2.58`            |

#### 範例表格 (`HVG_List` Sheet):

```
gene_id          hvg_category   log2fc_WT_vs_Ms1   p_value
Ghir_A01G000100  WT特有TopHVG   2.58               0.001
Ghir_A01G000200  共同TopHVG     -1.75              0.025
...              ...            ...                ...
```

-----

## 3\. 配置文件指南

工具包的行為由兩個核心的 YAML (`.yml`) 配置文件驅動。您可以在GUI的「配置編輯」選項卡中修改它們。

### 3.1. 主配置文件 (`config.yml`)

這個文件是所有操作的控制中心。

#### 通用設置

| 參數            | 說明                                                      | 範例      |
| :-------------- | :-------------------------------------------------------- | :-------- |
| `i18n_language` | 設置程序界面的語言。可選值:`zh-hans` `zh-hant`, `en` 等。 | `zh-hant` |

#### 下載器配置 (`downloader`)

此部分控制數據下載功能的行為。

| 參數                       | 說明                                                         | 範例                             |
| :------------------------- | :----------------------------------------------------------- | :------------------------------- |
| `genome_sources_file`      | 指向包含基因組下載連結的 `genome_sources_list.yml` 文件。可以是相對路徑或絕對路徑。 | `genome_sources_list.yml`        |
| `download_output_base_dir` | 所有下載文件存放的基礎目錄。                                 | `downloaded_cotton_data`         |
| `force_download`           | 是否強制重新下載已存在的文件。`true` 為是, `false` 為否。    | `false`                          |
| `max_workers`              | 多線程下載時使用的最大線程數。                               | `3`                              |
| `proxies`                  | 設置網路代理。如果不需要，請將 `http` 和 `https` 都設為 `null`。 | `http: "http://your-proxy:port"` |

#### 整合流程配置 (`integration_pipeline`)

此部分定義了**整合分析**以及**獨立功能模塊**所需的大部分參數。

| 參數                          | 說明                                                         | 範例                                               |
| :---------------------------- | :----------------------------------------------------------- | :------------------------------------------------- |
| `input_excel_path`            | 【整合分析】包含BSA和HVG數據的輸入Excel文件路徑。            | `data/my_analysis.xlsx`                            |
| `bsa_sheet_name`              | 【整合分析】輸入Excel中BSA數據所在的工作表(Sheet)名稱。      | `BSA_Results`                                      |
| `hvg_sheet_name`              | 【整合分析】輸入Excel中HVG數據所在的工作表(Sheet)名稱。      | `HVG_List`                                         |
| `output_sheet_name`           | 【整合分析】分析結果將被寫入到輸入Excel中的一個新工作表，這是該工作表的名稱。 | `Combined_BSA_HVG_Analysis`                        |
| `bsa_assembly_id`             | 您的BSA數據所基於的基因組版本ID。此ID必須與 `genome_sources_list.yml` 中的ID匹配。 | `NBI_v1.1`                                         |
| `hvg_assembly_id`             | 您的HVG數據所基於的基因組版本ID。如果與 `bsa_assembly_id` 相同，則跳過同源映射。 | `HAU_v2.0`                                         |
| `gff_files`                   | (可選) 手動指定GFF文件的路徑。如果設为 `null`，程序會根據下載目錄和版本ID自動推斷路徑。 | `NBI_v1.1: local/NBI.gff3.gz`                      |
| `homology_files`              | (可選) 手動指定同源關係CSV文件的路徑。當BSA和HVG版本不同時需要。 | `bsa_to_bridge_csv: local/NBI_to_At.csv`           |
| `bridge_species_name`         | 用於跨版本同源映射的橋樑物種名稱。                           | `Arabidopsis_thaliana`                             |
| `gff_db_storage_dir`          | gffutils數據庫的快取目錄。                                   | `gff_databases_cache`                              |
| `force_gff_db_creation`       | 是否強制重新創建GFF數據庫，即使快取已存在。                  | `false`                                            |
| `bsa_columns`                 | 定義BSA工作表中染色體、起始和結束位置的欄位名。              | `{chr: chr, start: region.start, end: region.end}` |
| `hvg_columns`                 | 定義HVG工作表中基因ID、分類和Log2FC值的欄位名。              | `{gene_id: gene_id, category: hvg_category, ...}`  |
| `homology_columns`            | 定義同源關係CSV文件中的欄位名。                              | `{query: Query, match: Match, evalue: Exp, ...}`   |
| `selection_criteria_...`      | 定義同源映射中篩選最佳匹配的詳細標準（E-value, PID, Score閾值等）。 | `{top_n: 1, evalue_threshold: 1.0e-10, ...}`       |
| `common_hvg_log2fc_threshold` | 用於判斷「共同TopHVG」類別基因表達差異是否顯著的Log2FC絕對值閾值。 | `1.0`                                              |

-----

> ### **💡 重要提示：關於基因ID的模糊匹配**
>
> 在「整合分析」和「基因組轉換」流程中，當程序根據您提供的基因ID在同源數據庫中進行查找時，會自動啟用 **模糊匹配** 機制。
>
>   * **工作原理**: 如果您提供的基因ID（例如 `Ghir.A01G000300`）在同源文件中沒有找到完全相同的結果，程序會自動嘗試查找所有以此ID為 **前綴** 的基因（例如 `Ghir.A01G000300.1`, `Ghir.A01G000300.2` 等）。
>   * **結果體現**:
>       * 當模糊匹配發生時，**GUI界面和命令行(CLI)的日誌**中會顯示一條警告信息，提示您此種匹配已發生。
>       * 在最終生成的Excel或CSV結果文件中，會有一個名為 **`Match_Note`** 的列。對於通過模糊匹配找到的條目，該列會明確標註 **"模糊匹配 on '原始ID'"** 及相關信息，方便您溯源和核對。
>
> 這個功能旨在提高匹配的成功率，確保您不會因為基因ID後綴的微小差異（如轉錄本編號）而錯失重要的同源關係。

-----

### 3.2. 基因組源文件 (`genome_sources_list.yml`)

這個文件是一個清單，定義了每個棉花基因組版本的數據下載連結。

  * **頂級鍵**: `genome_sources`。
  * **子鍵**: 每個子鍵都是一個您自定義的、唯一的**基因組版本ID**（例如 `NBI_v1.1`）。這個ID將在主配置文件的 `bsa_assembly_id` 和 `hvg_assembly_id` 中被引用。

每個基因組版本ID下包含以下參數：

| 參數                 | 說明                                                         | 範例                                                    |
| :------------------- | :----------------------------------------------------------- | :------------------------------------------------------ |
| `gff3_url`           | 該版本基因組GFF3註釋文件的下載連結。                         | `"https://.../NBI_v1.1.gene.gff3.gz"`                   |
| `homology_ath_url`   | 該版本與擬南芥（或其他橋樑物種）的同源關係文件的下載連結。通常是BLAST結果。 | `"https://.../blastx_..._vs_arabidopsis.xlsx.gz"`       |
| `species_name`       | 物種和版本的詳細名稱，主要用於創建易於識別的下載目錄名。     | `"Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"` |
| `homology_id_slicer` | (可選) 用於剪切同源文件中基因ID的分隔符。例如，如果ID是`gene.1_other`，slicer設为`_`，程序會使用`gene.1`進行匹配。如果不需要剪切，設为 `null`。 | `_`                                                     |

#### 範例文件 (`genome_sources_list.yml`):

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