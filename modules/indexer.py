import json
import math
from collections import Counter

import config
from modules.stats import human_size
from modules.tokenizer import tokenize





# fields with one text
TEXT_FIELDS = [
    "name",
    "scientific_name",
    "class",
    "taxon_level",
    "summary",
    "status",
    "lifespan_wild",
    "lifespan_captivity",
    "social",
    "activity",
    "diet",
    "domestication",
    "danger_level",
    "as_pet",
    "cultural_significance",
]

# fields with a list of texts
LIST_FIELDS = [
    "also_known_as",
    "locations",
    "distinguishing_features",
    "communication",
    "did_you_know",
    "adaptations",
    "behaviors",
    "myths_legends",
]





def field_boost(field):
    # how many times the field is put into the text, fields not in config have 1
    return config.FIELD_BOOSTS.get(field, 1)


def record_sections(record):
    # section = one field or one section of the article, weight = boost of its field
    sections = []

    for field in TEXT_FIELDS:
        if record[field]:
            sections.append((field_boost(field), record[field]))

    for field in LIST_FIELDS:
        if record[field]:
            sections.append((field_boost(field), " ".join(record[field])))      # whole list is one section

    for section in record["article"]:
        text = section["text"]
        if section["heading"]:
            text = section["heading"] + " " + text
        sections.append((field_boost("article"), text))

    return sections


def doc_norm(term_counts):
    # length of the document vector, weight of a term is 1 + log(tf), used in cosine scoring
    total = 0
    for tf in term_counts.values():
        weight = 1 + math.log10(tf)
        total += weight ** 2
    return math.sqrt(total)


def index_record(record):
    # one animal -> term counts, section weights of terms, length, section weight of the document
    term_counts = {}            # term -> tf, every occurrence counts "weight" times (boost)
    term_section_weights = {}   # term -> sum of weights of sections, where the term is
    length = 0
    doc_section_weight = 0      # sum of weights of all non-empty sections

    for weight, text in record_sections(record):
        tokens = tokenize(text)
        if not tokens:
            continue            # empty section does not count into coverage

        length += len(tokens) * weight
        doc_section_weight += weight

        for term, count in Counter(tokens).items():
            term_counts[term] = term_counts.get(term, 0) + count * weight
            term_section_weights[term] = term_section_weights.get(term, 0) + weight

    return term_counts, term_section_weights, length, doc_section_weight


def format_weight(weight):
    # 2.0 -> 2, 1.5 -> 1.5 (boosts are usually whole numbers)
    return f"{weight:g}"





def save_docs(docs):
    with open(config.DOCS_FILE, "w", encoding="utf-8") as f:
        f.write("doc_index\tslug\tname\tlength\tnorm\tsection_weight\n")
        for doc_index, (slug, name, length, norm, section_weight) in enumerate(docs):
            f.write(f"{doc_index}\t{slug}\t{name}\t{length}\t{norm:.6f}\t{format_weight(section_weight)}\n")


def save_postings(postings):
    with open(config.POSTINGS_FILE, "w", encoding="utf-8") as f:
        f.write("term\tdf\tpostings\n")

        for term in sorted(postings):
            doc_items = postings[term]

            items = []
            for doc_index in sorted(doc_items):
                tf, section_weight = doc_items[doc_index]
                items.append(f"{doc_index}:{tf}:{format_weight(section_weight)}")      # 15:3:2 = 3 times in document 15, in sections with weight 2

            df = len(doc_items)
            f.write(f"{term}\t{df}\t{','.join(items)}\n")


def build():
    if not config.EXTRACTED_FILE.exists():
        print("extracted.jsonl not found - run the extractor first")
        return

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)

    postings = {}       # term -> {doc_index: (tf, section_weight)}
    docs = []           # (slug, name, length, norm, section_weight)

    with open(config.EXTRACTED_FILE, encoding="utf-8") as f:
        for doc_index, line in enumerate(f):
            record = json.loads(line)

            term_counts, term_section_weights, length, doc_section_weight = index_record(record)

            for term, tf in term_counts.items():
                if term not in postings:
                    postings[term] = {}
                postings[term][doc_index] = (tf, term_section_weights[term])

            name = record["name"]
            if not name:
                name = record["id"]
            docs.append((record["id"], name, length, doc_norm(term_counts), doc_section_weight))

            if (doc_index + 1) % 500 == 0:
                print(f" {doc_index + 1} documents indexed")

    save_docs(docs)
    save_postings(postings)

    print(f"\nIndexed {len(docs)} documents, {len(postings)} terms -> {config.INDEX_DIR}")
    show_stats()





def load_docs():
    docs = []
    with open(config.DOCS_FILE, encoding="utf-8") as f:
        next(f)         # skip header
        for line in f:
            doc_index, slug, name, length, norm, section_weight = line.rstrip("\n").split("\t")
            docs.append({
                "slug": slug,
                "name": name,
                "length": int(length),
                "norm": float(norm),
                "section_weight": float(section_weight),
            })
    return docs


def load_postings():
    # term -> [(doc_index, tf, section_weight), ...]
    postings = {}
    with open(config.POSTINGS_FILE, encoding="utf-8") as f:
        next(f)         # skip header
        for line in f:
            term, df, joined = line.rstrip("\n").split("\t")

            items = []
            for item in joined.split(","):
                doc_index, tf, section_weight = item.split(":")
                items.append((int(doc_index), int(tf), float(section_weight)))

            postings[term] = items
    return postings


def load():
    return load_docs(), load_postings()


def collection_frequencies(postings):
    # cf = how many times the term is in the whole collection (sum of tf)
    cf = {}
    for term, items in postings.items():
        total = 0
        for doc_index, tf, section_weight in items:
            total += tf
        cf[term] = total
    return cf





def show_stats():
    if not config.POSTINGS_FILE.exists():
        print("Index not found - build it first")
        return

    docs, postings = load()

    lengths = []
    for doc in docs:
        lengths.append(doc["length"])

    dfs = {}
    for term, items in postings.items():
        dfs[term] = len(items)

    only_once = 0
    for df in dfs.values():
        if df == 1:
            only_once += 1

    section_weights = []
    for doc in docs:
        section_weights.append(doc["section_weight"])

    size = config.DOCS_FILE.stat().st_size + config.POSTINGS_FILE.stat().st_size

    print("\nIndex")
    print(f" Documents: {len(docs)}")
    print(f" Unique terms: {len(postings)}")
    print(f" Postings (term-document pairs): {sum(dfs.values())}")
    print(f" Tokens total: {sum(lengths)}")
    print(f" Average document length: {sum(lengths) / len(docs):.1f} tokens")
    print(f" Shortest / longest document: {min(lengths)} / {max(lengths)} tokens")
    print(f" Terms in only 1 document: {only_once}")
    print(f" Average section weight of document: {sum(section_weights) / len(docs):.1f}")
    print(f" Size on disk: {human_size(size)}")

    print("\nMost common terms (df)")
    for term, df in sorted(dfs.items(), key=lambda item: item[1], reverse=True)[:15]:
        print(f" {term:<20}{df}")