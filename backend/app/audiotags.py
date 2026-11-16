"""Read an audio file's tags as plain text, under the same names for every format.

mutagen's "easy" tags already do that for FLAC, MP3, M4A, Ogg and Opus. WAV files are read here: they keep their
tags in an ID3 chunk or in the older RIFF INFO list, and mutagen gives neither of them easy names.
"""

import struct
from pathlib import Path

import mutagen
from mutagen.easymp4 import EasyMP4Tags
from mutagen.wave import WAVE

VARIOUS = "Various Artists"  # album artist of a compilation
KEYS = ("title", "artist", "album", "albumartist", "date", "tracknumber", "compilation")

ID3 = {
    "TIT2": "title",
    "TPE1": "artist",
    "TALB": "album",
    "TPE2": "albumartist",
    "TDRC": "date",
    "TRCK": "tracknumber",
    "TCMP": "compilation",
}
INFO = {
    b"INAM": "title",
    b"IART": "artist",
    b"IPRD": "album",
    b"ICRD": "date",
    b"ITRK": "tracknumber",
    b"IPRT": "tracknumber",
}
MAX_INFO = 1024**2  # bytes; a bigger LIST chunk isn't a list of tags


def _mp4_compilation(tags, key: str) -> list[str]:
    """Read the "part of a compilation" flag of an M4A file, which mutagen has no easy name for."""
    if not tags.get("cpil"):
        raise KeyError(key)
    return ["1"]


EasyMP4Tags.RegisterKey("compilation", getter=_mp4_compilation)


def _info_fields(data: bytes, into: dict[str, list[str]]):
    """Add the fields of a RIFF INFO list to `into`. Fields that are already there are kept.

    Args:
        data: The list's content after its "INFO" marker: field name, length and text, one after the other.
        into: The tags so far; changed in place.
    """
    pos = 0
    while pos + 8 <= len(data):
        name, size = data[pos : pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        raw = data[pos + 8 : pos + 8 + size].split(b"\x00")[0]
        pos += 8 + size + size % 2  # fields are padded to an even length
        try:
            text = raw.decode().strip()
        except UnicodeDecodeError:
            text = raw.decode("latin-1").strip()
        if (key := INFO.get(name)) and text:
            into.setdefault(key, [text])


def _riff_info(path: Path, into: dict[str, list[str]]):
    """Add the tags of a WAV file's RIFF INFO list to `into`. Only chunk headers are read, not the audio.

    Args:
        path: The WAV file.
        into: The tags so far; changed in place. Nothing is added when the file has no INFO list.
    """
    try:
        with path.open("rb") as f:
            head = f.read(12)
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return
            while len(chunk := f.read(8)) == 8:
                name, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
                if name == b"LIST" and 4 <= size <= MAX_INFO:
                    data = f.read(size)
                    if data[:4] == b"INFO":
                        _info_fields(data[4:], into)
                else:
                    f.seek(size, 1)
                if size % 2:  # chunks are padded to an even length
                    f.seek(1, 1)
    except (OSError, struct.error):
        return


def text_tags(audio: mutagen.FileType, path: Path) -> dict[str, list[str]]:
    """Get the tags an import uses, as lists of text.

    Args:
        audio: The file as opened with `mutagen.File(path, easy=True)`.
        path: The same file on disk.

    Returns:
        The values of the tags in KEYS that the file has. A tag it doesn't have is left out.
    """
    tags = audio.tags
    out: dict[str, list[str]] = {}
    if isinstance(audio, WAVE):
        for frame_id, key in ID3.items():
            frame = tags.get(frame_id) if tags is not None else None
            values = [str(v).strip() for v in getattr(frame, "text", [])]
            if any(values):
                out[key] = [v for v in values if v]
        _riff_info(path, out)
        return out
    for key in KEYS:
        values = [str(v).strip() for v in (tags.get(key) if tags is not None else None) or []]
        if any(values):
            out[key] = [v for v in values if v]
    return out


def read(path: Path) -> dict[str, list[str]]:
    """Get a file's tags without importing it.

    Args:
        path: An audio file.

    Returns:
        Its tags (see text_tags()). Empty when it has none, is damaged or isn't audio.
    """
    try:
        audio = mutagen.File(path, easy=True)
    except (mutagen.MutagenError, OSError):
        return {}
    return text_tags(audio, path) if audio is not None else {}


def is_compilation(tags: dict[str, list[str]]) -> bool:
    """Whether a file's tags mark it as part of a compilation (iTunes' flag: "1")."""
    return (tags.get("compilation") or [""])[0].lower() in ("1", "true", "yes")
