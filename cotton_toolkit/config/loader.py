# cotton_toolkit/config/loader.py

import os
import re

import yaml
import logging  # Ensure logging is imported
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
# 确保从 models.py 正确导入 MainConfig 和 GenomeSourcesConfig, GenomeSourceItem
from cotton_toolkit.config.models import MainConfig, GenomeSourcesConfig, GenomeSourceItem  # ADD GenomeSourceItem

# --- 模块级缓存变量 ---
_GENOME_SOURCES_CACHE: Optional[Dict[str, GenomeSourceItem]] = None  # 缓存的类型改为 Dict[str, GenomeSourceItem]
_LAST_CACHED_GS_FILE_PATH: Optional[str] = None


# --- 国际化和日志设置 ---
# 假设 _ 函数已由主应用程序入口设置到 builtins
# 为了让静态检查工具识别 _，可以这样做：
try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):  # builtins._ 未设置或导入builtins失败
    # 如果在测试或独立运行此模块时，_ 可能未设置
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.loader")

# --- 新增辅助函数：获取本地已下载文件的预期路径 ---
def get_local_downloaded_file_path(
        main_config: MainConfig,
        genome_info: GenomeSourceItem,
        file_type: str
) -> Optional[str]:
    """
    【全功能修正版】根据主配置和基因组信息，确定本地已下载文件的预期绝对路径。
    """
    downloader_cfg = main_config.downloader
    if not downloader_cfg or not downloader_cfg.download_output_base_dir:
        return None

    # --- 路径构建逻辑 (保持不变) ---
    base_download_dir = downloader_cfg.download_output_base_dir
    config_abs_path = main_config._config_file_abs_path_
    if not os.path.isabs(base_download_dir):
        if config_abs_path and os.path.dirname(config_abs_path):
            base_download_dir = os.path.join(os.path.dirname(config_abs_path), base_download_dir)
        else:
            base_download_dir = os.path.join(os.getcwd(), base_download_dir)
    base_download_dir = os.path.abspath(base_download_dir)
    safe_dir_name = re.sub(r'[\\/*?:"<>|]', "_", genome_info.species_name).replace(" ", "_")
    version_output_dir = os.path.join(base_download_dir, safe_dir_name)

    # --- 【核心修正点】补全所有文件类型的映射 ---
    url_map = {
        'gff3': (genome_info.gff3_url, f"{safe_dir_name}_annotations.gff3.gz"),
        'homology_ath': (genome_info.homology_ath_url, f"{safe_dir_name}_homology_ath.xlsx.gz"),
        'GO': (genome_info.GO_url, f"{safe_dir_name}_genes2Go.txt.gz"),
        'IPR': (genome_info.IPR_url, f"{safe_dir_name}_genes2IPR.txt.gz"),
        'KEGG_pathways': (genome_info.KEGG_pathways_url, f"{safe_dir_name}_KEGG-pathways.txt.gz"),
        'KEGG_orthologs': (genome_info.KEGG_orthologs_url, f"{safe_dir_name}_KEGG-orthologs.txt.gz"),
    }

    if file_type not in url_map:
        # 如果请求的类型不在地图中，返回None
        return None

    url, default_name_pattern = url_map[file_type]

    if not url:
        return None

    # 从URL确定标准文件名
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path) if parsed_url.path and '.' in os.path.basename(
        parsed_url.path) else default_name_pattern

    # --- 【逻辑修正】只对同源文件优先查找CSV ---
    # 对于 homology_ath 类型的 .xlsx.gz 文件，优先返回已转换的 .csv 文件
    if file_type == 'homology_ath' and filename.lower().endswith((".xlsx.gz", ".xls.gz")):
        base_name_no_gz_ext = os.path.splitext(filename)[0]
        csv_filename = os.path.splitext(base_name_no_gz_ext)[0] + ".csv"
        local_csv_path = os.path.join(version_output_dir, csv_filename)
        if os.path.exists(local_csv_path):
            return local_csv_path  # 如果CSV存在，优先返回它

    # 对于所有其他文件，或同源文件的CSV不存在时，返回原始下载文件的路径
    local_path = os.path.join(version_output_dir, filename)
    return local_path


