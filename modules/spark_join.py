import json
import re
import shutil
import time
import unicodedata

import config





BRACKETS_REGEX = re.compile(r"\([^)]*\)")           # Owlfly (Ascalaphidae) -> Owlfly
NOT_WORD_REGEX = re.compile(r"[^a-z0-9' ]+")
SPACES_REGEX = re.compile(r"\s+")
GENERIC_WORD_REGEX = re.compile(r" (dog|cat|chicken|goat|cattle|rabbit|horse|pig|sheep|fish)$")      # "basenji dog" -> "basenji"
BREED_KIND_REGEX = re.compile(r"^Infobox (.+) breed$")         # "Infobox dog breed" -> "dog"

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
    "scientific_name": 2,               # scientific name = wiki scientific name
    "scientific_name_redirect": 3,      # scientific name = wiki title or redirect (old name, synonym)
    "name": 4,                          # only common name = wiki title or redirect, the genus or species has to match too
    "breed_name": 5,                    # breed name = title of a wiki page with breed infobox
    "shared_scientific_name": 6,        # breed without own page -> page of its species (Abyssinian -> Cat)
    "parent_taxon": 7,                  # subspecies or species without own page -> page of its species or genus
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
    names = {}
    for animal in animals:
        scientific_words[animal["id"]] = genus_and_epithet(animal["scientific_name"])
        names[animal["id"]] = normalize(animal["name"])

    return {"keys": keys, "shared": shared, "scientific_words": scientific_words, "names": names}





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
    # one taxon -> list of (animal id, (level, page id, match type)) for animals it matches
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
                candidates.append((animal_id, (level, taxon["page_id"], "breed_name")))
            continue

        found_type = match_type(pairs, animal_id, lookup)

        # subgenus page "Equus (Hippotigris)" is not the genus "Equus", Mule -> Zebra would be wrong
        if found_type == "parent_taxon" and "(" in taxon["scientific_name"]:
            found_type = None

        if found_type is None and ("name", "title") in pairs:
            shared = animal_id in lookup["shared"]
            if name_confirmed(lookup["names"][animal_id], lookup["scientific_words"][animal_id], shared, taxon):
                found_type = "name"

        if found_type:
            candidates.append((animal_id, (match_level(found_type, taxon), taxon["page_id"], found_type)))
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


def wiki_part(taxon, found_type):
    # attributes from wiki, which are added to the animal record
    return {
        "page_id": taxon["page_id"],
        "title": taxon["title"],
        "infobox": taxon["infobox"],
        "scientific_name": taxon["scientific_name"],
        "authority": taxon["authority"],
        "authority_year": taxon["authority_year"],
        "status": taxon["status"],
        "status_system": taxon["status_system"],
        "origin": taxon.get("origin"),
        "categories": taxon["categories"],
        "redirects": taxon["redirects"],
        "lead": taxon["lead"],
        "match_type": found_type,
    }


def add_wiki(pair):
    # (animal id, (animal, (taxon, match type) or None)) -> animal record with "wiki"
    animal, match = pair[1]
    if match:
        taxon, found_type = match
        animal["wiki"] = wiki_part(taxon, found_type)
    else:
        animal["wiki"] = None
    return animal


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


def print_run_summary(animal_count, matched_count, unique_pages, types, unmatched, shared, seconds):
    shared_unmatched = 0         # breeds whose species has no wiki page
    for animal in unmatched:
        if animal["id"] in shared:
            shared_unmatched += 1

    print(f"\nAnimals:                    {animal_count}")
    print(f"Joined with wiki:           {matched_count} ({matched_count / animal_count * 100:.1f} %)")
    print(f"Unique wiki pages joined:   {unique_pages}")

    print("\nJoined by")
    for found_type in MATCH_LEVELS:
        print(f" {found_type + ':':<28}{types.get(found_type, 0)}")

    print(f"\nNot joined:                 {len(unmatched)} -> {config.JOIN_UNMATCHED_FILE}")
    print(f" {'breeds (shared name):':<28}{shared_unmatched}")
    print(f" {'not found:':<28}{len(unmatched) - shared_unmatched}")

    print(f"\nSaved -> {config.ANIMALS_WIKI_DIR}")
    print(f"Done in {seconds / 60:.1f} min")


def run():
    for folder in (config.SPARK_ANIMALS_DIR, config.WIKI_TAXA_DIR, config.WIKI_REDIRECTS_DIR):
        if not folder.exists():
            print(f"{folder} not found - run Spark extraction of animals and wiki first")
            return

    from modules.spark_utils import create_session      # pyspark is imported only when Spark is used

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

    # 3) join taxa back to the best matches by page id: (page id, (animal id, type)) x (page id, taxon)
    matches_by_page = best.map(lambda pair: (pair[1][1], (pair[0], pair[1][2])))
    taxa_by_page = taxa.keyBy(lambda taxon: taxon["page_id"])
    matched = matches_by_page.join(taxa_by_page).map(lambda pair: (pair[1][0][0], (pair[1][1], pair[1][0][1])))

    # 4) every animal stays in the output, the ones without a wiki page have "wiki": null
    joined = animals.keyBy(lambda animal: animal["id"]).leftOuterJoin(matched).map(add_wiki)

    if config.ANIMALS_WIKI_DIR.exists():
        shutil.rmtree(config.ANIMALS_WIKI_DIR)
    joined.map(to_json_line).coalesce(1).saveAsTextFile(str(config.ANIMALS_WIKI_DIR))       # one file for the indexer

    # statistics
    matched_count = best.count()
    unique_pages = best.map(lambda pair: pair[1][1]).distinct().count()
    types = best.map(lambda pair: pair[1][2]).countByValue()
    unmatched = joined.filter(lambda animal: animal["wiki"] is None).collect()
    shared = lookup.value["shared"]

    spark.stop()

    save_unmatched(unmatched, shared)
    print_run_summary(len(animal_list), matched_count, unique_pages, types, unmatched, shared, time.time() - start)





def show_record():
    if not config.ANIMALS_WIKI_DIR.exists():
        print("Joined data not found - run the join first")
        return

    slug = input("Animal slug (red-fox): ").strip().lower()

    for path in sorted(config.ANIMALS_WIKI_DIR.glob("part-*")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                animal = json.loads(line)
                if animal["id"] != slug:
                    continue

                wiki = animal["wiki"]
                print(f"{animal['name']} ({animal['scientific_name']})")
                if wiki is None:
                    print("\nNo wiki page joined.")
                    return

                wiki["lead"] = wiki["lead"][:300] + " ..."     # lead is long, show only the beginning
                print(json.dumps(wiki, ensure_ascii=False, indent=1))
                return

    print(f"'{slug}' not found")