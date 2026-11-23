import bz2
import unittest
from pathlib import Path

from modules.wiki_extractor import (add_lineage, authority_year, category_locations, clean, extract, extract_taxonomy, find_infobox, is_animal,
                                    lineage, page_name, parse_params, parse_xml_page, scientific_name, taxon_name, templates_by_name)





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

    def test_new_fields(self):
        fox = extract(PAGES["Arctic fox"])
        self.assertEqual(fox["rank"], "species")
        self.assertEqual(fox["taxonomy"], ["Vulpes"])           # lineage starts at the genus
        self.assertIn("Arctic", fox["locations"])               # Mammals of the Arctic
        self.assertIn("Europe", fox["locations"])

        beagle = extract(PAGES["Beagle"])
        self.assertEqual(beagle["rank"], "breed")
        self.assertEqual(beagle["other_names"], ["English Beagle"])
        self.assertEqual(beagle["taxonomy"], [])

        dolphin = extract(PAGES["Dolphin"])
        self.assertEqual(dolphin["taxonomy"], ["Odontoceti"])   # Paraphyletic group has its parent
        self.assertEqual(dolphin["other_names"], ["Dolphins"])

        self.assertTrue(extract(PAGES["Aurochs"])["extinct"])  # extinct = 1627
        self.assertFalse(fox["extinct"])
        self.assertIsNone(extract(PAGES["Anaconda"])["rank"])  # Automatic taxobox, the rank is in its template

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





# taxonomy templates as they are in the dump, Mammalia/skip skips some levels (same as)
TEMPLATE_TEXTS = {
    "Vulpes": "{{Don't edit this line {{{machine code|}}}\n|rank=genus\n|link=Vulpes\n|parent=Canidae\n|refs={{cite web|title=x}}\n}}",
    "Canidae": "{{Don't edit this line {{{machine code|}}}\n|rank=familia\n|link=Canidae\n|parent=Carnivora\n}}",
    "Carnivora": "{{Don't edit this line {{{machine code|}}}\n|rank=ordo\n|link=Carnivora\n|parent=Theria/skip\n}}",
    "Theria/skip": "{{Don't edit this line {{{machine code|}}}\n|same_as=Theria\n|parent=Mammalia/skip\n}}",
    "Theria": "{{Don't edit this line {{{machine code|}}}\n|rank=subclassis\n|parent=Mammalia\n}}",
    "Mammalia/skip": "{{Don't edit this line {{{machine code|}}}\n|same as=Mammalia\n|parent=Chordata\n}}",
    "Mammalia": "{{Don't edit this line {{{machine code|}}}\n|rank=classis\n|parent=Mammaliaformes/skip\n}}",
    "Chordata": "{{Don't edit this line {{{machine code|}}}\n|rank=phylum\n|parent=Animalia\n}}",
    "Animalia": "<noinclude>{{pp-template}}</noinclude>{{Don't edit this line {{{machine code|}}}\n|rank=regnum\n|link=Animal|Animalia\n|parent=Choanozoa\n}}",
    "Eunectes": "{{Don't edit this line {{{machine code|}}}\n|rank=genus\n|parent=Boidae\n|extinct=no\n}}",
    "Boidae": "{{Don't edit this line {{{machine code|}}}\n|rank=familia\n|parent=Reptilia\n}}",
    "Reptilia": "{{Don't edit this line {{{machine code|}}}\n|rank=classis\n|parent=Chordata\n}}",
    "Quercus": "{{Don't edit this line {{{machine code|}}}\n|rank=genus\n|parent=Plantae\n}}",
    "Plantae": "{{Don't edit this line {{{machine code|}}}\n|rank=regnum\n|link=Plant|Plantae\n|parent=Archaeplastida\n}}",
    "Agelenidae": "{{Don't edit this line {{{machine code|}}}\n|rank=familia\n|parent=RTA_clade\n}}",
    "RTA clade": "{{Don't edit this line {{{machine code|}}}\n|rank=clade\n|parent=Animalia\n}}",
}


def template_page(name, text, redirect=None):
    return {"title": "Template:Taxonomy/" + name, "namespace": 10, "page_id": 1, "redirect": redirect, "text": text}


def build_templates():
    templates = [extract_taxonomy(template_page(name, text)) for name, text in TEMPLATE_TEXTS.items()]
    templates.append(extract_taxonomy(template_page("Vulpes (genus)", "#REDIRECT [[Template:Taxonomy/Vulpes]]", "Template:Taxonomy/Vulpes")))
    return templates_by_name(templates)


TEMPLATES = build_templates()


def taxon(infobox, taxonomy, rank=None, taxobox=None):
    # taxon record before the lineage, as it comes from extract()
    return {"infobox": infobox, "rank": rank, "taxonomy": taxonomy, "lineage": taxobox or {}}





