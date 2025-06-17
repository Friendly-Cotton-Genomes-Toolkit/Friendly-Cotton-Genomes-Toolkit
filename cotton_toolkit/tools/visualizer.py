# cotton_toolkit/tools/visualizer.py

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from upsetplot import from_contents, UpSet
from typing import List, Optional, Dict
import os
import textwrap  # 导入文本换行工具


# ------------------- 通用绘图函数 -------------------

def plot_enrichment_bubble(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 25,  # 默认显示更多条目以匹配参考图
        sort_by: str = 'p_value',  # 按p_value排序以匹配参考图
        show_title: bool = True,
        title: Optional[str] = None,
        width: float = 10,
        height: float = 8
) -> Optional[str]:
    """
    【RichFactor专业版】绘制富集分析气泡图，风格与主流工具对齐。
    - X轴使用 RichFactor。
    - 气泡大小代表 GeneNumber。
    - 气泡颜色代表 p_value 或 FDR。
    """
    if enrichment_df is None or enrichment_df.empty:
        return None
    try:
        # 按p_value或FDR升序排序，p值越小越显著
        df_plot = enrichment_df.sort_values(by=sort_by, ascending=True).head(top_n).copy()

        if df_plot.empty:
            return None

        # 为了让Y轴顺序好看（RichFactor大的在上面），我们在这里反转顺序
        df_plot = df_plot.iloc[::-1]

        # 【修改】对长描述进行自动换行
        df_plot['Description'] = df_plot['Description'].apply(
            lambda x: '\n'.join(textwrap.wrap(str(x), width=45, break_long_words=True))
        )

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(width, height))

        # 核心绘图逻辑
        scatter = ax.scatter(
            x='RichFactor',
            y='Description',
            data=df_plot,
            s='GeneNumber',  # 气泡大小
            c=sort_by,  # 气泡颜色
            cmap='coolwarm_r',  # 红->蓝 色带，值越小越红
            alpha=0.8,
            edgecolors="black",
            linewidth=0.5
        )

        ax.set_xlabel("Rich Factor", fontsize=14, weight='bold')
        ax.set_ylabel("Pathway", fontsize=14, weight='bold')
        ax.tick_params(axis='y', labelsize=12)

        if show_title:
            plot_title = title if title else f"Top {top_n} of KEGG Enrichment"
            ax.set_title(plot_title, fontsize=16, weight='bold', pad=20)

        # 创建图例
        # 大小图例
        size_handles, size_labels = scatter.legend_elements(prop="sizes", alpha=0.6, num=5)
        size_legend = ax.legend(size_handles, size_labels, title="GeneNumber", loc="center left",
                                bbox_to_anchor=(1.05, 0.7))
        ax.add_artist(size_legend)

        # 颜色图例
        color_legend = fig.colorbar(scatter, ax=ax, pad=0.01, fraction=0.05, location='right')
        color_legend.set_label(sort_by, size=12, weight='bold')

        # 自动调整布局，防止内容溢出
        plt.tight_layout(rect=[0, 0, 0.85, 1])  # 为图例留出右侧空间

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"Error plotting bubble chart: {e}")
        import traceback
        traceback.print_exc()
        return None

