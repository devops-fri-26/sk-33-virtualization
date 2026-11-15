"""Album info found next to audio files (an uploaded folder, or files a plugin imports).

That is front-cover pictures, archive.org's <item>_files.xml / <item>_meta.xml and Kodi/Jellyfin album.nfo. It only
fills in what the audio file's own tags leave empty; these files aren't kept in the library.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePath

IMAGES = {"jpg", "jpeg", "png", "webp"}
SIDECARS = IMAGES | {"xml", "nfo"}
MAX_SIDECAR = 20 * 1024**2  # bigger pictures are scans, bigger XML isn't per-album metadata

COVER_NAMES = ["cover", "folder", "front", "albumart", "album", "albumartlarge"]  # best first
NAMED = len(COVER_NAMES)  # rank of other names that say cover/front, e.g. "Artist - Album - Front.jpg"
PLAIN = NAMED + 1  # some other picture: used only when it's the folder's only one
NOT_COVER = {"back", "inlay", "inside", "booklet", "tray", "spectrogram", "thumb", "artist", "logo", "label", "obi"}
ART_DIRS = {"artwork", "art", "covers", "cover", "scans", "scan", "images"}  # Album/Artwork/front.jpg
DISC = re.compile(r"^(cd|disc|disk)\s*\d*$", re.IGNORECASE)  # Album/CD1/… folders, CD.jpg disc photos
NUMBER = re.compile(r"^\s*(\d{1,3})(?!\d)")  # "03 - Song.flac" -> 3


@dataclass
class Extras:
    """What the files around one audio file add to it. This is the result of find()."""

    tags: dict[str, str] = field(default_factory=dict)  # title, artist, album, albumartist, date, tracknumber
    cover: Path | None = None  # picture for the album (or for the track, when it has no album)


@dataclass
class _Xml:
    """What the XML/NFO files of one folder say. Applies to the audio in it and in its subfolders."""

    album: dict[str, str] = field(default_factory=dict)
    files: dict[str, dict[str, str]] = field(default_factory=dict)  # path relative to the folder (lowercase) -> tags
    titles: dict[int, str] = field(default_factory=dict)  # album.nfo: track number -> title


def suffix(name: str | PurePath) -> str:
    """Get a file's extension in lower case and without the dot ("" when it has none)."""
    return PurePath(name).suffix.lower().lstrip(".")


def cover_rank(name: str | PurePath) -> int | None:
    """Judge from a picture's file name how likely it is the front cover.

    Args:
        name: The picture's name or path.

    Returns:
        A rank where lower is better: the position in COVER_NAMES for exactly those names, NAMED for other names
        that say cover, front or folder, PLAIN for any other picture. None when the name says it's something
        else (back, booklet, a disc photo…).
    """
    stem = PurePath(name).stem.lower()
    words = set(re.findall(r"[a-z]+", stem))
    if words & NOT_COVER or DISC.match(stem):
        return None
    if stem in COVER_NAMES:
        return COVER_NAMES.index(stem)
    return NAMED if words & {"cover", "front", "folder"} else PLAIN


def useful(name: str | PurePath) -> bool:
    """Whether a file is a sidecar worth reading: XML/NFO, or a picture that could be a front cover."""
    ext = suffix(name)
    return ext in ("xml", "nfo") or (ext in IMAGES and cover_rank(name) is not None)


def _text(el: ET.Element, tag: str) -> str | None:
    """Get the text of an element's child `tag`, or None when the child is missing or empty."""
    found = el.find(tag)
    if found is None or not found.text:
        return None
    return found.text.strip() or None


