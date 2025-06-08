import logging

from pygit2 import Commit
from pygit2.repository import Repository

from mst.extractor import Extractor
from mst.git_utils import (
    DfsActions,
    GraftedError,
    dfs,
    find_commit_for_ref,
    is_grafted,
)
from mst.helpers import NOTES_BRANCH_NAME, HostOid, ProjectMetadata
from mst.st_actions import (
    StAction,
    StCommitMapped,
    StExtract,
    StNew,
    st_action_from_record,
)

logger = logging.getLogger(__name__)


# @dataclass
# class ExtractionInput:
#     host_commits: list[HostCommit] = field(default_factory=list)


class NoDepthError(RuntimeError):
    def __init__(self):
        super().__init__(
            "No depth specified but ran into grafted commit. Cannot continue "
            "extraction.",
        )


class ExtractPrepper:
    def __init__(
        self,
        repo: Repository,
        tag_name: str,
        initial_depth: int = 0,
        remote_name: str = "origin",
    ):
        self._next_depth = initial_depth
        self._repo = repo
        self._remote_name = remote_name

        self._start_cid = find_commit_for_ref(repo, f"refs/tags/{tag_name}").id

    def _deepen(self):
        if self._next_depth == 0:
            raise NoDepthError()

        self._repo.remotes[self._remote_name].fetch(
            refspecs=[f"{self._start_cid.hex}"],
            depth=int(self._next_depth),
        )

        self._next_depth *= 1.5

        # Refresh the repo.
        self._repo = Repository(self._repo.path)

    def _load_st_action(
        self,
        project_name: str,
        host_oid: HostOid,
    ) -> StAction:
        note = self._repo.lookup_note(host_oid.hex, ref=NOTES_BRANCH_NAME)
        if note is None:
            return StExtract()
        return st_action_from_record(note.message, project_name)

    def _load_extractor(self, project_name: str) -> Extractor:
        roots: dict[HostOid, StCommitMapped] = {}
        actions_unsorted: dict[HostOid, StAction] = {}
        actions: list[tuple[HostOid, StAction]] = []

        def _pre_visit(commit: Commit) -> bool:
            commit_id = HostOid(commit.id)
            st_action = self._load_st_action(project_name, commit_id)
            if isinstance(st_action, StCommitMapped):
                roots[commit_id] = st_action
                return False

            if isinstance(st_action, StNew):
                actions.append((commit_id, st_action))
                return False

            if is_grafted(commit):
                raise GraftedError(commit_id)

            actions_unsorted[commit_id] = st_action

            return True

        def _post_visit(commit: Commit):
            cid = HostOid(commit.id)
            actions.append((cid, actions_unsorted.pop(cid)))

        start_commit = self._repo[self._start_cid]
        if not isinstance(start_commit, Commit):
            raise TypeError  # This should not be reachable.

        dfs(
            start_commit,
            DfsActions(pre_visit=_pre_visit, post_visit=_post_visit),
        )
        assert len(actions_unsorted) == 0

        return Extractor(repo=self._repo, mappings=roots, actions=actions)

    def prepare(self, project: ProjectMetadata) -> Extractor:
        logger.info(f"({project.name}) identifying commits")

        while True:
            try:
                extractor = self._load_extractor(project.name)
                break
            except GraftedError:
                logger.info(
                    "Found unextracted grafted commit. Need more commits. "
                    f"Fetching to depth {int(self._next_depth)}.",
                )
                self._deepen()

        # Ensure roots are available.
        logger.info(f"({project.name}) creating mst remote")
        subtree_remote = self._repo.remotes.create(
            f"mst/{project.name}",
            f"ssh://gitlab.com/{project.remote}",
        )
        logger.info(f"({project.name}) fetching root commits for extraction")
        subtree_remote.fetch(
            [
                mapping.subtree_commit_id.hex
                for mapping in extractor.mappings.values()
            ],
            depth=1,
        )

        return extractor
