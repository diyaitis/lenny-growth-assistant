# Knowledge base data

This app is grounded on real transcripts from **Lenny's Podcast**, sourced from the
official free starter pack: [`LennysNewsletter/lennys-newsletterpodcastdata`](https://github.com/LennysNewsletter/lennys-newsletterpodcastdata)
(50 podcast transcripts, AI-friendly markdown, published by Lenny's Newsletter).

## Why the raw transcripts are not committed to this repo

The starter pack's license permits personal, non-commercial use, remixing, and
building projects on top of it — **but it explicitly prohibits redistributing the
raw dataset files**. Committing the `.md` transcripts into this (public) repo would
violate that term. Instead:

- `data/transcripts/` is where transcripts live **locally** and is git-ignored.
- `scripts/fetch_transcripts.sh` reproduces the exact demo corpus by cloning the
  official repo and copying a curated subset into `data/transcripts/`.
- `data/corpus_manifest.json` records *which* episodes make up the demo corpus
  (titles, guests, source URLs) — metadata only, no copyrighted body text — so the
  selection is reproducible and auditable without redistributing the content.

This is documented as an explicit **risk/scope decision** in `PRD.md` (see
"Data licensing").

## Demo corpus

10 episodes selected for growth/PM relevance (~186k words total): Elena Verna,
Amol Avasare (Claude growth), Jason Cohen (retention/NRR framework), Grant Lee
(Gamma), Evan Spiegel, Mark Pincus, Brian Halligan, Nikhyl Singhal, Jason Lemkin,
Stewart Butterfield. See `corpus_manifest.json` for exact source URLs.

## Getting the data locally

```bash
bash scripts/fetch_transcripts.sh
```

This clones the official starter-pack repo into a temp directory, copies the
curated subset (or `--all` for all 50 free episodes) into `data/transcripts/`,
and discards the temp clone. Then run ingestion:

```bash
cd backend
python scripts/ingest.py
```

## Swapping in your own corpus / the full paid archive

Drop any `.md` files with the same YAML frontmatter shape (`title`, `date`, `guest`,
`post_url`, `description`) into `data/transcripts/` and re-run `ingest.py` — the
ingestion pipeline is not hardcoded to this specific dataset. The paid full archive
at [lennysdata.com](https://www.lennysdata.com) (313 podcast transcripts) uses the
same file format and would drop in without code changes.
