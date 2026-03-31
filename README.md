# IPS Backend

Backend service and CLI utilities for the IPS workflow.

This repository contains:

- Scopus API client logic
- Web of Science API client logic
- normalization utilities for publication records
- CSV builders for IPS and detailed outputs
- a small local HTTP server
- basic tests

## Files

- `ips_api.py`
- `server.py`
- `smoke_test.sh`
- `.env.example`
- `tests/test_normalization.py`

## Environment variables

Set only the credentials you actually have.

```bash
export SCOPUS_API_KEY="..."
export WOS_API_KEY="..."
```

Optional:

```bash
export SCOPUS_INSTTOKEN="..."
export WOS_API_BASE_URL="https://api.clarivate.com/apis/wos-starter/v1"
```

## CLI examples

Resolve a Scopus author profile:

```bash
python3 ips_api.py scopus-author --author-id 7004212771
```

Search Scopus publications by author id:

```bash
python3 ips_api.py scopus-pubs --author-id 7004212771 --start-year 2022 --end-year 2026
```

Generate the IPS-style CSV from Scopus:

```bash
python3 ips_api.py scopus-ips-table \
  --author-id 50060939700 \
  --researcher-name "EMANUELE BOSI" \
  --ssd "BIO/18" \
  --start-year 2022 \
  --end-year 2026 \
  --output /tmp/emanuele_bosi_scopus_ips.csv
```

Generate the detailed CSV from Scopus:

```bash
python3 ips_api.py scopus-detailed-table \
  --author-id 50060939700 \
  --researcher-name "EMANUELE BOSI" \
  --ssd "BIO/18" \
  --start-year 2022 \
  --end-year 2026 \
  --output /tmp/emanuele_bosi_scopus_detailed.csv
```

Run the local HTTP service:

```bash
python3 server.py
```

Then query it:

```bash
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/api/scopus/author-search?query=authlast%28Bosi%29%20and%20authfirst%28Emanuele%29"
```

## Notes

- keep provider API keys only on the backend
- enable CORS for the frontend origin
- quartile/category enrichment may still need refinement depending on provider coverage

## Render deploy

This repository is ready for a simple Render web service deploy.

Recommended settings:

- service type: `Web Service`
- runtime: `Python`
- build command: leave empty
- start command: `python3 server.py`

Environment variables to set in Render:

- `SCOPUS_API_KEY`
- `SCOPUS_INSTTOKEN` if your Scopus access needs it
- `WOS_API_KEY` only if you actually use Web of Science endpoints
- `WOS_API_BASE_URL` only if you need a non-default base URL

Render will inject `PORT` automatically. The server is configured to listen on it.

After deploy, test:

```bash
curl "https://your-service.onrender.com/health"
```
