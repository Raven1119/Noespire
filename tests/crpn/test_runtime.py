"""Installed and editable runtimes bind the same actual production sources."""
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from substrate import runtime


def packages(root):
    result = {}
    for name in ("crpn", "substrate", "danus"):
        base = root / name
        base.mkdir(parents=True)
        (base / "__init__.py").write_text("# Package initialization.\n", encoding="utf-8")
        (base / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
        result[name] = base
    (result["danus"] / "capabilities.cjs").write_text("export const version = 1;\n", encoding="utf-8")
    return result


def resolve(monkeypatch, roots):
    monkeypatch.setattr(runtime, "find_spec", lambda name: SimpleNamespace(
        origin=str(roots[name] / "__init__.py"), submodule_search_locations=[str(roots[name])]))


def test_identical_source_and_wheel_layout_have_identical_digest(tmp_path, monkeypatch):
    source = packages(tmp_path / "source" / "src")
    # The editable vendor may have a different root from the Noespire packages.
    vendor = tmp_path / "source" / "vendor" / "danus" / "danus"
    vendor.parent.mkdir(parents=True)
    shutil.move(str(source["danus"]), vendor)
    source["danus"] = vendor
    installed = {}
    for name, base in source.items():
        destination = tmp_path / "site-packages" / name
        shutil.copytree(base, destination)
        installed[name] = destination
    resolve(monkeypatch, source)
    before = runtime.source_digest()
    resolve(monkeypatch, installed)
    assert runtime.source_digest() == before


def test_tests_and_caches_do_not_change_production_fingerprint(tmp_path, monkeypatch):
    roots = packages(tmp_path)
    resolve(monkeypatch, roots)
    before = runtime.source_digest()
    for ignored in ("tests", "test", "__pycache__", ".pytest_cache"):
        path = roots["danus"] / ignored / "generated.py"
        path.parent.mkdir()
        path.write_text("changed_test_only = True", encoding="utf-8")
    assert runtime.source_digest() == before
    (roots["danus"] / "capabilities.cjs").write_text("export const version = 2;", encoding="utf-8")
    assert runtime.source_digest() != before


@pytest.mark.parametrize("defect", ["missing_package", "missing_origin", "empty_sources", "ambiguous_roots"])
def test_unavailable_or_empty_source_never_silently_hashes_empty(tmp_path, monkeypatch, defect):
    roots = packages(tmp_path)
    if defect == "empty_sources":
        for file in roots["danus"].iterdir():
            file.unlink()
        # A metadata-only origin still must not make an empty source set valid.
        (roots["danus"] / "metadata.txt").write_text("not production code")
    def spec(name):
        base = roots[name]
        if name == "danus":
            if defect == "missing_package":
                return None
            if defect == "missing_origin":
                return SimpleNamespace(origin=None, submodule_search_locations=[str(base)])
            if defect == "ambiguous_roots":
                return SimpleNamespace(origin=str(base / "__init__.py"),
                                       submodule_search_locations=[str(base), str(base / "other")])
            return SimpleNamespace(origin=str(base / "metadata.txt"), submodule_search_locations=[str(base)])
        return SimpleNamespace(origin=str(base / "__init__.py"), submodule_search_locations=[str(base)])
    monkeypatch.setattr(runtime, "find_spec", spec)
    with pytest.raises(RuntimeError, match="production|fingerprint"):
        runtime.source_digest()


def test_resume_rejects_production_code_drift_before_model_call(tmp_path, monkeypatch):
    roots = packages(tmp_path / "code")
    resolve(monkeypatch, roots)
    calls = []
    def unused(*args, **kwargs):
        calls.append(1)
        pytest.fail("runtime drift must fail before invocation")
    run = tmp_path / "run"
    first = runtime.Runtime(run, runner=unused, fingerprint={"image": "frozen"})
    recorded = (run / "runtime.json").read_bytes()
    assert first.fingerprint["source"] == runtime.source_digest()
    (roots["crpn"] / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable evidence changed"):
        runtime.Runtime(run, runner=unused, fingerprint={"image": "frozen"})
    assert (run / "runtime.json").read_bytes() == recorded and calls == []


def test_real_loaded_packages_have_nonempty_stable_fingerprint():
    digest = runtime.source_digest()
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert digest == runtime.source_digest()
