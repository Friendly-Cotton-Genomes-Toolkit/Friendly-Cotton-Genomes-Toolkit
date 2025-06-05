<table>
  <tr>
    <td width="120" align="center" valign="middle">
     <img src="ico.png" alt="logo" width="128" height="128" style="object-fit:cover;" />
    </td>
    <td valign="middle">
      <h1 style="font-weight:700; letter-spacing:2px; margin-bottom:0;">
        Friendly Cotton Genomes Toolkit <br>
        <span style="font-size:1.1em;">(FCGT)</span>
      </h1>
      <p style="font-size:1.1em; margin-top:0.5em;">
        <b>Developed with assistance from Gemini AI · Open-source academic project · Peer review and suggestions are welcome</b>
      </p>
    </td>
  </tr>
</table>


## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md)	[English](README_en.md)	[日本語](README_ja.md)	 [繁體中文](README_zh-hant.md)

---

## Project Overview

**FCGT** (Friendly Cotton Genomes Toolkit) provides professional and user-friendly tools for cotton genome data analysis. It supports both graphical user interface (GUI) and command-line interface (CLI) modes, focusing on lowering the threshold of bioinformatics and empowering research and breeding practices.  
This toolkit focuses on the screening of loss-of-function genes, homology mapping, and integrative analysis, addressing the current lack of Liftover-like tools and data in cotton genomics.  
The Liftover implementation in FCGT differs from traditional generic tools and is more tailored to the practical needs of cotton and related crops.

---

## Key Features

- **Standardized Data Download**  
  Automatically connects to authoritative databases such as CottonGen to quickly obtain mainstream cotton genomes and annotation data.
- **Homology Mapping and Prioritization**  
  Supports multi-parameter customization, enabling precise screening and ranking of homologous genes based on BLAST and other results.
- **Loss-of-Function Gene Integrative Analysis**  
  Integrates multi-omics tables, annotations, and homology information to assist in complex genetic analyses.
- **Flexible Configuration and Batch Processing**  
  Supports YAML configuration for large-scale automation and team collaboration.
- **Multilingual Friendly Interface**  
  Simplified Chinese by default; CLI/GUI language can be freely switched, suitable for users from different backgrounds.
- **User-Friendly Full Workflow**  
  Usable with zero foundation, detailed documentation provided, supporting both graphical and command-line operations.

---

## Academic Positioning and Innovation

- **Beginner-Friendly, Professionally Extensible**  
  Both researchers and students can easily get started, and the toolkit is convenient for customization and secondary development.
- **Filling the Industry Gap**  
  The cotton field has long lacked Liftover and other genome mapping tools. FCGT is committed to advancing the discipline.
- **Rigorous and Reproducible**  
  All workflows and parameters are traceable, facilitating result reproducibility and sharing.

---

## Data Sources and Academic Acknowledgments

This project relies heavily on authoritative data provided by [CottonGen](https://www.cottongen.org/). We thank the CottonGen team for their ongoing openness and maintenance.

**References:**

- Yu, J, Jung S, Cheng CH, Lee T, Zheng P, Buble K, Crabb J, Humann J, Hough H, Jones D, Campbell JT, Udall J, Main D (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 2021, 10(12), 2805.
- Yu J, Jung S, Cheng CH, Ficklin SP, Lee T, Zheng P, Jones D, Percy R, Main D (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.

At the same time, we extend our highest respect to all researchers who have contributed to cotton genome sequencing, assembly, annotation, and functional studies!

> **Note: This toolkit automatically downloads the required data from the internet. The project itself does not include any third-party database content.**

---

## Getting Started

We provide ready-to-use executable files on the [Releases Page](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases):  
No Python environment required—just download and run:

- **GUI Version:** `FCGT-GUI.exe`
- **Command-line Tool:** `FCGT.exe`

Suitable for most users.

**Advanced users and developers** can start from source code:

```bash
# GUI
python gui_app.py

# Command line
python -m cotton_toolkit.cli --help
```

All configuration and data source files use the YAML format. See documentation for details.

---

## Feedback and Academic Exchange

For suggestions, issues, or collaboration opportunities, please contact us via [GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues).  
Peer review and contributions to the open-source ecosystem are welcome!

---

<p align="center" style="color:#888;">
  <i>Developed with assistance from Gemini AI. Continuous iteration for academic collaboration and code quality.</i>
</p>