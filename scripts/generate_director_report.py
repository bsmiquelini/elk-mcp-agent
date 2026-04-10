"""
Gera um relatório executivo em HTML usando o runtime interno do agente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "reports"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))
from executive_report import (
    generate_sections,
    parse_include_sections,
    render_report,
    slugify,
)
from mcp_server.config_loader import load_config
from runtime import AgentRuntimeWorker


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

    worker = AgentRuntimeWorker(str(ROOT / "config.yaml"))
    worker.start()
    try:
        sections = worker.run(
            generate_sections(
                worker.runtime,
                prompt=args.prompt,
                time_range=time_range,
                include_sections=include_sections,
            )
        )
    finally:
        worker.stop()
    html = render_report(config, title, sections)
    output_path.write_text(html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
