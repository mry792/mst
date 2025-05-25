import logging
from pathlib import Path

import click  # type: ignore (reportMissingImports)
from pygit2 import Oid
from pygit2.repository import Repository

from mst.st_actions import StMove, record_actions

logger = logging.getLogger(__name__)


@click.command
def move(
    repo: Repository,
    name: str,
    cid: Oid,
    prefix: Path,
    remote_name: str = "origin",
):
    """
    Note the move subtree project in the monorepo.

    usage:
        mst move [NAME] [COMMIT] [NEW PREFIX]
    """

    record_actions(repo, name, {cid: StMove(prefix)}, remote_name)
