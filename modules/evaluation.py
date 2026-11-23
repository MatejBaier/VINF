import json
import re
import time

import config





# systems in the order of the tables
OLD = "old index"
LUCENE = "Lucene"
LUCENE_FIELDS = "Lucene + fields"
GOOGLE = "Google"
DOMAIN = "a-z-animals"

TIME_REPEATS = 5            # every query is run more times, the average time is used

ANIMAL_URL_REGEX = re.compile(r"a-z-animals\.com/animals/([a-z0-9-]+)")         # URL from Google / a-z search -> slug





def load_queries():
    with open(config.EVALUATION_QUERIES_FILE, encoding="utf-8") as f:
        return json.load(f)["queries"]


def url_to_slug(url):
    # https://a-z-animals.com/animals/arctic-fox/ -> arctic-fox, other pages (blog articles) stay as they are, they are never relevant
    match = ANIMAL_URL_REGEX.search(url.lower())
    if match:
        return match.group(1)
    return url


def load_external():
    # system, query id, rank, url -> {system: {query id: [slug, ...]}}
    if not config.EVALUATION_EXTERNAL_FILE.exists():
        return {}

    results = {}
    with open(config.EVALUATION_EXTERNAL_FILE, encoding="utf-8") as f:
        next(f)                 # header
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue

            system, query_id, rank, url = line.split("\t")
            results.setdefault(system, {}).setdefault(query_id, []).append((int(rank), url_to_slug(url)))

    # animal page and its pictures page are one result
    for system in results:
        for query_id, ranked in results[system].items():
            slugs = []
            for rank, slug in sorted(ranked):
                if slug not in slugs:
                    slugs.append(slug)
            results[system][query_id] = slugs
    return results





# metrics, results = list of slugs from the best, relevant = set of slugs

def precision_at(results, relevant, k):
    found = 0
    for slug in results[:k]:
        if slug in relevant:
            found += 1
    return found / k


def recall_at(results, relevant, k):
    found = 0
    for slug in results[:k]:
        if slug in relevant:
            found += 1
    return found / len(relevant)


def reciprocal_rank(results, relevant):
    # 1 / position of the first relevant result, 0 if there is none
    for rank, slug in enumerate(results, 1):
        if slug in relevant:
            return 1 / rank
    return 0.0


def evaluate(results, relevant):
    return {
        "P@5": precision_at(results, relevant, 5),
        "P@10": precision_at(results, relevant, 10),
        "R@10": recall_at(results, relevant, 10),
        "RR": reciprocal_rank(results, relevant),
    }


METRICS = ["P@5", "P@10", "R@10", "RR"]





def timed(function, repeats=TIME_REPEATS):
    # result of the function and its average time in ms, the first run warms up caches
    result = function()
    start = time.perf_counter()
    for _ in range(repeats):
        function()
    milliseconds = (time.perf_counter() - start) * 1000 / repeats
    return result, milliseconds


def run_old(queries):
    # old index from part 1 with the best scoring from part 1
    from modules import search as old_search

    index = old_search.load_index()
    if index is None:
        return None

    runs = {}
    for query in queries:
        def function():
            return old_search.search(query["text"], index, config.OLD_SCORING, config.OLD_IDF, top_k=config.EVALUATION_TOP_K)

        results, milliseconds = timed(function)
        runs[query["id"]] = ([doc["slug"] for score, doc in results], milliseconds)
    return runs


def run_lucene(queries):
    # the same text as in the old index, and the query written with fields (if the query has one)
    from modules import lucene_search

    prepared = lucene_search.prepare()
    if prepared is None:
        return None, None
    searcher, parsers = prepared

    def lucene_run(text):
        def function():
            return lucene_search.search(text, searcher, parsers, top_k=config.EVALUATION_TOP_K)

        (results, total, search_ms), milliseconds = timed(function)
        return [result["slug"] for result in results], milliseconds

    text_runs = {}
    field_runs = {}
    for query in queries:
        text_runs[query["id"]] = lucene_run(query["text"])
        field_runs[query["id"]] = lucene_run(query["lucene"] or query["text"])
    return text_runs, field_runs





def average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def format_table(header, rows, wiki=False):
    # aligned text table, or DokuWiki table (^ header ^, | cell |) which can be pasted to the wiki
    if wiki:
        lines = ["^ " + " ^ ".join(header) + " ^"]
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    widths = []
    for column in range(len(header)):
        widths.append(max(len(str(row[column])) for row in [header] + rows))

    lines = []
    for row in [header] + rows:
        cells = []
        for column, cell in enumerate(row):
            cells.append(f"{cell:<{widths[column]}}")
        lines.append(" " + "  ".join(cells).rstrip())
    lines.insert(1, " " + "  ".join("-" * width for width in widths))
    return "\n".join(lines)


