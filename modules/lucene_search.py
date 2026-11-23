import re
import time

import config
from modules.lucene_utils import DOUBLE_FIELDS, INT_FIELDS, KEYWORD_FIELDS, create_analyzer, init_lucene, open_directory
from modules.spark_join import SOURCE_AZ





# field:[low TO high], * = no limit, only for numeric fields, the rest of the query goes to the query parser
RANGE_REGEX = re.compile(r"(\w+):\[\s*([\d.]+|\*)\s+TO\s+([\d.]+|\*)\s*\]")
LOOSE_OPERATOR_REGEX = re.compile(r"^\s*(AND|OR)\s+|\s+(AND|OR)\s*$")        # "class:aves AND " left after removing the range
DOUBLE_OPERATOR_REGEX = re.compile(r"\b(AND|OR)\s+(?:AND|OR)\b")             # "a AND  AND b" -> "a AND b"

INT_LIMITS = (-2 ** 31, 2 ** 31 - 1)
DOUBLE_LIMITS = (float("-inf"), float("inf"))

QUERY_EXAMPLES = [
    ("Boolean AND", "fox AND arctic"),
    ("Boolean OR", "jaguar OR leopard"),
    ("Boolean NOT", "python NOT ball"),
    ("Phrase", '"apex predator"'),
    ("Field", "name:fox"),
    ("Fuzzy (typo)", "name:elefant~"),
    ("Wildcard", "octo*"),
    ("Range - year of description", "authority_year:[1750 TO 1760]"),
    ("Range - lifespan", "class:reptilia AND lifespan_max:[100 TO *]"),
    ("Keyword filter", "class:aves AND status:cr"),
    ("Keyword filter (whole value)", 'venomous AND as_pet:"suitable as pet"'),
    ("Status from wiki (fossils)", "locations:slovakia AND status:ex"),
    ("Filter + range", "class:mammalia AND lifespan_max:[50 TO *]"),
    ("Wiki redirect (old name)", '"Alopex lagopus"'),
    ("Wiki category", 'categories:"mammals of africa" AND status:(vu OR en OR cr)'),
    ("Source - only a-z records", "source:az AND name:lion"),
    ("Source - only wiki records", "source:wiki AND NOT source:az AND class:mammalia AND status:cr"),
    ("One name, more records (join check)", "name:lion"),
]

HELP = f"""
Query syntax
 words                  fox arctic                       (AND between words, then filled by OR)
 Boolean                fox AND arctic, python NOT ball, (lion OR tiger) AND white
 phrase                 "apex predator"
 fuzzy / wildcard       elefant~   octo*
 field                  name:fox   class:aves   status:cr   diet:herbivore   as_pet:"suitable as pet"
 range (numbers)        authority_year:[1750 TO 1800]   lifespan_max:[50 TO *]
 source                 source:az (a-z records)   source:wiki (wiki records)   source:wiki NOT source:az (only wiki)

Searched without field name: {", ".join(config.LUCENE_FIELD_BOOSTS)}
Keyword fields: {", ".join(KEYWORD_FIELDS)}
Numeric fields: {", ".join(INT_FIELDS + DOUBLE_FIELDS)}"""





def open_searcher():
    from org.apache.lucene.index import DirectoryReader
    from org.apache.lucene.search import IndexSearcher

    return IndexSearcher(DirectoryReader.open(open_directory()))


def create_parser(operator):
    # words without field name are searched in more fields, every field has its boost from config
    from java.lang import Float
    from java.util import HashMap
    from org.apache.lucene.queryparser.classic import MultiFieldQueryParser, QueryParser

    boosts = HashMap()
    for field, boost in config.LUCENE_FIELD_BOOSTS.items():
        boosts.put(field, Float(boost))

    parser = MultiFieldQueryParser(list(config.LUCENE_FIELD_BOOSTS), create_analyzer(), boosts)
    if operator == "AND":
        parser.setDefaultOperator(QueryParser.Operator.AND)
    return parser


def create_parsers():
    # (AND parser, OR parser), words without operator are first joined by AND, then by OR
    return create_parser("AND"), create_parser("OR")


def filter_source(query, source):
    # only records with this source (source:az in the evaluation), a filter does not change the score
    from org.apache.lucene.index import Term
    from org.apache.lucene.search import BooleanClause, BooleanQuery, TermQuery

    builder = BooleanQuery.Builder()
    builder.add(query, BooleanClause.Occur.MUST)
    builder.add(TermQuery(Term("source", source)), BooleanClause.Occur.FILTER)
    return builder.build()


def range_query(field, low, high):
    # numeric range, * means no limit
    from org.apache.lucene.document import DoubleField, IntField

    if field in INT_FIELDS:
        low = INT_LIMITS[0] if low == "*" else int(float(low))
        high = INT_LIMITS[1] if high == "*" else int(float(high))
        return IntField.newRangeQuery(field, low, high)

    low = DOUBLE_LIMITS[0] if low == "*" else float(low)
    high = DOUBLE_LIMITS[1] if high == "*" else float(high)
    return DoubleField.newRangeQuery(field, low, high)


def parse_text(parser, text):
    # MultiFieldQueryParser has also static parse() methods, PyLucene would call them, so the instance method is called directly
    from org.apache.lucene.queryparser.classic import QueryParserBase

    return QueryParserBase.parse(parser, text)


