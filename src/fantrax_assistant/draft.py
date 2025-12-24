"""Main draft assistant CLI."""

from typing import Annotated
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box

from .colors import COLORS
from .config import DraftConfig
from .draft_state import DraftState
from .suggest import PlayerRecommendationEngine

console = Console()
app = typer.Typer(help="Fantrax Draft Assistant")

def get_position_color(pos: str) -> str:
    """Get color for position."""
    if pos.startswith('G'):
        return COLORS['gk']
    elif pos.startswith('D'):
        return COLORS['defender']
    elif pos.startswith('M'):
        return COLORS['midfielder']
    elif pos.startswith('F'):
        return COLORS['forward']
    return 'white'


def get_score_color(score: float) -> str:
    """Get color based on score."""
    if score > 75:
        return COLORS['high_score']
    elif score > 60:
        return COLORS['mid_score']
    return COLORS['low_score']

def get_position_need_color(current: int, max_allowed: int) -> str:
    """Get color based on same logic as calculate_position_need()."""
    if current >= max_allowed:
        return COLORS['need_full']
    elif current == 0:
        return COLORS['need_critical']
    else:
        return COLORS['need_moderate']

# Completion callbacks
def complete_teams() -> list[str]:
    """Complete team names."""
    state = DraftState()
    return list(state.teams.keys())

def complete_positions() -> list[str]:
    """Complete positions."""
    return ['G', 'D', 'M', 'F']


def complete_clubs() -> list[str]:
    """Complete club names."""
    config = DraftConfig()
    if config.load_all_data():
        clubs = {p.get('team', '') for p in config.rankings.get('rankings', [])}
        return sorted(list(clubs))
    return []