def save_config(config_obj: Any, file_path: str) -> bool:
    """
    将配置对象（MainConfig 或 GenomeSourcesConfig 实例）保存为 YAML 文件。
    它依赖于 config_obj 实现了 to_dict() 方法。
    """
    try:
        # 确保 config_obj 是一个 dataclass 实例，并且实现了 to_dict() 方法
        # 如果不是，asdict(config_obj) 也能工作，但 to_dict 提供了更好的控制
        if hasattr(config_obj, 'to_dict') and callable(config_obj.to_dict):
            config_dict = config_obj.to_dict()
        else:
            # Fallback for generic dataclasses or if to_dict is not explicitly implemented
            from dataclasses import asdict
            config_dict = asdict(config_obj)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)  # 确保输出目录存在

        with open(file_path, 'w', encoding='utf-8') as f:
            # indent=2 让 YAML 文件更易读，default_flow_style=False 避免所有内容都在一行
            # sort_keys=False 保持字典键的原始顺序（Python 3.7+ 字典保持插入顺序）
            yaml.dump(config_dict, f, indent=2, default_flow_style=False, sort_keys=False)
        print(f"INFO: 配置文件已保存到 '{file_path}'")
        return True
    except Exception as e:
        print(f"ERROR: 无法保存配置文件 '{file_path}': {e}")
        return False


def load_config(config_path: str) -> Optional[MainConfig]:
    """
    从 YAML 文件加载配置，并将其转换为 MainConfig 对象。
    """
    if not os.path.exists(config_path):
        print(f"ERROR: 配置文件 '{config_path}' 未找到。")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            print(f"ERROR: 配置文件 '{config_path}' 的顶层结构必须是一个字典。")
            return None

        # 检查 config_version
        if data.get('config_version') != 1:
            print(f"ERROR: 配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")
            # 通常这里会抛出异常或返回 None，让调用者处理
            raise ValueError(f"配置文件 '{config_path}' 的版本不兼容。当前程序仅支持版本 1。")

        # 将字典转换为 MainConfig 对象
        config_obj = MainConfig.from_dict(data)

        # 存储配置文件的绝对路径，以便后续相对路径处理（如 genome_sources_file）
        config_obj._config_file_abs_path_ = os.path.abspath(config_path)

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


def get_genome_data_sources(main_config: MainConfig, logger_func: Optional[callable] = None) -> Optional[
    Dict[str, GenomeSourceItem]]:
    """
     从主配置对象中获取或加载基因组数据源，并硬编码注入桥梁物种的配置。
    """
    global _GENOME_SOURCES_CACHE, _LAST_CACHED_GS_FILE_PATH

    log = logger_func if logger_func else logger.info

    if not main_config or not main_config.downloader:
        logger.error(_("错误: 主配置对象(main_config)或其downloader部分为空。"))
        return None

    gs_file_rel = main_config.downloader.genome_sources_file
    main_config_dir = os.path.dirname(main_config._config_file_abs_path_) if hasattr(main_config,
                                                                                     '_config_file_abs_path_') and main_config._config_file_abs_path_ else os.getcwd()
    gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

    if _GENOME_SOURCES_CACHE is not None and _LAST_CACHED_GS_FILE_PATH == gs_file_path_abs:
        log(f"INFO: {_('从缓存加载基因组源数据。')}")
        return _GENOME_SOURCES_CACHE

    if not os.path.exists(gs_file_path_abs):
        logger.error(_("错误: 基因组源文件 '{}' 不存在。").format(gs_file_path_abs))
        return None

    try:
        log(f"INFO: {_('从文件加载基因组源数据: {}').format(gs_file_path_abs)}")
        with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        genome_sources_config = GenomeSourcesConfig.from_dict(data)
        converted_genome_sources = genome_sources_config.genome_sources


        log(_("成功加载并处理了 {} 个基因组源。").format(len(converted_genome_sources)))

        _GENOME_SOURCES_CACHE = converted_genome_sources
        _LAST_CACHED_GS_FILE_PATH = gs_file_path_abs

        return converted_genome_sources
    except Exception as e:
        logger.error(_("错误: 加载或解析基因组源文件 '{}' 失败: {}").format(gs_file_path_abs, e))
        logger.exception("完整错误堆栈:")
        return None



