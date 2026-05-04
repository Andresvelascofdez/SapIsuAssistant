"""Small .env loader/writer for local secrets."""
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.lstrip("\ufeff").strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def read_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    """Read a simple KEY=VALUE .env file."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parsed = _parse_line(line)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def load_env_file(path: Path = ENV_PATH, overwrite: bool = False) -> dict[str, str]:
    """Load .env values into os.environ."""
    values = read_env_file(path)
    for key, value in values.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return values


def set_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    """Create or update a key in .env without disturbing unrelated values."""
    key = key.strip()
    if not key:
        raise ValueError("key cannot be empty")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = False
    output = []
    for line in lines:
        parsed = _parse_line(line)
        if parsed and parsed[0] == key:
            output.append(f"{key}={value}")
            updated = True
        else:
            output.append(line)
    if not updated:
        output.append(f"{key}={value}")
    path.write_text("\n".join(output).strip() + "\n", encoding="utf-8")
