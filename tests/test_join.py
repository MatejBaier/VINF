import unittest

from modules.spark_join import (MATCH_LEVELS, WIKI_SECTION, az_name_keys, better_candidate, build_animal_keys, duplicate_of,
                                find_candidates, genus_and_epithet, join_key, merge_pair, merged_record, merged_status, normalize,
                                taxon_level, wiki_record, wiki_status)





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
    animal("rabbit", "Rabbit", "Leporidae"),
    animal("python", "Python", "Pythonidae"),
    animal("ostrich", "Ostrich", "Struthio camelus"),
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

    def test_name_and_lineage(self):
        # a-z has the family as the scientific name, the page with the same name below the family is better than the family page
        rabbit_page = taxon(70, "Rabbit", None, infobox="Paraphyletic group")
        rabbit_page.update({"family": "Leporidae", "order": "Lagomorpha"})
        taxa = [taxon(71, "Leporidae", "Leporidae", infobox="Automatic taxobox"), rabbit_page]
        self.assertEqual(best_match(taxa, "rabbit"), ("name_and_lineage", 70))

    def test_name_and_lineage_needs_exact_title(self):
        # "Python (genus)" is not the page of all pythons, the family page stays
        genus_page = taxon(80, "Python (genus)", "Python", infobox="Automatic taxobox")
        genus_page["family"] = "Pythonidae"
        taxa = [taxon(81, "Pythonidae", "Pythonidae", infobox="Automatic taxobox"), genus_page]
        self.assertEqual(best_match(taxa, "python"), ("scientific_name", 81))

    def test_species_is_not_moved_to_genus(self):
        # Ostrich in a-z is the species Struthio camelus, the genus page "Ostrich" has it only as a genus
        genus_page = taxon(90, "Ostrich", "Struthio", infobox="Automatic taxobox")
        genus_page["family"] = "Struthionidae"
        taxa = [taxon(91, "Common ostrich", "Struthio camelus"), genus_page]
        self.assertEqual(best_match(taxa, "ostrich"), ("scientific_name", 91))

    def test_match_levels_order(self):
        levels = [MATCH_LEVELS[name] for name in MATCH_LEVELS]
        self.assertEqual(levels, sorted(levels))





# a-z animal and wiki animal with all fields used in the merge
def az_animal(slug, name, scientific, **fields):
    record = {
        "id": slug, "name": name, "scientific_name": scientific, "also_known_as": None, "summary": "A-Z summary.",
        "article": [{"heading": "Facts", "text": "A-Z text."}], "locations": ["Norway"], "class": "Mammalia",
        "taxon_level": "Species", "status": "Least Concern", "lifespan_wild": "1–10 years", "domestication": "Wild",
    }
    record.update(fields)
    return record


def wiki_taxon(page_id, title, scientific, **fields):
    record = {
        "page_id": page_id, "title": title, "scientific_name": scientific, "infobox": "Speciesbox", "rank": "species",
        "redirects": [], "other_names": [], "lead": "Wiki lead.", "categories": [], "locations": ["Europe"],
        "class": "Mammalia", "status": "LC", "status_system": "IUCN3.1", "extinct": False, "lifespan": None,
        "authority_year": 1758, "origin": None,
    }
    record.update(fields)
    return record


def full_outer_join(animals, taxa):
    # the same as the Spark job: best match for every animal, key by page id, full outer join, merge
    lookup = build_animal_keys(animals)
    best = {}
    for one_taxon in taxa:
        for animal_id, candidate in find_candidates(one_taxon, lookup):
            best[animal_id] = candidate if animal_id not in best else better_candidate(best[animal_id], candidate)

    left = {}
    for animal in animals:
        key, value = join_key((animal["id"], (animal, best.get(animal["id"]))))
        left.setdefault(key, []).append(value)
    right = {one_taxon["page_id"]: one_taxon for one_taxon in taxa}

    records = []
    for key in list(left) + [page_id for page_id in right if page_id not in left]:
        for az_part in left.get(key, [None]):
            records.append(merge_pair((key, (az_part, right.get(key)))))
    return records