class TestTaxonomyTemplates(unittest.TestCase):

    def test_template_params(self):
        template = TEMPLATES["Vulpes"]
        self.assertEqual(template["rank"], "genus")
        self.assertEqual(template["parent"], "Canidae")        # the parameters of refs are not used

    def test_same_as(self):
        # Mammalia/skip takes the rank of Mammalia, but keeps its own parent
        self.assertEqual(TEMPLATES["Mammalia/skip"]["rank"], "classis")
        self.assertEqual(TEMPLATES["Mammalia/skip"]["parent"], "Chordata")
        self.assertEqual(TEMPLATES["Theria/skip"]["rank"], "subclassis")

    def test_redirect_template(self):
        self.assertEqual(TEMPLATES["Vulpes (genus)"]["parent"], "Vulpes")
        self.assertIsNone(TEMPLATES["Vulpes (genus)"]["rank"])

    def test_names(self):
        self.assertEqual(page_name("RTA_clade"), "RTA clade")
        self.assertEqual(page_name("crown Formicidae"), "crown Formicidae")     # subpage names keep their case
        self.assertEqual(page_name("{{Taxonomy/Gruiformes"), "Gruiformes")
        self.assertEqual(page_name("Prorhynchidae#Genera"), "Prorhynchidae")
        self.assertIsNone(page_name(None))
        self.assertEqual(taxon_name("Mammalia/skip"), "Mammalia")
        self.assertEqual(taxon_name("Morus (bird)"), "Morus")





class TestLineage(unittest.TestCase):

    def test_chain(self):
        names = [name for name, rank in lineage(["Vulpes"], TEMPLATES)]
        self.assertEqual(names[:3], ["Vulpes", "Canidae", "Carnivora"])
        self.assertIn("Mammalia/skip", names)
        self.assertNotIn("Mammalia", names)                     # skipped by Mammalia/skip
        self.assertEqual(names[-1], "Animalia")

    def test_species(self):
        fox = add_lineage(taxon("Speciesbox", ["Vulpes"], rank="species"), TEMPLATES)
        self.assertEqual(fox["kingdom"], "Animalia")
        self.assertEqual(fox["class"], "Mammalia")
        self.assertEqual(fox["order"], "Carnivora")
        self.assertEqual(fox["family"], "Canidae")
        self.assertEqual(fox["rank"], "species")
        self.assertTrue(is_animal(fox))
        self.assertNotIn("taxonomy", fox)                       # helper fields are removed

    def test_automatic_taxobox_rank(self):
        anaconda = add_lineage(taxon("Automatic taxobox", ["Eunectes", "Anaconda"]), TEMPLATES)
        self.assertEqual(anaconda["rank"], "genus")
        self.assertEqual(anaconda["class"], "Reptilia")

    def test_first_known_name(self):
        # the first name has no template, the second one is used
        spider = add_lineage(taxon("Speciesbox", ["Eratigena", "Agelenidae"], rank="species"), TEMPLATES)
        self.assertEqual(spider["kingdom"], "Animalia")         # parent RTA_clade = template "RTA clade"

    def test_redirect_on_the_way(self):
        fox = add_lineage(taxon("Speciesbox", ["Vulpes (genus)"], rank="species"), TEMPLATES)
        self.assertEqual(fox["class"], "Mammalia")

    def test_plants_and_unknown_are_not_animals(self):
        oak = add_lineage(taxon("Speciesbox", ["Quercus"], rank="species"), TEMPLATES)
        self.assertEqual(oak["kingdom"], "Plantae")
        self.assertFalse(is_animal(oak))

        unknown = add_lineage(taxon("Speciesbox", ["Nothing"], rank="species"), TEMPLATES)
        self.assertIsNone(unknown["kingdom"])
        self.assertFalse(is_animal(unknown))

    def test_breed(self):
        beagle = add_lineage(taxon("Infobox dog breed", [], rank="breed"), TEMPLATES)
        self.assertTrue(is_animal(beagle))
        self.assertEqual(beagle["class"], "Mammalia")

    def test_old_taxobox(self):
        wolf = add_lineage(taxon("Taxobox", [], rank="species", taxobox={"kingdom": "Animalia", "class": "Mammalia"}), TEMPLATES)
        self.assertTrue(is_animal(wolf))
        self.assertEqual(wolf["class"], "Mammalia")

    def test_cycle(self):
        broken = templates_by_name([
            {"name": "A", "rank": "genus", "parent": "B", "same_as": None, "extinct": False},
            {"name": "B", "rank": "familia", "parent": "A", "same_as": None, "extinct": False},
        ])
        self.assertEqual(len(lineage(["A"], broken)), 2)





class TestLocations(unittest.TestCase):

    def test_category_locations(self):
        categories = [
            "Mammals of Europe",
            "Endemic fauna of the Canary Islands",
            "Fish of the Atlantic Ocean",
            "Birds of prey",                        # not a place
            "Natural history of Peru",              # not where it lives
            "Mammals described in 1758",
            "Fauna of Europe",                      # the same place again
        ]
        self.assertEqual(category_locations(categories), ["Europe", "Canary Islands", "Atlantic Ocean"])
