from collections.abc import Sequence
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from eth_rescue.types import (
    ActionOutcome,
    PreparedAction,
    RescueData,
    SimulationResult,
)

console = Console()


def title(text: str) -> None:
    console.print()
    console.rule(f"[bold cyan]{text}[/bold cyan]", style="cyan")
    console.print()


def section(text: str) -> None:
    console.print(f"\n[bold cyan]{text}[/bold cyan]")


def info(message: str) -> None:
    console.print(f"[cyan]INFO[/cyan] {message}")


def success(message: str) -> None:
    console.print(f"[green]OK[/green] {message}")


def warning(message: str) -> None:
    console.print(f"[yellow]WARN[/yellow] {message}")


def error(message: str) -> None:
    console.print(f"[red]ERROR[/red] {message}")


def callout(title_text: str, lines: Sequence[str], style: str = "cyan") -> None:
    console.print(
        Panel(
            "\n".join(lines),
            title=title_text,
            title_align="left",
            border_style=style,
            box=box.ASCII,
        )
    )


def render_rescue_plan(actions: list[RescueData]) -> None:
    table = Table(title="Rescue plan", box=box.ASCII, show_lines=True)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Action", overflow="fold")
    table.add_column("Contract", overflow="fold")
    table.add_column("Call", overflow="fold")

    for i, action in enumerate(actions, 1):
        desc = action.get("description") or action["function_signature"]
        table.add_row(
            str(i),
            desc,
            action["address"],
            f"{action['function_signature']} {action['args']}",
        )

    console.print()
    console.print(table)
    console.print()


def render_cost_preview(
    w3: Any, prepared: list[PreparedAction], max_fee_per_gas: int
) -> None:
    section("Step 3: Plan & cost preview")
    console.print(
        f"Network gas (maxFeePerGas): "
        f"[bold]{w3.from_wei(max_fee_per_gas, 'gwei')} gwei[/bold]"
    )

    table = Table(title="Estimated rescue cost", box=box.ASCII)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Target", overflow="fold")
    table.add_column("Gas", justify="right")
    table.add_column("Estimated ETH", justify="right")

    total = 0
    for i, action in enumerate(prepared, 1):
        cost = action["gas"] * max_fee_per_gas
        total += cost
        table.add_row(
            str(i),
            action["to"],
            f"{action['gas']:,}",
            str(w3.from_wei(cost, "ether")),
        )

    table.add_section()
    table.add_row("", "Total rescue actions", "", str(w3.from_wei(total, "ether")))
    console.print(table)


def render_simulation_result(result: SimulationResult) -> None:
    table = Table(title="Bundle simulation", box=box.ASCII)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Tx hash", overflow="fold")
    table.add_column("Gas used", justify="right")
    table.add_column("Status", overflow="fold")

    for i, tx_result in enumerate(result.get("results", []), 1):
        error_text = tx_result.get("error") or tx_result.get("revert") or ""
        table.add_row(
            str(i),
            str(tx_result.get("txHash", "")),
            f"{int(tx_result.get('gasUsed', 0)):,}",
            error_text or "OK",
        )

    table.add_section()
    table.add_row(
        "",
        "Total gas used",
        f"{int(result.get('totalGasUsed', 0)):,}",
        f"Bundle hash: {result.get('bundleHash', '')}",
    )
    console.print(table)


def render_outcome_report(
    actions: list[RescueData], outcomes: list[ActionOutcome]
) -> None:
    styles = {
        "rescued": "[green]rescued[/green]",
        "failed": "[red]failed[/red]",
        "unverified": "[yellow]unverified[/yellow]",
    }
    table = Table(title="Rescue outcome", box=box.ASCII, show_lines=True)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Action", overflow="fold")
    table.add_column("Result")

    for outcome in outcomes:
        action = actions[outcome.index]
        desc = action.get("description") or action["function_signature"]
        table.add_row(
            str(outcome.index + 1), desc, styles.get(outcome.status, outcome.status)
        )

    console.print()
    console.print(table)
    if any(o.status == "unverified" for o in outcomes):
        warning(
            "Unverified actions could not be checked automatically; confirm them "
            "manually. They are not retried in the legacy fallback."
        )
    console.print()


def render_accounts(victim_address: str, gas_address: str) -> None:
    table = Table(title="Accounts", box=box.ASCII)
    table.add_column("Role", style="bold")
    table.add_column("Address", overflow="fold")
    table.add_row("Victim", victim_address)
    table.add_row("Gas wallet", gas_address)
    console.print()
    console.print(table)
