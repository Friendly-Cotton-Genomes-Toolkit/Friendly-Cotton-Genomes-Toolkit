# cotton_toolkit/tools/visualizer_for_enrichment.py
import traceback

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from upsetplot import from_contents, UpSet
from typing import List, Optional, Dict, Any
import os
import textwrap
import re
import logging # 修改: 导入 logging


try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 修改: 创建 logger 实例
logger = logging.getLogger("cotton_toolkit.tools.visualizer")


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
        # 修改: 使用 logger.warning
        logger.warning(_("Enrichment DataFrame is empty for bubble plot."))
        return None

    df = enrichment_df.copy()
    fig, ax = None, None

    try:
        plt.style.use('seaborn-v0_8-whitegrid')

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

        fig, ax = plt.subplots(figsize=(width, dynamic_height))

        scatter = ax.scatter(
            x=df['RichFactor'], y=df['Description'], s=df['GeneNumber'] * 25,
            c=df[actual_sort_by_col], cmap='viridis_r', alpha=0.9, edgecolors="black", linewidth=0.5
        )

        fig.subplots_adjust(right=0.78, top=0.85)

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
            labelspacing=1.5,
            title_fontsize=12,
            fontsize=10
        )
        ax.add_artist(legend1)

        cbar_ax = fig.add_axes([0.86, 0.2, 0.03, 0.35])
        cbar = plt.colorbar(scatter, cax=cbar_ax, orientation='vertical')
        cbar.ax.set_title('FDR', pad=10, fontsize=12)
        cbar.outline.set_visible(False)

        ax.set_xlabel("Rich Factor", fontsize=12)
        ax.set_ylabel("Term Description", fontsize=12)
        y_labels = [textwrap.fill(label, width=50, break_long_words=False) for label in df['Description']]
        ax.set_yticklabels(y_labels, fontsize=10)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        if show_title:
            main_title_x_pos = 0.5 * (fig.subplotpars.right)
            fig.suptitle(title, fontsize=16, fontweight='bold', x=main_title_x_pos, y=0.98)
            ax.set_title(f"Top {len(df)} Enriched Terms by FDR", fontsize=11, pad=15)

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Error plotting bubble chart: {}").format(e))
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
    if enrichment_df is None or enrichment_df.empty:
        # 修改: 使用 logger.warning
        logger.warning(_("Enrichment DataFrame is empty for bar plot."))
        return None
    fig, ax = None, None
    try:
        plt.style.use('seaborn-v0_8-whitegrid')

        df_plot = enrichment_df.copy()
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

        ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5, color='grey', alpha=0.6)
        ax.grid(False, which='major', axis='y')

        if show_title:
            plot_title = title if title else "Enrichment Analysis Bar Plot"
            ax.set_title(plot_title, fontsize=14, weight='bold')

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Error plotting bar chart: {}").format(e))
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
        # 修改: 使用 logger.warning
        logger.warning(_("Enrichment DataFrame is empty for upset plot."))
        return None
    fig = None
    try:
        required_cols = ['FDR', 'Description', 'Genes']
        if not all(col in enrichment_df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in enrichment_df.columns]
            # 修改: 使用 logger.error
            logger.error(_("Error: Missing required columns for upset plot: {}. Available columns: {}").format(missing_cols,
                                                                                                        enrichment_df.columns.tolist()))
            return None

        df_plot = enrichment_df.sort_values(by='FDR').head(top_n)

        if df_plot.empty:
            # 修改: 使用 logger.warning
            logger.warning(_("DataFrame is empty after sorting and head for upset plot."))
            return None

        gene_sets = {row['Description']: set(row['Genes'].split(';')) for index, row in df_plot.iterrows()}
        upset_data = from_contents(gene_sets)

        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 7 + top_n * 0.2))

        upset = UpSet(upset_data, orientation='horizontal', sort_by='degree',
                      show_counts=True, element_size=40)
        upset.plot(fig=fig)

        plt.suptitle("Gene Overlap in Enriched Terms", fontsize=16, y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.95])

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        return output_path
    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Error plotting upset chart: {}").format(e))
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
        term_color = '#D3D3D3'
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
        # 修改: 使用 logger.error
        logger.error(_(f"Error plotting cnet chart: {e}"))
        return None
    finally:
        if fig is not None:
            plt.close(fig)


