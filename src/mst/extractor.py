from dataclasses import dataclass

from pygit2 import Oid
from pygit2.repository import Repository

from mst.st_actions import StAction, StCommitMapped


@dataclass
class Extractor:
    repo: Repository
    mappings: dict[Oid, StCommitMapped]
    actions: list[tuple[Oid, StAction]]

    def extract(self) -> Oid:
        for host_cid, action in self.actions:
            # TODO
            pass

        last_host_cid = self.actions[-1][0]
        return self.mappings[last_host_cid].subtree_commit_id
