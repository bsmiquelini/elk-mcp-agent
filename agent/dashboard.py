"""
Geração de dashboards HTML para perguntas principais do MVP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
import re


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

    html = render_dashboard_html(question, answer, dashboard)
    specific_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    return specific_path


def render_dashboard_html(question: str, answer: str, dashboard: dict) -> str:
    title = dashboard.get("title") or question
    cards = dashboard.get("cards", [])
    sections = dashboard.get("sections", [])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    cards_html = "".join(render_card(card) for card in cards)
    sections_html = "".join(render_section(section) for section in sections)
    raw_json = escape(json.dumps(dashboard, ensure_ascii=False, indent=2))

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f5f2ea;
      --panel: #fffdf8;
      --ink: #182028;
      --muted: #5f6b76;
      --line: #dfd6c6;
      --accent: #174c4f;
      --accent-2: #c46a2d;
      --success: #1f7a45;
      --warning: #a45b11;
      --danger: #b23a2b;
      --shadow: 0 18px 40px rgba(24, 32, 40, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(196, 106, 45, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(23, 76, 79, 0.18), transparent 24%),
        var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(23,76,79,0.96), rgba(29,54,65,0.94));
      color: #f8f4ea;
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
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
      background: var(--panel);
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
      .bar-row {{
        grid-template-columns: 1fr;
      }}
      .bar-value {{
        text-align: left;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">GitHub Workflow Intelligence</div>
      <h1>{escape(title)}</h1>
      <div class="subtitle"><strong>Pergunta:</strong> {escape(question)}<br><strong>Resposta:</strong> {escape(answer)}</div>
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

    text = escape(str(section.get("text", "")))
    return f'<section class="section"><h2>{title}</h2><p>{text}</p></section>'


def render_kv_item(item: dict) -> str:
    key = escape(str(item.get("key", "")))
    value = escape(str(item.get("value", "")))
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
