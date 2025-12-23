"""CLI for running individual scrapers."""

import click
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import stat_scraper, injury_scraper, adp_scraper, recent_form_scraper, fdr_scraper

console = Console()


@click.group()
def scrape_cli():
    """Scrape data from various sources for draft assistant."""
    pass


@scrape_cli.command()
def stats():
    """Scrape current season stats from Premier League API."""
    console.print("[bold cyan]Scraping Premier League Stats[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching data...", total=None)

        try:
            if stat_scraper.save_stats():
                progress.update(task, description="[green]✓ Stats saved[/green]")
                console.print("\n[green]Success![/green] Stats saved to data/current_stats.json")
            else:
                progress.update(task, description="[red]✗ Failed[/red]")
                console.print("\n[red]Failed to fetch stats[/red]")
        except Exception as e:
            progress.update(task, description=f"[red]✗ Error: {e}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")


@scrape_cli.command()
def injuries():
    """Scrape injury data from SportsGambler."""
    console.print("[bold cyan]Scraping Injuries[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching data...", total=None)

        try:
            if injury_scraper.save_injuries():
                progress.update(task, description="[green]✓ Injury data saved[/green]")
                console.print("\n[green]Success![/green] Injuries saved to data/injuries.json")
            else:
                progress.update(task, description="[red]✗ Failed[/red]")
                console.print("\n[red]Failed to scrape injuries[/red]")
        except Exception as e:
            progress.update(task, description=f"[red]✗ Error: {e}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")


@scrape_cli.command()
@click.option('--csv', '-c', 'csv_file',
              type=click.Path(exists=True),
              default='data/fantrax_export.csv',
              help='Path to Fantrax CSV export file')
def adp(csv_file):
    """Load ADP rankings from Fantrax CSV export."""
    console.print("[bold cyan]Loading Fantrax ADP Data[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading CSV...", total=None)

        try:
            if adp_scraper.save_rankings(csv_file):
                progress.update(task, description="[green]✓ Rankings saved[/green]")
                console.print("\n[green]Success![/green] Rankings saved to data/adp_rankings.json")
            else:
                progress.update(task, description="[red]✗ Failed[/red]")
                console.print("\n[red]Failed to load CSV[/red]")
        except Exception as e:
            progress.update(task, description=f"[red]✗ Error: {e}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")


@scrape_cli.command()
@click.option('--days', '-d', type=int, default=30,
              help='Number of days covered (30 or 60)')
def form(days):
    """Load recent form data from Fantrax CSV export."""
    # Construct the CSV path based on days parameter
    csv_file = f'data/fantrax_recent_{days}d.csv'

    console.print(f"[bold cyan]Loading {days}-Day Form Data[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading CSV...", total=None)

        try:
            if recent_form_scraper.save_recent_form(csv_file, days=days):
                progress.update(task, description="[green]✓ Form data saved[/green]")
                console.print("\n[green]Success![/green] Recent form saved to data/recent_form.json")
            else:
                progress.update(task, description="[red]✗ Failed[/red]")
                console.print("\n[red]Failed to load CSV[/red]")
        except Exception as e:
            progress.update(task, description=f"[red]✗ Error: {e}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")


@scrape_cli.command()
def fdr():
    """Scrape Fixture Difficulty Ratings from FPL API."""
    console.print("[bold cyan]Scraping FPL Fixture Difficulty Ratings[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching data...", total=None)

        try:
            if fdr_scraper.save_fdr():
                progress.update(task, description="[green]✓ FDR saved[/green]")
                console.print("\n[green]Success![/green] FDR saved to data/fdr.json")
            else:
                progress.update(task, description="[red]✗ Failed[/red]")
                console.print("\n[red]Failed to scrape FDR[/red]")
        except Exception as e:
            progress.update(task, description=f"[red]✗ Error: {e}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")


@scrape_cli.command()
def afcon():
    """Load AFCON 2025 call-ups (manual JSON file)."""
    console.print("[bold cyan]Checking AFCON Call-ups[/bold cyan]\n")

    afcon_file = Path('data/afcon_callups.json')

    if afcon_file.exists():
        console.print("[green]✓[/green] AFCON data found at data/afcon_callups.json")
    else:
        console.print("[yellow]⚠[/yellow] AFCON data not found")
        console.print("Please create data/afcon_callups.json manually")


@scrape_cli.command()
@click.option('--csv', '-c', 'csv_file',
              type=click.Path(exists=True),
              default='data/fantrax_export.csv',
              help='Path to Fantrax CSV export file')
def all(csv_file):
    """Run all data collection tasks."""
    console.print("[bold cyan]Running All Data Collection[/bold cyan]\n")

    scrapers = [
        ("Premier League Stats", lambda: stat_scraper.save_stats()),
        ("Injury Data", lambda: injury_scraper.save_injuries()),
        ("Fantrax ADP", lambda: adp_scraper.save_rankings(csv_file)),
        ("FPL Fixture Difficulty", lambda: fdr_scraper.save_fdr()),
    ]

    results = []

    for name, scraper_func in scrapers:
        console.print(f"\n[cyan]→[/cyan] {name}...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing...", total=None)

            try:
                success = scraper_func()
                results.append((name, success))

                if success:
                    progress.update(task, description="[green]✓ Complete[/green]")
                else:
                    progress.update(task, description="[red]✗ Failed[/red]")
            except Exception as e:
                results.append((name, False))
                progress.update(task, description=f"[red]✗ Error[/red]")
                console.print(f"  [red]Error:[/red] {e}")

    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]Summary[/bold]\n")

    success_count = sum(1 for _, success in results if success)

    for name, success in results:
        status = "[green]✓[/green]" if success else "[red]✗[/red]"
        console.print(f"{status} {name}")

    console.print(f"\n{success_count}/{len(results)} tasks succeeded")

    if success_count == len(results):
        console.print("\n[green]All data collected successfully![/green]")
    else:
        console.print("\n[yellow]Some tasks failed[/yellow]")

    # Check for optional data
    console.print("\n[dim]Optional data:[/dim]")

    form_file = Path('data/recent_form.json')
    if form_file.exists():
        console.print("[green]✓[/green] Recent form data available")
    else:
        console.print("[yellow]○[/yellow] Recent form data not loaded (run 'scrape form')")

    afcon_file = Path('data/afcon_callups.json')
    if afcon_file.exists():
        console.print("[green]✓[/green] AFCON data available")
    else:
        console.print("[yellow]○[/yellow] AFCON data not loaded")


if __name__ == "__main__":
    scrape_cli()
