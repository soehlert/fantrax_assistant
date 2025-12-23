"""Player search functionality for draft assistant."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

from .config import DraftConfig

console = Console()


def find_all_matches(config: DraftConfig, search_name: str) -> list[dict]:
    """Find all players matching the search name."""
    if not config.rankings or 'rankings' not in config.rankings:
        return []

    matches = []
    search_lower = search_name.lower().strip()

    for ranking in config.rankings['rankings']:
        player_name = ranking.get('player', '')
        player_lower = player_name.lower().strip()

        # Check if search term matches
        if (search_lower == player_lower or
            search_lower in player_lower or
            player_lower in search_lower):
            matches.append(ranking)

    return matches


def display_player_details(config: DraftConfig, player_adp: dict):
    """Display detailed information for a single player."""
    player_name = player_adp['player']

    # Get additional data
    stats = config.get_player_stats(player_name)
    injury = config.get_player_injury(player_name)

    # Create header panel
    header = Panel(
        f"[bold white]{player_name}[/bold white]\n"
        f"[cyan]{player_adp['position']}[/cyan] • [cyan]{player_adp['team']}[/cyan]",
        title="Player Info",
        border_style="cyan",
        box=box.ROUNDED
    )
    console.print(header)

    # ADP & Rankings Table
    adp_table = Table(title="Draft Information", box=box.SIMPLE, show_header=False)
    adp_table.add_column("Metric", style="cyan")
    adp_table.add_column("Value", style="white")

    adp_table.add_row("ADP (Average Draft Position)", f"{player_adp.get('adp', 'N/A'):.1f}")
    adp_table.add_row("Overall Rank", str(player_adp.get('rank', 'N/A')))

    if 'fpts' in player_adp:
        adp_table.add_row("Fantasy Points (Season)", f"{player_adp['fpts']:.1f}")
    if 'fpg' in player_adp:
        adp_table.add_row("Fantasy Points/Game", f"{player_adp['fpg']:.2f}")

    console.print(adp_table)

    # Current Season Stats Table
    if stats:
        stats_table = Table(title="2024-25 Season Stats", box=box.SIMPLE)
        stats_table.add_column("Stat", style="cyan")
        stats_table.add_column("Value", justify="right", style="white")

        stats_table.add_row("Matches Played", str(stats.get('matches_played', 0)))
        stats_table.add_row("Starts", str(stats.get('starts', 0)))
        stats_table.add_row("Minutes", str(stats.get('minutes', 0)))
        stats_table.add_row("Goals", str(stats.get('goals', 0)))
        stats_table.add_row("Assists", str(stats.get('assists', 0)))

        if stats.get('yellow_cards', 0) > 0:
            stats_table.add_row("Yellow Cards", f"[yellow]{stats['yellow_cards']}[/yellow]")
        if stats.get('red_cards', 0) > 0:
            stats_table.add_row("Red Cards", f"[red]{stats['red_cards']}[/red]")

        console.print(stats_table)
    else:
        console.print("[yellow]⚠ No current season stats available[/yellow]\n")

    # Injury Status
    injury_severity = injury.get('severity', 'Unknown')

    if injury_severity == 'Healthy':
        injury_panel = Panel(
            "[green]✓ Healthy - No injury concerns[/green]",
            title="Injury Status",
            border_style="green",
            box=box.ROUNDED
        )
    elif injury_severity in ['Questionable', 'Doubtful']:
        injury_panel = Panel(
            f"[yellow]⚠ {injury_severity}[/yellow]\n"
            f"Type: {injury.get('injury_type', 'Unknown')}\n"
            f"Return: {injury.get('return_date', 'TBD')}",
            title="Injury Status",
            border_style="yellow",
            box=box.ROUNDED
        )
    else:
        injury_panel = Panel(
            f"[red]✗ {injury_severity}[/red]\n"
            f"Type: {injury.get('injury_type', 'Unknown')}\n"
            f"Return: {injury.get('return_date', 'TBD')}",
            title="Injury Status",
            border_style="red",
            box=box.ROUNDED
        )

    console.print(injury_panel)

    afcon_status = config.get_player_afcon_status(player_name)

    if afcon_status.get('at_afcon'):
        afcon_panel = Panel(
            f"[yellow]⚠ At AFCON 2025[/yellow]\n"
            f"Country: {afcon_status.get('country', 'Unknown')}\n"
            f"Unavailable: {afcon_status.get('start_date')} to {afcon_status.get('end_date')}\n"
            f"[red]Will miss ~4-6 gameweeks[/red]",
            title="AFCON Status",
            border_style="yellow",
            box=box.ROUNDED
        )
        console.print(afcon_panel)



@click.command()
@click.argument('player_name')
def search(player_name: str):
    """
    Search for a player and display their information.

    PLAYER_NAME: Name of the player to search for
    """
    # Load config and data
    config = DraftConfig()

    console.print(f"\n[cyan]Searching for:[/cyan] {player_name}\n")

    with console.status("[bold cyan]Loading data..."):
        if not config.load_all_data():
            console.print("[red]Failed to load data. Please run scrapers first.[/red]")
            return

    # Find all matching players
    matches = find_all_matches(config, player_name)

    if not matches:
        console.print(f"[red]✗[/red] No players found matching '{player_name}'")
        return

    # If only one match, display it
    if len(matches) == 1:
        display_player_details(config, matches[0])
        return

    # Multiple matches - let user choose
    console.print(f"[yellow]Found {len(matches)} players matching '{player_name}':[/yellow]\n")

    selection_table = Table(box=box.SIMPLE, show_header=True)
    selection_table.add_column("#", style="cyan", width=3)
    selection_table.add_column("Player", style="white")
    selection_table.add_column("Position", style="cyan", width=8)
    selection_table.add_column("Team", style="white", width=15)
    selection_table.add_column("ADP", justify="right", style="white", width=6)

    for i, match in enumerate(matches, 1):
        selection_table.add_row(
            str(i),
            match['player'],
            match['position'],
            match['team'],
            f"{match['adp']:.1f}"
        )

    console.print(selection_table)
    console.print()

    # Prompt user to select
    try:
        choice = Prompt.ask(
            "Select a player",
            choices=[str(i) for i in range(1, len(matches) + 1)],
            default="1"
        )

        selected_index = int(choice) - 1
        console.print()
        display_player_details(config, matches[selected_index])

    except (ValueError, KeyboardInterrupt):
        console.print("\n[yellow]Search cancelled[/yellow]")


if __name__ == "__main__":
    search()
