"""Every file under tritobol_app/static must be covered by pyproject package-data, or an installed copy would miss it."""
import fnmatch
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def package_data_patterns():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(text)["tool"]["setuptools"]["package-data"]["tritobol_app"]
    except ImportError:  # Python 3.10: no tomllib; read the single list line instead
        line = re.search(r"^tritobol_app\s*=\s*\[(.*?)\]", text, re.M).group(1)
        return re.findall(r'"([^"]+)"', line)


def test_all_static_files_are_declared_as_package_data():
    patterns = package_data_patterns()
    static = REPO / "tritobol_app" / "static"
    files = [p.relative_to(REPO / "tritobol_app").as_posix() for p in static.rglob("*") if p.is_file()]
    assert files, "no static files found"
    missing = [f for f in files if not any(fnmatch.fnmatchcase(f, pat) for pat in patterns)]
    assert missing == [], f"not included in the installed package: {missing}"


def test_favicon_is_declared_and_exists():
    assert (REPO / "tritobol_app" / "static" / "favicon.svg").is_file()
    assert any(fnmatch.fnmatchcase("static/favicon.svg", pat) for pat in package_data_patterns())


def test_index_references_only_declared_assets():
    html = (REPO / "tritobol_app" / "static" / "index.html").read_text(encoding="utf-8")
    patterns = package_data_patterns()
    for ref in re.findall(r'(?:href|src)="/(static/[^"]+)"', html):
        assert (REPO / "tritobol_app" / ref).is_file(), ref
        assert any(fnmatch.fnmatchcase(ref, pat) for pat in patterns), f"{ref} would be missing after install"
