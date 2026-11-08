import html
import json
import re

import config
from modules.utils import iter_raw_pages, read_raw_page




# Manually skipped pages
SKIPPED_SLUGS = {
    # old duplicates without data, full page is under another slug
    "alosaurus",            # allosaurus
    "blister-beetle",       # blister-beetles
    "liopleurodon",         # liopleurodon-2
    "sauropoda",            # sauropoda-2
    "spongy-moth",          # spongy-moth-2

    # not animals
    "venus-flytrap",        # plant
    "stromatolite",         # bacteria
}


FLAGS = re.DOTALL           # extends "." regex and now matches . and new lines

# Top of the page: name + scientific name
NAME_REGEX = re.compile(r'<h1 class="site-hero__title">(.*?)</h1>', FLAGS)
SCIENTIFIC_NAME_REGEX = re.compile(r'<p class="site-hero__scientific">(.*?)</p>', FLAGS)


# Locations:
LOCATION_REGEX = re.compile(r'<span class="enc-map__country-name[^"]*">(.*?)</span>', FLAGS)                            # countries from the map
MARINE_ZONE_REGEX = re.compile(r'<span class="enc-map__marine-zone-tag">(.*?)</span>', FLAGS)                           # sea animals have ocean regions instead of countries
WORLDWIDE_REGEX = re.compile(r'class="enc-quick-stats__type enc-quick-stats__type--cosmopolitan"')                      # animals living everywhere have no map, only "Found Worldwide" badge
DOMESTIC_SUBTITLE_REGEX = re.compile(r'<p class="enc-map__subtitle enc-map__subtitle--domestic">(.*?)</p>', FLAGS)      # domesticated animals have empty map with subtitle "Found Worldwide"



# At a Glance box
ALT_NAMES_BLOCK_REGEX = re.compile(r'<span class="enc-quick-stats__alt-names-list">(.*?)</span>', FLAGS)
STRONG_REGEX = re.compile(r"<strong>(.*?)</strong>", FLAGS)
STATUS_REGEX = re.compile(r'<span class="enc-quick-stats__label">Status</span>\s*<(?:a|span)[^>]*class="enc-quick-stats__value[^"]*"[^>]*>(.*?)</(?:a|span)>', FLAGS)



# Scientific Classification
SUMMARY_REGEX = re.compile(r'<p class="enc-classification__summary">(.*?)</p>', FLAGS)
CLASS_REGEX = re.compile(r'<dt class="enc-classification__rank-label">Class</dt>\s*<dd class="enc-classification__rank-value">(.*?)</dd>', FLAGS)
RANK_LABEL_REGEX = re.compile(r'<dt class="enc-classification__rank-label">(.*?)</dt>', FLAGS)
RANK_REGEX = re.compile(r'<dt class="enc-classification__rank-label">(.*?)</dt>\s*<dd class="enc-classification__rank-value">(.*?)</dd>', FLAGS)
FEATURES_BLOCK_REGEX = re.compile(r'<ul class="enc-classification__features-list[^"]*">(.*?)</ul>', FLAGS)
FEATURE_ITEM_REGEX = re.compile(r"<li[^>]*>.*?<span>(.*?)</span>\s*</li>", FLAGS)



# Life Cycle
LIFESPAN_WILD_REGEX = re.compile(r'<span class="enc-lifecycle__lifespan-label">In the Wild</span>.*?<span class="enc-lifecycle__lifespan-value">(.*?)</span>', FLAGS)
LIFESPAN_CAPTIVITY_REGEX = re.compile(r'<span class="enc-lifecycle__lifespan-label">In Captivity</span>.*?<span class="enc-lifecycle__lifespan-value">(.*?)</span>', FLAGS)



# Behavior & Ecology, communication ends where next section starts
COMMUNICATION_BLOCK_REGEX = re.compile(r'data-section="communication">(.*?)(?=data-section="|<!-- Habitat Section)', FLAGS)
NOTE_REGEX = re.compile(r'<div class="enc-fieldnotes__note[^"]*"[^>]*>(.*?)</div>', FLAGS)
NOTE_NAME_REGEX = re.compile(r'<span class="enc-fieldnotes__note-name">(.*?)</span>', FLAGS)
NOTE_DESC_REGEX = re.compile(r'<span class="enc-fieldnotes__note-desc">(.*?)</span>', FLAGS)

