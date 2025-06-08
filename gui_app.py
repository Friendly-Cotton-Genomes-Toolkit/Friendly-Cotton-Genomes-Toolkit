# gui_app.py
import copy
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import asdict, is_dataclass, fields
from queue import Queue
from tkinter import filedialog, font as tkfont
from typing import Callable, Dict, Optional, Any, Tuple

import customtkinter as ctk
import pandas as pd
import yaml
from PIL import Image

from cotton_toolkit.config.models import MainConfig, GenomeSourcesConfig

try:
    from cotton_toolkit.tools_pipeline import run_functional_annotation, run_ai_task, AIWrapper
    from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
        get_genome_data_sources
    from cotton_toolkit.core.downloader import download_genome_data
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg, run_homology_mapping_standalone, \
        run_gff_gene_lookup_standalone
    from cotton_toolkit.cli import setup_cli_i18n, APP_NAME_FOR_I18N, get_about_text
    from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL

    COTTON_TOOLKIT_LOADED = True
    print("INFO: gui_app.py - Successfully imported COTTON_TOOLKIT modules.")  #
except ImportError as e:
    print(f"错误：无法导入 cotton_toolkit 模块 (gui_app.py): {e}")  #
    COTTON_TOOLKIT_LOADED = False  #
    PKG_VERSION = "DEV"
    PKG_HELP_URL = "https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit/blob/master/docs/HELP.md"  #


    def load_config(config_path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(config_path):
            print(f"ERROR: 配置文件 '{config_path}' 未找到。")  # Changed to f-string for clarity
            return None
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                print(f"ERROR: 配置文件 '{config_path}' 的顶层结构必须是一个字典。")
                return None

            if data.get('config_version') != 1:
                # 使用 print 明确指出版本不兼容问题
                print(f"ERROR: 配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")
                raise ValueError(f"配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")

            # 将字典转换为 MainConfig 对象 (如果 COTTON_TOOLKIT_LOADED 为 True)
            if COTTON_TOOLKIT_LOADED:  # Ensure this check exists if it's a mock
                config_obj = MainConfig.from_dict(data)  #
            else:
                config_obj = data  # For mock, just return the dict

            # 确保 _config_file_abs_path_ 字段在返回前设置
            if isinstance(config_obj, MainConfig):
                config_obj._config_file_abs_path_ = os.path.abspath(config_path)
            elif isinstance(config_obj, dict):  # For mock scenario
                config_obj['_config_file_abs_path_'] = os.path.abspath(config_path)

            print(f"INFO: 配置文件 '{config_path}' 加载成功。")
            return config_obj
        except yaml.YAMLError as e:
            print(f"ERROR: 解析配置文件 '{config_path}' 失败: {e}")
            return None
        except ValueError as e:
            # 重新抛出版本错误，让调用者可以捕获
            raise e
        except Exception as e:
            print(f"ERROR: 加载配置文件 '{config_path}' 时发生未知错误: {e}")
            return None


    def save_config_to_yaml(config_dict, file_path):
        print(f"MOCK (gui_app.py): save_config_to_yaml({file_path})")  #
        with open(file_path, 'w', encoding='utf-8') as f: yaml.dump(config_dict, f)  #
        return True  #


    def get_genome_data_sources(main_config: MainConfig) -> Optional[Dict[str, Any]]:
        """【修正版】从主配置对象中获取或加载基因组数据源。"""
        # 直接通过对象属性访问，不再使用 .get()
        gs_file_rel = main_config.downloader.genome_sources_file
        if not gs_file_rel:
            print(_("错误: 主配置的 'downloader' 部分缺少 'genome_sources_file' 定义。"))
            return None

        main_config_dir = os.path.dirname(
            main_config._config_file_abs_path_) if main_config._config_file_abs_path_ else os.getcwd()
        gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

        if not os.path.exists(gs_file_path_abs):
            print(_("错误: 基因组源文件 '{}' 未找到。").format(gs_file_path_abs))
            return None

        try:
            with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data.get('list_version') != 1:
                # 对于这个函数，直接打印错误并返回None，因为调用它的地方较多，不适合都加异常处理
                print(_("错误: 基因组源文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(gs_file_path_abs))
                return None

            gs_config = GenomeSourcesConfig.from_dict(data)
            # 将 GenomeSourceItem 对象转换为字典，以兼容旧代码
            return {k: asdict(v) for k, v in gs_config.genome_sources.items()}
        except Exception as e:
            print(_("错误: 加载或解析基因组源文件 '{}' 失败: {}").format(gs_file_path_abs, e))
            return None


    def generate_default_config_files(
            output_dir: str,
            main_config_filename: str = "config.yml",
            genome_sources_filename: str = "genome_sources_list.yml",
            overwrite: bool = False
    ) -> Tuple[bool, str, str]:
        """通过实例化配置类来生成默认的配置文件，并支持覆盖选项。"""
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                print(_("错误: 创建目录 '{}' 失败: {}").format(output_dir, e))
                return False, "", ""

        main_config_path = os.path.join(output_dir, main_config_filename)
        genome_sources_path = os.path.join(output_dir, genome_sources_filename)

        success_main = False
        success_gs = False

        # 生成主配置文件，增加覆盖判断
        if os.path.exists(main_config_path) and not overwrite:
            print(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_path))
            success_main = True
        else:
            main_conf_default = MainConfig()
            main_conf_default.downloader.genome_sources_file = genome_sources_filename
            success_main = save_config(main_conf_default, main_config_path)

        # 生成基因组源文件，增加覆盖判断
        if os.path.exists(genome_sources_path) and not overwrite:
            print(_("警告: 基因组源文件 '{}' 已存在，跳过生成。").format(genome_sources_path))
            success_gs = True
        else:
            gs_conf_default = GenomeSourcesConfig()
            success_gs = save_config(gs_conf_default, genome_sources_path)

        return success_main and success_gs, main_config_path, genome_sources_path


    def download_genome_data(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("下载")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.DOWNLOAD_TASK_KEY, True, task_display_name)  #


    def integrate_bsa_with_hvg(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("整合分析")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.INTEGRATE_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_homology_mapping_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("同源映射")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.HOMOLOGY_MAP_TASK_KEY, True, task_display_name)  #
        return True  #


    def run_gff_gene_lookup_standalone(**kwargs):
        status_cb, progress_cb, task_done_cb = kwargs.get('status_callback'), kwargs.get(
            'progress_callback'), kwargs.get('task_done_callback')  #
        task_display_name = _("GFF基因查询")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 开始...")  #
        for i in range(101): time.sleep(0.005); progress_cb(i, f"MOCK: {task_display_name} {i}%")  #
        if status_cb: status_cb(f"MOCK: {task_display_name} 完成!");  #
        if task_done_cb: task_done_cb(CottonToolkitApp.GFF_QUERY_TASK_KEY, True, task_display_name)  #
        return True  #


    def setup_cli_i18n(language_code='en', app_name='cotton_toolkit'):  #
        return lambda s: str(s) + f" (mock_{language_code})"  #

# --- 全局翻译函数占位符 ---
_ = lambda s: str(s)  #


class CottonToolkitApp(ctk.CTk):
    LANG_CODE_TO_NAME = {"zh-hans": "简体中文", "zh-hant": "繁體中文", "en": "English", "ja": "日本語"}
    LANG_NAME_TO_CODE = {v: k for k, v in LANG_CODE_TO_NAME.items()}

    # --- AI服务商及其元数据 ---
    AI_PROVIDERS = {
        "google": {"name": "Google Gemini"},
        "openai": {"name": "OpenAI"},
        "deepseek": {"name": "DeepSeek (月之暗面)"},
        "qwen": {"name": "Qwen (通义千问)"},
        "siliconflow": {"name": "SiliconFlow (硅基流动)"},
        "openai_compatible": {"name": _("通用OpenAI兼容接口")}
    }

    def __init__(self):
        super().__init__()

        self.title_text_key = "友好棉花基因组工具包 - FCGT"
        self.title(_(self.title_text_key))
        self.geometry("1000x700")
        self.minsize(1000, 700)


        # --- 【第1步】初始化所有变量，为后续方法做准备 ---
        self.log_queue = queue.Queue()
        self.current_config: Optional[MainConfig] = None
        self.config_path: Optional[str] = None
        self.ui_settings: Dict[str, Any] = {}
        self.message_queue: Queue = Queue()
        self.about_window: Optional[ctk.CTkToplevel] = None
        self.translatable_widgets: Dict[ctk.CTkBaseClass, Any] = {}
        self.active_task_name: Optional[str] = None
        self.log_viewer_visible: bool = False
        self.error_dialog_lock: threading.Lock = threading.Lock()
        self.tool_tab_frames: Dict[str, ctk.CTkFrame] = {}

        # 记录每个工具选项卡是否已加载其UI
        self.tool_tab_ui_loaded: Dict[str, bool] = {}  #
        self.editor_widgets: Dict[str, Any] = {}
        self.tab_keys: Dict[str, str] = {
            "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
            "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
        }

        # 用于管理异步启动加载状态的变量和队列
        self.initial_config_loaded = threading.Event() # 用于标记初始配置是否加载完成
        self.initial_ui_setup_done = threading.Event() # 用于标记初始UI设置是否完成
        self.startup_progress_queue = Queue() # 用于启动时的进度和状态更新

        # 新增：启动阶段UI更新任务的完成标志
        self.startup_ui_tasks_completed = {
            "config_applied": False,  # _apply_config_to_ui_async 完成
            "editor_populated": False,  # _populate_editor_ui 完成
            "genome_dropdowns_updated": False  # _update_assembly_id_dropdowns 收到异步消息并更新
        }

        # 标记配置编辑器UI是否已加载
        self.editor_ui_loaded: bool = False  #

        # 用于取消模型获取的事件和进度弹窗
        self.cancel_model_fetch_event: threading.Event = threading.Event()
        self.progress_dialog: Optional[ctk.CTkToplevel] = None
        self.progress_dialog_text_var: Optional[tk.StringVar] = None
        self.progress_dialog_bar: Optional[ctk.CTkProgressBar] = None


        self.excel_sheet_cache = {}  # 新增：用于缓存Excel文件的工作表名称，避免重复读取

        # 定义配置编辑器的结构
        # 键是配置文件中的路径 (点分隔)，值是 (显示名称, 提示文本, UI类型, 默认值/选项列表)
        # UI类型: "entry", "switch", "textbox", "optionmenu", "model_selector"
        self.config_structure = {  #
            "downloader": {  #
                "title": _("数据下载器配置"),  #
                "items": {  #
                    "genome_sources_file": (_("基因组源文件"), _("定义基因组下载链接的YAML文件路径。"), "entry",
                                            "genome_sources_list.yml"),  #
                    "download_output_base_dir": (_("下载输出根目录"), _("所有下载文件存放的基准目录。"), "entry",
                                                 "downloaded_cotton_data"),  #
                    "force_download": (_("强制重新下载"), _("如果文件已存在，是否强制重新下载。"), "switch", False),  #
                    "max_workers": (_("最大下载线程数"), _("多线程下载时使用的最大线程数。"), "entry", 3),  #
                    "proxies": {  #
                        "title": _("网络代理设置 (可选)"),  #
                        "items": {  #
                            "http": (_("HTTP代理"), _("HTTP代理地址，例如 'http://your-proxy:port'。不使用则留空。"),
                                     "entry", None),  #
                            "https": (_("HTTPS代理"), _("HTTPS代理地址，例如 'https://your-proxy:port'。不使用则留空。"),
                                      "entry", None)  #
                        }
                    }
                }
            },
            "ai_services": {  #
                "title": _("AI 服务配置"),  #
                "items": {  #
                    "default_provider": (_("默认AI服务商"), _("选择默认使用的AI模型提供商。"), "optionmenu",
                                         list(self.AI_PROVIDERS.keys())),  #
                    "providers": {  #
                        "title": _("AI 服务商详情"),  #
                        "items": {  #
                            "google": {  #
                                "title": "Google Gemini",  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("您的Google Gemini API密钥。"), "entry",
                                                "YOUR_GOOGLE_API_KEY"),  #
                                    "model": (_("模型名称"), _("要使用的Google Gemini模型名称。"), "model_selector",
                                              "models/gemini-1.5-flash-latest"),  #
                                    "base_url": (_("Base URL"), _("Google Gemini API的基础URL。"), "entry",
                                                 "https://generativelanguage.googleapis.com/v1beta")  #
                                }
                            },
                            "openai": {  #
                                "title": "OpenAI",  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("您的OpenAI API密钥。"), "entry", "YOUR_OPENAI_API_KEY"),
                                    #
                                    "model": (_("模型名称"), _("要使用的OpenAI模型名称。"), "model_selector",
                                              "gpt-4o-mini"),  #
                                    "base_url": (_("Base URL"), _("OpenAI API的基础URL。"), "entry",
                                                 "https://api.openai.com/v1")  #
                                }
                            },
                            "deepseek": {  #
                                "title": "DeepSeek",  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("您的DeepSeek API密钥。"), "entry",
                                                "YOUR_DEEPSEEK_API_KEY"),  #
                                    "model": (_("模型名称"), _("要使用的DeepSeek模型名称。"), "model_selector",
                                              "deepseek-chat"),  #
                                    "base_url": (_("Base URL"), _("DeepSeek API的基础URL。"), "entry",
                                                 "https://api.deepseek.com/v1")  #
                                }
                            },
                            "qwen": {  #
                                "title": "Qwen",  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("您的通义千问API密钥。"), "entry", "YOUR_QWEN_API_KEY"),
                                    #
                                    "model": (_("模型名称"), _("要使用的通义千问模型名称。"), "model_selector",
                                              "qwen-turbo"),  #
                                    "base_url": (_("Base URL"), _("通义千问API的基础URL。"), "entry",
                                                 "https://dashscope.aliyuncs.com/api/v1")  #
                                }
                            },
                            "siliconflow": {  #
                                "title": "SiliconFlow",  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("您的SiliconFlow API密钥。"), "entry",
                                                "YOUR_SILICONFLOW_API_KEY"),  #
                                    "model": (_("模型名称"), _("要使用的SiliconFlow模型名称。"), "model_selector",
                                              "alibaba/Qwen2-7B-Instruct"),  #
                                    "base_url": (_("Base URL"), _("SiliconFlow API的基础URL。"), "entry",
                                                 "https://api.siliconflow.cn/v1")  #
                                }
                            },
                            "openai_compatible": {  #
                                "title": _("通用OpenAI兼容接口"),  #
                                "items": {  #
                                    "api_key": (_("API Key"), _("自定义API密钥。"), "entry", "YOUR_CUSTOM_API_KEY"),  #
                                    "model": (_("模型名称"), _("要使用的自定义模型名称。"), "model_selector",
                                              "custom-model"),  #
                                    "base_url": (_("Base URL"), _("自定义OpenAI兼容API的基础URL。"), "entry",
                                                 "http://localhost:8000/v1")  #
                                }
                            },
                        }
                    }
                }
            },
            "ai_prompts": {  #
                "title": _("AI 提示词模板"),  #
                "items": {  #
                    "translation_prompt": (_("翻译提示词"), _("用于翻译任务的提示词模板。必须包含 {text} 占位符。"),
                                           "textbox",
                                           "请将以下生物学领域的文本翻译成中文：\\n\\n---\\n{text}\\n---\\n\\n请只返回翻译结果，不要包含任何额外的解释或说明。"),
                    #
                    "analysis_prompt": (_("分析提示词"), _("用于分析任务的提示词模板。必须包含 {text} 占位符。"),
                                        "textbox",
                                        "我正在研究植物雄性不育，请分析以下基因功能描述与我的研究方向有何关联，并提供一个简洁的总结。基因功能描述：\\n\\n---\\n{text}\\n---")
                    #
                }
            },
            "annotation_tool": {  #
                "title": _("功能注释工具配置"),  #
                "items": {  #
                    "database_root_dir": (_("数据库根目录"), _("存放注释数据库文件的目录。"), "entry",
                                          "annotation_databases"),  #
                    "database_files": {  #
                        "title": _("数据库文件"),  #
                        "items": {  #
                            "go": (_("GO注释文件"), _("Gene Ontology注释文件路径。"), "entry",
                                   "AD1_HAU_v1.0_genes2Go.csv"),  #
                            "ipr": (_("InterPro注释文件"), _("InterPro注释文件路径。"), "entry",
                                    "AD1_HAU_v1.0_genes2IPR.csv"),  #
                            "kegg_orthologs": (_("KEGG Orthologs文件"), _("KEGG直系同源注释文件路径。"), "entry",
                                               "AD1_HAU_v1.0_KEGG-orthologs.csv"),  #
                            "kegg_pathways": (_("KEGG Pathways文件"), _("KEGG通路注释文件路径。"), "entry",
                                              "AD1_HAU_v1.0_KEGG-pathways.csv"),  #
                        }
                    },
                    "database_columns": {  #
                        "title": _("数据库列名"),  #
                        "items": {  #
                            "query": (_("查询列名"), _("数据库文件中用于查询的列名。"), "entry", "Query"),  #
                            "match": (_("匹配列名"), _("数据库文件中用于匹配的列名。"), "entry", "Match"),  #
                            "description": (_("描述列名"), _("数据库文件中描述信息的列名。"), "entry", "Description"),  #
                        }
                    }
                }
            },
            "integration_pipeline": {  #
                "title": _("整合分析流程配置"),  #
                "items": {  #
                    "input_excel_path": (_("输入Excel路径"), _("包含BSA和HVG数据的Excel文件路径。"), "entry",
                                         "path/to/your/input_data.xlsx"),  #
                    "bsa_sheet_name": (_("BSA工作表名"), _("输入Excel中BSA数据的工作表名称。"), "entry", "BSA_Results"),
                    #
                    "hvg_sheet_name": (_("HVG工作表名"), _("输入Excel中HVG数据的工作表名称。"), "entry", "HVG_List"),  #
                    "output_sheet_name": (_("输出工作表名"), _("整合分析结果将被写入的新工作表名称。"), "entry",
                                          "Combined_BSA_HVG_Analysis"),  #
                    "bsa_assembly_id": (_("BSA基因组版本ID"), _("BSA数据所基于的基因组版本ID。"), "entry", "NBI_v1.1"),
                    #
                    "hvg_assembly_id": (_("HVG基因组版本ID"),
                                        _("HVG数据所基于的基因组版本ID。如果与BSA版本相同，则跳过同源映射。"), "entry",
                                        "HAU_v2.0"),  #
                    "bridge_species_name": (_("桥梁物种名"), _("用于跨版本同源映射的桥梁物种名称。"), "entry",
                                            "Arabidopsis_thaliana"),  #
                    "gff_db_storage_dir": (_("GFF数据库缓存目录"), _("gffutils数据库文件的缓存目录。"), "entry",
                                           "gff_databases_cache"),  #
                    "force_gff_db_creation": (_("强制创建GFF数据库"), _("即使缓存已存在，也强制重新创建GFF数据库。"),
                                              "switch", False),  #
                    "gff_files": {  #
                        "title": _("GFF文件路径 (可选覆盖)"),  #
                        "items": {  #
                            "NBI_v1.1": (_("NBI_v1.1 GFF"), _("手动指定NBI_v1.1 GFF文件路径。留空则自动推断。"), "entry",
                                         None),  #
                            "HAU_v2.0": (_("HAU_v2.0 GFF"), _("手动指定HAU_v2.0 GFF文件路径。留空则自动推断。"), "entry",
                                         None),  #
                            # 可以在这里添加更多版本
                        }
                    },
                    "homology_files": {  #
                        "title": _("同源文件路径 (可选覆盖)"),  #
                        "items": {  #
                            "bsa_to_bridge_csv": (_("BSA到桥梁文件"),
                                                  _("手动指定BSA基因组到桥梁物种的同源关系CSV文件路径。"), "entry",
                                                  None),  #
                            "bridge_to_hvg_csv": (_("桥梁到HVG文件"),
                                                  _("手动指定桥梁物种到HVG基因组的同源关系CSV文件路径。"), "entry",
                                                  None),  #
                        }
                    },
                    "bsa_columns": {  #
                        "title": _("BSA列名映射"),  #
                        "items": {  #
                            "chr": (_("染色体列"), _("BSA数据中染色体或支架ID的列名。"), "entry", "chr"),  #
                            "start": (_("起始位置列"), _("BSA数据中区域起始位置的列名。"), "entry", "region.start"),  #
                            "end": (_("结束位置列"), _("BSA数据中区域结束位置的列名。"), "entry", "region.end"),  #
                        }
                    },
                    "hvg_columns": {  #
                        "title": _("HVG列名映射"),  #
                        "items": {  #
                            "gene_id": (_("基因ID列"), _("HVG数据中基因ID的列名。"), "entry", "gene_id"),  #
                            "category": (_("分类列"), _("HVG数据中基因分类的列名。"), "entry", "hvg_category"),  #
                            "log2fc": (_("Log2FC列"), _("HVG数据中Log2FC值的列名。"), "entry", "log2fc_WT_vs_Ms1"),  #
                        }
                    },
                    "homology_columns": {  #
                        "title": _("同源文件列名映射"),  #
                        "items": {  #
                            "query": (_("查询ID列"), _("同源文件中查询ID的列名。"), "entry", "Query"),  #
                            "match": (_("匹配ID列"), _("同源文件中匹配ID的列名。"), "entry", "Match"),  #
                            "evalue": (_("E-value列"), _("同源文件中E-value的列名。"), "entry", "Exp"),  #
                            "score": (_("Score列"), _("同源文件中Score的列名。"), "entry", "Score"),  #
                            "pid": (_("PID列"), _("同源文件中PID (Identity) 的列名。"), "entry", "PID"),  #
                        }
                    },
                    "selection_criteria_source_to_bridge": {  #
                        "title": _("源到桥梁筛选标准"),  #
                        "items": {  #
                            "sort_by": (_("排序依据"), _("排序结果的优先级列表 (如 Score, Exp, PID)。"), "entry",
                                        "Score,Exp"),  # List as comma-separated string
                            "ascending": (_("升序/降序"), _("与排序依据对应的升序 (True) / 降序 (False) 列表。"),
                                          "entry", "False,True"),  # List as comma-separated string
                            "top_n": (_("Top N"), _("每个查询基因选择的最佳匹配数量。"), "entry", 1),  #
                            "evalue_threshold": (_("E-value阈值"), _("匹配E-value的最大值。"), "entry", 1.0e-10),  #
                            "pid_threshold": (_("PID阈值"), _("匹配PID的最小值。"), "entry", 30.0),  #
                            "score_threshold": (_("Score阈值"), _("匹配Score的最小值。"), "entry", 50.0),  #
                        }
                    },
                    "selection_criteria_bridge_to_target": {  #
                        "title": _("桥梁到目标筛选标准"),  #
                        "items": {  #
                            "sort_by": (_("排序依据"), _("排序结果的优先级列表 (如 Score, Exp, PID)。"), "entry",
                                        "Score,Exp"),  #
                            "ascending": (_("升序/降序"), _("与排序依据对应的升序 (True) / 降序 (False) 列表。"),
                                          "entry", "False,True"),  #
                            "top_n": (_("Top N"), _("每个查询基因选择的最佳匹配数量。"), "entry", 1),  #
                            "evalue_threshold": (_("E-value阈值"), _("匹配E-value的最大值。"), "entry", 1.0e-15),  #
                            "pid_threshold": (_("PID阈值"), _("匹配PID的最小值。"), "entry", 40.0),  #
                            "score_threshold": (_("Score阈值"), _("匹配Score的最小值。"), "entry", 80.0),  #
                        }
                    },
                    "common_hvg_log2fc_threshold": (_("共同HVG Log2FC阈值"),
                                                    _("用于判断“共同TopHVG”类别基因表达差异是否显著的Log2FC绝对值阈值。"),
                                                    "entry", 1.0),  #
                }
            }
        }

        self.placeholder_genes_homology_key: str = "例如:\nGhir.A01G000100\nGhir.A01G000200\n(每行一个基因ID，或逗号分隔)"
        self.placeholder_genes_gff_key: str = "例如:\nGhir.D05G001800\nGhir.D05G001900\n(每行一个基因ID，与下方区域查询二选一)"

        self.DOWNLOAD_TASK_KEY = "download"
        self.INTEGRATE_TASK_KEY = "integrate"
        self.HOMOLOGY_MAP_TASK_KEY = "homology_map"
        self.GFF_QUERY_TASK_KEY = "gff_query"

        # 初始化 Tkinter 变量
        self.selected_language_var = tk.StringVar()
        self.selected_appearance_var = tk.StringVar()
        self.ai_task_type_var = tk.StringVar(value=_("翻译"))
        self.go_anno_var = tk.BooleanVar(value=True)
        self.ipr_anno_var = tk.BooleanVar(value=True)
        self.kegg_ortho_anno_var = tk.BooleanVar(value=False)
        self.kegg_path_anno_var = tk.BooleanVar(value=False)
        self.selected_bsa_assembly = tk.StringVar()
        self.selected_hvg_assembly = tk.StringVar()
        self.selected_bsa_sheet = tk.StringVar()
        self.selected_hvg_sheet = tk.StringVar()
        self.selected_homology_source_assembly = tk.StringVar()
        self.selected_homology_target_assembly = tk.StringVar()
        self.selected_gff_query_assembly = tk.StringVar()
        self.download_force_checkbox_var = tk.BooleanVar()
        self.download_genome_vars: Dict[str, tk.BooleanVar] = {}
        self.download_proxy_var = tk.BooleanVar(value=False)
        self.ai_proxy_var = tk.BooleanVar(value=False)


        # --- 【第2步】设置字体，因为后续创建UI都需要它 ---
        self._setup_fonts()

        # --- 【第3步】设置颜色变量和加载图标 ---
        self.secondary_text_color = ("#495057", "#999999")
        self.placeholder_color = ("#868e96", "#5c5c5c")
        self.default_text_color = ctk.ThemeManager.theme["CTkTextbox"]["text_color"]
        try:
            self.default_label_text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        except Exception:
            self.default_label_text_color = ("#000000", "#FFFFFF")

        self.logo_image = self._load_image_resource("logo.png", (48, 48))
        self.home_icon = self._load_image_resource("home.png")
        self.integrate_icon = self._load_image_resource("integrate.png")
        self.tools_icon = self._load_image_resource("tools.png")
        self.settings_icon = self._load_image_resource("settings.png")
        self.folder_icon = self._load_image_resource("folder.png")
        self.new_file_icon = self._load_image_resource("new-file.png")
        self.help_icon = self._load_image_resource("help.png")
        self.info_icon = self._load_image_resource("info.png")

        # --- 【第4步】加载UI设置（如主题），这会影响控件外观 ---
        self._load_ui_settings()

        # --- 【第5步】创建基础UI布局（如状态栏、日志区、导航栏）---
        self._create_layout()

        # --- 【第6步】最后，创建并填充所有主页面，并完成最终设置 ---
        self._init_pages_and_final_setup()

        self._start_app_async_startup()

    def toggle_log_viewer(self):
        """切换日志文本框的可见性。"""
        if self.log_viewer_visible:
            # 当前可见，则隐藏
            self.log_textbox.grid_remove()
            self.toggle_log_button.configure(text=_("显示日志"))
            self.log_viewer_visible = False
        else:
            # 当前隐藏，则显示
            self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
            self.toggle_log_button.configure(text=_("隐藏日志"))
            self.log_viewer_visible = True

    def _fetch_ai_models(self, provider_key: str):
        """无需保存，直接从UI输入框获取API Key和URL来刷新模型列表。"""
        self._log_to_viewer(
            f"{_('正在获取')} '{self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)}' {_('的模型列表...')} ")

        try:
            # Directly get the corresponding UI widget from self.editor_widgets and its current value
            api_key_widget_path = f"ai_services.providers.{provider_key}.api_key"
            base_url_widget_path = f"ai_services.providers.{provider_key}.base_url"

            api_key_widget = self.editor_widgets.get(api_key_widget_path)
            api_key = api_key_widget.get().strip() if api_key_widget else None

            base_url = None
            base_url_widget = self.editor_widgets.get(base_url_widget_path)
            # Handle optionmenu and entry for base_url if it's a model selector too (though usually base_url is entry)
            # 这里 base_url 应该总是 entry 类型，所以简化获取方式
            if isinstance(base_url_widget, ctk.CTkEntry):
                base_url = base_url_widget.get().strip()
            # 如果是 model_selector 本身，它是一个元组 (frame, entry, dropdown, dropdown_var, button)
            # 但这里我们只是获取 base_url，它通常只是一个 Entry
            elif isinstance(base_url_widget, tuple) and len(base_url_widget) == 5:
                # 理论上 base_url 不会是 model_selector，但如果结构变了，这里做个防护
                _frame, entry_widget, dropdown_widget, dropdown_var, _button = base_url_widget
                base_url = entry_widget.get().strip()
            elif base_url_widget: # normal entry
                base_url = base_url_widget.get().strip()


            if not api_key or "YOUR_" in api_key:
                self.show_warning_message(_("缺少API Key"),
                                          _("请先在上方输入框中为 '{}' 填写有效的API Key。").format(provider_key))
                return
        except Exception as e:
            self._log_to_viewer(f"{_('读取配置编辑器UI失败:')} {e}", "ERROR")
            return

        # 清除之前的取消事件，为新的获取任务做准备
        self.cancel_model_fetch_event.clear()
        self._show_progress_dialog(
            title=_("获取模型列表"),
            message=_("正在从 {} 获取模型列表，请稍候...").format(
                self.AI_PROVIDERS.get(provider_key, {}).get('name', provider_key)),
            on_cancel=lambda: self.cancel_model_fetch_event.set()
        )

        def fetch_in_thread():
            try:
                timeout_seconds = 30
                models = AIWrapper.get_models(
                    provider=provider_key,
                    api_key=api_key,
                    base_url=base_url,
                    cancel_event=self.cancel_model_fetch_event,
                    timeout=timeout_seconds
                )
                if self.cancel_model_fetch_event.is_set():
                    self.message_queue.put(("ai_models_failed", (provider_key, _("操作已取消"))))
                    return

                self.message_queue.put(("ai_models_fetched", (provider_key, models)))
            except Exception as e:
                self.message_queue.put(("ai_models_failed", (provider_key, str(e))))
            finally:
                self.message_queue.put(("hide_progress_dialog", None))


        threading.Thread(target=fetch_in_thread, daemon=True).start()

    def _show_progress_dialog(self, title: str, message: str, on_cancel: Optional[Callable] = None):
        """显示一个模态的进度弹窗，包含进度条和取消按钮。"""
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.destroy()  # 销毁任何已存在的弹窗，避免重复

        self.progress_dialog = ctk.CTkToplevel(self)
        self.progress_dialog.title(title)
        self.progress_dialog.transient(self)  # 使其模态化，阻止与主窗口交互
        self.progress_dialog.grab_set()  # 捕获焦点
        self.progress_dialog.resizable(False, False)
        self.progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁用关闭按钮，强制通过代码控制

        main_frame = ctk.CTkFrame(self.progress_dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.progress_dialog_text_var = tk.StringVar(value=message)
        ctk.CTkLabel(main_frame, textvariable=self.progress_dialog_text_var,
                     font=self.app_font, wraplength=300, justify="center").pack(pady=10, padx=10)

        self.progress_dialog_bar = ctk.CTkProgressBar(main_frame, width=250, mode="indeterminate")
        self.progress_dialog_bar.pack(pady=10)
        self.progress_dialog_bar.start()  # 启动不确定模式动画

        if on_cancel:  # 如果提供了取消回调函数，则显示取消按钮
            cancel_button = ctk.CTkButton(main_frame, text=_("强制停止"), command=on_cancel, font=self.app_font)
            cancel_button.pack(pady=(10, 0))

        # 居中弹窗
        self.progress_dialog.update_idletasks()  # 强制更新以获取实际尺寸
        x = self.winfo_x() + (self.winfo_width() // 2) - (self.progress_dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (self.progress_dialog.winfo_height() // 2)
        self.progress_dialog.geometry(f"+{x}+{y}")
        self.progress_dialog.deiconify()  # 显示弹窗

    def _hide_progress_dialog(self):
        """隐藏并销毁进度弹窗。"""
        if self.progress_dialog and self.progress_dialog.winfo_exists():
            self.progress_dialog.grab_release()  # 释放焦点
            self.progress_dialog.destroy()  # 销毁弹窗
            self.progress_dialog = None
            self.progress_dialog_text_var = None
            self.progress_dialog_bar = None

    def _create_log_viewer_widgets(self):
        """创建并打包操作日志区域的全部控件，并添加折叠功能。"""
        self.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(self.log_viewer_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        self.log_viewer_label_widget = ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold)
        self.log_viewer_label_widget.grid(row=0, column=0, sticky="w")
        self.translatable_widgets[self.log_viewer_label_widget] = "操作日志"

        # 创建一个按钮容器
        buttons_sub_frame = ctk.CTkFrame(log_header_frame, fg_color="transparent")
        buttons_sub_frame.grid(row=0, column=1, sticky="e")

        # 添加新的“显示/隐藏”按钮
        self.toggle_log_button = ctk.CTkButton(buttons_sub_frame, text=_("显示日志"), width=90, height=28,
                                               command=self.toggle_log_viewer, font=self.app_font)
        self.toggle_log_button.pack(side="left", padx=(0, 10))
        self.translatable_widgets[self.toggle_log_button] = ("toggle_button", "显示日志", "隐藏日志")  # 特殊注册

        self.clear_log_button = ctk.CTkButton(buttons_sub_frame, text=_("清除日志"), width=80, height=28,
                                              command=self.clear_log_viewer, font=self.app_font)
        self.clear_log_button.pack(side="left")
        self.translatable_widgets[self.clear_log_button] = "清除日志"

        # 创建日志文本框，但先不显示
        self.log_textbox = ctk.CTkTextbox(self.log_viewer_frame, height=140, state="disabled", wrap="word",
                                          font=self.app_font)
        # 注意：这里只创建，不调用 .grid()，因为它默认是隐藏的

        self._update_log_tag_colors()

    def _update_log_tag_colors(self):
        """根据当前的外观模式更新日志文本框的标签颜色。"""
        if hasattr(self, 'log_textbox') and self.log_textbox.winfo_exists():
            # 获取当前是 "Light" 还是 "Dark" 模式
            current_mode = ctk.get_appearance_mode()

            # 根据模式选择对应的单一颜色值
            error_color = "#d9534f" if current_mode == "Light" else "#e57373"
            warning_color = "#f0ad4e" if current_mode == "Light" else "#ffb74d"

            # 使用单一颜色值为 tag 进行配置
            self.log_textbox.tag_config("error_log", foreground=error_color)
            self.log_textbox.tag_config("warning_log", foreground=warning_color)



    def _create_status_bar_widgets(self):
        """创建并打包状态栏的全部控件。"""
        self.status_bar_frame.grid_columnconfigure(0, weight=1)

        # 1. 状态文本标签
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        # 2. 进度条
        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()  # 默认隐藏，只在任务进行时显示

    def _create_layout(self):
        self.status_bar_frame = ctk.CTkFrame(self, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self._create_status_bar_widgets()
        self.log_viewer_frame = ctk.CTkFrame(self)
        self.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self._create_log_viewer_widgets()
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(side="top", fill="both", expand=True)
        self.top_frame.grid_columnconfigure(1, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1)
        self._create_navigation_frame(parent=self.top_frame)
        self._create_main_content_area(parent=self.top_frame)

        # gui_app.py

    def _init_pages_and_final_setup(self):
        # 1. 创建所有主内容区域的 Frame 并赋值给 self 属性
        self.home_frame = self._create_home_frame(self.main_content_frame)
        self.editor_frame = self._create_editor_frame(self.main_content_frame)
        self.integrate_frame = self._create_integrate_frame(self.main_content_frame)
        self.tools_frame = self._create_tools_frame(self.main_content_frame)

        # 2. 同步填充所有工具选项卡的内容 (不再懒加载)
        # 这将创建所有工具页面的UI元素
        self._populate_tools_notebook()

        # 3. 同步构建配置编辑器 UI
        # _populate_editor_ui 内部会检查 self.editor_widgets 是否为空，然后进行一次构建。
        # 此时 self.editor_widgets 肯定是空的，所以它会进行完整构建。
        self._populate_editor_ui()

        # 4. 设置初始显示的页面 (例如 "home")
        self.select_frame_by_name("home")

        # 5. 更新UI语言和按钮状态 (这些方法现在可以安全地调用，因为所有基础UI元素都已创建)
        self.update_language_ui()
        self._update_button_states()

        # 6. 启动消息队列的周期性检查 (确保主线程能够处理来自后台的消息)
        self.check_queue_periodic()

        # 7. 设置窗口关闭协议和应用程序图标
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_app_icon()

    def _start_app_async_startup(self):
        """
        Orchestrates the asynchronous startup process for the entire application.
        This is called once at the end of __init__ to kick off loading and UI creation.
        """
        # 立即显示启动进度对话框
        self._show_progress_dialog(
            title=_("图形界面启动中..."),  # <-- 确认这里的文本
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None  # 启动阶段不允许取消
        )

        def startup_task_thread():
            try:
                # 1. 加载 config.yml
                self.startup_progress_queue.put((10, _("加载配置文件...")))
                default_config_path = "config.yml"
                loaded_config_data = None
                config_file_path = None

                print(f"DEBUG_LOAD: 尝试从路径 '{os.path.abspath(default_config_path)}' 加载配置文件。")


                if os.path.exists(default_config_path):
                    try:
                        loaded_config_data = load_config(os.path.abspath(default_config_path))
                        config_file_path = os.path.abspath(default_config_path)
                    except ValueError as e:
                        self.startup_progress_queue.put((100, f"[ERROR] {_('配置文件版本不兼容:')} {e}"))
                        return  # Exit thread on error
                    except Exception as e:
                        self.startup_progress_queue.put((100, f"[ERROR] {_('加载配置文件失败:')} {e}"))
                        return  # Exit thread on error
                else:
                    self.startup_progress_queue.put((100, _("未找到默认 config.yml，请手动加载或生成。")))
                    loaded_config_data = None
                    config_file_path = None

                # 2. 加载基因组源数据 (依赖 loaded_config_data 获取路径)
                self.startup_progress_queue.put((30, _("加载基因组数据源...")))
                genome_sources_data = get_genome_data_sources(loaded_config_data)

                # --- 发送数据到主线程并触发UI更新 ---
                # These messages will be processed by check_queue_periodic on the main thread.

                # 首先，在主线程中设置 self.current_config 和 self.config_path
                self.message_queue.put(("set_initial_config_and_path", (loaded_config_data, config_file_path)))

                # 然后，应用加载的配置值到UI（包括编辑器UI，它此时已创建）
                self.startup_progress_queue.put((70, _("应用配置到UI...")))
                self.message_queue.put(("trigger_apply_config_to_ui_values", None))

                # 最后，更新基因组下拉菜单（它会从 self.current_config 读取数据）
                self.startup_progress_queue.put((80, _("更新基因组下拉菜单...")))
                self.message_queue.put(("trigger_update_assembly_dropdowns", None))

                # --- 最终化和完成消息 ---
                self.startup_progress_queue.put((90, _("完成基本初始化...")))
                self.initial_config_loaded.set()  # 标记异步配置加载完成

            except Exception as e:
                self.startup_progress_queue.put((100, f"[ERROR] {_('启动过程中发生未知错误:')} {e}"))
                self.initial_config_loaded.set()
            finally:
                self.startup_progress_queue.put((100, _("启动完成！")))  # Final progress message

        threading.Thread(target=startup_task_thread, daemon=True).start()


    def _create_editor_frame(self, parent):
        """
        创建配置编辑器的主框架，现在恢复到更紧凑的原始顶部布局。
        包含警告、滚动区域和保存按钮。
        """
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1) # 第1行用于滚动框架

        top_frame = ctk.CTkFrame(page, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_frame.grid_columnconfigure(0, weight=1)

        warning_color = ("#D32F2F", "#E57373")
        ctk.CTkLabel(top_frame, text=_("!! 警告: 配置文件可能包含API Key等敏感信息，请勿轻易分享给他人。"),
                     font=self.app_font_bold, text_color=warning_color).grid(row=0, column=0, sticky="w", padx=5)

        self.save_editor_button = ctk.CTkButton(top_frame, text=_("应用并保存配置"), command=self._save_config_from_editor,
                                               font=self.app_font)
        self.save_editor_button.grid(row=0, column=1, sticky="e", padx=5)


        self.editor_scroll_frame = ctk.CTkScrollableFrame(page)
        self.editor_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
        self._bind_mouse_wheel_to_scrollable(self.editor_scroll_frame)

        # Add a placeholder label for when no config is loaded
        self.editor_no_config_label = ctk.CTkLabel(self.editor_scroll_frame, text=_("请先从“主页”加载或生成一个配置文件。"),
                                                   font=self.app_subtitle_font, text_color=self.secondary_text_color)
        self.editor_no_config_label.grid(row=0, column=0, pady=50, sticky="nsew")
        self.editor_scroll_frame.grid_rowconfigure(0, weight=1) # Center the message if it's the only thing


        return page


    def _get_settings_path(self):
        """获取UI设置文件的路径"""
        # 将设置文件保存在程序根目录，方便用户查找和管理
        return "ui_settings.json"

    def _load_ui_settings(self):
        """加载UI设置，如果文件不存在则使用默认值"""
        settings_path = self._get_settings_path()
        # 默认值
        defaults = {"language": "zh-hans", "appearance_mode": "System"}

        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self.ui_settings = json.load(f)
            else:
                self.ui_settings = defaults
        except (json.JSONDecodeError, IOError):
            # 如果文件损坏或无法读取，也使用默认值
            self.ui_settings = defaults

        # 仅应用主题，不设置变量，变量的设置统一由 update_language_ui 管理
        ctk.set_appearance_mode(self.ui_settings.get("appearance_mode", "System"))

    def _save_ui_settings(self):
        """保存当前的UI设置到文件"""
        settings_path = self._get_settings_path()
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.ui_settings, f, indent=4)
            self._log_to_viewer(_("界面设置已保存。"))
        except IOError as e:
            self._log_to_viewer(f"{_('错误: 无法保存界面设置:')} {e}", "ERROR")

    def _show_custom_dialog(self, title, message, buttons, icon_type=None):
        # 1. 创建窗口并立即隐藏，避免闪烁
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()

        # 2. 设置窗口基础属性
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)

        result = [None]

        # 3. 创建并打包所有内部控件 (这部分代码不变)
        main_frame = ctk.CTkFrame(dialog, corner_radius=10)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(padx=10, pady=10, fill="both", expand=True)
        icon_text = ""
        if icon_type == "error":
            icon_text = "❌"
        elif icon_type == "warning":
            icon_text = "⚠️"
        elif icon_type == "question":
            icon_text = "❓"
        elif icon_type == "info":
            icon_text = "ℹ️"
        if icon_text:
            ctk.CTkLabel(content_frame, text=icon_text, font=("Segoe UI Emoji", 26)).pack(pady=(10, 10))
        ctk.CTkLabel(content_frame, text=message, font=self.app_font, wraplength=400, justify="center").pack(
            pady=(0, 20), padx=10, fill="x")
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=(10, 10), anchor="center")

        def on_button_click(button_text):
            result[0] = button_text
            dialog.destroy()

        for i, button_text in enumerate(buttons):
            is_primary = (i == 0 and len(buttons) > 1 and button_text in [_("确定"), _("Yes")]) or len(buttons) == 1
            btn = ctk.CTkButton(button_frame, text=button_text, command=lambda bt=button_text: on_button_click(bt),
                                font=self.app_font)
            if not is_primary:
                btn.configure(fg_color="transparent", border_width=1,
                              border_color=ctk.ThemeManager.theme["CTkButton"]["border_color"])
            btn.pack(side="left" if len(buttons) > 1 else "top", padx=10)

        # 4. 强制更新以计算窗口的最终所需尺寸
        dialog.update_idletasks()

        # 5. 计算并设置屏幕居中位置
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 6. 在窗口可见之前设置图标
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 设置对话框图标失败: {e}")

        # 7. 设置关闭协议
        dialog.protocol("WM_DELETE_WINDOW", lambda: on_button_click(buttons[-1] if buttons else None))

        # 8. 一切就绪后，显示窗口
        dialog.deiconify()

        # 9. 捕获焦点并等待
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0]

    def _load_image_resource(self, file_name, size=(24, 24)):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath("./assets")
            image_path = os.path.join(base_path, file_name)
            if os.path.exists(image_path):
                return ctk.CTkImage(Image.open(image_path), size=size)
        except Exception as e:
            print(f"警告: 无法加载图片资源 '{file_name}': {e}")
        return None

    def _create_navigation_frame(self, parent):
        self.navigation_frame = ctk.CTkFrame(parent, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(5, weight=1)  # 调整权重行

        nav_header_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        nav_header_frame.grid(row=0, column=0, padx=20, pady=20)

        nav_logo_label = ctk.CTkLabel(nav_header_frame, text="", image=self.logo_image)
        nav_logo_label.pack(pady=(0, 10))

        self.nav_title_label = ctk.CTkLabel(nav_header_frame, text=" FCGT", font=ctk.CTkFont(size=20, weight="bold"))
        self.nav_title_label.pack()

        # --- 【顺序和新增按钮修改】 ---
        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                         text=_("主页"), fg_color="transparent", text_color=("gray10", "gray90"),
                                         anchor="w", image=self.home_icon, font=self.app_font_bold,
                                         command=lambda: self.select_frame_by_name("home"))
        self.home_button.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # 配置编辑器按钮
        self.editor_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                           text=_("配置编辑器"), fg_color="transparent",
                                           text_color=("gray10", "gray90"),
                                           anchor="w", image=self.settings_icon, font=self.app_font_bold,
                                           command=lambda: self.select_frame_by_name("editor"))
        self.editor_button.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.integrate_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                              text=_("整合分析"), fg_color="transparent",
                                              text_color=("gray10", "gray90"), anchor="w", image=self.integrate_icon,
                                              font=self.app_font_bold,
                                              command=lambda: self.select_frame_by_name("integrate"))
        self.integrate_button.grid(row=3, column=0, sticky="ew", padx=10, pady=5)  # 行号+1

        self.tools_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10,
                                          text=_("数据工具"), fg_color="transparent", text_color=("gray10", "gray90"),
                                          anchor="w", image=self.tools_icon, font=self.app_font_bold,
                                          command=lambda: self.select_frame_by_name("tools"))
        self.tools_button.grid(row=4, column=0, sticky="ew", padx=10, pady=5)  # 行号+1
        # --- 修改结束 ---

        settings_frame = ctk.CTkFrame(self.navigation_frame, corner_radius=0, fg_color="transparent")
        settings_frame.grid(row=5, column=0, padx=10, pady=10, sticky="s")
        settings_frame.grid_columnconfigure(0, weight=1)

        self.language_label = ctk.CTkLabel(settings_frame, text=_("语言"), font=self.app_font)
        self.language_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

        self.language_optionmenu = ctk.CTkOptionMenu(settings_frame, variable=self.selected_language_var,
                                                     values=list(self.LANG_CODE_TO_NAME.values()),
                                                     command=self.on_language_change, font=self.app_font,
                                                     dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        self.appearance_mode_label = ctk.CTkLabel(settings_frame, text=_("外观模式"), font=self.app_font)
        self.appearance_mode_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")

        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(settings_frame, variable=self.selected_appearance_var,
                                                             values=[_("浅色"), _("深色"), _("系统")],
                                                             font=self.app_font, dropdown_font=self.app_font,
                                                             command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=3, column=0, padx=5, pady=(0, 10), sticky="ew")

        self.translatable_widgets[self.appearance_mode_optionemenu] = ("values", ["浅色", "深色", "系统"])

    def _create_main_content_area(self, parent):
        self.main_content_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

    def select_frame_by_name(self, name):
        # 设置按钮高亮 (假设按钮已经创建，通常在 _create_navigation_frame 中)
        # 如果这些按钮在 _create_navigation_frame 中没有被创建，可能会继续报错
        # 最佳实践是，这些导航按钮也应该在 __init__ 或 _create_layout 中直接创建
        # (根据您提供的代码，它们已经在 _create_navigation_frame 中创建)
        self.home_button.configure(fg_color=self.home_button.cget("hover_color") if name == "home" else "transparent")
        self.editor_button.configure(
            fg_color=self.editor_button.cget("hover_color") if name == "editor" else "transparent")
        self.integrate_button.configure(
            fg_color=self.integrate_button.cget("hover_color") if name == "integrate" else "transparent")
        self.tools_button.configure(
            fg_color=self.tools_button.cget("hover_color") if name == "tools" else "transparent")

        # 隐藏所有页面：现在保证这些框架都已存在且非 None
        self.home_frame.grid_forget()
        self.editor_frame.grid_forget()
        self.integrate_frame.grid_forget()
        self.tools_frame.grid_forget()

        # 根据名称显示对应的页面：现在保证这些框架都已存在且非 None
        if name == "home":
            self.home_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "editor":
            self.editor_frame.grid(row=0, column=0, sticky="nsew")  # 显示编辑器框架
            # 再次调用 _populate_editor_ui
            # 此时，如果UI已构建（self.editor_widgets不为空），它只会更新值；
            # 如果由于某种原因（比如强制清空）UI被销毁了，它会重建。
            self._populate_editor_ui()

        elif name == "integrate":
            self.integrate_frame.grid(row=0, column=0, sticky="nsew")
        elif name == "tools":
            self.tools_frame.grid(row=0, column=0, sticky="nsew")

    def _populate_editor_ui(self):
        """
        根据当前的配置对象，动态生成或更新整个编辑器UI。
        此函数旨在实现“一次构建，多次更新”的策略。
        """
        self._log_to_viewer(
            f"DEBUG: _populate_editor_ui called. self.editor_widgets empty: {not self.editor_widgets}, self.current_config is: {type(self.current_config)}",
            "DEBUG")

        # 检查主滚动框架是否存在且就绪 (这个检查是防御性的，确保容器可用)
        if not hasattr(self, 'editor_scroll_frame') or not self.editor_scroll_frame.winfo_exists():
            self._log_to_viewer(
                "DEBUG: editor_scroll_frame not yet created or mapped, skipping _populate_editor_ui content creation.",
                "DEBUG")
            return

        # 核心逻辑：只有当 self.editor_widgets 为空时才执行UI构建
        if not self.editor_widgets:  # 界面尚未构建（这是首次运行，或者之前被清空过）
            self._log_to_viewer("DEBUG: self.editor_widgets is EMPTY. Performing FIRST-TIME UI BUILD.", "DEBUG")

            # 首次构建时，确保清空旧的Tkinter子控件，防止视觉残留
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()
            # 此时 self.editor_widgets 肯定是空的，不需要再 clear()，_build_editor_content 会填充它。

            # 如果没有加载配置文件，或者current_config为None，_build_editor_content会使用默认值来绘制UI
            self._log_to_viewer(_("正在根据配置动态生成编辑器界面 (首次构建)..."), "INFO")
            # 调用 _build_editor_content 来创建所有 UI 控件，并填充 self.editor_widgets
            self._build_editor_content(self.editor_scroll_frame, self.current_config, [])
            self._log_to_viewer("DEBUG: First-time UI build COMPLETED. self.editor_widgets now contains: " + str(
                len(self.editor_widgets)) + " widgets.", "DEBUG")

            # 标记编辑器UI已加载，确保只构建一次
            self.editor_ui_loaded = True  #
            # 移除这里的 self.message_queue.put(("editor_ui_populated_done", None)) 调用，
            # 因为这个消息主要用于异步启动流程，现在编辑器是同步创建的。
            # 如果后面需要通知启动完成，由 _start_app_async_startup 统一管理。

        # 无论是否首次构建，如果 self.current_config 存在，就更新UI值
        if self.current_config:
            self._log_to_viewer(_("编辑器界面已存在，正在更新配置值..."), "INFO")
            self._update_editor_ui_values()
            self._log_to_viewer("DEBUG: Existing UI values UPDATED.", "DEBUG")
            # 确保保存按钮在有配置时是启用的
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="normal")
        else:
            # 如果 current_config 为 None (例如，程序刚启动，或者用户手动清空了配置)
            # 此时编辑器UI已经构建了，但应该显示默认或空状态
            if self.editor_widgets:  # 只有当UI已经构建过时才尝试清空值
                self._log_to_viewer(
                    "DEBUG: current_config is EMPTY, but editor_widgets is NOT. Clearing existing UI values.", "DEBUG")
                # 触发一次空配置的更新，让所有控件显示默认/空值
                self._update_editor_ui_values_from_none_config()  #

            # 显示“未加载配置”的提示 (这个标签在 _create_editor_frame 中创建)
            if hasattr(self, 'editor_no_config_label') and self.editor_no_config_label.winfo_exists():
                self.editor_no_config_label.grid(row=0, column=0, pady=50, sticky="nsew")
                self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
            # 禁用保存按钮
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="disabled")


    def _save_config_from_editor(self):
        """
        从动态生成的 UI 控件中收集数据并保存配置。
        此版本重构 update_obj_from_ui，确保变量作用域和逻辑清晰。
        """
        if not self.current_config or not self.config_path:
            self.show_error_message(_("错误"), _("没有加载配置文件，无法保存。"))
            return

        self._log_to_viewer(_("正在从编辑器收集配置并准备保存..."))

        try:
            # 递归地更新配置对象
            def update_obj_from_ui(target_config_obj, current_path_parts):
                """
                递归函数，从 UI 控件中获取值并更新 target_config_obj。
                target_config_obj: 当前需要更新的 dataclass 实例 或 纯 Python 字典。
                current_path_parts: 当前对象在完整配置路径中的列表表示 (例如 ['ai_services', 'providers'])。
                """
                # 获取当前对象在 config_structure 中的定义，以获取其字段的类型和UI信息
                current_struct_def = self._get_structure_for_path(self.config_structure, current_path_parts)

                if not current_path_parts:  # This is the very first call (root)
                    items_definition_iter = self.config_structure.items()
                    is_root_call = True
                elif not current_struct_def or "items" not in current_struct_def:
                    return  # If definition is missing or malformed, stop recursion for this branch
                else:
                    items_definition_iter = current_struct_def["items"].items()
                    is_root_call = False

                for field_name_in_struct, field_def_value_from_struct in items_definition_iter:
                    # 获取当前字段在 config_structure 中的定义
                    if is_root_call:
                        current_field_definition = field_def_value_from_struct  # field_def_value_from_struct is already the section dict
                    else:
                        current_field_definition = field_def_value_from_struct  # field_def_value_from_struct is the tuple/dict definition from 'items'

                    # 忽略 config_version 和内部隐藏属性
                    if field_name_in_struct == "config_version" or field_name_in_struct.startswith('_'):
                        continue

                    # 构建当前字段的完整路径
                    field_full_path_parts = current_path_parts + [field_name_in_struct]
                    field_full_path_str = ".".join(field_full_path_parts)

                    # 获取当前字段在 target_config_obj 中的实际值 (可能是 dataclass, dict, 或简单值)
                    current_field_value_in_obj = None
                    if isinstance(target_config_obj, dict):
                        current_field_value_in_obj = target_config_obj.get(field_name_in_struct)
                    elif is_dataclass(target_config_obj):
                        current_field_value_in_obj = getattr(target_config_obj, field_name_in_struct, None)

                    # 1. 检查这个字段是否在 editor_widgets 中有对应的 UI 控件 (叶子节点)
                    if field_full_path_str in self.editor_widgets:
                        ui_widget_info = self.editor_widgets[field_full_path_str]
                        new_value = None

                        # 根据 UI 控件的类型获取新值
                        if isinstance(ui_widget_info, tuple):
                            # 处理开关 (widget, var)
                            if isinstance(ui_widget_info[0], ctk.CTkSwitch):
                                new_value = ui_widget_info[1].get()
                            # 处理模型选择器 (frame, entry, dropdown, dropdown_var, button)
                            elif len(ui_widget_info) == 5:
                                _frame, entry_widget, dropdown_widget, dropdown_var, _button = ui_widget_info
                                if dropdown_widget.winfo_ismapped():  # 如果下拉框可见，使用其值
                                    new_value = dropdown_var.get()
                                else:  # 否则，使用输入框的值
                                    new_value = entry_widget.get().strip()
                            else:
                                self._log_to_viewer(
                                    f"[WARNING] {_('未知的元组控件类型，跳过更新:')} {field_full_path_str}",
                                    "WARNING")
                                continue

                        elif isinstance(ui_widget_info, ctk.CTkTextbox):
                            text_content = ui_widget_info.get("1.0", tk.END).strip()
                            # 尝试从 YAML 字符串解析回字典（如果原始字段是字典）
                            if isinstance(current_field_value_in_obj, dict):
                                try:
                                    parsed_dict = yaml.safe_load(text_content)
                                    if isinstance(parsed_dict, dict):
                                        new_value = parsed_dict
                                    else:
                                        self._log_to_viewer(
                                            f"[WARNING] {_('YAML文本解析结果不是字典，跳过更新:')} {field_full_path_str}",
                                            "WARNING")
                                        continue
                                except yaml.YAMLError as e:
                                    self._log_to_viewer(
                                        f"[ERROR] {_('YAML解析错误，无法更新字段:')} {field_full_path_str} - {e}",
                                        "ERROR")
                                    continue
                            else:
                                new_value = text_content  # 普通文本内容

                        elif isinstance(ui_widget_info, ctk.CTkOptionMenu):
                            new_value = ui_widget_info.get()

                        else:  # 处理普通输入框 (CTkEntry)
                            text_content = ui_widget_info.get().strip()
                            new_value = text_content

                            # 尝试类型转换
                            if new_value.lower() == 'null' or new_value == '':
                                new_value = None
                            elif isinstance(new_value, str) and new_value.replace('.', '', 1).isdigit():
                                if '.' in new_value:
                                    try:
                                        new_value = float(new_value)
                                    except ValueError:
                                        pass
                                else:
                                    try:
                                        new_value = int(new_value)
                                    except ValueError:
                                        pass
                            # 列表类型字段从逗号分隔字符串转换回列表
                            if isinstance(current_field_value_in_obj, list) and isinstance(new_value, str):
                                new_value = [item.strip() for item in new_value.split(',') if item.strip()]

                        # 将新值设置回 dataclass 实例或字典
                        if isinstance(target_config_obj, dict):
                            target_config_obj[field_name_in_struct] = new_value
                        else:  # dataclass
                            # 确保新值与目标字段类型兼容
                            f_def = None
                            for fld in fields(target_config_obj):
                                if fld.name == field_name_in_struct:
                                    f_def = fld
                                    break

                            if f_def:
                                if new_value is None:
                                    if f_def.default is not fields(target_config_obj)[field_name_in_struct].MISSING:
                                        setattr(target_config_obj, field_name_in_struct, f_def.default)
                                    elif f_def.default_factory is not fields(target_config_obj)[
                                        field_name_in_struct].MISSING and f_def.default_factory:
                                        setattr(target_config_obj, field_name_in_struct, f_def.default_factory())
                                    else:
                                        setattr(target_config_obj, field_name_in_struct, None)
                                else:
                                    setattr(target_config_obj, field_name_in_struct, new_value)
                            else:  # 如果字段定义未找到，则直接设置为 None
                                setattr(target_config_obj, field_name_in_struct, None)

                    # 2. 如果字段值是一个嵌套的 dataclass 实例或字典 (非叶子节点)，递归调用
                    # 只有当 config_structure 中存在对应的子结构定义时才递归
                    elif isinstance(current_field_definition, dict) and "items" in current_field_definition:
                        update_obj_from_ui(current_field_value_in_obj, field_full_path_parts)

            # 从顶层配置对象开始递归更新，路径列表为空表示根
            # 使用 deepcopy 以免在更新过程中意外修改原始 current_config
            temp_config_copy = copy.deepcopy(self.current_config)
            update_obj_from_ui(temp_config_copy, [])

            # 调用保存函数
            # save_config 函数期望传入一个 MainConfig 实例
            if save_config(temp_config_copy, self.config_path):
                # 保存成功后，将临时副本赋给 self.current_config
                self.current_config = temp_config_copy
                self.show_info_message(_("保存成功"), _("配置文件已更新。"))
                self._apply_config_to_ui()  # 刷新所有UI以确保一致性
            else:
                self.show_error_message(_("保存失败"), _("写入文件时发生未知错误。"))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_error_message(_("保存错误"), f"{_('在更新或保存配置时发生错误')}: {e}")

    def _create_status_bar(self, parent):
        self.status_bar_frame = ctk.CTkFrame(parent, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar_frame.grid_columnconfigure(0, weight=1)
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()


    def _create_home_frame(self, parent):
        # 使用可滚动的框架，并让其内容居中
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        # 配置列以允许内容水平居中
        frame.grid_columnconfigure(0, weight=1)

        # --- 顶部信息区 ---
        top_info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        top_info_frame.grid(row=0, column=0, pady=(40, 20), padx=40, sticky="ew")
        top_info_frame.grid_columnconfigure(0, weight=1)  # 允许标签内容居中

        # --- 先将文本赋值给变量，再传递给控件 ---
        title_text = _(self.title_text_key)
        ctk.CTkLabel(top_info_frame, text=title_text, font=self.app_title_font).pack(pady=(0, 10))

        self.config_path_label = ctk.CTkLabel(top_info_frame, text=_("未加载配置"), wraplength=500,
                                              font=self.app_font, text_color=self.secondary_text_color)
        self.translatable_widgets[self.config_path_label] = ("config_path_display", _("当前配置: {}"), _("未加载配置"))
        self.config_path_label.pack(pady=(10, 0))

        # --- 卡片式布局 ---
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1), weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)

        # --- 卡片1: 配置文件操作 ---
        config_card = ctk.CTkFrame(cards_frame)
        config_card.grid(row=0, column=0, padx=20, pady=10, sticky="nsew")
        config_card.grid_columnconfigure(0, weight=1)
        config_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(config_card, text=_("配置文件"), font=self.app_font_bold).grid(
            row=0, column=0, pady=(15, 20), padx=20, sticky="w")
        self.load_config_button = ctk.CTkButton(config_card, text=_("加载配置文件..."), image=self.folder_icon,
                                                command=self.load_config_file, height=40, font=self.app_font)
        self.translatable_widgets[self.load_config_button] = "加载配置文件..."
        self.load_config_button.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        self.gen_config_button = ctk.CTkButton(config_card, text=_("生成默认配置..."), image=self.new_file_icon,
                                               command=self._generate_default_configs_gui, height=40,
                                               font=self.app_font,
                                               fg_color="transparent", border_width=1)
        self.translatable_widgets[self.gen_config_button] = "生成默认配置..."
        self.gen_config_button.grid(row=3, column=0, pady=(10, 15), padx=20, sticky="ew")

        # --- 卡片2: 帮助与支持 ---
        help_card = ctk.CTkFrame(cards_frame)
        help_card.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
        help_card.grid_columnconfigure(0, weight=1)
        help_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(help_card, text=_("帮助与支持"), font=self.app_font_bold).grid(
            row=0, column=0, pady=(15, 20), padx=20, sticky="w")
        self.help_button = ctk.CTkButton(help_card, text=_("在线帮助文档"), image=self.help_icon,
                                         command=self._open_online_help, height=40, font=self.app_font)
        self.translatable_widgets[self.help_button] = "在线帮助文档"
        self.help_button.grid(row=1, column=0, pady=10, padx=20, sticky="ew")
        self.about_button = ctk.CTkButton(help_card, text=_("关于本软件"), image=self.info_icon,
                                          command=self.show_about_dialog, height=40, font=self.app_font,
                                          fg_color="transparent", border_width=1)
        self.translatable_widgets[self.about_button] = "关于本软件"
        self.about_button.grid(row=3, column=0, pady=(10, 15), padx=20, sticky="ew")

        return frame

    def _create_integrate_frame(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=_("整合分析: BSA 定位区域筛选高变异基因 (HVG)"), font=self.app_title_font).pack(
            pady=(20, 25), padx=30)

        # --- 卡片1: 输入文件 ---
        input_card = ctk.CTkFrame(frame)
        input_card.pack(fill="x", padx=30, pady=10)
        input_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(input_card, text=_("第一步: 选择包含BSA和HVG数据的Excel文件"), font=self.app_font_bold).grid(row=0,
                                                                                                                  column=0,
                                                                                                                  columnspan=3,
                                                                                                                  padx=15,
                                                                                                                  pady=15,
                                                                                                                  sticky="w")

        excel_path_label = ctk.CTkLabel(input_card, text=_("Excel文件路径:"), font=self.app_font)
        self.translatable_widgets[excel_path_label] = "Excel文件路径:"
        excel_path_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_card, font=self.app_font, height=35,
                                                  placeholder_text=_("点击“浏览”选择文件，或从配置加载"))
        self.translatable_widgets[self.integrate_excel_entry] = ("placeholder", _("从配置加载或在此覆盖"))
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 15), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_card, text=_("BSA数据工作表:"), font=self.app_font)
        self.translatable_widgets[bsa_sheet_label] = "BSA数据工作表:"
        bsa_sheet_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 15), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_card, text=_("HVG数据工作表:"), font=self.app_font)
        self.translatable_widgets[hvg_sheet_label] = "HVG数据工作表:"
        hvg_sheet_label.grid(row=3, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_sheet_dropdown = ctk.CTkOptionMenu(input_card, variable=self.selected_hvg_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_hvg_sheet_dropdown.grid(row=3, column=1, columnspan=2, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片2: 基因组版本 ---
        version_card = ctk.CTkFrame(frame)
        version_card.pack(fill="x", padx=30, pady=10)
        version_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(version_card, text=_("第二步: 指定对应的基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                         column=0,
                                                                                                         columnspan=2,
                                                                                                         padx=15,
                                                                                                         pady=15,
                                                                                                         sticky="w")

        bsa_assembly_label = ctk.CTkLabel(version_card, text=_("BSA基因组版本:"), font=self.app_font)
        self.translatable_widgets[bsa_assembly_label] = "BSA基因组版本:"
        bsa_assembly_label.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 15), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_card, text=_("HVG基因组版本:"), font=self.app_font)
        self.translatable_widgets[hvg_assembly_label] = "HVG基因组版本:"
        hvg_assembly_label.grid(row=2, column=0, padx=(15, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_card, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 15), pady=(10, 15), sticky="ew")

        # --- 卡片3: 运行 ---
        run_card = ctk.CTkFrame(frame, fg_color="transparent")
        run_card.pack(fill="x", padx=30, pady=20)
        self.integrate_start_button = ctk.CTkButton(run_card, text=_("开始整合分析"), height=50,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始整合分析"
        self.integrate_start_button.pack(fill="x", expand=True)

        return frame

    def _create_tools_frame(self, parent):

        def _on_tab_change():
            """当工具区的选项卡发生切换时被调用。"""
            # 不再有懒加载逻辑，所有tabs都在启动时创建
            selected_tab_name = self.tools_notebook.get()
            # 如果需要，可以在这里为特定的tab添加切换逻辑 (例如刷新数据)
            # 例如：if selected_tab_name == _("AI 助手"): self._update_ai_assistant_tab_info()
            # 但请注意，_update_ai_assistant_tab_info 已经在 _apply_config_to_ui_async 中调用过。

        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=_("数据工具"), font=self.app_title_font).grid(row=0, column=0, padx=30, pady=(20, 25),
                                                                               sticky="w")

        self.tools_notebook = ctk.CTkTabview(frame, corner_radius=8, command=_on_tab_change)
        if hasattr(self.tools_notebook, '_segmented_button'):
            self.tools_notebook._segmented_button.configure(font=self.app_font)
        self.tools_notebook.grid(row=1, column=0, padx=30, pady=10, sticky="nsew")

        return frame

    def _populate_tools_notebook(self):
        tool_tab_definitions = {
            "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
            "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
        }

        # 清理旧的tab和frame，确保每次都是干净的构建
        for tab_frame_key in list(self.tool_tab_frames.keys()):
            tab_frame = self.tool_tab_frames.pop(tab_frame_key, None)
            if tab_frame and tab_frame.winfo_exists():
                tab_frame.destroy()

        for tab_name in list(self.tools_notebook._tab_dict.keys()):
            self.tools_notebook.delete(tab_name)

        self.tool_tab_ui_loaded.clear()  # 重置加载状态

        # 现在，创建 ALL tabs and populate their content synchronously at startup
        for simple_key, display_name in tool_tab_definitions.items():
            tab_frame = self.tools_notebook.add(display_name)
            self.tool_tab_frames[display_name] = tab_frame

            # 不再懒加载：直接填充内容
            if simple_key == "download":
                self._populate_download_tab_structure(tab_frame)
            elif simple_key == "homology":
                self._populate_homology_map_tab_structure(tab_frame)
            elif simple_key == "gff_query":
                self._populate_gff_query_tab_structure(tab_frame)
            elif simple_key == "annotation":
                self._populate_annotation_tab(tab_frame)
            elif simple_key == "ai_assistant":
                self._populate_ai_assistant_tab(tab_frame)
            elif simple_key == "xlsx_to_csv":
                self._populate_xlsx_to_csv_tab(tab_frame)

            # 标记为已加载，因为内容已经创建
            self.tool_tab_ui_loaded[display_name] = True

        # 默认选中第一个工具tab
        if tool_tab_definitions:
            self.tools_notebook.set(list(tool_tab_definitions.values())[0])

    def _populate_xlsx_to_csv_tab(self, page):
        """创建“XLSX转CSV”页面的UI"""
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("Excel (.xlsx) 转 CSV 工具"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 10), padx=20)

        # 添加功能说明标签
        info_label = ctk.CTkLabel(page, text=_(
            "此工具会将一个Excel文件中的所有工作表(Sheet)内容合并到一个CSV文件中。\n适用于所有Sheet表头格式一致的情况。"),
                                  font=self.app_font, wraplength=600, justify="center",
                                  text_color=self.secondary_text_color)
        info_label.pack(pady=(0, 20), padx=30)

        # 创建一个卡片容纳主要控件
        card = ctk.CTkFrame(page)
        card.pack(fill="x", expand=True, padx=20, pady=10)
        card.grid_columnconfigure(1, weight=1)

        # 输入文件选择
        ctk.CTkLabel(card, text=_("输入Excel文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=(20, 10),
                                                                              sticky="w")
        self.xlsx_input_entry = ctk.CTkEntry(card, placeholder_text=_("选择要转换的 .xlsx 文件"), height=35,
                                             font=self.app_font)
        self.xlsx_input_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=(20, 10))
        ctk.CTkButton(card, text=_("浏览..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_file(self.xlsx_input_entry, [("Excel files", "*.xlsx")])).grid(row=0,
                                                                                                                  column=2,
                                                                                                                  padx=10,
                                                                                                                  pady=(
                                                                                                                      20,
                                                                                                                      10))

        # 输出文件选择
        ctk.CTkLabel(card, text=_("输出CSV文件:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                            sticky="w")
        self.csv_output_entry = ctk.CTkEntry(card, placeholder_text=_("选择保存位置和文件名 (不填则自动命名)"),
                                             height=35, font=self.app_font)
        self.csv_output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(card, text=_("另存为..."), width=100, height=35, font=self.app_font,
                      command=lambda: self._browse_save_file(self.csv_output_entry, [("CSV files", "*.csv")])).grid(
            row=1, column=2, padx=10, pady=10)

        # 开始转换按钮
        self.convert_start_button = ctk.CTkButton(page, text=_("开始转换"), height=40,
                                                  command=self.start_xlsx_to_csv_conversion, font=self.app_font_bold)
        self.convert_start_button.pack(fill="x", padx=20, pady=(20, 20))

    def start_xlsx_to_csv_conversion(self):
        """启动XLSX到CSV的转换任务"""
        from cotton_toolkit.core.convertXlsx2csv import convert_xlsx_to_single_csv

        input_path = self.xlsx_input_entry.get().strip()
        output_path = self.csv_output_entry.get().strip()

        if not input_path or not os.path.exists(input_path):
            self.show_error_message(_("输入错误"), _("请输入一个有效的Excel文件路径。"))
            return

        # 如果输出路径为空，则自动生成一个
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
            self.csv_output_entry.insert(0, output_path)

        self.active_task_name = _("XLSX转CSV")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self._update_button_states(is_task_running=True)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.start()

        # 在后台线程中运行转换，防止UI卡顿
        threading.Thread(
            target=lambda: (
                result := convert_xlsx_to_single_csv(input_path, output_path),
                self.task_done_callback(result, self.active_task_name)
            ),
            daemon=True
        ).start()

    def _populate_annotation_tab(self, page):
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text=_("对基因列表进行 GO/IPR/KEGG 功能注释"), font=self.app_font_bold, wraplength=500).pack(
            pady=(20, 15), padx=20)

        input_card = ctk.CTkFrame(page)
        input_card.pack(fill="x", padx=20, pady=10)
        input_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(input_card, text=_("输入文件 (含基因ID列):"), font=self.app_font).grid(row=0, column=0, padx=10,
                                                                                            pady=10, sticky="w")
        self.anno_input_file_entry = ctk.CTkEntry(input_card, placeholder_text=_("选择一个Excel或CSV文件"), height=35,
                                                  font=self.app_font)
        self.anno_input_file_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ctk.CTkButton(input_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.anno_input_file_entry, [("Table files", "*.xlsx *.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=10, pady=10)

        ctk.CTkLabel(input_card, text=_("基因ID所在列名:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                     sticky="w")
        self.anno_gene_col_entry = ctk.CTkEntry(input_card, placeholder_text=_("例如: gene, gene_id (默认: gene)"),
                                                height=35, font=self.app_font)
        self.anno_gene_col_entry.grid(row=1, column=1, columnspan=2, padx=(5, 10), sticky="ew")

        type_card = ctk.CTkFrame(page)
        type_card.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(type_card, text=_("选择注释类型 (需要本地数据库文件支持)"), font=self.app_font).pack(anchor="w",
                                                                                                          padx=10,
                                                                                                          pady=10)
        checkbox_frame = ctk.CTkFrame(type_card, fg_color="transparent")
        checkbox_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkCheckBox(checkbox_frame, text="GO", variable=self.go_anno_var, font=self.app_font).pack(side="left",
                                                                                                       padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="IPR", variable=self.ipr_anno_var, font=self.app_font).pack(side="left",
                                                                                                         padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Orthologs", variable=self.kegg_ortho_anno_var,
                        font=self.app_font).pack(side="left", padx=15)
        ctk.CTkCheckBox(checkbox_frame, text="KEGG Pathways", variable=self.kegg_path_anno_var,
                        font=self.app_font).pack(side="left", padx=15)

        self.anno_start_button = ctk.CTkButton(page, text=_("开始功能注释"), height=40,
                                               command=self.start_annotation_task, font=self.app_font_bold)
        self.anno_start_button.pack(fill="x", padx=20, pady=20)

    def _load_prompts_to_ai_tab(self):
        """将配置中的Prompt模板加载到AI助手页面的输入框中。"""
        if not self.current_config: return

        # 直接从 MainConfig 对象访问 prompts
        prompts_cfg = self.current_config.ai_prompts
        trans_prompt = prompts_cfg.translation_prompt
        analy_prompt = prompts_cfg.analysis_prompt

        if hasattr(self, 'ai_translate_prompt_textbox'):
            self.ai_translate_prompt_textbox.delete("1.0", tk.END)
            self.ai_translate_prompt_textbox.insert("1.0", trans_prompt)

        if hasattr(self, 'ai_analyze_prompt_textbox'):
            self.ai_analyze_prompt_textbox.delete("1.0", tk.END)
            self.ai_analyze_prompt_textbox.insert("1.0", analy_prompt)


    def _populate_ai_assistant_tab(self, page):
        """创建AI助手页面，为不同任务提供独立的、可编辑的Prompt输入框。"""
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(page, text=_("使用AI批量处理表格数据"), font=self.app_title_font, wraplength=500).pack(
            pady=(20, 10), padx=20)

        ai_info_card = ctk.CTkFrame(page, fg_color=("gray90", "gray20"))
        ai_info_card.pack(fill="x", padx=20, pady=10)
        ai_info_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ai_info_card, text=_("当前AI配置:"), font=self.app_font_bold).grid(row=0, column=0, padx=10,
                                                                                        pady=(10, 5), sticky="w")
        self.ai_info_provider_label = ctk.CTkLabel(ai_info_card, text=_("服务商: -"), font=self.app_font)
        self.ai_info_provider_label.grid(row=1, column=0, padx=20, pady=2, sticky="w")
        self.ai_info_model_label = ctk.CTkLabel(ai_info_card, text=_("模型: -"), font=self.app_font)
        self.ai_info_model_label.grid(row=1, column=1, padx=10, pady=2, sticky="w")
        self.ai_info_key_label = ctk.CTkLabel(ai_info_card, text=_("API Key: -"), font=self.app_font)
        self.ai_info_key_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(2, 10), sticky="w")

        # --- UI重构部分 ---
        main_card = ctk.CTkFrame(page)
        main_card.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        main_card.grid_columnconfigure(1, weight=1)
        main_card.grid_rowconfigure(3, weight=1)  # 为Prompt输入框分配权重

        # 任务选择和文件输入
        ctk.CTkLabel(main_card, text=_("输入CSV文件:"), font=self.app_font).grid(row=0, column=0, padx=10, pady=10,
                                                                                 sticky="w")
        self.ai_input_file_entry = ctk.CTkEntry(main_card, placeholder_text=_("选择一个CSV文件"), height=35,
                                                font=self.app_font)
        self.ai_input_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ctk.CTkButton(main_card, text=_("浏览..."), width=100, height=35,
                      command=lambda: self._browse_file(self.ai_input_file_entry, [("CSV files", "*.csv")]),
                      font=self.app_font).grid(row=0, column=2, padx=(0, 10))

        ctk.CTkLabel(main_card, text=_("选择任务类型:"), font=self.app_font).grid(row=1, column=0, padx=10, pady=10,
                                                                                  sticky="w")
        self.ai_task_type_menu = ctk.CTkOptionMenu(main_card, variable=self.ai_task_type_var,
                                                   values=[_("翻译"), _("分析")], command=self._on_ai_task_type_change,
                                                   height=35, font=self.app_font, dropdown_font=self.app_font)
        self.ai_task_type_menu.grid(row=1, column=1, columnspan=2, padx=(0, 10), sticky="ew")

        # Prompt 输入区域
        ctk.CTkLabel(main_card, text=_("Prompt 指令 (用 {text} 代表单元格内容):"), font=self.app_font).grid(row=2,
                                                                                                            column=0,
                                                                                                            columnspan=3,
                                                                                                            padx=10,
                                                                                                            pady=(10,
                                                                                                                  0),
                                                                                                            sticky="w")

        # 为翻译任务创建Prompt输入框
        self.ai_translate_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_translate_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        # 为分析任务创建Prompt输入框
        self.ai_analyze_prompt_textbox = ctk.CTkTextbox(main_card, height=100, font=self.app_font)
        self.ai_analyze_prompt_textbox.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")

        # 其他参数
        param_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        param_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        param_frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(param_frame, text=_("源列名:"), font=self.app_font).grid(row=0, column=0, padx=5)
        self.ai_source_col_entry = ctk.CTkEntry(param_frame, placeholder_text="Description", height=35,
                                                font=self.app_font)
        self.ai_source_col_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(param_frame, text=_("新列名:"), font=self.app_font).grid(row=0, column=2, padx=5)
        self.ai_new_col_entry = ctk.CTkEntry(param_frame, placeholder_text=_("描述/解释"), height=35,
                                             font=self.app_font)
        self.ai_new_col_entry.grid(row=0, column=3, sticky="ew")

        ai_proxy_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        ai_proxy_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        self.ai_proxy_switch = ctk.CTkSwitch(ai_proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.ai_proxy_var, font=self.app_font)
        self.ai_proxy_switch.pack(side="left")

        self.ai_start_button = ctk.CTkButton(page, text=_("开始AI任务"), height=40, command=self.start_ai_task,
                                             font=self.app_font_bold)
        self.ai_start_button.pack(fill="x", padx=20, pady=(0, 20), side="bottom")

        # 初始时，根据下拉菜单的默认值显示正确的Prompt输入框
        self._on_ai_task_type_change(self.ai_task_type_var.get())

    def _on_ai_task_type_change(self, choice):
        """根据AI任务类型切换显示的Prompt输入框。"""
        if choice == _("分析"):
            self.ai_analyze_prompt_textbox.grid()
            self.ai_translate_prompt_textbox.grid_remove()
        else:  # 默认为翻译
            self.ai_translate_prompt_textbox.grid()
            self.ai_analyze_prompt_textbox.grid_remove()

    def start_annotation_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.anno_input_file_entry.get().strip()
        gene_col = self.anno_gene_col_entry.get().strip()
        output_dir_parent = os.path.dirname(input_file) if input_file else "."
        output_dir = os.path.join(output_dir_parent, "annotation_results")

        if not input_file or not gene_col:
            self.show_error_message(_("输入缺失"), _("请输入文件路径和基因列名。"))
            return

        anno_types = []
        if self.go_anno_var.get(): anno_types.append('go')
        if self.ipr_anno_var.get(): anno_types.append('ipr')
        if self.kegg_ortho_anno_var.get(): anno_types.append('kegg_orthologs')
        if self.kegg_path_anno_var.get(): anno_types.append('kegg_pathways')

        if not anno_types:
            self.show_error_message(_("输入缺失"), _("请至少选择一种注释类型。"))
            return

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("功能注释")
        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)  # 使用不确定模式
        self.progress_bar.start()

        threading.Thread(target=run_functional_annotation, kwargs={
            "config": self.current_config, "input_file": input_file, "output_dir": output_dir,
            "annotation_types": anno_types, "gene_column_name": gene_col,
            "status_callback": self.gui_status_callback
        }, daemon=True).start()

    def start_ai_task(self):
        """启动AI任务，并从正确的UI控件获取Prompt。"""
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return

        input_file = self.ai_input_file_entry.get().strip()
        source_col = self.ai_source_col_entry.get().strip()
        new_col = self.ai_new_col_entry.get().strip()
        task_type_display = self.ai_task_type_var.get()

        if not all([input_file, source_col, new_col]):
            self.show_error_message(_("输入缺失"), _("请输入文件路径、源列名和新列名。"));
            return

        # --- 根据任务类型从对应的输入框获取Prompt ---
        task_type = "analyze" if task_type_display == _("分析") else "translate"
        if task_type == 'analyze':
            prompt = self.ai_analyze_prompt_textbox.get("1.0", tk.END).strip()
        else:
            prompt = self.ai_translate_prompt_textbox.get("1.0", tk.END).strip()

        if not prompt or "{text}" not in prompt:
            self.show_error_message(_("Prompt格式错误"), _("Prompt指令不能为空，且必须包含占位符 '{text}'。"));
            return
        # --- 修改结束 ---

        temp_config = self.current_config.copy()
        proxy_status_msg = "OFF"
        if self.ai_proxy_var.get():
            proxies_cfg = self.current_config.get("downloader", {}).get("proxies")
            if not proxies_cfg or not (proxies_cfg.get('http') or proxies_cfg.get('httpss')):
                self.show_warning_message(_("代理未配置"), _("您开启了代理开关，但配置文件中未找到有效的代理地址。"))
                return
            proxy_status_msg = "ON"
        else:
            temp_config['downloader'] = self.current_config.get('downloader', {}).copy()
            temp_config['downloader']['proxies'] = None

        output_dir_parent = os.path.dirname(input_file)
        output_dir = os.path.join(output_dir_parent, "ai_results")

        self._update_button_states(is_task_running=True)
        self.active_task_name = _("AI 助手")
        self._log_to_viewer(
            f"{self.active_task_name} ({task_type_display}) {_('任务开始...')} ({_('代理')}: {proxy_status_msg})")
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.start()

        def task_wrapper():
            success = False
            try:
                success = run_ai_task(
                    config=temp_config, input_file=input_file, output_dir=output_dir,
                    source_column=source_col, new_column=new_col, task_type=task_type,
                    custom_prompt_template=prompt, status_callback=self.gui_status_callback
                )
            except Exception as e:
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

    def _update_ai_assistant_tab_info(self):
        """
        更新AI助手页面的配置信息显示。
        在尝试操作控件前先检查它们是否存在，以兼容懒加载。
        """
        # 检查关键控件是否存在，如果不存在则跳过更新
        if not hasattr(self, 'ai_info_provider_label') or not self.ai_info_provider_label.winfo_exists():
            self._log_to_viewer("DEBUG: AI assistant info labels not yet created, skipping update.", "DEBUG")
            return # 控件还未创建，跳过此次更新

        if not self.current_config:
            provider, model, key_status = "-", "-", _("未加载配置")
            key_color = self.secondary_text_color
        else:
            ai_cfg = self.current_config.ai_services # 直接通过属性访问
            provider = ai_cfg.default_provider
            provider_cfg = ai_cfg.providers.get(provider) # 这是 ProviderConfig 实例

            if provider_cfg:
                model = provider_cfg.model
                api_key = provider_cfg.api_key
            else:
                model = _("未设置")
                api_key = ""

            if not api_key or "YOUR_" in api_key:
                key_status = _("未配置或无效")
                key_color = ("#d9534f", "#e57373")  # red
            else:
                key_status = f"{api_key[:5]}...{api_key[-4:]} ({_('已配置')})"
                key_color = ("#28a745", "#73bf69")  # green

        self.ai_info_provider_label.configure(text=f"{_('服务商')}: {provider}")
        self.ai_info_model_label.configure(text=f"{_('模型')}: {model}")
        self.ai_info_key_label.configure(text=f"{_('API Key')}: {key_status}", text_color=key_color)

    def _handle_textbox_focus_out(self, event, textbox_widget, placeholder_text_key):
        """当Textbox失去焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        if not current_text:
            placeholder = _(placeholder_text_key)

            # 根据当前外观模式动态选择单一颜色值
            current_mode = ctk.get_appearance_mode()
            placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[
                1]
            textbox_widget.configure(text_color=placeholder_color_value)

            textbox_widget.insert("0.0", placeholder)

    def _handle_textbox_focus_in(self, event, textbox_widget, placeholder_text_key):
        """当Textbox获得焦点时的处理函数"""
        current_text = textbox_widget.get("1.0", tk.END).strip()
        placeholder = _(placeholder_text_key)

        # 检查当前文本是否为占位符
        # 一个更稳妥的检查方式是同时判断内容和颜色
        current_ph_color_tuple = self.placeholder_color
        current_mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0

        is_placeholder = False
        if current_text == placeholder:
            # 尝试获取颜色，如果失败则假定为占位符
            try:
                if textbox_widget.cget("text_color") == current_ph_color_tuple[current_mode_idx]:
                    is_placeholder = True
            except (AttributeError, IndexError):
                is_placeholder = True

        if is_placeholder:
            textbox_widget.delete("1.0", tk.END)
            # 【重要修复】使用在__init__中定义的、适配亮/暗模式的默认颜色元组
            # CTkTextbox.configure 方法可以正确处理颜色元组
            textbox_widget.configure(text_color=self.default_text_color)

    def set_app_icon(self):
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 加载主窗口图标失败: {e}。")

    # --- 新增：创建工具栏的方法 ---
    def _create_toolbar(self):
        toolbar_frame = ctk.CTkFrame(self, corner_radius=0, height=45)
        toolbar_frame.pack(side="top", fill="x", padx=0, pady=0)

        load_btn = ctk.CTkButton(toolbar_frame, text=_("加载配置..."), width=100, font=self.toolbar_font,
                                 command=self.load_config_file)
        load_btn.pack(side="left", padx=(10, 5), pady=8)
        self.translatable_widgets[load_btn] = "加载配置..."

        gen_btn = ctk.CTkButton(toolbar_frame, text=_("生成配置..."), width=100, font=self.toolbar_font,
                                command=self._generate_default_configs_gui)
        gen_btn.pack(side="left", padx=5, pady=8)
        self.translatable_widgets[gen_btn] = "生成配置..."

        help_btn = ctk.CTkButton(toolbar_frame, text=_("在线文档"), width=90, font=self.toolbar_font,
                                 command=self._open_online_help)
        help_btn.pack(side="left", padx=(20, 5), pady=8)
        self.translatable_widgets[help_btn] = "在线文档"

        about_btn = ctk.CTkButton(toolbar_frame, text=_("关于"), width=60, font=self.toolbar_font,
                                  command=self.show_about_dialog)
        about_btn.pack(side="left", padx=5, pady=8)
        self.translatable_widgets[about_btn] = "关于"

        exit_btn = ctk.CTkButton(toolbar_frame, text=_("退出"), width=60, font=self.toolbar_font,
                                 command=self.on_closing, fg_color=("#D32F2F", "#B71C1C"),
                                 hover_color=("#E53935", "#C62828"))
        exit_btn.pack(side="right", padx=10, pady=8)
        self.translatable_widgets[exit_btn] = "退出"

    def _open_online_help(self):  #
        try:
            self._log_to_viewer(_("正在浏览器中打开在线帮助文档..."))  #
            webbrowser.open(PKG_HELP_URL)  #
        except Exception as e:  #
            self.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))  #


    def show_about_dialog(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.focus_set()
            return

        # 1. 创建窗口并立即隐藏
        self.about_window = ctk.CTkToplevel(self)
        self.about_window.withdraw()

        # 2. 设置窗口基础属性
        self.about_window.title(_("关于"))
        self.about_window.transient(self)
        self.about_window.resizable(False, False)

        # 3. 创建并打包所有内部控件
        about_frame = ctk.CTkFrame(self.about_window)
        about_frame.pack(fill="both", expand=True, padx=25, pady=20)
        try:
            logo_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_image_path = os.path.join(logo_path, "icon.ico")
            if os.path.exists(icon_image_path):
                logo_image = ctk.CTkImage(light_image=Image.open(icon_image_path),
                                          dark_image=Image.open(icon_image_path), size=(64, 64))
                ctk.CTkLabel(about_frame, image=logo_image, text="").pack(pady=(10, 10))
        except Exception as e:
            print(f"警告: 无法加载Logo图片: {e}")

        # 获取完整的关于文本字符串
        about_content_str = get_about_text(translator=_)  # 获取字符串内容

        # 直接使用一个 CTkTextbox 或 CTkLabel 显示整个文本，而不是按键访问
        # 使用 Textbox 可以自动处理多行文本和滚动
        about_textbox = ctk.CTkTextbox(about_frame, height=250, width=400, font=self.app_font, wrap="word",
                                       state="disabled")
        about_textbox.insert("1.0", about_content_str)
        about_textbox.pack(pady=10, padx=10, fill="both", expand=True)

        hyperlink_font = ctk.CTkFont(family="Microsoft YaHei UI", size=14, underline=True)
        # 链接部分可以从 get_about_text 的内容中解析或者直接硬编码
        # 如果 get_about_text 不返回字典，就不能用 .get("help_url_target") 了
        # 这里直接使用 PKG_HELP_URL (从 cotton_toolkit.__init__ 或 mock 导入)
        url_target = PKG_HELP_URL  # 或者从别的地方获取，如果 get_about_text 返回其他信息的话
        link_frame = ctk.CTkFrame(about_frame, fg_color="transparent")
        link_frame.pack(pady=10)
        ctk.CTkLabel(link_frame, text=f"{_('帮助文档')}: ", font=self.app_font).pack(side="left")  # 修正文本
        url_label = ctk.CTkLabel(link_frame, text=_('GitHub'), font=hyperlink_font,
                                 text_color=("#1f6aa5", "#4a90e2"),  # 文本修改
                                 cursor="hand2")
        url_label.pack(side="left", padx=5)
        url_label.bind("<Button-1>", lambda e: webbrowser.open_new(url_target))

        ctk.CTkButton(about_frame, text=_("关闭"), command=self.about_window.destroy, font=self.app_font).pack(
            pady=(20, 10))

        # 4. 强制更新以计算窗口的最终所需尺寸
        self.about_window.update_idletasks()

        # 5. 计算并设置屏幕居中位置
        dialog_width = self.about_window.winfo_reqwidth()
        dialog_height = self.about_window.winfo_reqheight()
        screen_width = self.about_window.winfo_screenwidth()
        screen_height = self.about_window.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        self.about_window.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 6. 在窗口可见之前设置图标
        try:
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            icon_path = os.path.join(base_path, "icon.ico")
            if os.path.exists(icon_path):
                self.about_window.iconbitmap(icon_path)
        except Exception as e:
            print(f"警告: 设置'关于'窗口图标失败: {e}")

        # 7. 一切就绪后，显示窗口
        self.about_window.deiconify()

        # 8. 捕获焦点并等待
        self.about_window.grab_set()
        self.about_window.wait_window()

    def _create_config_widgets_structure(self):
        self.config_frame = ctk.CTkFrame(self.main_container)
        self.config_frame.pack(side="top", pady=(5, 5), padx=10, fill="x")
        self.config_frame.grid_columnconfigure(0, weight=1)
        self.config_path_label_base_key = "配置文件"
        self.config_path_display_part = lambda: os.path.basename(self.config_path) if self.config_path else _(
            "未加载 (请点击“加载配置...”)")
        self.config_path_label = ctk.CTkLabel(self.config_frame,
                                              text=f"{_(self.config_path_label_base_key)}: {self.config_path_display_part()}",
                                              font=self.app_font, anchor="w")
        self.translatable_widgets[self.config_path_label] = ("label_with_dynamic_part", self.config_path_label_base_key,
                                                             self.config_path_display_part)
        self.config_path_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.language_label = ctk.CTkLabel(self.config_frame, text=_("语言:"), font=self.app_font)
        self.translatable_widgets[self.language_label] = "语言:"
        self.language_label.grid(row=0, column=1, padx=(10, 5), pady=10)
        self.language_optionmenu = ctk.CTkOptionMenu(self.config_frame, variable=self.selected_language_var,
                                                     values=list(self.LANG_CODE_TO_NAME.values()),
                                                     command=self.on_language_change, font=self.app_font,
                                                     dropdown_font=self.app_font)
        self.language_optionmenu.grid(row=0, column=2, padx=(0, 10), pady=10)

    def change_appearance_mode_event(self, selected_display_mode: str):
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(selected_display_mode, "System")
        ctk.set_appearance_mode(new_mode)

        # 更新日志颜色以匹配新模式
        self._update_log_tag_colors()

        # 更新并保存UI设置
        self.ui_settings['appearance_mode'] = new_mode
        self.ui_settings['appearance_mode_display'] = selected_display_mode
        self._save_ui_settings()

    def on_language_change(self, selected_display_name: str):
        new_language_code = self.LANG_NAME_TO_CODE.get(selected_display_name, "en")

        # 更新并保存UI设置
        self.ui_settings['language'] = new_language_code
        self._save_ui_settings()

        self.update_language_ui(new_language_code)

    def _create_status_widgets_structure(self):
        self.status_bar_frame = ctk.CTkFrame(self.main_container, height=35, corner_radius=0)
        self.status_bar_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        self.status_bar_frame.grid_columnconfigure(0, weight=1)
        self.status_label_base_key = "准备就绪"
        self.status_label = ctk.CTkLabel(self.status_bar_frame, text=_(self.status_label_base_key), anchor="w",
                                         font=self.app_font)
        self.translatable_widgets[self.status_label] = ("label_with_dynamic_part", self.status_label_base_key,
                                                        lambda: "")
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.status_bar_frame, width=200)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.grid_remove()

    def _create_log_viewer_structure(self, parent):
        self.log_viewer_frame = ctk.CTkFrame(parent)
        self.log_viewer_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self.log_viewer_frame.grid_columnconfigure(0, weight=1)

        log_header_frame = ctk.CTkFrame(self.log_viewer_frame, fg_color="transparent")
        log_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        log_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_header_frame, text=_("操作日志"), font=self.app_font_bold).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(log_header_frame, text=_("清除日志"), width=80, height=28, command=self.clear_log_viewer,
                      font=self.app_font).grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(self.log_viewer_frame, height=140, state="disabled", wrap="word",
                                          font=self.app_font)
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.log_textbox.tag_config("error_log", foreground="#d9534f")
        self.log_textbox.tag_config("warning_log", foreground="#f0ad4e")

    def _create_tab_view_structure(self):
        self.tab_view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_view_frame.pack(side="bottom", fill="both", expand=True, padx=10, pady=5)
        self.tab_view = ctk.CTkTabview(self.tab_view_frame, corner_radius=8)
        if hasattr(self.tab_view, '_segmented_button'):
            self.tab_view._segmented_button.configure(font=self.app_font)
        self.tab_view.pack(fill="both", expand=True, padx=0, pady=0)
        self.download_tab_internal_key = "DOWNLOAD_TAB_INTERNAL"
        self.integrate_tab_internal_key = "INTEGRATE_TAB_INTERNAL"
        self.homology_map_tab_internal_key = "HOMOLOGY_MAP_TAB_INTERNAL"
        self.gff_query_tab_internal_key = "GFF_QUERY_TAB_INTERNAL"
        self.editor_tab_internal_key = "EDITOR_TAB_INTERNAL"
        self.download_tab_display_key = "数据下载"
        self.integrate_tab_display_key = "整合分析"
        self.homology_map_tab_display_key = "基因组转换"
        self.gff_query_tab_display_key = "基因位点查询"
        self.editor_tab_display_key = "配置编辑"
        self.tab_view.add(self.download_tab_internal_key)
        self.tab_view.add(self.integrate_tab_internal_key)
        self.tab_view.add(self.homology_map_tab_internal_key)
        self.tab_view.add(self.gff_query_tab_internal_key)
        self.tab_view.add(self.editor_tab_internal_key)
        self._populate_download_tab_structure()
        self._populate_integrate_tab_structure()
        self._populate_homology_map_tab_structure()
        self._populate_gff_query_tab_structure()
        self._populate_editor_tab_structure()

    def _populate_download_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        target_card = ctk.CTkFrame(page)
        target_card.pack(fill="both", expand=True, pady=(15, 10), padx=15)
        target_card.grid_columnconfigure(0, weight=1)
        target_card.grid_rowconfigure(2, weight=1)

        target_header_frame = ctk.CTkFrame(target_card, fg_color="transparent")
        target_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        target_header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(target_header_frame, text=_("下载目标: 选择基因组版本"), font=self.app_font_bold).grid(row=0,
                                                                                                            column=0,
                                                                                                            sticky="w")

        selection_buttons_frame = ctk.CTkFrame(target_header_frame, fg_color="transparent")
        selection_buttons_frame.grid(row=0, column=1, sticky="e")

        self.dl_select_all_button = ctk.CTkButton(selection_buttons_frame, text=_("全选"), width=80, height=28,
                                                  font=self.app_font,
                                                  command=lambda: self._toggle_all_download_genomes(True))
        self.dl_deselect_all_button = ctk.CTkButton(selection_buttons_frame, text=_("取消全选"), width=90, height=28,
                                                    font=self.app_font,
                                                    command=lambda: self._toggle_all_download_genomes(False))
        self.dl_select_all_button.pack(side="left", padx=(0, 10))
        self.dl_deselect_all_button.pack(side="left")

        ctk.CTkLabel(target_card, text=_("勾选需要下载的基因组版本。若不勾选任何项，将默认下载所有可用版本。"),
                     text_color=self.secondary_text_color, font=self.app_font, wraplength=500).grid(row=1, column=0,
                                                                                                    padx=10,
                                                                                                    pady=(0, 10),
                                                                                                    sticky="w")

        self.download_genomes_checkbox_frame = ctk.CTkScrollableFrame(target_card, label_text="")
        self.download_genomes_checkbox_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        options_frame = ctk.CTkFrame(page)
        options_frame.pack(fill="x", expand=False, pady=10, padx=15)
        options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options_frame, text=_("下载选项"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                      padx=10, pady=(10, 15),
                                                                                      sticky="w")

        # --- 代理开关 ---
        proxy_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        proxy_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.dl_proxy_switch = ctk.CTkSwitch(proxy_frame, text=_("使用网络代理 (需在配置中设置)"),
                                             variable=self.download_proxy_var, font=self.app_font)
        self.dl_proxy_switch.pack(side="left")

        force_download_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        force_download_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))
        self.dl_force_switch_label = ctk.CTkLabel(force_download_frame, text=_("强制重新下载:"), font=self.app_font)
        self.dl_force_switch_label.pack(side="left", padx=(0, 10))
        self.dl_force_switch = ctk.CTkSwitch(force_download_frame, text="", variable=self.download_force_checkbox_var)
        self.dl_force_switch.pack(side="left")

        self.download_start_button = ctk.CTkButton(page, text=_("开始下载"), height=40,
                                                   command=self.start_download_task, font=self.app_font_bold)
        self.download_start_button.pack(fill="x", padx=15, pady=(10, 15), side="bottom")





    def browse_download_output_dir(self):
        """
        打开文件夹选择对话框，让用户选择下载文件的输出目录。
        """
        directory = filedialog.askdirectory(title=_("选择下载输出目录"))
        if directory and self.download_output_dir_entry:
            self.download_output_dir_entry.delete(0, tk.END)
            self.download_output_dir_entry.insert(0, directory)

    def _populate_editor_ui(self):
        """
        根据当前的配置对象，动态生成或更新整个编辑器UI。
        此函数旨在实现“一次构建，多次更新”的策略。
        """
        self._log_to_viewer(
            f"DEBUG: _populate_editor_ui called. self.editor_widgets empty: {not self.editor_widgets}, self.current_config is: {type(self.current_config)}",
            "DEBUG")

        # 核心逻辑：只有当 self.editor_widgets 为空时才执行UI构建
        if not self.editor_widgets:  # 界面尚未构建（首次运行）
            self._log_to_viewer("DEBUG: self.editor_widgets is EMPTY. Performing FIRST-TIME UI BUILD.", "DEBUG")

            # 清除旧的 Tkinter 控件（防止意外残留）。
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()
            # 此时 self.editor_widgets 是空的，不需要 clear()，因为它会被 _build_editor_content 填充。

            # 如果没有加载配置，显示提示信息并返回
            if not self.current_config:
                self._log_to_viewer("DEBUG: No config loaded for editor, displaying placeholder.", "DEBUG")
                no_config_label = ctk.CTkLabel(self.editor_scroll_frame,
                                               text=_("请先从“主页”加载或生成一个配置文件。"),
                                               font=self.app_subtitle_font, text_color=self.secondary_text_color)
                no_config_label.grid(row=0, column=0, pady=50, sticky="nsew")
                self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
                if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                    self.save_editor_button.configure(state="disabled")
                return

            self._log_to_viewer(_("正在根据配置动态生成编辑器界面 (首次构建)..."), "INFO")
            # 调用 _build_editor_content 来创建所有 UI 控件，并填充 self.editor_widgets
            self._build_editor_content(self.editor_scroll_frame, self.current_config, [])
            self._log_to_viewer("DEBUG: First-time UI build COMPLETED. self.editor_widgets now contains: " + str(
                len(self.editor_widgets)) + " widgets.", "DEBUG")

            # 确保只有在UI构建完成后才设置标志和发送消息
            # 此时， যেহেতু _populate_editor_ui 是在 _init_pages_and_final_setup 中同步调用的，
            # 并且它只构建一次，所以 editor_ui_loaded 标志是用于异步启动流程的。
            if not self.editor_ui_loaded:  # 确保只发送一次
                self.editor_ui_loaded = True
                self.message_queue.put(("editor_ui_populated_done", None))  # 通知主线程编辑器UI已就绪
                self._log_to_viewer("DEBUG: Editor UI loaded and notified for startup.", "DEBUG")

        # 无论是否首次构建，只要有 current_config，就更新UI值
        if self.current_config:
            self._log_to_viewer(_("编辑器界面已存在，正在更新配置值..."), "INFO")
            self._update_editor_ui_values()
            self._log_to_viewer("DEBUG: Existing UI values UPDATED.", "DEBUG")
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="normal")
        else:
            # self.editor_widgets 不为空，但 current_config 为空 (例如，用户手动清空了配置)
            if self.editor_widgets:  # 如果之前有构建过UI
                self._log_to_viewer("DEBUG: current_config is EMPTY, but editor_widgets is NOT. Clearing existing UI.",
                                    "DEBUG")
                for widget in self.editor_scroll_frame.winfo_children():
                    widget.destroy()
                self.editor_widgets.clear()  # 清空控件引用
                self._log_to_viewer("DEBUG: Editor UI cleared.", "DEBUG")

            # 显示“未加载配置”的提示
            no_config_label = ctk.CTkLabel(self.editor_scroll_frame, text=_("请先从“主页”加载或生成一个配置文件。"),
                                           font=self.app_subtitle_font, text_color=self.secondary_text_color)
            no_config_label.grid(row=0, column=0, pady=50, sticky="nsew")
            self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="disabled")

    def _update_download_genomes_list(self):
        """
        根据当前配置，动态更新下载页面的基因组版本复选框列表，并高亮显示已存在的项。
        在尝试操作 download_genomes_checkbox_frame 之前，检查其是否存在。
        """
        # 优化：在操作控件前先检查其是否存在
        if not hasattr(self, 'download_genomes_checkbox_frame') or not self.download_genomes_checkbox_frame.winfo_exists():
            self._log_to_viewer("DEBUG: download_genomes_checkbox_frame does not exist yet, skipping update.", "DEBUG")
            return # 如果控件还未创建，则跳过此次更新

        # 清理旧的复选框和变量
        for widget in self.download_genomes_checkbox_frame.winfo_children():
            widget.destroy()
        self.download_genome_vars.clear()

        # 定义颜色 (亮色模式, 暗色模式)
        existing_item_color = ("#28a745", "#73bf69")
        default_color = self.default_label_text_color

        if not self.current_config:
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("请先加载配置文件"),
                         text_color=self.secondary_text_color).pack()
            return

        genome_sources = get_genome_data_sources(self.current_config)
        downloader_cfg = self.current_config.get("downloader", {})
        base_download_dir = downloader_cfg.get("download_output_base_dir", "downloaded_cotton_data")

        if not genome_sources or not isinstance(genome_sources, dict):
            ctk.CTkLabel(self.download_genomes_checkbox_frame, text=_("配置文件中未找到基因组源"),
                         text_color=self.secondary_text_color).pack()
            return

        # 为每个基因组版本创建一个复选框
        for genome_id, details in genome_sources.items():
            var = tk.BooleanVar(value=False)
            species_name = details.get('species_name', _('未知物种'))
            display_text = f"{genome_id} ({species_name})"

            # --- 检查目录是否存在 ---
            safe_dir_name = species_name.replace(" ", "_").replace(".", "_").replace("(", "").replace(")", "").replace(
                "'", "")
            version_output_dir = os.path.join(base_download_dir, safe_dir_name)
            text_color_to_use = existing_item_color if os.path.exists(version_output_dir) else default_color

            cb = ctk.CTkCheckBox(
                self.download_genomes_checkbox_frame,
                text=display_text,
                variable=var,
                font=self.app_font,
                text_color=text_color_to_use
            )
            cb.pack(anchor="w", padx=10, pady=5)
            self.download_genome_vars[genome_id] = var

    def _toggle_all_download_genomes(self, select: bool):
        """全选或取消全选所有下载基因组的复选框"""
        for var in self.download_genome_vars.values():
            var.set(select)

    def _populate_integrate_tab_structure(self):
        page = self.tab_view.tab(self.integrate_tab_internal_key)
        scrollable_frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Card 1: Input Data
        input_frame = ctk.CTkFrame(scrollable_frame)
        input_frame.pack(fill="x", expand=True, pady=(5, 10), padx=5)
        input_frame.grid_columnconfigure(1, weight=1)

        input_label = ctk.CTkLabel(input_frame, text=_("输入数据"), font=self.app_font_bold)
        self.translatable_widgets[input_label] = "输入数据"
        input_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        excel_path_label = ctk.CTkLabel(input_frame, text=_("Excel文件路径:"), font=self.app_font)
        self.translatable_widgets[excel_path_label] = "Excel文件路径:"
        excel_path_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_excel_entry = ctk.CTkEntry(input_frame, font=self.app_font, height=35)
        self.translatable_widgets[self.integrate_excel_entry] = "从配置加载或在此覆盖"
        self.integrate_excel_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.int_excel_browse_button = ctk.CTkButton(input_frame, text=_("浏览..."), width=100, height=35,
                                                     command=self.browse_integrate_excel, font=self.app_font)
        self.translatable_widgets[self.int_excel_browse_button] = "浏览..."
        self.int_excel_browse_button.grid(row=1, column=2, padx=(0, 10), pady=10)
        self.integrate_excel_entry.bind("<FocusOut>", lambda event: self._update_excel_sheet_dropdowns())
        self.integrate_excel_entry.bind("<Return>", lambda event: self._update_excel_sheet_dropdowns())

        bsa_sheet_label = ctk.CTkLabel(input_frame, text=_("BSA数据工作表:"), font=self.app_font)
        self.translatable_widgets[bsa_sheet_label] = "BSA数据工作表:"
        bsa_sheet_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_bsa_sheet_dropdown = ctk.CTkOptionMenu(input_frame, variable=self.selected_bsa_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_bsa_sheet_dropdown.grid(row=2, column=1, columnspan=2, padx=(0, 10), pady=10, sticky="ew")

        hvg_sheet_label = ctk.CTkLabel(input_frame, text=_("HVG数据工作表:"), font=self.app_font)
        self.translatable_widgets[hvg_sheet_label] = "HVG数据工作表:"
        hvg_sheet_label.grid(row=3, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_hvg_sheet_dropdown = ctk.CTkOptionMenu(input_frame, variable=self.selected_hvg_sheet,
                                                              values=[_("请先指定Excel文件")], font=self.app_font,
                                                              height=35, dropdown_font=self.app_font)
        self.integrate_hvg_sheet_dropdown.grid(row=3, column=1, columnspan=2, padx=(0, 10), pady=10, sticky="ew")

        # Card 2: Genome Versions
        version_frame = ctk.CTkFrame(scrollable_frame)
        version_frame.pack(fill="x", expand=True, pady=10, padx=5)
        version_frame.grid_columnconfigure(1, weight=1)

        version_label = ctk.CTkLabel(version_frame, text=_("基因组版本"), font=self.app_font_bold)
        self.translatable_widgets[version_label] = "基因组版本"
        version_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15), sticky="w")

        bsa_assembly_label = ctk.CTkLabel(version_frame, text=_("BSA基因组版本:"), font=self.app_font)
        self.translatable_widgets[bsa_assembly_label] = "BSA基因组版本:"
        bsa_assembly_label.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_bsa_assembly_dropdown = ctk.CTkOptionMenu(version_frame, variable=self.selected_bsa_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_bsa_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        hvg_assembly_label = ctk.CTkLabel(version_frame, text=_("HVG基因组版本:"), font=self.app_font)
        self.translatable_widgets[hvg_assembly_label] = "HVG基因组版本:"
        hvg_assembly_label.grid(row=2, column=0, padx=(10, 5), pady=10, sticky="w")
        self.integrate_hvg_assembly_dropdown = ctk.CTkOptionMenu(version_frame, variable=self.selected_hvg_assembly,
                                                                 values=[_("加载中...")], font=self.app_font, height=35,
                                                                 dropdown_font=self.app_font)
        self.integrate_hvg_assembly_dropdown.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")

        # Start Button
        self.integrate_start_button = ctk.CTkButton(scrollable_frame, text=_("开始整合分析"), height=40,
                                                    command=self.start_integrate_task, font=self.app_font_bold)
        self.translatable_widgets[self.integrate_start_button] = "开始整合分析"
        self.integrate_start_button.pack(fill="x", padx=5, pady=(10, 5))

    def _populate_homology_map_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        container = ctk.CTkFrame(page, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure((0, 1), weight=1)
        container.grid_rowconfigure(1, weight=1)
        input_frame = ctk.CTkFrame(container)
        input_frame.grid(row=0, column=0, rowspan=2, padx=(15, 5), pady=15, sticky="nsew")
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text=_("输入基因与版本"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                          padx=10, pady=(10, 15),
                                                                                          sticky="w")

        self.homology_map_genes_entry = ctk.CTkTextbox(input_frame, font=self.app_font, wrap="none")
        self.homology_map_genes_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.homology_map_genes_entry.insert("0.0", _(self.placeholder_genes_homology_key))

        # 根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.homology_map_genes_entry.configure(text_color=placeholder_color_value)

        self.homology_map_genes_entry.bind("<FocusIn>",
                                           lambda e: self._handle_textbox_focus_in(e, self.homology_map_genes_entry,
                                                                                   self.placeholder_genes_homology_key))
        self.homology_map_genes_entry.bind("<FocusOut>",
                                           lambda e: self._handle_textbox_focus_out(e, self.homology_map_genes_entry,
                                                                                    self.placeholder_genes_homology_key))

        ctk.CTkLabel(input_frame, text=_("源基因组版本:"), font=self.app_font).grid(row=2, column=0, padx=10, pady=10,
                                                                                    sticky="w")
        self.homology_map_source_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_source_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_source_assembly_dropdown.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(input_frame, text=_("目标基因组版本:"), font=self.app_font).grid(row=4, column=0, padx=10, pady=10,
                                                                                      sticky="w")
        self.homology_map_target_assembly_dropdown = ctk.CTkOptionMenu(input_frame, font=self.app_font, height=35,
                                                                       variable=self.selected_homology_target_assembly,
                                                                       values=[_("加载中...")],
                                                                       dropdown_font=self.app_font)
        self.homology_map_target_assembly_dropdown.grid(row=5, column=0, columnspan=2, padx=10, pady=(5, 10),
                                                        sticky="ew")
        file_frame = ctk.CTkFrame(container)
        file_frame.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="new")
        file_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(file_frame, text=_("同源与输出文件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=3,
                                                                                         padx=10, pady=(10, 15),
                                                                                         sticky="w")
        ctk.CTkLabel(file_frame, text=_("源到桥梁文件:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                   pady=5, sticky="w")
        self.homology_map_sb_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_sb_file_entry.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("桥梁到目标文件:"), font=self.app_font).grid(row=3, column=0, padx=(10, 5),
                                                                                     pady=5, sticky="w")
        self.homology_map_bt_file_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_bt_file_entry.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(file_frame, text=_("结果输出CSV文件:"), font=self.app_font).grid(row=5, column=0, padx=(10, 5),
                                                                                      pady=5, sticky="w")
        self.homology_map_output_csv_entry = ctk.CTkEntry(file_frame, font=self.app_font, height=35)
        self.homology_map_output_csv_entry.grid(row=6, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        self.homology_map_start_button = ctk.CTkButton(container, text=_("开始同源映射"), height=40,
                                                       command=self.start_homology_map_task, font=self.app_font_bold)
        self.homology_map_start_button.grid(row=1, column=1, padx=(5, 15), pady=15, sticky="sew")

    def _populate_gff_query_tab_structure(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        query_frame = ctk.CTkFrame(page)
        query_frame.pack(fill="x", padx=15, pady=(15, 10))
        query_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(query_frame, text=_("查询条件"), font=self.app_font_bold).grid(row=0, column=0, columnspan=2,
                                                                                    padx=10, pady=(10, 15), sticky="w")
        ctk.CTkLabel(query_frame, text=_("基因组版本ID:"), font=self.app_font).grid(row=1, column=0, padx=(10, 5),
                                                                                    pady=10, sticky="w")
        self.gff_query_assembly_dropdown = ctk.CTkOptionMenu(query_frame, font=self.app_font, height=35,
                                                             variable=self.selected_gff_query_assembly,
                                                             values=[_("加载中...")], dropdown_font=self.app_font)
        self.gff_query_assembly_dropdown.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ctk.CTkLabel(query_frame, text=_("染色体区域:"), font=self.app_font).grid(row=2, column=0, padx=(10, 5),
                                                                                  pady=10, sticky="w")
        self.gff_query_region_entry = ctk.CTkEntry(query_frame, font=self.app_font, height=35,
                                                   placeholder_text=_("例如: chr1:1000-5000 (与下方基因ID二选一)"))
        self.gff_query_region_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        gene_list_frame = ctk.CTkFrame(page)
        gene_list_frame.pack(fill="both", expand=True, padx=15, pady=10)
        gene_list_frame.grid_columnconfigure(0, weight=1)
        gene_list_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(gene_list_frame, text=_("或输入基因ID (每行一个):"), font=self.app_font).grid(row=0, column=0,
                                                                                                   padx=10, pady=5,
                                                                                                   sticky="w")

        self.gff_query_genes_entry = ctk.CTkTextbox(gene_list_frame, font=self.app_font, wrap="none")
        self.gff_query_genes_entry.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.gff_query_genes_entry.insert("0.0", _(self.placeholder_genes_gff_key))

        # 根据当前外观模式动态选择单一颜色值
        current_mode = ctk.get_appearance_mode()
        placeholder_color_value = self.placeholder_color[0] if current_mode == "Light" else self.placeholder_color[1]
        self.gff_query_genes_entry.configure(text_color=placeholder_color_value)

        self.gff_query_genes_entry.bind("<FocusIn>",
                                        lambda e: self._handle_textbox_focus_in(e, self.gff_query_genes_entry,
                                                                                self.placeholder_genes_gff_key))
        self.gff_query_genes_entry.bind("<FocusOut>",
                                        lambda e: self._handle_textbox_focus_out(e, self.gff_query_genes_entry,
                                                                                 self.placeholder_genes_gff_key))

        output_frame = ctk.CTkFrame(page)
        output_frame.pack(fill="x", padx=15, pady=10)
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(output_frame, text=_("结果输出CSV文件:"), font=self.app_font).pack(padx=10, pady=5, anchor="w")
        self.gff_query_output_csv_entry = ctk.CTkEntry(output_frame, font=self.app_font, height=35,
                                                       placeholder_text=_("可选, 默认自动生成"))
        self.gff_query_output_csv_entry.pack(padx=10, pady=5, fill="x")
        self.gff_query_start_button = ctk.CTkButton(page, text=_("开始基因查询"), height=40,
                                                    command=self.start_gff_query_task, font=self.app_font_bold)
        self.gff_query_start_button.pack(fill="x", padx=15, pady=15)

    def _load_initial_config(self):
        """
        在后台线程中异步加载配置文件，并更新UI。
        显示一个启动进度对话框。
        """
        # 立即显示启动进度对话框
        self._show_progress_dialog(
            title=_("图形界面启动中..."), # <-- 修改这里
            message=_("正在初始化应用程序和加载配置，请稍候..."),
            on_cancel=None # 启动阶段不允许取消
        )


        def startup_task_thread():
            try:
                self.startup_progress_queue.put((10, _("加载配置文件...")))
                # ... (加载配置文件的逻辑) ...

                self.startup_progress_queue.put((30, _("应用配置到UI...")))
                # **重要：先发送更新配置的数据到主线程**
                self.message_queue.put(("set_initial_config", (loaded_config_data, config_file_path)))
                # 在这里等待主线程处理完 `set_initial_config` 并完成大部分UI属性设置，
                # 但不阻塞当前后台线程太久，仅提供一个建议的等待点。
                # 实际Tkinter的UI更新是异步的，无法直接在这里完全同步。

                self.startup_progress_queue.put((50, _("更新基因组信息...")))
                # ... (get_genome_data_sources 逻辑) ...
                self.message_queue.put(("update_genome_dropdowns_async", genome_sources_data)) #

                self.startup_progress_queue.put((70, _("构建编辑器及工具UI...")))
                # **重要：在这里发送消息触发编辑器UI的构建和填充**
                self.message_queue.put(("populate_editor_ui_async", None))
                # 如果有其他懒加载的UI需要在启动时强制创建，也在这里发送消息

                self.startup_progress_queue.put((90, _("完成基本初始化...")))

            except Exception as e:
                self.startup_progress_queue.put((100, f"[ERROR] {_('启动过程中发生未知错误:')} {e}"))
                self.initial_config_loaded.set()
                return
            finally:
                # 无论成功失败，都标记初始配置加载完成
                self.initial_config_loaded.set()
                # 确保所有UI更新消息都已发送到队列，然后发送最终完成消息
                self.startup_progress_queue.put((100, _("启动完成！")))

        threading.Thread(target=startup_task_thread, daemon=True).start()

    def _apply_config_to_ui_async(self):  # 不再接收参数
        """
        在主线程中执行的UI更新部分，由消息队列触发。
        它从 self.current_config 中获取配置数据并应用到已创建的UI元素。
        """
        self._log_to_viewer(f"DEBUG: _apply_config_to_ui_async called.", "DEBUG")

        if not self.current_config:  # 如果没有加载配置
            self._log_to_viewer(_("没有加载配置，无法应用到UI (async)。"), level="WARNING")
            # 确保UI元素重置为默认或空值
            if hasattr(self, 'download_force_checkbox_var'): self.download_force_checkbox_var.set(False)
            if hasattr(self, 'download_proxy_var'): self.download_proxy_var.set(False)
            if hasattr(self, 'ai_proxy_var'): self.ai_proxy_var.set(False)
            if hasattr(self, 'integrate_excel_entry') and self.integrate_excel_entry.winfo_exists():
                self.integrate_excel_entry.delete(0, tk.END)
                self.integrate_excel_entry.insert(0, "")
            if hasattr(self, 'selected_bsa_assembly'): self.selected_bsa_assembly.set(_("无可用版本"))
            if hasattr(self, 'selected_hvg_assembly'): self.selected_hvg_assembly.set(_("无可用版本"))
            if hasattr(self, 'selected_homology_source_assembly'): self.selected_homology_source_assembly.set(
                _("无可用版本"))
            if hasattr(self, 'selected_homology_target_assembly'): self.selected_homology_target_assembly.set(
                _("无可用版本"))
            if hasattr(self, 'selected_gff_query_assembly'): self.selected_gff_query_assembly.set(_("无可用版本"))
            if hasattr(self, 'selected_bsa_sheet'): self.selected_bsa_sheet.set(_("请先指定Excel文件"))
            if hasattr(self, 'selected_hvg_sheet'): self.selected_hvg_sheet.set(_("请先指定Excel文件"))
            return

        # 从 self.current_config 中获取数据并更新 UI 元素
        self._update_download_genomes_list()  # 这个方法内部有检查
        self._update_ai_assistant_tab_info()  # 这个方法内部有检查
        self._load_prompts_to_ai_tab()  # 这个方法内部有检查

        downloader_cfg = self.current_config.downloader
        if hasattr(self, 'download_force_checkbox_var'):
            self.download_force_checkbox_var.set(downloader_cfg.force_download)
        proxies = downloader_cfg.proxies
        proxy_is_configured = bool(proxies and (proxies.http or proxies.https))
        if hasattr(self, 'download_proxy_var'):
            self.download_proxy_var.set(proxy_is_configured)
        if hasattr(self, 'ai_proxy_var'):
            self.ai_proxy_var.set(proxy_is_configured)

        integration_cfg = self.current_config.integration_pipeline
        if hasattr(self, 'selected_bsa_assembly'):
            self.selected_bsa_assembly.set(integration_cfg.bsa_assembly_id)
        if hasattr(self, 'selected_hvg_assembly'):
            self.selected_hvg_assembly.set(integration_cfg.hvg_assembly_id)

        if hasattr(self, 'integrate_excel_entry') and self.integrate_excel_entry.winfo_exists():
            self.integrate_excel_entry.delete(0, tk.END)
            self.integrate_excel_entry.insert(0, integration_cfg.input_excel_path)
        self._update_excel_sheet_dropdowns()  # 这个方法内部有检查

        if hasattr(self, 'selected_homology_source_assembly'):
            self.selected_homology_source_assembly.set(integration_cfg.bsa_assembly_id)
        if hasattr(self, 'selected_homology_target_assembly'):
            self.selected_homology_target_assembly.set(integration_cfg.hvg_assembly_id)
        default_gff_assembly = integration_cfg.bsa_assembly_id or integration_cfg.hvg_assembly_id
        if default_gff_assembly and hasattr(self, 'selected_gff_query_assembly'):
            self.selected_gff_query_assembly.set(default_gff_assembly)

        self._log_to_viewer(_("配置已成功应用到UI字段（异步）。"))

        # 核心：确保在配置加载后，编辑器UI的值被更新
        # _populate_editor_ui 内部会处理是首次构建还是更新值
        self._populate_editor_ui()


        self.initial_ui_setup_done.set()  # 标记初始UI设置完成

    def _populate_editor_ui(self):
        """
        根据当前的配置对象，动态生成或更新整个编辑器UI。
        此函数旨在实现“一次构建，多次更新”的策略。
        """
        self._log_to_viewer(
            f"DEBUG: _populate_editor_ui called. self.editor_widgets empty: {not self.editor_widgets}, self.current_config is: {type(self.current_config)}",
            "DEBUG")

        # 核心逻辑：只有当 self.editor_widgets 为空时才执行UI构建
        if not self.editor_widgets:  # 界面尚未构建（首次运行）
            self._log_to_viewer("DEBUG: self.editor_widgets is EMPTY. Performing FIRST-TIME UI BUILD.", "DEBUG")

            # 清除旧的 Tkinter 控件（防止意外残留）。
            for widget in self.editor_scroll_frame.winfo_children():
                widget.destroy()
            # 此时 self.editor_widgets 是空的，不需要 clear()，因为它会被 _build_editor_content 填充。

            # 如果没有加载配置，显示提示信息
            # 这部分逻辑已移动到 _build_editor_content 内部，由它来决定如何显示默认值或占位符
            # 在这里，我们只需确保 config_obj_data 传入 _build_editor_content
            # 如果 self.current_config 是 None，_build_editor_content 会从 config_structure 的默认值绘制

            self._log_to_viewer(_("正在根据配置动态生成编辑器界面 (首次构建)..."), "INFO")
            # 调用 _build_editor_content 来创建所有 UI 控件，并填充 self.editor_widgets
            # 传入 self.current_config，如果为 None，_build_editor_content 会使用默认值
            self._build_editor_content(self.editor_scroll_frame, self.current_config, [])
            self._log_to_viewer("DEBUG: First-time UI build COMPLETED. self.editor_widgets now contains: " + str(
                len(self.editor_widgets)) + " widgets.", "DEBUG")

            # 确保只有在UI构建完成后才设置标志 (editor_ui_loaded 是在 __init__ 中初始化的)
            # 这里的通知仅在 _populate_editor_ui 被异步流程触发时才有意义
            # 考虑到 _populate_editor_ui 现在在 _init_pages_and_final_setup 中同步调用
            # 并且它只构建一次，所以这里不发送 "editor_ui_populated_done" 消息，
            # 而是由 _init_pages_and_final_setup 确保其在启动时完成。
            self.editor_ui_loaded = True  # 标记为已加载

        # 无论是否首次构建，只要有 current_config，就更新UI值
        if self.current_config:
            self._log_to_viewer(_("编辑器界面已存在，正在更新配置值..."), "INFO")
            self._update_editor_ui_values()
            self._log_to_viewer("DEBUG: Existing UI values UPDATED.", "DEBUG")
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="normal")
        else:
            # self.editor_widgets 不为空，但 current_config 为空 (例如，用户手动清空了配置)
            # 此时需要清除现有值，并显示“未加载配置”提示。
            # _populate_editor_ui 已经被修改为根据 current_config 的存在来决定显示内容
            # 所以这里只需确保将所有值设为空，_update_editor_ui_values 内部会处理
            if self.editor_widgets:  # 如果之前有构建过UI
                self._log_to_viewer(
                    "DEBUG: current_config is EMPTY, but editor_widgets is NOT. Clearing existing UI values.", "DEBUG")
                # 触发一次空配置的更新，让所有控件显示默认/空值
                self._update_editor_ui_values_from_none_config()  # 新增辅助方法

            # 显示“未加载配置”的提示 (这个标签在 _create_editor_frame 中创建)
            if hasattr(self, 'editor_no_config_label') and self.editor_no_config_label.winfo_exists():
                self.editor_no_config_label.grid(row=0, column=0, pady=50, sticky="nsew")
                self.editor_scroll_frame.grid_columnconfigure(0, weight=1)
            if hasattr(self, 'save_editor_button') and self.save_editor_button.winfo_exists():
                self.save_editor_button.configure(state="disabled")



    def _build_editor_content(self, parent_widget, config_obj_data, key_path):
        self._log_to_viewer(f"DEBUG: _build_editor_content called for path: {'.'.join(key_path)}", "DEBUG")

        # 检查并隐藏 "未加载配置" 标签，因为现在正在构建内容
        if hasattr(self, 'editor_no_config_label') and self.editor_no_config_label.winfo_exists():
            self.editor_no_config_label.grid_remove()

        # 获取当前路径在 config_structure 中的定义
        current_struct_def = self._get_structure_for_path(self.config_structure, key_path)

        # 针对顶级调用，如果 key_path 为空，current_struct_def 就是 self.config_structure 本身
        # 此时它没有 'items' 键，需要特殊处理，直接从 config_structure 遍历顶级 sections
        if not key_path: # This is the very first call
            items_to_process = self.config_structure.items()
            is_root_call = True
        elif not current_struct_def or "items" not in current_struct_def:
            self._log_to_viewer(
                f"DEBUG: No 'items' definition found for path: {'.'.join(key_path)}. Skipping build for this branch (might be a leaf node or an invalid path in config_structure).",
                "DEBUG")
            return
        else:
            items_to_process = current_struct_def["items"].items()
            is_root_call = False

        current_row_in_parent_frame = 0

        for field_name, field_def_value in items_to_process:
            current_item_full_path = key_path + [field_name]
            full_path_str = ".".join(current_item_full_path)
            self._log_to_viewer(f"DEBUG: Processing field: {full_path_str}", "DEBUG")

            # 在这里重新获取 item_definition，因为它可能是一个子项 (field_def_value)
            # 或者在 root_call 中，field_def_value 本身就是 section 定义
            if is_root_call:
                item_definition = field_def_value # field_def_value is directly the section dict
            else:
                item_definition = self._get_structure_for_path(self.config_structure, current_item_full_path)

            if item_definition is None:
                self._log_to_viewer(f"DEBUG: No UI definition found for field: {full_path_str}. Skipping.", "DEBUG")
                continue # Skip this field if no definition is found

            # 获取当前字段在实际 config_obj_data 中的值
            actual_field_value = None
            if config_obj_data: # Only try to get actual value if config_obj_data is not None
                if isinstance(config_obj_data, dict):
                    actual_field_value = config_obj_data.get(field_name)
                elif is_dataclass(config_obj_data):
                    actual_field_value = getattr(config_obj_data, field_name, None)
            self._log_to_viewer(f"DEBUG:   Actual value for {full_path_str}: {actual_field_value}", "DEBUG")


            # --- Case 1: The field represents a nested section (dict in config_structure with 'title' and 'items') ---
            if isinstance(item_definition, dict) and "items" in item_definition:
                section_title = item_definition.get("title", field_name.replace("_", " ").title())
                self._log_to_viewer(f"DEBUG:   Creating nested section: {section_title} at path: {full_path_str}", "DEBUG")

                if current_row_in_parent_frame > 0: # Add a separator if it's not the very first item
                    ctk.CTkFrame(parent_widget, height=2, fg_color=("gray70", "gray40")).grid(
                        row=current_row_in_parent_frame, column=0, sticky="ew", padx=0, pady=(20, 10))
                    current_row_in_parent_frame += 1

                ctk.CTkLabel(parent_widget, text=f"◇ {section_title} ◇", font=self.app_subtitle_font,
                             text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"]).grid(
                    row=current_row_in_parent_frame, column=0, sticky="ew", padx=10, pady=(10, 15))
                current_row_in_parent_frame += 1

                section_outer_frame = ctk.CTkFrame(parent_widget, corner_radius=8, fg_color="transparent",
                                                   border_width=1, border_color=("gray70", "gray40"))
                section_outer_frame.grid(row=current_row_in_parent_frame, column=0, sticky="ew", padx=5, pady=5)
                section_outer_frame.grid_columnconfigure(0, weight=1)

                # 递归调用，传入对应的实际配置数据子对象
                # 如果 actual_field_value 是 None (例如，config_obj_data 是 None 或字段不存在)，
                # 递归调用时会使用该 None，_build_editor_content 会根据 config_structure 的默认值来绘制。
                self._build_editor_content(section_outer_frame, actual_field_value, current_item_full_path)
                current_row_in_parent_frame += 1
                continue

            # --- Case 2: The field is a leaf node (tuple in config_structure) ---
            elif isinstance(item_definition, tuple) and len(item_definition) >= 3:
                label_text = item_definition[0]
                tooltip_text = item_definition[1]
                widget_type = item_definition[2]
                default_val_from_structure = item_definition[3] if len(item_definition) > 3 else None

                self._log_to_viewer(f"DEBUG:   Creating widget type {widget_type} for field: {full_path_str}", "DEBUG")


                item_container_frame = ctk.CTkFrame(parent_widget, fg_color="transparent")
                item_container_frame.grid(row=current_row_in_parent_frame, column=0, sticky="ew", pady=5, padx=5)
                item_container_frame.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(item_container_frame, text=label_text, font=self.app_font).grid(row=0, column=0,
                                                                                             sticky="w", padx=10,
                                                                                             pady=5)
                if tooltip_text:
                    ctk.CTkLabel(item_container_frame, text=tooltip_text, font=self.app_comment_font,
                                 text_color=self.secondary_text_color, wraplength=400, justify="left").grid(row=1,
                                                                                                            column=0,
                                                                                                            columnspan=2,
                                                                                                            sticky="w",
                                                                                                            padx=10,
                                                                                                            pady=(0, 5))
                widget = None
                if widget_type == "switch":
                    var = tk.BooleanVar() # Value will be set in _update_editor_ui_values
                    widget = ctk.CTkSwitch(item_container_frame, text="", variable=var)
                    widget.grid(row=0, column=1, sticky="w", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = (widget, var)
                elif widget_type == "textbox":
                    widget = ctk.CTkTextbox(item_container_frame, height=120, font=self.app_font, wrap="word")
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5, rowspan=2)
                    self.editor_widgets[full_path_str] = widget
                    self._bind_mouse_wheel_to_scrollable(widget)
                elif widget_type == "optionmenu":
                    # For optionmenu, ensure values are derived from default_val_from_structure
                    options_list = [str(v) for v in default_val_from_structure] if isinstance(default_val_from_structure, list) else []
                    var = tk.StringVar(value=options_list[0] if options_list else "") # Default value
                    widget = ctk.CTkOptionMenu(item_container_frame, variable=var, values=options_list,
                                               font=self.app_font, dropdown_font=self.app_font)
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = widget
                elif widget_type == "model_selector":
                    model_selector_frame = ctk.CTkFrame(item_container_frame, fg_color="transparent")
                    model_selector_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    model_selector_frame.grid_columnconfigure(0, weight=1)

                    entry = ctk.CTkEntry(model_selector_frame, font=self.app_font)
                    entry.grid(row=0, column=0, sticky="ew")

                    dropdown_var = tk.StringVar(value="") # Initial empty value
                    dropdown = ctk.CTkOptionMenu(model_selector_frame, variable=dropdown_var, values=[_("点击刷新")],
                                                 font=self.app_font, dropdown_font=self.app_font)
                    dropdown.grid(row=0, column=0, sticky="ew")
                    dropdown.grid_remove() # Initially hide dropdown, show entry

                    provider_key_for_button = ""
                    try: # Safely get provider key from path
                        providers_index = current_item_full_path.index("providers")
                        if len(current_item_full_path) > providers_index + 1:
                            provider_key_for_button = current_item_full_path[providers_index + 1]
                    except ValueError:
                        pass # 'providers' not in path

                    refresh_button = ctk.CTkButton(model_selector_frame, text=_("刷新"), width=60, font=self.app_font,
                                                   command=lambda p=provider_key_for_button: self._fetch_ai_models(p))
                    refresh_button.grid(row=0, column=1, padx=(10, 0))

                    self.editor_widgets[full_path_str] = (model_selector_frame, entry, dropdown, dropdown_var, refresh_button)

                else: # Default to entry for other types
                    widget = ctk.CTkEntry(item_container_frame, font=self.app_font)
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = widget

                current_row_in_parent_frame += 1
                if tooltip_text and widget_type != "textbox": # Tooltip takes up extra row if not a textbox
                    current_row_in_parent_frame += 1
            else: # This means item_definition is not a dict with "items" and not a tuple
                self._log_to_viewer(f"DEBUG: Field {full_path_str} has an unexpected definition type in config_structure ({type(item_definition)}). Skipping UI creation.", "DEBUG")
                pass

        parent_widget.grid_rowconfigure(current_row_in_parent_frame, weight=1)

    def _build_editor_content(self, parent_widget, config_obj_data, key_path):
        self._log_to_viewer(f"DEBUG: _build_editor_content called for path: {'.'.join(key_path)}", "DEBUG")

        # 获取当前路径在 config_structure 中的定义
        current_struct_def = self._get_structure_for_path(self.config_structure, key_path)

        # 针对顶级调用，如果 key_path 为空，current_struct_def 就是 self.config_structure 本身
        # 此时它没有 'items' 键，需要特殊处理，直接从 config_structure 遍历顶级 sections
        if not key_path: # This is the very first call
            items_to_process = self.config_structure.items()
            is_root_call = True
        elif not current_struct_def or "items" not in current_struct_def:
            self._log_to_viewer(
                f"DEBUG: No 'items' definition found for path: {'.'.join(key_path)}. Skipping build for this branch (might be a leaf node or an invalid path in config_structure).",
                "DEBUG")
            return
        else:
            items_to_process = current_struct_def["items"].items()
            is_root_call = False

        current_row_in_parent_frame = 0

        for field_name, field_def_value in items_to_process:
            current_item_full_path = key_path + [field_name]
            full_path_str = ".".join(current_item_full_path)
            self._log_to_viewer(f"DEBUG: Processing field: {full_path_str}", "DEBUG")

            # 在这里重新获取 item_definition，因为它可能是一个子项 (field_def_value)
            # 或者在 root_call 中，field_def_value 本身就是 section 定义
            if is_root_call:
                item_definition = field_def_value # field_def_value is directly the section dict
            else:
                item_definition = self._get_structure_for_path(self.config_structure, current_item_full_path)

            if item_definition is None:
                self._log_to_viewer(f"DEBUG: No UI definition found for field: {full_path_str}. Skipping.", "DEBUG")
                continue # Skip this field if no definition is found

            # 获取当前字段在实际 config_obj_data 中的值
            actual_field_value = None
            if config_obj_data:
                if isinstance(config_obj_data, dict):
                    actual_field_value = config_obj_data.get(field_name)
                elif is_dataclass(config_obj_data):
                    actual_field_value = getattr(config_obj_data, field_name, None)
            self._log_to_viewer(f"DEBUG:   Actual value for {full_path_str}: {actual_field_value}", "DEBUG")


            # --- Case 1: The field represents a nested section (dict in config_structure with 'title' and 'items') ---
            if isinstance(item_definition, dict) and "items" in item_definition:
                section_title = item_definition.get("title", field_name.replace("_", " ").title())
                self._log_to_viewer(f"DEBUG:   Creating nested section: {section_title} at path: {full_path_str}", "DEBUG")

                if current_row_in_parent_frame > 0:
                    ctk.CTkFrame(parent_widget, height=2, fg_color=("gray70", "gray40")).grid(
                        row=current_row_in_parent_frame, column=0, sticky="ew", padx=0, pady=(20, 10))
                    current_row_in_parent_frame += 1

                ctk.CTkLabel(parent_widget, text=f"◇ {section_title} ◇", font=self.app_subtitle_font,
                             text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"]).grid(
                    row=current_row_in_parent_frame, column=0, sticky="ew", padx=10, pady=(10, 15))
                current_row_in_parent_frame += 1

                section_outer_frame = ctk.CTkFrame(parent_widget, corner_radius=8, fg_color="transparent",
                                                   border_width=1, border_color=("gray70", "gray40"))
                section_outer_frame.grid(row=current_row_in_parent_frame, column=0, sticky="ew", padx=5, pady=5)
                section_outer_frame.grid_columnconfigure(0, weight=1)

                # 递归调用，传入对应的实际配置数据子对象
                self._build_editor_content(section_outer_frame, actual_field_value, current_item_full_path)
                current_row_in_parent_frame += 1
                continue

            # --- Case 2: The field is a leaf node (tuple in config_structure) ---
            elif isinstance(item_definition, tuple) and len(item_definition) >= 3:
                label_text = item_definition[0]
                tooltip_text = item_definition[1]
                widget_type = item_definition[2]
                default_val_from_structure = item_definition[3] if len(item_definition) > 3 else None

                self._log_to_viewer(f"DEBUG:   Creating widget type {widget_type} for field: {full_path_str}", "DEBUG")


                item_container_frame = ctk.CTkFrame(parent_widget, fg_color="transparent")
                item_container_frame.grid(row=current_row_in_parent_frame, column=0, sticky="ew", pady=5, padx=5)
                item_container_frame.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(item_container_frame, text=label_text, font=self.app_font).grid(row=0, column=0,
                                                                                             sticky="w", padx=10,
                                                                                             pady=5)
                if tooltip_text:
                    ctk.CTkLabel(item_container_frame, text=tooltip_text, font=self.app_comment_font,
                                 text_color=self.secondary_text_color, wraplength=400, justify="left").grid(row=1,
                                                                                                            column=0,
                                                                                                            columnspan=2,
                                                                                                            sticky="w",
                                                                                                            padx=10,
                                                                                                            pady=(0, 5))
                widget = None
                if widget_type == "switch":
                    var = tk.BooleanVar() # 值将在 _update_editor_ui_values 中设置
                    widget = ctk.CTkSwitch(item_container_frame, text="", variable=var)
                    widget.grid(row=0, column=1, sticky="w", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = (widget, var)
                elif widget_type == "textbox":
                    widget = ctk.CTkTextbox(item_container_frame, height=120, font=self.app_font, wrap="word")
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5, rowspan=2)
                    self.editor_widgets[full_path_str] = widget
                    self._bind_mouse_wheel_to_scrollable(widget)
                elif widget_type == "optionmenu":
                    options = [str(v) for v in default_val_from_structure] if isinstance(default_val_from_structure, list) else []
                    var = tk.StringVar(value=options[0] if options else "")
                    widget = ctk.CTkOptionMenu(item_container_frame, variable=var, values=options,
                                               font=self.app_font, dropdown_font=self.app_font)
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = widget
                elif widget_type == "model_selector":
                    model_selector_frame = ctk.CTkFrame(item_container_frame, fg_color="transparent")
                    model_selector_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    model_selector_frame.grid_columnconfigure(0, weight=1)

                    entry = ctk.CTkEntry(model_selector_frame, font=self.app_font)
                    entry.grid(row=0, column=0, sticky="ew")

                    dropdown_var = tk.StringVar(value="")
                    dropdown = ctk.CTkOptionMenu(model_selector_frame, variable=dropdown_var, values=[_("点击刷新")],
                                                 font=self.app_font, dropdown_font=self.app_font)
                    dropdown.grid(row=0, column=0, sticky="ew")
                    dropdown.grid_remove()

                    provider_key_for_button = ""
                    try: # Safely get provider key
                        providers_index = key_path.index("providers")
                        if len(key_path) > providers_index + 1:
                            provider_key_for_button = key_path[providers_index + 1]
                    except ValueError:
                        pass # 'providers' not in path_parts


                    refresh_button = ctk.CTkButton(model_selector_frame, text=_("刷新"), width=60, font=self.app_font,
                                                   command=lambda p=provider_key_for_button: self._fetch_ai_models(p))
                    refresh_button.grid(row=0, column=1, padx=(10, 0))

                    self.editor_widgets[full_path_str] = (model_selector_frame, entry, dropdown, dropdown_var, refresh_button)

                else: # Default to entry for other types
                    widget = ctk.CTkEntry(item_container_frame, font=self.app_font)
                    widget.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
                    self.editor_widgets[full_path_str] = widget

                current_row_in_parent_frame += 1
                if tooltip_text and widget_type != "textbox":
                    current_row_in_parent_frame += 1
            else: # This else block handles field_def_value not being a dict with "items" and not a tuple
                # This means it's a field_def_value that is neither a nested section nor a leaf node as expected.
                # It might be a direct dictionary for raw YAML, which _build_editor_content doesn't explicitly create now.
                # Or it's a structure that isn't properly defined in config_structure.
                self._log_to_viewer(f"DEBUG: Field {full_path_str} has an unexpected definition type in config_structure ({type(item_definition)}). Skipping UI creation.", "DEBUG")
                pass

        parent_widget.grid_rowconfigure(current_row_in_parent_frame, weight=1)


    def _get_structure_for_path(self, current_structure, path_parts):
        """
        根据路径查找 config_structure 中对应的配置项定义。
        这个函数现在会先尝试在当前层级直接找到 `part`，如果 `current_structure` 是一个字典
        并且有 `items` 键，它还会尝试在 `items` 键中查找 `part`。

        返回可以是:
        - None (如果路径未找到)
        - tuple (如果找到了一个叶子节点，即 (display_name, tooltip, widget_type, default_value))
        - dict (如果找到了一个嵌套的section定义，即 {"title": "...", "items": {...}})
        """
        temp_structure = current_structure
        self._log_to_viewer(f"DEBUG: _get_structure_for_path called for path_parts: {path_parts}", "DEBUG")
        for i, part in enumerate(path_parts):
            self._log_to_viewer(
                f"DEBUG:   Current part: {part}, Current temp_structure type: {type(temp_structure)}", "DEBUG")
            if isinstance(temp_structure, dict):
                # 优先在当前字典层级查找
                if part in temp_structure:
                    temp_structure = temp_structure[part]
                    self._log_to_viewer(f"DEBUG:     Found part in current level: {part}", "DEBUG")
                # 如果当前层级没有，且有 'items' 键，则尝试在 'items' 字典中查找
                elif "items" in temp_structure and isinstance(temp_structure["items"], dict) and part in \
                        temp_structure["items"]:
                    temp_structure = temp_structure["items"][part]
                    self._log_to_viewer(f"DEBUG:     Found part in 'items' level: {part}", "DEBUG")
                else:
                    self._log_to_viewer(
                        f"DEBUG:     Part '{part}' not found in current structure or its 'items'. Returning None.",
                        "DEBUG")
                    return None  # 路径未找到
            else:
                self._log_to_viewer(f"DEBUG:   temp_structure is not a dict at part '{part}'. Returning None.",
                                    "DEBUG")
                return None  # 不是字典，无法继续遍历
        self._log_to_viewer(
            f"DEBUG: Successfully resolved structure for path. Returning type: {type(temp_structure)}", "DEBUG")
            
        return temp_structure

    def _setup_fonts(self):
        """设置全局字体，并实现字体栈回退机制。"""
        # 定义一个字体栈，程序会从前到后依次尝试使用
        font_stack = ["Microsoft YaHei UI", "Segoe UI", "Calibri", "Helvetica", "Arial", "sans-serif"]
        available_fonts = tkfont.families()

        selected_font = "sans-serif"  # 默认的回退字体
        for font_name in font_stack:
            if font_name in available_fonts:
                selected_font = font_name
                print(f"INFO: UI font has been set to: {selected_font}")
                break

        self.app_font = ctk.CTkFont(family=selected_font, size=14)
        self.app_font_bold = ctk.CTkFont(family=selected_font, size=15, weight="bold")
        self.app_subtitle_font = ctk.CTkFont(family=selected_font, size=16)
        self.app_title_font = ctk.CTkFont(family=selected_font, size=24, weight="bold")
        self.app_comment_font = ctk.CTkFont(family=selected_font, size=12)

    def update_language_ui(self, lang_code_to_set=None):
        global _
        if not lang_code_to_set: lang_code_to_set = self.ui_settings.get('language', 'zh-hans')
        try:
            _ = setup_cli_i18n(language_code=lang_code_to_set, app_name="cotton_toolkit")
        except Exception as e:
            _ = lambda s: s
            logging.error(f"语言设置错误: {e}")

        # 1. 更新普通控件
        for widget, info in self.translatable_widgets.items():
            if not (widget and widget.winfo_exists()): continue
            if isinstance(info, tuple):
                op, data = info[0], info[1:]
                if op == "values": widget.configure(values=[_(v) for v in data[0]])
            elif isinstance(info, str):
                widget.configure(text=_(info))

        # --- 注册并更新下载页面的新按钮 ---
        if hasattr(self, 'dl_select_all_button'):
            self.dl_select_all_button.configure(text=_("全选"))
        if hasattr(self, 'dl_deselect_all_button'):
            self.dl_deselect_all_button.configure(text=_("取消全选"))
        if hasattr(self, 'dl_force_switch_label'):
            self.dl_force_switch_label.configure(text=_("强制重新下载:"))

        # 2. 更新下拉菜单的当前显示值
        display_lang_name = self.LANG_CODE_TO_NAME.get(lang_code_to_set, "简体中文")
        if hasattr(self, 'language_optionmenu'): self.language_optionmenu.set(display_lang_name)
        if hasattr(self, 'appearance_mode_optionemenu'):
            current_mode_value = self.ui_settings.get('appearance_mode', 'System')
            mode_map_to_display = {"Light": _("浅色"), "Dark": _("深色"), "System": _("系统")}
            display_text = mode_map_to_display.get(current_mode_value, _("系统"))
            self.appearance_mode_optionemenu.set(display_text)

        # 3. 更新工具选项卡的显示文本
        if hasattr(self, 'tools_notebook') and hasattr(self.tools_notebook, '_segmented_button'):
            try:
                tab_display_names = {
                    "download": _("数据下载"), "homology": _("基因组转换"), "gff_query": _("基因位点查询"),
                    "annotation": _("功能注释"), "ai_assistant": _("AI 助手"), "xlsx_to_csv": _("XLSX转CSV")
                }

                # Get the currently selected tab's frame object to restore selection later
                current_selected_display_name = self.tools_notebook.get()
                current_selected_frame = self.tools_notebook.tab(current_selected_display_name)

                # Prepare the new list of display names and the new tab->frame dictionary
                new_display_values = []
                new_tab_dict = {}
                restored_selection_name = None

                for simple_key, internal_key in self.tab_keys.items():
                    # Use the stable self.tool_tab_frames to get the frame
                    frame = self.tool_tab_frames.get(internal_key)
                    if frame:
                        new_display_name = tab_display_names.get(simple_key, internal_key)
                        new_display_values.append(new_display_name)
                        new_tab_dict[new_display_name] = frame
                        # Check if this is the frame we need to re-select
                        if frame == current_selected_frame:
                            restored_selection_name = new_display_name

                # Atomically update the internal state of the CTkTabView
                self.tools_notebook._tab_dict = new_tab_dict
                self.tools_notebook._name_list = new_display_values
                self.tools_notebook._segmented_button.configure(values=new_display_values)

                # Restore the selection with the new (translated) display name
                if restored_selection_name:
                    self.tools_notebook.set(restored_selection_name)

            except Exception as e:
                logging.error(f"动态更新TabView时发生严重错误: {e}")

        # 4. 更新窗口标题
        self.title(_(self.title_text_key))

    def _update_assembly_id_dropdowns(self):
        """直接将配置对象传递给后台函数。"""
        if not self.current_config:
            return
        self._log_to_viewer(_("正在更新基因组版本列表..."))

        genome_sources = get_genome_data_sources(self.current_config)

        if genome_sources and isinstance(genome_sources, dict):
            assembly_ids = list(genome_sources.keys())
            if not assembly_ids:
                assembly_ids = [_("无可用版本")]
        else:
            assembly_ids = [_("无法加载基因组源")]
            self._log_to_viewer(_("警告: 未能从配置文件或源文件中加载基因组列表。"), level="WARNING")

        dropdowns = [
            # 整合分析选项卡中的下拉菜单
            self.integrate_bsa_assembly_dropdown,
            self.integrate_hvg_assembly_dropdown,
            # 同源映射选项卡中的下拉菜单
            # 增加检查，确保这些控件已经被创建
            # self.homology_map_source_assembly_dropdown, # <-- 移除直接引用
            # self.homology_map_target_assembly_dropdown, # <-- 移除直接引用
            # GFF 查询选项卡中的下拉菜单
            # self.gff_query_assembly_dropdown # <-- 移除直接引用
        ]

        # 遍历所有可能的下拉菜单，如果它们已经存在，就更新它们
        if hasattr(self, 'integrate_bsa_assembly_dropdown') and self.integrate_bsa_assembly_dropdown.winfo_exists():
            self.integrate_bsa_assembly_dropdown.configure(values=assembly_ids)
            # 尝试设置默认值
            if self.current_config.integration_pipeline.bsa_assembly_id in assembly_ids:
                self.selected_bsa_assembly.set(self.current_config.integration_pipeline.bsa_assembly_id)
            elif assembly_ids and assembly_ids[0] != _("无可用版本") and assembly_ids[0] != _("无法加载基因组源"):
                self.selected_bsa_assembly.set(assembly_ids[0])

        if hasattr(self, 'integrate_hvg_assembly_dropdown') and self.integrate_hvg_assembly_dropdown.winfo_exists():
            self.integrate_hvg_assembly_dropdown.configure(values=assembly_ids)
            if self.current_config.integration_pipeline.hvg_assembly_id in assembly_ids:
                self.selected_hvg_assembly.set(self.current_config.integration_pipeline.hvg_assembly_id)
            elif assembly_ids and assembly_ids[0] != _("无可用版本") and assembly_ids[0] != _("无法加载基因组源"):
                self.selected_hvg_assembly.set(assembly_ids[0])

        # 对于懒加载的选项卡中的下拉菜单，当它们被创建时，它们会从 _apply_config_to_ui 再次触发更新，
        # 此时 self.selected_homology_source_assembly 等变量会被正确设置。
        # 这里我们只检查并更新那些可能在启动时就已经存在的（比如“整合分析”页面）。

        # 由于同源映射和GFF查询的下拉菜单是懒加载的，在它们被创建时，
        # 它们会尝试根据 self.selected_homology_source_assembly / self.selected_gff_query_assembly 的值来设置。
        # 所以，我们只需要确保在 `_apply_config_to_ui` 阶段，这些 StringVar 的值被正确设定即可，
        # 不需要在这里提前配置这些下拉菜单的 `values`。
        # 实际的 `configure(values=...)` 和 `set(default_value)` 会在它们各自的 `_populate_xxx_tab_structure` 方法
        # 被调用时，通过 `_update_assembly_id_dropdowns` 再次触发（或者直接在 `_populate_xxx_tab_structure` 内部完成）。
        #
        # 因此，在 `_apply_config_to_ui` 的末尾，更新这些 StringVar 的值：
        # self.selected_homology_source_assembly.set(integration_cfg.bsa_assembly_id)
        # self.selected_homology_target_assembly.set(integration_cfg.hvg_assembly_id)
        # self.selected_gff_query_assembly.set(default_gff_assembly)
        # 这样，当对应的 Tab 被懒加载时，下拉菜单会使用这些已经设置好的值。

    #用于在没有加载配置文件时清空编辑器UI的值
    def _update_editor_ui_values_from_none_config(self):
        """
        当 current_config 为 None 时，将编辑器UI中的所有值重置为默认/空状态。
        """

        # 递归遍历 config_structure，清空所有控件的值
        def recursive_reset_ui(config_struct_part_items, path_parts):
            for field_name_in_struct, field_def_value_from_struct in config_struct_part_items:
                field_full_path_str = ".".join(path_parts + [field_name_in_struct])
                if field_full_path_str in self.editor_widgets:
                    widget_info = self.editor_widgets[field_full_path_str]
                    if isinstance(widget_info, tuple) and isinstance(widget_info[0], ctk.CTkSwitch):
                        _widget, var = widget_info
                        var.set(False)  # Default for switch
                    elif isinstance(widget_info, ctk.CTkTextbox):
                        widget_info.delete("1.0", tk.END)
                        widget_info.insert("1.0", "")  # Empty for textbox
                    elif isinstance(widget_info, ctk.CTkOptionMenu):
                        options = widget_info.cget("values")
                        if options:
                            widget_info.set(options[0])  # Set to first option
                        else:
                            widget_info.set("")
                    elif isinstance(widget_info, tuple) and len(widget_info) == 5:  # Model selector
                        _frame, entry_widget, dropdown_widget, dropdown_var, _button = widget_info
                        entry_widget.delete(0, tk.END)
                        entry_widget.insert(0, "")  # Empty for entry
                        dropdown_var.set("")  # Empty for dropdown
                        entry_widget.grid()  # Show entry, hide dropdown
                        dropdown_widget.grid_remove()
                    elif isinstance(widget_info, ctk.CTkEntry):
                        widget_info.delete(0, tk.END)
                        widget_info.insert(0, "")  # Empty for entry

                # Recursively reset nested sections
                if isinstance(field_def_value_from_struct, dict) and "items" in field_def_value_from_struct:
                    recursive_reset_ui(field_def_value_from_struct["items"].items(),
                                       path_parts + [field_name_in_struct])

        # Start recursion from the top-level config_structure
        recursive_reset_ui(self.config_structure.items(), [])


    def _update_excel_sheet_dropdowns(self):
        excel_path = self.integrate_excel_entry.get().strip()

        # 如果路径为空或文件不存在，重置下拉菜单并返回
        if not excel_path or not os.path.exists(excel_path):
            self.integrate_bsa_sheet_dropdown.configure(values=[_("请先指定有效的Excel文件")])
            self.integrate_hvg_sheet_dropdown.configure(values=[_("请先指定有效的Excel文件")])
            self.excel_sheet_cache.pop(excel_path, None)  # 从缓存中移除无效路径
            return

        # 如果文件已在缓存中，直接使用缓存数据更新 UI
        if excel_path in self.excel_sheet_cache:
            sheet_names_to_set = self.excel_sheet_cache[excel_path]
            self._update_sheet_dropdowns_ui(sheet_names_to_set)  # 调用新的 UI 更新方法
            return

        # 文件不在缓存中，异步读取
        self._log_to_viewer(_("正在异步读取Excel工作表，请稍候..."))
        # 立即更新 UI，显示加载状态
        self.integrate_bsa_sheet_dropdown.configure(values=[_("读取中...")])
        self.integrate_hvg_sheet_dropdown.configure(values=[_("读取中...")])

        # 启动一个新线程来读取Excel文件
        def load_sheets_thread():
            try:
                xls = pd.ExcelFile(excel_path)  #
                sheet_names_from_file = xls.sheet_names  #
                self.excel_sheet_cache[excel_path] = sheet_names_from_file  # 缓存结果
                # 将结果和 Excel 路径放入主消息队列
                self.message_queue.put(("update_sheets_dropdown", (sheet_names_from_file, excel_path, None)))
            except Exception as e:
                # 将错误信息放入主消息队列
                self.message_queue.put(
                    ("update_sheets_dropdown", ([], excel_path, f"{_('错误: 无法读取Excel文件')}: {e}")))

        threading.Thread(target=load_sheets_thread, daemon=True).start()

    def _update_sheet_dropdowns_ui(self, sheet_names_to_set, excel_path_for_error=None, error_msg=None):
        """
        实际更新Excel Sheet下拉菜单UI的方法。
        这个方法应该只在主线程中通过消息队列调用。
        """
        bsa_dropdown = self.integrate_bsa_sheet_dropdown
        hvg_dropdown = self.integrate_hvg_sheet_dropdown

        if error_msg:
            self._log_to_viewer(f"{error_msg}", level="ERROR")
            sheet_names_to_set = [_("读取Excel失败")]
            # 如果是错误，并且缓存中存在，为了避免下次还报错，可以考虑清除缓存
            if excel_path_for_error and excel_path_for_error in self.excel_sheet_cache:
                self.excel_sheet_cache.pop(excel_path_for_error, None)

        if not sheet_names_to_set:  # 处理空列表或错误情况
            sheet_names_to_set = [_("Excel文件中无工作表")]

        # 更新下拉菜单的值
        if bsa_dropdown and bsa_dropdown.winfo_exists():
            bsa_dropdown.configure(values=sheet_names_to_set)
        if hvg_dropdown and hvg_dropdown.winfo_exists():
            hvg_dropdown.configure(values=sheet_names_to_set)

        # 尝试设置默认选中值
        if self.current_config:
            # 访问 MainConfig 实例的属性，而不是字典的 get 方法
            cfg_bsa_sheet = self.current_config.integration_pipeline.bsa_sheet_name
            cfg_hvg_sheet = self.current_config.integration_pipeline.hvg_sheet_name

            if cfg_bsa_sheet in sheet_names_to_set:
                self.selected_bsa_sheet.set(cfg_bsa_sheet)
            elif sheet_names_to_set and sheet_names_to_set[0] != _("读取Excel失败") and sheet_names_to_set[0] != _(
                    "Excel文件中无工作表"):
                self.selected_bsa_sheet.set(sheet_names_to_set[0])

            if cfg_hvg_sheet in sheet_names_to_set:
                self.selected_hvg_sheet.set(cfg_hvg_sheet)
            elif sheet_names_to_set and sheet_names_to_set[0] != _("读取Excel失败") and sheet_names_to_set[0] != _(
                    "Excel文件中无工作表"):
                self.selected_hvg_sheet.set(sheet_names_to_set[0])

    def browse_integrate_excel(self):  #
        filepath = filedialog.askopenfilename(title=_("选择输入Excel文件"),
                                              filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*")))  #
        if filepath:  #
            self.integrate_excel_entry.delete(0, tk.END)  #
            self.integrate_excel_entry.insert(0, filepath)  #
            self._update_excel_sheet_dropdowns()  #

    def start_integrate_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("整合分析")

        # 将UI参数收集移到包装器内部，确保在线程中获取最新值
        def task_wrapper():
            success = False
            try:
                cfg_pipeline = self.current_config.setdefault('integration_pipeline', {})
                cfg_pipeline['bsa_assembly_id'] = self.selected_bsa_assembly.get()
                cfg_pipeline['hvg_assembly_id'] = self.selected_hvg_assembly.get()
                cfg_pipeline['bsa_sheet_name'] = self.selected_bsa_sheet.get()
                cfg_pipeline['hvg_sheet_name'] = self.selected_hvg_sheet.get()
                excel_override = self.integrate_excel_entry.get().strip() or None

                self.gui_status_callback(f"{self.active_task_name} {_('任务开始...')}")
                self.progress_bar.grid();
                self.progress_bar.set(0)

                success = integrate_bsa_with_hvg(
                    config=self.current_config,
                    input_excel_path_override=excel_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback,
                )
            except Exception as e:
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                self.task_done_callback(success, self.active_task_name)

        threading.Thread(target=task_wrapper, daemon=True).start()

    def start_homology_map_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因组转换")

        gene_ids_text = self.homology_map_genes_entry.get("1.0", tk.END).strip()
        placeholder_text = _(self.placeholder_genes_homology_key)
        source_gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if
                                line.strip() and line.strip() != placeholder_text] if gene_ids_text != placeholder_text else []
        if not source_gene_ids_list:
            self.show_error_message(_("输入缺失"), _("请输入要映射的源基因ID。"));
            self._update_button_states(False);
            return

        source_assembly_id_override = self.selected_homology_source_assembly.get()
        target_assembly_id_override = self.selected_homology_target_assembly.get()
        s_to_b_homology_file_override = self.homology_map_sb_file_entry.get().strip() or None
        b_to_t_homology_file_override = self.homology_map_bt_file_entry.get().strip() or None
        output_csv_path = self.homology_map_output_csv_entry.get().strip() or None

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_homology_mapping_standalone, kwargs={
            "config": self.current_config, "source_gene_ids_override": source_gene_ids_list,
            "source_assembly_id_override": source_assembly_id_override,
            "target_assembly_id_override": target_assembly_id_override,
            "s_to_b_homology_file_override": s_to_b_homology_file_override,
            "b_to_t_homology_file_override": b_to_t_homology_file_override,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

    def start_gff_query_task(self):
        if not self.current_config: self.show_error_message(_("错误"), _("请先加载配置文件。")); return
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("基因位点查询")

        assembly_id_override = self.selected_gff_query_assembly.get()
        gene_ids_text = self.gff_query_genes_entry.get("1.0", tk.END).strip()
        current_placeholder = _(self.placeholder_genes_gff_key)
        if gene_ids_text == current_placeholder or not gene_ids_text:
            gene_ids_list = None
        else:
            gene_ids_list = [line.strip() for line in gene_ids_text.splitlines() if line.strip()]

        region_str = self.gff_query_region_entry.get().strip()
        output_csv_path = self.gff_query_output_csv_entry.get().strip() or None
        region_tuple = None
        if region_str:
            try:
                parts = region_str.split(':')
                if len(parts) == 2 and '-' in parts[1]:
                    chrom = parts[0]
                    start_end = parts[1].split('-')
                    start = int(start_end[0])
                    end = int(start_end[1])
                    region_tuple = (chrom, start, end)
                else:
                    raise ValueError("Format error")
            except Exception:
                self.show_error_message(_("输入错误"), _("染色体区域格式不正确。请使用 'chr:start-end' 格式。"));
                self._update_button_states(False);
                return

        if not assembly_id_override or assembly_id_override == _("加载中..."):
            self.show_error_message(_("输入缺失"), _("请选择一个基因组版本ID。"));
            self._update_button_states(False);
            return
        if not gene_ids_list and not region_tuple:
            self.show_error_message(_("输入缺失"), _("必须提供基因ID列表或染色体区域进行查询。"));
            self._update_button_states(False);
            return

        self._log_to_viewer(f"{self.active_task_name} {_('任务开始...')}")
        # 使用 .grid() 而不是 .pack()
        self.progress_bar.grid(row=0, column=1, padx=10, pady=5, sticky="e")
        self.progress_bar.set(0)

        thread = threading.Thread(target=run_gff_gene_lookup_standalone, kwargs={
            "config": self.current_config, "assembly_id_override": assembly_id_override,
            "gene_ids_override": gene_ids_list, "region_override": region_tuple,
            "output_csv_path": output_csv_path, "status_callback": self.gui_status_callback,
            "progress_callback": self.gui_progress_callback,
            "task_done_callback": lambda success: self.task_done_callback(success, self.active_task_name)
        }, daemon=True)
        thread.start()

    # Helper for Browse files
    def _browse_file(self, entry_widget, filetypes_list):
        filepath = filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list)  #
        if filepath and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filepath)

    def _browse_save_file(self, entry_widget, filetypes_list):  #
        filepath = filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list,
                                                defaultextension=filetypes_list[0][1].replace("*", ""))  #
        if filepath and entry_widget:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filepath)

    # --- (其余所有方法，如日志、状态、配置加载/保存等，保持不变) ---
    def clear_log_viewer(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self._log_to_viewer(_("日志已清除。"))

    def _log_to_viewer(self, message, level="INFO"):
        # 将日志消息放入队列，由主线程处理
        self.log_queue.put((message, level))

    def show_info_message(self, title, message):
        self._log_to_viewer(f"{title}: {message}", level="INFO")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color=self.default_label_text_color)
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="info")

    def show_error_message(self, title, message):
        self._log_to_viewer(f"ERROR - {title}: {message}", level="ERROR")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="red")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="error")

    def show_warning_message(self, title, message):
        self._log_to_viewer(f"WARNING - {title}: {message}", level="WARNING")
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=f"{title}: {message[:150]}", text_color="orange")
        self._show_custom_dialog(title, message, buttons=[_("确定")], icon_type="warning")

    def gui_status_callback(self, message: str):
        """
        线程安全的回调函数，用于更新状态栏和日志。
        能识别 "[ERROR]" 前缀并触发错误处理流程。
        """
        # 检查消息是否标记为错误
        if message.strip().upper().startswith("[ERROR]"):
            # 尝试获取锁，如果成功，则发送错误消息
            if self.error_dialog_lock.acquire(blocking=False):
                # 从消息中移除 "[ERROR]" 标记
                clean_message = message.strip()[7:].strip()
                self.message_queue.put(("error", clean_message))
            # 如果获取锁失败，说明已有另一个错误正在处理，忽略此错误以避免弹窗轰炸
        else:
            self.message_queue.put(("status", message))

        # 无论如何，都将原始消息记录到日志
        self._log_to_viewer(str(message))

    def gui_progress_callback(self, percentage, message):
        self.message_queue.put(("progress", (percentage, message)))  #

    def task_done_callback(self, success=True, task_display_name="任务"):
        self.message_queue.put(("task_done", (success, task_display_name)))

    def _display_log_message_in_ui(self, message, level):
        """
        实际更新日志文本框的UI，只在主线程中调用。
        并限制日志行数以提高性能。
        """
        if self.log_textbox and self.log_textbox.winfo_exists():
            self.log_textbox.configure(state="normal")

            # --- 优化：限制日志行数 ---
            max_lines = 500  # 最大保留的日志行数
            current_lines = int(self.log_textbox.index('end-1c linestart').split('.')[0])
            if current_lines > max_lines:
                # 删除旧的日志行
                self.log_textbox.delete(f"1.0", f"{current_lines - max_lines + 1}.0")
            # --- 优化结束 ---

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            color_tag = "normal_log"
            if level == "ERROR":
                color_tag = "error_log"
            elif level == "WARNING":
                color_tag = "warning_log"

            self.log_textbox.insert(tk.END, f"[{timestamp}] {message}\n", color_tag)
            self.log_textbox.see(tk.END)  # 保持滚动到底部
            self.log_textbox.configure(state="disabled")

            # 首次配置标签颜色只做一次，避免重复调用
            if not hasattr(self.log_textbox, '_tags_configured'):
                self._update_log_tag_colors()
                self.log_textbox._tags_configured = True

    def check_queue_periodic(self):
        """定时检查消息队列，并更新UI。增加了错误处理逻辑。"""
        try:
            # 处理主消息队列
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()

                if message_type == "status":
                    self.status_label.configure(text=str(data)[:150])


                elif message_type == "initial_config_applied_to_ui_done":
                    self.startup_ui_tasks_completed["config_applied"] = True
                    self._check_and_hide_startup_dialog()

                elif message_type == "editor_ui_populated_done":
                    self.startup_ui_tasks_completed["editor_populated"] = True
                    self._check_and_hide_startup_dialog()

                elif message_type == "update_genome_dropdowns_async":  # This is the message from _load_initial_config -> update_genome_dropdowns_async
                    genome_sources_data = data
                    self.startup_ui_tasks_completed["genome_dropdowns_updated"] = True
                    self._update_assembly_id_dropdowns()  # Still call it to ensure values are set
                    self._check_and_hide_startup_dialog()


                elif message_type == "progress":
                    percentage, text = data
                    if not self.progress_bar.winfo_viewable():
                        self.progress_bar.grid()
                    self.progress_bar.set(percentage / 100.0)
                    self.status_label.configure(text=f"{str(text)[:100]} ({percentage}%)")

                # 处理模型列表获取成功
                elif message_type == "ai_models_fetched":
                    provider_key, models = data
                    self._log_to_viewer(f"{provider_key} {_('模型列表获取成功。')} ")
                    model_selector_widgets = self.editor_widgets.get(
                        f"ai_services.providers.{provider_key}.model")
                    if model_selector_widgets:
                        _model_selector_frame, entry, dropdown, dropdown_var, _refresh_button = model_selector_widgets
                        dropdown.configure(values=models)
                        if models:
                            dropdown.set(models[0])
                        dropdown.grid()
                        entry.grid_remove()
                        self.show_info_message(_("刷新成功"),
                                               f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')} ")

                # 处理模型列表获取失败
                elif message_type == "ai_models_failed":
                    provider_key, error_msg = data
                    self._log_to_viewer(f"{provider_key} {_('模型列表获取失败:')} {error_msg}", "ERROR")
                    model_selector_widgets = self.editor_widgets.get(
                        f"ai_services.providers.{provider_key}.model")
                    if model_selector_widgets:
                        _model_selector_frame, entry, dropdown, _dropdown_var, _refresh_button = model_selector_widgets
                        dropdown.grid_remove()
                        entry.grid()
                        self.show_warning_message(_("刷新失败"),
                                                  f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")

                # 处理隐藏进度弹窗的消息
                elif message_type == "hide_progress_dialog":
                    self._hide_progress_dialog()

                # 处理更新 Excel 工作表下拉菜单的消息
                elif message_type == "update_sheets_dropdown":
                    sheet_names, excel_path_for_error, error_msg = data
                    self._update_sheet_dropdowns_ui(sheet_names, excel_path_for_error, error_msg)

                # --- 新增的启动异步加载消息处理 ---
                elif message_type == "set_initial_config":
                    loaded_config_data, config_file_path = data
                    self._apply_config_to_ui_async(loaded_config_data, config_file_path)

                elif message_type == "update_genome_dropdowns_async":
                    genome_sources_data = data
                    # 这个函数在 _apply_config_to_ui_async 中调用，但这里也需要一个触发点，
                    # 确保在异步加载完成后更新。
                    # 确保 _update_assembly_id_dropdowns 内部能够处理 data (dict)
                    # 我们可以通过直接设置 self.current_config.downloader.genome_sources 来模拟
                    # 或者，更简单，直接将 data 传递给它，但 _update_assembly_id_dropdowns 当前是从 self.current_config 获取
                    # 因此，最好的做法是，在 initial_config_loaded 之后，由 _apply_config_to_ui_async 统一处理。
                    # 这里，我们只需要确保，当这些下拉菜单被懒加载时，它们会获取到正确的值。
                    # 实际的配置数据已经通过 set_initial_config 更新到了 self.current_config。
                    self._update_assembly_id_dropdowns()  # 再次触发更新，这次应该能找到控件了

                elif message_type == "populate_editor_ui_async":
                    # 异步触发配置编辑器的UI构建和更新
                    # 此时，如果编辑器UI未构建，它会被构建；如果已构建，则更新其值。
                    self._populate_editor_ui()

                # --- 错误处理逻辑 ---
                elif message_type == "error":
                    self.show_error_message(_("任务执行出错"), data)
                    self.progress_bar.grid_remove()
                    self.status_label.configure(text=f"{_('任务终止于')}: {data[:100]}",
                                                text_color=("#d9534f", "#e57373"))
                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked():
                        self.error_dialog_lock.release()

                elif message_type == "task_done":
                    success, task_display_name = data
                    self.progress_bar.grid_remove()
                    if not self.error_dialog_lock.locked():
                        final_message = _("{} 执行{}。").format(task_display_name, _("成功") if success else _("失败"))
                        self.status_label.configure(text=final_message,
                                                    text_color=("green" if success else ("#d9534f", "#e57373")))

                    self._update_button_states(is_task_running=False)
                    self.active_task_name = None
                    if self.error_dialog_lock.locked():
                        self.error_dialog_lock.release()

                # 处理手动加载配置文件任务完成的消息
                elif message_type == "config_load_task_done":
                    success, message = data
                    # success 和 message 包含加载结果，用于显示信息
                    if success:
                        self._hide_progress_dialog()  # 关闭对话框
                        # self.show_info_message(_("加载成功"), _("配置文件已成功加载并应用到界面。")) # 不再弹窗，直接在状态栏显示
                    else:
                        self._hide_progress_dialog()  # 关闭对话框
                        self.show_error_message(_("加载失败"), message)


            # 处理启动进度队列 (用于更新启动对话框)
            while not self.startup_progress_queue.empty():
                progress_percent, message = self.startup_progress_queue.get_nowait()
                if self.progress_dialog_text_var:
                    self.progress_dialog_text_var.set(message)
                if progress_percent == 100:
                    # 启动任务完成，隐藏对话框
                    self._hide_progress_dialog()

                    # 确保主页的 config_path_label 最终被更新
                    if self.initial_config_loaded.is_set():
                        # 在UI完全设置好后，再刷新语言，确保所有字符串都正确翻译
                        self.update_language_ui()
                        self._update_button_states()  # 确保按钮状态正确
                        self.status_label.configure(text=_(self.status_label_base_key),
                                                    text_color=self.default_label_text_color)


            # 处理日志队列
            while not self.log_queue.empty():
                message, level = self.log_queue.get_nowait()
                self._display_log_message_in_ui(message, level)

        except Exception as e:
            print(f"CRITICAL ERROR in check_queue_periodic: {e}")
            logging.critical(f"Unhandled exception in check_queue_periodic: {e}", exc_info=True)
            pass

        self.after(100, self.check_queue_periodic)

    def _check_and_hide_startup_dialog(self):
        """
        检查所有启动阶段的UI更新任务是否完成，如果完成则关闭启动对话框。
        """
        # 确保所有必需的UI任务都已完成
        all_tasks_done = all(self.startup_ui_tasks_completed.values())

        # 只有在后台异步加载已完成，并且所有UI更新任务都已完成时才关闭对话框
        if self.initial_config_loaded.is_set() and all_tasks_done:
            self._hide_progress_dialog()
            # 可以选择在这里显示最终的启动成功/失败信息，不再使用弹窗
            # self.show_info_message(_("启动成功"), _("应用程序已成功启动！"))
            # 或者仅更新状态栏
            self.status_label.configure(text=_(self.status_label_base_key), text_color=self.default_label_text_color)
            self.update_language_ui()  # 最终刷新语言和按钮状态
            self._update_button_states()


    def _bind_mouse_wheel_to_scrollable(self, widget):
        """
        为 CustomTkinter 的可滚动widget（如 CTkScrollableFrame, CTkTextbox）绑定鼠标滚轮事件。
        直接绑定到 CustomTkinter 控件，因为它会处理底层的 Tkinter 组件。
        注意：CustomTkinter 在内部已经为 CTkScrollableFrame 和 CTkTextbox 实现了基本的滚轮功能。
        这个方法主要用于确保自定义的或额外的滚轮绑定能够正常工作，
        或者在某些情况下增强默认行为（尽管通常不推荐修改CTk的内部实现）。

        对于 CTkScrollableFrame，它内部有一个 canvas，事件需要绑定到 canvas 上。
        对于 CTkTextbox，它有自己的内部 Text 控件，事件需要绑定到该 Text 控件上。
        """
        # 对于 CTkScrollableFrame
        if hasattr(widget, "_canvas") and isinstance(widget._canvas, ctk.CTkCanvas):
            canvas = widget._canvas
            canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                        add="+")
            canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkScrollableFrame canvas: {widget}", "DEBUG")

        # 对于 CTkTextbox
        elif hasattr(widget, "_textbox") and isinstance(widget._textbox, tk.Text):
            textbox = widget._textbox
            textbox.bind("<MouseWheel>", lambda event: textbox.yview_scroll(int(-1 * (event.delta / 120)), "units"),
                         add="+")
            textbox.bind("<Button-4>", lambda event: textbox.yview_scroll(-1, "units"), add="+")  # Linux scroll up
            textbox.bind("<Button-5>", lambda event: textbox.yview_scroll(1, "units"), add="+")  # Linux scroll down
            self._log_to_viewer(f"DEBUG: Bound mouse wheel to CTkTextbox internal Text: {widget}", "DEBUG")

        # 对于其他可能需要滚动的 CustomTkinter 控件（如 CTkFrame，如果里面放了其他可滚动内容）
        # 可以尝试直接绑定到控件本身，但效果可能不如直接绑定到内部 canvas/text
        else:
            widget.bind("<MouseWheel>",
                        lambda event: widget.yview_scroll(int(-1 * (event.delta / 120)), "units") if hasattr(widget,
                                                                                                             'yview_scroll') else None,
                        add="+")
            widget.bind("<Button-4>",
                        lambda event: widget.yview_scroll(-1, "units") if hasattr(widget, 'yview_scroll') else None,
                        add="+")
            widget.bind("<Button-5>",
                        lambda event: widget.yview_scroll(1, "units") if hasattr(widget, 'yview_scroll') else None,
                        add="+")
            self._log_to_viewer(f"DEBUG: Attempted generic mouse wheel bind to: {widget}", "DEBUG")


    def on_closing(self):
        if self._show_custom_dialog(_("退出"), _("您确定要退出吗?"), buttons=[_("确定"), _("取消")],
                                    icon_type="question") == _("确定"):
            self.destroy()

    def load_config_file(self, filepath: Optional[str] = None, is_initial_load: bool = False):
        """
        加载配置文件，并异步应用到UI。
        """
        if not filepath:
            filepath = filedialog.askopenfilename(title=_("选择配置文件"),
                                                  filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")))

        if filepath:
            self._log_to_viewer(f"{_('尝试加载配置文件:')} {filepath}")
            if not is_initial_load:  # Show progress dialog only for manual load
                self._show_progress_dialog(
                    title=_("加载配置中..."),
                    message=_("正在加载配置文件并应用到UI，请稍候..."),
                    on_cancel=None
                )

            def load_config_task_thread():
                try:
                    loaded_config_data = None
                    config_file_path = None

                    if os.path.exists(filepath):
                        loaded_config_data = load_config(os.path.abspath(filepath))
                        config_file_path = os.path.abspath(filepath)

                    # Send config data and path to main thread
                    self.message_queue.put(("set_initial_config_and_path", (loaded_config_data, config_file_path)))

                    # Trigger UI updates after config is set in main thread
                    self.message_queue.put(("trigger_populate_editor_ui", None))
                    self.message_queue.put(("trigger_apply_config_to_ui_values", None))
                    self.message_queue.put(("trigger_update_assembly_dropdowns", None))

                    # Send task completion message
                    self.message_queue.put(("config_load_task_done", (True, _("配置文件加载"))))
                except ValueError as e:
                    self.message_queue.put(("config_load_task_done", (False, f"{_('配置文件版本不兼容:')} {e}")))
                except Exception as e:
                    self.message_queue.put(("config_load_task_done", (False, f"{_('加载配置文件失败:')} {e}")))
                finally:
                    # 在任务完成时，主线程会处理 config_load_task_done 消息
                    pass  # Ensure it doesn't try to hide here

            threading.Thread(target=load_config_task_thread, daemon=True).start()
        else:
            if not is_initial_load:
                self._log_to_viewer(_("用户取消加载配置文件。"))


    def save_config_file(self, config_data: Optional[Dict] = None, show_dialog: bool = False) -> bool:
        """保存当前配置, 可选择是否弹出另存为对话框"""
        if config_data is None:
            config_data = self.current_config

        if not config_data:
            self.show_error_message(_("错误"), _("没有可保存的配置。"))
            return False

        save_path = self.config_path
        if show_dialog or not save_path:
            save_path = filedialog.asksaveasfilename(
                title=_("配置文件另存为"),
                filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
                defaultextension=".yml"
            )

        if save_path:
            try:
                if save_config_to_yaml(config_data, save_path):
                    self.config_path = save_path  # 更新当前配置路径
                    self.current_config = config_data
                    self._apply_config_to_ui()  # 重新应用，确保路径等显示正确
                    self.show_info_message(_("保存成功"), _("配置文件已保存至: {}").format(save_path))
                    return True
                else:
                    # save_config_to_yaml 内部会打印错误
                    self.show_error_message(_("保存失败"), _("保存配置文件时发生未知错误，请检查日志。"))
                    return False
            except Exception as e:
                self.show_error_message(_("保存失败"), f"{_('保存配置文件时发生错误:')} {e}")
                return False
        return False

    def on_config_updated(self, new_config_data: Dict):
        """当外部窗口(如编辑器)更新了配置后，由此方法通知主窗口"""
        self.current_config = new_config_data
        self._apply_config_to_ui()
        self._log_to_viewer(_("配置已从高级编辑器更新。"))

    def _generate_default_configs_gui(self):
        """
        【全新版本】处理“生成默认配置”按钮的点击事件。
        能够检测文件是否存在，并根据用户的选择执行覆盖或加载操作。
        """
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if not output_dir:
            self._log_to_viewer(_("用户取消了目录选择。"))
            return

        self._log_to_viewer(f"{_('用户选择的配置目录:')} {output_dir}")
        main_config_filename = "config.yml"  # 使用硬编码以确保检查的文件名正确
        main_config_path = os.path.join(output_dir, main_config_filename)

        should_overwrite = False
        # 检查配置文件是否已存在
        if os.path.exists(main_config_path):
            # 如果文件存在，弹窗询问用户
            user_choice = self._show_custom_dialog(
                title=_("文件已存在"),
                message=_("配置文件 '{}' 已存在于所选目录中。\n\n您想覆盖它吗？\n(选择“否”将直接加载现有文件)").format(
                    main_config_filename),
                buttons=[_("是 (覆盖)"), _("否 (加载)")],
                icon_type="question"
            )

            if user_choice == _("是 (覆盖)"):
                should_overwrite = True
            elif user_choice == _("否 (加载)"):
                # 用户选择不覆盖，则直接加载现有文件
                self.load_config_file(filepath=main_config_path)
                return  # 结束流程
            else:
                # 用户关闭了对话框
                self._log_to_viewer(_("用户取消了覆盖操作。"))
                return

        # 如果文件不存在，或者用户同意覆盖，则执行生成
        try:
            self._log_to_viewer(_("正在生成默认配置文件..."))
            success, new_main_cfg_path, new_gs_cfg_path = generate_default_config_files(
                output_dir,
                overwrite=should_overwrite,
                main_config_filename=main_config_filename
            )
            if success:
                msg = f"{_('默认配置文件已成功生成到:')}\n{new_main_cfg_path}\n{new_gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"
                if self._show_custom_dialog(_("生成成功"), msg, [_("是"), _("否")], "info") == _("是"):
                    self.load_config_file(filepath=new_main_cfg_path)
            else:
                # generate_default_config_files 内部应该已经打印了日志
                self.show_error_message(_("生成失败"), _("生成默认配置文件失败，请检查日志获取详细信息。"))
        except Exception as e:
            self.show_error_message(_("生成错误"), f"{_('生成默认配置文件时发生未知错误:')} {e}")


    def _save_genome_sources_config(self):  #
        if not self.current_config: self.show_error_message(_("错误"), _("没有加载主配置文件。")); return  #
        gs_file_rel = self.current_config.get("downloader", {}).get("genome_sources_file")  #
        if not gs_file_rel: self.show_warning_message(_("无法保存"),
                                                      _("主配置文件中未指定基因组源文件路径。")); return  #
        abs_path = os.path.join(os.path.dirname(self.config_path), gs_file_rel) if not os.path.isabs(
            gs_file_rel) and self.config_path else gs_file_rel  #
        content_to_save = self.editor_gs_raw_yaml.get("1.0", tk.END).strip()  #
        try:
            parsed_yaml = yaml.safe_load(content_to_save)  #
            if not isinstance(parsed_yaml, dict): self.show_error_message(_("保存错误"),
                                                                          _("基因组源内容的YAML格式不正确。")); return  #
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content_to_save)  #
            self._log_to_viewer(f"{_('基因组源文件已保存到:')} {abs_path}");
            self.show_info_message(_("保存成功"), _("基因组源文件已成功保存。"))  #
        except yaml.YAMLError as e:
            self.show_error_message(_("保存错误"), f"{_('基因组源YAML解析错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('基因组源YAML解析错误:')} {e}", level="ERROR")  #
        except Exception as e:
            self.show_error_message(_("保存错误"), f"{_('保存基因组源文件时发生错误:')} {e}");
            self._log_to_viewer(
                f"ERROR: {_('保存基因组源文件时发生错误:')} {e}", level="ERROR")  #

    def _update_button_states(self, is_task_running=False):
        action_state = "disabled" if is_task_running else "normal"
        task_button_state = "normal" if self.current_config and not is_task_running else "disabled"

        # 所有任务按钮
        if hasattr(self, 'download_start_button') and self.download_start_button.winfo_exists():
            self.download_start_button.configure(state=task_button_state)
        if hasattr(self, 'integrate_start_button') and self.integrate_start_button.winfo_exists():
            self.integrate_start_button.configure(state=task_button_state)
        if hasattr(self, 'homology_map_start_button') and self.homology_map_start_button.winfo_exists():
            self.homology_map_start_button.configure(state=task_button_state)
        if hasattr(self, 'gff_query_start_button') and self.gff_query_start_button.winfo_exists():
            self.gff_query_start_button.configure(state=task_button_state)
        if hasattr(self, 'anno_start_button') and self.anno_start_button.winfo_exists(): # For annotation tab
            self.anno_start_button.configure(state=task_button_state)
        if hasattr(self, 'ai_start_button') and self.ai_start_button.winfo_exists(): # For AI assistant tab
            self.ai_start_button.configure(state=task_button_state)
        if hasattr(self, 'convert_start_button') and self.convert_start_button.winfo_exists(): # For XLSX to CSV tab
            self.convert_start_button.configure(state=task_button_state)

        # 侧边栏和配置按钮
        if hasattr(self, 'navigation_frame'): # 确保导航框架已经创建
            # 遍历这些按钮，并检查它们是否存在
            for btn_name in ['home_button', 'editor_button', 'integrate_button', 'tools_button',
                             'load_config_button', 'gen_config_button']: #
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    if btn.winfo_exists(): # 确保控件在Tkinter中仍存在
                        btn.configure(state=action_state)

    def start_download_task(self):
        if not self.current_config:
            self.show_error_message(_("错误"), _("请先加载配置文件。"))
            return

        # 禁用所有操作按钮，表明任务正在进行
        self._update_button_states(is_task_running=True)
        self.active_task_name = _("数据下载")

        # 将后台任务的执行逻辑包裹在一个函数中
        def task_wrapper():
            success = False
            try:
                # 1. 从UI复选框中收集需要下载的基因组ID列表
                versions_to_download = [gid for gid, var in self.download_genome_vars.items() if var.get()]
                # 如果用户没有勾选任何项，则列表为空，后台会理解为下载所有
                if not versions_to_download:
                    versions_to_download = None

                # 2. 根据UI开关状态决定是否使用代理
                proxies_to_use = None
                if self.download_proxy_var.get():
                    # 仅当开关打开时，才从配置中读取代理地址
                    proxies_to_use = self.current_config.downloader.proxies
                    if not proxies_to_use or not (proxies_to_use.http or proxies_to_use.https):
                        # 如果代理地址未配置，则通过消息队列报错并终止任务
                        self.gui_status_callback(f"[ERROR] {_('您开启了代理开关，但配置文件中未找到有效的代理地址。')}")
                        return  # 提前终止线程

                # 3. 准备传递给后台的配置
                # 使用 deepcopy 创建一个临时配置副本，避免修改内存中的原始配置对象
                import copy
                temp_config_obj = copy.deepcopy(self.current_config)
                temp_config_obj.downloader.proxies = proxies_to_use  # 覆盖代理设置

                force_download_override = self.download_force_checkbox_var.get()

                # 4. 更新UI状态，准备开始任务
                self.gui_status_callback(
                    f"{self.active_task_name} {_('任务开始...')} ({_('代理')}: {'ON' if proxies_to_use else 'OFF'})")
                self.gui_progress_callback(0, _("正在准备下载..."))  # 使用 progress 回调来更新状态

                # 5. 调用后台下载函数
                success = download_genome_data(
                    config=temp_config_obj,
                    genome_versions_to_download_override=versions_to_download,
                    force_download_override=force_download_override,
                    status_callback=self.gui_status_callback,
                    progress_callback=self.gui_progress_callback
                )
            except Exception as e:
                # 捕获任何意外的严重错误
                self.gui_status_callback(f"[ERROR] {_('一个意外的严重错误发生')}: {e}")
                success = False
            finally:
                # 无论成功或失败，都确保调用任务结束回调
                self.task_done_callback(success, self.active_task_name)

        # 启动包含以上全部逻辑的后台线程
        threading.Thread(target=task_wrapper, daemon=True).start()


if __name__ == "__main__":  #
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    app = CottonToolkitApp()  #
    app.mainloop()  #
