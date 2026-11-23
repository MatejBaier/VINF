import unittest

from modules.spark_join import MATCH_LEVELS, better_candidate, build_animal_keys, find_candidates, genus_and_epithet, normalize





def animal(slug, name, scientific):
    return {"id": slug, "name": name, "scientific_name": scientific}


def taxon(page_id, title, scientific, infobox="Speciesbox", redirects=None, lead="", categories=None):
    return {
        "page_id": page_id,
        "title": title,
        "scientific_name": scientific,
        "infobox": infobox,
        "redirects": redirects or [],
        "lead": lead,
        "categories": categories or [],
    }


# small set of a-z animals with the typical problems of the join
ANIMALS = [
    animal("red-fox", "Red Fox", "Vulpes vulpes"),
    animal("sun-bear", "Sun Bear", "Helarctos malayanus"),
    animal("beagle", "Beagle", "Canis lupus familiaris"),
    animal("chinook", "Chinook", "Canis lupus familiaris"),
    animal("chinook-salmon", "Chinook Salmon", "Oncorhynchus tshawytscha"),
    animal("basenji-dog", "Basenji Dog", "Canis lupus familiaris"),
    animal("ornate-rattlesnake", "Ornate Black-Tailed Rattlesnake", "Crotalus molossus ornatus"),
    animal("mule", "Mule", "Equus asinus × Equus caballus"),
    animal("zorse", "Zorse", "Equus ferus caballus × Equus quagga (hybrid)"),
    animal("squid", "Squid", "Teuthida"),
    animal("new-caledonian-gecko", "New Caledonian Gecko", "Correlophus auriculatus"),
    animal("abyssinian", "Abyssinian", "Felis catus"),
    animal("persian", "Persian", "Felis catus"),
    animal("pointer", "Pointer", "Canis lupus familiaris"),
]

LOOKUP = build_animal_keys(ANIMALS)


def best_match(taxa, slug):
    # the same as reduceByKey in Spark: the best candidate of all taxa for one animal
    best = None
    for one_taxon in taxa:
        for animal_id, candidate in find_candidates(one_taxon, LOOKUP):
            if animal_id == slug:
                best = candidate if best is None else better_candidate(best, candidate)
    if best is None:
        return None
    return best[2], best[1]          # (match type, page id)





class TestNormalize(unittest.TestCase):

    def test_normalize(self):
        for text, expected in (
            ("Adélie Penguin", "adelie penguin"),
            ("Orange-Crowned Warbler", "orange crowned warbler"),
            ("Owlfly (Ascalaphidae)", "owlfly"),
            ("Bredl’s Python", "bredl's python"),
            ("Equus asinus × Equus caballus", "equus asinus equus caballus"),
            ("  ", None),
            (None, None),
        ):
            with self.subTest(text=text):
                self.assertEqual(normalize(text), expected)

    def test_genus_and_epithet(self):
        self.assertEqual(genus_and_epithet("Correlophus auriculatus"), ("correlophus", "auriculatus"))
        self.assertEqual(genus_and_epithet("Crotalus molossus ornatus"), ("crotalus", "ornatus"))
        self.assertEqual(genus_and_epithet("Macaca"), ("macaca", None))
        self.assertEqual(genus_and_epithet(None), (None, None))





class TestAnimalKeys(unittest.TestCase):

    def test_shared_scientific_name(self):
        self.assertIn("beagle", LOOKUP["shared"])
        self.assertIn("chinook", LOOKUP["shared"])
        self.assertNotIn("red-fox", LOOKUP["shared"])

    def test_short_name(self):
        # "basenji dog" is also found as "basenji"
        self.assertIn(("basenji-dog", "name"), LOOKUP["keys"]["basenji"])

    def test_parent_taxa(self):
        self.assertIn(("ornate-rattlesnake", "parent"), LOOKUP["keys"]["crotalus molossus"])
        self.assertIn(("ornate-rattlesnake", "parent"), LOOKUP["keys"]["crotalus"])
        # hybrids have no parent taxa, Mule is not joined with the genus Equus
        self.assertNotIn(("mule", "parent"), LOOKUP["keys"].get("equus", []))





