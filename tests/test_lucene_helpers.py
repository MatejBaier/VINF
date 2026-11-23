import unittest

from modules.evaluation import precision_at, recall_at, reciprocal_rank, url_to_slug
from modules.lucene_indexer import lifespan, number_fields, split_values, text_fields
from modules.lucene_search import DOUBLE_OPERATOR_REGEX, LOOSE_OPERATOR_REGEX, RANGE_REGEX
from modules.lucene_utils import KEYWORD_FIELDS, NAME_FIELDS
from modules.spark_join import az_record, merged_record, wiki_record
from tests.test_join import az_animal, wiki_taxon

import config

# these parts work without PyLucene, the Lucene index itself is tested by the menu items 22 and 24 in Docker





def field_names(record):
    return {field for field, value, stored in text_fields(record)}


def values(record, name):
    return [value for field, value, stored in text_fields(record) if field == name]





class TestIndexedValues(unittest.TestCase):

    def test_lifespan(self):
        self.assertEqual(lifespan("10–33 years"), (10.0, 33.0))
        self.assertEqual(lifespan("8 years"), (8.0, 8.0))
        self.assertEqual(lifespan("0.5–1.5 years"), (0.5, 1.5))
        self.assertEqual(lifespan("12-15 years"), (12.0, 15.0))        # breeds from wiki have a hyphen
        self.assertIsNone(lifespan("unknown"))
        self.assertIsNone(lifespan(None))

    def test_split_values(self):
        self.assertEqual(split_values("Diurnal, Crepuscular"), ["Diurnal", "Crepuscular"])
        self.assertEqual(split_values(None), [])





class TestUnifiedFields(unittest.TestCase):
    # a-z, wiki and merged records go to the same fields, there is no wiki_ field

    def setUp(self):
        animal = az_animal("arctic-fox", "Arctic Fox", "Vulpes lagopus", diet="Omnivore", activity="Diurnal, Crepuscular")
        wiki = wiki_taxon(2208, "Arctic fox", "Vulpes lagopus", redirects=["Alopex lagopus"], categories=["Mammals of Europe"])
        self.merged = merged_record(animal, wiki, "scientific_name_and_name")
        self.az = az_record(animal, None)
        self.wiki = wiki_record(wiki_taxon(12, "Pallas's cat", "Otocolobus manul", redirects=["Manul"]))

    def test_no_wiki_fields(self):
        for record in (self.merged, self.az, self.wiki):
            for field in field_names(record):
                self.assertFalse(field.startswith("wiki"), field)

    def test_same_fields(self):
        # wiki record has the shared fields, only a-z fields (diet, facts ...) are missing
        shared = {"name", "scientific_name", "also_known_as", "summary", "locations", "class", "taxon_level", "status", "source"}
        self.assertTrue(shared <= field_names(self.wiki))
        self.assertTrue(shared <= field_names(self.merged))
        self.assertIn("diet", field_names(self.merged))
        self.assertNotIn("diet", field_names(self.wiki))

    def test_source(self):
        self.assertEqual(values(self.merged, "source"), ["az", "wiki"])
        self.assertEqual(values(self.az, "source"), ["az"])
        self.assertEqual(values(self.wiki, "source"), ["wiki"])
        self.assertIn("source", KEYWORD_FIELDS)

    def test_names(self):
        self.assertEqual(values(self.merged, "name"), ["Arctic Fox"])          # one name field, the wiki title is not repeated
        self.assertIn("Alopex lagopus", values(self.merged, "also_known_as"))
        self.assertEqual(values(self.wiki, "name"), ["Pallas's cat"])
        self.assertEqual(values(self.merged, "categories"), ["Mammals of Europe"])

    def test_numbers(self):
        self.assertEqual(number_fields(self.merged), [("lifespan_min", 1.0), ("lifespan_max", 10.0), ("authority_year", 1758)])
        self.assertEqual(number_fields(self.az), [("lifespan_min", 1.0), ("lifespan_max", 10.0)])

    def test_searched_fields_exist(self):
        # every field searched without a field name is filled by the indexer
        indexed = field_names(self.merged) | field_names(self.wiki) | {"facts", "origin"}
        for field in config.LUCENE_FIELD_BOOSTS:
            self.assertIn(field, indexed)
        for field in NAME_FIELDS:
            self.assertIn(field, config.LUCENE_FIELD_BOOSTS)





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
