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


#=========================================================================


# spark
SPARK_MASTER = "local[*]"
SPARK_DRIVER_MEMORY = "16g"
SPARK_HOST = "127.0.0.1"          # Spark driver listens only inside this computer, works on any network (Wi-Fi, VPN)

RAW_PAGES_FILE = DATA_DIR / "raw_pages.jsonl"       # ZIP converted for Spark, one page per line
SPARK_DIR = DATA_DIR / "spark"
SPARK_ANIMALS_DIR = SPARK_DIR / "animals"           # Spark output, part-* files with one animal per line




# wiki dump
WIKI_DUMP_FILE = Path.home() / "Desktop" / "enwiki-20261001-pages-articles.xml.bz2"
WIKI_SAMPLE_FILE = Path.home() / "Desktop" / "enwiki-sample.xml.bz2"     # first 6938 pages of the dump, for development
WIKI_TAXA_DIR = SPARK_DIR / "wiki_taxa"                 # animal articles with taxonomy or breed infobox, one per line
WIKI_REDIRECTS_DIR = SPARK_DIR / "wiki_redirects"       # redirects pointing to animal articles (Vulpes vulpes -> Red fox)
WIKI_TAXONOMY_DIR = SPARK_DIR / "wiki_taxonomy"         # taxonomy templates, rank and parent of every taxon (Vulpes -> Vulpini)

# join
ANIMALS_WIKI_DIR = SPARK_DIR / "animals_wiki"           # full outer join of a-z animals and wiki animals, input for the indexer
JOIN_UNMATCHED_FILE = DATA_DIR / "join_unmatched.tsv"   # a-z animals without a wiki page
JOIN_DUPLICATES_FILE = DATA_DIR / "join_duplicates.tsv" # wiki animals with the same name as an a-z animal, possible missed joins


# lucene
LUCENE_INDEX_DIR = DATA_DIR / "lucene_index"

# fields searched when the query has no field name, with their boosts, a-z and wiki records have the same fields
LUCENE_FIELD_BOOSTS = {
    "name": 4.0,
    "also_known_as": 3.0,
    "scientific_name": 3.0,
    "summary": 2.0,
    "locations": 1.5,
    "categories": 1.5,
    "origin": 1.5,
    "facts": 1.0,
    "article": 1.0,
}

# old index (part 1) in comparisons, the best combination from part 1
OLD_SCORING = "spread"
OLD_IDF = "standard"


# evaluation
EVALUATION_DIR = PROJECT_DIR / "evaluation"
EVALUATION_QUERIES_FILE = EVALUATION_DIR / "queries.json"               # queries and relevant animals (judged by hand)
EVALUATION_EXTERNAL_FILE = EVALUATION_DIR / "external_results.tsv"      # results of Google and a-z-animals search, written by hand
EVALUATION_RESULTS_FILE = EVALUATION_DIR / "results.txt"                # output of the evaluation, text tables for the wiki
EVALUATION_TOP_K = 10
