import bz2
import unittest
from pathlib import Path

from modules.wiki_extractor import authority_year, clean, extract, find_infobox, parse_params, parse_xml_page, scientific_name





TESTS_DIR = Path(__file__).parent
WIKI_PAGES_FILE = TESTS_DIR / "wiki_test_pages.xml.bz2"     # 9 real pages from the dump enwiki-20261001





def read_wiki_pages():
    # the same split as in Spark (record delimiter </page>), title -> page
    with bz2.open(WIKI_PAGES_FILE, "rt", encoding="utf-8") as f:
        records = f.read().split("</page>")

    pages = {}
    for record in records:
        page = parse_xml_page(record)
        if page:
            pages[page["title"]] = page
    return pages


PAGES = read_wiki_pages()

# values checked by hand on the Wikipedia pages
EXPECTED = {
    "Arctic fox": {
        "infobox": "Speciesbox", "scientific_name": "Vulpes lagopus", "authority_year": 1758,
        "status": "LC", "origin": None, "category": "Mammals described in 1758",
        "lead": "The Arctic fox (Vulpes lagopus), also known as the white fox, polar fox, or snow fox",
    },
    "Anaconda": {
        "infobox": "Automatic taxobox", "scientific_name": "Eunectes", "authority_year": 1830,
        "status": None, "origin": None, "category": "Snakes of South America",
        "lead": "Anacondas or water boas are a group of large boas of the genus Eunectes.",
    },
    "Aurochs": {
        "infobox": "Speciesbox", "scientific_name": "Bos primigenius", "authority_year": 1825,
        "status": "EX", "origin": None, "category": "Bos",
        "lead": "The aurochs (Bos primigenius",
    },
    "Beagle": {
        "infobox": "Infobox dog breed", "scientific_name": None, "authority_year": None,
        "status": None, "origin": "England", "category": "Dog breeds originating in England",
        "lead": "The Beagle is a British breed of scent hound",
    },
    "Cat": {
        "infobox": "Speciesbox", "scientific_name": "Felis catus", "authority_year": 1758,
        "status": "DOM", "origin": None, "category": "Mammals described in 1758",
        "lead": "The cat (Felis catus), also called domestic cat and house cat",
    },
    "Dolphin": {
        "infobox": "Paraphyletic group", "scientific_name": None, "authority_year": None,
        "status": None, "origin": None, "category": "Animals that use echolocation",
        "lead": "A dolphin is any one of the 40 extant species of aquatic mammal",
    },
}





class TestWikiPages(unittest.TestCase):
    # real pages from the dump

    def test_all_pages_read(self):
        self.assertEqual(len(PAGES), 9)

    def test_redirect(self):
        page = PAGES["AccessibleComputing"]
        self.assertEqual(page["redirect"], "Computer accessibility")
        self.assertEqual(page["page_id"], 10)
        self.assertEqual(page["namespace"], 0)

    def test_pages_without_taxon(self):
        # Anarchism has no infobox, Algae has "taxobox colour" inside another infobox
        for title in ("Anarchism", "Algae"):
            with self.subTest(title=title):
                self.assertIsNone(extract(PAGES[title]))

    def test_taxon_pages(self):
        for title, expected in EXPECTED.items():
            record = extract(PAGES[title])
            self.assertIsNotNone(record, title)

            for field in ("infobox", "scientific_name", "authority_year", "status", "origin"):
                with self.subTest(title=title, field=field):
                    self.assertEqual(record[field], expected[field])
            with self.subTest(title=title, field="categories"):
                self.assertIn(expected["category"], record["categories"])
            with self.subTest(title=title, field="lead"):
                self.assertTrue(record["lead"].startswith(expected["lead"]), record["lead"][:100])
            with self.subTest(title=title, field="lead without wikitext"):
                for mark in ("[[", "]]", "{{", "}}", "<ref", "'''"):
                    self.assertNotIn(mark, record["lead"])





class TestXmlPage(unittest.TestCase):

    def test_escaped_text(self):
        record = "<page><title>A &amp; B</title><ns>0</ns><id>5</id><revision><id>99</id><text bytes=\"1\">x &lt;ref&gt;y&lt;/ref&gt;</text></revision>"
        page = parse_xml_page(record)
        self.assertEqual(page["title"], "A & B")
        self.assertEqual(page["page_id"], 5)                 # first id is the page id, not the revision id
        self.assertEqual(page["text"], "x <ref>y</ref>")

    def test_redirect_with_section(self):
        page = parse_xml_page('<page><title>Vulpes vulpes</title><ns>0</ns><id>1</id><redirect title="Red fox#Taxonomy" />')
        self.assertEqual(page["redirect"], "Red fox")

    def test_end_of_file(self):
        self.assertIsNone(parse_xml_page("\n</mediawiki>\n"))





