<div align="center">
  <img src="../ui/assets/logo.png" alt="logo" width="128" height="128" />
  <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;">
    Friendly Cotton Genomes Toolkit (FCGT)
  </h1>
  <p>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a>
    <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a>
  </p>
</div>



## Change language



 [简体中文](../README.md) 

------



## 🚀 Project Introduction



**FCGT (Friendly Cotton Genomes Toolkit)** is a genomic data analysis toolbox designed specifically for cotton researchers, especially for scientists and students with a **non-bioinformatics background**. We are dedicated to encapsulating complex data processing workflows behind a simple graphical user interface (GUI), allowing you to use it **out-of-the-box** without tedious environment configuration and coding.

This toolkit provides a series of powerful tools for cotton genome data processing, including homologous gene mapping between different versions (Liftover), gene function annotation, gene locus query, enrichment analysis, BLAST, and batch data processing with an AI assistant. It aims to be an indispensable, **stable, and reliable** assistant in your daily research work.

------



## ⚠️ Important Notice: Regarding Gene and Transcript IDs



1. Under normal circumstances, this program supports both gene (e.g., Gohir.A12G149800) and transcript (e.g., Gohir.A12G149800.2) formats as input. However, in some cases, one type of input may not work correctly. Please refer to the following points for details.
2. If a gene ID is input and the data is stored in transcript format, the gene ID will be converted to its default first transcript (e.g., Gohir.A12G149800.1) for the search. If the data itself is stored in gene format, the search will proceed normally.
3. Conversely, if a transcript ID is input and the data is stored in gene format, the transcript suffix (e.g., .1, .2) will be removed, and the program will use the gene ID (e.g., Gohir.A12G149800) for the search. If the data itself is stored in transcript format, the search will proceed normally.
4. In summary, for scenarios requiring high-precision data, it is recommended to use transcript IDs as input and try searching for multiple different transcripts instead of just the first one.

------



## ✨ Core Highlights and Features

### 1. Extremely Friendly, Out-of-the-Box

- **Data Security**: Except for data download and AI functions, the entire process can be done offline to prevent data leakage. The source code is open and subject to community review.
- **GUI First**: All core tools can be operated through an intuitive graphical interface; analyses can be run with mouse clicks.
- **Interactive Task Feedback**: All time-consuming operations (like data download, AI processing) are equipped with real-time progress bar pop-ups, and you can cancel the task at any time. After the task is finished, you will receive a clear success, failure, or cancellation prompt, completely eliminating blind waiting.
- **Multi-language Support**: Built-in support for Simplified Chinese and English, breaking down language barriers.

### 2. Efficient Automation and Batch Processing

- **Powerful Concurrency and Task Management**: Built-in multi-threading acceleration significantly reduces waiting time, whether it's downloading massive genome data or processing thousands of table rows with the AI assistant. Interactive progress pop-ups keep you informed of the task status and allow for cancellation at any time.
- **Smart Configuration Sync**: Modifications made in the configuration editor (like changing the AI model) are synchronized to all function pages in real-time without needing a restart or manual refresh—what you see is what you get.
- **Batch Processing of Gene Data**: Solves the problem of some websites or tools that can only process single gene queries, allowing for high-accuracy batch processing.

### 3. Convenient Genome Toolkit

- **Automatic Genome Recognition**: A built-in automatic genome recognition function executes corresponding tasks without the need to manually select the genome.
- **Extensibility**: Uses `genome_sources_list.yml` to store cotton genome information, making it easy for users to add, remove, or adjust download addresses.
- **Genome Conversion**: Quickly batch convert between different cotton genomes via BLAST. Also supports conversion to and from Arabidopsis.
- **Standardized Data Download**: One-click download of mainstream cotton reference genomes and annotation files from the authoritative  database.
- **Convenient BLAST+**: Perform BLAST operations without an internet connection.
- **Batch Functional Annotation**: Perform GO, KEGG, and IPR annotation for a large number of genes in batches.
- **Enrichment Analysis Plotting**: Quickly generate bubble charts, bar charts, cnet plots, and upset plots. It also provides R scripts and data for users to customize the graphics.
- **Locus Conversion**: Convert genes within a genomic locus region from one genome to another specified cotton genome.
- **GFF Query**: Batch query GFF annotation information for genes.
- **CDS Sequence Extraction**: Input gene (or transcript) IDs to query their coding sequence information, supporting both single gene and multiple gene batch queries.
- **AI Batch Processing**: Use AI to batch process a specific column in a CSV table (e.g., interpreting the biological function of the content in that column) for rapid pre-processing in research.

### 4. Cross-platform, Usable Anywhere

- We provide pre-compiled executable files for **Windows** users (users on other systems can run the Python script or compile it themselves).
- You will get a consistent user experience regardless of which mainstream operating system you use.

------

## Quick Start



We have prepared out-of-the-box executable files for you on the , which is the most recommended way to use the software.

- **GUI Version**: Download and install `fcgt-setup.exe` (Windows). After installation, open and run it.

**Developers and advanced users** can also start from the source code:



