"""Backward-compat — use core.mcp.attachments."""

from core.mcp.attachments import ensure_file_path as prepare_ocr_args_for_external_mcp

__all__ = ["prepare_ocr_args_for_external_mcp"]
