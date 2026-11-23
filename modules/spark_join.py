import json
import re
import shutil
import time
import unicodedata

import config
from modules.wiki_extractor import BREED_KIND_REGEX





BRACKETS_REGEX = re.compile(r"\([^)]*\)")           # Owlfly (Ascalaphidae) -> Owlfly
NOT_WORD_REGEX = re.compile(r"[^a-z0-9' ]+")
SPACES_REGEX = re.compile(r"\s+")
GENERIC_WORD_REGEX = re.compile(r" (dog|cat|chicken|goat|cattle|rabbit|horse|pig|sheep|fish)$")      # "basenji dog" -> "basenji"

# breed infobox -> genera of animals which can get this breed page, Abyssinian cat is not the horse "Abyssinian"
BREED_GENERA = {
    "dog": {"canis"},
    "cat": {"felis"},
    "horse": {"equus"},
    "cattle": {"bos"},
    "cow": {"bos"},
    "water buffalo": {"bubalus"},
    "sheep": {"ovis"},
    "goat": {"capra"},
    "pig": {"sus"},
    "poultry": {"gallus", "anas", "anser", "meleagris", "numida", "coturnix", "cairina"},
    "pigeon": {"columba"},
    "goldfish": {"carassius"},
}

# match types from the best to the worst, lower number wins
MATCH_LEVELS = {
    "scientific_name_and_name": 1,      # scientific name and common name both match
    "name_and_lineage": 1.5,            # common name = wiki title and the a-z scientific name is a higher taxon of the page (Rabbit -> Leporidae)
    "scientific_name": 2,               # scientific name = wiki scientific name
    "scientific_name_redirect": 3,      # scientific name = wiki title or redirect (old name, synonym)
    "name": 4,                          # only common name = wiki title or redirect, the genus or species has to match too
    "breed_name": 5,                    # breed name = title of a wiki page with breed infobox
    "shared_scientific_name": 6,        # breed without own page -> page of its species (Abyssinian -> Cat)
    "parent_taxon": 7,                  # subspecies or species without own page -> page of its species or genus
}

# the wiki page is the animal's own page, the animal and the page are merged into one record (levels 1 to 5)
STRONG_MATCHES = {"scientific_name_and_name", "name_and_lineage", "scientific_name", "scientific_name_redirect", "name", "breed_name"}

# higher taxa of a wiki page, from its taxonomy templates
LINEAGE_FIELDS = ["family", "order", "class", "phylum"]

# source of a record, a merged record has both
SOURCE_AZ = "az"
SOURCE_WIKI = "wiki"
WIKI_SECTION = "Wikipedia"          # heading of the wiki lead in the article of a merged record

# a-z status text -> IUCN code, the same codes as in wiki
STATUS_CODES = {
    "Least Concern": "LC",
    "Near Threatened": "NT",
    "Vulnerable": "VU",
    "Endangered": "EN",
    "Critically Endangered": "CR",
    "Extinct in the Wild": "EW",
    "Extinct": "EX",
    "Data Deficient": "DD",
    "Not Evaluated": "NE",
}
IUCN_CODES = {"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"}

# wiki categories of extinct animals, "Extant Pleistocene first appearances" does not match
EXTINCT_CATEGORY_REGEX = re.compile(r"\bextinct\b|\bextinctions\b|\bfossil taxa\b|\bprehistoric\b", re.IGNORECASE)

# wiki rank -> taxon level with the same names as in a-z, other ranks only get a capital letter (subspecies -> Subspecies)
RANK_LEVELS = {
    "regnum": "Kingdom",
    "phylum": "Phylum",
    "classis": "Class",
    "subclassis": "Subclass",
    "ordo": "Order",
    "subordo": "Suborder",
    "superfamilia": "Superfamily",
    "familia": "Family",
    "subfamilia": "Subfamily",
    "tribus": "Tribe",
    "genus": "Genus",
    "subgenus": "Subgenus",
}





