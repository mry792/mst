import logging
from dataclasses import dataclass
from functools import singledispatch
from pathlib import Path

import yaml
from pygit2 import Oid
from pygit2.repository import Repository

from mst.helpers import NOTES_BRANCH_NAME

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


class StExtract:
    pass


type StAction = StCommitMapped | StNew | StMove | StExtract


class YamlParseTypeError(RuntimeError):
    def __init__(self, data_type: type):
        super().__init__(f"unexpected data type '{data_type}'")


class YamlParseKeysError(RuntimeError):
    def __init__(self, project_name: str, cid: Oid, keys: set[str]):
        super().__init__(
            f"Unexpected keys in note 'refs/notes/mst/{project_name}:"
            f"{cid.hex}': {keys}",
        )


def st_action_from_record(text: str, project_name: str, cid: Oid) -> StAction:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise YamlParseTypeError(type(data))

    project_data = data.get(project_name, None)
    if project_data is None:
        return StExtract()

    record_type = project_data["type"]
    if record_type == "new":
        return StNew(Path(project_data["prefix"]))
    if record_type == "move":
        return StMove(
            Path(project_data["old_prefix"]),
            Path(project_data["new_prefix"]),
        )
    if record_type == "commit_mapped":
        return StCommitMapped(
            Path(project_data["prefix"]),
            Oid(hex=project_data["subtree_commit_id"]),
        )

    raise YamlParseKeysError(project_name, cid, keys)


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


def record_actions(
    repo: Repository,
    project_name: str,
    actions: dict[Oid, StAction],
    remote_name: str = "origin",
):
    remote = repo.remotes[remote_name]
    notes_refspec = f"{NOTES_BRANCH_NAME}:{NOTES_BRANCH_NAME}"

    logger.debug(f'Fetching existing notes for subtree "{project_name}".')
    remote.fetch([notes_refspec], depth=1)  # TODO: Might fail?

    for cid, action in actions.items():
        note_text = serialize_st_action(action)
        logger.debug(f'Adding note to "{cid.hex}":\n{note_text}')
        repo.create_note(
            note_text,
            author=repo.default_signature,
            committer=repo.default_signature,
            annotated_id=cid.hex,
            ref=NOTES_BRANCH_NAME,
        )

    logger.info(f'Notes created. Pushing to remote "{remote_name}".')
    remote.push([notes_refspec])
