from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto, unique

from pygit2 import Commit, Oid


@unique
class VisitStatus(Enum):
    NOT_VISITED = auto()
    VISITING = auto()
    VISITED = auto()


@dataclass
class DfsActions:
    should_visit: Callable[[Commit], bool] | None = None
    post_visit: Callable[[Commit], None] | None = None


def _dfs_visit_commit(
    current: Commit, commit_visits: dict[Oid, VisitStatus], actions: DfsActions
):
    current_status = commit_visits.get(current.id, VisitStatus.NOT_VISITED)
    if current_status == VisitStatus.VISITED:
        return
    if current_status == VisitStatus.VISITING:
        raise RuntimeError(f"cycle at {current}")

    if actions.should_visit and not actions.should_visit(current):
        return

    commit_visits[current.id] = VisitStatus.VISITING
    for parent in current.parents:
        _dfs_visit_commit(parent, commit_visits, actions)

    commit_visits[current.id] = VisitStatus.VISITED
    if actions.post_visit:
        actions.post_visit(current)


def dfs(start: Commit, actions: DfsActions):
    _dfs_visit_commit(start, {}, actions)