def generate_default_config_files(
        output_dir: str,
        main_config_filename: str = "config.yml",
        genome_sources_filename: str = "genome_sources_list.yml",
        overwrite: bool = False
) -> Tuple[bool, str, str]:
    """
    通过实例化配置类来生成默认的配置文件（config.yml 和 genome_sources_list.yml），
    并支持覆盖选项。
    """
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            print(f"INFO: 创建目录 '{output_dir}' 成功。")
        except OSError as e:
            print(f"ERROR: 创建目录 '{output_dir}' 失败: {e}")
            return False, "", ""

    main_config_path = os.path.join(output_dir, main_config_filename)
    genome_sources_path = os.path.join(output_dir, genome_sources_filename)

    success_main = False
    success_gs = False

    # 生成主配置文件 (config.yml)
    if os.path.exists(main_config_path) and not overwrite:
        print(f"WARNING: 主配置文件 '{main_config_path}' 已存在，跳过生成。")
        success_main = True
    else:
        # 关键：实例化 MainConfig。这会自动带入 models.py 中定义的所有默认值。
        try:
            main_conf_default = MainConfig()
            # 确保 downloader.genome_sources_file 的默认值指向正确的文件名
            main_conf_default.downloader.genome_sources_file = genome_sources_filename
            success_main = save_config(main_conf_default, main_config_path)
            if success_main:
                print(f"INFO: 默认主配置文件已生成到 '{main_config_path}'。")
        except Exception as e:
            print(f"ERROR: 生成默认主配置文件失败: {e}")
            success_main = False

    # 生成基因组源文件 (genome_sources_list.yml)
    if os.path.exists(genome_sources_path) and not overwrite:
        print(f"WARNING: 基因组源文件 '{genome_sources_path}' 已存在，跳过生成。")
        success_gs = True
    else:
        # 关键：实例化 GenomeSourcesConfig。这会自动带入 models.py 中定义的所有默认值。
        try:
            gs_conf_default = GenomeSourcesConfig()
            success_gs = save_config(gs_conf_default, genome_sources_path)
            if success_gs:
                print(f"INFO: 默认基因组源文件已生成到 '{genome_sources_path}'。")
        except Exception as e:
            print(f"ERROR: 生成默认基因组源文件失败: {e}")
            success_gs = False

    return success_main and success_gs, main_config_path, genome_sources_path


def check_annotation_file_status(config: 'MainConfig', genome_info: 'GenomeSourceItem', file_key: str) -> str:
    """
    检查单个注释文件的状态。

    Args:
        config: 主配置对象。
        genome_info: 基因组信息对象。
        file_key (str): 文件类型关键字 (例如 'GO', 'IPR')。

    Returns:
        str: 'processed', 'not_processed', 或 'not_downloaded'
    """
    original_path = get_local_downloaded_file_path(config, genome_info, file_key)
    if not original_path:
        return 'not_downloaded' # URL不存在，视为未配置

    # 更可靠地推断CSV路径
    base_path = original_path.replace('.xlsx.gz', '').replace('.xlsx', '')
    processed_csv_path = base_path + '.csv'

    if os.path.exists(processed_csv_path):
        return 'processed'
    elif os.path.exists(original_path):
        return 'not_processed'
    else:
        return 'not_downloaded'