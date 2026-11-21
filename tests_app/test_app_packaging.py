"""The CLI distribution excludes the local web application."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_cli_distribution_excludes_app_and_keeps_optional_dependency():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^include\s*=\s*\["tritobol",\s*"tritobol\.\*"\]\s*$', text, re.M)
    scripts = re.search(r"(?ms)^\[project\.scripts\]\s*(.*?)(?=^\[|\Z)", text)
    assert scripts
    assert not re.search(r"^tritobol-app\s*=", scripts.group(1), re.M)
    assert re.search(r'^app\s*=\s*\["flask>=3\.0"\]\s*$', text, re.M)


def test_local_app_static_assets_remain_available_from_source():
    static = REPO / "tritobol_app" / "static"
    assert (static / "favicon.svg").is_file()
    html = (static / "index.html").read_text(encoding="utf-8")
    for ref in re.findall(r'(?:href|src)="/(static/[^"]+)"', html):
        assert (REPO / "tritobol_app" / ref).is_file(), ref
