import importlib.util
from pathlib import Path


MODULE_PATH = Path("/home/bosi/ips_api_prototype/ips_api.py")
spec = importlib.util.spec_from_file_location("ips_api", MODULE_PATH)
ips_api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ips_api)


def test_scopus_normalization():
    payload = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:123",
                    "prism:doi": "10.1000/example",
                    "dc:title": "Example title",
                    "prism:coverDate": "2024-06-10",
                    "prism:publicationName": "Example Journal",
                    "prism:issn": "12345678",
                    "prism:eIssn": "87654321",
                }
            ]
        }
    }

    pubs = ips_api.ScopusClient.normalize_publications(payload)

    assert len(pubs) == 1
    assert pubs[0].source == "scopus"
    assert pubs[0].doi == "10.1000/example"
    assert pubs[0].year == "2024"


def test_wos_normalization():
    payload = {
        "hits": [
            {
                "title": "WOS example",
                "publishYear": 2023,
                "identifiers": {
                    "uid": "WOS:001",
                    "doi": "10.1000/wos",
                },
                "source": {
                    "sourceTitle": "WOS Journal",
                    "issn": "11112222",
                    "eissn": "33334444",
                },
            }
        ]
    }

    pubs = ips_api.WosClient.normalize_publications(payload)

    assert len(pubs) == 1
    assert pubs[0].source == "wos"
    assert pubs[0].journal == "WOS Journal"
    assert pubs[0].year == "2023"


def test_quartile_from_percentile():
    assert ips_api._quartile_from_percentile("90") == "Q1"
    assert ips_api._quartile_from_percentile("55") == "Q2"
    assert ips_api._quartile_from_percentile("30") == "Q3"
    assert ips_api._quartile_from_percentile("10") == "Q4"


def test_citation_author_initials_are_not_double_dotted():
    publication = ips_api.Publication(
        source="scopus",
        source_id="SCOPUS_ID:1",
        doi="10.1000/example",
        title="Example",
        year="2024",
        journal="Journal",
        issn="12345678",
        eissn=None,
        raw={
            "author": [
                {"surname": "Bosi", "initials": "E."},
                {"surname": "Marchetti", "initials": "P."},
            ],
            "prism:volume": "1",
            "prism:issueIdentifier": "2",
            "prism:pageRange": "3-4",
        },
    )

    citation = ips_api._citation_from_publication(publication)

    assert "Bosi, E.." not in citation
    assert "Marchetti, P.." not in citation
    assert "Bosi, E." in citation
