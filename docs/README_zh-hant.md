<table>
  <tr>
    <td width="120" align="center" valign="middle">
      <img src="ico.png" alt="logo" width="128" height="128" style="object-fit:cover;" />
    </td>
    <td valign="middle">
      <h1 style="font-weight:700; letter-spacing:2px; margin-bottom:0;">
        友好棉花基因組工具包 <br>
        <span style="font-size:1.1em;">(Friendly Cotton Genomes Toolkit, FCGT)</span>
      </h1>
      <p style="font-size:1.1em; margin-top:0.5em;">
        <b>由 Gemini AI 協助開發 · 開源學術專案 · 歡迎同業批評指正</b>
      </p>
    </td>
  </tr>
</table>


## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md)	[English](README_en.md)	[日本語](README_ja.md)	 [繁體中文](README_zh-hant.md)

---

## 專案簡介

**FCGT**（Friendly Cotton Genomes Toolkit）為棉花基因組數據分析提供專業、易用的工具支援，涵蓋圖形界面（GUI）與命令列（CLI）模式，注重降低生物資訊學門檻，助力科研與育種實踐。  
本工具包聚焦於功能缺失基因篩選、同源性映射與整合分析，解決了目前棉花領域缺乏類似 Liftover 工具與數據的痛點。  
FCGT 的 Liftover 實現理念不同於傳統通用工具，更加貼合棉花及相關作物的實際需求。

---

## 主要功能特色

- **標準化數據下載**  
  自動連接 CottonGen 等權威資料庫，快速獲取主流棉花基因組及註釋數據。
- **同源映射與優先級篩選**  
  支援多參數自訂，基於 BLAST 等結果，實現精準同源基因篩選與排序。
- **功能缺失基因整合分析**  
  融合多組學表格、註釋與同源性資訊，輔助複雜遺傳分析。
- **靈活配置與批次處理**  
  支援 YAML 配置，便於大規模自動化與團隊協作。
- **多語言友好介面**  
  預設繁體中文，CLI/GUI 可自由切換，適合不同背景用戶。
- **全流程新手友好**  
  零基礎可用，配套詳細文件，支援圖形與命令列雙操作。

---

## 學術定位與創新

- **新手友好，專業可擴展**  
  科研人員與學生均可輕鬆上手，且便於自訂與二次開發。
- **填補業界空白**  
  棉花領域長期缺乏 Liftover 等基因組映射工具，FCGT 致力於推動學科進步。
- **嚴謹可複用**  
  所有流程與參數均可溯源，有利於成果重現與共享。

---

## 數據來源與學術致謝

本專案高度依賴 [CottonGen](https://www.cottongen.org/) 提供的權威數據，感謝其團隊持續的開放與維護。

**參考文獻：**

- Yu, J, Jung S, Cheng CH, Lee T, Zheng P, Buble K, Crabb J, Humann J, Hough H, Jones D, Campbell JT, Udall J, Main D (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 2021, 10(12), 2805.
- Yu J, Jung S, Cheng CH, Ficklin SP, Lee T, Zheng P, Jones D, Percy R, Main D (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.

同時，向所有為棉花基因組定序、組裝、註釋與功能研究做出貢獻的科研同仁致以崇高敬意！

> **注意：本工具會自動從網路下載所需數據，專案本體不包含任何第三方資料庫內容。**

---

## 快速入門

我們在[發布頁面](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases)提供開箱即用的可執行檔案：  
無需 Python 環境，下載後直接運行即可：

- **圖形介面版**：`FCGT-GUI.exe`
- **命令列工具**：`FCGT.exe`

適用於絕大多數用戶。

**進階用戶與開發者**可通過原始碼啟動：

```bash
# 圖形介面
python gui_app.py

# 命令列
python -m cotton_toolkit.cli --help
```

所有配置與數據源檔案均採用 YAML 格式，詳見說明文件。

---

## 反饋與學術交流

如有建議、問題或合作意向，歡迎通過 [GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues) 聯絡。  
歡迎同業批評指正，共建開源生態！

---

<p align="center" style="color:#888;">
  <i>由 Gemini AI 協助開發，功能持續迭代。學術交流為本，程式嚴謹為先。</i>
</p>