class TestCandidates(unittest.TestCase):

    def test_scientific_name_and_name(self):
        taxa = [taxon(1, "Red fox", "Vulpes vulpes")]
        self.assertEqual(best_match(taxa, "red-fox"), ("scientific_name_and_name", 1))

    def test_scientific_name_redirect(self):
        # mammals: scientific name is only a redirect to the common name
        taxa = [taxon(2, "Sun bear", "Helarctos malayanus", redirects=["Helarctos malayanus"])]
        self.assertEqual(best_match(taxa, "sun-bear"), ("scientific_name_and_name", 2))

    def test_species_moved_to_another_genus(self):
        # name matches, the genus is different, but the epithet is the same
        taxa = [taxon(3, "New Caledonian gecko", "Rhacodactylus auriculatus")]
        self.assertEqual(best_match(taxa, "new-caledonian-gecko"), ("name", 3))

    def test_breed_page_wins_over_species(self):
        taxa = [
            taxon(10, "Dog", "Canis familiaris", redirects=["Canis lupus familiaris"]),
            taxon(11, "Beagle", None, infobox="Infobox dog breed"),
        ]
        self.assertEqual(best_match(taxa, "beagle"), ("breed_name", 11))

    def test_breed_page_of_other_species(self):
        # "Abyssinian" is also a redirect to a horse breed, the cat must get the cat breed page
        taxa = [
            taxon(12, "Ethiopian horses", None, infobox="Infobox horse breed", redirects=["Abyssinian"]),
            taxon(13, "Abyssinian cat", None, infobox="Infobox cat breed"),
            taxon(14, "Cat", "Felis catus"),
        ]
        self.assertEqual(best_match(taxa, "abyssinian"), ("breed_name", 13))

    def test_breed_title_before_redirect(self):
        # "Pointer (German Shorthaired)" is only a redirect, the page with the same title wins
        taxa = [
            taxon(15, "German Shorthaired Pointer", None, infobox="Infobox dog breed", redirects=["Pointer (German Shorthaired)"]),
            taxon(16, "Pointer (dog breed)", None, infobox="Infobox dog breed"),
        ]
        self.assertEqual(best_match(taxa, "pointer"), ("breed_name", 16))

    def test_breed_without_page(self):
        taxa = [taxon(10, "Dog", "Canis familiaris", redirects=["Canis lupus familiaris"])]
        self.assertEqual(best_match(taxa, "basenji-dog"), ("shared_scientific_name", 10))

    def test_same_name_other_animal(self):
        # Chinook dog breed must not get the salmon and the salmon must not get the dog breed
        taxa = [
            taxon(20, "Chinook salmon", "Oncorhynchus tshawytscha", redirects=["Chinook"]),
            taxon(21, "Chinook (dog)", None, infobox="Infobox dog breed", redirects=["Chinook dog"]),
            taxon(10, "Dog", "Canis familiaris", redirects=["Canis lupus familiaris"]),
        ]
        self.assertEqual(best_match(taxa, "chinook"), ("breed_name", 21))
        self.assertEqual(best_match(taxa, "chinook-salmon"), ("scientific_name_and_name", 20))

    def test_name_without_genus(self):
        # page with the same name but from another genus is not joined
        taxa = [taxon(30, "Squid", "Loligo", lead="Loligo is a genus of squid")]
        self.assertIsNone(best_match(taxa, "squid"))

    def test_group_page_without_scientific_name(self):
        taxa = [taxon(31, "Squid", None, infobox="Paraphyletic group")]
        self.assertEqual(best_match(taxa, "squid"), ("name", 31))

    def test_hybrid_by_redirect(self):
        taxa = [taxon(40, "Zebroid", None, infobox="Hybridbox", redirects=["Zorse", "Zonkey (zebroid)"])]
        self.assertEqual(best_match(taxa, "zorse"), ("name", 40))

    def test_parent_taxon(self):
        taxa = [
            taxon(50, "Crotalus", "Crotalus", infobox="Automatic taxobox"),
            taxon(51, "Crotalus molossus", "Crotalus molossus"),
        ]
        self.assertEqual(best_match(taxa, "ornate-rattlesnake"), ("parent_taxon", 51))      # the species is closer than the genus

    def test_subgenus_is_not_parent(self):
        taxa = [taxon(60, "Zebra", "Equus (Hippotigris)", infobox="Automatic taxobox")]
        self.assertIsNone(best_match(taxa, "mule"))

    def test_match_levels_order(self):
        levels = [MATCH_LEVELS[name] for name in MATCH_LEVELS]
        self.assertEqual(levels, sorted(levels))
