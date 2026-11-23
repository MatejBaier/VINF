import html
import re




FLAGS = re.DOTALL           # extends "." regex and now matches . and new lines

# One page from the dump XML
TITLE_REGEX = re.compile(r"<title>(.*?)</title>", FLAGS)
NAMESPACE_REGEX = re.compile(r"<ns>(\d+)</ns>")
PAGE_ID_REGEX = re.compile(r"<id>(\d+)</id>")                              # first <id> is page id, next one is revision id
REDIRECT_REGEX = re.compile(r'<redirect title="(.*?)"\s*/>')
TEXT_REGEX = re.compile(r"<text\b[^>]*>(.*?)</text>", FLAGS)

ARTICLE_NAMESPACE = 0       # namespace of normal articles, others are talk pages, templates, files ...
TEMPLATE_NAMESPACE = 10
TAXONOMY_PREFIX = "Template:Taxonomy/"      # Template:Taxonomy/Vulpes has the rank and the parent taxon of Vulpes



# Taxonomy template, {{Don't edit this line {{{machine code|}}} |rank=genus |parent=Canini |link=Vulpes}}
# "Mammalia/skip" has |same as=Mammalia, it takes the rank of Mammalia, but skips some levels to its parent
TAXONOMY_PARAM_REGEX = re.compile(r"\|\s*(rank|parent|extinct|same[ _]as)\s*=\s*([^|}\n]*)")



# Infobox with taxonomy or breed (Infobox dog breed, Infobox cattle breed ...), "taxobox colour" and similar templates do not match
# space and _ are the same in template names, {{Automatic_taxobox}} = {{Automatic taxobox}}
INFOBOX_REGEX = re.compile(
    r"\{\{\s*(Speciesbox|Subspeciesbox|Infraspeciesbox|Automatic[ _]taxobox|Taxobox|Population[ _]taxobox|Paraphyletic[ _]group|Hybridbox"
    r"|Infobox[ _][a-z]+(?:[ _][a-z]+)?[ _]breed)\s*(?=\||\n|\}\})",
    re.IGNORECASE,
)
BRACES_REGEX = re.compile(r"\{\{|\}\}")                                     # used to find the end of the infobox
INNER_TEMPLATE_REGEX = re.compile(r"\{\{[^{}]*\}\}")                        # template without other templates inside
CONVERT_REGEX = re.compile(r"\{\{\s*(?:[Cc]onvert|[Cc]vt)\s*\|\s*([\d.,]+)\s*\|\s*(?:(to|and|-|–)\s*\|\s*([\d.,]+)\s*\|\s*)?([^|{}]+)[^{}]*\}\}")     # {{convert|46|to|68|cm}}
PARAM_REGEX = re.compile(r"\|\s*([A-Za-z_0-9 ]+?)\s*=\s*([^|]*)")         # | genus = Vulpes



# Wikitext cleaning
COMMENT_REGEX = re.compile(r"<!--.*?-->", FLAGS)
REF_REGEX = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", FLAGS | re.IGNORECASE)
TABLE_REGEX = re.compile(r"\{\|.*?\|\}", FLAGS)
LINK_REGEX = re.compile(r"\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]")            # [[target]] or [[target|label]], innermost links first
EXTERNAL_LINK_REGEX = re.compile(r"\[https?://[^\s\]]*\s*([^\]]*)\]")       # [http://url label] -> label
QUOTES_REGEX = re.compile(r"'{2,}")                                         # ''italic'' and '''bold'''
TAG_REGEX = re.compile(r"<[^>]+>")
EMPTY_BRACKETS_REGEX = re.compile(r"\(\s*[;,]?\s*\)")                       # ( ; ) left after removed pronunciation
BRACKET_START_REGEX = re.compile(r"\(\s*[;,]\s*")                           # "( ; Vulpes vulpes)" -> "(Vulpes vulpes)"
SPACE_BEFORE_PUNCT_REGEX = re.compile(r"\s+([,.;:)])")
SPACES_REGEX = re.compile(r"\s+")

SKIPPED_LINK_PREFIXES = ("file:", "image:", "category:")      # these links are not part of the text



