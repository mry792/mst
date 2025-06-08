import logging
from dataclasses import dataclass
from functools import singledispatch
from pathlib import Path

import yaml
from pygit2 import Oid
from pygit2.repository import Repository

from mst.helpers import (
    NOTES_BRANCH_NAME,
    HostOid,
    fetch_mst_notes,
    push_mst_notes,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StCommitMapped:
    prefix: Path
    subtree_commit_id: Oid


@dataclass(frozen=True)
class StNew:
    prefix: Path


@dataclass(frozen=True)
class StMove:
    old_prefix: Path
    new_prefix: Path


@dataclass(frozen=True)
class StExtract:
    pass


type StAction = StCommitMapped | StNew | StMove | StExtract


class YamlParseTypeError(RuntimeError):
    def __init__(self, data_type: type):
        super().__init__(f"unexpected data type '{data_type}'")


class StParseError(RuntimeError):
    def __init__(self, data: dict):
        super().__init__(f'Failed to parse ST action data: "{data}"')


def parse_st_action(data: dict | None) -> StAction:
    if data is None:
        return StExtract()

    action_type = data["type"]
    if action_type == "new":
        return StNew(Path(data["prefix"]))
    if action_type == "move":
        return StMove(
            Path(data["old_prefix"]),
            Path(data["new_prefix"]),
        )
    if action_type == "commit_mapped":
        return StCommitMapped(
            Path(data["prefix"]),
            Oid(hex=data["subtree_commit_id"]),
        )

    raise StParseError(data)


def st_action_from_record(text: str, project_name: str) -> StAction:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise YamlParseTypeError(type(data))

    return parse_st_action(data.get(project_name, None))


@singledispatch
def serialize_st_action(action: StAction) -> dict:
    # Function signature - not implemented.
    raise NotImplementedError


@serialize_st_action.register
def _(action: StCommitMapped) -> dict:
    return {
        "type": "commit_mapped",
        "prefix": action.prefix,
        "subtree_commit": action.subtree_commit_id.hex,
    }


@serialize_st_action.register
def _(action: StNew) -> dict:
    return {
        "type": "new",
        "prefix": action.prefix,
    }


@serialize_st_action.register
def _(action: StMove) -> dict:
    return {
        "type": "move",
        "old_prefix": action.old_prefix,
        "new_prefix": action.new_prefix,
    }


def _sumarize_project_actions(data: dict) -> str:
    if data:
        return "\n".join(
            f"  - {proj}: {action_data['type']}"
            for proj, action_data in data.items()
        )
    return "  (none)"


def serialize_st_actions(project_actions: dict[str, StAction]) -> dict:
    result = {}

    for project_name, action in project_actions.items():
        logger.debug(f"Recording action: {project_name}: {action}")
        action_data = serialize_st_action(action)
        result[project_name] = action_data

    return result


def record_actions(
    repo: Repository,
    host_oid: HostOid,
    project_actions: dict[str, StAction],
):
    note = repo.lookup_node(host_oid.hex, ref=NOTES_BRANCH_NAME) or ""
    data = yaml.safe_load(note.message) or {}

    logger.debug(
        f'Prior actions for commit "{host_oid.hex}":\n'
        f"{_sumarize_project_actions(data)}",
    )

    data.update(serialize_st_actions(project_actions))

    logger.debug(f'Recording {len(data)} actions for commit "{host_oid.hex}".')
    repo.create_note(
        yaml.dump(data),
        author=repo.default_signature,
        committer=repo.default_signature,
        annotated_id=host_oid.hex,
        ref=NOTES_BRANCH_NAME,
    )


def save_actions(
    repo: Repository,
    host_oid: HostOid,
    project_actions: dict[str, StAction],
    remote_name: str = "origin",
):
    fetch_mst_notes(repo, remote_name)
    record_actions(repo, host_oid, project_actions)
    push_mst_notes(repo, remote_name)
