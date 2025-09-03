# cotton_toolkit/config/loader.py

import os
import re

import yaml
import logging
from typing import Any, Dict, Optional, Tuple, List
from urllib.parse import urlparse

from pydantic import ValidationError

# 确保从 models.py 正确导入 MainConfig 和 GenomeSourcesConfig, GenomeSourceItem
from cotton_toolkit.config.models import MainConfig, GenomeSourcesConfig, GenomeSourceItem

# --- 模块级缓存变量 ---
_GENOME_SOURCES_CACHE: Optional[Dict[str, GenomeSourceItem]] = None
_LAST_CACHED_GS_FILE_PATH: Optional[str] = None


# --- 国际化和日志设置 ---
try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.loader")

# --- 获取本地已下载文件的预期路径 ---
def get_local_downloaded_file_path(config: MainConfig, genome_info: GenomeSourceItem, file_key: str) -> Optional[str]:
    """
    获取某个基因组的特定类型文件的本地期望路径。
    此版本会正确地包含基因组版本的子目录。
    """
    if not hasattr(genome_info, f"{file_key}_url"):
        return None

    url = getattr(genome_info, f"{file_key}_url")
    if not url:
        return None

    filename = os.path.basename(url)
    base_dir = config.downloader.download_output_base_dir

    version_identifier = getattr(genome_info, 'version_id', None)
    if not version_identifier:
        version_identifier = re.sub(r'[\\/*?:"<>|]', "_", genome_info.species_name).replace(" ", "_") if genome_info.species_name else "unknown_genome"

    version_specific_dir = os.path.join(base_dir, version_identifier)

    return os.path.join(version_specific_dir, filename)


def save_config(config: MainConfig, path: str) -> bool:
    """将配置对象保存到YAML文件。"""
    try:
        config_dict = config.model_dump(exclude={'config_file_abs_path_'}, exclude_none=True, exclude_defaults=False)

        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, allow_unicode=True, sort_keys=False, indent=2)
        logger.info(_("配置文件已成功保存到: {}").format(path))
        return True
    except Exception as e:
        logger.error(_("保存配置文件到 '{}' 时发生错误: {}").format(path, e))
        return False


def load_config(path: str) -> MainConfig:
    """从指定路径加载主配置文件并进行验证。"""
    abs_path = os.path.abspath(path)
    info = _("正在从 '{}' 加载主配置文件...")
    logger.info(info.format(abs_path))
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        config_obj = MainConfig.model_validate(data)

        setattr(config_obj, 'config_file_abs_path_', abs_path)

        logger.info(_("主配置文件加载并验证成功。"))
        return config_obj
    except FileNotFoundError:
        logger.error(_("配置文件未找到: {}").format(abs_path))
        raise
    except yaml.YAMLError as e:
        logger.error(_("解析YAML文件时发生错误 '{}': {}").format(abs_path, e))
        raise
    except ValidationError as e:
        logger.error(_("配置文件验证失败 '{}':\n{}").format(abs_path, e))
        raise
    except Exception as e:
        logger.error(_("加载配置文件时发生未知错误 '{}': {}").format(abs_path, e))
        raise


