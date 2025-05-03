from dataclasses import dataclass
from pathlib import Path

import yaml
from functools import singledispatch
from pygit2 import Oid


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
