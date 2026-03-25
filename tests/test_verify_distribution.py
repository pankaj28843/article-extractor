from __future__ import annotations

import importlib.util
import tarfile
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_distribution.py"
SPEC = importlib.util.spec_from_file_location("verify_distribution", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
verify_distribution = MODULE.verify_distribution


def test_verify_distribution_accepts_expected_wheel(tmp_path: Path):
    wheel = tmp_path / "article_extractor-0.5.7-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("article_extractor/__init__.py", '__version__ = "0.5.7"\n')
        archive.writestr(
            "article_extractor-0.5.7.dist-info/METADATA", "Metadata-Version: 2.4\n"
        )
        archive.writestr(
            "article_extractor-0.5.7.dist-info/WHEEL", "Wheel-Version: 1.0\n"
        )

    assert verify_distribution(str(wheel)) == []


def test_verify_distribution_rejects_pth_in_wheel(tmp_path: Path):
    wheel = tmp_path / "article_extractor-0.5.7-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("article_extractor/__init__.py", "__all__ = []\n")
        archive.writestr("article_extractor_init.pth", "import os\n")

    errors = verify_distribution(str(wheel))

    assert errors == ["banned file suffix: article_extractor_init.pth"]


def test_verify_distribution_rejects_unexpected_top_level_wheel_entry(tmp_path: Path):
    wheel = tmp_path / "article_extractor-0.5.7-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("article_extractor/__init__.py", "__all__ = []\n")
        archive.writestr("evil/__init__.py", "__all__ = []\n")

    errors = verify_distribution(str(wheel))

    assert errors == ["unexpected top-level wheel entry: evil/__init__.py"]


def test_verify_distribution_rejects_sitecustomize_in_sdist(tmp_path: Path):
    sdist = tmp_path / "article_extractor-0.5.7.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        package_root = tmp_path / "article_extractor-0.5.7"
        package_root.mkdir()
        pyproject = package_root / "pyproject.toml"
        pyproject.write_text(
            "[project]\nname = 'article-extractor'\n", encoding="utf-8"
        )
        suspicious = package_root / "sitecustomize.py"
        suspicious.write_text("print('oops')\n", encoding="utf-8")
        archive.add(pyproject, arcname="article_extractor-0.5.7/pyproject.toml")
        archive.add(suspicious, arcname="article_extractor-0.5.7/sitecustomize.py")

    errors = verify_distribution(str(sdist))

    assert errors == ["banned file name: sitecustomize.py"]
