"""One-shot CLI demo of the full pipeline.

Usage:
    python -m app.scripts.demo --product "Notion" --market us
    python -m app.scripts.demo --product "飞书" --market cn --json
"""
from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..observability.tracer import Tracer
from ..orchestration import AnalysisRequest, run_analysis


app = typer.Typer(add_completion=False, help="Run one analysis end-to-end and print the report.")
console = Console()


@app.command()
def main(
    product: str = typer.Option(..., "--product", "-p", help="Target product name"),
    market: str = typer.Option("us", "--market", "-m", help="Market code: cn | us"),
    extras: str = typer.Option("", "--extras", help="Extra competitors, comma-separated"),
    as_json: bool = typer.Option(False, "--json", help="Print the full JSON report"),
) -> None:
    extra_list = [s.strip() for s in extras.split(",") if s.strip()]
    req = AnalysisRequest(product=product, market=market, extra_competitors=extra_list)
    tracer = Tracer()

    async def _run():
        return await run_analysis(req, tracer)

    report = asyncio.run(_run())

    if as_json:
        console.print_json(report.model_dump_json(indent=2))
        return

    # Pretty summary
    console.print(Panel.fit(
        f"[bold]{report.title}[/]\n"
        f"product: {report.product}    market: {report.market}    locale: {report.locale}\n"
        f"competitors: {', '.join(c.name for c in report.competitors)}",
        title="Final report",
    ))

    metrics = report.metrics
    t = Table(title="Run metrics")
    t.add_column("Metric"); t.add_column("Value", justify="right")
    t.add_row("Elapsed (s)", f"{metrics.elapsed_seconds:.1f}")
    t.add_row("Total tokens", str(metrics.total_tokens))
    t.add_row("LLM calls", str(metrics.total_llm_calls))
    t.add_row("Schema completeness", f"{metrics.schema_completeness*100:.0f}%")
    t.add_row("Avg sources / competitor", f"{metrics.avg_sources_per_competitor}")
    t.add_row("QC iterations", str(metrics.qc_iterations))
    t.add_row("Rework count", str(metrics.rework_count))
    console.print(t)

    console.print(Panel(report.executive_summary_md, title="Executive summary"))
    for sec in report.sections:
        console.print(Panel(sec.body_md, title=sec.heading))

    console.print(f"\n[dim]Report id: {report.id}  (saved to backend/data/app.sqlite)[/]")
    console.print(f"[dim]Trace events: {len(tracer.events)}[/]")


if __name__ == "__main__":
    app()