def normalize(text):
    # "Adélie Penguin" -> "adelie penguin", "Orange-Crowned Warbler" -> "orange crowned warbler"
    if not text:
        return None

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))      # remove accents
    text = text.lower().replace("’", "'")
    text = BRACKETS_REGEX.sub(" ", text)
    text = text.replace("-", " ")
    text = NOT_WORD_REGEX.sub(" ", text)
    text = SPACES_REGEX.sub(" ", text).strip()

    if text:
        return text
    return None


def genus_and_epithet(scientific_name):
    # "Correlophus auriculatus" -> ("correlophus", "auriculatus"), "Macaca" -> ("macaca", None)
    key = normalize(scientific_name)
    if not key:
        return (None, None)

    words = key.split()
    if len(words) == 1:
        return (words[0], None)
    return (words[0], words[-1])





def build_animal_keys(animals):
    # runs on the driver: key -> list of (animal id, key type), animals are small, so the table is broadcast to executors
    scientific_counts = {}
    for animal in animals:
        key = normalize(animal["scientific_name"])
        scientific_counts[key] = scientific_counts.get(key, 0) + 1

    keys = {}
    shared = set()          # ids of animals with a scientific name shared by more animals (breeds, morphs)

    for animal in animals:
        scientific_key = normalize(animal["scientific_name"])
        name_key = normalize(animal["name"])

        if scientific_key:
            keys.setdefault(scientific_key, []).append((animal["id"], "scientific"))
            if scientific_counts[scientific_key] > 1:
                shared.add(animal["id"])

            # parent taxa, "crotalus molossus ornatus" -> "crotalus molossus" -> "crotalus", not for hybrids (×)
            if "×" not in animal["scientific_name"]:
                words = scientific_key.split()
                for count in range(len(words) - 1, 0, -1):
                    keys.setdefault(" ".join(words[:count]), []).append((animal["id"], "parent"))
        if name_key:
            keys.setdefault(name_key, []).append((animal["id"], "name"))

            short_name_key = GENERIC_WORD_REGEX.sub("", name_key)
            if short_name_key != name_key:
                keys.setdefault(short_name_key, []).append((animal["id"], "name"))

    scientific_words = {}
    scientific_names = {}
    names = {}
    for animal in animals:
        scientific_words[animal["id"]] = genus_and_epithet(animal["scientific_name"])
        scientific_names[animal["id"]] = normalize(animal["scientific_name"])
        names[animal["id"]] = normalize(animal["name"])

    return {"keys": keys, "shared": shared, "scientific_words": scientific_words, "scientific_names": scientific_names, "names": names}





# functions below run on executors

def add_redirects(pair):
    # (title, (taxon, list of redirect titles or None)) -> taxon with redirects
    taxon, redirects = pair[1]
    taxon["redirects"] = sorted(redirects) if redirects else []
    return taxon


def name_confirmed(name_key, scientific_words, shared, taxon):
    # protection against same names: Chinook dog vs Chinook salmon, the genus must appear in the wiki page
    if not shared and taxon["scientific_name"] is None:
        titles = [normalize(title) for title in [taxon["title"]] + taxon["redirects"]]
        if name_key in titles:
            return True         # group or hybrid page without scientific name, exactly the same title or redirect, Squid -> Squid, Zorse -> Zebroid

    genus_key, epithet = scientific_words
    if not genus_key:
        return True

    text = " ".join([taxon["scientific_name"] or "", taxon["lead"] or ""] + taxon["categories"])
    if genus_key in normalize(text).split():
        return True

    # species moved to another genus: Correlophus auriculatus = Rhacodactylus auriculatus
    wiki_words = (normalize(taxon["scientific_name"]) or "").split()
    return epithet is not None and epithet in wiki_words


