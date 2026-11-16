"""Conservative cache invalidation for extraction code and public configuration."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collection_fingerprint(*settings, root: Path = ROOT) -> str:
    digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode())
    for directory in ('collectors', 'extractors', 'normalization', 'config', 'comparison', 'util'):
        for path in sorted((root / directory).glob('*')):
            if path.is_file() and path.suffix in ('.py', '.yaml'):
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()
