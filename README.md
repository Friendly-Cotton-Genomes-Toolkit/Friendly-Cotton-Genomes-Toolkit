<table>
  <tr>
    <td width="120" align="center" valign="middle">
      <img src="docs/ico.png" alt="FCGT Logo" width="110" height="110"/>
    </td>
    <td valign="middle">
      <h1 style="font-weight:700; letter-spacing:2px; margin-bottom:0;">
        友好棉花基因组工具包 <br>
        <span style="font-size:1.1em;">(Friendly Cotton Genomes Toolkit, FCGT)</span>
      </h1>
      <p style="font-size:1.1em; margin-top:0.5em;">
        <b>由 Gemini AI 辅助开发 · 开源学术项目 · 欢迎同行批评指正</b>
      </p>
    </td>
  </tr>
</table>

<hr style="border: 1px solid #eaeaea; margin: 1.5em 0;" />


<p align="center"> | [简体中文](README.md) | [繁体中文](readme-zh_Hant.md) | [English](readme-en_US.md) |</p>

## 项目简介

**FCGT**（Friendly Cotton Genomes Toolkit）为棉花基因组数据分析提供专业、易用的工具支持，涵盖图形界面（GUI）与命令行（CLI）模式，注重降低生物信息学门槛，助力科研与育种实践。  
本工具包聚焦于功能缺失基因筛选、同源性映射与整合分析，解决了目前棉花领域缺乏类似 Liftover 工具与数据的痛点。  
FCGT 的 Liftover 实现理念不同于传统通用工具，更加贴合棉花及相关作物的实际需求。

---

## 主要功能特色

- **标准化数据下载**  
  自动连接 CottonGen 等权威数据库，快速获取主流棉花基因组及注释数据。
- **同源映射与优先级筛选**  
  支持多参数定制，基于 BLAST 等结果，实现精准同源基因筛选与排序。
- **功能缺失基因整合分析**  
  融合多组学表格、注释与同源性信息，辅助复杂遗传分析。
- **灵活配置与批量处理**  
  支持 YAML 配置，便于大规模自动化与团队协作。
- **多语言友好界面**  
  默认简体中文，CLI/GUI 可自由切换，适合不同背景用户。
- **全流程新手友好**  
  零基础可用，配套详细文档，支持图形与命令行双操作。

---

## 学术定位与创新

- **新手友好，专业可扩展**  
  科研人员与学生均可轻松上手，且便于自定义与二次开发。
- **填补行业空白**  
  棉花领域长期缺乏 Liftover 等基因组映射工具，FCGT 致力于推动学科进步。
- **严谨可复用**  
  所有流程与参数均可溯源，利于成果复现与共享。

---

## 数据来源与学术致谢

本项目高度依赖 [CottonGen](https://www.cottongen.org/) 提供的权威数据，感谢其团队持续的开放和维护。

**参考文献：**

- Yu, J, Jung S, Cheng CH, Lee T, Zheng P, Buble K, Crabb J, Humann J, Hough H, Jones D, Campbell JT, Udall J, Main D (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. *Plants* 2021, 10(12), 2805.
- Yu J, Jung S, Cheng CH, Ficklin SP, Lee T, Zheng P, Jones D, Percy R, Main D (2014) CottonGen: a genomics, genetics and breeding database for cotton research. *Nucleic Acids Research* 42(D1), D1229-D1236.

同时，向所有为棉花基因组测序、组装、注释与功能研究作出贡献的科研同仁致以崇高敬意！

> **注意：本工具通过网络自动下载所需数据，项目本体不包含任何第三方数据库内容。**

---

## 快速入门

我们在[发布页面](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/releases)提供开箱即用的可执行文件：  
无需 Python 环境，下载后直接运行即可：

- **图形界面版**：`FCGT-GUI.exe`
- **命令行工具**：`FCGT.exe`

适用于绝大多数用户。

**进阶用户与开发者**可通过源码启动：

```bash
# 图形界面
python gui_app.py

# 命令行
python -m cotton_toolkit.cli --help
```

所有配置与数据源文件均采用 YAML 格式，详见帮助文档。

---

## 反馈与学术交流

如有建议、问题或合作意向，欢迎通过 [GitHub Issues](https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/issues) 联系。  
欢迎同行批评指正、共建开源生态！

---

<p align="center" style="color:#888;">
  <i>由 Gemini AI 辅助开发，功能持续迭代。学术交流为本，代码严谨为先。</i>
</p>