from datetime import UTC, date, datetime
from pathlib import Path

from fair_value.collectors.opendart.client import OpenDartClient
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def fetch_periodic_disclosures(
    client: OpenDartClient,
    corp_code: str,
    begin_date: date,
    end_date: date,
    page_count: int = 100,
) -> list[dict[str, object]]:
    """Fetch all periodic-report disclosure metadata for a company."""
    if begin_date > end_date:
        raise ValueError("begin_date must not be later than end_date")

    records: list[dict[str, object]] = []
    page_no = 1

    while True:
        payload = client.get_json(
            path="/api/list.json",
            params={
                "corp_code": corp_code,
                "bgn_de": begin_date.strftime("%Y%m%d"),
                "end_de": end_date.strftime("%Y%m%d"),
                "pblntf_ty": "A",
                "page_no": str(page_no),
                "page_count": str(page_count),
            },
        )
        raw_records = payload.get("list")

        if isinstance(raw_records, list):
            records.extend(record for record in raw_records if isinstance(record, dict))

        total_page_raw = payload.get("total_page", 1)
        try:
            total_page = int(str(total_page_raw))
        except ValueError:
            total_page = 1

        if page_no >= total_page:
            break

        page_no += 1

    return records


def collect_periodic_disclosures(
    client: OpenDartClient,
    ticker: str,
    corp_code: str,
    begin_date: date,
    end_date: date,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    """Store disclosure receipt dates used for point-in-time availability."""
    records = fetch_periodic_disclosures(
        client=client,
        corp_code=corp_code,
        begin_date=begin_date,
        end_date=end_date,
    )
    document = {
        "source": "opendart",
        "collected_at": datetime.now(UTC).isoformat(),
        "request": {
            "ticker": ticker,
            "corp_code": corp_code,
            "begin_date": begin_date.isoformat(),
            "end_date": end_date.isoformat(),
            "disclosure_type": "periodic_report",
        },
        "record_count": len(records),
        "records": records,
    }
    target_storage = storage or LocalStorage()
    relative_path = f"opendart/disclosures/{ticker}/{begin_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    saved_path = target_storage.write_json(
        layer=DataLayer.BRONZE,
        relative_path=relative_path,
        data=document,
    )
    return saved_path, len(records)