@app.command()
def suggest(
    num_suggestions: Annotated[int, typer.Argument(help="Number of suggestions")] = 10,
    team: Annotated[str, typer.Option(
        "--team", "-t",
        help="Team to get suggestions for"
    )] = "Team 1",
    ignore_position: Annotated[str | None, typer.Option(
        "--ignore-position", "-i",
        help="Ignore positions (comma-separated: G,D,M,F)"
    )] = None,
    exclude_team: Annotated[str | None, typer.Option(
        "--exclude-team", "-x",
        help="Exclude players from this club (e.g., MCI, ARS)"
    )] = None,
    breakdown: Annotated[bool, typer.Option(
        "--breakdown", "-b",
        help="Show detailed score breakdown"
    )] = False,
):
    """Get player recommendations."""
    config = DraftConfig()
    state = DraftState()

    console.print(f"\n[{COLORS['header']}]🎯 Top {num_suggestions} Recommendations[/{COLORS['header']}]\n")

    if exclude_team:
        console.print(f"[{COLORS['warning']}]⛔ Excluding club:[/{COLORS['warning']}] [bold]{exclude_team.upper()}[/bold]")

    if ignore_position:
        ignore_positions = [p.strip().upper() for p in ignore_position.split(',')]
        console.print(f"[{COLORS['warning']}]🚫 Ignoring positions:[/{COLORS['warning']}] [bold]{', '.join(ignore_positions)}[/bold]\n")

    with console.status(f"[{COLORS['info']}]Calculating...[/{COLORS['info']}]"):
        if not config.load_all_data():
            console.print(f"[{COLORS['error']}]✗ Failed to load data[/{COLORS['error']}]")
            return

    team_roster = state.get_team(team)
    engine = PlayerRecommendationEngine(config, team_roster, state.drafted_players)
    recs = engine.get_recommendations(1, num_suggestions, exclude_team=exclude_team, ignore_position=ignore_position)

    if breakdown:
        # Detailed breakdown view
        for i, rec in enumerate(recs, 1):
            pos_color = get_position_color(rec['position'])
            console.print(f"\n[bold {COLORS['header']}]{i}. {rec['player']}[/bold {COLORS['header']}] ([{pos_color}]{rec['position']}[/{pos_color}]) - {rec['team']}")
            console.print(f"   ADP: {rec.get('adp', 0):.1f} | FP/G: {rec.get('fpg', 0):.2f}")

            breakdown_data = engine.get_score_breakdown(rec, 1)

            breakdown_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), border_style=COLORS['border'])
            breakdown_table.add_column("Component", style="dim")
            breakdown_table.add_column("Score", justify="right", style="white")
            breakdown_table.add_column("Weight", justify="right", style="dim")

            breakdown_table.add_row("Base (Fantrax Points)", f"[{COLORS['info']}]{breakdown_data['base_value']:.2f}[/{COLORS['info']}]", "30%")
            breakdown_table.add_row("ADP Value", f"[{COLORS['info']}]{breakdown_data['adp_value']:.2f}[/{COLORS['info']}]", "15%")
            breakdown_table.add_row("Recent Form", f"[{COLORS['info']}]{breakdown_data['form_value']:.2f}[/{COLORS['info']}]", "20%")
            breakdown_table.add_row("Health/Availability", f"[{COLORS['info']}]{breakdown_data['injury_penalty']:.2f}[/{COLORS['info']}]", "15%")
            breakdown_table.add_row("Position Need", f"[{COLORS['info']}]{breakdown_data['position_need']:.2f}[/{COLORS['info']}]", "10%")
            breakdown_table.add_row("Position Scarcity", f"[{COLORS['info']}]{breakdown_data['scarcity']:.2f}[/{COLORS['info']}]", "5%")
            breakdown_table.add_row("Positional Value", f"[{COLORS['info']}]{breakdown_data['positional_value']:.2f}[/{COLORS['info']}]", "5%")
            breakdown_table.add_row("[bold]TOTAL[/bold]", f"[bold {COLORS['high_score']}]{breakdown_data['total']:.2f}[/bold {COLORS['high_score']}]", "")

            console.print(breakdown_table)

            injury = rec.get('injury', {})
            afcon = config.get_player_afcon_status(rec['player'])

            if afcon.get('at_afcon'):
                console.print(f"   [{COLORS['warning']}]⚠ At AFCON (until Jan 18)[/{COLORS['warning']}]")
            elif injury.get('severity') != 'Healthy':
                console.print(f"   [{COLORS['warning']}]⚠ Injury: {injury.get('severity')}[/{COLORS['warning']}]")
    else:
        # Standard table view
        table = Table(
            title=Text("Player Recommendations", style=COLORS['header']),
            box=box.ROUNDED,
            border_style=COLORS['border']
        )

        table.add_column("#", style="cyan", width=3)
        table.add_column("Player", style="bold white", width=20)
        table.add_column("Pos", width=5)
        table.add_column("Team", style="yellow", width=12)
        table.add_column("ADP", justify="right", style=COLORS['info'], width=6)
        table.add_column("FP/G", justify="right", style="bright_green", width=6)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Status", width=15)

        for i, rec in enumerate(recs, 1):
            injury = rec.get('injury', {})
            afcon = config.get_player_afcon_status(rec['player'])
            pos_color = get_position_color(rec['position'])
            score = rec['recommendation_score']
            score_color = get_score_color(score)

            if afcon.get('at_afcon'):
                status = f"[{COLORS['warning']}]⚠️ AFCON[/{COLORS['warning']}]"
            elif injury.get('severity') == 'Healthy':
                status = f"[{COLORS['success']}]✅[/{COLORS['success']}]"
            else:
                status = f"[{COLORS['warning']}]🔨 {injury.get('severity')}[/{COLORS['warning']}]"

            table.add_row(
                str(i),
                rec['player'],
                f"[{pos_color}]{rec['position']}[/{pos_color}]",
                rec['team'],
                f"{rec.get('adp', 0):.1f}",
                f"{rec.get('fpg', 0):.2f}",
                f"[{score_color}]{score:.0f}[/{score_color}]",
                status
            )

        console.print(table)
        console.print(f"\n[{COLORS['muted']}]Tip: Use --breakdown flag to see detailed scoring breakdown[/{COLORS['muted']}]")


@app.command()
def pick(
    player_name: str,
    team: Annotated[str | None, typer.Option("--team", "-t", help="Team to add player to (defaults to your team)")] = None,
):
    """Add player to your team."""
    config = DraftConfig()
    state = DraftState()

    team_name = team or state.my_team

    with console.status(f"[{COLORS['info']}]Loading...[/{COLORS['info']}]"):
        if not config.load_all_data():
            return

    player_adp = config.get_player_adp(player_name)

    if not player_adp:
        console.print(f"[{COLORS['error']}]✗[/{COLORS['error']}] Player not found")
        return

    # Check the return value of add_to_team()
    if state.add_to_team(player_adp, team_name):
        console.print(f"[{COLORS['success']}]✓[/{COLORS['success']}] Added [bold]{player_adp['player']}[/bold] to [{COLORS['info']}]{team_name}[/{COLORS['info']}]")
        my_team = state.get_team(team_name)
        _display_position_breakdown(config, my_team)


