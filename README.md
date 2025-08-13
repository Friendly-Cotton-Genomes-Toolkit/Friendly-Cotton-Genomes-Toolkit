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



## Change language

 [English](docs/README_en.md) 

---

## 🚀 项目简介

**FCGT (Friendly Cotton Genomes Toolkit)** 是一款专为棉花研究者，尤其是**非生物信息专业背景**的科研人员和学生设计的基因组数据分析工具箱。我们致力于将复杂的数据处理流程封装在简洁的图形界面（GUI）背后，让您无需进行繁琐的环境配置和代码编写，即可**开箱即用**。

本工具包提供了一系列强大的棉花基因组数据处理工具，包括多版本间的同源基因映射（Liftover）、基因功能注释、基因位点查询、富集分析、AI助手批量处理数据等。它旨在成为您日常科研工作中不可或缺的、**稳定可靠**的得力助手。

---

## ✨ 核心亮点与功能

### 1. 极致友好，开箱即用
* **数据安全**：除数据下载与AI功能外，全程无需联网，防止数据泄露。源码开源，接受社区检查。
* **图形界面优先**: 所有核心工具均可通过直观的图形界面完成，鼠标点击即可运行分析。
* **交互式任务反馈**: 所有耗时操作（如数据下载、AI处理）均配有实时进度条弹窗，您可以随时取消任务。任务结束后会收到清晰的成功、失败或取消提示，彻底告别盲目等待。
* **多语言支持**: 内置简体中文和英文，打破语言壁垒。

### 2. 高效的自动化与批量处理

* **强大的并发与任务管理**: 内置多线程加速，无论是下载海量基因组数据，还是使用AI助手批量处理上千行表格，都能显著缩短等待时间。交互式的进度弹窗让您对任务状态了如指掌，并能随时取消。
* **智能配置同步**: 在配置编辑器中做的修改（如更换AI模型）会实时同步到所有功能页面，无需重启或手动刷新，所见即所得。

### 3. 便捷的基因组工具集
* **棉花版 Liftover**: 解决了棉花领域长期缺乏在不同基因组版本间进行基因列表转换工具的难题。
* **一站式数据工具**: 集合了基因注释、GFF查询、富集分析、格式转换等多种常用功能，无需在多个软件间来回切换。
* **标准化数据下载**: 一键下载来自 [CottonGen](https://www.cottongen.org/) 权威数据库的主流棉花参考基因组及注释文件。

### 4. 跨平台，随处可用
* 我们为 **Windows** 用户都提供了预编译的可执行文件（其他系统的用户可以执行Python运行）。
* 无论您使用何种主流操作系统，都能获得一致、流畅的使用体验。

---

## 快速入门

我们已在 **[发布页面 (Releases)](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases)** 为您准备了开箱即用的可执行文件，这是最推荐的使用方式。

* **图形界面版**: 下载安装`fcgt-setup.exe` (Windows)，安装完成后打开运行即可 。

**开发者与高级用户**也可以从源码启动：
```bash
# 运行图形界面
pixi run start

# 打包程序
pixi run build
```

## 截图预览

<img src="assets/主界面.png" style="zoom:50%;" />

<img src="assets\配置编辑器.png" style="zoom:50%;" />

<img src="assets\数据工具.png" style="zoom:50%;" />

<img src="assets\中文功能.png"  style="zoom:50%;"/>

------

## 致谢与引用

### 开发与致谢

- **特别感谢**: 本项目的开发得到了**开源社区**和所有为棉花研究做出贡献的**科研工作者**的支持。

### 版权与许可

本工具的开发使用了以下优秀的开源软件包，感谢它们的开发者：

- 应用程序本体

| **库**       | **主要用途**                   | **开源许可证**                                               |
| ------------ | ------------------------------ | ------------------------------------------------------------ |
| babel        | 国际化工具                     | BSD License (BSD-3-Clause)                                   |
| biopython    | 生物学处理                     | Freely Distributable                                         |
| click        | 用于创建命令行工具             | BSD-3-Clause                                                 |
| diskcache    | AI回答记录缓存到硬盘中         | Apache 2.0                                                   |
| gffutils     | 处理GFF建库任务                | MIT License                                                  |
| matplotlib   | 图表绘制                       | Python Software Foundation License (License agreement for matplotlib versions 1.3.0 and later |
| networkx     | 互作图绘制                     | BSD License                                                  |
| numpy        | 快速数据计算                   | BSD License (Copyright (c) 2005-2025                         |
| openpyxl     | 读写excel                      | MIT License                                                  |
| pandas       | excel数据处理                  | BSD 3-Clause License                                         |
| pillow       | GUI图片处理                    | MIT-CMU                                                      |
| protobuf     | 序列化数据                     | 3-Clause BSD License                                         |
| pydantic     | 维护数据结构                   | MIT                                                          |
| pyyaml       | 储存配置文件和棉花数据下载地址 | MIT License                                                  |
| requests     | 网络请求（下载数据和AI请求）   | Apache-2.0                                                   |
| scipy        | 高级科学运算                   | BSD License (Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers.) |
| statsmodels  | 统计分析和建模                 | BSD License                                                  |
| ttkbootstrap | GUI                            | MIT License                                                  |
| tqdm         | 显示任务进度                   | MIT License                                                  |
| upsetplot    | Upset图绘制                    | BSD License (BSD-3-Clause)                                   |

- po翻译器

| **库**   | **主要用途**         | **开源许可证** |
| -------- | -------------------- | -------------- |
| openai   | 简易地处理AI翻译逻辑 | Apache-2.0     |
| polib    | 读写po文件           | MIT License    |
| tenacity | 翻译失败后重试       | Apache 2.0     |
| tqdm     | 翻译进度显示         | MIT License    |

### 数据来源与引文

本工具依赖 [CottonGen](https://www.cottongen.org/) 提供的权威数据，感谢其团队持续的开放和维护。

- **CottonGen 文章**:
  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **BLAST+ 文章:**
  - Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. BLAST+: architecture and applications. BMC Bioinformatics. 2009 Dec 15;10:421. doi: 10.1186/1471-2105-10-421. PMID: 20003500; PMCID: PMC2803857.

- **基因组引用文献**:
  - **NAU-NBI_v1.1**: Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. *Nature Biotechnology*. 33, 531–537. 2015
  - **UTX-JGI-Interim-release_v1.1**: 
    - Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].
    - Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .
    - Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.
    - Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.

  - **HAU_v1 / v1.1**: Wang *et al.* Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. *Nature genetics*. 2018 Dec 03
  - **ZJU-improved_v2.1_a1**: Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. *Nature genetics*. 2019 Jan;51(1):164.
  - **CRI_v1**: Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.
  - **WHU_v1**: Huang, G. *et al*., Genome sequence of *Gossypium herbaceum* and genome updates of *Gossypium arboreum* and *Gossypium hirsutum* provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4
  - **UTX_v2.1**: Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.
  - **HAU_v2.0**: Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. "High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres." Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722




> **免责声明**：上述基因组的数据下载与处理均由用户执行，本工具仅进行框架服务。

------

## 反馈与交流

如有任何建议、问题或合作意向，欢迎通过 **[GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues)** 与我们联系。我们非常欢迎同行的批评指正，共同建设一个更好的开源工具生态！
