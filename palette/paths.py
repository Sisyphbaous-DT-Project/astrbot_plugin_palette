from __future__ import annotations

from pathlib import Path

from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_data_path,
)

from .constants import PLUGIN_NAME


class PalettePaths:
    """集中管理插件运行时路径。"""

    def __init__(self) -> None:
        self.data_root = Path(get_astrbot_data_path())
        self.plugin_data_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME
        self.background_dir = self.plugin_data_dir / "backgrounds"
        self.thumbnail_dir = self.plugin_data_dir / "thumbnails"
        self.patch_backup_dir = self.plugin_data_dir / "dashboard_backups"
        self.user_dashboard_dist = self.data_root / "dist"
        self.user_dashboard_index = self.user_dashboard_dist / "index.html"

    def ensure_runtime_dirs(self) -> None:
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.background_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.patch_backup_dir.mkdir(parents=True, exist_ok=True)

    def resolve_background_file(self, filename: str) -> Path:
        clean_name = Path(filename).name
        if not clean_name or clean_name != filename:
            raise ValueError("背景图片文件名不正确。")
        return self.background_dir / clean_name

    def resolve_thumbnail_file(self, filename: str) -> Path:
        clean_name = Path(filename).name
        if not clean_name or clean_name != filename:
            raise ValueError("缩略图文件名不正确。")
        return self.thumbnail_dir / clean_name

    def to_public_dict(self) -> dict[str, str]:
        return {
            "plugin_data_dir": str(self.plugin_data_dir),
            "background_dir": str(self.background_dir),
            "thumbnail_dir": str(self.thumbnail_dir),
            "patch_backup_dir": str(self.patch_backup_dir),
            "dashboard_index": str(self.user_dashboard_index),
        }
