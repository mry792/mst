from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto, unique

from pygit2 import Commit, Oid
from pygit2.repository import Repository


class GitError(RuntimeError):
    pass


class UnexpectedParentsError(GitError):
    def __init__(self):
        super().__init__("Found unexpected parents.")


class ReferenceNotFoundError(GitError):
    def __init__(self, name: str):
        super().__init__(f"No reference '{name}'.")


class GraftedError(GitError):
    def __init__(self, oid: Oid):
        super().__init__(f"Commit is grafted: {oid.hex}")


class CycleError(GitError):
    def __init__(self, commit: Commit):
        super().__init__(f"Commit cycle found at {commit}.")


def find_commit_for_ref(repo: Repository, name: str) -> Commit:
    ref = repo.lookup_reference(name)
    if ref is None:
        raise ReferenceNotFoundError(name)
    return ref.peel(Commit)


def is_grafted(commit: Commit) -> bool:
    expected_parent_ids: set[Oid] = set()
    for line in commit.read_raw().decode().splitlines():
        tokens = line.split()
        if tokens and tokens[0] == "parent":
            expected_parent_ids.add(Oid(hex=tokens[1]))

    found_parent_ids = set(commit.parent_ids)
    if len(found_parent_ids - expected_parent_ids) > 0:
        raise UnexpectedParentsError()

    return len(expected_parent_ids - found_parent_ids) > 0


@unique
class VisitStatus(Enum):
    NOT_VISITED = auto()
    VISITING = auto()
    VISITED = auto()


@dataclass
class DfsActions:
    pre_visit: Callable[[Commit], bool] | None = None
    post_visit: Callable[[Commit], None] | None = None


def _dfs_visit_commit(
    current: Commit,
    commit_visits: dict[Oid, VisitStatus],
    actions: DfsActions,
):
    current_status = commit_visits.get(current.id, VisitStatus.NOT_VISITED)

    if current_status == VisitStatus.VISITED:
        # Might be the case if we have a split then a merge.
        return

    if current_status == VisitStatus.VISITING:
        raise CycleError(current)

    if actions.pre_visit and not actions.pre_visit(current):
        return

    commit_visits[current.id] = VisitStatus.VISITING
    for parent in current.parents:
        _dfs_visit_commit(parent, commit_visits, actions)

    commit_visits[current.id] = VisitStatus.VISITED
    if actions.post_visit:
        actions.post_visit(current)


def dfs(start: Commit, actions: DfsActions):
    _dfs_visit_commit(start, {}, actions)
