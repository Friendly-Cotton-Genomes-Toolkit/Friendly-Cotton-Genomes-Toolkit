
<table>
  <tr>
    <td width="120" align="center" valign="middle">
     <img src="../ui/assets/logo.png" alt="logo" width="128" height="128" style="object-fit:cover;" />
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

## 🚀 專案簡介

**FCGT (Friendly Cotton Genomes Toolkit)** 是一款專為棉花研究者，尤其是**非生物資訊專業背景**的科研人員和學生設計的基因組資料分析工具箱。我們致力於將複雜的資料處理流程封裝在簡潔的圖形介面（GUI）和命令列介面（CLI）背後，讓您無需進行繁瑣的環境設定和程式碼編寫，即可**開箱即用**。

本工具箱提供了一系列強大的棉花基因組資料處理工具，包括多版本間的同源基因映射（Liftover）、基因功能註釋、基因位點查詢、富集分析、AI助手批次處理資料等。它旨在成為您日常科研工作中不可或缺的得力助手。

---

## ✨ 核心亮點與功能

### 1. 極致友好，開箱即用
* **圖形介面優先**: 所有核心工具均可透過直觀的圖形介面完成，滑鼠點擊即可運行分析。
* **無需複雜配置**: 下載後直接運行，無需安裝Python或處理複雜的相依性關係。
* **多語言支援**: 內建簡/繁中文、英文、日文介面，打破語言壁壘。
* **核心功能離線運行**: 除首次資料下載和AI助手功能外，所有核心分析均可在本地離線完成，確保您的資料安全。

### 2. 高效的自動化與批次處理
* **多執行緒加速**: 內建多執行緒支援，無論是下載海量基因組資料，還是使用AI助手批次翻譯、分析上千行表格，都能顯著縮短等待時間。
* **命令列支援**: 對於進階使用者，我們同樣提供功能完善的命令列工具，方便您將FCGT整合到自動化分析流程中。

### 3. 精準的基因組工具集
* **棉花版 Liftover**: 解決了棉花領域長期缺乏在不同基因組版本間进行基因列表轉換工具的難題。
* **一站式資料工具**: 集合了基因註釋、GFF查詢、富集分析、格式轉換等多種常用功能，無需在多個軟體間來回切換。
* **標準化資料下載**: 一鍵下載來自 [CottonGen](https://www.cottongen.org/) 等權威資料庫的主流棉花參考基因組及註釋檔案。

### 4. 跨平台，隨處可用
* 我們為 **Windows** 使用者都提供了預編譯的可執行檔（其他系統的使用者可以執行Python運行）。
* 無論您使用何種主流作業系統，都能獲得一致、流暢的使用體驗。

---

## 快速入門

我們已在 **[發布頁面 (Releases)](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases)** 為您準備了開箱即用的可執行檔，這是最推薦的使用方式。

* **圖形介面版**: 下載 `FCGT-GUI.exe` (Windows) 或對應您系統的檔案，直接雙擊運行。
* **命令列工具**: 下載 `FCGT.exe` (Windows) 或對應您系統的檔案，在終端中運行。

**開發者與進階使用者**也可以從原始碼啟動：
```bash
# 運行圖形介面
python gui_app.py

# 查看命令列幫助
python -m cotton_toolkit.cli --helpxxxxxxxxxx <p align="center" style="color:#888;">  <i>由 Gemini AI 協助開發，功能持續迭代。學術交流為本，程式嚴謹為先。</i></p>
  由 Gemini AI 協助開發，功能持續迭代。學術交流為本，程式嚴謹為先。