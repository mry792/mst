from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import singledispatchmethod
from pathlib import Path
from typing import TypeVar

from pygit2 import Commit
from pygit2.repository import Repository

from mst.helpers import HostCommit, HostOid, SubtreeCommit, SubtreeOid
from mst.st_actions import StAction, StCommitMapped, StExtract, StMove, StNew

T = TypeVar("T")


def stable_unique(items: Iterable[T]) -> list[T]:
    seen = set()
    return [item for item in items if not (item in seen or seen.add(item))]


class PrefixError(ValueError):
    def __init__(
        self,
        host_commit: HostCommit,
        parent_prefixes: set[Path],
        cmd: str,
    ):
        super().__init__(
            f'Cannot determine prefix for host commit "{host_commit.id.hex}". '
            "No prefix is recorded for this commit, and its parents do not "
            f"specify a unique prefix ({parent_prefixes}). Please explicitly "
            f"annotate this commit with a prefix using `msg {cmd}`.",
        )


@dataclass
class Extractor:
    repo: Repository
    mappings: dict[HostOid, StCommitMapped]
    actions: list[tuple[HostOid, StAction]]

    def _get_st_cid(self, host_commit: HostCommit) -> SubtreeOid:
        return self.mappings[HostOid(host_commit.id)].subtree_commit_id

    def _should_use_parent(
        self,
        candidate_parent: HostCommit,
        all_parents: Sequence[HostCommit],
    ) -> bool:
        # If the candidate parent is an ancestor of any other host parent, it's
        # assumed its use as a parent in a merge is intentional and should be
        # kept. (NOTE: If the subtree was not changed in the merge nor on any
        # incoming branches of the merge, the parents will map to the same
        # subtree parent commits and be deduplicated. This will result in no
        # new subtree commit.)
        if any(
            self.repo.descendant_of(other.id, candidate_parent.id)
            for other in all_parents
            if other != candidate_parent
        ):
            return True

        # If the candidate parent's subtree counterpart is an ancestor of any
        # other parent's subtree counterpart, it's assumed the branch exists
        # to change other subtrees and should be pruned from the subtree's
        # extracted history.
        if any(  # noqa: SIM103
            self.repo.descendant_of(
                self._get_st_cid(other),
                self._get_st_cid(candidate_parent),
            )
            for other in all_parents
            if other != candidate_parent
        ):
            return False

        # In any other case, we should use this parent.
        return True

    def _get_subtree_parents(
        self,
        host_commit: HostCommit,
    ) -> list[SubtreeCommit]:
        parents = []
        for parent in host_commit.parents:
            assert HostOid(parent.id) in self.mappings
            # if HostOid(parent.id) not in self.mappings:
            #     raise RuntimeError(
            #         f'Parent commit "{parent.id.hex}" not found in existing '
            #         "mapped commits.",
            #     )
            parents.append(HostCommit(parent))

        return stable_unique(
            SubtreeCommit(self.repo[self._get_st_cid(host_parent)])
            for host_parent in parents
            if self._should_use_parent(host_parent, parents)
        )

    # def _get_subtree_parent_mappings(
    #     self,
    #     host_commit: HostCommit,
    # ) -> dict[HostOid, StCommitMapped]:
    #     all_parents = list(host_commit.parents)
    #     processed_mappings: Set[StCommitMapped] = set()
    #     parent_mappings: Dict[HostOid, StCommitMapped] = {}

    #     for parent in host_commit.parents:
    #         # TODO: Handle case where subtree is created in one branch then
    #         # merged with a branch without the subtree.
    #         mapping = self.mappings[parent.id]

    #     # .......

    def _get_prefix(self, host_commit: HostCommit) -> Path:
        host_oid = HostOid(host_commit.id)

        # If the host commit is already mapped, use its recorded prefix.
        if host_oid in self.mappings:
            return self.mappings[host_oid].prefix

        # If all of the host commit's parents have the same prefix, use that
        # prefix. (This will fail if any of the host commit's parents are not
        # yet mapped.)
        parent_prefixes = {
            self.mappings[HostOid(parent.id)].prefix
            for parent in host_commit.parents
        }
        if len(parent_prefixes) == 1:
            return parent_prefixes.pop()

        raise PrefixError(
            host_commit,
            parent_prefixes,
            "move" if parent_prefixes else "new",
        )

    def _is_new_st_commit_needed(
        self,
        source: HostCommit,
        prefix: Path,
        parents: Sequence[SubtreeCommit],
    ) -> bool:
        # There should be at least one parent.
        assert len(parents) > 0

        # If there is a merge between two branches, then we need a new subtree
        # commit.
        if len(parents) != 1:
            return True

        # Otherwise, we only need a new subtree commit if the subtree contents
        # change.
        source_subtree = source.tree / str(prefix)
        return source_subtree != parents[0].tree

    def _save_mapping(
        self,
        host_oid: HostOid,
        prefix: Path,
        st_oid: SubtreeOid,
    ):
        self.mappings[host_oid] = StCommitMapped(prefix, st_oid)

    def _make_new_st_commit(
        self,
        host_commit: HostCommit,
        prefix: Path,
        st_parents: Sequence[SubtreeCommit],
    ):
        st_tree = host_commit.tree / prefix

        st_oid = self.repo.create_commit(
            None,  # ref
            host_commit.author,
            host_commit.committer,
            host_commit.message,
            tree=st_tree.id,
            parents=[p.id for p in st_parents],
        )

        st_commit = self.repo[st_oid]
        assert isinstance(st_commit, Commit)

        self._save_mapping(HostOid(host_commit.id), prefix, SubtreeOid(st_oid))

    @singledispatchmethod
    def _do_action(self, st_action: StAction, host_commit: HostCommit):
        # Function signature - not implemented.
        raise NotImplementedError

    @_do_action.register
    def _(self, st_action: StCommitMapped, host_commit: HostCommit):
        # No action to do. Should not be called.
        raise NotImplementedError

    @_do_action.register
    def _(self, st_action: StNew, host_commit: HostCommit):
        self._make_new_st_commit(host_commit, st_action.prefix, [])

    @_do_action.register
    def _(self, st_action: StMove, host_commit: HostCommit):
        prefix = st_action.new_prefix
        st_parents = self._get_subtree_parents(host_commit)

        if self._is_new_st_commit_needed(host_commit, prefix, st_parents):
            self._make_new_st_commit(host_commit, prefix, st_parents)
        else:
            host_oid = HostOid(host_commit.id)
            st_oid = SubtreeOid(st_parents[0].id)
            self._save_mapping(host_oid, prefix, st_oid)

    @_do_action.register
    def _(self, _: StExtract, host_commit: HostCommit):
        prefix = self._get_prefix(host_commit)
        st_parents = self._get_subtree_parents(host_commit)

        if self._is_new_st_commit_needed(host_commit, prefix, st_parents):
            self._make_new_st_commit(host_commit, prefix, st_parents)
        else:
            host_oid = HostOid(host_commit.id)
            st_oid = SubtreeOid(st_parents[0].id)
            self._save_mapping(host_oid, prefix, st_oid)

    def extract(self) -> SubtreeOid:
        for host_cid, action in self.actions:
            self._do_action(action, HostCommit(self.repo[host_cid]))

        last_host_cid = self.actions[-1][0]
        return self.mappings[last_host_cid].subtree_commit_id
