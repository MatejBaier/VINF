import json
import re
import shutil
import time

import config
from modules.lucene_utils import INT_FIELDS, create_analyzer, init_lucene, open_directory
from modules.stats import human_size





# a-z lists, which are put into one text field "facts", wiki records do not have them
FACT_FIELDS = [
    "distinguishing_features",
    "communication",
    "did_you_know",
    "adaptations",
    "behaviors",
    "myths_legends",
]

LIFESPAN_REGEX = re.compile(r"([\d.]+)(?:\s*[–-]\s*([\d.]+))?\s*years")       # "10–33 years" -> 10, 33





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


def split_values(text):
    # "Diurnal, Crepuscular" -> ["Diurnal", "Crepuscular"]
    if not text:
        return []
    return [value.strip() for value in text.split(",") if value.strip()]


def text_fields(record):
    # one record -> [(field, value, stored)], a-z, wiki and merged records have the same fields, missing values are skipped
    fields = []

    # names, the most important for search
    fields.append(("name", record["name"], True))
    fields.append(("scientific_name", record["scientific_name"], True))
    for name in record["also_known_as"]:
        fields.append(("also_known_as", name, False))

    # full text, a-z article has one more section with the wiki lead in merged records
    fields.append(("summary", record["summary"], False))
    for location in record["locations"]:
        fields.append(("locations", location, False))
    for category in record["categories"]:
        fields.append(("categories", category, False))
    fields.append(("origin", record["origin"], False))
    fields.append(("facts", record.get("cultural_significance"), False))
    for field in FACT_FIELDS:
        for fact in record.get(field) or []:
            fields.append(("facts", fact, False))
    for section in record["article"]:
        fields.append(("article", " ".join(part for part in (section["heading"], section["text"]) if part), False))

    # keyword fields for filters (class:aves AND status:cr AND source:wiki)
    for source in record["source"]:
        fields.append(("source", source, True))
    fields.append(("class", record["class"], True))
    fields.append(("taxon_level", record["taxon_level"], False))
    fields.append(("status", record["status"], True))
    fields.append(("diet", record.get("diet"), False))
    for activity in split_values(record.get("activity")):
        fields.append(("activity", activity, False))
    fields.append(("domestication", record["domestication"], False))
    fields.append(("danger_level", record.get("danger_level"), False))
    fields.append(("as_pet", record.get("as_pet"), False))

    return [field for field in fields if field[1]]


def number_fields(record):
    # numbers for range queries (lifespan_max:[50 TO *], authority_year:[1750 TO 1760]) -> [(field, value)]
    fields = []
    years = lifespan(record["lifespan"])
    if years:
        fields.append(("lifespan_min", years[0]))
        fields.append(("lifespan_max", years[1]))
    if record["authority_year"]:
        fields.append(("authority_year", record["authority_year"]))
    return fields





def create_document(record):
    # one record -> one Lucene document
    from org.apache.lucene.document import Document, DoubleField, Field, IntField, StringField, TextField

    doc = Document()

    # identifier, exact value, not analyzed (a-z slug or wiki-<page id>)
    doc.add(StringField("slug", record["id"], Field.Store.YES))

    for field, value, stored in text_fields(record):
        doc.add(TextField(field, value, Field.Store.YES if stored else Field.Store.NO))

    for field, value in number_fields(record):
        if field in INT_FIELDS:
            doc.add(IntField(field, int(value), Field.Store.YES))
        else:
            doc.add(DoubleField(field, float(value), Field.Store.YES))

    return doc





def read_records():
    # records one by one, the joined file is too big to keep all of it in memory
    for path in sorted(config.ANIMALS_WIKI_DIR.glob("part-*")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)


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

    # new index every time
    if config.LUCENE_INDEX_DIR.exists():
        shutil.rmtree(config.LUCENE_INDEX_DIR)

    writer_config = IndexWriterConfig(create_analyzer())
    writer_config.setOpenMode(IndexWriterConfig.OpenMode.CREATE)
    writer = IndexWriter(open_directory(), writer_config)

    sources = {}
    for record in read_records():
        writer.addDocument(create_document(record))
        label = "+".join(record["source"])
        sources[label] = sources.get(label, 0) + 1

    writer.forceMerge(1)        # one segment, statistics are exact
    writer.close()

    print(f"Indexed {sum(sources.values())} records -> {config.LUCENE_INDEX_DIR}")
    for label, count in sorted(sources.items()):
        print(f" {label + ':':<12}{count}")
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
