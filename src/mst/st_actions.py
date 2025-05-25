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
class StCommitMapping:
    prefix: Path
    subtree_commit_id: Oid


@dataclass(frozen=True)
class StNew:
    prefix: Path


@dataclass(frozen=True)
class StMove:
    new_prefix: Path


type StAction = StCommitMapping | StNew | StMove | None


class YamlParseTypeError(RuntimeError):
    def __init__(self, data_type: type):
        super().__init__(f"unexpected data type '{data_type}'")


class YamlParseKeysError(RuntimeError):
    def __init__(self, project_name: str, cid: Oid, keys: set[str]):
        super().__init__(
            f"Unexpected keys in note 'refs/notes/mst/{project_name}:"
            f"{cid.hex}': {keys}",
        )


def parse_st_action(text: str, project_name: str, cid: Oid) -> StAction:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise YamlParseTypeError(type(data))

    keys = set(data.keys())
    if keys == {"add"}:
        return StNew(Path(data["add"]))
    if keys == {"move"}:
        return StMove(Path(data["move"]))
    if keys == {"prefix", "subtree_commit"}:
        return StCommitMapping(
            Path(data["prefix"]),
            Oid(hex=data["subtree_commit"]),
        )

    raise YamlParseKeysError(project_name, cid, keys)


@singledispatch
def serialize_st_action(action: StAction) -> str:
    # Function signature - not implemented.
    raise NotImplementedError


@serialize_st_action.register
def _(action: StCommitMapping) -> str:
    return (
        f"prefix: {action.prefix}\n"
        f"subtree_commit: {action.subtree_commit_id.hex}"
    )


@serialize_st_action.register
def _(action: StNew) -> str:
    return f"new: {action.prefix}"


@serialize_st_action.register
def _(action: StMove) -> str:
    return f"move: {action.new_prefix}"


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
