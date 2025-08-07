<div align="center"> <img src="../ui/assets/logo.png" alt="logo" width="128" height="128" /> <h1 style="font-weight:700; letter-spacing:1px; margin-bottom:0;"> 友好棉花基因組工具包 (FCGT) </h1> <p> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases"><img alt="Version" src="https://img.shields.io/github/v/release/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge&logo=github"></a> <a href="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/LICENSE"><img alt="License" src="https://img.shields.io/github/license/PureAmaya/Friendly-Cotton-Genomes-Toolkit?style=for-the-badge"></a> </p> </div>

## 選擇你的語言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md) | [English](README_en.md) | [日本語](README_ja.md) | [繁體中文](README_zh-hant.md)

## 🚀 專案簡介

**FCGT (Friendly Cotton Genomes Toolkit)** 是一款專為棉花研究者，尤其是**非生物資訊專業背景**的科研人員和學生設計的基因組資料分析工具箱。我們致力於將複雜的資料處理流程封裝在簡潔的圖形化介面（GUI）和命令列（CLI）背後，讓您無需進行繁瑣的環境設定和程式碼編寫，即可**開箱即用**。

本工具包提供了一系列強大的棉花基因組資料處理工具，包括多版本間的同源基因映射（Liftover）、基因功能註釋、基因位點查詢、富集分析、AI 助手批次處理資料等。它旨在成為您日常科研工作中不可或缺的、**穩定可靠**的得力助手。

## ✨ 核心亮點與功能

### 1. 極致友好，開箱即用

- **資料安全**：除資料下載、AI 功能和更新檢測外，全程無需聯網，防止資料洩露。原始碼開源，接受社群檢查。
- **圖形化介面優先**：所有核心工具均可透過直觀的圖形化介面完成，滑鼠點擊即可執行分析。
- **互動式任務回饋**：**所有耗時操作（如資料下載、AI 處理）均配有即時進度條彈窗，您可以隨時取消任務。任務結束後會收到清晰的成功、失敗或取消提示，徹底告別盲目等待。**
- **流暢的操作體驗**：**經過精心優化的 UI 邏輯，確保了介面切換的即時回應和**全頁面順滑的滑鼠滾輪滾動**，體驗媲美原生桌面應用。**
- **多語言支援**：內建簡/繁中文、英文、日文介面，打破語言壁壘。

### 2. 高效的自動化與批次處理

- **強大的並行與任務管理**：內建多執行緒加速，無論是下載海量基因組資料，還是使用 AI 助手批次處理上千行表格，都能顯著縮短等待時間。互動式的進度彈窗讓您對任務狀態瞭若指掌，並能隨時取消。
- **智慧設定同步**：在設定編輯器中所做的修改（如更換 AI 模型）會即時同步到所有功能頁面，無需重新啟動或手動重新整理，所見即所得。
- **命令列支援**：對於進階使用者，我們同樣提供功能完善的命令列工具，方便您將 FCGT 整合到自動化分析流程中。

### 3. 精準的基因組工具集

