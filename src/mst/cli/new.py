import logging
from pathlib import Path

import click  # type: ignore
from pygit2 import Oid
from pygit2.repository import Repository

from mst.helpers import make_notes_branch_name
from mst.st_actions import StNew, serialize_st_action

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

    remote = repo.remotes[remote_name]
    notes_branch_name = make_notes_branch_name(name)
    notes_refspec = f"{notes_branch_name}:{notes_branch_name}"

    logger.debug(f'Checking for existing notes for project "{name}".')
    remote.fetch([notes_refspec], depth=1)  # TODO: Might fail?

    note_text = serialize_st_action(StNew(prefix))
    logger.debug(f'Adding note to "{cid.hex}":\n{note_text}')
    repo.create_note(
        note_text,
        author=repo.default_signature,
        committer=repo.default_signature,
        annotated_id=cid.hex,
        ref=notes_branch_name,
    )

    logger.info(f'Note created. Pushing to remote "{remote_name}".')
    remote.push([notes_refspec])
