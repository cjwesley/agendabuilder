"""Parse HTML form data with bracket-notation paths into a nested dict.

Field name grammar:
    name      = segment ( ('.' | '[' INT ']') segment? )*
    segment   = identifier

Examples:
    headlines[0].figure       → ["headlines", 0, "figure"]
    sections[2].items[1].name → ["sections", 2, "items", 1, "name"]
    legistar_ids[0]           → ["legistar_ids", 0]

Booleans use a hidden+checkbox pair (hidden default = "false", checkbox = "true").
The parser picks the last value, which Pydantic coerces to bool.

List ordering uses numeric indices verbatim — gaps are preserved as None at
parse time and stripped when collapsing to a list. Re-numbering on the client
should happen after remove/reorder, so gaps are normally a transient state.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"([a-zA-Z_][\w-]*)|\[(\d+)\]")


def parse_path(field: str) -> list[str | int]:
    """'sections[2].items[1].name' → ['sections', 2, 'items', 1, 'name']."""
    tokens: list[str | int] = []
    for m in _TOKEN_RE.finditer(field):
        if m.group(1) is not None:
            tokens.append(m.group(1))
        else:
            tokens.append(int(m.group(2)))
    return tokens


def _ensure_container(parent: Any, key: str | int, next_is_index: bool) -> Any:
    """Make sure parent[key] exists as the right container type, return it."""
    want_list = next_is_index
    if isinstance(parent, list):
        assert isinstance(key, int)
        while len(parent) <= key:
            parent.append(None)
        if parent[key] is None:
            parent[key] = [] if want_list else {}
        return parent[key]
    else:
        assert isinstance(key, str)
        if key not in parent or parent[key] is None:
            parent[key] = [] if want_list else {}
        return parent[key]


def _set(parent: Any, key: str | int, value: Any) -> None:
    if isinstance(parent, list):
        assert isinstance(key, int)
        while len(parent) <= key:
            parent.append(None)
        parent[key] = value
    else:
        assert isinstance(key, str)
        parent[key] = value


def insert(root: dict, tokens: list[str | int], value: Any) -> None:
    """Place value at the path indicated by tokens, creating intermediates."""
    cur: Any = root
    for i, tok in enumerate(tokens[:-1]):
        next_tok = tokens[i + 1]
        cur = _ensure_container(cur, tok, isinstance(next_tok, int))
    _set(cur, tokens[-1], value)


def _strip_none_from_lists(node: Any) -> Any:
    """Walk the tree, drop None entries from any list (gaps from sparse paths)."""
    if isinstance(node, list):
        return [_strip_none_from_lists(x) for x in node if x is not None]
    if isinstance(node, dict):
        return {k: _strip_none_from_lists(v) for k, v in node.items()}
    return node


def form_to_dict(items: list[tuple[str, str]]) -> dict:
    """Convert (key, value) pairs (in DOM order) to a nested dict.

    When the same key appears multiple times, the last value wins. This is what
    we want for hidden+checkbox boolean pairs.
    """
    root: dict = {}
    last_value: dict[str, str] = {}
    for k, v in items:
        last_value[k] = v
    for k, v in last_value.items():
        tokens = parse_path(k)
        # Skip empty submissions for non-required fields. Pydantic handles
        # required-field violations.
        insert(root, tokens, v)
    return _strip_none_from_lists(root)


def _coerce_empty(node: Any) -> Any:
    """Strip empty-string fields so Pydantic defaults take over."""
    if isinstance(node, dict):
        return {k: _coerce_empty(v) for k, v in node.items() if v not in ("", None)}
    if isinstance(node, list):
        return [_coerce_empty(x) for x in node]
    return node


def form_to_issue_dict(items: list[tuple[str, str]]) -> dict:
    """Top-level: form items → dict suitable for Issue.model_validate."""
    return _coerce_empty(form_to_dict(items))
