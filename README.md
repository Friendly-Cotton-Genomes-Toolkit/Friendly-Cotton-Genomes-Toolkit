<div align="center">
  <img src="assets/logo.png" alt="logo" width="128" height="128" />
  <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;">
    友好棉花基因组工具包 (FCGT)
  </h1>
  <p>
    <strong>作者:</strong> PureAmaya
  </p>
  <p>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a>
  </p>
</div>


## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md) | [English](docs/README_en.md) | [日本語](docs/README_ja.md) | [繁體中文](docs/README_zh-hant.md)

---

## 🚀 项目简介

**FCGT (Friendly Cotton Genomes Toolkit)** 是一款专为棉花研究者，尤其是**非生物信息专业背景**的科研人员和学生设计的基因组数据分析工具。我们致力于将复杂的数据处理流程封装在简洁的图形界面（GUI）和命令行（CLI）背后，让您无需进行繁琐的环境配置和代码编写，即可**开箱即用**。

本工具包聚焦于功能缺失基因筛选、多版本间的同源基因映射（Liftover）与多组学数据的整合分析，解决了目前棉花领域工具链不完善、操作门槛高的痛点。

---

## ✨ 核心亮点与功能

### 1. 极致友好，开箱即用
* **图形界面优先**: 所有核心功能均可通过直观的图形界面完成，鼠标点击即可运行分析。
* **无需复杂配置**: 下载后直接运行，无需安装Python或处理复杂的依赖关系。
* **多语言支持**: 内置简/繁中文、英文、日文界面，打破语言壁垒。
* **核心功能离线运行**: 除首次数据下载和AI助手功能外，所有核心分析均可在本地离线完成，确保您的数据安全。

### 2. 高效的自动化与批量处理
* **多线程加速**: 内置多线程支持，无论是下载海量基因组数据，还是使用AI助手批量翻译、分析上千行表格，都能显著缩短等待时间。
* **命令行支持**: 对于高级用户，我们同样提供功能完善的命令行工具，方便您将FCGT整合到自动化分析流程中。

### 3. 精准的同源映射与整合分析
* **棉花版 Liftover**: 解决了棉花领域长期缺乏在不同基因组版本间进行基因列表转换工具的难题。
* **一站式整合流程**: 可无缝整合BSA定位区间与高变异基因（HVG）数据，自动完成跨版本同源映射，快速筛选与性状关联的候选基因。
* **标准化数据下载**: 一键下载来自 [CottonGen](https://www.cottongen.org/) 等权威数据库的主流棉花参考基因组及注释文件。

### 4. 跨平台，随处可用
* 我们为 **Windows**, **macOS** 和 **Linux** 用户都提供了预编译的可执行文件。
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
```

------

## 截图预览

<img src="assets/主界面.png" style="zoom:50%;" />

<img src="D:\Python\cotton_tool\assets\配置编辑器.png" style="zoom:50%;" />

<img src="D:\Python\cotton_tool\assets\联合分析.png" style="zoom:50%;" />

<img src="D:\Python\cotton_tool\assets\数据工具.png" style="zoom:50%;" />

------

## 致谢与引用

### 开发与致谢

- **作者**: [PureAmaya](https://github.com/PureAmaya)
- **特别感谢**: 本项目的开发得到了**开源社区**和所有为棉花研究做出贡献的**科研工作者**的支持。

### 版权与许可

本工具的开发使用了以下优秀的开源软件包，感谢它们的开发者：

- requests (Apache-2.0 License)
- tqdm (MIT License)
- gffutils (MIT License)
- pandas (BSD 3-Clause License)
- PyYAML (MIT License)
- numpy (BSD License)
- pillow (MIT-CMU License)
- diskcache (Apache 2.0 License)
- openpyxl (MIT License)
- customtkinter (MIT License)

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




> **免责声明**：上述基因组的数据下载均由用2户执行，本工具仅进行通用的分析操作。

------

## 反馈与交流

如有任何建议、问题或合作意向，欢迎通过 **[GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues)** 与我们联系。我们非常欢迎同行的批评指正，共同建设一个更好的开源工具生态！
