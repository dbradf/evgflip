import json
import logging
from datetime import datetime, time, timedelta

import click
import structlog
from evergreen.api import CachedEvergreenApi

from evgflip.find_flips import find

LOGGER = structlog.get_logger(__name__)

DEFAULT_THREADS = 16
EXTERNAL_LIBRARIES = [
    "evergreen.api",
    "urllib3"
]


def _setup_logging(verbose: bool):
    """Setup logging configuration"""
    structlog.configure(logger_factory=structlog.stdlib.LoggerFactory())
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level)
    for external_lib in EXTERNAL_LIBRARIES:
        logging.getLogger(external_lib).setLevel(logging.WARNING)


@click.group()
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose logging.")
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['evg_api'] = CachedEvergreenApi.get_api(use_config_file=True)

    _setup_logging(verbose)


@cli.command()
@click.pass_context
@click.option("--project", type=str, required=True, help="Evergreen project to analyze.")
@click.option("--days-back", type=int, required=True, help="How far back to analyze.")
@click.option("--n-threads", type=int, default=DEFAULT_THREADS,
              help="Number of threads to execute with.")
def find_flips(ctx, project, days_back, n_threads):
    evg_api = ctx.obj['evg_api']
    start_date = datetime.combine(datetime.now() - timedelta(days=days_back), time())

    LOGGER.debug("calling find_flips", project=project, start_date=start_date, evg_api=evg_api)
    commits_flipped = find(project, start_date, evg_api, n_threads)

    print(json.dumps(commits_flipped, indent=4))


def main():
    """Entry point into commandline."""
    return cli(obj={})
