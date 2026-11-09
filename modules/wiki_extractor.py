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



# Infobox with taxonomy, "taxobox colour" and similar templates do not match
INFOBOX_REGEX = re.compile(r"\{\{\s*(Speciesbox|Subspeciesbox|Infraspeciesbox|Automatic taxobox|Taxobox)\s*(?=\||\n|\}\})", re.IGNORECASE)
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
            return start.group(1).capitalize(), body, brace.end()

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


def scientific_name(infobox_type, params, title):
    if params.get("taxon"):
        return params["taxon"]

    if infobox_type == "Speciesbox":
        return join_names(params.get("genus"), params.get("species"))

    if infobox_type == "Subspeciesbox":
        return join_names(params.get("genus"), params.get("species"), params.get("subspecies"))

    if infobox_type == "Infraspeciesbox":
        return join_names(params.get("genus"), params.get("species"), params.get("variety") or params.get("infraspecies"))

    if infobox_type == "Automatic taxobox":
        return TITLE_BRACKETS_REGEX.sub("", title)       # without taxon parameter the page title is the taxon

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





def extract(page):
    # one article with taxonomy infobox -> one record, None if it is not a taxon page
    infobox = find_infobox(page["text"])
    if not infobox:
        return None

    infobox_type, body, end = infobox
    params = parse_params(body)
    authority_text = authority(params)

    return {
        "page_id": page["page_id"],
        "title": page["title"],
        "name": params.get("name") or page["title"],
        "infobox": infobox_type,
        "scientific_name": scientific_name(infobox_type, params, page["title"]),
        "authority": authority_text,
        "authority_year": authority_year(authority_text),
        "status": params.get("status"),
        "status_system": params.get("status_system"),
        "categories": [category.strip() for category in CATEGORY_REGEX.findall(page["text"])],
        "lead": lead_text(page["text"], end),
    }
