import config





# short fields with a few possible values, the whole value is one term, only lowercase (as_pet:"suitable as pet", status:cr)
KEYWORD_FIELDS = [
    "class",
    "taxon_level",
    "status",
    "diet",
    "activity",
    "domestication",
    "danger_level",
    "as_pet",
    "wiki_match",
]

# names are not stemmed, fuzzy and wildcard queries compare whole words (elefant~ -> elephant)
NAME_FIELDS = ["name", "also_known_as", "wiki_names", "scientific_name"]

# numeric fields, used in range queries, value type for the query parser
INT_FIELDS = ["authority_year"]
DOUBLE_FIELDS = ["lifespan_min", "lifespan_max"]

DOCKER_COMMAND = 'docker run --rm -it -v "$PWD":/project -w /project coady/pylucene python main.py'

vm_started = False





def init_lucene():
    # starts the Java VM once, returns False if PyLucene is not installed (outside of Docker)
    global vm_started
    if vm_started:
        return True

    try:
        import lucene
    except ImportError:
        print("PyLucene not found - run the program in Docker:")
        print(f" {DOCKER_COMMAND}")
        return False

    lucene.initVM()
    vm_started = True
    return True


def create_keyword_analyzer():
    # the whole value is one lowercase term, "Not Suitable as Pet" -> "not suitable as pet", so it is not found by "suitable as pet"
    from java.util import HashMap
    from org.apache.lucene.analysis.custom import CustomAnalyzer

    builder = CustomAnalyzer.builder()
    builder.withTokenizer("keyword", HashMap())         # Map overloads, PyLucene does not need Java varargs then
    builder.addTokenFilter("lowercase", HashMap())
    return builder.build()


def create_analyzer():
    # English analyzer (lowercase, stop words, stemming foxes -> fox) for text, standard for names, keyword for categories
    from java.util import HashMap
    from org.apache.lucene.analysis.en import EnglishAnalyzer
    from org.apache.lucene.analysis.miscellaneous import PerFieldAnalyzerWrapper
    from org.apache.lucene.analysis.standard import StandardAnalyzer

    field_analyzers = HashMap()
    for field in NAME_FIELDS:
        field_analyzers.put(field, StandardAnalyzer())

    keyword_analyzer = create_keyword_analyzer()
    for field in KEYWORD_FIELDS:
        field_analyzers.put(field, keyword_analyzer)

    return PerFieldAnalyzerWrapper(EnglishAnalyzer(), field_analyzers)


def open_directory():
    from java.nio.file import Paths
    from org.apache.lucene.store import FSDirectory

    return FSDirectory.open(Paths.get(str(config.LUCENE_INDEX_DIR)))
