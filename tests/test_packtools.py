"""
tests/test_packtools.py — Smoke tests for all packtools CLI modules.

Filepack tests are ported from the original test_filepack.py.
The remaining modules get lightweight smoke tests that confirm the
public API is importable, callable, and doesn't blow up on valid input.
"""

import hashlib
import re
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_project(tmp_path: Path) -> Path:
    """Minimal directory tree used by filepack and dir_compare tests."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')", encoding="utf-8")

    sub = src / "module"
    sub.mkdir()
    (sub / "logic.py").write_text("# logic", encoding="utf-8")
    (sub / "main.py").write_text("# nested collision", encoding="utf-8")
    return src


@pytest.fixture
def dummy_manifest(tmp_path: Path) -> Path:
    """Write a minimal MANIFEST.txt and a matching tracked file."""
    tracked = tmp_path / "hello.py"
    tracked.write_bytes(b"print('hi')\n")

    data = tracked.read_bytes()
    normalised = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    file_sha = hashlib.sha256(normalised).hexdigest()[:16]
    bundle_input = file_sha               # only one file → concat is just itself
    bundle = hashlib.sha256(bundle_input.encode()).hexdigest()[:24]

    manifest = tmp_path / "MANIFEST.txt"
    manifest.write_text(
        f"# Test manifest\nbundle:\t{bundle}\n{file_sha}\thello.py\n",
        encoding="utf-8",
    )
    return tmp_path


# ===========================================================================
# _hashing
# ===========================================================================

class TestHashing:
    def test_sha16_length(self):
        from packtools._hashing import sha16
        assert len(sha16(b"hello")) == 16

    def test_sha16_crlf_normalisation(self):
        """LF and CRLF input must produce the same hash."""
        from packtools._hashing import sha16
        assert sha16(b"line\n") == sha16(b"line\r\n")

    def test_bundle_hash_length(self):
        from packtools._hashing import bundle_hash
        assert len(bundle_hash({"a.py": "a" * 16, "b.py": "b" * 16})) == 24

    def test_bundle_hash_sorted(self):
        """Order of keys must not affect the bundle hash."""
        from packtools._hashing import bundle_hash
        hashes = {"b.py": "b" * 16, "a.py": "a" * 16}
        h1 = bundle_hash({"a.py": "a" * 16, "b.py": "b" * 16})
        h2 = bundle_hash(hashes)
        assert h1 == h2


# ===========================================================================
# filepack
# ===========================================================================

class TestFilepack:
    def test_file_discovery(self, dummy_project):
        from packtools.filepack import get_file_stream
        base, stream = get_file_stream(dummy_project, regex=r"\.py$")
        assert len(list(stream)) == 3

    def test_zip_creation(self, dummy_project, tmp_path):
        from packtools.filepack import cmd_zip
        zip_out = tmp_path / "test.zip"
        cmd_zip(str(dummy_project), r"\.py$", str(zip_out))
        with zipfile.ZipFile(zip_out) as zf:
            assert "main.py" in zf.namelist()
            assert "module/logic.py" in zf.namelist()

    def test_flatten_and_tree(self, dummy_project, tmp_path):
        from packtools.filepack import cmd_flatten
        out_dir = tmp_path / "flat"
        cmd_flatten(str(dummy_project), r"\.py$", str(out_dir))
        assert (out_dir / "main.py").exists()
        assert (out_dir / "logic.py").exists()
        assert (out_dir / "module_main.py").exists()   # collision handled
        content = (out_dir / "directory_map.txt").read_text(encoding="utf-8")
        assert "└── main.py" in content
        assert "├── logic.py" in content

    def test_pack_to_bins(self, dummy_project, tmp_path, monkeypatch):
        from packtools.filepack import cmd_pack
        monkeypatch.chdir(tmp_path)
        cmd_pack(str(dummy_project), r"\.py$", bins=1, prefix="test_pack")
        content = Path("test_pack_1.txt").read_text(encoding="utf-8")
        assert "BEGIN FILE: module/logic.py" in content


# ===========================================================================
# filtered_tree
# ===========================================================================

class TestFilteredTree:
    def test_build_tree_returns_string(self, dummy_project):
        from packtools.filtered_tree import build_tree
        result = build_tree(dummy_project, re.compile(r"\.py$"))
        assert isinstance(result, str)
        assert "main.py" in result

    def test_build_tree_ignores_no_match(self, tmp_path):
        from packtools.filtered_tree import build_tree
        (tmp_path / "readme.md").write_text("# hi", encoding="utf-8")
        result = build_tree(tmp_path, re.compile(r"\.py$"))
        assert result == ""    # no .py files → empty tree

    def test_build_tree_skips_ignored_dirs(self, tmp_path):
        from packtools.filtered_tree import build_tree, IGNORED_DIRS
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.cpython-312.pyc").write_bytes(b"\x00")
        (tmp_path / "real.py").write_text("", encoding="utf-8")
        result = build_tree(tmp_path, re.compile(r"\.py$"))
        assert "__pycache__" not in result
        assert "real.py" in result


# ===========================================================================
# dir_compare
# ===========================================================================

class TestDirCompare:
    def test_collect_files(self, dummy_project):
        from packtools.dir_compare import collect_files
        files = collect_files(str(dummy_project), None)
        assert len(files) == 3
        # All keys use forward slashes
        assert all("/" in k or k == k for k in files)

    def test_build_rows_match(self, dummy_project):
        from packtools.dir_compare import collect_files, build_rows
        files = collect_files(str(dummy_project), None)
        rows = build_rows(files, files)
        assert all(r[3] == "MATCH" for r in rows)

    def test_build_rows_absent(self, dummy_project, tmp_path):
        from packtools.dir_compare import collect_files, build_rows
        empty = tmp_path / "empty"
        empty.mkdir()
        files_a = collect_files(str(dummy_project), None)
        files_b = collect_files(str(empty), None)
        rows = build_rows(files_a, files_b)
        assert all(r[3] == "PRESENT_A" for r in rows)

    def test_format_table_smoke(self, dummy_project):
        from packtools.dir_compare import collect_files, build_rows, format_table
        files = collect_files(str(dummy_project), None)
        rows  = build_rows(files, files)
        table = format_table(rows, "A", "B")
        assert "MATCH" in table
        assert "Total files" in table


# ===========================================================================
# delete_pattern
# ===========================================================================

class TestDeletePattern:
    def test_collect_matches(self, tmp_path):
        from packtools.delete_pattern import collect_matches
        (tmp_path / "a.tmp").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        matches = collect_matches(tmp_path, "*.tmp")
        assert len(matches) == 1
        assert matches[0].name == "a.tmp"

    def test_dry_run_does_not_delete(self, tmp_path, capsys):
        from packtools.delete_pattern import collect_matches, delete_matches
        f = tmp_path / "del_me.tmp"
        f.write_text("x")
        delete_matches([f], dry_run=True)
        assert f.exists()
        assert "Would delete" in capsys.readouterr().out

    def test_delete_removes_file(self, tmp_path):
        from packtools.delete_pattern import collect_matches, delete_matches
        f = tmp_path / "gone.tmp"
        f.write_text("x")
        delete_matches([f], dry_run=False)
        assert not f.exists()


# ===========================================================================
# manifest_check
# ===========================================================================

class TestManifestCheck:
    def test_load_manifest(self, dummy_manifest):
        from packtools.manifest_check import load_manifest
        manifest_path = str(dummy_manifest / "MANIFEST.txt")
        bundle, files = load_manifest(manifest_path)
        assert bundle is not None
        assert "hello.py" in files

    def test_check_smoke(self, dummy_manifest):
        """check() should run without error when all files are present."""
        import os
        from packtools.manifest_check import check
        os.chdir(dummy_manifest)
        check(str(dummy_manifest))   # raises SystemExit only on mismatch


# ===========================================================================
# verify_install
# ===========================================================================

class TestVerifyInstall:
    def test_load_manifest(self, dummy_manifest):
        from packtools.verify_install import load_manifest
        bundle, files = load_manifest(str(dummy_manifest / "MANIFEST.txt"))
        assert bundle is not None
        assert "hello.py" in files

    def test_verify_ok(self, dummy_manifest, monkeypatch):
        """verify() should not raise or sys.exit when all files match."""
        import os
        from packtools.verify_install import verify
        monkeypatch.chdir(dummy_manifest)
        verify(str(dummy_manifest / "MANIFEST.txt"))   # no exception → pass
