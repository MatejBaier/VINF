import json
import shutil
import time

import config
from modules.wiki_extractor import ARTICLE_NAMESPACE, extract, parse_xml_page





# functions below run on executors, every executor processes its own part of the dump

def process_page(record):
    # one <page> -> (kind, value), kind is "taxon", "redirect", "article" or "other"
    page = parse_xml_page(record)
    if page is None:
        return None             # end of the file, not a page

    if page["namespace"] != ARTICLE_NAMESPACE:
        return ("other", None)          # talk pages, templates, files ...

    if page["redirect"]:
        return ("redirect", (page["title"], page["redirect"]))

    taxon = extract(page)
    if taxon:
        return ("taxon", taxon)
    return ("article", None)


def is_page(result):
    return result is not None


def is_taxon(result):
    return result[0] == "taxon"


def is_redirect(result):
    return result[0] == "redirect"


def result_kind(result):
    return result[0]


def result_value(result):
    return result[1]


def to_json_line(record):
    return json.dumps(record, ensure_ascii=False)





def read_dump(sc, path):
    # Hadoop splits the file by "</page>", so one record = one whole page, bz2 is read in parallel without unpacking
    records = sc.newAPIHadoopFile(
        str(path),
        "org.apache.hadoop.mapreduce.lib.input.TextInputFormat",
        "org.apache.hadoop.io.LongWritable",
        "org.apache.hadoop.io.Text",
        conf={"textinputformat.record.delimiter": "</page>"},
    )
    return records.map(result_value)        # (position in file, text) -> text


def save(rdd, folder):
    # saveAsTextFile fails if the output folder already exists
    if folder.exists():
        shutil.rmtree(folder)
    rdd.map(to_json_line).saveAsTextFile(str(folder))


def print_run_summary(kinds, infoboxes, taxa_count, redirect_count, seconds):
    print("\nPages in the dump")
    print(f" {'all pages:':<26}{sum(kinds.values())}")
    print(f" {'other namespaces:':<26}{kinds.get('other', 0)}")
    print(f" {'redirects:':<26}{kinds.get('redirect', 0)}")
    print(f" {'other articles:':<26}{kinds.get('article', 0)}")
    print(f" {'taxon and breed articles:':<26}{kinds.get('taxon', 0)}")

    print("\nTaxon and breed articles by infobox")
    for infobox, count in sorted(infoboxes.items(), key=lambda item: item[1], reverse=True):
        print(f" {infobox + ':':<30}{count}")

    print(f"\nSaved {taxa_count} taxa and breeds -> {config.WIKI_TAXA_DIR}")
    print(f"Saved {redirect_count} redirects to them -> {config.WIKI_REDIRECTS_DIR}")
    print(f"\nDone in {seconds / 60:.1f} min")


def run(full=False):
    if full:
        dump_file = config.WIKI_DUMP_FILE
    else:
        dump_file = config.WIKI_SAMPLE_FILE

    if not dump_file.exists():
        print(f"Dump not found: {dump_file}")
        return

    from modules.spark_utils import create_session      # pyspark is imported only when Spark is used
    from pyspark import StorageLevel

    start = time.time()
    spark = create_session("WikiExtractor")
    sc = spark.sparkContext

    pages = read_dump(sc, dump_file)
    print(f"Reading {dump_file.name}, split into {pages.getNumPartitions()} partitions")

    # the dump is read only once, small results are kept, if memory is full the rest goes to disk
    results = pages.map(process_page).filter(is_page).persist(StorageLevel.MEMORY_AND_DISK)

    kinds = results.map(result_kind).countByValue()

    taxa = results.filter(is_taxon).map(result_value)
    save(taxa, config.WIKI_TAXA_DIR)
    infoboxes = taxa.map(lambda taxon: taxon["infobox"]).countByValue()

    # only redirects pointing to a taxon page are kept, join: (target, title) x (taxon title, True)
    redirects = results.filter(is_redirect).map(result_value)
    redirects_by_target = redirects.map(lambda redirect: (redirect[1], redirect[0]))
    taxa_titles = taxa.map(lambda taxon: (taxon["title"], True))
    taxa_redirects = redirects_by_target.join(taxa_titles).map(lambda pair: {"title": pair[1][0], "target": pair[0]})
    save(taxa_redirects, config.WIKI_REDIRECTS_DIR)

    taxa_count = taxa.count()
    redirect_count = taxa_redirects.count()

    spark.stop()
    print_run_summary(kinds, infoboxes, taxa_count, redirect_count, time.time() - start)





def load_records(folder):
    records = []
    for path in sorted(folder.glob("part-*")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
    return records


def show_record():
    if not config.WIKI_TAXA_DIR.exists():
        print("Wiki output not found - process the wiki dump first")
        return

    title = input("Wiki title (Red fox): ").strip()

    taxa = load_records(config.WIKI_TAXA_DIR)
    redirects = load_records(config.WIKI_REDIRECTS_DIR)

    for taxon in taxa:
        if taxon["title"].lower() == title.lower():
            taxon["redirects"] = [redirect["title"] for redirect in redirects if redirect["target"] == taxon["title"]]
            print(json.dumps(taxon, ensure_ascii=False, indent=1))
            return

    print(f"'{title}' is not among {len(taxa)} taxa")