def number(value):
    return f"{value:.2f}"


def summary_table(systems, queries, scores, times, wiki):
    header = ["System"] + METRICS + ["Time (ms)"]
    rows = []
    for system in systems:
        row = [system]
        for metric in METRICS:
            row.append(number(average([scores[system][query["id"]][metric] for query in queries])))
        if system in times:
            row.append(f"{average(list(times[system].values())):.1f}")
        else:
            row.append("-")
        rows.append(row)
    return format_table(header, rows, wiki)


def per_query_table(systems, queries, scores, metric, wiki):
    header = ["Query", "Relevant"] + systems
    rows = []
    for query in queries:
        row = [f"{query['id']} {query['text']}", str(len(query["relevant"]))]
        for system in systems:
            row.append(number(scores[system][query["id"]][metric]))
        rows.append(row)
    return format_table(header, rows, wiki)


def top_results_table(systems, query, results, wiki, top=5):
    # top 5 of every system, relevant results are marked with * (bold in the wiki)
    header = ["Rank"] + systems
    relevant = set(query["relevant"])
    rows = []
    for rank in range(top):
        row = [str(rank + 1)]
        for system in systems:
            ranked = results[system][query["id"]]
            if rank >= len(ranked):
                row.append("")
                continue

            slug = ranked[rank]
            if slug not in relevant:
                row.append(slug)
            elif wiki:
                row.append(f"**{slug}**")
            else:
                row.append(f"*{slug}")
        rows.append(row)
    return format_table(header, rows, wiki)


def build_report(systems, queries, results, scores, times, wiki=False):
    parts = []

    parts.append(f"Summary (average over {len(queries)} queries, top {config.EVALUATION_TOP_K})")
    parts.append(summary_table(systems, queries, scores, times, wiki))

    parts.append("\nP@10 per query")
    parts.append(per_query_table(systems, queries, scores, "P@10", wiki))

    parts.append("\nRR (1 / rank of the first relevant result) per query")
    parts.append(per_query_table(systems, queries, scores, "RR", wiki))

    parts.append("\nTop 5 per query (* = relevant)")
    for query in queries:
        lucene_query = query["lucene"] or query["text"]
        parts.append(f"\n{query['id']}: {query['need']}")
        parts.append(f" text query:   {query['text']}")
        parts.append(f" Lucene query: {lucene_query}")
        parts.append(top_results_table(systems, query, results, wiki))

    return "\n".join(parts)





def run():
    queries = load_queries()

    results = {}        # system -> query id -> list of slugs
    times = {}          # system -> query id -> ms

    old_runs = run_old(queries)
    if old_runs:
        results[OLD] = {query_id: slugs for query_id, (slugs, ms) in old_runs.items()}
        times[OLD] = {query_id: ms for query_id, (slugs, ms) in old_runs.items()}

    text_runs, field_runs = run_lucene(queries)
    if text_runs:
        for system, runs in ((LUCENE, text_runs), (LUCENE_FIELDS, field_runs)):
            results[system] = {query_id: slugs for query_id, (slugs, ms) in runs.items()}
            times[system] = {query_id: ms for query_id, (slugs, ms) in runs.items()}

    # Google and a-z search can not be run from the program, their results are written by hand
    external = load_external()
    for system in (GOOGLE, DOMAIN):
        if system in external:
            results[system] = {query["id"]: external[system].get(query["id"], []) for query in queries}

    systems = [system for system in (OLD, LUCENE, LUCENE_FIELDS, GOOGLE, DOMAIN) if system in results]
    if not systems:
        print("Nothing to evaluate - build the indexes first")
        return

    scores = {}
    for system in systems:
        scores[system] = {}
        for query in queries:
            scores[system][query["id"]] = evaluate(results[system][query["id"]], set(query["relevant"]))

    print()
    print(build_report(systems, queries, results, scores, times))

    with open(config.EVALUATION_RESULTS_FILE, "w", encoding="utf-8") as f:
        f.write(build_report(systems, queries, results, scores, times))
        f.write("\n\n\n===== DokuWiki tables =====\n\n")
        f.write(build_report(systems, queries, results, scores, times, wiki=True))
        f.write("\n")
    print(f"\nSaved -> {config.EVALUATION_RESULTS_FILE}")
