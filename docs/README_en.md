
<div align="center"> <img src="../ui/assets/logo.png" alt="logo" width="128" height="128" /> <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;"> Friendly Cotton Genomes Toolkit (FCGT) </h1> <p> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a> </p> </div>

## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md) | [English](README_en.md) | [日本語](README_ja.md) | [繁體中文](README_zh-hant.md)

## 🚀 Introduction

**FCGT (Friendly Cotton Genomes Toolkit)** is a genomic data analysis toolkit designed specifically for cotton researchers, especially for scientists and students with a **non-bioinformatics background**. We are committed to encapsulating complex data processing workflows behind a simple graphical user interface (GUI) and command-line interface (CLI), allowing you to use it **out of the box** without tedious environment configuration and coding.

This toolkit provides a series of powerful tools for cotton genome data processing, including homologous gene mapping between different versions (Liftover), gene functional annotation, gene locus query, enrichment analysis, and batch data processing with an AI assistant. It aims to be an indispensable and **reliable** assistant in your daily research work.

## ✨ Core Highlights & Features

### 1. Extremely Friendly, Out of the Box

- **Data Security**: No internet connection is required except for data download, AI functions, and update checks, preventing data leakage. The source code is open and subject to community review.
- **GUI First**: All core tools can be operated through an intuitive graphical interface with simple mouse clicks.
- **Interactive Task Feedback**: **All time-consuming operations (like data download, AI processing) have real-time progress bar pop-ups, and you can cancel the task at any time. After the task is completed, you will receive clear success, failure, or cancellation prompts, completely eliminating blind waiting.**
- **Smooth User Experience**: Carefully optimized UI logic ensures instant response for interface switching and **smooth mouse wheel scrolling across all pages**, providing an experience comparable to native desktop applications.
- **Multi-language Support**: Built-in support for Simplified/Traditional Chinese, English, and Japanese interfaces, breaking down language barriers.

### 2. Efficient Automation & Batch Processing

- **Powerful Concurrency & Task Management**: Built-in multi-threading acceleration significantly reduces waiting time, whether you are downloading massive genome data or processing thousands of rows in a table with the AI assistant. Interactive progress pop-ups keep you informed of the task status and allow you to cancel at any time.
- **Smart Configuration Sync**: Changes made in the configuration editor (such as switching AI models) are synchronized to all function pages in real-time without restarting or manual refreshing—what you see is what you get.
- **Command-Line Support**: For advanced users, we also provide a full-featured command-line tool, making it easy to integrate FCGT into your automated analysis pipelines.

### 3. Precise Genomics Toolset