# Article parts
CATEGORY_REGEX = re.compile(r"\[\[\s*Category\s*:\s*([^\]|]+)", re.IGNORECASE)
FIRST_HEADING_REGEX = re.compile(r"\n==")                                   # lead section ends with the first heading
YEAR_REGEX = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")                         # year from authority (Linnaeus, 1758)
TITLE_BRACKETS_REGEX = re.compile(r"\s*\([^)]*\)$")                         # Jaguar (animal) -> Jaguar
LOCATION_CATEGORY_REGEX = re.compile(r"^(.+?) of (?:the )?([A-Z].*)$")     # "Mammals of Europe" -> Europe, "Birds of prey" does not match
NAMES_SPLIT_REGEX = re.compile(r"\s*(?:,|;|\bor\b)\s*")                     # altname "Beagle-Harrier, English Beagle"

# categories "... of <place>" which do not say where the animal lives
NOT_LOCATION_CATEGORIES = ("Natural history", "Symbols", "National symbols", "State symbols", "Lists", "List")



# Taxonomy
# infobox -> rank of the taxon, Automatic taxobox gets it from its taxonomy template, old Taxobox from its lowest filled rank
INFOBOX_RANKS = {
    "Speciesbox": "species",
    "Subspeciesbox": "subspecies",
    "Infraspeciesbox": "variety",
    "Population taxobox": "population",
    "Hybridbox": "hybrid",
    "Paraphyletic group": "group",
}
TAXOBOX_RANKS = [
    ("trinomial", "subspecies"),
    ("binomial", "species"),
    ("genus", "genus"),
    ("familia", "familia"),
    ("ordo", "ordo"),
    ("classis", "classis"),
    ("phylum", "phylum"),
]

# ranks of the lineage which are kept in the record, the other ranks (clade, tribus ...) are skipped
LINEAGE_FIELDS = {"regnum": "kingdom", "phylum": "phylum", "classis": "class", "ordo": "order", "familia": "family"}

ANIMAL_KINGDOM = "Animalia"
MAX_LINEAGE = 100           # protection against a cycle of parents in broken templates

# breed infobox -> class, breeds have no taxonomy templates, all of them are animals
BREED_KIND_REGEX = re.compile(r"^Infobox (.+) breed$")         # "Infobox dog breed" -> "dog"
BREED_CLASSES = {
    "dog": "Mammalia",
    "cat": "Mammalia",
    "horse": "Mammalia",
    "cattle": "Mammalia",
    "cow": "Mammalia",
    "water buffalo": "Mammalia",
    "sheep": "Mammalia",
    "goat": "Mammalia",
    "pig": "Mammalia",
    "poultry": "Aves",
    "pigeon": "Aves",
    "goldfish": "Actinopterygii",
}





def replace_convert(match):
    # {{convert|46|to|68|cm}} -> 46 to 68 cm
    value, separator, value_to, unit = match.groups()
    if value_to:
        return f"{value} {separator} {value_to} {unit.strip()}"
    return f"{value} {unit.strip()}"


def remove_templates(text):
    # removes templates from the inside out, {{a|{{b}}}} -> {{a|}} -> "", only units from {{convert}} are kept
    text = CONVERT_REGEX.sub(replace_convert, text)
    while True:
        new_text = INNER_TEMPLATE_REGEX.sub("", text)
        if new_text == text:
            return text
        text = new_text


def replace_link(match):
    target = match.group(1).strip()
    label = match.group(2)

    if target.lower().startswith(SKIPPED_LINK_PREFIXES):
        return ""
    if label is None:
        return target           # [[fox]] -> fox
    return label                # [[Red fox|foxes]] -> foxes


def replace_links(text):
    # nested links ([[File:x.jpg|A [[fox]] in snow]]) are replaced from the inside out
    while True:
        new_text = LINK_REGEX.sub(replace_link, text)
        if new_text == text:
            return text
        text = new_text