@app.command()
def drafted(player_name: str):
    """Mark player as drafted by opponent."""
    config = DraftConfig()
    state = DraftState()

    if not config.load_all_data():
        console.print(f"[{COLORS['error']}]✗ Failed to load data[/{COLORS['error']}]")
        return

    player_adp = config.get_player_adp(player_name)

    if not player_adp:
        console.print(f"[{COLORS['error']}]✗[/{COLORS['error']}] Player not found")
        return

    exact_name = player_adp['player']
    state.mark_drafted(exact_name)
    console.print(f"[{COLORS['success']}]✓[/{COLORS['success']}] Marked [bold]{exact_name}[/bold] as drafted")


@app.command()
def show_team(
    team: Annotated[str, typer.Option(
        "--team", "-t",
        help="Team name to view"
    )] = "Team 1",
):
    """Show a team's roster."""
    config = DraftConfig()
    state = DraftState()

    team_name = team or state.my_team
    team_roster = state.get_team(team_name)

    if not team_roster:
        console.print(f"[{COLORS['warning']}]📭 No players on {team_name} yet[/{COLORS['warning']}]")
        return

    table = Table(
        title=Text(team_name, style=COLORS['header']),
        box=box.ROUNDED,
        border_style=COLORS['border'],
        header_style=COLORS['header']
    )

    table.add_column("#", width=3, style="cyan")
    table.add_column("Player", style="bold white")
    table.add_column("Position", width=8)
    table.add_column("Team", width=12)
    table.add_column("ADP", justify="right", width=6)

    for i, player in enumerate(team_roster, 1):
        pos_color = get_position_color(player['position'])
        table.add_row(
            str(i),
            player['player'],
            f"[{pos_color}]{player['position']}[/{pos_color}]",
            player['team'],
            f"{player['adp']:.1f}"
        )

    console.print(table)

    if config.load_all_data() and config.league_config:
        roster_rules = config.league_config['roster_rules']

        breakdown = Table(
            title=Text("Position Breakdown", style=COLORS['header']),
            box=box.SIMPLE,
            border_style=COLORS['border'],
            header_style=COLORS['header']
        )
        breakdown.add_column("Position", style=COLORS['header'])
        breakdown.add_column("Current", justify="right", style=COLORS['header'])
        breakdown.add_column("Max", justify="right", style=COLORS['header'])
        breakdown.add_column("Need", justify="right", style=COLORS['header'])


        for pos, max_count in roster_rules.items():
            current = sum(1 for p in team_roster if pos in p.get('position', ''))
            need = max_count - current

            need_color = get_position_need_color(current, max_count)

            if need == 0:
                need_str = f"[Full[/{need_color}]"
            elif need == max_count:
                need_str = f"[{need_color}]! {need}[/{need_color}]"
            else:
                need_str = f"[{need_color}]• {need}[/{need_color}]"

            breakdown.add_row(pos, str(current), str(max_count), need_str)
        console.print("\n", breakdown)



@app.command()
def reset():
    """Reset draft state."""
    if Confirm.ask("[bold]Reset everything?[/bold]", default=False):
        state = DraftState()
        state.reset()
        console.print(f"[{COLORS['success']}]✓[/{COLORS['success']}] Reset complete")


@app.command()
def init(
    teams: Annotated[str, typer.Option(
        "--teams", "-t",
        help='Comma-separated team names (e.g., "Sam,Scott,Hayden")'
    )] = "My Team",
):
    """Initialize draft with specified teams."""
    state = DraftState()

    team_list = [t.strip() for t in teams.split(',')]
    state.teams = {team: [] for team in team_list}
    state.drafted_players = set()
    state.save()

    console.print(f"[{COLORS['success']}]✓[/{COLORS['success']}] Draft initialized with {len(team_list)} teams:\n")

    for team_name in state.teams.keys():
        console.print(f"  [{COLORS['info']}]{team_name}[/{COLORS['info']}]")


# Helper functions

