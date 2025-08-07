<div align="center">
  <img src="ui/assets/logo.png" alt="logo" width="128" height="128" />
  <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;">
    友好棉花基因组工具包 (FCGT)
  </h1>
  <p>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a>
  </p>
</div>



## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md) | [English](docs/README_en.md) | [日本語](docs/README_ja.md) | [繁體中文](docs/README_zh-hant.md)

---

## 🚀 项目简介

**FCGT (Friendly Cotton Genomes Toolkit)** 是一款专为棉花研究者，尤其是**非生物信息专业背景**的科研人员和学生设计的基因组数据分析工具箱。我们致力于将复杂的数据处理流程封装在简洁的图形界面（GUI）和命令行（CLI）背后，让您无需进行繁琐的环境配置和代码编写，即可**开箱即用**。

本工具包提供了一系列强大的棉花基因组数据处理工具，包括多版本间的同源基因映射（Liftover）、基因功能注释、基因位点查询、富集分析、AI助手批量处理数据等。它旨在成为您日常科研工作中不可或缺的、**稳定可靠**的得力助手。

---

## ✨ 核心亮点与功能

### 1. 极致友好，开箱即用
* **数据安全**：除数据下载、AI功能和更新检测外，全程无需联网，防止数据泄露。源码开源，接受社区检查。
* **图形界面优先**: 所有核心工具均可通过直观的图形界面完成，鼠标点击即可运行分析。
* **交互式任务反馈**: **所有耗时操作（如数据下载、AI处理）均配有实时进度条弹窗，您可以随时取消任务。任务结束后会收到清晰的成功、失败或取消提示，彻底告别盲目等待。**
* *流畅的操作体验**: 经过精心优化的UI逻辑，确保了界面切换的即时响应和**全页面顺滑的鼠标滚轮滚动**，体验媲美原生桌面应用。**
* 多语言支持**: 内置简/繁中文、英文、日文界面，打破语言壁垒。

### 2. 高效的自动化与批量处理

* **强大的并发与任务管理**: 内置多线程加速，无论是下载海量基因组数据，还是使用AI助手批量处理上千行表格，都能显著缩短等待时间。交互式的进度弹窗让您对任务状态了如指掌，并能随时取消。
* **智能配置同步**: 在配置编辑器中做的修改（如更换AI模型）会实时同步到所有功能页面，无需重启或手动刷新，所见即所得。
* **命令行支持**: 对于高级用户，我们同样提供功能完善的命令行工具，方便您将FCGT整合到自动化分析流程中。