def clean(text):
    # wikitext -> plain text
    if text is None:
        return None

    text = COMMENT_REGEX.sub("", text)
    text = REF_REGEX.sub("", text)
    text = remove_templates(text)
    text = TABLE_REGEX.sub("", text)
    text = replace_links(text)
    text = EXTERNAL_LINK_REGEX.sub(r"\1", text)
    text = QUOTES_REGEX.sub("", text)
    text = TAG_REGEX.sub(" ", text)
    text = html.unescape(text)                  # &nbsp; inside the wikitext
    text = SPACES_REGEX.sub(" ", text)
    text = EMPTY_BRACKETS_REGEX.sub("", text)
    text = BRACKET_START_REGEX.sub("(", text)
    text = SPACE_BEFORE_PUNCT_REGEX.sub(r"\1", text)
    return text.strip()





def parse_xml_page(record):
    # one <page> from the dump -> dict with title, namespace, id, redirect and wikitext
    title = TITLE_REGEX.search(record)
    if not title:
        return None         # end of the file (</mediawiki>), no page

    namespace = NAMESPACE_REGEX.search(record)
    page_id = PAGE_ID_REGEX.search(record)
    redirect = REDIRECT_REGEX.search(record)
    text = TEXT_REGEX.search(record)

    page = {
        "title": html.unescape(title.group(1)),
        "namespace": int(namespace.group(1)) if namespace else None,
        "page_id": int(page_id.group(1)) if page_id else None,
        "redirect": None,
        "text": "",
    }

    if redirect:
        target = html.unescape(redirect.group(1))
        page["redirect"] = target.split("#")[0].strip()        # Red fox#Diet -> Red fox
    if text:
        page["text"] = html.unescape(text.group(1))             # text in XML is escaped (&lt;ref&gt;)
    return page


def find_infobox(text):
    # returns (infobox type, infobox text without the outer braces, end position) or None
    start = INFOBOX_REGEX.search(text)
    if not start:
        return None

    # end of infobox is where the number of {{ and }} is the same
    depth = 0
    for brace in BRACES_REGEX.finditer(text, start.start()):
        if brace.group() == "{{":
            depth += 1
        else:
            depth -= 1

        if depth == 0:
            body = text[start.end():brace.start()]
            infobox_type = start.group(1).replace("_", " ").capitalize()
            return infobox_type, body, brace.end()

    return None             # infobox is not closed, broken page


def parse_params(body):
    # infobox text -> {param: value}, nested templates and links are removed first, so their | do not split values
    body = COMMENT_REGEX.sub("", body)
    body = REF_REGEX.sub("", body)
    body = remove_templates(body)
    body = replace_links(body)

    params = {}
    for name, value in PARAM_REGEX.findall(body):
        value = clean(value)
        if value:
            params[name.strip().lower()] = value
    return params


def join_names(*parts):
    # genus + species (+ subspecies), None if any part is missing
    for part in parts:
        if not part:
            return None
    return " ".join(parts)


def is_breed(infobox_type):
    return infobox_type.endswith("breed")


def scientific_name(infobox_type, params, title):
    if is_breed(infobox_type):
        return None             # breeds have no own scientific name

    if params.get("taxon"):
        return params["taxon"]

    genus = params.get("genus")
    if genus:
        genus = TITLE_BRACKETS_REGEX.sub("", genus)         # genus = Vandellia (fish) -> Vandellia

    if infobox_type == "Speciesbox":
        return join_names(genus, params.get("species"))

    if infobox_type in ("Subspeciesbox", "Population taxobox"):
        return join_names(genus, params.get("species"), params.get("subspecies"))

    if infobox_type == "Infraspeciesbox":
        return join_names(genus, params.get("species"), params.get("variety") or params.get("infraspecies"))

    if infobox_type == "Automatic taxobox":
        return TITLE_BRACKETS_REGEX.sub("", title)       # without taxon parameter the page title is the taxon

    if infobox_type in ("Paraphyletic group", "Hybridbox"):
        return None             # group of more taxa (squid) or hybrid (mule), joined by name

    # old Taxobox, the lowest rank which is filled
    for field in ("trinomial", "binomial", "genus", "familia", "ordo", "classis"):
        if params.get(field):
            return params[field]
    return None


def authority(params):
    for field in ("authority", "trinomial_authority", "binomial_authority", "genus_authority"):
        if params.get(field):
            return params[field]
    return None


