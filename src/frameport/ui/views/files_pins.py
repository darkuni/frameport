"""Files → pinned folders: folders the user pins show at the top of the Locations column (and in Move to…), one click
from anywhere. Kept per Frame in the library's settings (`files.pins`: {frame id: [{"loc", "path"}]}), where "loc" is
the id of the location the folder is in (`videos`, `drive:/media/SD`, `app:<package>`, `home`) and "path" the folder's
path on the Frame. A game's saves and /tmp can't be pinned (`can_pin`). Pins follow renames and moves made in
FramePort and go away with folders deleted in it; a folder changed elsewhere keeps its pin (shown as unavailable when
its location is gone, an error when the folder is). No Flet here: the view renders, this module decides."""
from __future__ import annotations

import posixpath

from ...core import library

SETTING = "files.pins"


def frame_key(frame) -> str:
    from ...install.screenshots import frame_id

    return frame_id(frame)


def can_pin(loc: dict | None) -> bool:
    """Not in a game's saves (agent-only, closed while the game runs) or /tmp (emptied at every restart)."""
    return bool(loc) and bool(loc.get("id")) and not (loc.get("saves") or loc.get("parent") or loc.get("tmp"))


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def pins(frame) -> list[dict]:
    """This Frame's pins, oldest first."""
    raw = (library.setting(SETTING) or {}).get(frame_key(frame)) or []
    return [{"loc": p["loc"], "path": p["path"]} for p in raw
            if isinstance(p, dict) and isinstance(p.get("loc"), str) and isinstance(p.get("path"), str)]


def _edit(frame, fn) -> bool:
    """Change this Frame's pins in one step: `fn(pins) -> pins`. True when they changed."""
    key = frame_key(frame)
    changed = False

    def change(everything):
        nonlocal changed
        everything = dict(everything or {})
        before = [dict(p) for p in everything.get(key) or [] if isinstance(p, dict)]
        mine = fn([dict(p) for p in before])
        changed = mine != before
        if mine:
            everything[key] = mine
        else:
            everything.pop(key, None)
        return everything
    library.update_setting(SETTING, change, {})
    return changed


def is_pinned(frame, loc_id: str, path: str) -> bool:
    path = posixpath.normpath(path)
    return any(p["loc"] == loc_id and p["path"] == path for p in pins(frame))


def pin(frame, loc: dict, path: str) -> None:
    if not can_pin(loc):
        raise ValueError("this folder can't be pinned")
    path = posixpath.normpath(path)

    def add(mine):
        if not any(p.get("loc") == loc["id"] and p.get("path") == path for p in mine):
            mine.append({"loc": loc["id"], "path": path})
        return mine
    _edit(frame, add)


def unpin(frame, loc_id: str, path: str) -> None:
    path = posixpath.normpath(path)
    _edit(frame, lambda mine: [p for p in mine if not (p.get("loc") == loc_id and p.get("path") == path)])


def forget(frame, loc_id: str, paths: list[str]) -> bool:
    """Folders deleted in FramePort: their pins, and pins of folders inside them, go."""
    gone = [posixpath.normpath(p) for p in paths]
    return _edit(frame, lambda mine: [p for p in mine if not (p.get("loc") == loc_id
                                                              and any(_under(p.get("path", ""), g) for g in gone))])


def follow(frame, src_id: str, moved: dict[str, str], dest_id: str) -> bool:
    """Folders renamed or moved in FramePort ({old path: new path}, from location `src_id` to `dest_id`): their pins,
    and pins of folders inside them, follow. A pin that would land where one already is merges into it."""
    moved = {posixpath.normpath(a): posixpath.normpath(b) for a, b in moved.items()}

    def apply(mine):
        out = []
        for p in mine:
            if p.get("loc") == src_id:
                for old, new in moved.items():
                    if _under(p.get("path", ""), old):
                        p = {"loc": dest_id, "path": new + p["path"][len(old):]}
                        break
            if not any(q["loc"] == p.get("loc") and q["path"] == p.get("path") for q in out):
                out.append(p)
        return out
    return _edit(frame, apply)


def label(path: str, loc: dict | None) -> str:
    """The pin's name in the list: the folder's name (its location's name for the location's own top folder)."""
    if loc and loc.get("path") and posixpath.normpath(loc["path"]) == path:
        return loc.get("label") or path
    return posixpath.basename(path) or path


def where(path: str, loc: dict | None) -> str:
    """The pin's subtitle: its location's name and the folder above it inside the location."""
    if not loc:
        return ""
    top = loc.get("path")
    parent = posixpath.dirname(path)
    if not top or not _under(parent, posixpath.normpath(top)) or parent == posixpath.normpath(top):
        return loc.get("label") or ""
    return f"{loc.get('label') or ''} › {posixpath.relpath(parent, top)}"


def find_location(groups: list[tuple[str | None, list[tuple[dict, str, str]]]], loc_id: str):
    """(location, icon) with this id among the Files locations, or None (an uninstalled game, an unplugged drive)."""
    for _heading, entries in groups:
        for loc, icon, _sub in entries:
            if loc.get("id") == loc_id:
                return loc, icon
    return None
