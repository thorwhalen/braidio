"""The shipped skill must survive the path CI takes: sdist first, wheel from it.

A wheel built straight from the working tree passes while the published one is
broken (hatchling dedupes the `.claude/skills/` symlink against the real file
and keeps the symlink's path in the sdist) — so this test builds the sdist,
unpacks it, and builds the wheel from *that*.
"""

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("braidio/data/skills/braidio/SKILL.md", "braidio/data/skills/braidio-commentary-video/SKILL.md")

pytest.importorskip("build")


def _build(kind: str, src: Path, out: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "build", f"--{kind}", "--outdir", str(out), str(src)],
        check=True,
        capture_output=True,
    )
    return next(out.glob("*.tar.gz" if kind == "sdist" else "*.whl"))


def test_skill_ships_in_wheel_built_from_sdist(tmp_path):
    sdist = _build("sdist", ROOT, tmp_path / "sdist")
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
        tf.extractall(tmp_path / "src", filter="data")
    for skill in SKILLS:
        assert any(n.endswith(skill) for n in names), names
    assert not any("/.claude/" in n for n in names), "the symlink bridge leaked into the sdist"
    (src_dir,) = (tmp_path / "src").iterdir()
    wheel = _build("wheel", src_dir, tmp_path / "wheel")
    with zipfile.ZipFile(wheel) as zf:
        for skill in SKILLS:
            assert skill in zf.namelist(), zf.namelist()
