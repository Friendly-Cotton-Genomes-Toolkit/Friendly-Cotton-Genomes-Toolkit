[中文（简体）](HELP.md) | [English](HELP_en.md) | [日本語](HELP_ja.md) | [繁體中文](HELP_zh-hant.md)

---

# フレンドリーコットンゲノムツールキット (FCGT) - ヘルプマニュアル

このページでは、ツールキットの使用に必要なデータ準備と設定ファイルに関する詳細なガイドを提供します。

## 目次

- [1. コア機能](https://www.google.com/search?q=%231-コア機能)
  - [1.1. 統合解析 (BSA領域によるHVGのスクリーニング)](https://www.google.com/search?q=%2311-統合解析-bsa領域によるhvgのスクリーニング)
  - [1.2. ゲノム変換 (独立したホモロジーマッピング)](https://www.google.com/search?q=%2312-ゲノム変換-独立したホモロジーマッピング)
  - [1.3. 遺伝子座検索 (GFFクエリ)](https://www.google.com/search?q=%2313-遺伝子座検索-gffクエリ)
- [2. データ準備ガイド](https://www.google.com/search?q=%232-データ準備ガイド)
  - [2.1. BSA座位領域テーブル](https://www.google.com/search?q=%2321-bsa座位領域テーブル)
  - [2.2. 高変動遺伝子 (HVG) データテーブル](https://www.google.com/search?q=%2322-高変動遺伝子-hvg-データテーブル)
- [3. 設定ファイルガイド](https://www.google.com/search?q=%233-設定ファイルガイド)
  - [3.1. メイン設定ファイル (`config.yml`)](https://www.google.com/search?q=%2331-メイン設定ファイル-configyml)
  - [3.2. ゲノムソースファイル (`genome_sources_list.yml`)](https://www.google.com/search?q=%2332-ゲノムソースファイル-genome_sources_listyml)

------

## 1. コア機能

このツールキットは主に3つのコア機能を提供しており、GUIの各タブまたはCLIの異なるサブコマンドで呼び出すことができます。

### 1.1. 統合解析 (BSA領域によるHVGのスクリーニング)

これはツールキットの中核機能であり、**BSAによって特定されたゲノム領域を使用して、提供された高変動遺伝子（HVG）のリストをフィルタリングする**ことを目的としています。これにより、候補遺伝子の範囲を大幅に絞り込み、後続のファインマッピングをサポートします。

**ワークフロー:**

1. **BSA領域の入力**: Excelの「BSAシート」に、対象の形質に関連するゲノム**領域**を入力する必要があります。これには `chr`, `region.start`, `region.end` の3つの列が必須です。
2. **領域内の全遺伝子の検索**: 設定ファイルで指定されたゲノムバージョン（`bsa_assembly_id`）に基づき、ツールは対応するGFFアノテーションファイルを読み込み、上記のBSA領域内に完全に含まれるすべての遺伝子を特定します。
3. **HVGリストとの共通集合の取得**: 次に、ツールは「HVGシート」で提供された遺伝子リストを読み込みます。
4. **バージョン間変換 (必要な場合)**: BSAデータとHVGデータが**異なる**ゲノムバージョンに基づいている場合、ツールは自動的に「ゲノム変換」（ホモロジーマッピング）を実行します。ステップ2で見つかった遺伝子IDをHVGゲノムバージョン上の対応するIDに変換してから、HVGリストとの共通集合を取得します。
5. **結果の出力**: 最終的に、重要なマッピング区間に位置し、かつ高変動遺伝子であるという、優先度の高い候補遺伝子のリストが、入力Excelファイルの新しいシートに出力されます。

### 1.2. ゲノム変換 (独立したホモロジーマッピング)

この機能を使用すると、あるゲノムバージョン上の遺伝子IDリストを、別のバージョンのホモログ遺伝子IDに独立して変換できます。これは、異なるゲノムアセンブリアノテーション間で遺伝子リストの「リフトオーバー」を行うのに非常に便利です。

- **入力**: ソース遺伝子IDリスト、ソースゲノムバージョン、ターゲットゲノムバージョン、および2つのホモロジー関係ファイル（ソース -> ブリッジ種、ブリッジ種 -> ターゲット）。
- **出力**: ソース遺伝子、ブリッジ遺伝子、正常にマッピングされたターゲット遺伝子、および関連するアライメントスコアを含むCSVファイル。

### 1.3. 遺伝子座検索 (GFFクエリ)

この機能では、遺伝子IDまたはゲノム領域に基づいて、GFFアノテーションファイルから詳細な遺伝子情報を迅速に抽出できます。

- **入力**: ゲノムバージョンID、1つ以上の遺伝子ID（カンマ区切り） **または** ゲノム領域（例： `Scaffold_A1:1000-5000`）。
- **出力**: 照会された遺伝子の詳細情報（位置、ストランド、転写産物、エクソン、CDS座標など）を含むCSVファイル。

------

## 2. データ準備ガイド

解析パイプラインをスムーズに実行するために、以下の指示に従って入力Excelファイルを準備してください。

### 2.1. BSA座位領域テーブル

これは、BSA (Bulked Segregant Analysis) 法によって特定した候補**領域**を含むテーブルです。

- **シート名**: このテーブルを含むシートの名前は、`config.yml` ファイルの `integration_pipeline.bsa_sheet_name` の値と一致させる必要があります (デフォルト: `BSA_Results`)。
- **必須列**: テーブルには以下の3つの列が含まれている必要があり、その名前は `config.yml` の `bsa_columns` 設定と完全に一致する必要があります。

| **列名 (デフォルト)** | **型**   | **説明**                                                     | **例**     |
| --------------------- | -------- | ------------------------------------------------------------ | ---------- |
| `chr`                 | テキスト | 染色体またはスカフォールドのID。GFFファイルのIDと一致する必要があります。 | `Ghir_A03` |
| `region.start`        | 整数     | 候補領域の開始位置（1-based）。                              | `10050`    |
| `region.end`          | 整数     | 候補領域の終了位置（1-based）。                              | `250000`   |

#### テーブル例 (`BSA_Results` シート):

```
chr				region.start   region.end   some_other_info
Ghir_A03	    10050          25000        0.98
Ghir_D04	    550000         780000       0.95
...          	...            ...          ...
```

------

### 2.2. 高変動遺伝子 (HVG) データテーブル

これは、スクリーニングした高変動遺伝子 (Highly Variable Genes) の情報を含むテーブルです。

- **シート名**: このテーブルを含むシートの名前は、`config.yml` の `integration_pipeline.hvg_sheet_name` の値と一致させる必要があります (デフォルト: `HVG_List`)。
- **必須列**: テーブルには以下の3つの列が含まれている必要があり、その名前は `config.yml` の `hvg_columns` 設定と完全に一致する必要があります。

| **列名 (デフォルト)** | **型**   | **説明**                                                     | **例**            |
| --------------------- | -------- | ------------------------------------------------------------ | ----------------- |
| `gene_id`             | テキスト | 遺伝子ID。HVGデータが基づいているゲノムバージョンのGFFファイルの遺伝子IDと一致する必要があります。 | `Ghir_A01G000100` |
| `hvg_category`        | テキスト | HVG分類。次の3つの値のいずれかである必要があります："WT特有TopHVG", "Ms1特有TopHVG", "共同TopHVG" | `WT特有TopHVG`    |
| `log2fc_WT_vs_Ms1`    | 数値     | Log2 Fold Change (WT vs Ms1) の値。                          | `2.58`            |

#### テーブル例 (`HVG_List` シート):

```
gene_id          hvg_category   log2fc_WT_vs_Ms1   p_value
Ghir_A01G000100  WT特有TopHVG   2.58               0.001
Ghir_A01G000200  共同TopHVG     -1.75              0.025
...              ...            ...                ...
```

------

## 3. 設定ファイルガイド

ツールキットの動作は、2つのコアYAML (`.yml`) 設定ファイルによって制御されます。これらはGUIの「設定エディタ」タブで変更できます。

### 3.1. メイン設定ファイル (`config.yml`)

このファイルは、すべての操作のコントロールセンターです。

#### 一般設定

| **パラメータ**  | **説明**                                                     | **例** |
| --------------- | ------------------------------------------------------------ | ------ |
| `i18n_language` | インターフェースの言語を設定します。選択肢: `zh-hans`, `zh-hant`, `en`, `ja` など。 | `ja`   |

#### ダウンローダー設定 (`downloader`)

このセクションは、データダウンロード機能の動作を制御します。

| **パラメータ**             | **説明**                                                     | **例**                           |
| -------------------------- | ------------------------------------------------------------ | -------------------------------- |
| `genome_sources_file`      | ゲノムのダウンロードリンクを含む `genome_sources_list.yml` ファイルを指します。相対パスまたは絶対パスが使用できます。 | `genome_sources_list.yml`        |
| `download_output_base_dir` | ダウンロードされたすべてのファイルが保存されるベースディレクトリ。 | `downloaded_cotton_data`         |
| `force_download`           | 既存のファイルを強制的に再ダウンロードするかどうか。`true` で「はい」、`false` で「いいえ」。 | `false`                          |
| `max_workers`              | マルチスレッドダウンロード時に使用する最大スレッド数。       | `3`                              |
| `proxies`                  | ネットワークプロキシを設定します。不要な場合は、`http` と `https` の両方を `null` に設定してください。 | `http: "http://your-proxy:port"` |

#### 統合パイプライン設定 (`integration_pipeline`)

このセクションでは、**統合解析**および**独立した機能モジュール**に必要なパラメータのほとんどを定義します。

| **パラメータ**                | **説明**                                                     | **例**                                             |
| ----------------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `input_excel_path`            | 【統合解析】BSAおよびHVGデータを含む入力Excelファイルのパス。 | `data/my_analysis.xlsx`                            |
| `bsa_sheet_name`              | 【統合解析】入力Excel内のBSAデータが含まれるシート名。       | `BSA_Results`                                      |
| `hvg_sheet_name`              | 【統合解析】入力Excel内のHVGデータが含まれるシート名。       | `HVG_List`                                         |
| `output_sheet_name`           | 【統合解析】解析結果が書き込まれる、入力Excel内の新しいシートの名前。 | `Combined_BSA_HVG_Analysis`                        |
| `bsa_assembly_id`             | BSAデータが基づいているゲノムバージョンID。このIDは `genome_sources_list.yml` 内のIDと一致する必要があります。 | `NBI_v1.1`                                         |
| `hvg_assembly_id`             | HVGデータが基づいているゲノムバージョンID。`bsa_assembly_id` と同じ場合、ホモロジーマッピングはスキップされます。 | `HAU_v2.0`                                         |
| `gff_files`                   | (任意) GFFファイルへのパスを手動で指定します。`null` に設定すると、プログラムはダウンロードディレクトリとバージョンIDからパスを推測します。 | `NBI_v1.1: local/NBI.gff3.gz`                      |
| `homology_files`              | (任意) ホモロジー関係CSVファイルへのパスを手動で指定します。BSAとHVGのバージョンが異なる場合に必要です。 | `bsa_to_bridge_csv: local/NBI_to_At.csv`           |
| `bridge_species_name`         | バージョン間のホモロジーマッピングに使用されるブリッジ種の名称。 | `Arabidopsis_thaliana`                             |
| `gff_db_storage_dir`          | gffutilsデータベースのキャッシュディレクトリ。               | `gff_databases_cache`                              |
| `force_gff_db_creation`       | キャッシュが既に存在する場合でも、GFFデータベースを強制的に再作成するかどうか。 | `false`                                            |
| `bsa_columns`                 | BSAシート内の染色体、開始位置、終了位置の列名を定義します。  | `{chr: chr, start: region.start, end: region.end}` |
| `hvg_columns`                 | HVGシート内の遺伝子ID、カテゴリ、Log2FC値の列名を定義します。 | `{gene_id: gene_id, category: hvg_category, ...}`  |
| `homology_columns`            | ホモロジー関係CSVファイル内の列名を定義します。              | `{query: Query, match: Match, evalue: Exp, ...}`   |
| `selection_criteria_...`      | ホモロジーマッピングで最適なマッチを選択するための詳細な基準を定義します（E-value, PID, Score閾値など）。 | `{top_n: 1, evalue_threshold: 1.0e-10, ...}`       |
| `common_hvg_log2fc_threshold` | 「共同TopHVG」カテゴリの遺伝子の発現差が有意であるかを判断するためのLog2FC絶対値の閾値。 | `1.0`                                              |

------

> ### **💡 重要なお知らせ：遺伝子IDのあいまい一致について**
>
> 「統合解析」および「ゲノム変換」ワークフローでは、提供された遺伝子IDをホモロジーデータベースで検索する際に、**あいまい一致**メカニズムが自動的に有効になります。
>
> - **仕組み**: 提供された遺伝子ID（例：`Ghir.A01G000300`）がホモロジーファイルで完全一致として見つからない場合、プログラムはこのIDを**プレフィックス**として持つすべての遺伝子（例：`Ghir.A01G000300.1`, `Ghir.A01G000300.2`など）を自動的に検索しようとします。
>
> - 結果への反映
>
>   :
>
>   - あいまい一致が発生した場合、**GUIおよびCLIのログ**に警告メッセージが表示され、この種のマッチングが行われたことが通知されます。
>   - 最終的に出力されるExcelまたはCSVファイルには、**`Match_Note`**という名前の列が作成されます。あいまい一致で見つかったエントリには、この列に**「Fuzzy Match on '元のID'」**といった情報が明記され、結果の追跡と検証が容易になります。
>
> この機能は、マッチングの成功率を高め、遺伝子IDのサフィックス（転写産物番号など）のわずかな違いによって重要なホモロジー関係を見逃さないように設計されています。

------

### 3.2. ゲノムソースファイル (`genome_sources_list.yml`)

このファイルは、各綿花ゲノムバージョンのデータダウンロードリンクを定義するカタログです。

- **トップレベルキー**: `genome_sources`。
- **サブキー**: 各サブキーは、ユーザーが定義する一意の**ゲノムバージョンID**です（例：`NBI_v1.1`）。このIDは、メイン設定ファイルの `bsa_assembly_id` および `hvg_assembly_id` パラメータで参照されます。

各ゲノムバージョンIDには、以下のパラメータが含まれます：

| **パラメータ**       | **説明**                                                     | **例**                                                  |
| -------------------- | ------------------------------------------------------------ | ------------------------------------------------------- |
| `gff3_url`           | このゲノムバージョンのGFF3アノテーションファイルのダウンロードリンク。 | `"https://.../NBI_v1.1.gene.gff3.gz"`                   |
| `homology_ath_url`   | このバージョンとシロイヌナズナ（または他のブリッジ種）とのホモロジー関係ファイルのダウンロードリンク。通常はBLASTの結果です。 | `"https://.../blastx_..._vs_arabidopsis.xlsx.gz"`       |
| `species_name`       | 種とバージョンの詳細な名称。主に、分かりやすいダウンロードディレクトリ名を作成するために使用されます。 | `"Gossypium hirsutum (AD1) 'TM-1' genome NAU-NBI_v1.1"` |
| `homology_id_slicer` | (任意) ホモロジーファイル内の遺伝子IDをトリミングするための区切り文字。例えば、IDが`gene.1_other`で、スライサーが`_`に設定されている場合、プログラムは`gene.1`を使用してマッチングします。トリミングが不要な場合は`null`に設定します。 | `_`                                                     |

#### ファイル例 (`genome_sources_list.yml`):

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