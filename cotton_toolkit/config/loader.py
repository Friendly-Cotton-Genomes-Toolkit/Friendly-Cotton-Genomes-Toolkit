# cotton_toolkit/config/loader.py

import os
import yaml
import logging  # Ensure logging is imported
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
# 确保从 models.py 正确导入 MainConfig 和 GenomeSourcesConfig, GenomeSourceItem
from cotton_toolkit.config.models import MainConfig, GenomeSourcesConfig, GenomeSourceItem  # ADD GenomeSourceItem

# --- 模块级缓存变量 ---
_GENOME_SOURCES_CACHE: Optional[Dict[str, GenomeSourceItem]] = None  # 缓存的类型改为 Dict[str, GenomeSourceItem]
_LAST_CACHED_GS_FILE_PATH: Optional[str] = None


# --- 新增辅助函数：获取本地已下载文件的预期路径 ---
def get_local_downloaded_file_path(
        main_config: MainConfig,
        genome_info: GenomeSourceItem,
        file_type: str  # 'gff3' 或 'homology_ath'
) -> Optional[str]:
    """
    根据主配置和基因组信息，确定本地已下载文件的预期绝对路径。
    此路径应与主下载器保存文件的路径一致。

    Args:
        main_config: 应用程序的主配置对象。
        genome_info: 特定基因组的 GenomeSourceItem 对象。
        file_type: 字符串，'gff3' 表示 GFF 文件，'homology_ath' 表示同源文件。

    Returns:
        如果能确定路径，返回文件的绝对路径；否则返回 None。
    """
    downloader_cfg = main_config.downloader
    if not downloader_cfg or not downloader_cfg.download_output_base_dir:
        return None

    # 确定绝对路径的下载基础目录
    # 优先使用配置中的绝对路径，否则与配置文件所在目录拼接，否则使用当前工作目录
    base_download_dir = downloader_cfg.download_output_base_dir
    config_abs_path = main_config._config_file_abs_path_

    if not os.path.isabs(base_download_dir):
        if config_abs_path and os.path.dirname(config_abs_path):
            base_download_dir = os.path.join(os.path.dirname(config_abs_path), base_download_dir)
        else:
            base_download_dir = os.path.join(os.getcwd(), base_download_dir)

    base_download_dir = os.path.abspath(base_download_dir)

    # 构建物种特定的子目录
    safe_dir_name = genome_info.species_name.replace(" ", "_").replace(".", "_").replace("(", "").replace(")",
                                                                                                          "").replace(
        "'", "")
    version_output_dir = os.path.join(base_download_dir, safe_dir_name)

    url = None
    default_name_pattern = None

    if file_type == 'gff3':
        url = genome_info.gff3_url
        default_name_pattern = f"{safe_dir_name}_annotations.gff3.gz"  # 与 downloader.py 中的命名保持一致
    elif file_type == 'homology_ath':
        url = genome_info.homology_ath_url
        default_name_pattern = f"{safe_dir_name}_homology_ath.xlsx.gz"  # 与 downloader.py 中的命名保持一致
    else:
        return None  # 不支持的文件类型

    if not url:
        return None  # 未定义 URL

    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path) if parsed_url.path and '.' in os.path.basename(
        parsed_url.path) else default_name_pattern

    # 如果文件是压缩的 Excel 文件 (例如 .xlsx.gz)，实际使用的可能是转换后的 .csv 版本
    # 所以也需要检查 .csv 版本是否存在，并优先返回它
    if filename.lower().endswith((".xlsx.gz", ".xls.gz")):
        base_name_no_gz_ext = os.path.splitext(filename)[0]  # 例如：xxx.xlsx
        csv_filename = os.path.splitext(base_name_no_gz_ext)[0] + ".csv"  # 例如：xxx.csv
        local_csv_path = os.path.join(version_output_dir, csv_filename)
        # 如果对应的CSV文件已存在，则认为该数据已就绪，返回CSV路径
        if os.path.exists(local_csv_path):
            return local_csv_path

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