def _display_position_breakdown(config: DraftConfig, my_team: list):
    """Display position breakdown table."""
    if not config.league_config:
        return

    roster_rules = config.league_config.get('roster_rules', {})

    breakdown = Table(
        title=f"[{COLORS['header']}]Position Breakdown[/{COLORS['header']}]",
        box=box.SIMPLE,
        border_style=COLORS['border']
    )
    breakdown.add_column("Position", style=COLORS['header'])
    breakdown.add_column("Current", justify="right", style=COLORS['header'])
    breakdown.add_column("Max", justify="right", style=COLORS['header'])
    breakdown.add_column("Need", justify="right", style=COLORS['header'])


    for pos, max_count in roster_rules.items():
        current = sum(1 for p in my_team if pos in p.get('position', ''))
        need = max_count - current

        # Get color based on need urgency
        need_color = get_position_need_color(current, max_count)

        # Format the need column
        if need == 0:
            need_str = f"[{need_color}]✓ Full[/{need_color}]"
        elif need == max_count:
            need_str = f"[{need_color}]!!! {need}[/{need_color}]"
        else:
            need_str = f"[{need_color}]• {need}[/{need_color}]"

        breakdown.add_row(pos, str(current), str(max_count), need_str)

    console.print("\n", breakdown)


def _display_player_details(config: DraftConfig, player_adp: dict):
    """Display detailed information for a single player."""
    from .draft_state import DraftState
    from .suggest import PlayerRecommendationEngine

    player_name = player_adp['player']

    stats = config.get_player_stats(player_name)
    injury = config.get_player_injury(player_name)
    afcon = config.get_player_afcon_status(player_name)

    state = DraftState()
    engine = PlayerRecommendationEngine(config, [], state.drafted_players)
    pos_rank = engine.get_positional_rank(player_name)

    pos_name = player_adp.get('position', '')
    pos_color = get_position_color(pos_name)
    pos_labels = {'G': 'Goalkeeper', 'D': 'Defender', 'M': 'Midfielder', 'F': 'Forward'}
    pos_label = pos_labels.get(pos_name, pos_name)

    rank_str = f"#{pos_rank} {pos_label}"

    header = Panel(
        f"[bold white]{player_name}[/bold white]\n"
        f"[{pos_color}]{player_adp['position']}[/{pos_color}] • [{COLORS['info']}]{player_adp['team']}[/{COLORS['info']}]\n"
        f"[{COLORS['highlight']}]{rank_str}[/{COLORS['highlight']}]",
        title="Player Info",
        border_style=pos_color,
        box=box.ROUNDED
    )
    console.print(header)

    # ADP Table
    adp_table = Table(
        title="Draft Information",
        box=box.SIMPLE,
        show_header=False,
        border_style=COLORS['border']
    )
    adp_table.add_column("Metric", style=COLORS['info'])
    adp_table.add_column("Value", style="white")

    adp_table.add_row("ADP", f"{player_adp.get('adp', 'N/A'):.1f}")
    adp_table.add_row("Overall Rank", str(player_adp.get('rank', 'N/A')))

    if 'fpts' in player_adp:
        adp_table.add_row("Fantasy Points (Season)", f"[bright_green]{player_adp['fpts']:.1f}[/bright_green]")
    if 'fpg' in player_adp:
        adp_table.add_row("Fantasy Points/Game", f"[bright_green]{player_adp['fpg']:.2f}[/bright_green]")

    console.print(adp_table)
    console.print()

    # Stats Table
    if stats:
        stats_table = Table(
            title="2024-25 Season Stats",
            box=box.SIMPLE,
            border_style=COLORS['border']
        )
        stats_table.add_column("Stat", style=COLORS['info'])
        stats_table.add_column("Value", justify="right", style="white")

        stats_table.add_row("Matches Played", str(stats.get('matches_played', 0)))
        stats_table.add_row("Starts", str(stats.get('starts', 0)))
        stats_table.add_row("Minutes", str(stats.get('minutes', 0)))
        stats_table.add_row("Goals", f"[bright_green]{stats.get('goals', 0)}[/bright_green]")
        stats_table.add_row("Assists", f"[bright_green]{stats.get('assists', 0)}[/bright_green]")

        if stats.get('yellow_cards', 0) > 0:
            stats_table.add_row("Yellow Cards", f"[yellow]{stats['yellow_cards']}[/yellow]")
        if stats.get('red_cards', 0) > 0:
            stats_table.add_row("Red Cards", f"[red]{stats['red_cards']}[/red]")

        console.print(stats_table)
        console.print()

    # Score Breakdown
    enriched_player = player_adp.copy()
    enriched_player['stats'] = stats
    enriched_player['injury'] = injury

    breakdown = engine.get_score_breakdown(enriched_player, 1)

    breakdown_table = Table(
        title="Score Breakdown",
        box=box.SIMPLE,
        show_header=True,
        border_style=COLORS['border']
    )
    breakdown_table.add_column("Component", style=COLORS['info'])
    breakdown_table.add_column("Calculation", style=COLORS['muted'])
    breakdown_table.add_column("Score", justify="right", style="white")

    breakdown_table.add_row(
        "Base Value (Fantrax Points)",
        f"{breakdown['base_fpg']:.1f} FP/G × {breakdown['base_position_weight']:.1f} (pos weight) × 0.30",
        f"[{COLORS['info']}]{breakdown['base_value']:.2f}[/{COLORS['info']}]"
    )

    if breakdown['club_bonus'] > 0:
        breakdown_table.add_row("Club Bonus (Non-Top 8)", "Goals ≥ 5", f"[{COLORS['info']}]{breakdown['club_bonus']:.2f}[/{COLORS['info']}]")

    breakdown_table.add_row(
        "ADP Value",
        f"100 - ({breakdown['adp_value_raw']} ÷ 2) = {breakdown['adp_normalized']:.1f} × 0.15",
        f"[{COLORS['info']}]{breakdown['adp_value']:.2f}[/{COLORS['info']}]"
    )

    breakdown_table.add_row("Recent Form", f"{breakdown['form_matches']} matches × 0.20", f"[{COLORS['info']}]{breakdown['form_value']:.2f}[/{COLORS['info']}]")
    breakdown_table.add_row("Health/Availability", f"{breakdown['injury_status']} (× {breakdown['injury_multiplier']}) × 15", f"[{COLORS['info']}]{breakdown['injury_penalty']:.2f}[/{COLORS['info']}]")
    breakdown_table.add_row("Position Need", "Roster depth check", f"[{COLORS['info']}]{breakdown['position_need']:.2f}[/{COLORS['info']}]")
    breakdown_table.add_row("Position Scarcity", "Drop-off vs next tier", f"[{COLORS['info']}]{breakdown['scarcity']:.2f}[/{COLORS['info']}]")
    breakdown_table.add_row("Positional Value", "Points vs position avg", f"[{COLORS['info']}]{breakdown['positional_value']:.2f}[/{COLORS['info']}]")
    breakdown_table.add_row("[bold]TOTAL SCORE[/bold]", "", f"[bold {COLORS['high_score']}]{breakdown['total']:.2f}[/bold {COLORS['high_score']}]")

    console.print(breakdown_table)
    console.print()

    # Injury Status
    injury_severity = injury.get('severity', 'Unknown')

    if injury_severity == 'Healthy':
        injury_panel = Panel(
            f"[{COLORS['success']}]✓ Healthy[/{COLORS['success']}]",
            title="Injury Status",
            border_style=COLORS['success'],
            box=box.ROUNDED
        )
    elif injury_severity in ['Questionable', 'Doubtful']:
        injury_panel = Panel(
            f"[{COLORS['warning']}]⚠ {injury_severity}[/{COLORS['warning']}]\nType: {injury.get('injury_type', 'Unknown')}\nReturn: {injury.get('return_date', 'TBD')}",
            title="Injury Status",
            border_style=COLORS['warning'],
            box=box.ROUNDED
        )
    else:
        injury_panel = Panel(
            f"[{COLORS['error']}]✗ {injury_severity}[/{COLORS['error']}]\nType: {injury.get('injury_type', 'Unknown')}\nReturn: {injury.get('return_date', 'TBD')}",
            title="Injury Status",
            border_style=COLORS['error'],
            box=box.ROUNDED
        )

    console.print(injury_panel)

    # AFCON Status
    if afcon.get('at_afcon'):
        afcon_panel = Panel(
            f"[{COLORS['warning']}]⚠ At AFCON 2025[/{COLORS['warning']}]\nCountry: {afcon.get('country', 'Unknown')}\nUnavailable: {afcon.get('start_date')} to {afcon.get('end_date')}\n[{COLORS['error']}]Will miss ~4-6 gameweeks[/{COLORS['error']}]",
            title="AFCON Status",
            border_style=COLORS['warning'],
            box=box.ROUNDED
        )
        console.print(afcon_panel)


if __name__ == "__main__":
    app()
