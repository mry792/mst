from dataclasses import dataclass
from pathlib import Path
from typing import NewType

from pygit2 import Commit

HostCommit = NewType("HostCommit", Commit)
SubtreeCommit = NewType("SubtreeCommit", Commit)


def make_notes_branch_name(project_name: str):
    return f"refs/notes/mst/{project_name}"


@dataclass(frozen=True)
class ProjectMetadata:
    name: str
    prefix: Path
    remote: Path