def _generate_r_script_and_data(
        enrichment_df: pd.DataFrame,
        r_output_dir: str,
        file_prefix: str,
        plot_type: str,
        plot_kwargs: Dict[str, Any],
        analysis_title: str,
        gene_log2fc_map: Optional[Dict[str, float]] = None
) -> Optional[List[str]]:
    # 修改: 移除 log 参数
    try:
        if not os.path.exists(r_output_dir):
            os.makedirs(r_output_dir)

        top_n = plot_kwargs.get('top_n', 20)
        sort_by = plot_kwargs.get('sort_by', 'FDR').lower()

        df_plot = enrichment_df.copy()
        sort_col = 'FDR'
        if sort_by == 'pvalue':
            sort_col = 'PValue'
        elif sort_by == 'foldenrichment':
            sort_col = 'RichFactor'

        ascending = sort_by in ['fdr', 'pvalue']
        current_top_n = plot_kwargs.get('top_n', 10) if plot_type == 'upset' else top_n
        df_plot = df_plot.sort_values(by=sort_col, ascending=ascending).head(current_top_n)

        if df_plot.empty:
            logger.warning(f"DataFrame is empty for plot type '{plot_type}'. Cannot generate R script.")
            return None

        if 'FDR' in df_plot.columns:
            fdr_numeric = pd.to_numeric(df_plot['FDR'], errors='coerce').replace(0, np.finfo(float).tiny)
            df_plot['log10FDR'] = -np.log10(fdr_numeric)

        if plot_type != 'upset':
            df_plot = df_plot.iloc[::-1].copy()

        data_path = os.path.join(r_output_dir, f"{file_prefix}_{plot_type}_data.csv")
        script_path = os.path.join(r_output_dir, f"{file_prefix}_{plot_type}_script.R")
        r_script_content = ""
        log2fc_data_path = None
        df_plot.to_csv(data_path, index=False, encoding='utf-8-sig')

        if plot_type == 'bubble':
            r_script_content = f"""
# R Script: Bubble Plot for Enrichment Analysis

# 1. Load required packages
# install.packages(c("ggplot2", "dplyr", "stringr"))
library(ggplot2)
library(dplyr)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for plotting
# Convert 'Description' to a factor to preserve the sorting order from Python.
enrich_data$Description <- factor(enrich_data$Description, levels = unique(enrich_data$Description))
# Wrap long labels to prevent overlap.
levels(enrich_data$Description) <- str_wrap(levels(enrich_data$Description), width = 50)

# 4. Create the bubble plot
bubble_plot <- ggplot(enrich_data, aes(x = RichFactor, y = Description, size = GeneNumber, color = {sort_col})) +
  geom_point(alpha = 0.8, shape = 16) +
  scale_color_viridis_c(direction = -1, name = "{sort_col}") +
  scale_size_continuous(name = "Gene Count", range = c(3, 10)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Top {current_top_n} Enriched Terms by {sort_by.upper()}",
    x = "Rich Factor",
    y = "Term Description"
  ) +
  theme_minimal(base_size = 14) +
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold", size = 16),
    plot.subtitle = element_text(hjust = 0.5),
    axis.text = element_text(colour = "black"),
    panel.grid.minor = element_blank()
  )

# 5. Save the plot
ggsave(
  "{file_prefix}_bubble_plot_from_R.png",
  plot = bubble_plot,
  width = {plot_kwargs.get('width', 10)},
  height = {plot_kwargs.get('height', 8)},
  dpi = 300,
  bg = "white"
)
"""
        elif plot_type == 'bar':
            use_log2fc = False
            if gene_log2fc_map and 'Genes' in df_plot.columns:
                use_log2fc = True
                avg_fc_list = [np.mean(
                    [gene_log2fc_map.get(g) for g in re.sub(r'\.\d+$', '', str(gene_str)).split(';') if
                     g and gene_log2fc_map.get(g) is not None] or [0]) for gene_str in df_plot['Genes']]
                df_with_fc = df_plot.copy();
                df_with_fc['avg_log2FC'] = avg_fc_list
                df_with_fc.to_csv(data_path, index=False, encoding='utf-8-sig')
            r_script_content = f"""
# R Script: Bar Plot for Enrichment Analysis

# 1. Load required packages
library(ggplot2)
library(dplyr)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for plotting
enrich_data$Description <- factor(enrich_data$Description, levels = unique(enrich_data$Description))
levels(enrich_data$Description) <- str_wrap(levels(enrich_data$Description), width = 40)

# 4. Create the bar plot
use_log2fc_color <- {'TRUE' if use_log2fc else 'FALSE'}
bar_plot <- ggplot(enrich_data, aes(x = log10FDR, y = Description)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Top {current_top_n} Enriched Terms by {sort_by.upper()}",
    x = "-log10(FDR)",
    y = "Term Description"
  ) +
  theme_minimal(base_size = 14) +
  theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size=16),
      plot.subtitle = element_text(hjust = 0.5),
      axis.text = element_text(colour = "black"),
      panel.grid.minor.y = element_blank(),
      panel.grid.major.y = element_blank()
  )

# 5. Set fill color based on log2FC availability
if (use_log2fc_color) {{
  # Calculate the mean of the log2FC values to create a relative, high-contrast color scale.
  midpoint_val <- mean(enrich_data$avg_log2FC, na.rm = TRUE)

  final_plot <- bar_plot +
    geom_col(aes(fill = avg_log2FC)) +
    # Use the calculated midpoint to ensure a diverging scale (blue to red), similar to Python's.
    scale_fill_gradient2(
      low = "blue",
      mid = "white",
      high = "red",
      midpoint = midpoint_val,
      name = "Average log2FC"
    )
}} else {{
  final_plot <- bar_plot + geom_col(fill = "skyblue")
}}

# 6. Save the plot
ggsave(
  "{file_prefix}_bar_plot_from_R.png",
  plot = final_plot,
  width = {plot_kwargs.get('width', 10)},
  height = {plot_kwargs.get('height', 8)},
  dpi = 300,
  bg = "white"
)
"""
        elif plot_type == 'cnet':
            cnet_top_n = plot_kwargs.get('top_n', 5)
            if gene_log2fc_map:
                log2fc_data_path = os.path.join(r_output_dir, f"{file_prefix}_cnet_log2fc_data.csv")
                cleaned_fc_data = []
                processed_keys = set()
                for k, v in gene_log2fc_map.items():
                    if not isinstance(k, str): continue
                    cleaned_key = re.sub(r'\.\d+$', '', k)
                    if cleaned_key not in processed_keys:
                        cleaned_fc_data.append({'GeneID': cleaned_key, 'log2FC': v})
                        processed_keys.add(cleaned_key)
                if cleaned_fc_data:
                    pd.DataFrame(cleaned_fc_data).to_csv(log2fc_data_path, index=False, encoding='utf-8-sig')

            r_script_content = f"""
# R Script: Gene-Concept Network (cnet) Plot (Manual Version)

# 1. Load required packages
library(ggplot2)
library(dplyr)
library(ggraph)
library(igraph)
library(tidyr)

# 2. Load data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)
gene_log2fc <- NULL
log2fc_file <- "{os.path.basename(log2fc_data_path) if log2fc_data_path else 'NULL'}"
if (!is.null(log2fc_file) && file.exists(log2fc_file)) {{
  log2fc_data <- read.csv(log2fc_file)
  gene_log2fc <- setNames(log2fc_data$log2FC, log2fc_data$GeneID)
}}

# 3. Prepare data for network graphing
edge_list <- enrich_data %>%
  select(Description, Genes) %>%
  rename(from = Description, to = Genes) %>%
  separate_rows(to, sep = ";")
graph_obj <- graph_from_data_frame(edge_list, directed = FALSE)

# 4. Prepare node attributes
V(graph_obj)$type <- ifelse(V(graph_obj)$name %in% enrich_data$Description, "Term", "Gene")

if (!is.null(gene_log2fc)) {{
  # Map log2FC values to each node. Terms will have NA.
  V(graph_obj)$logFC <- gene_log2fc[V(graph_obj)$name]
}} else {{
  V(graph_obj)$logFC <- as.numeric(NA)
}}

# Set node size based on degree
node_degrees <- degree(graph_obj, V(graph_obj))
V(graph_obj)$size <- ifelse(V(graph_obj)$type == "Term", node_degrees, 3)

# 5. Create the plot using ggraph
set.seed(123)
cnet_plot <- ggraph(graph_obj, layout = 'fr') +
  geom_edge_link(alpha = 0.4, colour = 'grey50') +
  # Map color aesthetic directly to the numeric logFC attribute
  geom_node_point(aes(color = logFC, size = size), alpha = 0.8) +
  geom_node_text(aes(label = name), repel = TRUE, size = 3) +

  # Add the color scale, which will create the legend and color the nodes.
  # 'na.value' sets the color for Term nodes (where logFC is NA).
  scale_color_gradient2(
    name = "log2FC",
    low = "blue",
    mid = "white",
    high = "red",
    midpoint = 0,
    na.value = "skyblue"
  ) +

  scale_size_continuous(name = "Gene Count", range = c(3, 15)) +
  labs(
    title = "{analysis_title}",
    subtitle = "Gene-Concept Network"
  ) +
  theme_graph() +
  theme(
    plot.title = element_text(hjust = 0.5, face="bold"),
    legend.position = "right"
  ) +
  guides(size = guide_legend(order=1), color = guide_colorbar(order=2))

if (!is.null(gene_log2fc)) {{
  valid_fc_values <- na.omit(V(graph_obj)$logFC[V(graph_obj)$type == 'Gene'])
  if(length(valid_fc_values) > 0) {{
    midpoint_val <- mean(valid_fc_values, na.rm = TRUE)
    cnet_plot <- cnet_plot +
      scale_color_gradient2(
        name = "log2FC",
        low = "blue",
        mid = "white",
        high = "red",
        midpoint = midpoint_val,
        na.value = "skyblue"
      )
  }}
}} else {{
    # If there is no logFC data, ensure terms are still colored
    cnet_plot <- cnet_plot + scale_color_continuous(na.value = "skyblue")
}}

# 6. Save the plot
ggsave(
  "{file_prefix}_cnet_plot_from_R.png",
  plot = cnet_plot,
  width = 12, height = 12, dpi = 300, bg = "white"
)
"""

        elif plot_type == 'upset':
            r_script_content = f"""
# R Script: Upset Plot for Gene Set Intersections

# 1. Load required packages
# install.packages(c("UpSetR", "stringr"))
library(UpSetR)
library(stringr)

# 2. Load the data
enrich_data <- read.csv("{os.path.basename(data_path)}", stringsAsFactors = FALSE)

# 3. Prepare data for UpSetR
# Wrap long set names to prevent overlap
enrich_data$Description <- str_wrap(enrich_data$Description, width = 40)

# Create a named list where names are terms and values are gene vectors.
gene_list <- strsplit(enrich_data$Genes, ";")
names(gene_list) <- enrich_data$Description

# 4. Create and save the Upset plot
png("{file_prefix}_upset_plot_from_R.png", width = 1200, height = 700, res = 100)
upset(
  fromList(gene_list),
  sets = enrich_data$Description,
  nsets = nrow(enrich_data),
  nintersects = 40,
  order.by = "freq",

  # mb.ratio controls the height ratio of the main bar plot to the matrix.
  # c(0.4, 0.6) gives 40% height to the bar plot and 60% to the matrix.
  mb.ratio = c(0.4, 0.6),
  text.scale = 1.3,
  mainbar.y.label = "Intersection Size",
  sets.x.label = "Set Size"
)
dev.off() # Close the PNG device
"""

        if r_script_content:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(r_script_content)
            generated_files = [data_path, script_path]
            if log2fc_data_path: generated_files.append(log2fc_data_path)
            # 修改: 使用 logger
            logger.info(f"Successfully generated R script and data for '{plot_type}' plot.")
            return generated_files
        return None
    except Exception as e:
        # 修改: 使用 logger
        logger.error(f"An error occurred while generating the R script for plot type '{plot_type}': {e}")
        logger.debug(traceback.format_exc())
        return None
