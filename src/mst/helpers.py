from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import NewType

from pygit2 import Commit, Oid
from pygit2.repository import Repository

logger = getLogger(__name__)


HostCommit = NewType("HostCommit", Commit)
HostOd = NewType("HostOd", Oid)
SubtreeCommit = NewType("SubtreeCommit", Commit)
SubtreeOid = NewType("SubtreeOid", Oid)


NOTES_BRANCH_NAME = "refs/notes/mst"
NOTES_REFSPEC = f"{NOTES_BRANCH_NAME}:{NOTES_BRANCH_NAME}"


@dataclass(frozen=True)
class ProjectMetadata:
    name: str
    prefix: Path
    remote: Path


def fetch_mst_notes(repo: Repository, remote_name: str = "origin"):
    logger.info(f'Fetching existing MST notes from remote "{remote_name}".')
    remote = repo.remotes[remote_name]
    remote.fetch([NOTES_REFSPEC], depth=1)  # TODO: Might fail?


def push_mst_notes(repo: Repository, remote_name: str = "origin"):
    logger.info(f'Pushing MST notes to remote "{remote_name}".')
    remote = repo.remotes[remote_name]
    remote.push([NOTES_REFSPEC])