- **棉花版 Liftover**：解決了棉花領域長期缺乏在不同基因組版本間進行基因列表轉換工具的難題。
- **一站式資料工具**：集合了基因註釋、GFF 查詢、富集分析、格式轉換等多種常用功能，無需在多個軟體間來回切換。
- **標準化資料下載**：一鍵下載來自 [CottonGen](https://www.cottongen.org/) 等權威資料庫的主流棉花參考基因組及註釋檔案。

### 4. 跨平台，隨處可用

- 我們為 **Windows** 使用者都提供了預先編譯的可執行檔（其他系統的使用者可以執行 Python 執行）。
- 無論您使用何種主流作業系統，都能獲得一致、流暢的使用體驗。

## 快速入門

我們已在 [**發布頁面 (Releases)**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases) 為您準備了開箱即用的可執行檔，這是最推薦的使用方式。

- **圖形化介面版**：下載 `FCGT-GUI.exe` (Windows) 或對應您系統的檔案，直接雙擊執行。
- **命令列工具**：下載 `FCGT.exe` (Windows) 或對應您系統的檔案，在終端機中執行。

**開發者與進階使用者**也可以從原始碼啟動：

```
# 執行圖形化介面
python gui_app.py

# 查看命令列說明
python -m cotton_toolkit.cli --help

# 打包程序/打包程式/Packaging program/パッケージングプログラム
python -m nuitka --standalone --mingw64 --windows-disable-console --windows-icon-from-ico=ui/assets/logo.ico --plugin-enable=tk-inter --plugin-enable=anti-bloat --lto=yes --include-data-dir=ui/assets=ui/assets --include-package-data=ttkbootstrap --output-dir=dist main.py
```

## 截圖預覽

<img src="../assets/主界面.png" style="zoom:50%;" />

<img src="../assets\配置编辑器.png" style="zoom:50%;" />

<img src="../assets\数据工具.png" style="zoom:50%;" />

## 致謝與引用

### 開發與致謝

- **特別感謝**: 本專案的開發得到了**開源社群**和所有為棉花研究做出貢獻的**科研工作者**的支援。

### 版權與授權

本工具的開發使用了以下優秀的開源軟體套件，感謝它們的開發者：

| **函式庫**              | **主要用途**                                                 | **開源授權**                                       |
| ----------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| **pydantic**            | 用於資料驗證、設定管理和型別提示強制，是專案中設定模型的核心。 | MIT License                                        |
| **typing-extensions**   | 為標準 `typing` 模組提供新的或實驗性的型別提示支援。         | Python Software Foundation License                 |
| **packaging**           | 用於處理 Python 套件的版本、標記和規範。                     | Apache-2.0 / BSD                                   |
| **requests**            | 一個優雅、簡潔的HTTP函式庫，用於執行網路請求，如下載資料。   | Apache-2.0 License                                 |
| **tqdm**                | 一個快速、可擴展的進度條工具，用於在命令列和迴圈中顯示進度。 | MIT License                                        |
| **gffutils**            | 用於建立、管理和查詢GFF/GTF檔案資料庫，是基因組註釋操作的基礎。 | MIT License                                        |
| **pandas**              | 提供高效能、易於使用的資料結構和資料分析工具，是所有資料處理的核心。 | BSD 3-Clause License                               |
| **pyyaml**              | 用於解析YAML檔案，是載入 `config.yml` 設定檔的關鍵。         | MIT License                                        |
| **google-generativeai** | Google 的官方函式庫，用於與 Gemini 等生成式AI模型進行互動。  | Apache-2.0 License                                 |
| **numpy**               | Python科學計算的基礎套件，為Pandas等函式庫提供多維陣列物件和數學運算支援。 | BSD 3-Clause License                               |
| **customtkinter**       | 用於建構現代化、美觀的圖形化使用者介面（GUI）。              | MIT License                                        |
| **pillow**              | Pillow (PIL Fork) 是一個強大的影像處理函式庫，用於在GUI中載入和顯示圖示等圖片。 | Historical Permission Notice and Disclaimer (HPND) |
| **diskcache**           | 提供基於磁碟的快取功能，用於儲存臨時或可重複使用的資料，以提高效能。 | Apache-2.0 License                                 |
| **click**               | 用於以組合式的方式建立漂亮的命令列介面（CLI）。              | BSD 3-Clause License                               |
| **matplotlib**          | 一個全面的函式庫，用於在Python中建立靜態、動畫和互動式的視覺化圖表。 | matplotlib License (BSD-style)                     |
| **statsmodels**         | 提供用於估計多種統計模型、進行統計檢驗和資料探索的類別和函式。 | BSD 3-Clause License                               |
| **protobuf**            | Google 的資料交換格式，通常被其他函式庫（如TensorFlow或某些API客戶端）所依賴。 | BSD 3-Clause License                               |
| **openpyxl**            | 用於讀取和寫入 Excel 2010 xlsx/xlsm/xltx/xltm 檔案的函式庫。 | MIT License                                        |
| **networkx**            | 用於建立、操作和研究複雜網路的結構、動態和功能的Python套件。 | BSD 3-Clause License                               |
| **upsetplot**           | 用於生成UpSet圖，這是一種用於視覺化集合交集資料的有效方法。  | BSD 3-Clause License                               |

### 資料來源與引文

本工具依賴 [CottonGen](https://www.cottongen.org/) 提供的權威資料，感謝其團隊持續的開放和維護。

- **CottonGen 文章**:
  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 10(12), 2805.
  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.
- **基因組引用文獻**:
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

> **免責聲明**：上述基因組的資料下載與處理均由使用者執行，本工具僅進行框架服務。

## 回饋與交流

如有任何建議、問題或合作意向，歡迎透過 [**GitHub Issues**](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues) 與我們聯絡。我們非常歡迎同行的批評指正，共同建設一個更好的開源工具生態！