from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from core.brain.engine import Brain
    from core.devices.discovery import DiscoveryOrchestrator

console = Console()


async def interactive_cli(
    discovery: DiscoveryOrchestrator,
    brain: Brain,
) -> None:
    console.print("\n[bold cyan]Anima CLI[/bold cyan] — Make Every Hardware Intelligent")
    console.print("Type [bold]help[/bold] for commands, [bold]quit[/bold] to exit.\n")

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: input("anima> "),
            )
        except (EOFError, KeyboardInterrupt):
            break

        cmd = user_input.strip().lower()

        if cmd in ("quit", "exit", "q"):
            break
        elif cmd == "help":
            console.print("""
[bold]Commands:[/bold]
  devices       — List all discovered devices
  scan          — Re-scan for new devices
  status <id>   — Show device status
  rooms         — List rooms
  history       — Show recent AI decisions
  quit          — Exit CLI
            """)
        elif cmd == "devices":
            _print_devices(discovery)
        elif cmd == "scan":
            console.print("[yellow]Scanning...[/yellow]")
            new = await discovery.scan()
            console.print(f"[green]Found {len(new)} new device(s), {len(discovery.devices)} total[/green]")
        elif cmd.startswith("status "):
            device_id = cmd.split(" ", 1)[1]
            device = discovery.get_device(device_id)
            if device:
                console.print(device.model_dump_json(indent=2))
            else:
                console.print(f"[red]Device not found: {device_id}[/red]")
        elif cmd == "history":
            history = await brain._memory.get_history("default", limit=10)
            for entry in history:
                console.print(
                    f"  [{entry.get('timestamp', '?')}] {entry.get('action', '?')} on {entry.get('device_id', '?')} — {entry.get('reason', '')}"
                )
        else:
            console.print(f"[red]Unknown command: {cmd}[/red]. Type 'help' for available commands.")


def _print_devices(discovery: DiscoveryOrchestrator) -> None:
    devices = discovery.get_all_devices()
    if not devices:
        console.print("[yellow]No devices discovered yet.[/yellow]")
        return

    table = Table(title="Discovered Devices")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type", style="green")
    table.add_column("Adapter")
    table.add_column("Room")
    table.add_column("Online", style="bold")

    for d in devices:
        table.add_row(d.device_id, d.name, d.type, d.adapter, d.room or "-", "✓" if d.online else "✗")

    console.print(table)
