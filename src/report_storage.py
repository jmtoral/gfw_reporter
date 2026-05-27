import json
import re
from datetime import datetime
from pathlib import Path


def slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return normalized or "report"


def save_report_bundle(result: dict, base_dir: str = "saved_reports") -> Path:
    base_path = Path(base_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    country_slug = slugify(result["country"])
    report_dir = base_path / f"{timestamp}_{country_slug}"
    report_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = report_dir / "report.md"
    pdf_path = report_dir / result["pdf_name"]
    docx_path = report_dir / result["docx_name"]
    metadata_path = report_dir / "metadata.json"

    markdown_path.write_text(result["report_text"], encoding="utf-8")
    pdf_path.write_bytes(result["pdf_bytes"])
    if result.get("docx_bytes"):
        docx_path.write_bytes(result["docx_bytes"])

    metadata = {
        "country": result["country"],
        "date_range": result.get("date_range"),
        "provider": result["provider"],
        "model_name": result["model_name"],
        "analysis_skill": result["analysis_skill"],
        "report_mode": result.get("report_mode"),
        "women_events_count": result["women_events_count"],
        "other_events_count": result["other_events_count"],
        "women_peak_dates": result.get("women_peak_dates"),
        "overall_peak_dates": result.get("overall_peak_dates"),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    if result.get("usage"):
        metadata["usage"] = result["usage"]
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    return report_dir