```bash
# Running a graphical interface
pixi run start

# Compile this program (Nuitka)
pixi run build
```


## Screenshots Preview



<img src="../assets/主界面.png" style="zoom:50%;" />

<img src="../assets\配置编辑器.png" style="zoom:50%;" />

<img src="../assets\数据下载.png" style="zoom:50%;" />

<img src="../assets\功能注释.png"  style="zoom:50%;"/>

<img src="../assets\富集分析.png"  style="zoom:50%;"/>

<img src="../assets\序列提取.png"  style="zoom:50%;"/>

<img src="../assets\组类识别.png"  style="zoom:50%;"/>

<img src="../assets\同源转换.png"  style="zoom:50%;"/>

<img src="../assets\拟南芥互转.png"  style="zoom:50%;"/>

<img src="../assets\位点转换.png"  style="zoom:50%;"/>

<img src="../assets\GFF查询.png"  style="zoom:50%;"/>

<img src="../assets\本地BLAST.png"  style="zoom:50%;"/>

<img src="../assets\AI辅助.png"  style="zoom:50%;"/>

------

## Acknowledgments and Citations



### Development and Acknowledgments

- **Special Thanks**: The development of this project has been supported by the **open-source community** and all the **researchers** who have contributed to cotton research.

### Copyright and Licensing

The development of this tool uses the following excellent open-source software packages. Thanks to their developers:

- Application Body

| **Library**  | **Main Purpose**                                      | **Open Source License**                                      |
| ------------ | ----------------------------------------------------- | ------------------------------------------------------------ |
| babel        | Internationalization tool                             | BSD License (BSD-3-Clause)                                   |
| biopython    | Biological processing                                 | Freely Distributable                                         |
| click        | For creating command-line tools                       | BSD-3-Clause                                                 |
| diskcache    | Cache AI responses to disk                            | Apache 2.0                                                   |
| gffutils     | Handle GFF database creation tasks                    | MIT License                                                  |
| matplotlib   | Chart plotting                                        | Python Software Foundation License (License agreement for matplotlib versions 1.3.0 and later) |
| networkx     | Interaction graph plotting                            | BSD License                                                  |
| numpy        | Fast data computation                                 | BSD License (Copyright (c) 2005-2025)                        |
| openpyxl     | Read/write excel                                      | MIT License                                                  |
| pandas       | excel data processing                                 | BSD 3-Clause License                                         |
| pillow       | GUI image processing                                  | MIT-CMU                                                      |
| protobuf     | Serialize data                                        | 3-Clause BSD License                                         |
| pydantic     | Maintain data structures                              | MIT                                                          |
| pyyaml       | Store config files and cotton data download addresses | MIT License                                                  |
| requests     | Network requests (data download and AI requests)      | Apache-2.0                                                   |
| scipy        | Advanced scientific computation                       | BSD License (Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers.) |
| statsmodels  | Statistical analysis and modeling                     | BSD License                                                  |
| ttkbootstrap | GUI                                                   | MIT License                                                  |
| tqdm         | Display task progress                                 | MIT License                                                  |
| upsetplot    | Upset plot drawing                                    | BSD License (BSD-3-Clause)                                   |

- PO Translator

| **Library** | **Main Purpose**                   | **Open Source License** |
| ----------- | ---------------------------------- | ----------------------- |
| openai      | Easily handle AI translation logic | Apache-2.0              |
| polib       | Read/write PO files                | MIT License             |
| tenacity    | Retry on translation failure       | Apache 2.0              |
| tqdm        | Display translation progress       | MIT License             |

### Data Sources and Citations

This tool relies on [CottonGen](https://www.cottongen.org/) authoritative data provided by . We thank their team for their continued openness and maintenance.

- **CottonGen Articles**:
  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **BLAST+ Article:**
  - Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. BLAST+: architecture and applications. BMC Bioinformatics. 2009 Dec 15;10:421. doi: 10.1186/1471-2105-10-421. PMID: 20003500; PMCID: PMC2803857.
- **Genome Reference Literature**:
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
  - **UTX_v3.1**: Chen et al. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement Nat Genet 20 April 2020.

---

## License and Disclaimer



This program is licensed under the `Apache-2.0` License.

> **Please Note**: Users are free to use, modify, and distribute the code, but no contributor (including the original author and their affiliated institution) provides any warranty and is not liable for any issues arising from the use of this software.

> **Disclaimer**: 
>
> **Tool's Role:** This software provides framework services only. It does not host or distribute any genomic data.
>
> **User's Responsibility:** The download, processing, and analysis of all genomic data are executed solely by the user. Users are responsible for ensuring they comply with all licenses, terms of use, and publication restrictions set by the original data providers.
>
> **No Warranty:** This tool and its generated results are provided "as is" for research purposes only, without any warranty of accuracy or fitness for a particular purpose.Feedback and Communication



If you have any suggestions, questions, or collaboration inquiries, feel free to contact us via **[GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues)**. We welcome criticism and suggestions from peers to jointly build a better open-source tool ecosystem!