def authority_year(text):
    if not text:
        return None
    match = YEAR_REGEX.search(text)
    if match:
        return int(match.group(1))
    return None


def lead_text(text, start):
    # text from the end of the infobox to the first heading
    end = FIRST_HEADING_REGEX.search(text, start)
    if end:
        lead = text[start:end.start()]
    else:
        lead = text[start:]
    return clean(lead)


def taxon_rank(infobox_type, params):
    # species, genus ... None for Automatic taxobox, its rank is in its taxonomy template
    if is_breed(infobox_type):
        return "breed"
    if infobox_type in INFOBOX_RANKS:
        return INFOBOX_RANKS[infobox_type]

    if infobox_type == "Taxobox":
        for field, rank in TAXOBOX_RANKS:
            if params.get(field):
                return rank
    return None


def taxonomy_names(infobox_type, params, title):
    # names of taxonomy templates where the lineage starts, the first existing one is used later (Vulpes lagopus -> Vulpes)
    if is_breed(infobox_type):
        return []

    taxon = params.get("taxon")
    if infobox_type == "Automatic taxobox":
        names = [taxon, title, TITLE_BRACKETS_REGEX.sub("", title)]
    elif infobox_type == "Taxobox":
        names = [params.get(field) for field in ("genus", "familia", "ordo", "classis", "phylum")]
    else:
        names = [params.get("parent"), params.get("genus")]
        if taxon:
            names.append(taxon.split()[0])      # genus from "Vulpes lagopus"

    result = []
    for name in names:
        name = page_name(name)
        if name and name not in result:
            result.append(name)
    return result


def taxobox_lineage(infobox_type, params):
    # old Taxobox has the whole lineage in its parameters (regnum = Animalia, classis = Mammalia ...)
    if infobox_type != "Taxobox":
        return {}

    result = {}
    for rank, field in LINEAGE_FIELDS.items():
        if params.get(rank):
            result[field] = params[rank]
    return result


def other_names(params, title):
    # name in the infobox (Dolphins) and alternative names of breeds (altname = English Beagle)
    names = []
    for value in (params.get("name"), params.get("altname")):
        if not value:
            continue
        for name in NAMES_SPLIT_REGEX.split(value):
            name = name.strip()
            if name and name.lower() != title.lower() and name not in names:
                names.append(name)
    return names


def is_extinct(params):
    # extinct = yes, or the year of extinction (Aurochs: extinct = 1627)
    value = params.get("extinct")
    return value is not None and value.lower() not in ("no", "false")


def category_locations(categories):
    # "Mammals of Europe", "Endemic fauna of the Canary Islands" -> Europe, Canary Islands
    locations = []
    for category in categories:
        match = LOCATION_CATEGORY_REGEX.match(category)
        if not match or match.group(1).startswith(NOT_LOCATION_CATEGORIES):
            continue

        location = match.group(2).strip()
        if location not in locations:
            locations.append(location)
    return locations





def extract(page):
    # one article with taxonomy or breed infobox -> one record, None if it is not a taxon or breed page
    infobox = find_infobox(page["text"])
    if not infobox:
        return None

    infobox_type, body, end = infobox
    params = parse_params(body)
    authority_text = authority(params)
    categories = [category.strip() for category in CATEGORY_REGEX.findall(page["text"])]

    return {
        "page_id": page["page_id"],
        "title": page["title"],
        "name": params.get("name") or page["title"],
        "infobox": infobox_type,
        "scientific_name": scientific_name(infobox_type, params, page["title"]),
        "rank": taxon_rank(infobox_type, params),
        "authority": authority_text,
        "authority_year": authority_year(authority_text),
        "status": params.get("status"),
        "status_system": params.get("status_system"),
        "extinct": is_extinct(params),
        "origin": params.get("country") or params.get("origin"),         # country of origin, only breeds have it
        "lifespan": params.get("life_span") or params.get("lifespan"),   # only breeds have it (12–15 years)
        "other_names": other_names(params, page["title"]),
        "categories": categories,
        "locations": category_locations(categories),
        "lead": lead_text(page["text"], end),
        "taxonomy": taxonomy_names(infobox_type, params, page["title"]),     # where the lineage starts, removed after it is found
        "lineage": taxobox_lineage(infobox_type, params),
    }





