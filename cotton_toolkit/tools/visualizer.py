# cotton_toolkit/tools/visualizer.py

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from upsetplot import from_contents, UpSet
from typing import List, Optional, Dict
import os
import textwrap
import re  # 【新增】导入re模块

try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


def plot_enrichment_bubble(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 20,
        sort_by: str = 'FDR',
        show_title: bool = True,
        title: Optional[str] = "KEGG Enrichment",
        width: float = 10,
        height: float = 8
) -> Optional[str]:
    """
    Generates an enrichment bubble plot with an R/ggplot2-like style.
    """
    if enrichment_df.empty:
        print(_("Warning: Enrichment DataFrame is empty for bubble plot."))
        return None

    df = enrichment_df.copy()
    fig, ax = None, None

    try:
        # 使用更接近ggplot2的样式
        plt.style.use('seaborn-v0_8-whitegrid')

        # --- 数据准备 ---
        actual_sort_by_col = 'FDR'
        if sort_by.lower() == 'pvalue':
            possible_cols = ['PValue', 'p_value', 'P-value']
            actual_sort_by_col = next((col for col in possible_cols if col in df.columns), 'PValue')
        elif sort_by.lower() == 'foldenrichment':
            possible_cols = ['RichFactor', 'FoldEnrichment']
            actual_sort_by_col = next((col for col in possible_cols if col in df.columns), 'RichFactor')
        else:
            possible_cols = ['FDR', 'Adjusted P-value', 'FDR_pvalue']
            actual_sort_by_col = next((col for col in possible_cols if col in df.columns), 'FDR')

        if sort_by.lower() in ['fdr', 'pvalue']:
            df = df.sort_values(by=actual_sort_by_col, ascending=True).head(top_n).copy()
        else:
            df = df.sort_values(by=actual_sort_by_col, ascending=False).head(top_n).copy()

        if df.empty: return None
        df['GeneNumber'] = pd.to_numeric(df['GeneNumber'], errors='coerce')
        df[actual_sort_by_col] = pd.to_numeric(df[actual_sort_by_col], errors='coerce')
        df.dropna(subset=['GeneNumber', actual_sort_by_col, 'Description', 'RichFactor'], inplace=True)
        if df.empty: return None

        num_terms = len(df)
        dynamic_height = height
        if num_terms > 10:
            dynamic_height = 8 + (num_terms - 10) * 0.5
        df = df.iloc[::-1]

        # --- 绘图 ---
        fig, ax = plt.subplots(figsize=(width, dynamic_height))

        scatter = ax.scatter(
            x=df['RichFactor'], y=df['Description'], s=df['GeneNumber'] * 25,
            c=df[actual_sort_by_col], cmap='viridis_r', alpha=0.9, edgecolors="black", linewidth=0.5
        )

        # --- 优化图例和整体布局以模仿ggplot2风格 ---

        # 1. 调整子图布局，为右侧图例和顶部标题留出空间
        fig.subplots_adjust(right=0.78, top=0.85)

        # 2. 创建 Gene Count (大小) 图例
        min_size = df['GeneNumber'].min()
        max_size = df['GeneNumber'].max()
        legend_labels = [int(i) for i in np.linspace(min_size, max_size, 4)]
        legend_labels = sorted(list(set(legend_labels)))
        if len(legend_labels) < 2:
            legend_labels = sorted(list(set(df['GeneNumber'].astype(int))))

        legend_handles = [ax.scatter([], [], s=label * 25, c='black', alpha=1.0) for label in legend_labels]

        legend1 = ax.legend(
            legend_handles, legend_labels,
            title="Gene Count",
            loc='upper left',
            bbox_to_anchor=(1.04, 1.02),
            frameon=False,
            labelspacing=1.5,  # 修改：减小行距使其更紧凑
            title_fontsize=12,
            fontsize=10
        )
        ax.add_artist(legend1)

        # 3. 创建 FDR (颜色) 图例 (Colorbar)
        cbar_ax = fig.add_axes([0.86, 0.2, 0.03, 0.35])
        cbar = plt.colorbar(scatter, cax=cbar_ax, orientation='vertical')
        cbar.ax.set_title('FDR', pad=10, fontsize=12)
        cbar.outline.set_visible(False)

        # --- 坐标轴标签和网格线 ---
        ax.set_xlabel("Rich Factor", fontsize=12)
        ax.set_ylabel("Term Description", fontsize=12)
        y_labels = [textwrap.fill(label, width=50, break_long_words=False) for label in df['Description']]
        ax.set_yticklabels(y_labels, fontsize=10)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # --- 标题和副标题 ---
        if show_title:
            main_title_x_pos = 0.5 * (fig.subplotpars.right)
            fig.suptitle(title, fontsize=16, fontweight='bold', x=main_title_x_pos, y=0.98)
            ax.set_title(f"Top {len(df)} Enriched Terms by FDR", fontsize=11, pad=15)

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting bubble chart: {}").format(e))
        return None
    finally:
        if fig is not None:
            plt.close(fig)


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
    if enrichment_df is None or enrichment_df.empty: return None
    fig, ax = None, None
    try:
        # --- STYLE MODIFICATION: Switch to 'whitegrid' for consistency ---
        plt.style.use('seaborn-v0_8-whitegrid')

        df_plot = enrichment_df.copy()
        # Data preparation (remains the same)
        actual_sort_by_col = 'FDR'
        if sort_by.lower() == 'pvalue':
            actual_sort_by_col = 'PValue'
        elif sort_by.lower() == 'foldenrichment':
            actual_sort_by_col = 'RichFactor'
        if sort_by.lower() in ['fdr', 'pvalue']:
            df_plot = df_plot.sort_values(by=actual_sort_by_col, ascending=True).head(top_n).copy()
        else:
            df_plot = df_plot.sort_values(by=actual_sort_by_col, ascending=False).head(top_n).copy()
        if df_plot.empty: return None
        df_plot['FDR'] = pd.to_numeric(df_plot['FDR'], errors='coerce')
        df_plot.dropna(subset=['FDR', 'Description'], inplace=True)
        if df_plot.empty: return None
        num_terms = len(df_plot)
        if num_terms > 10: height = 6 + (num_terms - 10) * 0.4
        df_plot['Description'] = df_plot['Description'].apply(lambda x: '\n'.join(textwrap.wrap(str(x), width=40)))
        df_plot = df_plot.iloc[::-1]

        use_log2fc_color = False
        if gene_log2fc_map and 'Genes' in df_plot.columns:
            avg_fc_list = [np.mean([gene_log2fc_map.get(g) for g in re.sub(r'\.\d+$', '', str(gene_str)).split(';') if
                                    g and gene_log2fc_map.get(g) is not None] or [0]) for gene_str in df_plot['Genes']]
            df_plot['avg_log2FC'] = avg_fc_list
            use_log2fc_color = True

        fig, ax = plt.subplots(figsize=(width, height))
        y_pos = range(len(df_plot))

        # The 'coolwarm' diverging palette is a strong academic choice for up/down regulation
        if use_log2fc_color:
            norm = plt.Normalize(df_plot['avg_log2FC'].min(), df_plot['avg_log2FC'].max())
            cmap = plt.get_cmap('coolwarm')
            colors = cmap(norm(df_plot['avg_log2FC']))
            bars = ax.barh(y_pos, -np.log10(df_plot['FDR']), align='center', color=colors)
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm);
            sm.set_array([])
            cbar = fig.colorbar(sm, ax=ax)
            cbar.set_label('Average log2FC', fontsize=12, rotation=270, labelpad=15)
        else:
            bars = ax.barh(y_pos, -np.log10(df_plot['FDR']), align='center', color='skyblue')

        ax.set_yticks(y_pos)
        ax.set_yticklabels(df_plot['Description'], fontsize=10)
        ax.set_xlabel('-log10(FDR)', fontsize=12)
        ax.tick_params(axis='x', labelsize=10)

        # Customize grid for bar chart
        ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5, color='grey', alpha=0.6)
        ax.grid(False, which='major', axis='y')

        if show_title:
            plot_title = title if title else "Enrichment Analysis Bar Plot"
            ax.set_title(plot_title, fontsize=14, weight='bold')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting bar chart: {}").format(e))
        return None
    finally:
        if fig is not None:
            plt.close(fig)


def plot_enrichment_upset(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 10
) -> Optional[str]:
    if enrichment_df is None or enrichment_df.empty:
        print(_("Warning: Enrichment DataFrame is empty for upset plot."))
        return None
    fig = None
    try:
        required_cols = ['FDR', 'Description', 'Genes']
        if not all(col in enrichment_df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in enrichment_df.columns]
            print(_("Error: Missing required columns for upset plot: {}. Available columns: {}").format(missing_cols,
                                                                                                        enrichment_df.columns.tolist()))
            return None

        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)

        if df_plot.empty:
            print(_("Warning: DataFrame is empty after sorting and head for upset plot."))
            return None

        gene_sets = {row['Description']: set(row['Genes'].split(';')) for index, row in df_plot.iterrows()}
        upset_data = from_contents(gene_sets)

        # 【优化】Upset图的字体大小和图表大小
        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 7 + top_n * 0.2))  # 根据富集项数量调整高度

        upset = UpSet(upset_data, orientation='horizontal', sort_by='degree',
                      show_counts=True, element_size=40)  # 调整元素大小
        upset.plot(fig=fig)

        plt.suptitle("Gene Overlap in Enriched Terms", fontsize=16, y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.95])

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting upset chart: {}").format(e))
        return None
    finally:
        if fig is not None:
            plt.close(fig)