def match_type(found, animal_id, lookup):
    # found = set of ("scientific" / "name", wiki field) pairs for one animal and one taxon
    scientific = ("scientific", "scientific_name") in found
    scientific_redirect = ("scientific", "title") in found
    name = ("name", "title") in found or ("name", "scientific_name") in found
    shared = animal_id in lookup["shared"]

    if (scientific or scientific_redirect) and name:
        return "scientific_name_and_name"
    if shared and (scientific or scientific_redirect):
        return "shared_scientific_name"         # breeds have the same scientific name, used only if nothing better is found
    if scientific:
        return "scientific_name"
    if scientific_redirect:
        return "scientific_name_redirect"
    if ("parent", "scientific_name") in found:
        return "parent_taxon"
    return None


def lineage_keys(taxon):
    # normalized higher taxa and genus of a wiki page, Rabbit -> {leporidae, lagomorpha, mammalia, chordata}
    keys = set()
    for field in LINEAGE_FIELDS:
        key = normalize(taxon.get(field))
        if key:
            keys.add(key)

    genus = genus_and_epithet(taxon["scientific_name"])[0]
    if genus:
        keys.add(genus)
    return keys


def name_and_lineage(taxon, name_key, scientific_key):
    # the page title is exactly the a-z name (no brackets, Python (genus) does not count) and the a-z scientific name is above it
    if "(" in taxon["title"] or normalize(taxon["title"]) != name_key:
        return False
    return scientific_key is not None and scientific_key in lineage_keys(taxon)


def breed_genus_matches(taxon, scientific_words):
    # the genus of the animal must fit the breed infobox, "Infobox animal breed" fits every animal
    kind = BREED_KIND_REGEX.match(taxon["infobox"])
    if not kind:
        return True

    genera = BREED_GENERA.get(kind.group(1).lower())
    if genera is None:
        return True
    return scientific_words[0] in genera


def breed_title_matches(taxon, name_key):
    # the breed name is the page title itself, "Abyssinian cat" counts for "abyssinian"
    title_key = normalize(taxon["title"])
    return name_key == title_key or name_key == GENERIC_WORD_REGEX.sub("", title_key)


def find_candidates(taxon, lookup):
    # one taxon -> list of (animal id, (level, page id, match type, title)) for animals it matches
    wiki_keys = [(normalize(taxon["scientific_name"]), "scientific_name"), (normalize(taxon["title"]), "title")]
    for redirect in taxon["redirects"]:
        wiki_keys.append((normalize(redirect), "title"))        # redirect is another title of the same page

    if is_breed(taxon):
        # breed page "Abyssinian cat" is also found as "abyssinian", a-z has only "Abyssinian"
        for wiki_key, wiki_field in list(wiki_keys):
            if wiki_field == "title" and wiki_key:
                short_key = GENERIC_WORD_REGEX.sub("", wiki_key)
                if short_key != wiki_key:
                    wiki_keys.append((short_key, "title"))

    found = {}          # animal id -> set of (animal key type, wiki field)
    for wiki_key, wiki_field in wiki_keys:
        for animal_id, key_type in lookup["keys"].get(wiki_key, []):
            found.setdefault(animal_id, set()).add((key_type, wiki_field))

    candidates = []
    for animal_id, pairs in found.items():
        if is_breed(taxon):
            # breed page only for animals sharing the scientific name, Chinook dog -> Chinook (dog), not Chinook salmon
            if animal_id not in lookup["shared"] or ("name", "title") not in pairs:
                continue
            if breed_genus_matches(taxon, lookup["scientific_words"][animal_id]):
                level = MATCH_LEVELS["breed_name"]
                if not breed_title_matches(taxon, lookup["names"][animal_id]):
                    level += 0.5        # only a redirect has the name, Pointer -> "Pointer (dog breed)", not "Pointer (German Shorthaired)"
                candidates.append((animal_id, (level, taxon["page_id"], "breed_name", taxon["title"])))
            continue

        found_type = match_type(pairs, animal_id, lookup)

        # subgenus page "Equus (Hippotigris)" is not the genus "Equus", Mule -> Zebra would be wrong
        if found_type == "parent_taxon" and "(" in taxon["scientific_name"]:
            found_type = None

        if found_type is None and ("name", "title") in pairs:
            shared = animal_id in lookup["shared"]
            if name_confirmed(lookup["names"][animal_id], lookup["scientific_words"][animal_id], shared, taxon):
                found_type = "name"

        # a-z often has a family as the scientific name of a group (Rabbit = Leporidae), the page "Rabbit" fits better than "Leporidae"
        if found_type != "scientific_name_and_name" and name_and_lineage(taxon, lookup["names"][animal_id], lookup["scientific_names"][animal_id]):
            found_type = "name_and_lineage"

        if found_type:
            candidates.append((animal_id, (match_level(found_type, taxon), taxon["page_id"], found_type, taxon["title"])))
    return candidates