def _parse(path: Path) -> ET.Element | None:
    """Parse an XML file that came from a stranger.

    Args:
        path: The file.

    Returns:
        Its root element. None when the file can't be read, isn't XML, or uses a DOCTYPE or ENTITY.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    # Metadata files never use DOCTYPE/ENTITY; refusing them blocks entity-expansion tricks. A NUL byte means
    # UTF-16/32, where that check wouldn't see them.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data or b"\x00" in data:
        return None
    try:
        return ET.fromstring(data)
    except (ET.ParseError, ValueError, LookupError):  # e.g. a release .nfo that's plain text
        return None


def _read(path: Path, into: _Xml):
    """Read one XML/NFO file and add what it says to its folder's info.

    Three formats are understood, told apart by the root element: archive.org's `<files>` and `<metadata>`, and
    the `<album>` of a Kodi/Jellyfin album.nfo. Anything else is ignored. Album tags and track titles that an
    earlier file already set are kept.

    Args:
        path: The file to read.
        into: The folder's info so far; it is changed in place.
    """
    root = _parse(path)
    if root is None:
        return
    kind = root.tag.lower()
    if kind == "files":  # archive.org <item>_files.xml: per-file tags
        for f in root.iter("file"):
            if name := f.get("name"):
                tags = {
                    "title": _text(f, "title"),
                    "artist": _text(f, "artist") or _text(f, "creator"),
                    "album": _text(f, "album"),
                    "tracknumber": _text(f, "track"),
                }
                into.files.setdefault(name.lower(), {}).update({k: v for k, v in tags.items() if v})
    elif kind == "metadata":  # archive.org <item>_meta.xml: the item is the album
        creator = _text(root, "creator")
        tags = {"album": _text(root, "title"), "albumartist": creator, "artist": creator}
        tags["date"] = _text(root, "date") or _text(root, "year")
        into.album.update({k: v for k, v in tags.items() if v and k not in into.album})
    elif kind == "album":  # Kodi / Jellyfin album.nfo
        artist = _text(root, "albumartist") or _text(root, "artist")
        tags = {"album": _text(root, "title"), "albumartist": artist, "artist": artist}
        tags["date"] = _text(root, "year") or _text(root, "releasedate")
        into.album.update({k: v for k, v in tags.items() if v and k not in into.album})
        for t in root.iter("track"):
            pos, title = NUMBER.match(_text(t, "position") or ""), _text(t, "title")
            if pos and title:
                into.titles.setdefault(int(pos.group(1)), title)


def _cover(folder: Path, images: dict[Path, list[Path]]) -> Path | None:
    """Pick the front cover for the audio in `folder`.

    Args:
        folder: The folder the audio files are in.
        images: Every picture that came along, grouped by the folder it is in.

    Returns:
        A picture named like a cover (in the folder, else in an Artwork/Scans subfolder), else the folder's only
        picture. None when there is no such picture.
    """
    here = images.get(folder, [])
    art = [p for d, ps in images.items() if d.parent == folder and d.name.lower() in ART_DIRS for p in ps]
    # Tuples compare left to right, so min() prefers the folder itself over an art subfolder, then the better
    # rank, then the name (which only makes the choice the same every time).
    named = [
        (where, rank, p.name.lower(), p)
        for where, group in enumerate((here, art))
        for p in group
        if (rank := cover_rank(p)) is not None and rank < PLAIN
    ]
    if named:
        return min(named)[3]
    plain = [p for p in here if cover_rank(p) == PLAIN]
    return plain[0] if len(plain) == 1 else None


def find(root: Path, audio: list[Path], others: list[Path]) -> dict[Path, Extras]:
    """Work out what the sidecar files add to each audio file.

    Args:
        root: The top folder of the upload or download. Nothing above it is looked at.
        audio: The audio files, all under `root`.
        others: The sidecar files (pictures, XML, NFO), also under `root`.

    Returns:
        The Extras of every audio file, keyed by its path.
    """
    images: dict[Path, list[Path]] = {}
    xml: dict[Path, _Xml] = {}
    for p in sorted(others):  # sorted: which file wins a tie must not depend on the order they arrived in
        if suffix(p) in IMAGES:
            images.setdefault(p.parent, []).append(p)
        elif suffix(p) in ("xml", "nfo"):
            _read(p, xml.setdefault(p.parent, _Xml()))

    out = {}
    for a in audio:
        tags: dict[str, str] = {}
        folder = a.parent
        while True:  # the nearest folder's info wins
            if info := xml.get(folder):
                rel = a.relative_to(folder).as_posix().lower()
                n = NUMBER.match(a.name)
                by_number = {"title": info.titles[int(n.group(1))]} if n and int(n.group(1)) in info.titles else {}
                if by_number:
                    by_number["tracknumber"] = n.group(1)
                # Most specific first: this file's own entry, then its title by track number, then the album's.
                for source in (info.files.get(rel, {}), by_number, info.album):
                    for k, v in source.items():
                        tags.setdefault(k, v)
            if folder == root or root not in folder.parents:
                break
            folder = folder.parent
        cover = _cover(a.parent, images)
        if not cover and DISC.match(a.parent.name) and a.parent != root:  # Album/CD1/01.flac + Album/cover.jpg
            cover = _cover(a.parent.parent, images)
        out[a] = Extras(tags, cover)
    return out
