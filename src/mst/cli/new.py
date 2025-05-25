import logging
from pathlib import Path

import click  # type: ignore (reportMissingImports)
from pygit2 import Oid
from pygit2.repository import Repository

from mst.st_actions import StNew, record_actions

logger = logging.getLogger(__name__)


@click.command
def new(
    repo: Repository,
    name: str,
    cid: Oid,
    prefix: Path,
    remote_name: str = "origin",
):
    """
    Note a new subtree project in the monorepo.

    usage:
        mst new [NAME] [COMMIT] [PREFIX]
    """

    record_actions(repo, name, {cid: StNew(prefix)}, remote_name)
