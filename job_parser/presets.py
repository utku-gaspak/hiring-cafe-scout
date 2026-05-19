from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from job_parser.config import SearchConfig


DEFAULT_PRESET_SLUG = "software-germany-junior"
PRESETS_DIR = "presets"


@dataclass(frozen=True, slots=True)
class Preset:
    slug: str
    name: str
    description: str
    config: SearchConfig
    builtin: bool = True
    path: str | None = None


def get_builtin_presets() -> dict[str, Preset]:
    return {
        DEFAULT_PRESET_SLUG: Preset(
            slug=DEFAULT_PRESET_SLUG,
            name="Software Germany Junior",
            description=(
                "Junior and entry-level software roles in Germany or remote Europe "
                "matching the current default tech stack keywords."
            ),
            config=SearchConfig(),
            path=None,
        )
    }


def get_builtin_preset(slug: str) -> Preset:
    presets = get_builtin_presets()
    try:
        return presets[slug]
    except KeyError as exc:
        raise KeyError(f"Unknown built-in preset: {slug}") from exc


def get_default_preset() -> Preset:
    return get_builtin_preset(DEFAULT_PRESET_SLUG)


def get_default_config() -> SearchConfig:
    return SearchConfig.from_dict(get_default_preset().config.to_dict())


def list_saved_presets(directory: str | Path = PRESETS_DIR) -> dict[str, Preset]:
    presets_dir = Path(directory)
    if not presets_dir.exists():
        return {}

    presets: dict[str, Preset] = {}
    for path in sorted(presets_dir.glob("*.json")):
        preset = load_saved_preset_from_path(path)
        presets[preset.slug] = preset
    return presets


def load_saved_preset(slug: str, directory: str | Path = PRESETS_DIR) -> Preset:
    path = Path(directory) / f"{slug}.json"
    return load_saved_preset_from_path(path)


def load_saved_preset_from_path(path: str | Path) -> Preset:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Preset file must contain a JSON object.")

    config_payload = payload.get("config") or {}
    if not isinstance(config_payload, dict):
        raise ValueError("Preset config must be a JSON object.")

    slug = str(payload.get("slug") or file_path.stem)
    return Preset(
        slug=slug,
        name=str(payload.get("name") or slug.replace("-", " ").title()),
        description=str(payload.get("description") or ""),
        config=SearchConfig.from_dict(config_payload),
        builtin=False,
        path=str(file_path),
    )


def list_all_presets(directory: str | Path = PRESETS_DIR) -> dict[str, Preset]:
    presets = get_builtin_presets()
    presets.update(list_saved_presets(directory))
    return presets


def save_preset(
    name: str,
    config: SearchConfig,
    description: str = "",
    directory: str | Path = PRESETS_DIR,
) -> Preset:
    slug = slugify_preset_name(name)
    presets_dir = Path(directory)
    presets_dir.mkdir(parents=True, exist_ok=True)
    path = presets_dir / f"{slug}.json"
    payload = {
        "slug": slug,
        "name": name.strip(),
        "description": description.strip(),
        "config": config.to_dict(),
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return load_saved_preset_from_path(path)


def slugify_preset_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().casefold()).strip("-")
    return slug or "preset"
