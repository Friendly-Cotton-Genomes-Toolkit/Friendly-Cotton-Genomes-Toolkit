# 数据准备指南

为了确保整合分析流程 (Integration Pipeline) 能够顺利运行，请根据以下说明准备您的输入 Excel 文件。

---

## 1. BSA 定位结果表

这是包含您通过 BSA (Bulked Segregant Analysis) 方法定位到的候选区域的表格。

* **Sheet 名称**: 表格所在的 Sheet 名称必须与 `config.yml` 文件中 `integration_pipeline.bsa_sheet_name` 的值一致 (默认为: `BSA_Results`)。
* **必需列**: 表格中必须包含以下三列，且列名必须与 `config.yml` 中 `bsa_columns` 的配置完全一致。

| 列名 (默认) | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `chr` | 文本 | 染色体或支架(Scaffold)的ID。必须与GFF文件中的ID匹配。 | `Scaffold_A1` |
| `region.start`| 整数 | 候选区域的起始位置（1-based）。 | `10050` |
| `region.end` | 整数 | 候选区域的结束位置（1-based）。 | `250000` |

#### 示例表格 (`BSA_Results` Sheet):
```

chr          region.start   region.end   some_other_info

Scaffold_A1  1000           25000        0.98

Scaffold_D5  550000         780000       0.95

...          ...            ...          ...

```
---

## 2. 高变异基因 (HVG) 数据表

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
---

### **重要提示**

* **文件格式**: 请确保您的输入文件是标准的 Excel 文件 (`.xlsx` 或 `.xls`)。
* **列名匹配**: **最关键的一步**是确保您 Excel 表中的列标题与 `config.yml` 中 `bsa_columns` 和 `hvg_columns` 部分指定的名称**完全一致**。您可以在 "配置编辑" 选项卡中查看或修改这些预期的列名。
* **数据类型**: 请确保 `start` 和 `end` 列为整数，`log2fc` 列为数字。