def parse_query(text, parser):
    # numeric ranges are taken out of the text, other parts are parsed by Lucene, all parts must match
    from org.apache.lucene.search import BooleanClause, BooleanQuery

    ranges = []
    for match in RANGE_REGEX.finditer(text):
        field, low, high = match.groups()
        if field in INT_FIELDS or field in DOUBLE_FIELDS:
            ranges.append(range_query(field, low, high))
            text = text.replace(match.group(0), " ")

    text = DOUBLE_OPERATOR_REGEX.sub(r"\1", text)
    text = LOOSE_OPERATOR_REGEX.sub(" ", text).strip()
    if not ranges:
        return parse_text(parser, text)

    builder = BooleanQuery.Builder()
    for query in ranges:
        builder.add(query, BooleanClause.Occur.MUST)
    if text:
        builder.add(parse_text(parser, text), BooleanClause.Occur.MUST)
    return builder.build()


def run_query(query, searcher, top_k, all_words):
    top = searcher.search(query, top_k)
    stored_fields = searcher.storedFields()

    results = []
    for score_doc in top.scoreDocs:
        doc = stored_fields.document(score_doc.doc)
        results.append({
            "score": score_doc.score,
            "slug": doc.get("slug"),
            "name": doc.get("name"),
            "class": doc.get("class"),
            "status": doc.get("status"),
            "source": "+".join(str(source) for source in doc.getValues("source")),
            "all_words": all_words,
        })
    return results, hit_count(top.totalHits)


def search(text, searcher, parsers, top_k=config.TOP_K, source=None):
    # AND query first (all words), the rest of top_k is filled by the OR query, returns (results, AND hits, ms)
    and_parser, or_parser = parsers
    and_query = parse_query(text, and_parser)
    or_query = parse_query(text, or_parser)
    if source:
        and_query = filter_source(and_query, source)
        or_query = filter_source(or_query, source)

    start = time.perf_counter()
    results, total = run_query(and_query, searcher, top_k, all_words=True)
    if len(results) < top_k:
        found = {result["slug"] for result in results}
        or_results, or_total = run_query(or_query, searcher, top_k, all_words=False)
        for result in or_results:
            if result["slug"] not in found and len(results) < top_k:
                results.append(result)
    milliseconds = (time.perf_counter() - start) * 1000

    return results, total, milliseconds


def hit_count(total_hits):
    # Lucene 10 has the method value(), older versions the field value
    value = total_hits.value
    if callable(value):
        return value()
    return value


def error_message(error):
    # Lucene parse errors are long, the first line is enough
    return str(error).splitlines()[0]


def print_results(results, total, milliseconds):
    print(f" {total} hits with all words, {milliseconds:.1f} ms")
    for rank, result in enumerate(results, 1):
        mark = " " if result["all_words"] else "~"          # ~ = found only by some of the words
        print(f" {rank:>2}.{mark}{result['score']:7.3f}  {result['name'][:31]:<32}{result['class'] or '':<16}{result['status']:<4}{result['source']:<9}{result['slug']}")


def prepare():
    # Lucene VM, searcher and parser, None if something is missing
    if not config.LUCENE_INDEX_DIR.exists():
        print("Lucene index not found - build it first")
        return None
    if not init_lucene():
        return None
    return open_searcher(), create_parsers()





def run():
    prepared = prepare()
    if prepared is None:
        return
    searcher, parsers = prepared

    print(HELP)
    while True:
        text = input("\n[Lucene] Query (Enter = back): ").strip()
        if text == "":
            return

        try:
            results, total, milliseconds = search(text, searcher, parsers)
        except Exception as error:
            print(f" wrong query: {error_message(error)}")
            continue

        if not results:
            print(" nothing found")
            continue
        print_results(results, total, milliseconds)


def examples():
    # one example query for every query type
    prepared = prepare()
    if prepared is None:
        return
    searcher, parsers = prepared

    for label, text in QUERY_EXAMPLES:
        results, total, milliseconds = search(text, searcher, parsers, top_k=5)

        print(f"\n{label}:  {text}")
        if not results:
            print(" nothing found")
            continue
        print_results(results, total, milliseconds)


def compare():
    # the same query in the old index (part 1) and in the Lucene index, top 10 side by side
    from modules import search as old_search

    prepared = prepare()
    if prepared is None:
        return
    searcher, parsers = prepared

    old_index = old_search.load_index()
    if old_index is None:
        return

    while True:
        text = input("\nQuery to compare (Enter = back): ").strip()
        if text == "":
            return

        start = time.perf_counter()
        old_results = old_search.search(text, old_index, config.OLD_SCORING, config.OLD_IDF)
        old_milliseconds = (time.perf_counter() - start) * 1000

        try:
            new_results, total, new_milliseconds = search(text, searcher, parsers, source=SOURCE_AZ)     # the old index has only a-z
        except Exception as error:
            print(f" wrong query: {error_message(error)}")
            continue

        old_label = f"old index ({config.OLD_SCORING} / {config.OLD_IDF})"
        print(f"\n {'':4}{old_label:<36}{'Lucene (source:az)':<36}")
        print(f" {'':4}{f'{old_milliseconds:.1f} ms':<36}{f'{new_milliseconds:.1f} ms, {total} hits':<36}")

        for rank in range(config.TOP_K):
            old_name = old_results[rank][1]["name"] if rank < len(old_results) else ""
            new_name = new_results[rank]["name"] if rank < len(new_results) else ""
            if not old_name and not new_name:
                break
            print(f" {rank + 1:>2}. {old_name[:35]:<36}{new_name[:35]:<36}")
