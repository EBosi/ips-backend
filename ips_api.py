#!/usr/bin/env python3

import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SCOPUS_BASE_URL = "https://api.elsevier.com/content"
WOS_BASE_URL = os.getenv("WOS_API_BASE_URL", "https://api.clarivate.com/apis/wos-starter/v1")


class ApiError(RuntimeError):
    pass


def _http_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code} for {url}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"Network error for {url}: {exc}") from exc


def _print(data: Any) -> None:
    print(json.dumps(_redact(data), indent=2, ensure_ascii=False, sort_keys=True))


def _is_authorization_error(exc: Exception) -> bool:
    message = str(exc)
    return "AUTHORIZATION_ERROR" in message or "HTTP 401" in message or "HTTP 403" in message


def _redact(value: Any) -> Any:
    secret_values = [item for item in (os.getenv("SCOPUS_API_KEY"), os.getenv("WOS_API_KEY")) if item]
    if isinstance(value, dict):
        return {key: _redact(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            redacted = redacted.replace(secret, "***REDACTED***")
        redacted = re.sub(r"([?&]apiKey=)[^&]+", r"\1***REDACTED***", redacted)
        return redacted
    return value


@dataclass
class Publication:
    source: str
    source_id: str | None
    doi: str | None
    title: str | None
    year: str | None
    journal: str | None
    issn: str | None
    eissn: str | None
    raw: dict[str, Any]


@dataclass
class JournalMetric:
    source: str
    issn: str | None
    eissn: str | None
    journal: str | None
    year: str
    subject_code: str | None
    subject_name: str | None
    rank: str | None
    percentile: str | None
    cite_score: str | None
    quartile: str | None
    raw: dict[str, Any]


@dataclass
class AuthorMatch:
    author_id: str
    preferred_name: str
    orcid: str | None
    document_count: str | None
    affiliation_name: str | None
    affiliation_country: str | None
    subject_areas: list[str]
    raw: dict[str, Any]


@dataclass
class IpsRow:
    nome: str
    ssd: str
    numero_pubblicazione: str
    iris_articolo: str
    subject_category: str
    quartile: str


@dataclass
class DetailedRow:
    publication_number: str
    doi: str | None
    title: str | None
    year: str | None
    journal: str | None
    issn: str | None
    eissn: str | None
    citation: str
    source: str
    ranking_year: str | None
    subject_code: str | None
    subject_category: str | None
    percentile: str | None
    rank: str | None
    quartile: str | None
    cite_score: str | None


IPS_FIELDNAMES = [
    "NOME",
    "SSD",
    "numero pubblicazione",
    "IRIS Articoli su rivista - Periodo 2022-2026",
    "SUBJECT CATEGORY",
    "QUARTILE utilizzando wos o scopus o Scimago",
]


class ScopusClient:
    def __init__(self, api_key: str, insttoken: str | None = None) -> None:
        self.api_key = api_key
        self.insttoken = insttoken

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": self.api_key,
        }
        if self.insttoken:
            headers["X-ELS-Insttoken"] = self.insttoken
        return headers

    def author_retrieval(self, author_id: str) -> dict[str, Any]:
        url = f"{SCOPUS_BASE_URL}/author/author_id/{urllib.parse.quote(author_id)}?view=ENHANCED"
        return _http_get(url, self._headers())

    def author_search(self, query: str, count: int = 25, start: int = 0) -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "count": str(count),
                "start": str(start),
                "view": "STANDARD",
            }
        )
        url = f"{SCOPUS_BASE_URL}/search/author?{params}"
        return _http_get(url, self._headers())

    def search_publications_by_author(self, author_id: str, start_year: int, end_year: int, count: int = 25) -> dict[str, Any]:
        query = f"AU-ID({author_id}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}"
        params = urllib.parse.urlencode(
            {
                "query": query,
                "count": str(count),
                "start": "0",
                "view": "COMPLETE",
            }
        )
        url = f"{SCOPUS_BASE_URL}/search/scopus?{params}"
        return _http_get(url, self._headers())

    def search_publications_page(self, query: str, count: int = 25, start: int = 0, view: str = "COMPLETE") -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "count": str(count),
                "start": str(start),
                "view": view,
            }
        )
        url = f"{SCOPUS_BASE_URL}/search/scopus?{params}"
        return _http_get(url, self._headers())

    def serial_title(self, issn: str) -> dict[str, Any]:
        params = urllib.parse.urlencode({"issn": issn, "view": "CITESCORE"})
        url = f"{SCOPUS_BASE_URL}/serial/title?{params}"
        return _http_get(url, self._headers())

    @staticmethod
    def normalize_publications(payload: dict[str, Any]) -> list[Publication]:
        entries = payload.get("search-results", {}).get("entry", [])
        normalized: list[Publication] = []
        for entry in entries:
            normalized.append(
                Publication(
                    source="scopus",
                    source_id=entry.get("dc:identifier"),
                    doi=entry.get("prism:doi"),
                    title=entry.get("dc:title"),
                    year=entry.get("prism:coverDate", "")[:4] or None,
                    journal=entry.get("prism:publicationName"),
                    issn=entry.get("prism:issn"),
                    eissn=entry.get("prism:eIssn"),
                    raw=entry,
                )
            )
        return normalized

    @staticmethod
    def normalize_author_search(payload: dict[str, Any]) -> list[AuthorMatch]:
        entries = payload.get("search-results", {}).get("entry", [])
        normalized: list[AuthorMatch] = []
        for entry in entries:
            author_id = (entry.get("dc:identifier") or "").replace("AUTHOR_ID:", "")
            preferred = entry.get("preferred-name", {}) or {}
            affiliation = entry.get("affiliation-current", {}) or {}
            subject_area = entry.get("subject-area", [])
            if isinstance(subject_area, dict):
                subject_area = [subject_area]
            normalized.append(
                AuthorMatch(
                    author_id=author_id,
                    preferred_name=" ".join(filter(None, [preferred.get("given-name"), preferred.get("surname")])),
                    orcid=(entry.get("orcid") or "").strip("[]") or None,
                    document_count=entry.get("document-count"),
                    affiliation_name=affiliation.get("affiliation-name"),
                    affiliation_country=affiliation.get("affiliation-country"),
                    subject_areas=[item.get("$") for item in subject_area if isinstance(item, dict) and item.get("$")],
                    raw=entry,
                )
            )
        return normalized

    @staticmethod
    def normalize_serial_title(payload: dict[str, Any]) -> list[JournalMetric]:
        entries = payload.get("serial-metadata-response", {}).get("entry", [])
        normalized: list[JournalMetric] = []
        for entry in entries:
            subjects = entry.get("subject-area", [])
            if isinstance(subjects, dict):
                subjects = [subjects]
            subject_map = {item.get("@code"): item.get("$") for item in subjects if isinstance(item, dict)}

            years = entry.get("citeScoreYearInfoList", {}).get("citeScoreYearInfo", [])
            for year_info in years:
                year = year_info.get("@year")
                info_lists = year_info.get("citeScoreInformationList", [])
                if isinstance(info_lists, dict):
                    info_lists = [info_lists]
                for info_list in info_lists:
                    cite_infos = info_list.get("citeScoreInfo", [])
                    if isinstance(cite_infos, dict):
                        cite_infos = [cite_infos]
                    for cite_info in cite_infos:
                        ranks = cite_info.get("citeScoreSubjectRank", [])
                        if isinstance(ranks, dict):
                            ranks = [ranks]
                        for rank in ranks:
                            percentile = rank.get("percentile")
                            normalized.append(
                                JournalMetric(
                                    source="scopus",
                                    issn=entry.get("prism:issn"),
                                    eissn=entry.get("prism:eIssn"),
                                    journal=entry.get("dc:title"),
                                    year=year,
                                    subject_code=rank.get("subjectCode"),
                                    subject_name=subject_map.get(rank.get("subjectCode")),
                                    rank=rank.get("rank"),
                                    percentile=percentile,
                                    cite_score=cite_info.get("citeScore"),
                                    quartile=_quartile_from_percentile(percentile),
                                    raw=rank,
                                )
                            )
        return normalized

    def collect_publications_by_author(self, author_id: str, start_year: int, end_year: int, count: int = 25) -> list[Publication]:
        query = f"AU-ID({author_id}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}"
        start = 0
        publications: list[Publication] = []
        view = "COMPLETE"
        while True:
            try:
                payload = self.search_publications_page(query=query, count=count, start=start, view=view)
            except ApiError as exc:
                if view == "COMPLETE" and _is_authorization_error(exc):
                    view = "STANDARD"
                    payload = self.search_publications_page(query=query, count=count, start=start, view=view)
                else:
                    raise
            batch = self.normalize_publications(payload)
            publications.extend(batch)
            total_str = payload.get("search-results", {}).get("opensearch:totalResults", "0")
            total = int(total_str)
            start += count
            if start >= total or not batch:
                break
        return publications


