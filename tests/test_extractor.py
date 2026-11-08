import json
import unittest
import zipfile
from pathlib import Path

from modules.extractor import extract, is_animal_page





TESTS_DIR = Path(__file__).parent
PAGES_ZIP = TESTS_DIR / "unit_test_pages.zip"   # downloaded HTML pages used in tests
EXPECTED_FILE = TESTS_DIR / "expected.json"     # manually checked values for every page

with open(EXPECTED_FILE, encoding="utf-8") as f:
    EXPECTED = json.load(f)





def read_page(slug):
    with zipfile.ZipFile(PAGES_ZIP) as archive:
        for name in archive.namelist():
            # page can be directly in the ZIP or in a folder inside it (unit_test_pages/gorilla.html)
            if name == f"{slug}.html" or name.endswith(f"/{slug}.html"):
                return archive.read(name).decode("utf-8")

    raise FileNotFoundError(f"{slug}.html is not in {PAGES_ZIP}")


def list_summary(values):
    # lists are long (80 countries), so only count and first value are compared
    if values:
        first = values[0]
    else:
        first = None
    return {"count": len(values), "first": first}


def article_summary(article):
    has_intro = False
    headings = []

    for section in article:
        if section["heading"] is None:
            has_intro = True
        else:
            headings.append(section["heading"])

    return {"has_intro": has_intro, "headings": headings}





class TestExtractor(unittest.TestCase):

    def check_page(self, slug):
        expected = EXPECTED[slug]
        page = read_page(slug)

        self.assertEqual(is_animal_page(page), expected["is_animal_page"], f"{slug}: page type")

        if not expected["is_animal_page"]:
            return          # not animal pages are skipped by the extractor, nothing more to check

        record = extract(slug, page)

        # one text value per field
        for field, value in expected["fields"].items():
            with self.subTest(page=slug, field=field):
                self.assertEqual(record[field], value)

        # lists: count + first item
        for field, value in expected["lists"].items():
            with self.subTest(page=slug, field=field):
                self.assertEqual(list_summary(record[field]), value)

        # article: intro + headings of sections
        with self.subTest(page=slug, field="article"):
            self.assertEqual(article_summary(record["article"]), expected["article"])





def make_test(slug):
    def test(self):
        self.check_page(slug)
    return test


# one test for every page in expected.json (test_gorilla, test_blue_whale)
for slug in EXPECTED:
    test_name = "test_" + slug.replace("-", "_")
    setattr(TestExtractor, test_name, make_test(slug))


if __name__ == "__main__":
    unittest.main()