SOCIAL_REGEX = re.compile(r'<span class="enc-fieldnotes__fact-label">Social</span>\s*<span class="enc-fieldnotes__fact-value">(.*?)</span>', FLAGS)
GROUP_SIZE_REGEX = re.compile(r'<span class="enc-fieldnotes__fact-label">Social</span>.*?<span class="enc-fieldnotes__fact-sub">\s*Group:\s*(\d+)', FLAGS)
ACTIVITY_REGEX = re.compile(r'<span class="enc-fieldnotes__fact-label">Activity</span>\s*<span class="enc-fieldnotes__fact-value">(.*?)</span>', FLAGS)
DIET_REGEX = re.compile(r'<span class="enc-fieldnotes__fact-label">Diet</span>\s*<span class="enc-fieldnotes__fact-value">(.*?)</span>', FLAGS)



# Human Interaction
DOMESTICATION_REGEX = re.compile(r'<span class="enc-human-interaction__status-badge[^"]*">(.*?)</span>', FLAGS)
DANGER_REGEX = re.compile(r'<span class="enc-human-interaction__danger-badge[^"]*">(.*?)</span>', FLAGS)
PET_REGEX = re.compile(r'<span class="enc-human-interaction__pet-badge[^"]*"[^>]*>(.*?)</span>', FLAGS)



# Did You Know? box
FACT_CARD_REGEX = re.compile(r'<p class="enc-facts__card-text[^"]*">(.*?)</p>', FLAGS)
ADAPTATIONS_BLOCK_REGEX = re.compile(r'Unique Adaptations\s*</h3>\s*<ul class="enc-facts__list[^"]*">(.*?)</ul>', FLAGS)
BEHAVIORS_BLOCK_REGEX = re.compile(r'Interesting Behaviors\s*</h3>\s*<ul class="enc-facts__list[^"]*">(.*?)</ul>', FLAGS)
CULTURAL_REGEX = re.compile(r'<p class="enc-facts__cultural-text[^"]*">(.*?)</p>', FLAGS)
MYTH_REGEX = re.compile(r'<blockquote class="enc-facts__myth[^"]*">(.*?)</blockquote>', FLAGS)



# article text
ARTICLE_REGEX = re.compile(r'<div class="article-body" itemprop="articleBody">(.*?)(?:<div class="fwpPitch|<!-- /\.article-body|</article>)', FLAGS)
SCRIPT_STYLE_REGEX = re.compile(r"<(script|style)[^>]*>.*?</\1>", FLAGS)

# images are in <figure>, but tables too (<figure class="wp-block-table">), keep tables
IMAGE_FIGURE_REGEX = re.compile(r"<figure\b(?![^>]*wp-block-table)[^>]*>.*?</figure>", FLAGS)

# empty headings, <h2 id="h-"></h2> or <h2><br/><br/></h2> (corn snake, papillon)
EMPTY_H2_REGEX = re.compile(r"<h2[^>]*>(?:\s|<br\s*/?>|&nbsp;)*</h2>", FLAGS)
H2_REGEX = re.compile(r"<h2[^>]*>(.*?)</h2>", FLAGS)

# paragraphs, list items and table cells, \b so <path>, <picture>, <thead> do not match
TEXT_UNIT_REGEX = re.compile(r"<(?:p|li|td|th)\b[^>]*>(.*?)</(?:p|li|td|th)>", FLAGS)

SKIPPED_SECTIONS = {"Quick Take"}       # short summary box, repeats the article





def clean(text):
    if text is None:
        return None

    text = re.compile(r"<[^>]+>").sub(" ", text)    # remove HTML tags, replace by " "
    text = html.unescape(text)                      # code text -> text (&amp; -> &)
    text = re.compile(r"\s+").sub(" ", text)        # multiple spaces and new lines -> one space
    return text.strip()


def find_first(regex, text):
    match = regex.search(text)          # returns regex match
    if match:
        return clean(match.group(1))    # return cleaned group
    else:
        return None


def find_all(regex, text):
    found = []
    for item in regex.findall(text):
        found.append(clean(item))
    return found                        # return a list of cleaned groups


def find_in_block(block_regex, item_regex, page):
    block = block_regex.search(page)                # find the block
    if not block:
        return []
    return find_all(item_regex, block.group(1))     # go over all items inside the block and return cleaned items





def page_template(page):
    match = re.compile(r'<body class="([^"]*)"').search(page)
    if match:
        return match.group(1)       # returns class attribute from body
    return ""


def is_animal_page(page):
    classes = page_template(page).split()
    return "post-template-single-animals" in classes    # is animal if contains this is body class


def template_name(page):
    # the most specific class of page, (page-template-page-class-hub)
    classes = page_template(page).split()
    for name in classes:
        if "-template-" in name:
            return name

    if classes:
        return classes[0]       # If class does not contain -template-, return first class
    return "-"





def extract_scientific_name(page):
    name = find_first(SCIENTIFIC_NAME_REGEX, page)
    if name:
        return name

    # some pages do not have it at the top (eagle), take the lowest rank from classification
    ranks = RANK_REGEX.findall(page)
    if not ranks:
        return None

    lowest_rank_value = ranks[-1][1]
    return clean(lowest_rank_value)