class TestMerge(unittest.TestCase):

    def test_conflicts_az_wins(self):
        animal = az_animal("arctic-fox", "Arctic Fox", "Vulpes lagopus", also_known_as=["Polar fox"])
        wiki = wiki_taxon(2208, "Arctic fox", "Alopex lagopus", redirects=["Polar Fox", "White fox"], status="VU",
                          categories=["Mammals of Europe"], origin=None)
        record = merged_record(animal, wiki, "scientific_name_and_name")

        self.assertEqual(record["source"], ["az", "wiki"])
        self.assertEqual(record["name"], "Arctic Fox")                         # a-z name stays
        self.assertEqual(record["scientific_name"], "Vulpes lagopus")          # a-z scientific name stays
        self.assertEqual(record["also_known_as"], ["Polar fox", "Alopex lagopus", "White fox"])     # wiki names added, no duplicates
        self.assertEqual(record["summary"], "A-Z summary.")
        self.assertEqual(record["article"][-1], {"heading": WIKI_SECTION, "text": "Wiki lead."})
        self.assertEqual(record["status"], "LC")                               # a-z status wins
        self.assertEqual(record["locations"], ["Norway", "Europe"])            # places from both
        self.assertEqual(record["categories"], ["Mammals of Europe"])          # only wiki has them
        self.assertEqual(record["authority_year"], 1758)
        self.assertEqual(record["lifespan"], "1–10 years")
        self.assertEqual(record["wiki"]["match"], "scientific_name_and_name")

    def test_wiki_fills_missing_values(self):
        animal = az_animal("dog-x", "Dog X", "Canis lupus familiaris", status="Not Evaluated", domestication=None,
                           taxon_level=None, lifespan_wild=None)
        animal["class"] = None          # "class" can not be a keyword argument
        wiki = wiki_taxon(5, "Dog X", None, infobox="Infobox dog breed", rank="breed", status=None, lifespan="12–15 years",
                          origin="England", authority_year=None)
        record = merged_record(animal, wiki, "breed_name")
        self.assertEqual(record["class"], "Mammalia")
        self.assertEqual(record["taxon_level"], "Breed")
        self.assertEqual(record["lifespan"], "12–15 years")
        self.assertEqual(record["domestication"], "Domesticated")
        self.assertEqual(record["origin"], "England")
        self.assertEqual(record["status"], "NE")

    def test_wiki_record(self):
        wiki = wiki_taxon(77, "Pallas's cat", "Otocolobus manul", redirects=["Manul", "Pallas's Cat"], rank="species", status="LC")
        record = wiki_record(wiki)
        self.assertEqual(record["id"], "wiki-77")
        self.assertEqual(record["source"], ["wiki"])
        self.assertEqual(record["name"], "Pallas's cat")
        self.assertEqual(record["also_known_as"], ["Manul"])                    # title in another case is not repeated
        self.assertEqual(record["summary"], "Wiki lead.")
        self.assertEqual(record["taxon_level"], "Species")
        self.assertEqual(record["status"], "LC")

    def test_status(self):
        self.assertEqual(merged_status({"status": "Critically Endangered"}, None), "CR")
        self.assertEqual(merged_status({"status": "Least Concern"}, wiki_taxon(1, "x", None, status="EN")), "LC")
        self.assertEqual(merged_status({"status": "Not Evaluated"}, wiki_taxon(1, "x", None, status="VU")), "VU")
        self.assertIsNone(wiki_status(wiki_taxon(1, "x", None, status="G5", status_system="TNC")))         # other system than IUCN
        self.assertIsNone(wiki_status(wiki_taxon(1, "x", None, status="DOM", status_system=None)))
        self.assertEqual(wiki_status(wiki_taxon(1, "x", None, status="fossil", status_system=None)), "EX")
        self.assertEqual(wiki_status(wiki_taxon(1, "x", None, status=None, extinct=True)), "EX")
        fossil = wiki_taxon(1, "x", None, status=None, categories=["Pleistocene bears", "Fossil taxa described in 1794"])
        living = wiki_taxon(1, "x", None, status=None, categories=["Extant Pleistocene first appearances"])
        self.assertEqual(wiki_status(fossil), "EX")
        self.assertIsNone(wiki_status(living))

    def test_taxon_level(self):
        self.assertEqual(taxon_level("species"), "Species")
        self.assertEqual(taxon_level("familia"), "Family")
        self.assertEqual(taxon_level("subspecies"), "Subspecies")
        self.assertIsNone(taxon_level(None))