class WosClient:
    def __init__(self, api_key: str, base_url: str = WOS_BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-ApiKey": self.api_key,
        }

    def search_documents(self, query: str, limit: int = 25, page: int = 1, db: str = "WOS") -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "limit": str(limit),
                "page": str(page),
                "db": db,
            }
        )
        url = f"{self.base_url}/documents?{params}"
        return _http_get(url, self._headers())

    def journal_by_issn(self, issn: str) -> dict[str, Any]:
        url = f"{self.base_url}/journals?{urllib.parse.urlencode({'issn': issn})}"
        return _http_get(url, self._headers())

    @staticmethod
    def normalize_publications(payload: dict[str, Any]) -> list[Publication]:
        hits = payload.get("hits", [])
        normalized: list[Publication] = []
        for hit in hits:
            identifiers = hit.get("identifiers", {}) or {}
            source = hit.get("source", {}) or {}
            names = source.get("sourceTitle") or source.get("title")
            normalized.append(
                Publication(
                    source="wos",
                    source_id=identifiers.get("uid"),
                    doi=identifiers.get("doi"),
                    title=hit.get("title"),
                    year=str(hit.get("publishYear")) if hit.get("publishYear") else None,
                    journal=names,
                    issn=source.get("issn"),
                    eissn=source.get("eissn"),
                    raw=hit,
                )
            )
        return normalized


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ApiError(f"Missing required environment variable: {name}")
    return value


