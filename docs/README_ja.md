<table>
  <tr>
    <td width="120" align="center" valign="middle">
      <img src="ico.png" alt="logo" width="128" height="128" style="object-fit:cover;" />
    </td>
    <td valign="middle">
      <h1 style="font-weight:700; letter-spacing:2px; margin-bottom:0;">
        フレンドリーコットンゲノムツールキット <br>
        <span style="font-size:1.1em;">(Friendly Cotton Genomes Toolkit, FCGT)</span>
      </h1>
      <p style="font-size:1.1em; margin-top:0.5em;">
        <b>Gemini AIの協力で開発 · オープンソース学術プロジェクト · 同業者によるレビューとご意見を歓迎します</b>
      </p>
    </td>
  </tr>
</table>


## 选择你的语言 | Select your language | 言語を選択 | 選擇語言

[中文（简体）](../README.md)	[English](README_en.md)	[日本語](README_ja.md)	 [繁體中文](README_zh-hant.md)

---

## プロジェクト概要

**FCGT**（Friendly Cotton Genomes Toolkit）は、綿花ゲノムデータ解析のためのプロフェッショナルかつユーザーフレンドリーなツールを提供します。グラフィカルユーザーインターフェース（GUI）とコマンドラインインターフェース（CLI）の両方に対応し、バイオインフォマティクスの敷居を下げ、研究や育種活動を支援します。  
本ツールキットは、機能喪失遺伝子のスクリーニング、ホモロジーマッピング、統合解析に焦点を当てており、綿花ゲノム分野におけるLiftoverのようなツールやデータの不足を解決します。  
FCGTのLiftover機能は、従来の汎用ツールとは異なるアプローチで実装されており、綿花や関連作物の実際のニーズにより適しています。

---

## 主な特徴

- **標準化されたデータダウンロード**  
  CottonGenなどの信頼できるデータベースと自動的に接続し、主流の綿花ゲノムやアノテーションデータを迅速に取得できます。
- **ホモロジーマッピングと優先順位付け**  
  複数パラメータのカスタマイズが可能で、BLAST等の結果に基づき、ホモログ遺伝子の精密なスクリーニングと順位付けを実現します。
- **機能喪失遺伝子の統合解析**  
  マルチオミクス表、アノテーション、ホモロジー情報を統合し、複雑な遺伝解析を支援します。
- **柔軟な設定とバッチ処理**  
  YAML設定をサポートし、大規模な自動化やチームでの共同作業にも対応します。
- **多言語対応のフレンドリーなインターフェース**  
  デフォルトは簡体字中国語ですが、CLI/GUIで自由に言語を切り替え可能。様々な背景のユーザーに対応します。
- **初心者にも優しいワークフロー**  
  プログラミング未経験者でも利用できるように設計されており、詳細なドキュメントも提供。GUIとCLI両方に対応しています。

---

## 学術的な位置づけとイノベーション

- **初心者に優しく、専門性の拡張も可能**  
  研究者や学生も簡単に利用でき、カスタマイズや二次開発も容易です。
- **分野のギャップを埋める**  
  綿花分野では長らくLiftoverやゲノム間マッピングツールが不足していました。FCGTはこの分野の発展に貢献します。
- **厳密さと再現性**  
  すべてのワークフローとパラメータは追跡可能で、成果の再現や共有が容易です。

---

## データソースと学術的謝辞

本プロジェクトは [CottonGen](https://www.cottongen.org/) が提供する信頼性の高いデータに大きく依存しています。CottonGenチームによる継続的な公開と保守に深く感謝いたします。

**参考文献:**

- Yu, J, Jung S, Cheng CH, Lee T, Zheng P, Buble K, Crabb J, Humann J, Hough H, Jones D, Campbell JT, Udall J, Main D (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 2021, 10(12), 2805.
- Yu J, Jung S, Cheng CH, Ficklin SP, Lee T, Zheng P, Jones D, Percy R, Main D (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.

また、綿花ゲノムのシーケンシング、アセンブリ、アノテーション、機能研究に貢献されたすべての研究者の皆様に心より敬意を表します。

> **注意：本ツールキットは必要なデータをインターネット経由で自動ダウンロードします。本プロジェクト自体には第三者データベースの内容は含まれていません。**

---

## はじめに

[リリースページ](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases) にはすぐに使える実行ファイルを提供しています。  
Python環境は不要で、ダウンロードしてそのまま実行可能です：

- **GUI版:** `FCGT-GUI.exe`
- **コマンドラインツール:** `FCGT.exe`

ほとんどのユーザーはこちらをご利用ください。

**上級ユーザーや開発者**はソースコードから起動可能です：

```bash
# GUI
python gui_app.py

# コマンドライン
python -m cotton_toolkit.cli --help
```

すべての設定およびデータソースファイルはYAML形式を利用しています。詳細はドキュメントをご参照ください。

---

## フィードバックと学術交流

ご提案、ご質問、共同研究のご希望がありましたら [GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues) からご連絡ください。  
同業者によるレビューとオープンソースへの貢献を歓迎します！

---

<p align="center" style="color:#888;">
  <i>Gemini AIの協力により開発。学術的なコラボレーションとコード品質のために継続的に改善中。</i>
</p>