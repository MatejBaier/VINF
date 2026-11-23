import unittest

from modules.evaluation import precision_at, recall_at, reciprocal_rank, url_to_slug
from modules.lucene_indexer import lifespan, split_values, status_code, wiki_names
from modules.lucene_search import DOUBLE_OPERATOR_REGEX, LOOSE_OPERATOR_REGEX, RANGE_REGEX

# these parts work without PyLucene, the Lucene index itself is tested by the menu items 22 and 24 in Docker





def record(status, wiki=None, name="Arctic Fox", also_known_as=None):
    return {"status": status, "wiki": wiki, "name": name, "also_known_as": also_known_as or []}


def wiki(status=None, system=None, match_type="scientific_name_and_name", categories=None, title="Arctic fox", redirects=None):
    return {
        "status": status,
        "status_system": system,
        "match_type": match_type,
        "categories": categories or [],
        "title": title,
        "redirects": redirects or [],
    }





class TestIndexedValues(unittest.TestCase):

    def test_lifespan(self):
        self.assertEqual(lifespan("10–33 years"), (10.0, 33.0))
        self.assertEqual(lifespan("8 years"), (8.0, 8.0))
        self.assertEqual(lifespan("0.5–1.5 years"), (0.5, 1.5))
        self.assertIsNone(lifespan("unknown"))
        self.assertIsNone(lifespan(None))

    def test_split_values(self):
        self.assertEqual(split_values("Diurnal, Crepuscular"), ["Diurnal", "Crepuscular"])
        self.assertEqual(split_values(None), [])

    def test_status_from_a_z(self):
        self.assertEqual(status_code(record("Critically Endangered")), "CR")
        self.assertEqual(status_code(record("Least Concern", wiki("EN", "IUCN3.1"))), "LC")       # a-z has priority

    def test_status_from_wiki(self):
        self.assertEqual(status_code(record("Not Evaluated", wiki("VU", "IUCN3.1"))), "VU")
        self.assertEqual(status_code(record("Not Evaluated", wiki("G5", "TNC"))), "NE")           # other system than IUCN
        self.assertEqual(status_code(record("Not Evaluated", wiki("DOM"))), "NE")                 # domesticated
        self.assertEqual(status_code(record("Not Evaluated", wiki("VU", "IUCN3.1", match_type="shared_scientific_name"))), "NE")
        self.assertEqual(status_code(record(None)), "NE")

    def test_status_of_fossils(self):
        fossil = wiki(categories=["Pleistocene bears", "Fossil taxa described in 1794"])
        living = wiki(categories=["Extant Pleistocene first appearances", "Mammals of Europe"])
        self.assertEqual(status_code(record("Not Evaluated", fossil)), "EX")
        self.assertEqual(status_code(record("Not Evaluated", living)), "NE")

    def test_wiki_names(self):
        # names already in a-z are not repeated
        one = record("Least Concern", wiki(title="Arctic fox", redirects=["Alopex lagopus", "Polar fox", "Arctic Fox"]), also_known_as=["Polar Fox"])
        self.assertEqual(wiki_names(one), ["Alopex lagopus"])





class TestQueryRegex(unittest.TestCase):

    def test_range(self):
        matches = RANGE_REGEX.findall("class:aves AND lifespan_max:[50 TO *] AND authority_year:[1750 TO 1760]")
        self.assertEqual(matches, [("lifespan_max", "50", "*"), ("authority_year", "1750", "1760")])

    def test_operators_left_after_range(self):
        text = "class:aves AND   AND status:cr"
        self.assertEqual(DOUBLE_OPERATOR_REGEX.sub(r"\1", text), "class:aves AND status:cr")
        self.assertEqual(LOOSE_OPERATOR_REGEX.sub(" ", "class:aves AND ").strip(), "class:aves")
        self.assertEqual(LOOSE_OPERATOR_REGEX.sub(" ", " AND status:cr").strip(), "status:cr")





class TestEvaluationMetrics(unittest.TestCase):

    def test_metrics(self):
        results = ["fox", "arctic-fox", "wolf", "red-fox", "lynx"]
        relevant = {"arctic-fox", "red-fox", "fennec-fox"}
        self.assertAlmostEqual(precision_at(results, relevant, 5), 2 / 5)
        self.assertAlmostEqual(precision_at(results, relevant, 10), 2 / 10)       # missing results count as not relevant
        self.assertAlmostEqual(recall_at(results, relevant, 10), 2 / 3)
        self.assertAlmostEqual(reciprocal_rank(results, relevant), 1 / 2)
        self.assertEqual(reciprocal_rank(["wolf"], relevant), 0.0)

    def test_url_to_slug(self):
        self.assertEqual(url_to_slug("https://a-z-animals.com/animals/arctic-fox/"), "arctic-fox")
        self.assertEqual(url_to_slug("https://a-z-animals.com/animals/arctic-fox/pictures/"), "arctic-fox")
        self.assertEqual(url_to_slug("https://a-z-animals.com/blog/foxes/"), "https://a-z-animals.com/blog/foxes/")
