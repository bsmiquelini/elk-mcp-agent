"""
Tema visual compartilhado entre CLI, dashboards e relatórios.
"""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_UI = {
    "branding": {
        "product_name": "GitHub Workflow Intelligence",
        "favicon_emoji": "📊",
        "header_logo_png": "",
        "favicon_png": "",
        "header_badge": "CI/CD Intelligence",
    },
    "theme": {
        "background": "#f5f2ea",
        "panel": "#fffdf8",
        "ink": "#182028",
        "muted": "#5f6b76",
        "line": "#dfd6c6",
        "accent": "#174c4f",
        "accent_2": "#c46a2d",
        "success": "#1f7a45",
        "warning": "#a45b11",
        "danger": "#b23a2b",
        "hero_gradient_from": "#174c4f",
        "hero_gradient_to": "#1d3641",
        "page_background_image": "",
        "panel_background_image": "",
        "custom_css_file": "",
    },
    "cli": {
        "assistant_icon": "🤖",
        "user_icon": "🧑",
        "thinking_icon": "⏳",
        "info_icon": "ℹ️",
        "warning_icon": "⚠️",
        "error_icon": "❌",
        "success_icon": "✅",
        "border_style": "cyan",
        "response_border_style": "green",
        "title_style": "bold cyan",
        "prompt_style": "bold green",
    },
    "reports": {
        "show_management_table": True,
        "show_recommendations": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_ui_theme(config: dict) -> dict:
    ui_cfg = config.get("ui", {})
    merged = _deep_merge(DEFAULT_UI, ui_cfg)
    domain_name = config.get("domain", {}).get("name")
    if domain_name and not merged["branding"].get("product_name"):
        merged["branding"]["product_name"] = domain_name
    return merged


def resolve_asset_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.exists() else None


def _asset_to_data_uri(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    suffix = path.suffix.lower()
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".webp": "image/webp",
    }.get(suffix)
    if not content_type:
        return None
    return f"data:{content_type};base64,{b64encode(path.read_bytes()).decode('ascii')}"


def favicon_href(theme: dict) -> str:
    branding = theme.get("branding", {})
    theme_colors = theme.get("theme", {})
    favicon_png = resolve_asset_path(branding.get("favicon_png"))
    data_uri = _asset_to_data_uri(favicon_png)
    if data_uri:
        return data_uri
    logo_png = resolve_asset_path(branding.get("header_logo_png"))
    data_uri = _asset_to_data_uri(logo_png)
    if data_uri:
        return data_uri
    emoji = branding.get("favicon_emoji", "📊")
    bg = theme_colors.get("accent", "#174c4f")
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        f"<rect width='64' height='64' rx='14' fill='{bg}'/>"
        f"<text x='50%' y='54%' text-anchor='middle' dominant-baseline='middle' font-size='34'>{emoji}</text>"
        f"</svg>"
    )
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def logo_src(theme: dict) -> str | None:
    return _asset_to_data_uri(resolve_asset_path(theme.get("branding", {}).get("header_logo_png")))


def custom_css(theme: dict) -> str:
    css_file = resolve_asset_path(theme.get("theme", {}).get("custom_css_file"))
    if not css_file:
        return ""
    return css_file.read_text(encoding="utf-8")


def css_variables(theme: dict) -> str:
    theme_colors = theme.get("theme", {})
    mapping = {
        "background": "--bg",
        "panel": "--panel",
        "ink": "--ink",
        "muted": "--muted",
        "line": "--line",
        "accent": "--accent",
        "accent_2": "--accent-2",
        "success": "--success",
        "warning": "--warning",
        "danger": "--danger",
        "hero_gradient_from": "--hero-from",
        "hero_gradient_to": "--hero-to",
    }
    lines = []
    for key, css_name in mapping.items():
        value = theme_colors.get(key)
        if value:
            lines.append(f"      {css_name}: {value};")
    lines.append("      --shadow: 0 18px 40px rgba(24, 32, 40, 0.08);")
    return "\n".join(lines)


def page_background_css(theme: dict) -> str:
    bg_image = theme.get("theme", {}).get("page_background_image")
    bg_path = resolve_asset_path(bg_image)
    if bg_path:
        uri = _asset_to_data_uri(bg_path)
        if uri:
            return (
                f"background: linear-gradient(rgba(245,242,234,0.92), rgba(245,242,234,0.92)), "
                f"url('{uri}') center/cover no-repeat fixed;"
            )
    return (
        "background:"
        " radial-gradient(circle at top left, rgba(196, 106, 45, 0.18), transparent 28%),"
        " radial-gradient(circle at top right, rgba(23, 76, 79, 0.18), transparent 24%),"
        " var(--bg);"
    )


def panel_background_css(theme: dict) -> str:
    bg_image = theme.get("theme", {}).get("panel_background_image")
    bg_path = resolve_asset_path(bg_image)
    if bg_path:
        uri = _asset_to_data_uri(bg_path)
        if uri:
            return f"background: linear-gradient(rgba(255,253,248,0.95), rgba(255,253,248,0.95)), url('{uri}') center/cover no-repeat;"
    return "background: var(--panel);"
