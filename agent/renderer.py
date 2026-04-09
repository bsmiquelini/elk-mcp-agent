"""
Renderiza respostas, gráficos e status no terminal com Rich.
"""

from rich.console  import Console
from rich.markdown import Markdown
from rich.panel    import Panel
from rich.text     import Text
from rich.live     import Live
from rich          import box

console = Console()

_CHART_WIDTH = 40
_SHOW_TOOL_CALLS = True


def configure_interface(interface: dict | None):
    global _SHOW_TOOL_CALLS
    interface = interface or {}
    _SHOW_TOOL_CALLS = interface.get("show_tool_calls", True)


def print_welcome(config: dict):
    domain    = config.get("domain", {})
    agent_cfg = config.get("agent", {})
    interface = agent_cfg.get("interface", {})
    model     = agent_cfg.get("model", "?")
    if not interface.get("show_welcome_panel", True):
        return

    banner_title = interface.get("banner_title") or domain.get("name", "ELK MCP Agent")
    banner_help = interface.get("banner_help", "Digite sair para encerrar · limpar para resetar contexto")
    if "banner_subtitle" in interface:
        banner_subtitle = interface.get("banner_subtitle", "")
    else:
        banner_subtitle = f"Modelo: {model}"

    lines = [f"[bold cyan]🤖 {banner_title}[/bold cyan]"]
    if banner_subtitle:
        lines.append(f"[dim]{banner_subtitle}[/dim]")
    if banner_help:
        lines.append(f"[dim]{banner_help}[/dim]")

    console.print()
    console.print(Panel.fit(
        "\n".join(lines),
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()


def print_thinking():
    return Live(
        Text("⏳ Analisando...", style="dim yellow"),
        console=console,
        refresh_per_second=10,
        transient=True,
    )


def print_tool_call(tool_name: str, args: dict):
    if not _SHOW_TOOL_CALLS:
        return
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items()) if args else ""
    console.print(f"  [dim]🔧 {tool_name}({args_str})[/dim]", highlight=False)


def print_response(content: str):
    console.print()
    console.print(Panel(
        Markdown(content),
        border_style="green",
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()


def print_error(message: str):
    console.print(f"\n[bold red]❌ {message}[/bold red]\n")


def print_info(message: str):
    console.print(f"[dim cyan]ℹ  {message}[/dim cyan]")


def print_warning(message: str):
    console.print(f"[bold yellow]⚠️  {message}[/bold yellow]")


def get_user_input(turn: int) -> str:
    try:
        return console.input(f"[bold green]você[/bold green] [dim]#{turn}[/dim] › ").strip()
    except (EOFError, KeyboardInterrupt):
        return "sair"
