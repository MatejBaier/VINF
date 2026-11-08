import math
from collections import Counter

import config
from modules.indexer import collection_frequencies, load
from modules.tokenizer import tokenize





def idf_standard(df, n_docs, cf, total_tokens):
    # log(N / df), term in every document has idf 0
    return math.log10(n_docs / df)


def idf_smooth(df, n_docs, cf, total_tokens):
    # log((N + 1) / (df + 1)) + 1, never 0, common terms still count a little
    return math.log10((n_docs + 1) / (df + 1)) + 1


def idf_squared(df, n_docs, cf, total_tokens):
    # log(N / df) ^ 2, rare terms get much more weight than common ones
    return math.log10(n_docs / df) ** 2


def idf_linear(df, n_docs, cf, total_tokens):
    # 1 - df / N, without logarithm, from 0 (term in every document) to almost 1
    return 1 - df / n_docs


def idf_shifted(df, n_docs, cf, total_tokens):
    # log(N / df) + 0.5, like standard, but term in every document still has 0.5
    return math.log10(n_docs / df) + 0.5


IDF_METHODS = {
    "standard": idf_standard,
    "smooth": idf_smooth,
    "squared": idf_squared,
    "linear": idf_linear,
    "shifted": idf_shifted,
}

# descriptions shown in the menu
IDF_DESCRIPTIONS = {
    "standard": "log(N / df) - classic idf, term in every document = 0",
    "smooth": "log((N + 1) / (df + 1)) + 1 - never 0, common terms still count a little",
    "squared": "log(N / df) ^ 2 - rare terms much stronger than common ones",
    "linear": "1 - df / N - without logarithm, from 0 to almost 1",
    "shifted": "log(N / df) + 0.5 - classic idf, but common terms still have 0.5",
}





# scoring functions, each returns {doc_index: score}

def score_tfidf(query_counts, index, idf):
    # sum of tf * idf for every query term
    scores = Counter()

    for term in query_counts:
        for doc_index, tf, section_weight in index["postings"][term]:
            scores[doc_index] += tf * idf[term]

    return scores


def score_cosine(query_counts, index, idf):
    # lnc.ltc (lecture), document and query vectors are normalized by their length
    docs = index["docs"]

    query_weights = {}
    for term, tf in query_counts.items():
        query_weights[term] = (1 + math.log10(tf)) * idf[term]

    query_norm = 0
    for weight in query_weights.values():
        query_norm += weight ** 2
    query_norm = math.sqrt(query_norm)

    if query_norm == 0:
        query_norm = 1      # all query terms have idf 0

    scores = Counter()

    for term, query_weight in query_weights.items():
        for doc_index, tf, section_weight in index["postings"][term]:
            doc_norm = docs[doc_index]["norm"]
            if doc_norm == 0:
                continue        # empty document

            doc_weight = (1 + math.log10(tf)) / doc_norm
            scores[doc_index] += (query_weight / query_norm) * doc_weight

    return scores


def score_share(query_counts, index, idf):
    # sum of idf * tf / cf
    scores = Counter()

    for term in query_counts:
        cf = index["cf"][term]
        if cf == 0:
            continue

        for doc_index, tf, section_weight in index["postings"][term]:
            scores[doc_index] += idf[term] * tf / cf

    return scores


def score_spread(query_counts, index, idf):
    # sum of (1 + log tf) * idf * (SPREAD_BASE + coverage)
    docs = index["docs"]
    scores = Counter()

    for term in query_counts:
        for doc_index, tf, section_weight in index["postings"][term]:
            doc_section_weight = docs[doc_index]["section_weight"]

            if doc_section_weight > 0:
                coverage = min(section_weight / doc_section_weight, 1)       # part of the document with the term, 0..1
            else:
                coverage = 0

            scores[doc_index] += (1 + math.log10(tf)) * idf[term] * (config.SPREAD_BASE + coverage)

    return scores


SCORING_METHODS = {
    "tfidf": score_tfidf,
    "cosine": score_cosine,
    "share": score_share,
    "spread": score_spread,
}

# descriptions shown in the menu
SCORING_DESCRIPTIONS = {
    "tfidf": "sum of tf * idf - more occurrences = higher score, long documents win",
    "cosine": "lnc.ltc cosine similarity - log tf, normalized by document length",
    "share": "sum of idf * tf / cf - part of all occurrences of the term that are in this document",
    "spread": "sum of (1 + log tf) * idf * (base + coverage) - term in more sections of the document wins",
}





def search(query, index, scoring="tfidf", idf_method="standard", top_k=config.TOP_K):
    # returns [(score, doc), ...], the best first
    docs = index["docs"]
    postings = index["postings"]

    # query terms, which are in the index (unknown words are ignored)
    query_terms = []
    for term in tokenize(query):
        if term in postings:
            query_terms.append(term)

    if not query_terms:
        return []

    query_counts = Counter(query_terms)

    idf_function = IDF_METHODS[idf_method]
    idf = {}
    for term in query_counts:
        df = len(postings[term])
        idf[term] = idf_function(df, len(docs), index["cf"][term], index["total_tokens"])

    score_function = SCORING_METHODS[scoring]
    scores = score_function(query_counts, index, idf)

    # documents with score 0 are not results (e.g. all query terms have idf 0)
    positive = []
    for doc_index, score in scores.items():
        if score > 0:
            positive.append((doc_index, score))

    best = sorted(positive, key=lambda item: item[1], reverse=True)[:top_k]

    results = []
    for doc_index, score in best:
        results.append((score, docs[doc_index]))
    return results





def choose(label, options, descriptions):
    # numbered menu with description of every option, Enter = first option
    keys = list(options)

    print(f"\n{label}")
    for number, key in enumerate(keys, 1):
        print(f" {number}) {key:<10}{descriptions[key]}")

    choice = input("Choose (Enter = 1): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(keys):
        return keys[int(choice) - 1]
    return keys[0]


def load_index():
    if not config.POSTINGS_FILE.exists():
        print("Index not found - build it first")
        return None

    print("Loading index...")
    docs, postings = load()

    # computed once here, not for every query
    total_tokens = 0
    for doc in docs:
        total_tokens += doc["length"]

    return {
        "docs": docs,
        "postings": postings,
        "cf": collection_frequencies(postings),
        "total_tokens": total_tokens,
    }


def run():
    index = load_index()
    if index is None:
        return

    scoring = choose("Scoring function", SCORING_METHODS, SCORING_DESCRIPTIONS)
    idf_method = choose("IDF method", IDF_METHODS, IDF_DESCRIPTIONS)

    while True:
        query = input(f"\n[{scoring} / {idf_method}] Query (Enter = back): ").strip()
        if query == "":
            return

        results = search(query, index, scoring, idf_method)
        if not results:
            print(" nothing found")
            continue

        print(f" query terms: {tokenize(query)}")
        for rank, (score, doc) in enumerate(results, 1):
            print(f" {rank:>2}. {score:8.4f}  {doc['name']:<35}{doc['slug']}")


def compare():
    # one query, top 5 of every scoring + idf combination
    index = load_index()
    if index is None:
        return

    while True:
        query = input("\nQuery to compare (Enter = back): ").strip()
        if query == "":
            return

        print(f" query terms: {tokenize(query)}")

        for scoring in SCORING_METHODS:
            for idf_method in IDF_METHODS:
                results = search(query, index, scoring, idf_method, top_k=5)

                names = []
                for score, doc in results:
                    names.append(doc["name"])

                if not names:
                    names = ["nothing found"]

                label = f"{scoring} / {idf_method}"
                print(f" {label:<20}{', '.join(names)}")