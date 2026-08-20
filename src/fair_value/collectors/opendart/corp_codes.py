from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

from fair_value.collectors.opendart.client import (
    OpenDartAPIError,
    OpenDartClient,
)
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def fetch_corp_codes(
    client: OpenDartClient,
) -> list[dict[str, str]]:
    """OpenDART 회사 고유번호 전체 목록을 조회합니다."""
    archive = client.get_bytes("/api/corpCode.xml")

    try:
        with ZipFile(BytesIO(archive)) as zip_file:
            xml_names = [
                name
                for name in zip_file.namelist()
                if name.lower().endswith(".xml")
            ]

            if not xml_names:
                raise OpenDartAPIError(
                    "회사 고유번호 ZIP에 XML 파일이 없습니다."
                )

            xml_content = zip_file.read(xml_names[0])
    except BadZipFile:
        raise OpenDartAPIError(
            "회사 고유번호 응답이 올바른 ZIP 파일이 아닙니다."
        ) from None

    root = ElementTree.fromstring(xml_content)
    companies: list[dict[str, str]] = []

    for item in root.findall("list"):
        companies.append(
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "corp_eng_name": (
                    item.findtext("corp_eng_name") or ""
                ).strip(),
                "stock_code": (item.findtext("stock_code") or "").strip(),
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
        )

    return companies


def collect_corp_codes(
    client: OpenDartClient,
    storage: LocalStorage | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    """고유번호 목록을 Bronze JSON으로 저장합니다."""
    target_storage = storage or LocalStorage()
    companies = fetch_corp_codes(client)

    document = {
        "source": "opendart",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(companies),
        "records": companies,
    }

    saved_path = target_storage.write_json(
        layer=DataLayer.BRONZE,
        relative_path="opendart/corp_codes/corp_codes.json",
        data=document,
    )

    return saved_path, companies