class TestInfobox(unittest.TestCase):

    def test_nested_templates(self):
        text = "{{Short description|x}}\n{{Speciesbox\n| genus = Vulpes\n| species = vulpes\n| image = {{px|200}}\n}}\nThe red fox ..."
        infobox_type, body, end = find_infobox(text)
        self.assertEqual(infobox_type, "Speciesbox")
        self.assertEqual(text[end:].strip(), "The red fox ...")

    def test_template_names(self):
        for text, expected in (
            ("{{Automatic_taxobox\n| taxon = Macaca}}", "Automatic taxobox"),
            ("{{automatic taxobox | taxon = Macaca}}", "Automatic taxobox"),
            ("{{Infobox dog breed\n| name = Beagle}}", "Infobox dog breed"),
            ("{{Hybridbox\n| name = Zebroid}}", "Hybridbox"),
        ):
            with self.subTest(text=text):
                self.assertEqual(find_infobox(text)[0], expected)

    def test_not_taxon(self):
        for text in ("{{Infobox person\n| name = Linnaeus}}", "{{taxobox colour|Animalia}}", "{{Speciesbox\n| genus = Vulpes"):
            with self.subTest(text=text):
                self.assertIsNone(find_infobox(text))

    def test_params(self):
        body = "\n| genus = [[Vulpes]]\n| species = vulpes<ref>IUCN</ref>\n| authority = ([[Carl Linnaeus|Linnaeus]], 1758)\n| image = {{px|200}}\n"
        params = parse_params(body)
        self.assertEqual(params["genus"], "Vulpes")
        self.assertEqual(params["species"], "vulpes")
        self.assertEqual(params["authority"], "(Linnaeus, 1758)")
        self.assertNotIn("image", params)       # empty after the template is removed





class TestScientificName(unittest.TestCase):

    def test_infobox_types(self):
        for infobox_type, params, title, expected in (
            ("Speciesbox", {"genus": "Vulpes", "species": "vulpes"}, "Red fox", "Vulpes vulpes"),
            ("Speciesbox", {"taxon": "Vulpes lagopus"}, "Arctic fox", "Vulpes lagopus"),
            ("Subspeciesbox", {"genus": "Panthera", "species": "tigris", "subspecies": "altaica"}, "Siberian tiger", "Panthera tigris altaica"),
            ("Automatic taxobox", {}, "Jaguar (animal)", "Jaguar"),
            ("Taxobox", {"binomial": "Canis lupus", "genus": "Canis"}, "Wolf", "Canis lupus"),
            ("Infobox dog breed", {"species": "Canis familiaris"}, "Beagle", None),
            ("Hybridbox", {}, "Zebroid", None),
            ("Speciesbox", {"genus": "Vulpes"}, "Fox", None),
        ):
            with self.subTest(title=title):
                self.assertEqual(scientific_name(infobox_type, params, title), expected)

    def test_authority_year(self):
        self.assertEqual(authority_year("(Linnaeus, 1758)"), 1758)
        self.assertEqual(authority_year("Gray, 1825"), 1825)
        self.assertIsNone(authority_year("Linnaeus"))
        self.assertIsNone(authority_year(None))





class TestClean(unittest.TestCase):

    def test_wikitext(self):
        for text, expected in (
            ("The [[red fox]] is a [[Canidae|canid]].", "The red fox is a canid."),
            ("'''Arctic fox'''<ref name=\"a\">source</ref> lives", "Arctic fox lives"),
            ("Body {{convert|46|to|68|cm}} long", "Body 46 to 68 cm long"),
            ("A<!-- comment --> B", "A B"),
            ("[[File:Fox.jpg|thumb|A [[fox]] in snow]]Text", "Text"),
            ("Fox&nbsp;den", "Fox den"),
            ("Red fox ({{IPA|x}}; ''Vulpes vulpes'')", "Red fox (Vulpes vulpes)"),
            ("[https://example.com Example site]", "Example site"),
        ):
            with self.subTest(text=text):
                self.assertEqual(clean(text), expected)
