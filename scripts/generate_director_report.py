"""
Gera um relatório executivo em HTML a partir de um prompt.
O script usa a própria CLI do agente para consolidar respostas e dashboards.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "reports"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))
from ui_theme import css_variables, custom_css, favicon_href, get_ui_theme, logo_src, page_background_css, panel_background_css
from dashboard import render_rich_text
from mcp_server.config_loader import load_config


def compact(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"[╭╮╰╯│─]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "report"


def time_range_to_phrase(time_range: str) -> str:
    normalized = (time_range or "7d").strip().lower()
    mapping = {
        "1d": "ultimo dia",
        "7d": "ultimos 7 dias",
        "15d": "ultimos 15 dias",
        "30d": "ultimos 30 dias",
        "60d": "ultimos 60 dias",
        "90d": "ultimos 90 dias",
        "180d": "ultimos 180 dias",
        "365d": "ultimos 365 dias",
    }
    return mapping.get(normalized, f"ultimos {normalized}")


def parse_include_sections(value: str | None, config: dict) -> list[str]:
    defaults = config.get("ui", {}).get("reports", {}).get(
        "default_sections",
        ["overview", "risk", "success", "lead_time", "approvals"],
    )
    if not value:
        return defaults
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def extract_architectures(prompt: str) -> list[str]:
    prompt_low = prompt.lower()
    architectures = []
    for arch in ["api", "srv", "bff", "apim"]:
        if re.search(rf"\b{re.escape(arch)}\b", prompt_low):
            architectures.append(arch)
    return architectures


def select_questions(prompt: str, *, time_range: str, include_sections: list[str]) -> list[str]:
    prompt_low = prompt.lower()
    period = time_range_to_phrase(time_range)
    questions: list[str] = []
    architectures = extract_architectures(prompt)

    if "overview" in include_sections:
        questions.extend(
            [
                f"Qual é a porcentagem de sucesso e falha geral em todas as esteiras nos {period}?",
                f"Qual workflow concentrou mais execuções nos {period}?",
            ]
        )

    if "risk" in include_sections:
        questions.extend(
            [
                f"Qual é a esteira que mais falhou nos {period}?",
                f"Quais jobs com maior volume de falhas nos {period}?",
            ]
        )

    if "success" in include_sections:
        questions.append(f"Quais workflows com maior taxa de sucesso nos {period}?")

    if "lead_time" in include_sections:
        questions.extend(
            [
                f"Entre o gatilho e o deploy qual é o tempo medio nos {period}?",
                f"Qual é o tempo medio de execução de esteiras de hom e de prd nos {period}?",
            ]
        )

    if "approvals" in include_sections:
        questions.append("quantos jobs estão com status wating aguardando aprovação?")

    if "analysts" in include_sections:
        questions.append(f"Qual o analista com maior sucesso de execução de workflows nos {period}?")

    if "prd" in include_sections or any(token in prompt_low for token in ["prd", "producao", "produção"]):
        questions.extend(
            [
                f"Quais workflows com maior volume de falhas em PRD nos {period}?",
                f"Quais workflows com maior taxa de sucesso em PRD nos {period}?",
            ]
        )

    if "hml" in include_sections or "hml" in prompt_low or "hom" in prompt_low:
        questions.append(f"Quais workflows com maior volume de falhas em HML nos {period}?")

    for arch in ["api", "srv", "bff", "apim"]:
        if arch in include_sections or arch in architectures:
            questions.extend(
                [
                    f"Qual é a porcentagem de falhas e sucesso em esteiras de {arch} nos {period}?",
                    f"Quais repositórios de {arch} mais executaram workflows nos {period}?",
                ]
            )

    if "java" in include_sections or "java" in prompt_low:
        questions.append(f"Quais workflows Java com maior volume de falhas nos {period}?")

    if "teams" in include_sections or "time" in prompt_low or "vskey" in prompt_low:
        questions.append(f"Quais workflows do time core com maior volume de falhas nos {period}?")

    return list(dict.fromkeys(questions))


def run_question(question: str) -> tuple[str, str | None]:
    env = os.environ.copy()
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Falha ao executar pergunta: {question}\n{proc.stdout}\n{proc.stderr}")

    raw_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    output = compact(raw_output)
    dashboard_match = re.search(r"Dashboard HTML salvo em ([^\s]+\.html)", output)
    dashboard_path = dashboard_match.group(1) if dashboard_match else None
    answer = output
    if ".html" in answer:
        answer = answer.split(".html", 1)[1].strip()
    answer = re.sub(r"^❓\s*Pergunta:\s*.*?\s+", "", answer)
    return answer or output, dashboard_path


def _section_icon(title: str) -> str:
    low = title.lower()
    if "falha" in low or "risco" in low:
        return "❌"
    if "sucesso" in low:
        return "✅"
    if "tempo" in low or "lead time" in low:
        return "⏱️"
    if "analista" in low:
        return "👤"
    if "aprov" in low:
        return "🟡"
    return "📊"


def render_report(config: dict, prompt: str, sections: list[dict]) -> str:
    ui_theme = get_ui_theme(config)
    branding = ui_theme.get("branding", {})
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    favicon = favicon_href(ui_theme)
    logo = logo_src(ui_theme)
    brand_badge = escape(str(branding.get("header_badge", "Executive Dashboard")))
    product_name = escape(str(branding.get("product_name", "GitHub Workflow Intelligence")))
    kpi_cards = [
        ("Analises", str(len(sections))),
        ("Dashboards", str(sum(1 for section in sections if section.get("dashboard")))),
        ("Foco", "Diretoria"),
    ]
    cards_html = "".join(
        f'<article class="summary-card"><div class="summary-label">{escape(label)}</div><div class="summary-value">{escape(value)}</div></article>'
        for label, value in kpi_cards
    )
    cards = "".join(
        f"""
        <article class="card">
          <div class="label">{_section_icon(section["title"])} {escape(section["title"])}</div>
          <div class="answer">{render_rich_text(section["answer"])}</div>
          {f'<a href="../dashboards/{Path(section["dashboard"]).name}" target="_blank">Abrir dashboard detalhado</a>' if section.get("dashboard") else ""}
        </article>
        """
        for section in sections
    )
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(section['title'])}</td>"
        f"<td>{render_rich_text(section['answer'])}</td>"
        f"<td>{f'<a href=\"../dashboards/{Path(section['dashboard']).name}\" target=\"_blank\">Dashboard</a>' if section.get('dashboard') else 'n/a'}</td>"
        "</tr>"
        for section in sections
    )
    favicon_html = f'<link rel="icon" href="{favicon}">' if favicon else ""
    logo_html = f'<img class="brand-logo" src="{logo}" alt="Logo">' if logo else ""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatório Executivo</title>
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
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px 44px; }}
    .hero {{
      background: linear-gradient(135deg, var(--hero-from), var(--hero-to));
      color: #f8f4ea;
      border-radius: 28px;
      padding: 28px;
      box-shadow: 0 16px 36px rgba(19, 33, 38, 0.08);
    }}
    .hero-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .brand-lockup {{
      display: flex;
      gap: 14px;
      align-items: center;
    }}
    .brand-logo {{
      width: 64px;
      height: 64px;
      border-radius: 18px;
      object-fit: contain;
      padding: 10px;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: clamp(28px, 4vw, 44px); }}
    .hero p {{ margin: 0; line-height: 1.7; max-width: 900px; }}
    .meta {{ margin-top: 14px; font-size: 13px; opacity: 0.82; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 8px 14px;
      background: rgba(255,255,255,0.12);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .summary-card {{
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.16);
      border-radius: 18px;
      padding: 16px;
    }}
    .summary-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      opacity: 0.82;
    }}
    .summary-value {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
      margin-top: 24px;
    }}
    .card {{
      {panel_background_css(ui_theme)}
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 18px;
      box-shadow: 0 16px 36px rgba(19, 33, 38, 0.08);
    }}
    .label {{
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    p {{ line-height: 1.7; }}
    .answer p {{
      margin: 0 0 10px;
    }}
    .answer ul {{
      margin: 6px 0 0;
      padding-left: 20px;
      line-height: 1.7;
    }}
    code {{
      background: rgba(23, 76, 79, 0.08);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 999px;
      font-size: 0.95em;
    }}
    a {{
      color: var(--accent-2);
      text-decoration: none;
      font-weight: 700;
    }}
    .table-wrap {{
      margin-top: 24px;
      border-radius: 22px;
      overflow: hidden;
      border: 1px solid var(--line);
      {panel_background_css(ui_theme)}
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.6;
    }}
    th {{
      background: rgba(23, 76, 79, 0.08);
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 12px;
    }}
    @media (max-width: 720px) {{
      th, td {{
        padding: 12px;
      }}
    }}
{custom_css(ui_theme)}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="hero-top">
        <div class="brand-lockup">
          {logo_html}
          <div>
            <div class="badge">{brand_badge}</div>
            <h1>{product_name}</h1>
          </div>
        </div>
      </div>
      <p>{escape(prompt)}</p>
      <div class="meta">Gerado em {escape(generated_at)} • {len(sections)} análises consolidadas</div>
      <div class="summary-grid">{cards_html}</div>
    </section>
    <section class="grid">
      {cards}
    </section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Análise</th>
            <th>Insight executivo</th>
            <th>Detalhe</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Gera um relatório executivo em HTML a partir de um prompt.")
    parser.add_argument("--prompt", required=True, help="Prompt do relatório.")
    parser.add_argument("--output", help="Caminho do HTML de saída.")
    parser.add_argument("--title", help="Título opcional do relatório.")
    parser.add_argument("--time-range", help="Recorte temporal como 7d, 30d, 90d, 365d.")
    parser.add_argument(
        "--include",
        help="Blocos de dados a exibir. Ex: overview,risk,success,lead_time,approvals,prd,api,java,teams",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else OUTPUT_DIR / f"{slugify(args.prompt)}.html"
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    config = load_config(str(ROOT / "config.yaml"))
    time_range = args.time_range or config.get("ui", {}).get("reports", {}).get("default_time_range", "7d")
    include_sections = parse_include_sections(args.include, config)
    title = args.title or args.prompt

    sections = []
    for question in select_questions(args.prompt, time_range=time_range, include_sections=include_sections):
        answer, dashboard_path = run_question(question)
        sections.append(
            {
                "title": question,
                "answer": answer,
                "dashboard": dashboard_path,
            }
        )

    html = render_report(config, title, sections)
    output_path.write_text(html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