def plot_enrichment_cnet(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 5,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[str]:
    if enrichment_df is None or enrichment_df.empty: return None
    fig, ax = None, None
    try:
        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)
        if df_plot.empty: return None

        G = nx.Graph()
        gene_nodes = set();
        term_nodes = []
        for _idx, row in df_plot.iterrows():
            term_id = row['Description'];
            term_nodes.append(term_id)
            genes = str(row['Genes']).split(';')
            G.add_node(term_id, node_type='term')
            for gene in genes:
                clean_gene = re.sub(r'\.\d+$', '', gene.strip())
                if clean_gene:
                    if clean_gene not in gene_nodes:
                        G.add_node(clean_gene, node_type='gene');
                        gene_nodes.add(clean_gene)
                    G.add_edge(term_id, clean_gene)

        term_degrees = {node: G.degree(node) for node in term_nodes}
        node_sizes = [term_degrees.get(node, 0) * 100 if data['node_type'] == 'term' else 150 for node, data in
                      G.nodes(data=True)]

        node_colors = []
        # --- STYLE MODIFICATION: Use a more neutral color for terms to emphasize genes ---
        term_color = '#D3D3D3'  # Light Grey
        gene_default_color = 'lightgrey'
        cmap = plt.get_cmap('coolwarm')
        norm = None
        if gene_log2fc_map:
            fc_values = [v for v in gene_log2fc_map.values() if v is not None]
            if fc_values: norm = plt.Normalize(vmin=min(fc_values), vmax=max(fc_values))
        for node, data in G.nodes(data=True):
            if data['node_type'] == 'term':
                node_colors.append(term_color)
            else:
                if gene_log2fc_map and norm and node in gene_log2fc_map:
                    node_colors.append(cmap(norm(gene_log2fc_map[node])))
                else:
                    node_colors.append(gene_default_color)

        # Use a clean, blank style for network plots
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(14, 14))
        ax.grid(False)
        ax.set_xticks([]);
        ax.set_yticks([])

        pos = nx.spring_layout(G, k=0.9, iterations=50, seed=42)
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color='grey', alpha=0.6)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=node_sizes, alpha=0.9,
                               edgecolors='black', linewidths=0.5)
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=9, font_weight='bold')

        if norm:
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm);
            sm.set_array([])
            cbar = fig.colorbar(sm, ax=ax, shrink=0.5, aspect=20, pad=0.01)
            cbar.set_label('log2FC', rotation=270, labelpad=15, fontsize=12)
        if term_degrees:
            degrees = sorted(list(set(term_degrees.values())))
            if len(degrees) > 4:
                degrees = [degrees[0], degrees[len(degrees) // 3], degrees[2 * len(degrees) // 3], degrees[-1]]
            legend_handles = [
                plt.scatter([], [], s=deg * 100, color=term_color, alpha=0.9, label=str(deg), edgecolors='black',
                            linewidths=0.5) for deg in degrees]
            size_legend = ax.legend(handles=legend_handles, title='Gene Count', loc='lower left', frameon=False,
                                    labelspacing=1.5)
            ax.add_artist(size_legend)

        ax.set_title("Gene-Concept Network", fontsize=16, weight='bold')
        fig.suptitle("KEGG Enrichment", fontsize=20, weight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_(f"Error plotting cnet chart: {e}"))
        return None
    finally:
        if fig is not None:
            plt.close(fig)