def match_level(found_type, taxon):
    # the closest parent wins: species "Crotalus molossus" (7.33) before genus "Crotalus" (7.5)
    level = MATCH_LEVELS[found_type]
    if found_type == "parent_taxon":
        level += 1 / (1 + len(normalize(taxon["scientific_name"]).split()))
    return level


def is_breed(taxon):
    return taxon["infobox"].endswith("breed")


def better_candidate(a, b):
    # lower level wins, same level -> lower page id (older and usually the main article)
    return min(a, b)





# merging of an a-z animal with its own wiki page, the result has the same fields for all records (a-z, wiki or both)

def is_fossil(taxon):
    # prehistoric animals have no IUCN status in wiki, but their categories say it (Pleistocene extinctions, Fossil taxa described in 1794)
    for category in taxon["categories"]:
        if EXTINCT_CATEGORY_REGEX.search(category):
            return True
    return False


def wiki_status(taxon):
    # IUCN code from the wiki infobox, EX for extinct and prehistoric animals, None if wiki does not know it
    status = taxon["status"]
    if status in IUCN_CODES:
        system = taxon["status_system"] or "IUCN"
        if system.upper().startswith("IUCN"):
            return status
    if status is not None and status.lower() == "fossil":
        return "EX"
    if status is None and (taxon["extinct"] or is_fossil(taxon)):
        return "EX"
    return None


def merged_status(animal, taxon):
    # a-z status wins, if it is not evaluated, the status from wiki is used
    code = STATUS_CODES.get(animal["status"], "NE")
    if code == "NE" and taxon is not None:
        return wiki_status(taxon) or code
    return code


def taxon_level(rank):
    # species -> Species, familia -> Family
    if not rank:
        return None
    return RANK_LEVELS.get(rank, rank.capitalize())


def wiki_domestication(taxon):
    # breeds and domestic animals (status DOM) are domesticated, wiki does not say more
    if taxon["rank"] == "breed" or taxon["status"] == "DOM":
        return "Domesticated"
    return None


def add_unique(values, new_values, known):
    # adds values which are not in known yet, case does not matter (Arctic Fox = Arctic fox)
    for value in new_values:
        if value and value.lower() not in known:
            known.add(value.lower())
            values.append(value)
    return values


def wiki_info(page_id, title, found_type):
    # which wiki page belongs to the record, only for the statistics and show record, it is not indexed
    return {"page_id": page_id, "title": title, "match": found_type}


def wiki_record(taxon):
    # wiki animal without an a-z page -> record with the same fields as the a-z animals, the other a-z fields are missing
    names = add_unique([], taxon["other_names"] + taxon["redirects"], {taxon["title"].lower()})
    return {
        "id": f"wiki-{taxon['page_id']}",
        "source": [SOURCE_WIKI],
        "name": taxon["title"],
        "scientific_name": taxon["scientific_name"],
        "also_known_as": names,
        "summary": taxon["lead"],
        "article": [],
        "locations": taxon["locations"],
        "categories": taxon["categories"],
        "class": taxon["class"],
        "taxon_level": taxon_level(taxon["rank"]),
        "status": wiki_status(taxon) or "NE",
        "domestication": wiki_domestication(taxon),
        "lifespan": taxon["lifespan"],
        "authority_year": taxon["authority_year"],
        "origin": taxon["origin"],
        "wiki": wiki_info(taxon["page_id"], taxon["title"], None),
    }


