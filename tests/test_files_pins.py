"""Files → pinned folders: the per-Frame pin store, without a device or GUI."""
from types import SimpleNamespace

import pytest

from frameport.core import library
from frameport.ui.views import files_pins as pins


def frame(name="frame", host="10.0.0.5"):
    return SimpleNamespace(target=SimpleNamespace(name=name, host=host))


DL = {"id": "downloads", "label": "Downloads", "path": "/home/x/Downloads"}


def test_pin_unpin_per_frame():
    a, b = frame("a"), frame("b")
    pins.pin(a, DL, "/home/x/Downloads/mods/")
    pins.pin(a, DL, "/home/x/Downloads/mods")  # once
    assert pins.pins(a) == [{"loc": "downloads", "path": "/home/x/Downloads/mods"}]
    assert pins.is_pinned(a, "downloads", "/home/x/Downloads/mods/")
    assert pins.pins(b) == [] and not pins.is_pinned(b, "downloads", "/home/x/Downloads/mods")
    pins.unpin(a, "downloads", "/home/x/Downloads/mods")
    assert pins.pins(a) == [] and library.setting(pins.SETTING) == {}


@pytest.mark.parametrize("loc", [None, {}, {"id": "saves:p", "saves": "p"}, {"id": "tmp", "tmp": True},
                                 {"id": "x", "parent": DL}])
def test_cant_pin(loc):
    assert not pins.can_pin(loc)
    with pytest.raises(ValueError):
        pins.pin(frame(), loc, "/tmp/x")


def test_rename_move_and_delete_follow():
    f = frame()
    for p in ("/home/x/Downloads/mods", "/home/x/Downloads/mods/maps", "/home/x/Downloads/modsextra"):
        pins.pin(f, DL, p)
    pins.follow(f, "downloads", {"/home/x/Downloads/mods": "/home/x/Downloads/Mods"}, "downloads")  # rename
    assert [p["path"] for p in pins.pins(f)] == ["/home/x/Downloads/Mods", "/home/x/Downloads/Mods/maps",
                                                 "/home/x/Downloads/modsextra"]
    pins.follow(f, "downloads", {"/home/x/Downloads/Mods": "/media/SD/Mods"}, "drive:/media/SD")  # move
    assert pins.pins(f)[:2] == [{"loc": "drive:/media/SD", "path": "/media/SD/Mods"},
                                {"loc": "drive:/media/SD", "path": "/media/SD/Mods/maps"}]
    pins.forget(f, "drive:/media/SD", ["/media/SD/Mods"])
    assert pins.pins(f) == [{"loc": "downloads", "path": "/home/x/Downloads/modsextra"}]
    pins.forget(f, "videos", ["/home/x/Downloads/modsextra"])  # another location: untouched
    assert len(pins.pins(f)) == 1


def test_follow_merges_onto_an_existing_pin():
    f = frame()
    pins.pin(f, DL, "/home/x/Downloads/a")
    pins.pin(f, DL, "/home/x/Downloads/b")
    pins.follow(f, "downloads", {"/home/x/Downloads/a": "/home/x/Downloads/b"}, "downloads")
    assert pins.pins(f) == [{"loc": "downloads", "path": "/home/x/Downloads/b"}]


def test_bad_saved_entries_are_ignored():
    library.set_setting(pins.SETTING, {"frame": [{"loc": "downloads"}, "junk", {"loc": "home", "path": "/home/x/a"}]})
    assert pins.pins(frame()) == [{"loc": "home", "path": "/home/x/a"}]


def test_label_where_and_find():
    assert pins.label("/home/x/Downloads/mods", DL) == "mods"
    assert pins.label("/home/x/Downloads", DL) == "Downloads"
    assert pins.where("/home/x/Downloads/mods", DL) == "Downloads"
    assert pins.where("/home/x/Downloads/a/b/mods", DL) == "Downloads › a/b"
    assert pins.where("/x", None) == ""
    game = {"id": "app:p", "label": "Game"}  # a Quest game's storage before it's resolved
    assert pins.where("/home/x/sd/p/files", game) == "Game"
    groups = [(None, [(DL, "icon", "")]), ("Game storage", [(game, "pad", "")])]
    assert pins.find_location(groups, "app:p") == (game, "pad")
    assert pins.find_location(groups, "drive:/media/SD") is None


# ---------------------------------------------------------------------------------------------- the Files view
def view(installed=()):
    from frameport.install import files
    from frameport.ui.views.files import FilesView

    toasts = []
    f = SimpleNamespace(target=SimpleNamespace(name="frame", host="h"), home="/home/x")
    app = SimpleNamespace(target=SimpleNamespace(frame=f), frame_info={"installed": list(installed)},
                          run_bg=lambda fn, *a: fn(*a), toast=lambda msg, error=False: toasts.append(msg))
    v = FilesView(app)
    v.shared = [{**DL, "android": "/sdcard/Download", "shared": True, "package": None}]
    v.drives = []
    v.loc, v.path = v.shared[0], DL["path"]
    v.entries = [files.Entry("mods", "/home/x/Downloads/mods", True, 0, 0),
                 files.Entry("a.zip", "/home/x/Downloads/a.zip", False, 1, 0)]
    return v, f, toasts


def labels(actions):
    return [a[0] for a in actions if a]


def test_menus_pin_and_unpin():
    v, f, _ = view()
    folder, file = v.entries
    assert "Pin to Locations" in labels(v.menu_actions(folder))
    assert not any("Pin" in x for x in labels(v.menu_actions(file)))
    assert "Pin this folder" in labels(v.menu_actions(None))
    dict((a[0], a[2]) for a in v.menu_actions(folder) if a)["Pin to Locations"](None)
    assert pins.pins(f) == [{"loc": "downloads", "path": "/home/x/Downloads/mods"}]
    assert "Unpin" in labels(v.menu_actions(folder))
    assert [labels(v.pin_actions(p, loc)) for p, loc, _ in v.pinned()] == [["Open", "Unpin"]]
    v.loc = {"id": "tmp", "path": "/tmp", "tmp": True}
    assert not any("Pin" in x for x in labels(v.menu_actions(None)))


def test_unavailable_pin_and_folder_outside_its_location():
    v, f, toasts = view()
    pins.pin(f, {"id": "drive:/media/SD"}, "/media/SD/roms")
    (p, loc, _icon), = v.pinned()
    assert loc is None and labels(v.pin_actions(p, loc)) == ["Unpin"]
    v.open_pin(p, loc)
    assert "roms isn't on the Frame now" in toasts[-1]
    v.open_location(v.shared[0], "/media/SD/roms")  # not inside Downloads
    assert "isn't in Downloads anymore" in toasts[-1] and v.path == DL["path"]


def test_view_pins_follow_rename_move_and_delete():
    v, f, _ = view()
    pins.pin(f, DL, "/home/x/Downloads/mods")
    v._pins_moved(DL, {"/home/x/Downloads/mods": "/home/x/Downloads/Mods"}, DL)
    assert pins.is_pinned(f, "downloads", "/home/x/Downloads/Mods")
    v._pins_moved(DL, {"/home/x/Downloads/Mods": "/x/files/Mods"}, {"id": "saves:p", "saves": "p"})
    assert pins.pins(f) == []  # moved into a game's saves: can't be pinned there
    pins.pin(f, DL, "/home/x/Downloads/mods")
    v._pins_deleted(DL, ["/home/x/Downloads/mods"])
    assert pins.pins(f) == []
