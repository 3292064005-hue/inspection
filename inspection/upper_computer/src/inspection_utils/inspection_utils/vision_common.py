from __future__ import annotations

"""Stable image/plugin boundary exports for vision packages."""

from .image_tools import crop_roi, save_image
from .plugin_contracts import PluginManifest

__all__ = ['PluginManifest', 'crop_roi', 'save_image']