def _quartile_from_percentile(percentile: str | None) -> str | None:
    if percentile is None:
        return None
    try:
        value = float(percentile)
    except ValueError:
        return None
    if value >= 75:
        return "Q1"
    if value >= 50:
        return "Q2"
    if value >= 25:
        return "Q3"
    return "Q4"


def _safe_year(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _authors_as_text(raw_authors: Any) -> str:
    if not raw_authors:
        return ""
    authors = raw_authors if isinstance(raw_authors, list) else [raw_authors]
    chunks = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        surname = author.get("surname")
        initials = author.get("initials")
        if surname and initials:
            clean_initials = initials.rstrip(".")
            chunks.append(f"{surname}, {clean_initials}.")
        elif author.get("authname"):
            chunks.append(author["authname"])
    return ", ".join(chunks)


def _citation_from_publication(publication: Publication) -> str:
    raw = publication.raw
    authors = _authors_as_text(raw.get("author"))
    year = publication.year or ""
    title = publication.title or ""
    journal = publication.journal or ""
    volume = raw.get("prism:volume")
    issue = raw.get("prism:issueIdentifier")
    pages = raw.get("prism:pageRange") or raw.get("article-number")
    doi = publication.doi
    parts = []
    if authors:
        parts.append(authors)
    if year:
        parts.append(f"({year}).")
    if title:
        parts.append(title + ".")
    if journal:
        journal_part = journal
        if volume:
            journal_part += f", {volume}"
            if issue:
                journal_part += f"({issue})"
        if pages:
            journal_part += f", {pages}"
        journal_part += "."
        parts.append(journal_part)
    if doi:
        parts.append(f"https://doi.org/{doi}")
    return " ".join(parts).strip()


def _best_metric(metrics: list[JournalMetric], publication_year: str | None) -> JournalMetric | None:
    same_year = [item for item in metrics if item.year == publication_year]
    candidates = same_year or metrics
    if not candidates:
        return None

    def sort_key(item: JournalMetric) -> tuple[int, int, float]:
        quartile_rank = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(item.quartile or "", 99)
        misc_penalty = 1 if item.subject_name and "miscellaneous" in item.subject_name.lower() else 0
        try:
            percentile = -float(item.percentile or 0)
        except ValueError:
            percentile = 0.0
        return quartile_rank, misc_penalty, percentile

    return sorted(candidates, key=sort_key)[0]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def _ips_row_to_csv_dict(row: IpsRow) -> dict[str, str]:
    return {
        "NOME": row.nome,
        "SSD": row.ssd,
        "numero pubblicazione": row.numero_pubblicazione,
        "IRIS Articoli su rivista - Periodo 2022-2026": row.iris_articolo,
        "SUBJECT CATEGORY": row.subject_category,
        "QUARTILE utilizzando wos o scopus o Scimago": row.quartile,
    }


def build_scopus_tables(author_id: str, researcher_name: str, ssd: str, start_year: int, end_year: int) -> tuple[list[IpsRow], list[DetailedRow]]:
    client = ScopusClient(_require_env("SCOPUS_API_KEY"), os.getenv("SCOPUS_INSTTOKEN"))
    publications = client.collect_publications_by_author(author_id, start_year, end_year)
    publications = sorted(publications, key=lambda item: (_safe_year(item.year), item.title or ""))

    metrics_cache: dict[str, list[JournalMetric]] = {}
    ips_rows: list[IpsRow] = []
    detailed_rows: list[DetailedRow] = []

    for index, publication in enumerate(publications, start=1):
        metric_key = publication.issn or publication.eissn or ""
        metrics: list[JournalMetric] = []
        if metric_key:
            if metric_key not in metrics_cache:
                try:
                    payload = client.serial_title(metric_key.replace("-", ""))
                    metrics_cache[metric_key] = client.normalize_serial_title(payload)
                except ApiError as exc:
                    if _is_authorization_error(exc):
                        metrics_cache[metric_key] = []
                    else:
                        raise
            metrics = metrics_cache[metric_key]

        publication_metrics = [item for item in metrics if item.year == publication.year] or metrics
        citation = _citation_from_publication(publication)
        for metric in publication_metrics:
            detailed_rows.append(
                DetailedRow(
                    publication_number=str(index),
                    doi=publication.doi,
                    title=publication.title,
                    year=publication.year,
                    journal=publication.journal,
                    issn=publication.issn,
                    eissn=publication.eissn,
                    citation=citation,
                    source="scopus",
                    ranking_year=metric.year,
                    subject_code=metric.subject_code,
                    subject_category=metric.subject_name,
                    percentile=metric.percentile,
                    rank=metric.rank,
                    quartile=metric.quartile,
                    cite_score=metric.cite_score,
                )
            )

        best = _best_metric(publication_metrics, publication.year)
        ips_rows.append(
            IpsRow(
                nome=researcher_name,
                ssd=ssd,
                numero_pubblicazione=str(index),
                iris_articolo=citation,
                subject_category=best.subject_name or "",
                quartile=(best.quartile or "").replace("Q", "") if best else "",
            )
        )

    return ips_rows, detailed_rows


def cmd_scopus_author(args: argparse.Namespace) -> None:
    client = ScopusClient(_require_env("SCOPUS_API_KEY"), os.getenv("SCOPUS_INSTTOKEN"))
    _print(client.author_retrieval(args.author_id))


def cmd_scopus_author_search(args: argparse.Namespace) -> None:
    client = ScopusClient(_require_env("SCOPUS_API_KEY"), os.getenv("SCOPUS_INSTTOKEN"))
    payload = client.author_search(args.query, count=args.count, start=args.start)
    if args.normalized:
        _print([asdict(item) for item in client.normalize_author_search(payload)])
        return
    _print(payload)


def cmd_scopus_pubs(args: argparse.Namespace) -> None:
    client = ScopusClient(_require_env("SCOPUS_API_KEY"), os.getenv("SCOPUS_INSTTOKEN"))
    payload = client.search_publications_by_author(args.author_id, args.start_year, args.end_year, args.count)
    if args.normalized:
        _print([asdict(item) for item in client.normalize_publications(payload)])
        return
    _print(payload)


def cmd_scopus_serial(args: argparse.Namespace) -> None:
    client = ScopusClient(_require_env("SCOPUS_API_KEY"), os.getenv("SCOPUS_INSTTOKEN"))
    payload = client.serial_title(args.issn)
    if args.normalized:
        _print([asdict(item) for item in client.normalize_serial_title(payload)])
        return
    _print(payload)


def cmd_wos_pubs(args: argparse.Namespace) -> None:
    client = WosClient(_require_env("WOS_API_KEY"))
    payload = client.search_documents(args.query, limit=args.limit, page=args.page, db=args.db)
    if args.normalized:
        _print([asdict(item) for item in client.normalize_publications(payload)])
        return
    _print(payload)


def cmd_wos_journal(args: argparse.Namespace) -> None:
    client = WosClient(_require_env("WOS_API_KEY"))
    _print(client.journal_by_issn(args.issn))


def cmd_scopus_ips_table(args: argparse.Namespace) -> None:
    ips_rows, _ = build_scopus_tables(args.author_id, args.researcher_name, args.ssd, args.start_year, args.end_year)
    payload = [_ips_row_to_csv_dict(item) for item in ips_rows]
    if args.output:
        _write_csv(Path(args.output), payload, IPS_FIELDNAMES)
        print(args.output)
        return
    _print(payload)


def cmd_scopus_detailed_table(args: argparse.Namespace) -> None:
    _, detailed_rows = build_scopus_tables(args.author_id, args.researcher_name, args.ssd, args.start_year, args.end_year)
    payload = [asdict(item) for item in detailed_rows]
    if args.output:
        _write_csv(Path(args.output), payload, list(payload[0].keys()) if payload else list(DetailedRow.__annotations__.keys()))
        print(args.output)
        return
    _print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Scopus and Web of Science APIs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scopus_author = subparsers.add_parser("scopus-author", help="Retrieve a Scopus author profile.")
    scopus_author.add_argument("--author-id", required=True)
    scopus_author.set_defaults(func=cmd_scopus_author)

    scopus_author_search = subparsers.add_parser("scopus-author-search", help="Search Scopus authors.")
    scopus_author_search.add_argument("--query", required=True)
    scopus_author_search.add_argument("--count", type=int, default=25)
    scopus_author_search.add_argument("--start", type=int, default=0)
    scopus_author_search.add_argument("--normalized", action="store_true")
    scopus_author_search.set_defaults(func=cmd_scopus_author_search)

    scopus_pubs = subparsers.add_parser("scopus-pubs", help="Search Scopus publications by author id.")
    scopus_pubs.add_argument("--author-id", required=True)
    scopus_pubs.add_argument("--start-year", type=int, default=2022)
    scopus_pubs.add_argument("--end-year", type=int, default=2026)
    scopus_pubs.add_argument("--count", type=int, default=25)
    scopus_pubs.add_argument("--normalized", action="store_true")
    scopus_pubs.set_defaults(func=cmd_scopus_pubs)

    scopus_serial = subparsers.add_parser("scopus-serial", help="Retrieve Scopus serial title metadata.")
    scopus_serial.add_argument("--issn", required=True)
    scopus_serial.add_argument("--normalized", action="store_true")
    scopus_serial.set_defaults(func=cmd_scopus_serial)

    scopus_ips_table = subparsers.add_parser("scopus-ips-table", help="Build the IPS-style table from Scopus.")
    scopus_ips_table.add_argument("--author-id", required=True)
    scopus_ips_table.add_argument("--researcher-name", required=True)
    scopus_ips_table.add_argument("--ssd", required=True)
    scopus_ips_table.add_argument("--start-year", type=int, default=2022)
    scopus_ips_table.add_argument("--end-year", type=int, default=2026)
    scopus_ips_table.add_argument("--output")
    scopus_ips_table.set_defaults(func=cmd_scopus_ips_table)

    scopus_detailed_table = subparsers.add_parser("scopus-detailed-table", help="Build the detailed article/category/quartile table from Scopus.")
    scopus_detailed_table.add_argument("--author-id", required=True)
    scopus_detailed_table.add_argument("--researcher-name", required=True)
    scopus_detailed_table.add_argument("--ssd", required=True)
    scopus_detailed_table.add_argument("--start-year", type=int, default=2022)
    scopus_detailed_table.add_argument("--end-year", type=int, default=2026)
    scopus_detailed_table.add_argument("--output")
    scopus_detailed_table.set_defaults(func=cmd_scopus_detailed_table)

    wos_pubs = subparsers.add_parser("wos-pubs", help="Search Web of Science documents.")
    wos_pubs.add_argument("--query", required=True)
    wos_pubs.add_argument("--limit", type=int, default=25)
    wos_pubs.add_argument("--page", type=int, default=1)
    wos_pubs.add_argument("--db", default="WOS")
    wos_pubs.add_argument("--normalized", action="store_true")
    wos_pubs.set_defaults(func=cmd_wos_pubs)

    wos_journal = subparsers.add_parser("wos-journal", help="Retrieve Web of Science journal metadata by ISSN.")
    wos_journal.add_argument("--issn", required=True)
    wos_journal.set_defaults(func=cmd_wos_journal)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