def extract_taxon_level(page):
    # lowest rank: Species = one animal, Genus / Family = group of animals (gorilla, carp)
    ranks = find_all(RANK_LABEL_REGEX, page)
    if not ranks:
        return None
    return ranks[-1]


def extract_locations(page):
    locations = find_all(LOCATION_REGEX, page)

    for zone in find_all(MARINE_ZONE_REGEX, page):
        zone = zone.replace("_", " ").title()       # north_atlantic -> North Atlantic
        locations.append(zone)

    if locations:
        return locations

    # no map, only the worldwide badge
    if WORLDWIDE_REGEX.search(page):
        return ["Worldwide"]

    # domesticated animal, empty map with subtitle
    domestic = find_first(DOMESTIC_SUBTITLE_REGEX, page)
    if domestic:
        domestic = re.sub(r"^Found\s+", "", domestic)       # Found Worldwide -> Worldwide
        return [domestic]

    return []


def extract_communication(page):
    block = COMMUNICATION_BLOCK_REGEX.search(page)
    if not block:
        return []

    notes = []
    for note in NOTE_REGEX.findall(block.group(1)):
        name = find_first(NOTE_NAME_REGEX, note)
        desc = find_first(NOTE_DESC_REGEX, note)

        if name and desc:
            notes.append(f"{name}: {desc}")     # Grunts: Contact/foraging, reassurance
        else:
            notes.append(clean(note))           # note is only plain text
    return notes


def extract_group_size(page):
    match = GROUP_SIZE_REGEX.search(page)
    if match:
        return int(match.group(1))
    return None


def section_text(html_part):
    texts = []
    for text in find_all(TEXT_UNIT_REGEX, html_part):
        if text:
            texts.append(text)
    return " ".join(texts)


def extract_article(page):
    match = ARTICLE_REGEX.search(page)
    if not match:
        return []

    body = match.group(1)
    body = SCRIPT_STYLE_REGEX.sub(" ", body)
    body = IMAGE_FIGURE_REGEX.sub(" ", body)
    body = EMPTY_H2_REGEX.sub(" ", body)        # text after empty heading stays in previous section

    # parts = [intro, heading 1, content 1, heading 2, content 2, ...]
    parts = H2_REGEX.split(body)

    sections = []

    intro = section_text(parts[0])
    if intro:
        sections.append({"heading": None, "text": intro})

    for i in range(1, len(parts) - 1, 2):
        heading = clean(parts[i])
        if heading in SKIPPED_SECTIONS:
            continue

        text = section_text(parts[i + 1])
        sections.append({"heading": heading, "text": text})

    return sections





def extract(slug, page):
    # one HTML page -> one record, missing fields are None or []
    return {
        "id": slug,
        "name": find_first(NAME_REGEX, page),
        "scientific_name": extract_scientific_name(page),
        "locations": extract_locations(page),
        "also_known_as": find_in_block(ALT_NAMES_BLOCK_REGEX, STRONG_REGEX, page),
        "summary": find_first(SUMMARY_REGEX, page),
        "class": find_first(CLASS_REGEX, page),
        "taxon_level": extract_taxon_level(page),
        "distinguishing_features": find_in_block(FEATURES_BLOCK_REGEX, FEATURE_ITEM_REGEX, page),
        "status": find_first(STATUS_REGEX, page),
        "lifespan_wild": find_first(LIFESPAN_WILD_REGEX, page),
        "lifespan_captivity": find_first(LIFESPAN_CAPTIVITY_REGEX, page),
        "communication": extract_communication(page),
        "social": find_first(SOCIAL_REGEX, page),
        "group_size": extract_group_size(page),
        "activity": find_first(ACTIVITY_REGEX, page),
        "diet": find_first(DIET_REGEX, page),
        "domestication": find_first(DOMESTICATION_REGEX, page),
        "danger_level": find_first(DANGER_REGEX, page),
        "as_pet": find_first(PET_REGEX, page),
        "did_you_know": find_all(FACT_CARD_REGEX, page),
        "adaptations": find_in_block(ADAPTATIONS_BLOCK_REGEX, FEATURE_ITEM_REGEX, page),     # list items look the same as in features
        "behaviors": find_in_block(BEHAVIORS_BLOCK_REGEX, FEATURE_ITEM_REGEX, page),
        "cultural_significance": find_first(CULTURAL_REGEX, page),
        "myths_legends": find_all(MYTH_REGEX, page),
        "article": extract_article(page),
    }


def is_missing(value):
    return value is None or value == []





