"""
Geração de dashboards HTML para perguntas principais do MVP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
import re

from ui_theme import css_variables, custom_css, favicon_href, get_ui_theme, logo_src, page_background_css, panel_background_css


def slugify(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "dashboard"


def save_dashboard_html(config: dict, question: str, answer: str, dashboard: dict) -> Path:
    interface_cfg = config.get("agent", {}).get("interface", {})
    if not interface_cfg.get("generate_dashboard_html", True):
        return None
    output_dir = Path(interface_cfg.get("dashboard_output_dir", "artifacts/dashboards"))
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboard_id = dashboard.get("id") or slugify(question)
    specific_path = output_dir / f"{dashboard_id}.html"
    latest_path = output_dir / "last_dashboard.html"

    html = render_dashboard_html(question, answer, dashboard, config=config)
    specific_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    return specific_path


def render_dashboard_html(question: str, answer: str, dashboard: dict, config: dict | None = None) -> str:
    ui_theme = get_ui_theme(config or {})
    branding = ui_theme.get("branding", {})
    title = dashboard.get("title") or question
    cards = dashboard.get("cards", [])
    sections = dashboard.get("sections", [])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    favicon = favicon_href(ui_theme)
    logo = logo_src(ui_theme)
    brand_badge = escape(str(branding.get("header_badge", "CI/CD Intelligence")))
    product_name = escape(str(branding.get("product_name", "GitHub Workflow Intelligence")))
    custom_css_text = custom_css(ui_theme)

    cards_html = "".join(render_card(card) for card in cards)
    sections_html = "".join(render_section(section) for section in sections)
    raw_json = escape(json.dumps(dashboard, ensure_ascii=False, indent=2))
    logo_html = f'<img class="brand-logo" src="{logo}" alt="Logo">' if logo else ""
    favicon_html = f'<link rel="icon" href="{favicon}">' if favicon else ""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  {favicon_html}
  <style>
    :root {{
{css_variables(ui_theme)}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      {page_background_css(ui_theme)}
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, var(--hero-from), var(--hero-to));
      color: #f8f4ea;
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .hero-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }}
    .brand-lockup {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-logo {{
      width: 56px;
      height: 56px;
      border-radius: 16px;
      object-fit: contain;
      background: rgba(255,255,255,0.1);
      padding: 8px;
      border: 1px solid rgba(255,255,255,0.18);
    }}
    .brand-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 14px;
      background: rgba(255,255,255,0.12);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      opacity: 0.78;
    }}
    h1 {{
      margin: 10px 0 12px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.05;
    }}
    .subtitle {{
      font-size: 16px;
      line-height: 1.6;
      max-width: 900px;
      color: rgba(248, 244, 234, 0.92);
    }}
    .meta {{
      margin-top: 18px;
      font-size: 13px;
      color: rgba(248, 244, 234, 0.75);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}
    .card, .section {{
      {panel_background_css(ui_theme)}
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .card {{
      padding: 18px 18px 20px;
    }}
    .card .label {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .card .value {{
      margin-top: 8px;
      font-size: 30px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .card .note {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .tone-success .value {{ color: var(--success); }}
    .tone-warning .value {{ color: var(--warning); }}
    .tone-danger .value {{ color: var(--danger); }}
    .tone-accent .value {{ color: var(--accent); }}
    .section {{
      margin-top: 20px;
      padding: 20px;
    }}
    .section h2 {{
      margin: 0 0 14px;
      font-size: 20px;
    }}
    .section p {{
      color: var(--muted);
      line-height: 1.6;
    }}
    .rich-text p {{
      color: var(--muted);
      line-height: 1.7;
      margin: 0 0 10px;
    }}
    .rich-text ul {{
      margin: 8px 0 0 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.7;
    }}
    .rich-text code, .subtitle code, td code, .kv-item code {{
      background: rgba(23, 76, 79, 0.08);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 999px;
      font-size: 0.95em;
    }}
    .rich-text strong, .subtitle strong, td strong, .kv-item strong {{
      color: var(--ink);
    }}
    .bar-list {{
      display: grid;
      gap: 12px;
      margin-top: 10px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(120px, 220px) 1fr auto;
      gap: 12px;
      align-items: center;
    }}
    .bar-label {{
      font-size: 14px;
      font-weight: 600;
    }}
    .bar-track {{
      width: 100%;
      height: 16px;
      background: #ece5d8;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .bar-value {{
      font-size: 13px;
      color: var(--muted);
      min-width: 92px;
      text-align: right;
    }}
    .kv {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.55;
    }}
    th {{
      background: rgba(23, 76, 79, 0.08);
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 12px;
    }}
    .kv-item {{
      padding: 14px;
      border-radius: 16px;
      background: #f7f2e8;
      border: 1px solid #e8dfcf;
    }}
    .kv-item .k {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
    }}
    .kv-item .v {{
      margin-top: 8px;
      font-size: 18px;
      font-weight: 600;
      line-height: 1.35;
    }}
    pre {{
      margin: 0;
      overflow: auto;
      padding: 16px;
      border-radius: 18px;
      background: #1c232b;
      color: #eef2f4;
      font-size: 12px;
      line-height: 1.5;
    }}
    @media (max-width: 720px) {{
      .hero-top {{
        align-items: flex-start;
      }}
      .bar-row {{
        grid-template-columns: 1fr;
      }}
      .bar-value {{
        text-align: left;
      }}
    }}
{custom_css_text}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-top">
        <div class="brand-lockup">
          {logo_html}
          <div>
            <div class="eyebrow">{product_name}</div>
            <div class="brand-badge">{brand_badge}</div>
          </div>
        </div>
      </div>
      <h1>{escape(title)}</h1>
      <div class="subtitle"><strong>Pergunta:</strong> {escape(question)}<br><strong>Resposta:</strong> {render_rich_text(answer)}</div>
      <div class="meta">Gerado em {escape(generated_at)}</div>
    </section>

    <section class="grid">
      {cards_html}
    </section>

    {sections_html}

    <section class="section">
      <h2>Payload do Dashboard</h2>
      <pre>{raw_json}</pre>
    </section>
  </div>
</body>
</html>
"""


