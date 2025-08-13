<div align="center"> <img src="../ui/assets/logo.png" alt="logo" width="128" height="128" /> <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;"> Friendly Cotton Genomes Toolkit (FCGT) </h1> <p> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a> </p> </div>

## 替换语言

[中文（简体）版本](../README.md)

## 🚀 Project Introduction

**FCGT (Friendly Cotton Genomes Toolkit)** is a genomic data analysis toolbox designed specifically for cotton researchers, especially for scientists and students with a **non-bioinformatics background**. We are committed to encapsulating complex data processing workflows behind a simple graphical user interface (GUI), allowing you to use it **out-of-the-box** without tedious environment configuration and coding.

This toolkit provides a series of powerful tools for cotton genome data processing, including homologous gene mapping between different versions (Liftover), gene function annotation, gene locus query, enrichment analysis, and batch data processing with an AI assistant. It aims to be an indispensable, **stable, and reliable** assistant in your daily research work.

## ✨ Core Highlights & Features

### 1. Extremely Friendly, Out-of-the-Box

- **Data Security**: Except for data download and AI functions, the entire process can be done offline to prevent data leakage. The source code is open and subject to community review.
- **GUI First**: All core tools can be operated through an intuitive graphical interface, running analyses with just a mouse click.
- **Interactive Task Feedback**: All time-consuming operations (like data download, AI processing) come with a real-time progress bar pop-up, and you can cancel the task at any time. After the task is completed, you will receive clear success, failure, or cancellation prompts, completely eliminating blind waiting.
- **Multi-language Support**: Built-in support for Simplified Chinese and English, breaking down language barriers.

### 2. Efficient Automation & Batch Processing

- **Powerful Concurrency & Task Management**: Built-in multi-threading acceleration significantly shortens waiting times, whether for downloading massive genome data or batch processing thousands of table rows with the AI assistant. The interactive progress pop-up keeps you informed of the task status and allows for cancellation at any time.
- **Smart Configuration Sync**: Modifications made in the configuration editor (like changing the AI model) are synchronized in real-time across all function pages without needing a restart or manual refresh. What you see is what you get.

### 3. Convenient Genome Toolkit

- **Cotton Liftover**: Solves the long-standing problem in the cotton field of lacking a tool for converting gene lists between different genome versions.
- **One-stop Data Tools**: Integrates various common functions such as gene annotation, GFF query, enrichment analysis, and format conversion, eliminating the need to switch between multiple software.
- **Standardized Data Download**: One-click download of mainstream cotton reference genomes and annotation files from the authoritative [CottonGen](https://www.cottongen.org/) database.

### 4. Cross-platform, Use Anywhere

- We provide pre-compiled executable files for **Windows** users (users on other systems can run it via Python).
- You will get a consistent and smooth user experience regardless of which mainstream operating system you use.

## Quick Start

We have prepared out-of-the-box executable files for you on the [**Releases page**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases), which is the most recommended way to use the toolkit.

- **GUI Version**: Download and install `fcgt-setup.exe` (Windows). After installation, open and run it.

**Developers and advanced users** can also start from the source code:

```
# Run the GUI
pixi run start

# Build the application
pixi run build
```

## Screenshot Preview

<img src="assets/主界面.png" alt="Main Interface" style="zoom:50%;" />

<img src="assets\配置编辑器.png" alt="Configuration Editor" style="zoom:50%;" />

<img src="assets\数据工具.png" alt="Data Tools" style="zoom:50%;" />

<img src="assets\中文功能.png" alt="Feature Showcase" style="zoom:50%;"/>

## Acknowledgments and Citations

### Development & Acknowledgments

- **Special Thanks**: The development of this project was supported by the **open-source community** and all **researchers** who have contributed to cotton research.

### Copyright & License

The development of this tool uses the following excellent open-source packages. Thanks to their developers:

- **Application Body**

| **Library**  | **Main Purpose**                                        | **Open Source License**                                      |
| ------------ | ------------------------------------------------------- | ------------------------------------------------------------ |
| babel        | Internationalization tool                               | BSD License (BSD-3-Clause)                                   |
| biopython    | Biological processing                                   | Freely Distributable                                         |
| click        | For creating command-line tools                         | BSD-3-Clause                                                 |
| diskcache    | Cache AI responses to disk                              | Apache 2.0                                                   |
| gffutils     | Process GFF database creation tasks                     | MIT License                                                  |
| matplotlib   | Chart plotting                                          | Python Software Foundation License (for versions 1.3.0 and later) |
| networkx     | Interaction graph plotting                              | BSD License                                                  |
| numpy        | Fast data computation                                   | BSD License (Copyright (c) 2005-2025)                        |
| openpyxl     | Read/write Excel                                        | MIT License                                                  |
| pandas       | Excel data processing                                   | BSD 3-Clause License                                         |
| pillow       | GUI image processing                                    | MIT-CMU                                                      |
| protobuf     | Serialize data                                          | 3-Clause BSD License                                         |
| pydantic     | Maintain data structures                                | MIT                                                          |
| pyyaml       | Store configuration files and cotton data download URLs | MIT License                                                  |
| requests     | Network requests (data download and AI requests)        | Apache-2.0                                                   |
| scipy        | Advanced scientific computing                           | BSD License (Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers.) |
| statsmodels  | Statistical analysis and modeling                       | BSD License                                                  |
| ttkbootstrap | GUI                                                     | MIT License                                                  |
| tqdm         | Display task progress                                   | MIT License                                                  |
| upsetplot    | Upset plot drawing                                      | BSD License (BSD-3-Clause)                                   |

- **PO Translator**

| **Library** | **Main Purpose**                   | **Open Source License** |
| ----------- | ---------------------------------- | ----------------------- |
| openai      | Easily handle AI translation logic | Apache-2.0              |
| polib       | Read/write .po files               | MIT License             |
| tenacity    | Retry on translation failure       | Apache 2.0              |
| tqdm        | Display translation progress       | MIT License             |

### Data Sources & Citations

This tool relies on authoritative data provided by [CottonGen](https://www.cottongen.org/), thanks to their team for their continued openness and maintenance.

- **CottonGen Articles**:
  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **BLAST+ Article:**
  - Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. BLAST+: architecture and applications. BMC Bioinformatics. 2009 Dec 15;10:421. doi: 10.1186/1471-2105-10-421. PMID: 20003500; PMCID: PMC2803857.
- **Genome Citation Literature**:
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

> **Disclaimer**: The download and processing of the above genome data are performed by the user. This tool only provides the framework service.

## Feedback and Communication

If you have any suggestions, questions, or collaboration interests, please contact us via [**GitHub Issues**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues). We welcome criticism and corrections from our peers to build a better open-source tool ecosystem together!