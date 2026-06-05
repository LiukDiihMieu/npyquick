from __future__ import annotations

import zipfile
from dataclasses import dataclass

import numpy as np
from numpy.lib import format as _npy_format

from .limits import array_nbytes


@dataclass(frozen=True)
class MemberMeta:
    shape: tuple[int, ...]
    dtype: np.dtype
    nbytes: int
    compressed: bool = False


def read_npy_header(fp) -> tuple[tuple[int, ...], np.dtype]:
    """Read shape/dtype from a file-like positioned at the start of a .npy stream.

    Works for a bare .npy file or a .npy member opened from inside a zip.
    Only the header is consumed; the array body is never read.
    """
    major, _minor = _npy_format.read_magic(fp)
    if major == 1:
        shape, _fortran, dtype = _npy_format.read_array_header_1_0(fp)
    else:
        # 2.0 and 3.0 share the same 4-byte header-length layout.
        shape, _fortran, dtype = _npy_format.read_array_header_2_0(fp)
    return shape, dtype


def peek_npy(path: str) -> MemberMeta:
    """Read a .npy file's header only and return its metadata."""
    with open(path, "rb") as fp:
        shape, dtype = read_npy_header(fp)
    return MemberMeta(shape, dtype, array_nbytes(shape, dtype), compressed=False)


def peek_npz(path: str) -> dict[str, MemberMeta]:
    """Map each .npz member to its metadata without materializing array bodies.

    Reuses NumPy's own key list so the returned keys match ``f[key]`` exactly;
    for compressed members reading the header still decompresses a small leading
    chunk of the stream (non-zero cost, not a memmap).
    """
    metas: dict[str, MemberMeta] = {}
    with np.load(path, allow_pickle=False) as f:
        zf: zipfile.ZipFile = f.zip
        for key in f.files:
            member = key + ".npy"
            zinfo = zf.getinfo(member)
            compressed = zinfo.compress_type != zipfile.ZIP_STORED
            with zf.open(member) as stream:
                shape, dtype = read_npy_header(stream)
            metas[key] = MemberMeta(
                shape, dtype, array_nbytes(shape, dtype), compressed
            )
    return metas
