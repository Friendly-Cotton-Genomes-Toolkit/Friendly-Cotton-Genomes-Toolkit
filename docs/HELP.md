# 友好棉花基因组工具包 (FCGT) - 帮助文档

欢迎使用 FCGT！本帮助文档将引导您完成从配置到使用的全部流程，无论您是使用图形界面（GUI）还是命令行（CLI），都能在这里找到详细的指引。

## 目录
1.  [**核心概念：配置文件**](#1-核心概念配置文件)
2.  [**数据准备要求**](#2-数据准备要求)
3.  [**图形界面 (GUI) 使用教程**](#3-图形界面-gui-使用教程)
4.  [**命令行 (CLI) 详细使用指南**](#4-命令行-cli-详细使用指南)
    * [通用选项](#通用选项)
    * [init](#init)
    * [download](#download)
    * [status](#status)
    * [preprocess-annos](#preprocess-annos)
    * [homology](#homology)
    * [gff-query](#gff-query)
    * [annotate](#annotate)
    * [ai-task](#ai-task)
    * [test-ai](#test-ai)
5.  [**高级案例：结合BSA与转录组筛选候选基因 (`integrate`)**](#5-高级案例结合bsa与转录组筛选候选基因-integrate)
6.  [**其他：网络代理**](#6-其他网络代理)

---

## 1. 核心概念：配置文件

FCGT 的所有行为都由一个核心配置文件 `config.yml` 指导。无论是文件路径、分析参数还是API密钥，都储存在这个文件中。它让您的分析流程可重复、可追溯。推荐通过 `init` 命令生成。

---

## 2. 数据准备要求

在使用命令行工具时，部分命令需要特定格式的输入文件。

* **基因列表文件**: 多个命令（如 `homology`, `gff-query`, `annotate`）接受一个基因列表作为输入。
    * **格式**: 纯文本文件 (`.txt`)。
    * **内容**: 每个基因ID占一行，不含任何多余的字符或标题行。
* **高级案例的Excel文件**: `integrate` 命令需要一个特定结构的Excel文件。
    * **BSA数据工作表**: 必需列 `chr`, `region.start`, `region.end`。
    * **HVG/DEG数据工作表**: 必需列 `gene_id`。

---

## 3. 图形界面 (GUI) 使用教程

双击 `FCGT-GUI.exe` 启动程序。首先在主页加载或通过 `init` 命令生成 `config.yml` 文件，然后在“数据工具”中即可使用各项功能。教程详情请参考软件各界面上的提示信息。

---

## 4. 命令行 (CLI) 详细使用指南

对于高级用户和需要自动化处理的场景，FCGT 提供了功能完善的命令行工具。

### 通用选项
这些选项可用于所有子命令。

| 参数 | 必需 | 说明 |
| :--- | :--- | :--- |
| `--config` | 是 | 指定要使用的 `config.yml` 配置文件路径。 |
| `--lang` | 否 | 设置命令行输出语言 (例如: `en`, `zh-hans`)。 |
| `-v`, `--verbose`| 否 | 启用详细的DEBUG级别日志输出。 |

### init
生成默认的配置文件 (`config.yml`) 和基因组源列表文件 (`genome_sources_list.yml`)。

**用法**: `python -m cotton_toolkit.cli init [OPTIONS]`

| 参数 | 必需 | 说明 |
| :--- | :--- | :--- |
| `--output-dir` | 否 | 指定生成文件的目录，默认为当前目录。 |
| `--overwrite` | 否 | 如果配置文件已存在，则覆盖它。 |

**示例**:
```bash
# 在当前目录生成默认配置
python -m cotton_toolkit.cli init
```

### download

下载指定的棉花参考基因组和注释数据。

**用法**: `python -m cotton_toolkit.cli download [OPTIONS]`

| **参数**        | **必需** | **说明**                                       |
| --------------- | -------- | ---------------------------------------------- |
| `--versions`    | 否       | 要下载的基因组版本列表，逗号分隔。默认为全部。 |
| `--force`       | 否       | 即使文件已存在也强制重新下载。                 |
| `--http-proxy`  | 否       | 覆盖配置中的HTTP代理地址。                     |
| `--https-proxy` | 否       | 覆盖配置中的HTTPS代理地址。                    |

**示例**:

```
# 下载单个基因组版本
python -m cotton_toolkit.cli download --versions HAU_v2.0
```

### status

显示所有基因组注释文件的下载和预处理状态。

**用法**: `python -m cotton_toolkit.cli status`

**示例**:

```
python -m cotton_toolkit.cli status
```

### preprocess-annos

预处理所有已下载的原始注释文件，将其转换为内部使用的标准化CSV格式。

**用法**: `python -m cotton_toolkit.cli preprocess-annos`

**示例**:

```
# 对所有已下载但未处理的文件进行预处理
python -m cotton_toolkit.cli preprocess-annos
```

### homology

对基因列表或区域进行同源映射（Liftover）。

**用法**: `python -m cotton_toolkit.cli homology [OPTIONS]`

| **参数**               | **必需** | **说明**                                                    |
| ---------------------- | -------- | ----------------------------------------------------------- |
| `--genes`              | 否       | 源基因ID列表，以逗号分隔。与`--region`二选一。              |
| `--region`             | 否       | 源基因组区域, 格式如 'Chr01:1000-5000'。与`--genes`二选一。 |
| `--source-asm`         | 是       | 源基因组版本ID。                                            |
| `--target-asm`         | 是       | 目标基因组版本ID。                                          |
| `--output-csv`         | 否       | 指定输出CSV文件的路径。                                     |
| `--top-n`              | 否       | 为每个基因保留的最佳匹配数(0表示所有)。                     |
| `--evalue`             | 否       | E-value阈值。                                               |
| `--pid`                | 否       | 一致性百分比(PID)阈值。                                     |
| `--score`              | 否       | BLAST得分(Score)阈值。                                      |
| `--no-strict-priority` | 否       | 禁用严格的同亚组/同源染色体匹配模式。                       |

**示例**:

```
python -m cotton_toolkit.cli homology --genes Gh_A01G0001,Gh_A01G0002 --source-asm HAU_v1 --target-asm HAU_v2.0
```

### gff-query

从GFF文件中查询基因信息。

**用法**: `python -m cotton_toolkit.cli gff-query [OPTIONS]`

| **参数**        | **必需** | **说明**                                                     |
| --------------- | -------- | ------------------------------------------------------------ |
| `--assembly-id` | 是       | 要查询的基因组版本ID。                                       |
| `--genes`       | 否       | 要查询的基因ID列表，逗号分隔。与`--region`二选一。           |
| `--region`      | 否       | 要查询的染色体区域，格式如 'A01:10000-20000'。与`--genes`二选一。 |
| `--output-csv`  | 否       | 指定输出CSV文件的路径。                                      |

**示例**:

```
python -m cotton_toolkit.cli gff-query --assembly-id HAU_v2.0 --region "A01:10000-20000"
```

### annotate

对基因列表进行功能注释。

**用法**: `python -m cotton_toolkit.cli annotate [OPTIONS]`

| **参数**        | **必需** | **说明**                                                     |
| --------------- | -------- | ------------------------------------------------------------ |
| `--genes`       | 是       | 要注释的基因ID列表（逗号分隔），或包含基因列表的文件路径。   |
| `--assembly-id` | 是       | 基因所属的基因组版本。                                       |
| `--types`       | 否       | 要执行的注释类型，逗号分隔 (go,ipr,kegg_orthologs,kegg_pathways)。 |
| `--output-path` | 否       | 指定输出CSV文件的完整路径。                                  |

**示例**:

```
python -m cotton_toolkit.cli annotate --genes my_genes.txt --assembly-id HAU_v2.0 --types go,ipr
```

### ai-task

在CSV文件上运行批量AI任务。

**用法**: `python -m cotton_toolkit.cli ai-task [OPTIONS]`

| **参数**          | **必需** | **说明**                                    |
| ----------------- | -------- | ------------------------------------------- |
| `--input-file`    | 是       | 输入的CSV文件。                             |
| `--source-column` | 是       | 要处理的源列名。                            |
| `--new-column`    | 是       | 要创建的新列名。                            |
| `--output-file`   | 否       | 指定输出CSV文件的完整路径。默认为自动生成。 |
| `--task-type`     | 否       | AI任务类型 (`translate` 或 `analyze`)。     |
| `--prompt`        | 否       | 自定义提示词模板。必须包含 `{text}`。       |

**示例**:

```
python -m cotton_toolkit.cli ai-task --input-file data.csv --source-column Abstract --new-column Abstract_CN --task-type translate
```

### test-ai

测试配置文件中指定的AI服务商连接。

**用法**: `python -m cotton_toolkit.cli test-ai [OPTIONS]`

| **参数**     | **必需** | **说明**                                                     |
| ------------ | -------- | ------------------------------------------------------------ |
| `--provider` | 否       | 要测试的服务商 (如 'google', 'openai')。默认为配置中的默认服务商。 |

**示例**:

```
python -m cotton_toolkit.cli test-ai --provider openai
```

------

## 5. 高级案例：结合BSA与转录组筛选候选基因 (`integrate`)

### 研究背景

在实际研究中，我们常常需要结合多组学数据来缩小候选基因的范围。这是一个典型场景：

1. 通过 **BSA (混池测序分析)**，我们定位了一个或多个与目标性状关联的染色体区域。
2. 同时，通过 **转录组测序**，我们获得了一批在不同条件下差异表达的基因（DEGs）或高变异基因（HVGs）。

我们的最终目标是：**找出那些既位于BSA候选区域内，又在转录组数据中有显著变化的基因**。

### 便捷的自动化流程 (`integrate` 命令)

为了简化这个流程，FCGT提供了一个高级的 `integrate` 命令行工具。您只需准备好一个符合特定格式的Excel文件（格式要求见[数据准备要求](https://www.google.com/search?q=%23高级案例的excel文件)），并正确配置`config.yml`中的`integration_pipeline`部分，即可一键运行。

**用法**: `python -m cotton_toolkit.cli integrate [OPTIONS]`

| **参数**             | **必需** | **说明**                            |
| -------------------- | -------- | ----------------------------------- |
| `--excel-path`       | 否       | 覆盖配置文件中的输入Excel文件路径。 |
| `--log2fc-threshold` | 否       | 覆盖配置文件中的 Log2FC 阈值。      |

**示例**:

```
python -m cotton_toolkit.cli integrate -c config.yml
```

------

## 6. 其他：网络代理

如果您的网络环境需要通过代理才能访问外部网站，请在 `config.yml` 文件中配置 `proxy` 部分。

```
proxy:
  http: "[http://127.0.0.1:7890](http://127.0.0.1:7890)"
  https: "[http://127.0.0.1:7890](http://127.0.0.1:7890)"
```