### 3. 精准的基因组工具集
* **棉花版 Liftover**: 解决了棉花领域长期缺乏在不同基因组版本间进行基因列表转换工具的难题。
* **一站式数据工具**: 集合了基因注释、GFF查询、富集分析、格式转换等多种常用功能，无需在多个软件间来回切换。
* **标准化数据下载**: 一键下载来自 [CottonGen](https://www.cottongen.org/) 等权威数据库的主流棉花参考基因组及注释文件。

### 4. 跨平台，随处可用
* 我们为 **Windows** 用户都提供了预编译的可执行文件（其他系统的用户可以执行Python运行）。
* 无论您使用何种主流操作系统，都能获得一致、流畅的使用体验。

---

## 快速入门

我们已在 **[发布页面 (Releases)](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases)** 为您准备了开箱即用的可执行文件，这是最推荐的使用方式。

* **图形界面版**: 下载 `FCGT-GUI.exe` (Windows) 或对应您系统的文件，直接双击运行。
* **命令行工具**: 下载 `FCGT.exe` (Windows) 或对应您系统的文件，在终端中运行。

**开发者与高级用户**也可以从源码启动：
```bash
# 运行图形界面
python gui_app.py

# 查看命令行帮助
python -m cotton_toolkit.cli --help

# 打包程序/打包程式/Packaging program/パッケージングプログラム
python -m nuitka --standalone --mingw64 --windows-disable-console --windows-icon-from-ico=ui/assets/logo.ico --plugin-enable=tk-inter --plugin-enable=anti-bloat --lto=yes --include-data-dir=ui/assets=ui/assets --include-package-data=ttkbootstrap --output-dir=dist main.py
```

------

## 截图预览

<img src="assets/主界面.png" style="zoom:50%;" />

<img src="assets\配置编辑器.png" style="zoom:50%;" />

<img src="assets\数据工具.png" style="zoom:50%;" />

------

## 致谢与引用

### 开发与致谢

- **特别感谢**: 本项目的开发得到了**开源社区**和所有为棉花研究做出贡献的**科研工作者**的支持。

### 版权与许可

本工具的开发使用了以下优秀的开源软件包，感谢它们的开发者：

| **库**                  | **主要用途**                                                 | **开源许可证**                                     |
| ----------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| **pydantic**            | 用于数据验证、设置管理和类型提示强制，是项目中配置模型的核心。 | MIT License                                        |
| **typing-extensions**   | 为标准 `typing` 模块提供新的或实验性的类型提示支持。         | Python Software Foundation License                 |
| **packaging**           | 用于处理 Python 包的版本、标记和规范。                       | Apache-2.0 / BSD                                   |
| **requests**            | 一个优雅、简洁的HTTP库，用于执行网络请求，如下载数据。       | Apache-2.0 License                                 |
| **tqdm**                | 一个快速、可扩展的进度条工具，用于在命令行和循环中显示进度。 | MIT License                                        |
| **gffutils**            | 用于创建、管理和查询GFF/GTF文件数据库，是基因组注释操作的基础。 | MIT License                                        |
| **pandas**              | 提供高性能、易于使用的数据结构和数据分析工具，是所有数据处理的核心。 | BSD 3-Clause License                               |
| **pyyaml**              | 用于解析YAML文件，是加载 `config.yml` 配置文件的关键。       | MIT License                                        |
| **google-generativeai** | Google 的官方库，用于与 Gemini 等生成式AI模型进行交互。      | Apache-2.0 License                                 |
| **numpy**               | Python科学计算的基础包，为Pandas等库提供多维数组对象和数学运算支持。 | BSD 3-Clause License                               |
| **customtkinter**       | 用于构建现代化、美观的图形用户界面（GUI）。                  | MIT License                                        |
| **pillow**              | Pillow (PIL Fork) 是一个强大的图像处理库，用于在GUI中加载和显示图标等图片。 | Historical Permission Notice and Disclaimer (HPND) |
| **diskcache**           | 提供基于磁盘的缓存功能，用于存储临时或可重复使用的数据，以提高性能。 | Apache-2.0 License                                 |
| **click**               | 用于以组合式的方式创建漂亮的命令行界面（CLI）。              | BSD 3-Clause License                               |
| **matplotlib**          | 一个全面的库，用于在Python中创建静态、动画和交互式的可视化图表。 | matplotlib License (BSD-style)                     |
| **statsmodels**         | 提供用于估计多种统计模型、进行统计检验和数据探索的类和函数。 | BSD 3-Clause License                               |
| **protobuf**            | Google 的数据交换格式，通常被其他库（如TensorFlow或某些API客户端）所依赖。 | BSD 3-Clause License                               |
| **openpyxl**            | 用于读取和写入 Excel 2010 xlsx/xlsm/xltx/xltm 文件的库。     | MIT License                                        |
| **networkx**            | 用于创建、操作和研究复杂网络的结构、动态和功能的Python包。   | BSD 3-Clause License                               |
| **upsetplot**           | 用于生成UpSet图，这是一种用于可视化集合交集数据的有效方法。  | BSD 3-Clause License                               |

### 数据来源与引文

本工具依赖 [CottonGen](https://www.cottongen.org/) 提供的权威数据，感谢其团队持续的开放和维护。

- **CottonGen 文章**:

  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **基因组引用文献**:

  - **NAU-NBI_v1.1**: Zhang et. al., [Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement](http://www.nature.com/nbt/journal/v33/n5/full/nbt.3207.html). *Nature Biotechnology*. 33, 531–537. 2015
  - **UTX-JGI-Interim-release_v1.1**: 
    - Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].
    - Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .
    - Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.
    - Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.

  - **HAU_v1 / v1.1**: Wang *et al.* [Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense.](https://www.nature.com/articles/s41588-018-0282-x) *Nature genetics*. 2018 Dec 03
  - **ZJU-improved_v2.1_a1**: Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. *Nature genetics*. 2019 Jan;51(1):164.
  - **CRI_v1**: [Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.](https://www.cottongen.org/bio_data/16035)
  - **WHU_v1**: Huang, G. *et al*., Genome sequence of *Gossypium herbaceum* and genome updates of *Gossypium arboreum* and *Gossypium hirsutum* provide insights into cotton A-genome evolution. Nature Genetics. 2020. [doi.org/10.1038/s41588-020-0607-4](https://doi.org/10.1038/s41588-020-0607-4)
  - **UTX_v2.1**: [Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.](https://www.cottongen.org/bio_data/13714)
  - **HAU_v2.0**: Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. "[High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres](https://www.cottongen.org/bio_data/9803222)." Plant Communications 5, no. 2 (2024). [doi.org/10.1016/j.xplc.2023.100722](https://doi.org/10.1016/j.xplc.2023.100722)




> **免责声明**：上述基因组的数据下载与处理均由用户执行，本工具仅进行框架服务。

------

## 反馈与交流

如有任何建议、问题或合作意向，欢迎通过 **[GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues)** 与我们联系。我们非常欢迎同行的批评指正，共同建设一个更好的开源工具生态！