def az_record(animal, best):
    # a-z animal without its own wiki page, a weak match (breed -> page of its species) is only noted in "wiki"
    record = dict(animal)
    record["source"] = [SOURCE_AZ]
    record["also_known_as"] = animal["also_known_as"] or []
    record["locations"] = animal["locations"] or []
    record["article"] = animal["article"] or []
    record["status"] = merged_status(animal, None)
    record["lifespan"] = animal["lifespan_wild"]
    record["categories"] = []
    record["authority_year"] = None
    record["origin"] = None
    record["wiki"] = None
    if best:
        level, page_id, found_type, title = best
        record["wiki"] = wiki_info(page_id, title, found_type)
    return record


def merged_record(animal, taxon, found_type):
    # a-z animal + its own wiki page, in conflicts a-z wins (its fields are more complete), wiki fills what a-z does not have
    record = az_record(animal, None)
    record["source"] = [SOURCE_AZ, SOURCE_WIKI]

    # names: a-z name stays, the wiki title, other scientific name and redirects are added as other names
    known = {animal["name"].lower()}
    if animal["scientific_name"]:
        known.add(animal["scientific_name"].lower())
    names = add_unique([], record["also_known_as"], known)
    wiki_names = [taxon["title"], taxon["scientific_name"]] + taxon["other_names"] + taxon["redirects"]
    record["also_known_as"] = add_unique(names, wiki_names, known)
    record["scientific_name"] = animal["scientific_name"] or taxon["scientific_name"]

    # texts: a-z summary stays, the wiki lead is added to the article as one more section
    if taxon["lead"]:
        record["article"] = record["article"] + [{"heading": WIKI_SECTION, "text": taxon["lead"]}]

    # one value: a-z first, wiki only if a-z has nothing
    record["class"] = animal["class"] or taxon["class"]
    record["taxon_level"] = animal["taxon_level"] or taxon_level(taxon["rank"])
    record["status"] = merged_status(animal, taxon)
    record["lifespan"] = animal["lifespan_wild"] or taxon["lifespan"]
    record["domestication"] = animal["domestication"] or wiki_domestication(taxon)

    # list: places from both sources
    record["locations"] = add_unique([], record["locations"] + taxon["locations"], set())

    # only wiki has them
    record["categories"] = taxon["categories"]
    record["authority_year"] = taxon["authority_year"]
    record["origin"] = taxon["origin"]
    record["wiki"] = wiki_info(taxon["page_id"], taxon["title"], found_type)
    return record


def join_key(pair):
    # (animal id, (animal, best match or None)) -> (page id of its own wiki page or "a-z:slug", (animal, best match))
    animal, best = pair[1]
    if best and best[2] in STRONG_MATCHES:
        return (best[1], (animal, best))
    return ("a-z:" + animal["id"], (animal, best))       # this key is not in wiki, the animal stays alone in the full outer join


def merge_pair(pair):
    # row of the full outer join (key, (a-z part or None, taxon or None)) -> one record for the index
    az_part, taxon = pair[1]
    if az_part is None:
        return wiki_record(taxon)

    animal, best = az_part
    if taxon is None:
        return az_record(animal, best)
    return merged_record(animal, taxon, best[2])


def az_name_keys(animals, shared):
    # normalized names and scientific names of a-z animals -> slug, breeds share the scientific name, so only their name counts
    names = {}
    scientific_names = {}
    for animal in animals:
        key = normalize(animal["name"])
        if key:
            names.setdefault(key, animal["id"])
        key = normalize(animal["scientific_name"])
        if key and animal["id"] not in shared:
            scientific_names.setdefault(key, animal["id"])
    return {"name": names, "scientific name": scientific_names}


def duplicate_of(record, name_keys):
    # wiki record with the same name or scientific name as an a-z animal -> (slug of the animal, reason), else None
    if SOURCE_AZ in record["source"]:
        return None
    for reason, value in (("name", record["name"]), ("scientific name", record["scientific_name"])):
        key = normalize(value)
        if key in name_keys[reason]:
            return name_keys[reason][key], reason
    return None