def save_skipped(skipped):
    with open(config.SKIPPED_FILE, "w", encoding="utf-8") as f:
        f.write("slug\ttemplate\turl\n")
        for slug, template in skipped:
            f.write(f"{slug}\t{template}\t{config.BASE_URL}/animals/{slug}/\n")


def print_run_summary(count, skipped, missing):
    print(f"\nParsed {count} pages -> {config.EXTRACTED_FILE}")

    print(f"Skipped {len(skipped)} pages that are not animal profiles -> {config.SKIPPED_FILE}")
    for slug, template in skipped[:20]:
        print(f" {slug:<45}{template}")
    if len(skipped) > 20:
        print(f" ... and {len(skipped) - 20} more")

    print("\nMissing fields (pages)")
    if not missing:
        print(" none")

    # field with the most missing pages first
    for field, pages in sorted(missing.items(), key=lambda item: item[1], reverse=True):
        print(f" {field + ':':<26}{pages}")


def run():
    if not config.RAW_ZIP.exists():
        print("ZIP with pages not found - run the crawler first")
        return

    missing = {}        # field -> number of pages without it
    skipped = []        # (slug, reason)
    count = 0

    tmp = config.EXTRACTED_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for slug, page in iter_raw_pages():

            if slug in SKIPPED_SLUGS:
                skipped.append((slug, "manually skipped"))
                continue

            if not is_animal_page(page):
                skipped.append((slug, template_name(page)))
                continue

            record = extract(slug, page)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            for field, value in record.items():
                if is_missing(value):
                    missing[field] = missing.get(field, 0) + 1

            count += 1
            if count % 250 == 0:
                print(f" {count} pages parsed")

    tmp.replace(config.EXTRACTED_FILE)     # old output is replaced only after the whole run

    save_skipped(skipped)
    print_run_summary(count, skipped, missing)





def load_missing():
    # field -> list of slugs, where the field is missing
    missing = {}

    with open(config.EXTRACTED_FILE, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            for field, value in record.items():
                if is_missing(value):
                    if field not in missing:
                        missing[field] = []
                    missing[field].append(record["id"])

    return missing


def save_missing(missing):
    with open(config.MISSING_FILE, "w", encoding="utf-8") as f:
        f.write("field\tslug\turl\n")
        for field, slugs in missing.items():
            for slug in slugs:
                f.write(f"{field}\t{slug}\t{config.BASE_URL}/animals/{slug}/\n")


def print_pages_missing_most(missing):
    # pages without many fields at once, probably different page layout
    per_page = {}
    for slugs in missing.values():
        for slug in slugs:
            per_page[slug] = per_page.get(slug, 0) + 1

    print("\nPages with the most missing fields")
    for slug, count in sorted(per_page.items(), key=lambda item: item[1], reverse=True)[:50]:
        print(f" {count:>2}  {slug:<40}{config.BASE_URL}/animals/{slug}/")


def show_missing():
    if not config.EXTRACTED_FILE.exists():
        print("extracted.jsonl not found - run the extractor first")
        return

    missing = load_missing()
    if not missing:
        print("No missing fields.")
        return

    save_missing(missing)
    print(f"All missing fields saved -> {config.MISSING_FILE}\n")

    # field with the most missing pages first
    fields = sorted(missing, key=lambda field: len(missing[field]), reverse=True)
    for number, field in enumerate(fields, 1):
        print(f" {number:>2}) {field + ':':<26}{len(missing[field])}")

    choice = input("\nField number to list (Enter = pages missing most fields): ").strip()

    if choice == "":
        print_pages_missing_most(missing)
        return

    if not choice.isdigit() or not 1 <= int(choice) <= len(fields):
        print("Invalid choice.")
        return

    field = fields[int(choice) - 1]
    print(f"\nPages without '{field}' ({len(missing[field])})")
    for slug in missing[field]:
        print(f" {slug:<40}{config.BASE_URL}/animals/{slug}/")


def show_record():
    slug = input("Animal slug (gorilla): ").strip().lower()

    try:
        page = read_raw_page(slug)
    except KeyError:
        print(f"'{slug}.html' is not in the ZIP")
        return

    if slug in SKIPPED_SLUGS:
        print("! manually skipped page (SKIPPED_SLUGS), skipped by the extractor\n")
    elif not is_animal_page(page):
        print(f"! not an animal profile ({template_name(page)}), skipped by the extractor\n")

    record = extract(slug, page)
    article = record.pop("article")     # article is long, show only its sections
    print(json.dumps(record, ensure_ascii=False, indent=1))

    print("\nArticle sections")
    for section in article:
        heading = section["heading"]
        if heading is None:
            heading = "(intro)"
        print(f" {heading} - {len(section['text'])} chars")