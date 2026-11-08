from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

DATA_DIR = PROJECT_DIR / "data"
RAW_ZIP = DATA_DIR / "raw_htmls.zip"
FRONTIER_FILE = DATA_DIR / "URL_frontier_TO_BE_DOWNLOADED.tsv"
VISITED_FILE = DATA_DIR / "URL_visited.tsv"
HISTORY_FILE = DATA_DIR / "history.tsv"

BASE_URL = "https://a-z-animals.com"
SEED_URL = BASE_URL + "/animals/"

USER_AGENT_BOT = "VINF-AnimalCrawler (FIIT STU school project)"
USER_AGENT_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
USER_AGENT = USER_AGENT_BROWSER

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",

}


DISALLOWED_PATHS = [
    "/recommends/",
    "/wp-admin/",
    "/workers/cw-cache/",
    "/workers/alm-cache/",
    "/cdn-cgi/",
    "/b66d/",
    "/go/",
    "/t/impression",
    "/?s=",
    "/search/",

]

SLEEP_BASE = 5
SLEEP_JITTER = 3

BACKOFF_BASE = 30
BACKOFF_MULTIPLIER = 2
BACKOFF_TRIES = 3

CONNECTION_TIMEOUT = 10
READ_TIMEOUT = 30


#=========================================================================


# extractor
EXTRACTED_FILE = DATA_DIR / "extracted.jsonl"       # one animal per line
MISSING_FILE = DATA_DIR / "missing_fields.tsv"
SKIPPED_FILE = DATA_DIR / "skipped_pages.tsv"


# tokenizer
MIN_TOKEN_LENGTH = 2


# indexer
INDEX_DIR = DATA_DIR / "index"
DOCS_FILE = INDEX_DIR / "docs.tsv"                  # doc_index, slug, name, length, norm, section_weight
POSTINGS_FILE = INDEX_DIR / "postings.tsv"          # term, df, doc:tf:section_weight,...

FIELD_BOOSTS = {
    "name": 3,
    "also_known_as": 3,
    "locations": 2,
    "class": 2, "diet": 2, "activity": 2, "social": 2, "status": 2, "danger_level": 2,
    "adaptations": 2,
    "behaviors": 2,
    "did_you_know": 2,
}

# search
TOP_K = 10
SPREAD_BASE = 0.5       # spread scoring: base part, coverage (0..1) is added to it

TIKTOKEN_ENCODING = "o200k_base"