def source_label(record):
    # ["az", "wiki"] -> "az+wiki"
    return "+".join(record["source"])


def to_json_line(record):
    return json.dumps(record, ensure_ascii=False)





def save_unmatched(unmatched, shared):
    with open(config.JOIN_UNMATCHED_FILE, "w", encoding="utf-8") as f:
        f.write("slug\tname\tscientific_name\treason\n")
        for animal in sorted(unmatched, key=lambda animal: animal["id"]):
            if animal["id"] in shared:
                reason = "shared scientific name (breed)"
            else:
                reason = "not found"
            f.write(f"{animal['id']}\t{animal['name']}\t{animal['scientific_name']}\t{reason}\n")


def save_duplicates(duplicates, animals_by_id, best_by_animal):
    # wiki animal with the same name as an a-z animal and the page the a-z animal was joined with
    with open(config.JOIN_DUPLICATES_FILE, "w", encoding="utf-8") as f:
        f.write("slug\tname\tsame\tjoined_with\tmatch\twiki_id\twiki_title\twiki_scientific_name\n")
        for (slug, reason), wiki_id, title, scientific in sorted(duplicates):
            animal = animals_by_id[slug]
            best = best_by_animal.get(slug)
            joined_with, found_type = (best[3], best[2]) if best else ("", "not joined")
            f.write(f"{slug}\t{animal['name']}\t{reason}\t{joined_with}\t{found_type}\t{wiki_id}\t{title}\t{scientific}\n")


def print_run_summary(animal_count, matched_count, types, unmatched, shared, sources, merged_pages, duplicates, seconds):
    shared_unmatched = 0         # breeds whose species has no wiki page
    for animal in unmatched:
        if animal["id"] in shared:
            shared_unmatched += 1

    print(f"\nA-Z animals:                {animal_count}")
    print(f"Joined with wiki:           {matched_count} ({matched_count / animal_count * 100:.1f} %)")

    print("\nJoined by")
    for found_type in MATCH_LEVELS:
        print(f" {found_type + ':':<28}{types.get(found_type, 0)}")

    print(f"\nNot joined:                 {len(unmatched)} -> {config.JOIN_UNMATCHED_FILE}")
    print(f" {'breeds (shared name):':<28}{shared_unmatched}")
    print(f" {'not found:':<28}{len(unmatched) - shared_unmatched}")

    print(f"\nRecords after the full outer join: {sum(sources.values())}")
    print(f" {'a-z + own wiki page:':<28}{sources.get(SOURCE_AZ + '+' + SOURCE_WIKI, 0)} ({merged_pages} unique wiki pages)")
    print(f" {'only a-z:':<28}{sources.get(SOURCE_AZ, 0)}")
    print(f" {'only wiki:':<28}{sources.get(SOURCE_WIKI, 0)}")

    print(f"\nWiki animals with the name of an a-z animal: {len(duplicates)} -> {config.JOIN_DUPLICATES_FILE}")
    for reason in ("name", "scientific name"):
        count = sum(1 for duplicate in duplicates if duplicate[0][1] == reason)
        print(f" {'same ' + reason + ':':<28}{count}")

    print(f"\nSaved -> {config.ANIMALS_WIKI_DIR}")
    print(f"Done in {seconds / 60:.1f} min")