def page_name(name):
    # the same page name as on Wikipedia, space and _ are the same, "RTA_clade" -> "RTA clade", "{{Taxonomy/Gruiformes" -> "Gruiformes"
    if not name:
        return None
    name = name.replace("{{Taxonomy/", "").split("#")[0]
    return SPACES_REGEX.sub(" ", name.replace("_", " ")).strip() or None


def extract_taxonomy(page):
    # Template:Taxonomy/Vulpes -> {"name": "Vulpes", "rank": "genus", "parent": "Canini"}, redirect template -> parent is its target
    name = page["title"][len(TAXONOMY_PREFIX):]
    if page["redirect"]:
        return {"name": name, "rank": None, "parent": page_name(page["redirect"][len(TAXONOMY_PREFIX):]), "same_as": None, "extinct": False}

    params = {}
    for param, value in TAXONOMY_PARAM_REGEX.findall(COMMENT_REGEX.sub("", page["text"])):
        params.setdefault(param.replace(" ", "_"), value.strip())      # the first value counts, refs can have their own parameters

    return {
        "name": name,
        "rank": params.get("rank") or None,
        "parent": page_name(params.get("parent")),
        "same_as": page_name(params.get("same_as")),
        "extinct": params.get("extinct", "").lower() in ("yes", "true"),
    }


def is_taxonomy_page(page):
    return page["namespace"] == TEMPLATE_NAMESPACE and page["title"].startswith(TAXONOMY_PREFIX)


def templates_by_name(templates):
    # list of taxonomy templates -> {name: template}, "Mammalia/skip" gets the rank of Mammalia (same_as)
    lookup = {}
    for template in templates:
        lookup[template["name"]] = template

    for template in lookup.values():
        same = lookup.get(template["same_as"])
        if same:
            template["rank"] = template["rank"] or same["rank"]
            template["parent"] = template["parent"] or same["parent"]
    return lookup


def taxon_name(template_name):
    # name of the taxon without the parts of the template name, "Mammalia/skip" -> Mammalia, "Morus (bird)" -> Morus
    return TITLE_BRACKETS_REGEX.sub("", template_name.split("/")[0]).strip()


def lineage(names, templates):
    # [(name, rank), ...] from the first known template up to the root, Vulpes -> Canini -> Canidae -> ... -> Animalia
    current = None
    for name in names:
        if name in templates:
            current = name
            break

    result = []
    seen = set()
    while current in templates and current not in seen and len(result) < MAX_LINEAGE:
        seen.add(current)
        template = templates[current]
        if template["rank"]:
            result.append((current, template["rank"]))      # redirect templates have no rank, only their target is kept
        current = template["parent"]
    return result


def add_lineage(taxon, templates):
    # kingdom, phylum, class, order and family of the taxon from taxonomy templates (Arctic fox -> Animalia, Mammalia ...)
    for field in LINEAGE_FIELDS.values():
        taxon[field] = None

    chain = lineage(taxon["taxonomy"], templates)
    for name, rank in chain:
        field = LINEAGE_FIELDS.get(rank)
        if field and taxon[field] is None:
            taxon[field] = taxon_name(name)

    # the first template of Automatic taxobox is the taxon itself, its rank is there
    if taxon["rank"] is None and taxon["infobox"] == "Automatic taxobox" and chain:
        taxon["rank"] = chain[0][1]

    # old Taxobox and breeds have no templates, their lineage is in the infobox
    for field, value in taxon["lineage"].items():
        if taxon[field] is None:
            taxon[field] = value

    kind = BREED_KIND_REGEX.match(taxon["infobox"])
    if kind:
        taxon["kingdom"] = ANIMAL_KINGDOM
        taxon["class"] = BREED_CLASSES.get(kind.group(1).lower())

    del taxon["taxonomy"]
    del taxon["lineage"]
    return taxon


def is_animal(taxon):
    return taxon["kingdom"] == ANIMAL_KINGDOM
