import pytest
import zipfile
from pathlib import Path
from filepack import get_file_stream, cmd_zip, cmd_flatten, cmd_pack, generate_filtered_tree
import re

@pytest.fixture
def dummy_project(tmp_path):
    """Creates a fake directory structure for testing."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')", encoding="utf-8")
    
    sub = src / "module"
    sub.mkdir()
    (sub / "logic.py").write_text("# logic", encoding="utf-8")
    (sub / "main.py").write_text("# nested collision", encoding="utf-8")
    
    return src

def test_file_discovery(dummy_project):
    base, stream = get_file_stream(dummy_project, regex=r"\.py$")
    assert len(list(stream)) == 3

def test_zip_creation(dummy_project, tmp_path):
    zip_out = tmp_path / "test.zip"
    cmd_zip(str(dummy_project), r"\.py$", str(zip_out))
    
    with zipfile.ZipFile(zip_out, "r") as zf:
        assert "main.py" in zf.namelist()
        assert "module/logic.py" in zf.namelist()

def test_flatten_and_tree(dummy_project, tmp_path):
    out_dir = tmp_path / "flat_out"
    cmd_flatten(str(dummy_project), r"\.py$", str(out_dir))
    
    assert out_dir.exists()
    assert (out_dir / "main.py").exists()
    assert (out_dir / "logic.py").exists()
    assert (out_dir / "module_main.py").exists() # Collision handled
    
    map_file = out_dir / "directory_map.txt"
    assert map_file.exists()
    content = map_file.read_text(encoding="utf-8")
    
    # Check for the correct tree branch characters based on the sorting order
    assert "└── main.py" in content  # Changed from ├── to └──
    assert "├── logic.py" in content

def test_pack_to_bins(dummy_project, tmp_path):
    import os
    os.chdir(tmp_path)
    cmd_pack(str(dummy_project), r"\.py$", bins=1, prefix="test_pack")
    
    content = Path("test_pack_1.txt").read_text(encoding="utf-8")
    assert "BEGIN FILE: module/logic.py" in content