def run():
    for folder in (config.SPARK_ANIMALS_DIR, config.WIKI_TAXA_DIR, config.WIKI_REDIRECTS_DIR):
        if not folder.exists():
            print(f"{folder} not found - run Spark extraction of animals and wiki first")
            return

    from modules.spark_utils import create_session      # pyspark is imported only when Spark is used
    from pyspark import StorageLevel

    start = time.time()
    spark = create_session("AnimalsWikiJoin")
    sc = spark.sparkContext

    animals = sc.textFile(str(config.SPARK_ANIMALS_DIR)).map(json.loads).cache()
    taxa = sc.textFile(str(config.WIKI_TAXA_DIR)).map(json.loads)
    redirects = sc.textFile(str(config.WIKI_REDIRECTS_DIR)).map(json.loads)

    # 1) wiki join: every taxon gets the list of its redirects, (title, taxon) x (title, [redirects])
    redirects_by_target = redirects.map(lambda redirect: (redirect["target"], redirect["title"])).groupByKey()
    taxa = taxa.keyBy(lambda taxon: taxon["title"]).leftOuterJoin(redirects_by_target).map(add_redirects).cache()

    # 2) broadcast join: animal keys are small, every executor gets a copy and checks its taxa without shuffling the wiki
    animal_list = animals.collect()
    lookup = sc.broadcast(build_animal_keys(animal_list))
    candidates = taxa.flatMap(lambda taxon: find_candidates(taxon, lookup.value))

    # only the best wiki page for every animal is kept
    best = candidates.reduceByKey(better_candidate).cache()

    # 3) full outer join by page id: animal with its own wiki page is merged with it, other animals and wiki animals stay alone
    animals_by_page = animals.keyBy(lambda animal: animal["id"]).leftOuterJoin(best).map(join_key)
    taxa_by_page = taxa.keyBy(lambda taxon: taxon["page_id"])
    joined = animals_by_page.fullOuterJoin(taxa_by_page).map(merge_pair).persist(StorageLevel.MEMORY_AND_DISK)

    if config.ANIMALS_WIKI_DIR.exists():
        shutil.rmtree(config.ANIMALS_WIKI_DIR)
    joined.map(to_json_line).coalesce(1).saveAsTextFile(str(config.ANIMALS_WIKI_DIR))       # one file for the indexer

    # statistics
    matched_count = best.count()
    types = best.map(lambda pair: pair[1][2]).countByValue()
    best_by_animal = best.collectAsMap()
    sources = joined.map(source_label).countByValue()
    merged = joined.filter(lambda record: SOURCE_AZ in record["source"] and SOURCE_WIKI in record["source"])
    merged_pages = merged.map(lambda record: record["wiki"]["page_id"]).distinct().count()
    unmatched = joined.filter(lambda record: record["source"] == [SOURCE_AZ] and record["wiki"] is None).collect()
    shared = lookup.value["shared"]

    # the same animal from a-z and from wiki as two records = missed join, wiki animals with the name of an a-z animal are listed
    name_keys = sc.broadcast(az_name_keys(animal_list, shared))
    duplicates = joined.map(lambda record: (duplicate_of(record, name_keys.value), record["id"], record["name"], record["scientific_name"]))
    duplicates = duplicates.filter(lambda row: row[0] is not None).collect()

    spark.stop()

    animals_by_id = {animal["id"]: animal for animal in animal_list}
    save_unmatched(unmatched, shared)
    save_duplicates(duplicates, animals_by_id, best_by_animal)
    print_run_summary(len(animal_list), matched_count, types, unmatched, shared, sources, merged_pages, duplicates, time.time() - start)





def short(record):
    # long texts and lists are shortened for printing, only headings of the article are shown
    record = dict(record)
    for field, value in record.items():
        if isinstance(value, str) and len(value) > 300:
            record[field] = value[:300] + " ..."
        elif isinstance(value, list) and len(value) > 8 and field != "article":
            record[field] = value[:8] + [f"... {len(value) - 8} more"]
    record["article"] = [section["heading"] for section in record["article"]]
    return record


def show_record():
    if not config.ANIMALS_WIKI_DIR.exists():
        print("Joined data not found - run the join first")
        return

    text = input("Slug, wiki id or name (red-fox, wiki-2208, Red fox): ").strip().lower()

    for path in sorted(config.ANIMALS_WIKI_DIR.glob("part-*")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record["id"] != text and record["name"].lower() != text:
                    continue

                print(json.dumps(short(record), ensure_ascii=False, indent=1))
                return

    print(f"'{text}' not found")
