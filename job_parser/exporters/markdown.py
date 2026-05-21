from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_parser.config import SearchConfig
from job_parser.models import Job, sort_jobs


def save_markdown(jobs: list[Job], config: SearchConfig) -> None:
    sorted_jobs = sort_jobs(jobs)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Job Listings — hiring.cafe",
        "",
        f"**Keywords:** {' / '.join(config.keywords)}  ",
        "**Location:** Germany + Remote Europe  ",
        "**Level:** Junior / Entry  ",
        "**Commitment:** Full Time  ",
        f"**Scraped:** {now_str}  ",
        f"**Total matches:** {len(sorted_jobs)}",
        "",
        "---",
        "",
    ]

    for index, job in enumerate(sorted_jobs, 1):
        work_details = " · ".join(filter(None, [job.work_type, job.commitment]))
        apply_suffix = f" | Apply: {job.apply_url}" if job.apply_url else ""
        lines.append(
            f"{index}. {job.company} — {job.title} | {job.location} | "
            f"{work_details} | {job.posted_str} | {job.url}{apply_suffix}"
        )

    output_path = Path(config.markdown_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