- **Cotton Liftover**: Solves the long-standing problem in the cotton research field of lacking a tool for converting gene lists between different genome versions.
- **All-in-One Data Tools**: Integrates various common functions such as gene annotation, GFF query, enrichment analysis, and format conversion, eliminating the need to switch between multiple software.
- **Standardized Data Download**: One-click download of mainstream cotton reference genomes and annotation files from authoritative databases like [CottonGen](https://www.cottongen.org/).

### 4. Cross-Platform, Available Everywhere

- We provide pre-compiled executables for **Windows** users (users on other systems can run it from Python).
- You will get a consistent and smooth user experience regardless of which mainstream operating system you use.

## Quick Start

We have prepared out-of-the-box executables for you on the [**Releases**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases) page, which is the most recommended way to use the toolkit.

- **GUI Version**: Download `FCGT-GUI.exe` (Windows) or the corresponding file for your system and run it by double-clicking.
- **Command-Line Tool**: Download `FCGT.exe` (Windows) or the corresponding file for your system and run it in the terminal.

**Developers and advanced users** can also start from the source code:

```
# Run the GUI
python gui_app.py

# View command-line help
python -m cotton_toolkit.cli --help

# 打包程序/打包程式/Packaging program/パッケージングプログラム
python -m nuitka --standalone --mingw64 --windows-disable-console --windows-icon-from-ico=ui/assets/logo.ico --plugin-enable=tk-inter --plugin-enable=anti-bloat --lto=yes --include-data-dir=ui/assets=ui/assets --include-package-data=ttkbootstrap --output-dir=dist main.py
```

## Screenshot Preview

<img src="../assets/主界面.png" style="zoom:50%;" />

<img src="../assets\配置编辑器.png" style="zoom:50%;" />

<img src="../assets\数据工具.png" style="zoom:50%;" />

## Acknowledgements & Citations

### Development & Acknowledgements

- **Special Thanks**: The development of this project is supported by the **open-source community** and all the **researchers** who have contributed to cotton science.

### Copyright & Licenses

The development of this tool uses the following excellent open-source packages. Thanks to their developers:

| **Library**             | **Main Purpose**                                             | **License**                                        |
| ----------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| **pydantic**            | Used for data validation, settings management, and type hint enforcement; core of the project's configuration models. | MIT License                                        |
| **typing-extensions**   | Provides new or experimental type hint support for the standard `typing` module. | Python Software Foundation License                 |
| **packaging**           | Used for handling Python package versions, markers, and specifications. | Apache-2.0 / BSD                                   |
| **requests**            | An elegant and simple HTTP library for making network requests, such as downloading data. | Apache-2.0 License                                 |
| **tqdm**                | A fast, extensible progress bar tool for displaying progress in command lines and loops. | MIT License                                        |
| **gffutils**            | Used for creating, managing, and querying GFF/GTF file databases; the foundation for genome annotation operations. | MIT License                                        |
| **pandas**              | Provides high-performance, easy-to-use data structures and data analysis tools; the core of all data processing. | BSD 3-Clause License                               |
| **pyyaml**              | Used for parsing YAML files, crucial for loading the `config.yml` configuration file. | MIT License                                        |
| **google-generativeai** | Google's official library for interacting with generative AI models like Gemini. | Apache-2.0 License                                 |
| **numpy**               | The fundamental package for scientific computing in Python, providing multi-dimensional array objects and mathematical operations for libraries like Pandas. | BSD 3-Clause License                               |
| **customtkinter**       | Used for building modern and beautiful graphical user interfaces (GUIs). | MIT License                                        |
| **pillow**              | Pillow (PIL Fork) is a powerful image processing library used for loading and displaying images like icons in the GUI. | Historical Permission Notice and Disclaimer (HPND) |
| **diskcache**           | Provides disk-based caching to store temporary or reusable data to improve performance. | Apache-2.0 License                                 |
| **click**               | Used for creating beautiful command-line interfaces (CLIs) in a composable way. | BSD 3-Clause License                               |
| **matplotlib**          | A comprehensive library for creating static, animated, and interactive visualizations in Python. | matplotlib License (BSD-style)                     |
| **statsmodels**         | Provides classes and functions for the estimation of many different statistical models, as well as for conducting statistical tests and data exploration. | BSD 3-Clause License                               |
| **protobuf**            | Google's data interchange format, often depended upon by other libraries (like TensorFlow or some API clients). | BSD 3-Clause License                               |
| **openpyxl**            | A library to read/write Excel 2010 xlsx/xlsm/xltx/xltm files. | MIT License                                        |
| **networkx**            | A Python package for the creation, manipulation, and study of the structure, dynamics, and functions of complex networks. | BSD 3-Clause License                               |
| **upsetplot**           | For generating UpSet plots, an effective method for visualizing set intersection data. | BSD 3-Clause License                               |

### Data Sources & Citations

This tool relies on authoritative data provided by [CottonGen](https://www.cottongen.org/). We thank their team for their continued openness and maintenance.

- **CottonGen Articles**:
  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **Genome Citations**:
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

> **Disclaimer**: The downloading and processing of the above genome data are performed by the user. This tool only provides the framework service.

## Feedback & Communication

If you have any suggestions, questions, or collaboration inquiries, please feel free to contact us via [**GitHub Issues**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues). We welcome criticism and suggestions from peers to jointly build a better open-source tool ecosystem!

eloped with assistance from Gemini AI. Continuous iteration for academic collaboration and code quality.