def render_card(card: dict) -> str:
    tone = escape(card.get("tone", "accent"))
    label = escape(str(card.get("label", "")))
    value = escape(str(card.get("value", "")))
    note = escape(str(card.get("note", ""))) if card.get("note") else ""
    note_html = f'<div class="note">{note}</div>' if note else ""
    return (
        f'<article class="card tone-{tone}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f"{note_html}"
        f"</article>"
    )


def render_section(section: dict) -> str:
    section_type = section.get("type", "text")
    title = escape(str(section.get("title", "")))

    if section_type == "bar":
        series = section.get("series", [])
        return (
            f'<section class="section"><h2>{title}</h2>'
            f'{render_bar_list(series)}</section>'
        )

    if section_type == "kv":
        items = section.get("items", [])
        return (
            f'<section class="section"><h2>{title}</h2>'
            f'<div class="kv">{"".join(render_kv_item(item) for item in items)}</div>'
            f"</section>"
        )

    if section_type == "table":
        columns = section.get("columns", [])
        rows = section.get("rows", [])
        return (
            f'<section class="section"><h2>{title}</h2>'
            f'{render_table(columns, rows)}</section>'
        )

    text = render_rich_text(str(section.get("text", "")))
    return f'<section class="section"><h2>{title}</h2><div class="rich-text">{text}</div></section>'


def render_kv_item(item: dict) -> str:
    key = escape(str(item.get("key", "")))
    value = render_rich_text(str(item.get("value", "")))
    return f'<div class="kv-item"><div class="k">{key}</div><div class="v">{value}</div></div>'


def render_bar_list(series: list[dict]) -> str:
    max_value = max((float(item.get("value", 0) or 0) for item in series), default=0)
    rows = []
    for item in series:
        label = escape(str(item.get("label", "")))
        value = float(item.get("value", 0) or 0)
        note = escape(str(item.get("note", ""))) if item.get("note") else ""
        pct = 0 if max_value <= 0 else min(100, (value / max_value) * 100)
        value_text = escape(str(item.get("display_value", note or item.get("value", ""))))
        rows.append(
            "<div class=\"bar-row\">"
            f"<div class=\"bar-label\">{label}</div>"
            f"<div class=\"bar-track\"><div class=\"bar-fill\" style=\"width:{pct:.2f}%\"></div></div>"
            f"<div class=\"bar-value\">{value_text}</div>"
            "</div>"
        )
    return f'<div class="bar-list">{"".join(rows)}</div>'


def render_table(columns: list[dict], rows: list[dict]) -> str:
    headers = "".join(f"<th>{escape(str(column.get('label', '')))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = []
        for column in columns:
            key = column.get("key")
            cells.append(f"<td>{render_rich_text(str(row.get(key, '')))}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def render_rich_text(text: str) -> str:
    lines = [line.rstrip() for line in str(text or "").splitlines()]
    if any(line.lstrip().startswith("- ") for line in lines):
        blocks = []
        paragraph = []
        items = []

        def flush_paragraph():
            if paragraph:
                blocks.append(f"<p>{_render_inline(' '.join(part.strip() for part in paragraph if part.strip()))}</p>")
                paragraph.clear()

        def flush_items():
            if items:
                blocks.append("<ul>" + "".join(f"<li>{_render_inline(item)}</li>" for item in items) + "</ul>")
                items.clear()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                flush_items()
                continue
            if stripped.startswith("- "):
                flush_paragraph()
                items.append(stripped[2:].strip())
            else:
                flush_items()
                paragraph.append(stripped)

        flush_paragraph()
        flush_items()
        return "".join(blocks)

    paragraphs = [segment.strip() for segment in "\n".join(lines).split("\n\n") if segment.strip()]
    if not paragraphs:
        return ""
    return "".join(
        f"<p>{'<br>'.join(_render_inline(part.strip()) for part in paragraph.splitlines() if part.strip())}</p>"
        for paragraph in paragraphs
    )


def _render_inline(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped
