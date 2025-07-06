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


# ------------------- 通用绘图函数 -------------------

def plot_enrichment_bubble(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 20,
        sort_by: str = 'FDR',
        show_title: bool = True,
        title: Optional[str] = "Enrichment Analysis",
        width: float = 10,
        height: float = 8
) -> Optional[str]:
    if enrichment_df.empty:
        print(_("Warning: Enrichment DataFrame is empty for bubble plot."))
        return None

    df = enrichment_df.copy()
    fig, ax = None, None  # 初始化 fig 和 ax

    try:
        actual_sort_by_col = None
        if sort_by.lower() == 'fdr':
            possible_cols = ['FDR', 'Adjusted P-value', 'FDR_pvalue']
            for col in possible_cols:
                if col in df.columns:
                    actual_sort_by_col = col
                    break
        elif sort_by.lower() == 'pvalue':
            possible_cols = ['PValue', 'p_value', 'P-value']
            for col in possible_cols:
                if col in df.columns:
                    actual_sort_by_col = col
                    break
        elif sort_by.lower() == 'foldenrichment':
            possible_cols = ['RichFactor', 'FoldEnrichment']
            for col in possible_cols:
                if col in df.columns:
                    actual_sort_by_col = col
                    break

        if actual_sort_by_col is None:
            if 'FDR' in df.columns:
                actual_sort_by_col = 'FDR'
            elif 'Adjusted P-value' in df.columns:
                actual_sort_by_col = 'Adjusted P-value'
            elif 'PValue' in df.columns:
                actual_sort_by_col = 'PValue'
            else:
                print(
                    _("Error: Neither '{}' nor common alternatives found in DataFrame columns for sorting. Available columns: {}").format(
                        sort_by, df.columns.tolist()))
                return None

        required_cols = [actual_sort_by_col, 'Description', 'GeneNumber', 'RichFactor']
        if not all(col in df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in df.columns]
            print(_("Error: Missing required columns for bubble plot: {}. Available columns: {}").format(missing_cols,
                                                                                                         df.columns.tolist()))

            return None

        df = df.sort_values(by=actual_sort_by_col).head(top_n).copy()

        if df.empty:
            print(_("Warning: DataFrame is empty after sorting and head for cnet plot."))
            return None

        df['GeneNumber'] = pd.to_numeric(df['GeneNumber'], errors='coerce')
        df[actual_sort_by_col] = pd.to_numeric(df[actual_sort_by_col], errors='coerce')
        df.dropna(subset=['GeneNumber', actual_sort_by_col, 'Description', 'RichFactor'], inplace=True)
        if df.empty:
            print(_("Warning: DataFrame is empty after dropping NA for bubble plot."))
            return None

        df = df.iloc[::-1]

        plt.style.use('seaborn-v0_8-paper')
        fig, ax = plt.subplots(figsize=(width, height))  # fig 和 ax 在这里被赋值

        scaling_factor = 25
        scatter = ax.scatter(
            x=df['RichFactor'],
            y=df['Description'],
            s=df['GeneNumber'] * scaling_factor,
            c=df[actual_sort_by_col],
            cmap='viridis_r',
            alpha=0.7,
            edgecolors="black",
            linewidth=0.5
        )

        cbar = plt.colorbar(scatter, ax=ax, pad=0.08)
        cbar.set_label(actual_sort_by_col, rotation=270, labelpad=15)

        ax.set_xlabel("Rich Factor")
        ax.set_ylabel("Term Description")
        ax.grid(True, linestyle='--', alpha=0.6)

        y_labels = [textwrap.fill(label, width=50, break_long_words=False) for label in df['Description']]
        ax.set_yticklabels(y_labels)

        if show_title:
            plt.title(title, fontsize=16, fontweight='bold')

        fig.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting bubble chart: {}").format(e))
        return None
    finally:  # 确保在任何情况下都关闭图形
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
    if enrichment_df is None or enrichment_df.empty:
        print(_("Warning: Enrichment DataFrame is empty for bar plot."))
        return None
    fig, ax = None, None  # 初始化 fig 和 ax
    try:
        df_plot = enrichment_df.copy()

        actual_sort_by_col = None
        if sort_by.lower() == 'fdr':
            possible_cols = ['FDR', 'Adjusted P-value', 'FDR_pvalue']
            for col in possible_cols:
                if col in df_plot.columns:
                    actual_sort_by_col = col
                    break
        elif sort_by.lower() == 'pvalue':
            possible_cols = ['PValue', 'p_value', 'P-value']
            for col in possible_cols:
                if col in df_plot.columns:
                    actual_sort_by_col = col
                    break
        elif sort_by.lower() == 'foldenrichment':
            possible_cols = ['RichFactor', 'FoldEnrichment']
            for col in possible_cols:
                if col in df_plot.columns:
                    actual_sort_by_col = col
                    break

        if actual_sort_by_col is None:
            if 'FDR' in df_plot.columns:
                actual_sort_by_col = 'FDR'
            elif 'Adjusted P-value' in df_plot.columns:
                actual_sort_by_col = 'Adjusted P-value'
            elif 'PValue' in df_plot.columns:
                actual_sort_by_col = 'PValue'
            else:
                print(
                    _("Error: Neither '{}' nor common alternatives found in DataFrame columns for sorting. Available columns: {}").format(
                        sort_by, df_plot.columns.tolist()))
                return None

        df_plot = df_plot.sort_values(by=actual_sort_by_col).head(top_n).copy()

        if df_plot.empty:
            print(_("Warning: DataFrame is empty after sorting and head for bar plot."))
            return None

        if 'FDR' not in df_plot.columns:
            print(_("Error: 'FDR' column is required for bar plot but not found."))
            return None

        df_plot['FDR'] = pd.to_numeric(df_plot['FDR'], errors='coerce')
        df_plot.dropna(subset=['FDR', 'Description'], inplace=True)
        if df_plot.empty:
            print(_("Warning: DataFrame is empty after dropping NA for bar plot."))
            return None

        df_plot['Description'] = df_plot['Description'].apply(
            lambda x: '\n'.join(textwrap.wrap(str(x), width=40, break_long_words=True))
        )

        use_log2fc_color = False
        if gene_log2fc_map and 'Genes' in df_plot.columns:
            avg_fc_list = []
            for gene_str in df_plot['Genes']:
                genes = str(gene_str).split(';')
                cleaned_genes = [re.sub(r'\.\d+$', '', g.strip()) for g in genes if g.strip()]  # 这里会用到re
                fc_values = [gene_log2fc_map.get(g) for g in cleaned_genes if
                             gene_log2fc_map.get(g) is not None]
                if fc_values:
                    avg_fc_list.append(sum(fc_values) / len(fc_values))
                else:
                    avg_fc_list.append(0)
            df_plot['avg_log2FC'] = avg_fc_list
            use_log2fc_color = True

        plt.style.use('seaborn-v0_8-talk')
        fig, ax = plt.subplots(figsize=(width, height))  # fig 和 ax 在这里被赋值

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

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting bar chart: {}").format(e))
        return None
    finally:  # 确保在任何情况下都关闭图形
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
    fig = None  # 初始化 fig
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

        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 7))  # fig 在这里被赋值

        upset = UpSet(upset_data, orientation='horizontal', sort_by='degree')
        upset.plot(fig=fig)

        plt.suptitle("Gene Overlap in Enriched Terms", fontsize=16, y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.95])

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting upset chart: {}").format(e))
        return None
    finally:  # 确保在任何情况下都关闭图形
        if fig is not None:
            plt.close(fig)


def plot_enrichment_cnet(
        enrichment_df: pd.DataFrame,
        output_path: str,
        top_n: int = 5,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[str]:
    if enrichment_df is None or enrichment_df.empty:
        print(_("Warning: Enrichment DataFrame is empty for cnet plot."))
        return None
    fig, ax = None, None  # 初始化 fig 和 ax
    try:
        required_cols = ['FDR', 'Description', 'Genes']
        if not all(col in enrichment_df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in enrichment_df.columns]
            print(_("Error: Missing required columns for cnet plot: {}. Available columns: {}").format(missing_cols,
                                                                                                       enrichment_df.columns.tolist()))
            return None

        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)

        if df_plot.empty:
            print("Warning: DataFrame is empty after sorting and head for cnet plot.")
            return None

        G = nx.Graph()
        gene_nodes = set()

        for _c, row in df_plot.iterrows():
            term_id = row['Description']
            genes = str(row['Genes']).split(';')
            G.add_node(term_id, node_type='term')
            for gene in genes:
                clean_gene = re.sub(r'\.\d+$', '', gene.strip())  # 这里会用到re
                if clean_gene and clean_gene not in gene_nodes:
                    G.add_node(clean_gene, node_type='gene')
                    gene_nodes.add(clean_gene)
                if clean_gene:
                    G.add_edge(term_id, clean_gene)

        node_colors = []
        node_sizes = []
        term_color = 'skyblue'

        fc_colors = {}
        if gene_log2fc_map:
            valid_fc_values = [gene_log2fc_map.get(node) for node in gene_nodes if
                               gene_log2fc_map.get(node) is not None]
            if valid_fc_values:
                norm = plt.Normalize(min(valid_fc_values), max(valid_fc_values))
                cmap = plt.get_cmap('coolwarm')
                for node in gene_nodes:
                    fc_colors[node] = cmap(norm(gene_log2fc_map.get(node, 0)))

        for node in G.nodes():
            if G.nodes[node]['node_type'] == 'term':
                node_colors.append(term_color)
                node_sizes.append(G.degree(node) * 100)
            else:
                node_sizes.append(150)
                if node in fc_colors:
                    node_colors.append(fc_colors[node])
                else:
                    node_colors.append('lightgreen')

        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(12, 12))  # fig 和 ax 在这里被赋值

        pos = nx.spring_layout(G, k=0.8, iterations=50, seed=42)

        nx.draw(G, pos, ax=ax, with_labels=True, node_color=node_colors, node_size=node_sizes,
                font_size=9, font_weight='bold', edge_color='grey', alpha=0.8)

        ax.set_title("Gene-Concept Network", fontsize=16, weight='bold')

        fig.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        print(_("Error plotting cnet chart: {}").format(e))
        return None
    finally:  # 确保在任何情况下都关闭图形
        if fig is not None:
            plt.close(fig)