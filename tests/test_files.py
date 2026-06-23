from __future__ import annotations

import hashlib

from check_printing.files import sha256_file


def test_sha256_file_hashes_file_contents(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"sample-content")

    assert sha256_file(path) == hashlib.sha256(b"sample-content").hexdigest()