def get_genome_data_sources(main_config: MainConfig, logger: Optional[callable] = None) -> Optional[
    Dict[str, GenomeSourceItem]]:
    """
    【修改后】从主配置对象中获取或加载基因组数据源。
    引入缓存机制，并确保将数据转换为 GenomeSourceItem dataclass 实例。
    """
    global _GENOME_SOURCES_CACHE, _LAST_CACHED_GS_FILE_PATH

    # 统一日志输出接口
    log = logger if logger else print

    # 确保 logger 是一个正确的 logging.Logger 实例或可调用对象
    _log_func = log.info if isinstance(log, logging.Logger) else log
    _log_error = log.error if isinstance(log, logging.Logger) else (
        lambda msg, **kwargs: log(f"ERROR: {msg}", **kwargs))
    _log_warning = log.warning if isinstance(log, logging.Logger) else (
        lambda msg, **kwargs: log(f"WARNING: {msg}", **kwargs))

    _log_func(_("获取基因组源数据..."))

    if not main_config:
        _log_error(_("错误: 传入的主配置对象(main_config)为空。"))
        return None

    downloader_cfg = main_config.downloader
    if not downloader_cfg:
        _log_error(_("错误: 配置对象不完整，缺少 'downloader' 部分。"))
        return None

    gs_file_rel = downloader_cfg.genome_sources_file
    if not gs_file_rel:
        _log_error(_("错误: 主配置的 'downloader' 部分缺少 'genome_sources_file' 定义。"))
        return None

    main_config_dir = os.path.dirname(main_config._config_file_abs_path_) if hasattr(main_config,
                                                                                     '_config_file_abs_path_') and main_config._config_file_abs_path_ else os.getcwd()
    gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

    # --- 缓存检查 ---
    if _GENOME_SOURCES_CACHE is not None and _LAST_CACHED_GS_FILE_PATH == gs_file_path_abs:
        _log_func(f"INFO: {_('从缓存加载基因组源数据 (文件:')} '{gs_file_path_abs}')。")
        return _GENOME_SOURCES_CACHE
    # --- 缓存检查结束 ---

    if not os.path.exists(gs_file_path_abs):
        _log_error(_("错误: 基因组源文件 '{gs_file_path_abs}' 不存在。"))
        return None

    try:
        _log_func(f"INFO: {_('从文件加载基因组源数据 (文件:')} '{gs_file_path_abs}')...")
        with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if data.get('list_version') != 1:
            _log_error(_("错误: 基因组源文件 '{gs_file_path_abs}' 的版本不兼容。当前程序仅支持版本 1。"))
            return None

        genome_sources_raw_dict = data.get('genome_sources', {})
        if not isinstance(genome_sources_raw_dict, dict):
            _log_error(_("错误: 基因组源文件 '{gs_file_path_abs}' 中的 'genome_sources' 必须是一个字典。"))
            return None

        # --- 核心修改：将字典转换为 GenomeSourceItem 实例 ---
        converted_genome_sources: Dict[str, GenomeSourceItem] = {}
        for genome_id, genome_data in genome_sources_raw_dict.items():
            if isinstance(genome_data, dict):
                try:
                    converted_genome_sources[genome_id] = GenomeSourceItem.from_dict(genome_data)
                except Exception as e_convert:
                    _log_error(_("错误: 转换基因组 '{}' 的数据时失败：{}").format(genome_id, e_convert))
                    return None  # 转换失败，终止并返回 None
            else:
                _log_error(_("错误: 基因组 '{}' 的数据格式不正确，应为字典。").format(genome_id))
                return None  # 格式不正确，终止并返回 None
        # --- 核心修改结束 ---

        _log_func(_("成功从 '{}' 加载了 {} 个基因组源。").format(gs_file_path_abs, len(converted_genome_sources)))

        # --- 更新缓存 ---
        _GENOME_SOURCES_CACHE = converted_genome_sources  # 缓存转换后的对象
        _LAST_CACHED_GS_FILE_PATH = gs_file_path_abs
        # --- 更新缓存结束 ---

        return converted_genome_sources
    except Exception as e:
        import traceback  # 确保 traceback 已导入
        _log_error(_("错误: 加载或解析基因组源文件 '{gs_file_path_abs}' 失败: {e}\n--- TRACEBACK ---\n{}").format(
            traceback.format_exc()))  # 打印完整堆栈
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