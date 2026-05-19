from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_parser.config import SearchConfig
from job_parser.models import Job


def save_markdown(jobs: list[Job], config: SearchConfig) -> None:
    jobs.sort(key=lambda job: job.date_obj, reverse=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Job Listings — hiring.cafe",
        "",
        f"**Keywords:** {' / '.join(config.keywords)}  ",
        "**Location:** Germany + Remote Europe  ",
        "**Level:** Junior / Entry  ",
        "**Commitment:** Full Time  ",
        f"**Scraped:** {now_str}  ",
        f"**Total matches:** {len(jobs)}",
        "",
        "---",
        "",
    ]

    for index, job in enumerate(jobs, 1):
        work_details = " · ".join(filter(None, [job.work_type, job.commitment]))
        apply_suffix = f" | Apply: {job.apply_url}" if job.apply_url else ""
        lines.append(
            f"{index}. {job.company} — {job.title} | {job.location} | "
            f"{work_details} | {job.posted_str} | {job.url}{apply_suffix}"
        )

    Path(config.output).write_text("\n".join(lines), encoding="utf-8")

