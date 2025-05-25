from dataclasses import dataclass
from pathlib import Path
from typing import NewType

from pygit2 import Commit

HostCommit = NewType("HostCommit", Commit)
SubtreeCommit = NewType("SubtreeCommit", Commit)


NOTES_BRANCH_NAME = "refs/notes/mst"


@dataclass(frozen=True)
class ProjectMetadata:
    name: str
    prefix: Path
    remote: Path
