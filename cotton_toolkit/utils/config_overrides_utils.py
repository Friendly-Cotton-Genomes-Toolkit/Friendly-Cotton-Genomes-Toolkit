from typing import Any, Optional, Dict
import logging

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.config_overrides_utils")


def _update_config_from_overrides(config_obj: Any, overrides: Optional[Dict[str, Any]]):
    if not overrides:
        return
    for key, value in overrides.items():
        if value is not None:
            if hasattr(config_obj, key):
                setattr(config_obj, key, value)
            else:
                logger.warning(_("配置覆盖警告：在对象 {} 中找不到键 '{}'。").format(type(config_obj).__name__, key))
