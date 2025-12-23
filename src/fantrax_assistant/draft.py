"""Main draft assistant CLI."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box

from .config import DraftConfig
from .draft_state import DraftState
from .suggest import PlayerRecommendationEngine

console = Console()


@click.group()
def cli():
    """Fantrax Draft Assistant."""
    pass


@cli.command()
@click.argument('player_name')
def search(player_name: str):
    """Search for a player."""
    config = DraftConfig()

    console.print(f"\n[cyan]Searching for:[/cyan] {player_name}\n")

    with console.status("[bold cyan]Loading data..."):
        if not config.load_all_data():
            console.print("[red]Failed to load data[/red]")
            return

    matches = []
    search_lower = player_name.lower().strip()

    for ranking in config.rankings.get('rankings', []):
        player_lower = ranking.get('player', '').lower().strip()
        if search_lower in player_lower or player_lower in search_lower:
            matches.append(ranking)

    if not matches:
        console.print(f"[red]✗[/red] No players found")
        return

    if len(matches) > 1:
        console.print(f"[yellow]Found {len(matches)} players:[/yellow]\n")

        table = Table(box=box.SIMPLE)
        table.add_column("#", style="cyan", width=3)
        table.add_column("Player")
        table.add_column("Position", width=8)
        table.add_column("Team", width=15)
        table.add_column("ADP", justify="right", width=6)

        for i, match in enumerate(matches, 1):
            table.add_row(str(i), match['player'], match['position'],
                         match['team'], f"{match['adp']:.1f}")

        console.print(table)

        choice = Prompt.ask("Select", choices=[str(i) for i in range(1, len(matches) + 1)])
        selected = matches[int(choice) - 1]
    else:
        selected = matches[0]

    _display_player_details(config, selected)


@cli.command()
@click.argument('num_suggestions', type=int, default=10)
@click.option('--breakdown', '-b', is_flag=True, help='Show detailed score breakdown')
def suggest(num_suggestions: int, breakdown: bool):
    """Get player recommendations."""
    config = DraftConfig()
    state = DraftState()

    console.print(f"\n[cyan]Top {num_suggestions} Recommendations[/cyan]\n")

    with console.status("[bold cyan]Calculating..."):
        if not config.load_all_data():
            console.print("[red]Failed to load data[/red]")
            return

    engine = PlayerRecommendationEngine(config, state.my_team, state.drafted_players)
    recs = engine.get_recommendations(1, num_suggestions)

    if breakdown:
        # Detailed breakdown view
        for i, rec in enumerate(recs, 1):
            console.print(f"\n[bold cyan]{i}. {rec['player']}[/bold cyan] ({rec['position']}) - {rec['team']}")
            console.print(f"   ADP: {rec.get('adp', 0):.1f} | FP/G: {rec.get('fpg', 0):.2f}")

            # Get breakdown
            breakdown_data = engine.get_score_breakdown(rec, 1)

            # Create breakdown table
            breakdown_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            breakdown_table.add_column("Component", style="dim")
            breakdown_table.add_column("Score", justify="right", style="white")
            breakdown_table.add_column("Weight", justify="right", style="dim")

            breakdown_table.add_row("Base (Fantrax Points)", f"{breakdown_data['base_value']:.2f}", "30%")
            breakdown_table.add_row("ADP Value", f"{breakdown_data['adp_value']:.2f}", "15%")
            breakdown_table.add_row("Recent Form", f"{breakdown_data['form_value']:.2f}", "20%")
            breakdown_table.add_row("Health/Availability", f"{breakdown_data['injury_penalty']:.2f}", "15%")
            breakdown_table.add_row("Position Need", f"{breakdown_data['position_need']:.2f}", "10%")
            breakdown_table.add_row("Position Scarcity", f"{breakdown_data['scarcity']:.2f}", "5%")
            breakdown_table.add_row("Positional Value", f"{breakdown_data['positional_value']:.2f}", "5%")
            breakdown_table.add_row("[bold]TOTAL[/bold]", f"[bold green]{breakdown_data['total']:.2f}[/bold green]", "")

            console.print(breakdown_table)

            # Show injury/AFCON status
            injury = rec.get('injury', {})
            afcon = config.get_player_afcon_status(rec['player'])

            if afcon.get('at_afcon'):
                console.print(f"   [yellow]⚠ At AFCON (until Jan 18)[/yellow]")
            elif injury.get('severity') != 'Healthy':
                console.print(f"   [yellow]⚠ Injury: {injury.get('severity')}[/yellow]")
    else:
        # Standard table view
        table = Table(title="Player Recommendations", box=box.ROUNDED)
        table.add_column("#", width=3)
        table.add_column("Player", style="bold", width=20)
        table.add_column("Pos", width=5)
        table.add_column("Team", width=12)
        table.add_column("ADP", justify="right", width=6)
        table.add_column("FP/G", justify="right", width=6)
        table.add_column("Score", justify="right", width=7, style="bold green")
        table.add_column("Status", width=15)

        for i, rec in enumerate(recs, 1):
            injury = rec.get('injury', {})
            afcon = config.get_player_afcon_status(rec['player'])

            if afcon.get('at_afcon'):
                status = "[yellow]⚠ AFCON[/yellow]"
            elif injury.get('severity') == 'Healthy':
                status = "[green]✓[/green]"
            else:
                status = f"[yellow]{injury.get('severity')}[/yellow]"

            score = rec['recommendation_score']
            score_str = f"[green]{score}[/green]" if score > 70 else f"{score}"

            table.add_row(str(i), rec['player'], rec['position'], rec['team'],
                         f"{rec.get('adp', 0):.1f}", f"{rec.get('fpg', 0):.2f}",
                         score_str, status)

        console.print(table)
        console.print(f"\n[dim]Tip: Use --breakdown flag to see detailed scoring breakdown[/dim]")



@cli.command()
@click.argument('player_name')
def pick(player_name: str):
    """Add player to your team."""
    config = DraftConfig()
    state = DraftState()

    with console.status("[bold cyan]Loading..."):
        if not config.load_all_data():
            return

    player_adp = config.get_player_adp(player_name)

    if not player_adp:
        console.print(f"[red]✗[/red] Player not found")
        return

    state.add_to_my_team(player_adp)
    console.print(f"[green]✓[/green] Added [bold]{player_adp['player']}[/bold] to your team")

    my_team = state.my_team

    # Display updated position breakdown
    _display_position_breakdown(config, my_team)


@cli.command()
@click.argument('player_name')
def drafted(player_name: str):
    """Mark player as drafted by opponent."""
    config = DraftConfig()
    state = DraftState()

    # Load data and find exact player name for consistency
    if not config.load_all_data():
        console.print("[red]Failed to load data[/red]")
        return

    player_adp = config.get_player_adp(player_name)

    if not player_adp:
        console.print(f"[red]✗[/red] Player not found")
        return

    # Use the exact name from rankings to ensure consistency
    exact_name = player_adp['player']
    state.mark_drafted(exact_name)
    console.print(f"[green]✓[/green] Marked [bold]{exact_name}[/bold] as drafted")



@cli.command()
def team():
    """Show your team."""
    config = DraftConfig()
    state = DraftState()

    if not state.my_team:
        console.print("[yellow]No players yet[/yellow]")
        return

    table = Table(title="My Team", box=box.ROUNDED)
    table.add_column("#", width=3)
    table.add_column("Player", style="bold")
    table.add_column("Position")
    table.add_column("Team")
    table.add_column("ADP", justify="right")

    for i, player in enumerate(state.my_team, 1):
        table.add_row(str(i), player['player'], player['position'],
                     player['team'], f"{player['adp']:.1f}")

    console.print(table)

    # Position breakdown
    if config.load_all_data() and config.league_config:
        roster_rules = config.league_config['roster_rules']

        breakdown = Table(title="Position Breakdown", box=box.SIMPLE)
        breakdown.add_column("Position")
        breakdown.add_column("Current", justify="right")
        breakdown.add_column("Max", justify="right")
        breakdown.add_column("Need", justify="right")

        for pos, max_count in roster_rules.items():
            current = sum(1 for p in state.my_team if pos in p.get('position', ''))
            need = max_count - current
            need_str = "[green]✓[/green]" if need == 0 else str(need)
            breakdown.add_row(pos, str(current), str(max_count), need_str)

        console.print("\n", breakdown)


@cli.command()
def reset():
    """Reset draft state."""
    if Confirm.ask("Reset everything?", default=False):
        state = DraftState()
        state.reset()
        console.print("[green]✓[/green] Reset complete")


def _display_position_breakdown(config: DraftConfig, my_team: list):
    """Display position breakdown table."""
    if not config.league_config:
        return

    roster_rules = config.league_config.get('roster_rules', {})

    breakdown = Table(title="Position Breakdown", box=box.SIMPLE)
    breakdown.add_column("Position")
    breakdown.add_column("Current", justify="right")
    breakdown.add_column("Max", justify="right")
    breakdown.add_column("Need", justify="right")

    for pos, max_count in roster_rules.items():
        current = sum(1 for p in my_team if pos in p.get('position', ''))
        need = max_count - current
        need_str = "[green]✓[/green]" if need == 0 else str(need)
        breakdown.add_row(pos, str(current), str(max_count), need_str)

    console.print("\n", breakdown)

def _display_player_details(config: DraftConfig, player_adp: dict):
    """Display detailed information for a single player including draft value breakdown."""
    from .draft_state import DraftState
    from .suggest import PlayerRecommendationEngine

    player_name = player_adp['player']

    # Get player data
    stats = config.get_player_stats(player_name)
    injury = config.get_player_injury(player_name)
    afcon = config.get_player_afcon_status(player_name)

    # Get positional rank
    state = DraftState()
    engine = PlayerRecommendationEngine(config, state.my_team, state.drafted_players)
    pos_rank = engine.get_positional_rank(player_name)

    # Create header panel with positional rank
    pos_name = player_adp.get('position', '')
    pos_labels = {'G': 'Goalkeeper', 'D': 'Defender', 'M': 'Midfielder', 'F': 'Forward'}
    pos_label = pos_labels.get(pos_name, pos_name)

    rank_str = f"#{pos_rank} {pos_label}"

    header = Panel(
        f"[bold white]{player_name}[/bold white]\n"
        f"[cyan]{player_adp['position']}[/cyan] • [cyan]{player_adp['team']}[/cyan]\n"
        f"[green]{rank_str}[/green]",
        title="Player Info",
        border_style="cyan",
        box=box.ROUNDED
    )
    console.print(header)

    # ADP & Rankings Table
    adp_table = Table(title="Draft Information", box=box.SIMPLE, show_header=False)
    adp_table.add_column("Metric", style="cyan")
    adp_table.add_column("Value", style="white")

    adp_table.add_row("ADP", f"{player_adp.get('adp', 'N/A'):.1f}")
    adp_table.add_row("Overall Rank", str(player_adp.get('rank', 'N/A')))

    if 'fpts' in player_adp:
        adp_table.add_row("Fantasy Points (Season)", f"{player_adp['fpts']:.1f}")
    if 'fpg' in player_adp:
        adp_table.add_row("Fantasy Points/Game", f"{player_adp['fpg']:.2f}")

    console.print(adp_table)
    console.print()

    # Current Season Stats
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
        console.print()

    # Calculate draft value breakdown
    enriched_player = player_adp.copy()
    enriched_player['stats'] = stats
    enriched_player['injury'] = injury

    breakdown = engine.get_score_breakdown(enriched_player, 1)

    breakdown_table = Table(title="Score Breakdown", box=box.SIMPLE, show_header=True)
    breakdown_table.add_column("Component", style="cyan")
    breakdown_table.add_column("Calculation", style="dim")
    breakdown_table.add_column("Score", justify="right", style="white")

    breakdown_table.add_row(
        "Base Value (Fantrax Points)",
        f"{breakdown['base_fpg']:.1f} FP/G × {breakdown['base_position_weight']:.1f} (pos weight) × 0.30",
        f"{breakdown['base_value']:.2f}"
    )

    if breakdown['club_bonus'] > 0:
        breakdown_table.add_row(
            "Club Bonus (Non-Top 8)",
            "Goals ≥ 5",
            f"{breakdown['club_bonus']:.2f}"
        )

    breakdown_table.add_row(
        "ADP Value",
        f"100 - ({breakdown['adp_value_raw']} ÷ 2) = {breakdown['adp_normalized']:.1f} × 0.15",
        f"{breakdown['adp_value']:.2f}"
    )

    breakdown_table.add_row(
        "Recent Form",
        f"{breakdown['form_matches']} matches × 0.20",
        f"{breakdown['form_value']:.2f}"
    )

    breakdown_table.add_row(
        "Health/Availability",
        f"{breakdown['injury_status']} (× {breakdown['injury_multiplier']}) × 15",
        f"{breakdown['injury_penalty']:.2f}"
    )

    breakdown_table.add_row(
        "Position Need",
        "Roster depth check",
        f"{breakdown['position_need']:.2f}"
    )

    breakdown_table.add_row(
        "Position Scarcity",
        "Drop-off vs next tier",
        f"{breakdown['scarcity']:.2f}"
    )

    breakdown_table.add_row(
        "Positional Value",
        "Points vs position avg",
        f"{breakdown['positional_value']:.2f}"
    )

    breakdown_table.add_row(
        "[bold]TOTAL SCORE[/bold]",
        "",
        f"[bold green]{breakdown['total']:.2f}[/bold green]"
    )

    console.print(breakdown_table)
    console.print()

    # Injury Status
    injury_severity = injury.get('severity', 'Unknown')

    if injury_severity == 'Healthy':
        injury_panel = Panel(
            "[green]✓ Healthy[/green]",
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

    # AFCON Status
    if afcon.get('at_afcon'):
        afcon_panel = Panel(
            f"[yellow]⚠ At AFCON 2025[/yellow]\n"
            f"Country: {afcon.get('country', 'Unknown')}\n"
            f"Unavailable: {afcon.get('start_date')} to {afcon.get('end_date')}\n"
            f"[red]Will miss ~4-6 gameweeks[/red]",
            title="AFCON Status",
            border_style="yellow",
            box=box.ROUNDED
        )
        console.print(afcon_panel)


if __name__ == "__main__":
    cli()