def plot_enrichment_bar(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 20,
        sort_by: str = 'FDR',
        show_title: bool = True,
        title: Optional[str] = None,
        width: float = 10,
        height: float = 8,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[str]:
    """【log2FC美化版】绘制富集分析条形图，自动处理长文本和布局。"""
    if enrichment_df is None or enrichment_df.empty:
        return None
    try:
        df_plot = enrichment_df.sort_values(by=sort_by).head(top_n).copy()

        # 【修改】对长描述进行自动换行
        df_plot['Description'] = df_plot['Description'].apply(
            lambda x: '\n'.join(textwrap.wrap(str(x), width=40, break_long_words=True))
        )

        use_log2fc_color = False
        if gene_log2fc_map and 'Genes' in df_plot.columns:
            avg_fc_list = []
            for gene_str in df_plot['Genes']:
                genes = str(gene_str).split(';')
                fc_values = [gene_log2fc_map.get(g.strip()) for g in genes if
                             gene_log2fc_map.get(g.strip()) is not None]
                if fc_values:
                    avg_fc_list.append(sum(fc_values) / len(fc_values))
                else:
                    avg_fc_list.append(0)
            df_plot['avg_log2FC'] = avg_fc_list
            use_log2fc_color = True

        plt.style.use('seaborn-v0_8-talk')
        fig, ax = plt.subplots(figsize=(width, height))

        y_pos = range(len(df_plot))

        if use_log2fc_color:
            norm = plt.Normalize(df_plot['avg_log2FC'].min(), df_plot['avg_log2FC'].max())
            cmap = plt.get_cmap('coolwarm')
            colors = cmap(norm(df_plot['avg_log2FC']))
            bars = ax.barh(y_pos, -np.log10(df_plot['FDR']), align='center', color=colors)
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = fig.colorbar(sm, ax=ax)
            cbar.set_label('Average log2FC')
        else:
            bars = ax.barh(y_pos, -np.log10(df_plot['FDR']), align='center', color='skyblue')

        ax.set_yticks(y_pos)
        ax.set_yticklabels(df_plot['Description'], fontsize=12)
        ax.invert_yaxis()
        ax.set_xlabel('-log10(FDR)', fontsize=14)

        if show_title:
            plot_title = title if title else "Enrichment Analysis Bar Plot"
            ax.set_title(plot_title, fontsize=16, weight='bold')

        # 【修改】在保存前自动调整布局
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"Error plotting bar chart: {e}")
        return None


def plot_enrichment_upset(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 10
) -> Optional[str]:
    """【美化版】绘制Upset图，展示基因在不同富集通路中的重叠情况。"""
    if enrichment_df is None or enrichment_df.empty:
        return None
    try:
        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)

        # 准备Upset plot所需的数据格式
        gene_sets = {row['Description']: set(row['Genes'].split(';')) for index, row in df_plot.iterrows()}
        upset_data = from_contents(gene_sets)

        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 7))

        upset = UpSet(upset_data, orientation='horizontal', sort_by='degree')
        upset.plot(fig=fig)

        # 【修改】Upsetplot的布局较为特殊，但我们仍然可以尝试调整整体Figure的布局
        plt.suptitle("Gene Overlap in Enriched Terms", fontsize=16, y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.95])  # 为总标题留出空间

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"Error plotting upset chart: {e}")
        return None


def plot_enrichment_cnet(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 5,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[str]:
    """【美化版】绘制基因-概念网络图 (cnet plot)，自动调整布局。"""
    if enrichment_df is None or enrichment_df.empty:
        return None
    try:
        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)

        G = nx.Graph()
        gene_nodes = set()

        # 添加节点和边
        for _, row in df_plot.iterrows():
            term_id = row['Description']
            genes = str(row['Genes']).split(';')
            G.add_node(term_id, node_type='term')
            for gene in genes:
                if gene not in gene_nodes:
                    G.add_node(gene, node_type='gene')
                    gene_nodes.add(gene)
                G.add_edge(term_id, gene)

        # 设置节点颜色和大小
        node_colors = []
        node_sizes = []
        term_color = 'skyblue'

        # 准备log2FC颜色映射
        fc_colors = []
        if gene_log2fc_map:
            fc_values = [gene_log2fc_map.get(node, 0) for node in G.nodes() if G.nodes[node]['node_type'] == 'gene']
            if fc_values:
                norm = plt.Normalize(min(fc_values), max(fc_values))
                cmap = plt.get_cmap('coolwarm')
                fc_colors = {node: cmap(norm(gene_log2fc_map.get(node, 0))) for node in gene_nodes}

        for node in G.nodes():
            if G.nodes[node]['node_type'] == 'term':
                node_colors.append(term_color)
                node_sizes.append(G.degree(node) * 100)
            else:
                node_sizes.append(150)
                if gene_log2fc_map and node in fc_colors:
                    node_colors.append(fc_colors[node])
                else:
                    node_colors.append('lightgreen')

        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(12, 12))

        pos = nx.spring_layout(G, k=0.8, iterations=50, seed=42)

        nx.draw(G, pos, ax=ax, with_labels=True, node_color=node_colors, node_size=node_sizes,
                font_size=9, font_weight='bold', edge_color='grey', alpha=0.8)

        ax.set_title("Gene-Concept Network", fontsize=16, weight='bold')

        # 【修改】在保存前自动调整布局
        fig.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"Error plotting cnet chart: {e}")
        return None