def get_genome_data_sources(config: MainConfig) -> Dict[str, GenomeSourceItem]:
    """
    从主配置中获取基因组来源列表文件的路径，加载并解析该文件。
    增加了缓存机制以提高性能。
    """
    global _GENOME_SOURCES_CACHE, _LAST_CACHED_GS_FILE_PATH

    # 1. 检查传入的config对象是否有效，以及是否包含定位其他文件所需的绝对路径
    if not config or not getattr(config, 'config_file_abs_path_', None):
        logger.error(_("主配置对象无效或缺少必需的路径信息 'config_file_abs_path_'。"))
        return {}

    # 2. 从 downloader 配置中获取文件名，并构建其绝对路径
    sources_filename = config.downloader.genome_sources_file
    config_dir = os.path.dirname(config.config_file_abs_path_)
    sources_filepath = os.path.join(config_dir, sources_filename)

    # 3. 使用缓存（如果文件路径未变且缓存存在）
    if _LAST_CACHED_GS_FILE_PATH == sources_filepath and _GENOME_SOURCES_CACHE is not None:
        logger.debug(_("从缓存加载基因组源数据。"))
        return _GENOME_SOURCES_CACHE

    # 4. 检查文件是否存在
    if not os.path.exists(sources_filepath):
        logger.error(_("基因组来源文件未找到: {}").format(sources_filepath))
        # 清空缓存
        _GENOME_SOURCES_CACHE = None
        _LAST_CACHED_GS_FILE_PATH = None
        return {}

    # 5. 加载、解析和验证YAML文件
    try:
        logger.info(_("正在从 '{}' 加载基因组源...").format(sources_filepath))
        with open(sources_filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 使用正确的模型 GenomeSourcesConfig 来验证整个文件
        genome_sources_config = GenomeSourcesConfig.model_validate(data)

        # 提取核心的字典数据
        genome_sources_map = genome_sources_config.genome_sources

        # 关键步骤：用字典的key填充每个item中可能缺失的 version_id
        for version_id, item in genome_sources_map.items():
            if item.version_id is None:
                item.version_id = version_id

        logger.info(_("已成功加载 {} 个基因组源。").format(len(genome_sources_map)))

        # 更新缓存
        _GENOME_SOURCES_CACHE = genome_sources_map
        _LAST_CACHED_GS_FILE_PATH = sources_filepath

        return genome_sources_map

    except (yaml.YAMLError, ValidationError) as e:
        logger.error(_("解析或验证基因组来源文件 '{}' 失败: {}").format(sources_filepath, e))
    except Exception as e:
        logger.error(_("加载基因组来源文件 '{}' 时发生未知错误: {}").format(sources_filepath, e))

    # 如果发生任何错误，清空缓存并返回空字典
    _GENOME_SOURCES_CACHE = None
    _LAST_CACHED_GS_FILE_PATH = None
    return {}


def generate_default_config_files(output_dir: str, overwrite: bool = False, main_config_filename="config.yml",
                                  sources_filename="genome_sources_list.yml") -> Tuple[
    bool, Optional[str], Optional[str], List[str]]:
    """
    生成默认的配置文件和基因组源列表文件。
    返回: (成功状态, 主配置文件路径, 源文件路径, 已存在且未被覆盖的文件列表)
    """
    existing_files = [] # 3. 用于存储已存在的文件名
    try:
        os.makedirs(output_dir, exist_ok=True)
        main_config_path = os.path.join(output_dir, main_config_filename)
        sources_path = os.path.join(output_dir, sources_filename)

        # 分别检查每个文件是否存在
        if os.path.exists(main_config_path):
            existing_files.append(main_config_filename)
        if os.path.exists(sources_path):
            existing_files.append(sources_filename)

        # 如果文件存在且不允许覆盖，则记录日志并返回
        if not overwrite and existing_files:
            logger.warning(_("一个或多个默认配置文件已存在且不允许覆盖: {}").format(", ".join(existing_files)))
            return False, None, None, existing_files

        default_config = MainConfig()
        default_config.downloader.genome_sources_file = sources_filename
        save_config(default_config, main_config_path)

        default_sources_data = GenomeSourcesConfig()

        with open(sources_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_sources_data.model_dump(exclude_none=True), f, allow_unicode=True, sort_keys=False,
                      indent=2)
        return True, main_config_path, sources_path, []

    except Exception as e:
        logger.error(_("生成默认配置文件时发生错误: {}").format(e), exc_info=True)
        return False, None, None, []


def check_annotation_file_status(config: MainConfig, genome_info: GenomeSourceItem, file_type: str) -> str:
    local_path = get_local_downloaded_file_path(config, genome_info, file_type)

    if not local_path:
        return "not_applicable"

    if os.path.exists(local_path):
        if os.path.getsize(local_path) > 0:
            return 'complete'
        else:
            return 'incomplete'
    else:
        return 'missing'