class TestFullOuterJoin(unittest.TestCase):

    def test_join_key(self):
        animal = az_animal("beagle", "Beagle", "Canis lupus familiaris")
        self.assertEqual(join_key(("beagle", (animal, (5, 11, "breed_name", "Beagle"))))[0], 11)           # own page
        self.assertEqual(join_key(("beagle", (animal, (6, 10, "shared_scientific_name", "Dog"))))[0], "a-z:beagle")
        self.assertEqual(join_key(("beagle", (animal, None)))[0], "a-z:beagle")

    def test_all_records_stay(self):
        animals = [
            az_animal("red-fox", "Red Fox", "Vulpes vulpes"),
            az_animal("basenji-dog", "Basenji Dog", "Canis lupus familiaris"),
            az_animal("beagle", "Beagle", "Canis lupus familiaris"),
            az_animal("unicorn", "Unicorn", "Equus unicornis"),
        ]
        taxa = [
            wiki_taxon(1, "Red fox", "Vulpes vulpes"),
            wiki_taxon(10, "Dog", "Canis familiaris", redirects=["Canis lupus familiaris"]),
            wiki_taxon(11, "Beagle", None, infobox="Infobox dog breed", rank="breed"),
            wiki_taxon(12, "Arctic fox", "Vulpes lagopus"),
        ]
        records = {record["id"]: record for record in full_outer_join(animals, taxa)}

        self.assertEqual(len(records), 6)                                      # 4 a-z animals + 2 wiki pages without an a-z animal
        self.assertEqual(records["red-fox"]["source"], ["az", "wiki"])
        self.assertEqual(records["beagle"]["source"], ["az", "wiki"])
        self.assertEqual(records["basenji-dog"]["source"], ["az"])             # weak match, only noted
        self.assertEqual(records["basenji-dog"]["wiki"]["match"], "shared_scientific_name")
        self.assertEqual(records["unicorn"]["wiki"], None)                     # not joined, but it stays
        self.assertEqual(records["wiki-10"]["source"], ["wiki"])               # Dog is not an own page of any a-z animal here
        self.assertEqual(records["wiki-12"]["name"], "Arctic fox")
        self.assertNotIn("wiki-1", records)                                    # merged with Red Fox, not twice

    def test_possible_duplicates(self):
        animals = [az_animal("lion", "Lion", "Panthera leo"), az_animal("beagle", "Beagle", "Canis lupus familiaris")]
        keys = az_name_keys(animals, shared={"beagle"})
        self.assertEqual(duplicate_of(wiki_record(wiki_taxon(3, "Lion (animal)", None)), keys), ("lion", "name"))      # brackets do not matter
        self.assertEqual(duplicate_of(wiki_record(wiki_taxon(4, "African lion", "Panthera leo")), keys), ("lion", "scientific name"))
        self.assertIsNone(duplicate_of(wiki_record(wiki_taxon(5, "Dingo", "Canis lupus familiaris")), keys))     # breeds share it
        merged = merged_record(animals[0], wiki_taxon(6, "Lion", "Panthera leo"), "scientific_name_and_name")
        self.assertIsNone(duplicate_of(merged, keys))                          # a-z records are not duplicates
