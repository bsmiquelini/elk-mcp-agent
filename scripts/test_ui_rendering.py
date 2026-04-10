"""
Validação rápida da camada visual: dashboard, favicon, logo, CSS customizado
e relatório executivo.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from dashboard import render_dashboard_html
from generate_director_report import render_report


PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+Xn2QAAAAASUVORK5CYII="
)


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def build_test_config(tmp_dir: Path) -> dict:
    logo_path = tmp_dir / "logo.png"
    css_path = tmp_dir / "theme.css"
    logo_path.write_bytes(base64.b64decode(PNG_1X1))
    css_path.write_text(".hero { outline: 3px solid rgb(10, 20, 30); }", encoding="utf-8")
    return {
        "domain": {"name": "Workflow Intelligence UX"},
        "ui": {
            "branding": {
                "product_name": "Workflow Intelligence UX",
                "header_badge": "Painel Executivo",
                "favicon_emoji": "🚀",
                "header_logo_png": str(logo_path),
            },
            "theme": {
                "accent": "#0f5f63",
                "accent_2": "#d47a2f",
                "custom_css_file": str(css_path),
            },
        },
    }


def main():
    tmp_dir = ROOT / "artifacts" / "ui-test-assets"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    config = build_test_config(tmp_dir)

    dashboard_html = render_dashboard_html(
        question="Qual a taxa de sucesso em PRD?",
        answer="✅ Em PRD a taxa de sucesso ficou em 83.72%.",
        dashboard={
            "id": "ui-test",
            "title": "Teste Visual",
            "cards": [{"label": "Sucesso", "value": "83.72%", "tone": "success"}],
            "sections": [
                {
                    "type": "table",
                    "title": "Tabela Executiva",
                    "columns": [
                        {"key": "kpi", "label": "KPI"},
                        {"key": "value", "label": "Valor"},
                    ],
                    "rows": [{"kpi": "Sucesso PRD", "value": "83.72%"}],
                }
            ],
        },
        config=config,
    )
    assert_true('rel="icon"' in dashboard_html, "Dashboard sem favicon.")
    assert_true('class="brand-logo"' in dashboard_html, "Dashboard sem logo.")
    assert_true("Tabela Executiva" in dashboard_html, "Dashboard sem tabela.")
    assert_true("outline: 3px solid rgb(10, 20, 30);" in dashboard_html, "Dashboard sem CSS customizado.")

    report_html = render_report(
        config=config,
        prompt="Quero um resumo executivo de CI/CD.",
        sections=[
            {
                "title": "Taxa geral de sucesso",
                "answer": "✅ O ambiente PRD fechou em 83.72% de sucesso.",
                "dashboard": "artifacts/dashboards/prd_success.html",
            }
        ],
    )
    assert_true('rel="icon"' in report_html, "Relatório sem favicon.")
    assert_true('class="brand-logo"' in report_html, "Relatório sem logo.")
    assert_true("<table>" in report_html, "Relatório sem tabela gerencial.")
    assert_true("Painel Executivo" in report_html, "Relatório sem badge customizado.")

    print("OK: renderização visual validada.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
