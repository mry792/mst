from pygit2 import Commit, Oid
from pygit2.repository import Repository

from mst.extractor import Extractor
from mst.git_utils import (
    DfsActions,
    GraftedError,
    dfs,
    find_commit_for_ref,
    is_grafted,
)
from mst.helpers import ProjectMetadata, make_notes_branch_name
from mst.st_actions import StAction, StCommitMapping, StNew, parse_st_action

# @dataclass
# class ExtractionInput:
#     host_commits: list[HostCommit] = field(default_factory=list)


class ExtractPrepper:
    def __init__(
        self,
        repo: Repository,
        tag_name: str,
        initial_depth: int = 4,
        src_branch: str = "dev",
        remote_name: str = "origin",
    ):
        self._next_depth = initial_depth
        self._repo = repo
        self._src_branch = src_branch
        self._remote_name = remote_name

        self._start_commit = find_commit_for_ref(repo, f"refs/tags/{tag_name}")

    def _deepen(self):
        src_ref = f"refs/heads/{self._src_branch}"
        dest_ref = f"refs/remotes/{self._remote_name}/{self._src_branch}"

        self._repo.remotes[self._remote_name].fetch(
            refspecs=[f"{src_ref}:{dest_ref}"],
            depth=int(self._next_depth),
        )

        self._next_depth *= 1.5

        # Refresh the repo.
        self._repo = Repository(self._repo.path)

    def _load_st_action(
        self,
        project_name: str,
        host_commit_id: Oid,
    ) -> StAction:
        note = self._repo.lookup_note(
            host_commit_id.hex,
            ref=make_notes_branch_name(project_name),
        )
        if note is None:
            return None
        return parse_st_action(note.message, project_name, host_commit_id)

    def _load_extractor(self, project_name: str) -> Extractor:
        roots: dict[Oid, StCommitMapping] = {}
        actions_unsorted: dict[Oid, StAction] = {}
        actions: list[tuple[Oid, StAction]] = []

        def _pre_visit(commit: Commit) -> bool:
            st_action = self._load_st_action(project_name, commit.id)
            if isinstance(st_action, StCommitMapping):
                roots[commit.id] = st_action
                return False

            if isinstance(st_action, StNew):
                actions.append((commit.id, st_action))
                return False

            if is_grafted(commit):
                raise GraftedError(commit.id)

            actions_unsorted[commit.id] = st_action

            return True

        def _post_visit(commit: Commit):
            cid = commit.id
            actions.append((cid, actions_unsorted.pop(cid)))

        dfs(
            self._start_commit,
            DfsActions(
                pre_visit=_pre_visit,
                post_visit=_post_visit,
            ),
        )

        return Extractor(repo=self._repo, mappings=roots, actions=actions)

    def prepare(self, project: ProjectMetadata) -> Extractor:
        while True:
            try:
                extractor = self._load_extractor(project.name)
                break
            except GraftedError:
                self._deepen()

        # Ensure roots are available.
        subtree_remote = self._repo.remotes.create(
            f"mst/{project.name}",
            f"ssh://gitlab.com/{project.remote}",
        )
        subtree_remote.fetch(
            [
                mapping.subtree_commit_id.hex
                for mapping in extractor.mappings.values()
            ],
            depth=1,
        )

        return extractor
