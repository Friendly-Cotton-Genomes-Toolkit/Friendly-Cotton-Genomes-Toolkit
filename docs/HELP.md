# 友好棉花基因组工具包 (FCGT) - 帮助文档

欢迎使用 FCGT！本帮助文档将引导您完成从配置到使用的全部流程，无论您是使用图形界面（GUI）还是命令行（CLI），都能在这里找到详细的指引。

## 目录
1.  [**核心概念：配置文件讲解**](#1-核心概念配置文件讲解)
    * [`config.yml` 总览](#configyml-总览)
    * [各部分详解](#各部分详解)
2.  [**数据准备：输入文件格式要求**](#2-数据准备输入文件格式要求)
    * [**【重点】联合分析输入要求**](#重点联合分析输入要求)
        * [BSA 数据工作表](#bsa-数据工作表)
        * [HVG 数据工作表](#hvg-数据工作表)
    * [**其他工具输入要求**](#其他工具输入要求)
        * [功能注释](#功能注释)
        * [AI 助手](#ai-助手)
        * [基因组转换 / 基因位点查询](#基因组转换--基因位点查询)
3.  [**图形界面 (GUI) 使用教程**](#3-图形界面-gui-使用教程)
    * [主界面与导航](#主界面与导航)
    * [主页：开始你的工作](#主页开始你的工作)
    * [配置编辑器：自定义你的工具](#配置编辑器自定义你的工具)
    * [联合分析：核心流程](#联合分析核心流程)
    * [数据工具：多功能瑞士军刀](#数据工具多功能瑞士军刀)
4.  [**命令行 (CLI) 使用教程**](#4-命令行-cli-使用教程)
    * [基本用法](#基本用法)
    * [命令详解](#命令详解)
5.  [**高级主题：网络代理**](#5-高级主题网络代理)

---

## 1. 核心概念：配置文件讲解

FCGT 的所有行为都由一个核心配置文件 `config.yml` 指导。无论是 GUI 还是 CLI，都会读取这个文件来确定工作参数。理解这个文件是高效使用本工具的关键。

### `config.yml` 总览
这是一个 [YAML](https://yaml.org/) 格式的文件，具有清晰的层级结构，您可以使用任何文本编辑器打开它。它的主要部分包括：

* `downloader`: 数据下载器相关的配置。
* `ai_services`: AI 助手相关的配置，包括不同服务商的 API Key 和模型。
* `ai_prompts`: AI 任务的指令模板（Prompt）。
* `integration_pipeline`: “联合分析”核心流程的参数。
* `annotation_tool`: 功能注释工具的配置。

### 各部分详解

#### `downloader`
```yaml
downloader:
  genome_sources_file: genome_sources_list.yml
  download_output_base_dir: downloaded_cotton_data
  force_download: false
  max_workers: 3
  proxies:
    http: null
    https: null
```
* `genome_sources_file`: 定义基因组下载来源的另一个 YAML 文件路径，**通常保持默认即可**。
* `download_output_base_dir`: 所有下载的基因组数据存放的根目录。
* `force_download`: 是否强制重新下载已存在的文件。`false` 表示跳过已下载的文件。
* `max_workers`: 下载时使用的最大线程数，合理设置可以加速下载。
* `proxies`: 网络代理设置，详见 [网络代理](#5-高级主题网络代理) 部分。

#### `ai_services`
```yaml
ai_services:
  default_provider: google
  providers:
    google:
      api_key: 'YOUR_GOOGLE_API_KEY'
      model: 'gemini-1.5-flash'
      base_url: null
    openai:
      api_key: 'YOUR_OPENAI_API_KEY'
      model: 'gpt-4o'
      base_url: null
    # ... 其他服务商 ...
```
* `default_provider`: 在 GUI 的 AI 助手页面默认选择的服务商。
* `providers`: 包含所有支持的 AI 服务商。
    * `api_key`: **【必填】** 您从相应服务商获取的 API Key。
    * `model`: 您希望使用的具体模型名称。
    * `base_url`: 如果您使用第三方代理或私有部署的服务，请在此填写API的基地址。

#### `integration_pipeline`
这是**联合分析**功能的核心配置区域。
```yaml
integration_pipeline:
  input_excel_path: "path/to/your/input.xlsx"
  bsa_sheet_name: "BSA_QTL"
  hvg_sheet_name: "HVG_results"
  output_sheet_name: "Integrated_Candidates"
  bsa_assembly_id: "NAU-NBI_v1.1"
  hvg_assembly_id: "CRI_v1"
  bridge_species_name: "arabidopsis"
  # ... 其他高级参数 ...
```
* `input_excel_path`: 包含 BSA 和 HVG 数据的 Excel 文件路径。
* `bsa_sheet_name` / `hvg_sheet_name`: Excel 中对应数据所在的工作表（Sheet）名称。
* `output_sheet_name`: 分析结果将写入到这个新的工作表中。
* `bsa_assembly_id` / `hvg_assembly_id`: 两个数据集分别对应的基因组版本ID，必须与 `genome_sources_list.yml` 中的ID一致。
* `bridge_species_name`: 用于在不同版本间进行同源映射的“桥梁物种”，默认为拟南芥 `arabidopsis`。
* `selection_criteria_*`: 定义了从“源->桥梁”和“桥梁->目标”两步同源筛选时所使用的严格标准（如 E-value, PID, Score 等），**建议高级用户修改**。

---

## 2. 数据准备：输入文件格式要求

“Garbage in, garbage out.” 正确的数据格式是成功分析的第一步。

### **【重点】联合分析输入要求**

此功能是工具的核心，对输入格式要求最为严格。您需要准备一个 **Excel (`.xlsx`) 文件**，其中包含至少两个符合以下要求的工作表（Sheet）。

#### BSA 数据工作表
此工作表包含您通过 BSA (Bulked Segregant Analysis) 方法定位到的候选**区域**。

* **Sheet 名称**: 表格所在的 Sheet 名称必须与 `config.yml` 文件中 `integration_pipeline.bsa_sheet_name` 的值一致 (默认为: `BSA_Results`)。
* **必需列**: 表格中**必须**包含以下三列，列名（表头）必须与 `config.yml` 中 `bsa_columns` 的配置完全一致。

| 列名 (默认)    | 数据类型 | 说明                                                         | 示例         |
| :------------- | :------- | :----------------------------------------------------------- | :----------- |
| `chr`          | 文本     | 染色体或支架(Scaffold)的ID。必须与GFF文件中的ID命名方式一致。 | `Ghir_A03`   |
| `region.start` | 整数     | 候选区域的起始位置（1-based）。                              | `10050`      |
| `region.end`   | 整数     | 候选区域的结束位置（1-based）。                              | `250000`     |

* **示例表格** (`BSA_Results` Sheet):
    ```
    chr         region.start   region.end   some_other_info
    Ghir_A03    10050          25000        0.98
    Ghir_D04    550000         780000       0.95
    ...         ...            ...          ...
    ```

#### HVG 数据工作表
此工作表包含您筛选出的高变异基因 (Highly Variable Genes) 列表。

* **Sheet 名称**: 表格所在的 Sheet 名称必须与 `config.yml` 文件中 `integration_pipeline.hvg_sheet_name` 的值一致 (默认为: `HVG_List`)。
* **必需列**: 表格中**必须**包含以下三列，列名（表头）必须与 `config.yml` 中 `hvg_columns` 的配置完全一致。

| 列名 (默认)        | 数据类型 | 说明                                                         | 示例              |
| :----------------- | :------- | :----------------------------------------------------------- | :---------------- |
| `gene_id`          | 文本     | 基因ID。必须与HVG数据所基于的基因组版本的GFF文件中的基因ID匹配。 | `Ghir_A01G000100` |
| `hvg_category`     | 文本     | HVG 分类。用于后续的逻辑判断。                               | `WT特有TopHVG`    |
| `log2fc_WT_vs_Ms1` | 数字     | Log2 Fold Change 的值。                                      | `2.58`            |

* **示例表格** (`HVG_List` Sheet):
    ```
    gene_id          hvg_category   log2fc_WT_vs_Ms1   p_value
    Ghir_A01G000100  WT特有TopHVG   2.58               0.001
    Ghir_A01G000200  共同TopHVG     -1.75              0.025
    ...              ...            ...                ...
    ```

### **其他工具输入要求**

#### 功能注释
* **文件格式**: Excel (`.xlsx`) 或 CSV (`.csv`)。
* **要求**: 文件中必须有一列包含您想注释的**基因ID**。您需要在GUI界面上准确填写这一列的表头名称。

#### AI 助手
* **文件格式**: CSV (`.csv`)。
* **要求**: 文件中必须有一列是您希望AI处理的**文本内容**。您需要在GUI上指定该列的表头，并为AI生成的新内容指定一个新的列名。

#### 基因组转换 / 基因位点查询
* **格式**: 在GUI界面的大文本框中直接粘贴基因列表，**每行一个基因ID**。不支持其他格式。

---

## 3. 图形界面 (GUI) 使用教程

双击 `FCGT-GUI.exe` (或对应系统的可执行文件) 启动程序。

### 主界面与导航
* **左侧导航栏**: 用于切换四个主要功能页面：**主页**、**配置编辑器**、**联合分析**和**数据工具**。
* **底部状态栏**: 左侧显示当前操作状态，右侧显示任务进度条。
* **底部日志区**: 显示详细的操作日志，可通过“显示/隐藏日志”按钮控制。

### 主页：开始你的工作
这是程序的入口。
1.  **加载配置**: 点击 **“加载配置文件...”** 选择您本地的 `config.yml` 文件。成功加载后，程序会解锁所有功能。
2.  **生成配置**: 如果您是第一次使用，点击 **“生成默认配置...”**，选择一个空目录，程序会自动生成 `config.yml` 和 `genome_sources_list.yml` 两个模板文件。然后您需要根据本文第一部分的讲解，修改 `config.yml`（尤其是API Key），再回来加载它。

### 配置编辑器：自定义你的工具
这个页面是 `config.yml` 文件的可视化版本，您在这里做的所有修改，点击右上角的 **“应用并保存配置”** 按钮后都会被写入到文件中。
* **AI服务商**: 对于每个AI服务商，您可以填写`API Key`和`Base URL`。填写 Key 后，点击 **“刷新”** 按钮，程序会联网获取该服务商支持的模型列表，并填充到下方的“模型”下拉框中。

### 联合分析：核心流程
这是FCGT的核心，用于筛选候选基因。
1.  **指定文件**: 点击“浏览...”选择包含BSA和HVG数据的Excel文件。
2.  **选择工作表**: 程序会自动读取Excel中的所有工作表名称，请在下方的两个下拉框中分别选择BSA和HVG数据所在的工作表。
3.  **指定基因组版本**: 根据您的实验设计，在下方的两个下拉框中选择BSA和HVG数据对应的基因组版本。
4.  **开始分析**: 点击 **“开始联合分析”** 按钮。程序将自动执行：
    * 根据BSA区间提取基因。
    * 将BSA基因和HVG基因通过“桥梁物种”进行同源映射，统一到同一版本。
    * 取交集，找到最终的候选基因。
    * 结果会作为新工作表写入到您指定的Excel文件中。

### 数据工具：多功能瑞士军刀
这里集合了多个实用的小工具。

#### **数据下载**
* 选择您需要下载的棉花基因组版本（可多选）。
* **使用网络代理**: 如果您在 `config.yml` 中配置了代理地址，并希望下载时使用，请勾选此项。
* **强制重新下载**: 如果勾选，即使本地已存在文件，程序也会重新下载。
* 点击 **“开始下载”**。

#### **基因组转换 (Liftover)**
* 在左侧文本框中输入或粘贴源基因ID列表。
* 在“源基因组版本”下拉框中选择这些ID对应的版本。
* 在“目标基因组版本”下拉框中选择您想转换到的版本。**特别地**，您可以选择“拟南芥”，程序会自动寻找与您源基因ID同源的拟南芥基因。
* 点击 **“开始同源映射”**，结果会保存为一个CSV文件。

#### **基因位点查询**
* 选择一个基因组版本。
* **二选一查询**:
    1.  在“染色体区域”框中输入 `染色体:起始-终止` 格式的坐标，如 `Ghir_A01:10000-20000`。
    2.  或，在下方的大文本框中输入基因ID列表。
* 点击 **“开始基因查询”**，程序会查找指定区域内的所有基因，或查询指定基因的坐标信息。

#### **功能注释**
* 选择一个包含基因ID列表的CSV或Excel文件。
* 在“基因ID所在列名”中准确输入包含基因ID的列标题。
* 勾选您需要的注释类型（GO, IPR, KEGG）。**此功能需要本地数据库支持，请确保已按要求配置好数据库路径。**
* 点击 **“开始功能注释”**。

#### **AI 助手**
* 选择一个待处理的CSV文件。
* 选择任务类型：“翻译”或“分析”。
* 在下方的 **Prompt指令** 框中，修改或使用默认的指令模板。`{text}` 是一个占位符，程序运行时会自动替换为表格中每一行的内容。
* 在“源列名”中填写您要处理的列的标题。
* 在“新列名”中为AI生成的结果指定一个新的列标题。
* 点击 **“开始AI任务”**。

#### **XLSX转CSV**
* 一个简单的小工具，选择一个Excel文件，它会把里面**所有**工作表的内容合并到**一个**CSV文件中。

---

## 4. 命令行 (CLI) 使用教程

CLI提供了与GUI完全相同的功能，适合自动化和批量处理。

### 基本用法
所有命令都通过 `python -m cotton_toolkit.cli` 来调用。
```bash
# 查看所有可用命令
python -m cotton_toolkit.cli --help
```

### 命令详解
以下是主要命令及其常用参数：

#### `download`
下载基因组数据。
```bash
# 下载所有基因组
python -m cotton_toolkit.cli download --config config.yml

# 只下载特定版本，并强制覆盖
python -m cotton_toolkit.cli download -c config.yml -v NAU-NBI_v1.1 CRI_v1 --force
```

#### `integrate`
运行联合分析流程。
```bash
# 使用配置文件中的所有参数运行
python -m cotton_toolkit.cli integrate -c config.yml

# 命令行覆盖部分参数
python -m cotton_toolkit.cli integrate -c config.yml --input-excel new_data.xlsx --bsa-sheet "QTL-2" --hvg-sheet "DEG"
```

#### `homology_map`
进行同源基因映射 (Liftover)。
```bash
# 直接在命令行提供基因ID
python -m cotton_toolkit.cli homology_map -c config.yml --genes Ghir.A01G000100,Ghir.A01G000200 --source_assembly NAU-NBI_v1.1 --target_assembly CRI_v1
```

#### `gff_query`
查询基因位置信息。
```bash
# 按区域查询
python -m cotton_toolkit.cli gff_query -c config.yml --assembly NAU-NBI_v1.1 --region Ghir_D05:10000-50000

# 按基因ID查询
python -m cotton_toolkit.cli gff_query -c config.yml --assembly NAU-NBI_v1.1 --genes Ghir.A01G000100,Ghir.D05G001800
```

#### `ai`
执行AI任务。
```bash
python -m cotton_toolkit.cli ai -c config.yml --input data.csv --source-column "Description" --new-column "中文描述" --task-type translate
```
#### `convert`
转换XLSX到CSV。
```bash
python -m cotton_toolkit.cli convert -i input.xlsx -o output.csv
```
---

## 5. 高级主题：网络代理

如果您的网络环境需要通过代理才能访问外部资源（如CottonGen、AI服务商等），FCGT 提供了代理支持。

* **配置**: 在 `config.yml` 的 `downloader.proxies` 部分填写您的 `http` 和 `https` 代理地址。
    ```yaml
    proxies:
      http: '[http://127.0.0.1:7890](http://127.0.0.1:7890)'
      https: '[http://127.0.0.1:7890](http://127.0.0.1:7890)'
    ```
* **GUI中使用**:
    * 在 **数据下载** 工具中，勾选“使用网络代理”开关。
    * 在 **AI 助手** 工具中，勾选“使用网络代理”开关。
* **CLI中使用**:
    * CLI的 `download` 和 `ai` 命令会自动读取并使用配置文件中的代理，无需额外参数。

> **注意**: 如果您在GUI中开启了代理开关，但在配置文件中并未填写有效的代理地址，程序会提示错误并终止任务。

