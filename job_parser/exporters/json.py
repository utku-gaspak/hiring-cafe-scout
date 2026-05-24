from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from job_parser.config import SearchConfig
from job_parser.models import Job


def save_json(jobs: list[Job], config: SearchConfig) -> None:
    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "keywords": config.keywords,
            "cities": config.cities,
            "radius_km": config.radius_km,
            "radius_city": config.radius_city,
            "max_pages": config.max_pages,
        },
        "results": [job.to_dict() for job in jobs],
    }
    output_path = Path(config.json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
