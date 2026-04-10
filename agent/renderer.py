"""
Renderiza respostas, gráficos e status no terminal com Rich.
"""

from rich.console  import Console
from rich.markdown import Markdown
from rich.panel    import Panel
from rich.text     import Text
from rich.live     import Live
from rich          import box

from ui_theme import get_ui_theme

console = Console()

_CHART_WIDTH = 40
_SHOW_TOOL_CALLS = True
_CLI_THEME = get_ui_theme({})


def configure_interface(interface: dict | None, config: dict | None = None):
    global _SHOW_TOOL_CALLS, _CLI_THEME
    interface = interface or {}
    _SHOW_TOOL_CALLS = interface.get("show_tool_calls", True)
    _CLI_THEME = get_ui_theme(config or {})


def print_welcome(config: dict):
    domain    = config.get("domain", {})
    agent_cfg = config.get("agent", {})
    interface = agent_cfg.get("interface", {})
    ui_theme = get_ui_theme(config)
    cli_theme = ui_theme.get("cli", {})
    branding = ui_theme.get("branding", {})
    model     = agent_cfg.get("model", "?")
    if not interface.get("show_welcome_panel", True):
        return

    banner_title = interface.get("banner_title") or domain.get("name", "ELK MCP Agent")
    banner_help = interface.get("banner_help", "Digite sair para encerrar · limpar para resetar contexto")
    if "banner_subtitle" in interface:
        banner_subtitle = interface.get("banner_subtitle", "")
    else:
        banner_subtitle = f"Modelo: {model}"

    assistant_icon = cli_theme.get("assistant_icon", "🤖")
    title_style = cli_theme.get("title_style", "bold cyan")
    badge = branding.get("header_badge", "")

    lines = [f"[{title_style}]{assistant_icon} {banner_title}[/{title_style}]"]
    if badge:
        lines.append(f"[dim]{badge}[/dim]")
    if banner_subtitle:
        lines.append(f"[dim]{banner_subtitle}[/dim]")
    if banner_help:
        lines.append(f"[dim]{banner_help}[/dim]")

    console.print()
    console.print(Panel.fit(
        "\n".join(lines),
        border_style=cli_theme.get("border_style", "cyan"),
        box=box.ROUNDED,
    ))
    console.print()


def print_thinking():
    cli_theme = _CLI_THEME.get("cli", {})
    return Live(
        Text(f"{cli_theme.get('thinking_icon', '⏳')} Analisando...", style="dim yellow"),
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
    cli_theme = _CLI_THEME.get("cli", {})
    console.print()
    console.print(Panel(
        Markdown(content),
        border_style=cli_theme.get("response_border_style", "green"),
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()


def print_error(message: str):
    cli_theme = _CLI_THEME.get("cli", {})
    console.print(f"\n[bold red]{cli_theme.get('error_icon', '❌')} {message}[/bold red]\n")


def print_info(message: str):
    cli_theme = _CLI_THEME.get("cli", {})
    console.print(f"[dim cyan]{cli_theme.get('info_icon', 'ℹ️')}  {message}[/dim cyan]")


def print_warning(message: str):
    cli_theme = _CLI_THEME.get("cli", {})
    console.print(f"[bold yellow]{cli_theme.get('warning_icon', '⚠️')}  {message}[/bold yellow]")


def get_user_input(turn: int) -> str:
    cli_theme = _CLI_THEME.get("cli", {})
    try:
        user_icon = cli_theme.get("user_icon", "🧑")
        prompt_style = cli_theme.get("prompt_style", "bold green")
        return console.input(f"[{prompt_style}]{user_icon} você[/{prompt_style}] [dim]#{turn}[/dim] › ").strip()
    except (EOFError, KeyboardInterrupt):
        return "sair"
