import json
import re
import shutil
import time

import config
from modules.lucene_utils import create_analyzer, init_lucene, open_directory
from modules.stats import human_size





# a-z status text -> IUCN code, the same codes as in wiki
STATUS_CODES = {
    "Least Concern": "LC",
    "Near Threatened": "NT",
    "Vulnerable": "VU",
    "Endangered": "EN",
    "Critically Endangered": "CR",
    "Extinct in the Wild": "EW",
    "Extinct": "EX",
    "Data Deficient": "DD",
    "Not Evaluated": "NE",
}
IUCN_CODES = {"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"}

# wiki page is the animal's own page, its text and names can be indexed
STRONG_MATCHES = {"scientific_name_and_name", "scientific_name", "scientific_name_redirect", "name", "breed_name"}

# a-z lists, which are put into one text field "facts"
FACT_FIELDS = [
    "distinguishing_features",
    "communication",
    "did_you_know",
    "adaptations",
    "behaviors",
    "myths_legends",
]

LIFESPAN_REGEX = re.compile(r"([\d.]+)(?:\s*–\s*([\d.]+))?\s*years")       # "10–33 years" -> 10, 33





def status_code(record):
    # a-z status, if it is not evaluated, the IUCN status from wiki is used
    code = STATUS_CODES.get(record["status"], "NE")
    wiki = record["wiki"]

    if code == "NE" and wiki and wiki["status"] in IUCN_CODES:
        system = wiki["status_system"] or "IUCN"
        if system.upper().startswith("IUCN"):
            return wiki["status"]
    return code


def lifespan(text):
    # "10–33 years" -> (10.0, 33.0), "8 years" -> (8.0, 8.0)
    if not text:
        return None
    match = LIFESPAN_REGEX.search(text)
    if not match:
        return None

    low = float(match.group(1))
    high = float(match.group(2) or match.group(1))
    return low, high


def wiki_names(record):
    # wiki title and redirects (Alopex lagopus, Polar fox ...), without the names a-z already has
    wiki = record["wiki"]
    known = {record["name"].lower()}
    for alias in record["also_known_as"] or []:
        known.add(alias.lower())

    names = []
    for name in [wiki["title"]] + wiki["redirects"]:
        if name.lower() not in known:
            known.add(name.lower())
            names.append(name)
    return names


def split_values(text):
    # "Diurnal, Crepuscular" -> ["Diurnal", "Crepuscular"]
    if not text:
        return []
    return [value.strip() for value in text.split(",") if value.strip()]





def add_text(doc, field, value, stored=False):
    from org.apache.lucene.document import Field, TextField

    if value:
        doc.add(TextField(field, value, Field.Store.YES if stored else Field.Store.NO))


def add_texts(doc, field, values, stored=False):
    for value in values or []:
        add_text(doc, field, value, stored)


def create_document(record):
    # one animal -> one Lucene document
    from org.apache.lucene.document import Document, DoubleField, Field, IntField, StoredField, StringField

    doc = Document()
    wiki = record["wiki"]
    strong = wiki is not None and wiki["match_type"] in STRONG_MATCHES

    # identifier, exact value, not analyzed
    doc.add(StringField("slug", record["id"], Field.Store.YES))

    # names, the most important for search
    add_text(doc, "name", record["name"], stored=True)
    add_texts(doc, "also_known_as", record["also_known_as"])
    add_text(doc, "scientific_name", record["scientific_name"], stored=True)

    # full text from a-z
    add_text(doc, "summary", record["summary"])
    add_texts(doc, "locations", record["locations"])
    add_text(doc, "facts", record["cultural_significance"])
    for field in FACT_FIELDS:
        add_texts(doc, "facts", record[field])
    for section in record["article"]:
        add_text(doc, "article", " ".join(part for part in (section["heading"], section["text"]) if part))

    # keyword fields for filters (class:aves AND status:cr)
    add_text(doc, "class", record["class"], stored=True)
    add_text(doc, "taxon_level", record["taxon_level"])
    add_text(doc, "status", status_code(record), stored=True)
    add_text(doc, "diet", record["diet"])
    add_texts(doc, "activity", split_values(record["activity"]))
    add_text(doc, "domestication", record["domestication"])
    add_text(doc, "danger_level", record["danger_level"])
    add_text(doc, "as_pet", record["as_pet"])

    # numbers for range queries (lifespan_max:[50 TO *])
    years = lifespan(record["lifespan_wild"])
    if years:
        doc.add(DoubleField("lifespan_min", years[0], Field.Store.YES))
        doc.add(DoubleField("lifespan_max", years[1], Field.Store.YES))

    if wiki is None:
        add_text(doc, "wiki_match", "none")
        return doc

    # from wiki only the animal's own page is indexed, not Dog with its "Wolves" category for every breed
    add_text(doc, "wiki_match", wiki["match_type"].replace("_", " "))
    doc.add(StoredField("wiki_title", wiki["title"]))

    if strong:
        add_texts(doc, "wiki_categories", wiki["categories"])
        add_texts(doc, "wiki_names", wiki_names(record))
        add_text(doc, "wiki_lead", wiki["lead"])
        add_text(doc, "origin", wiki["origin"])
        if wiki["scientific_name"] and wiki["scientific_name"] != record["scientific_name"]:
            add_text(doc, "scientific_name", wiki["scientific_name"])      # newer or older scientific name
        if wiki["authority_year"]:
            doc.add(IntField("authority_year", wiki["authority_year"], Field.Store.YES))

    return doc





def load_records():
    records = []
    for path in sorted(config.ANIMALS_WIKI_DIR.glob("part-*")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
    return records


def folder_size(folder):
    size = 0
    for path in folder.iterdir():
        size += path.stat().st_size
    return size


def build():
    if not config.ANIMALS_WIKI_DIR.exists():
        print("Joined data not found - run the Spark join first")
        return
    if not init_lucene():
        return

    from org.apache.lucene.index import IndexWriter, IndexWriterConfig

    start = time.time()
    records = load_records()

    # new index every time
    if config.LUCENE_INDEX_DIR.exists():
        shutil.rmtree(config.LUCENE_INDEX_DIR)

    writer_config = IndexWriterConfig(create_analyzer())
    writer_config.setOpenMode(IndexWriterConfig.OpenMode.CREATE)
    writer = IndexWriter(open_directory(), writer_config)

    for record in records:
        writer.addDocument(create_document(record))

    writer.forceMerge(1)        # one segment, the index is small and statistics are exact
    writer.close()

    print(f"Indexed {len(records)} animals -> {config.LUCENE_INDEX_DIR}")
    print(f"Index size: {human_size(folder_size(config.LUCENE_INDEX_DIR))}")
    print(f"Done in {time.time() - start:.1f} s")





def show_stats():
    if not config.LUCENE_INDEX_DIR.exists():
        print("Lucene index not found - build it first")
        return
    if not init_lucene():
        return

    import lucene
    from org.apache.lucene.index import DirectoryReader, FieldInfos, MultiTerms

    reader = DirectoryReader.open(open_directory())
    print(f"Lucene {lucene.VERSION}, documents: {reader.numDocs()}\n")

    print(f" {'field':<18}{'documents':>10}{'unique terms':>14}{'tokens':>12}")
    fields = sorted(str(item) for item in FieldInfos.getIndexedFields(reader))      # PyLucene returns String as Object
    for field in fields:
        terms = MultiTerms.getTerms(reader, field)
        if terms is None:
            continue            # stored or numeric only field, no terms
        print(f" {field:<18}{reader.getDocCount(field):>10}{terms.size():>14}{reader.getSumTotalTermFreq(field):>12}")

    reader.close()
