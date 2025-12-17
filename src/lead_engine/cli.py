"""CLI interface for Lead Signal Engine."""

import sys
from pathlib import Path

import click
import structlog
from dotenv import load_dotenv

from .orchestrator import Orchestrator

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Lead Signal Engine - SERP-driven lead discovery and classification."""
    pass


@main.command()
@click.option(
    "--source",
    type=click.Choice(["hiring", "launch", "funding", "ecosystem"], case_sensitive=False),
    help="Run discovery for a specific source type",
)
@click.option("--all", "run_all", is_flag=True, help="Run discovery for all source types")
@click.option("--config-dir", type=click.Path(exists=True), default="config", help="Config directory path")
@click.option("--dry-run", is_flag=True, help="Dry run mode (no database writes)")
def run(source: str, run_all: bool, config_dir: str, dry_run: bool):
    """Run the lead discovery pipeline."""
    log = logger.bind(correlation_id=f"run_{source or 'all'}")
    log.info("Starting lead discovery pipeline", source=source, run_all=run_all, dry_run=dry_run)

    try:
        config_path = Path(config_dir)
        if not config_path.exists():
            log.error("Config directory not found", config_dir=config_dir)
            sys.exit(1)

        orchestrator = Orchestrator(config_path=config_path, dry_run=dry_run)
        
        if run_all:
            orchestrator.run_all()
        elif source:
            orchestrator.run_source(source_type=source)
        else:
            log.error("Must specify --source or --all")
            click.echo("Error: Must specify --source or --all")
            sys.exit(1)

        log.info("Pipeline completed successfully")
    except Exception as e:
        log.error("Pipeline failed", error=str(e), exc_info=True)
        sys.exit(1)


@main.command()
@click.option("--config-dir", type=click.Path(exists=True), default="config", help="Config directory path")
def export(config_dir: str):
    """Export leads to CSV files."""
    log = logger.bind(correlation_id="export")
    log.info("Exporting leads to CSV")

    try:
        config_path = Path(config_dir)
        orchestrator = Orchestrator(config_path=config_path)
        orchestrator.export_leads()
        
        log.info("Export completed successfully")
    except Exception as e:
        log.error("Export failed", error=str(e), exc_info=True)
        sys.exit(1)


@main.command()
def status():
    """Show system status and metrics."""
    click.echo("Status command - TODO: Implement metrics display")


if __name__ == "__main__":
    main()

