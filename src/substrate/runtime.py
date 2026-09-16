"""Noespire's runtime adapter. All invocation state/processes belong to DANUS."""
from hashlib import sha256
from importlib.util import find_spec
import json
from pathlib import Path
from danus.execution.durable import DurableRounds
from danus.core.durable_io import immutable_json
from .store import lane


def source_digest():
    """Fingerprint loaded production packages, identically in source and wheels.

    Repository-relative discovery silently hashed no files after installation.
    Resolve the actual packages instead, using package-relative names so install
    location cannot change identity. Missing/empty sources are corruption, never
    an apparently valid empty digest. Tests and interpreter caches are not code
    executed by the research entry point.
    """
    digest = sha256()
    ignored = {"tests", "test", "__pycache__", ".pytest_cache"}
    for package in ("crpn", "substrate", "danus"):
        spec = find_spec(package)
        locations = list(spec.submodule_search_locations or ()) if spec else []
        if len(locations) != 1 or not spec.origin:
            raise RuntimeError(f"cannot fingerprint production package: {package}")
        base = Path(locations[0]).resolve()
        if not base.is_dir() or not Path(spec.origin).is_file():
            raise RuntimeError(f"production package source is unavailable: {package}")
        files = sorted(path for path in base.rglob("*")
                       if path.is_file() and path.suffix in (".py", ".cjs")
                       and not ignored.intersection(path.relative_to(base).parts))
        if not files:
            raise RuntimeError(f"empty production source package: {package}")
        for path in files:
            name = (package + "/" + path.relative_to(base).as_posix()).encode("utf-8")
            payload = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big"))
            digest.update(name)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


class Runtime:
    def __init__(self, root, *, runner, fingerprint):
        self.root, self.runner = Path(root), runner
        self.fingerprint = {**fingerprint, "source": source_digest(),
                            "model": "gpt-5.6-sol", "effort": "xhigh", "timeout": 600}
        immutable_json(self.root / "runtime.json", self.fingerprint)

    def call(self, role, study_id, key, instruction, packet, schema):
        # Fresh verifier invocations never inherit Worker memory or capabilities.
        worker = study_id if role == "worker" else role + "-" + sha256(key.encode()).hexdigest()[:20]
        directory = lane(self.root, worker)
        directory.mkdir(parents=True, exist_ok=True)
        rounds = DurableRounds(directory, self.fingerprint, runner=self.runner)
        if rounds.request(key) is not None:
            return rounds.resume(key)
        prompt = instruction + "\nLOCAL INPUT:\n" + json.dumps(packet, ensure_ascii=False)
        if len(prompt.encode("utf-8")) > 256000:
            raise ValueError("local attention limit exceeded; request a smaller material page")
        return rounds.invoke(key, prompt, schema, role=role)
