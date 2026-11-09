import json
import shutil
import time

import config
from modules.extractor import SKIPPED_SLUGS, extract, is_animal_page, is_missing, save_skipped, template_name
from modules.utils import iter_raw_pages





def convert_zip_to_jsonl():
    # Spark can not read pages from ZIP, every page is saved as one line {"slug": ..., "html": ...}
    print(f"Converting {config.RAW_ZIP.name} -> {config.RAW_PAGES_FILE.name}")
    count = 0

    tmp = config.RAW_PAGES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for slug, page in iter_raw_pages():
            f.write(json.dumps({"slug": slug, "html": page}, ensure_ascii=False) + "\n")
            count += 1

    tmp.replace(config.RAW_PAGES_FILE)
    print(f" {count} pages converted\n")





# functions below run on executors, every executor processes its own part of the pages

def process_page(line):
    # one JSON line -> ("animal", record) or ("skipped", (slug, reason))
    page = json.loads(line)
    slug = page["slug"]
    html = page["html"]

    if slug in SKIPPED_SLUGS:
        return ("skipped", (slug, "manually skipped"))

    if not is_animal_page(html):
        return ("skipped", (slug, template_name(html)))

    return ("animal", extract(slug, html))      # same extractor as in part 1


def is_animal(result):
    return result[0] == "animal"


def is_skipped(result):
    return result[0] == "skipped"


def result_value(result):
    return result[1]


def missing_fields(record):
    # names of fields, which are missing in one record
    fields = []
    for field, value in record.items():
        if is_missing(value):
            fields.append(field)
    return fields


def to_json_line(record):
    return json.dumps(record, ensure_ascii=False)





def print_run_summary(count, skipped, missing, seconds):
    print(f"\nParsed {count} pages -> {config.SPARK_ANIMALS_DIR}")
    print(f"Skipped {len(skipped)} pages that are not animal profiles -> {config.SKIPPED_FILE}")

    print("\nMissing fields (pages)")
    if not missing:
        print(" none")

    # field with the most missing pages first
    for field, pages in sorted(missing.items(), key=lambda item: item[1], reverse=True):
        print(f" {field + ':':<26}{pages}")

    print(f"\nDone in {seconds:.1f} s")


def run():
    if not config.RAW_PAGES_FILE.exists():
        if not config.RAW_ZIP.exists():
            print("ZIP with pages not found - run the crawler first")
            return
        convert_zip_to_jsonl()

    from modules.spark_utils import create_session      # pyspark is imported only when Spark is used

    start = time.time()
    spark = create_session("AnimalsExtractor")
    sc = spark.sparkContext

    # file is split into partitions, each partition is processed in parallel by one executor
    lines = sc.textFile(str(config.RAW_PAGES_FILE))
    print(f"Input split into {lines.getNumPartitions()} partitions")

    results = lines.map(process_page).cache()       # cached, results are used three times below
    animals = results.filter(is_animal).map(result_value)
    skipped = results.filter(is_skipped).map(result_value)

    # saveAsTextFile fails if the output folder already exists
    if config.SPARK_ANIMALS_DIR.exists():
        shutil.rmtree(config.SPARK_ANIMALS_DIR)
    animals.map(to_json_line).saveAsTextFile(str(config.SPARK_ANIMALS_DIR))

    # missing fields counted on executors: field -> (field, 1) -> (field, count)
    missing_pairs = animals.flatMap(missing_fields).map(lambda field: (field, 1))
    missing = missing_pairs.reduceByKey(lambda a, b: a + b).collectAsMap()

    skipped_list = sorted(skipped.collect())        # small list, can be collected to the driver
    count = animals.count()

    spark.stop()

    save_skipped(skipped_list)
    print_run_summary(count, skipped_list, missing, time.time() - start)





def load_records(paths):
    # id -> record from JSON lines files
    records = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                records[record["id"]] = record
    return records


def compare():
    # checks that Spark output is the same as output of the part 1 extractor
    if not config.EXTRACTED_FILE.exists():
        print("extracted.jsonl not found - run the extractor first")
        return
    if not config.SPARK_ANIMALS_DIR.exists():
        print("Spark output not found - run Spark extraction first")
        return

    old = load_records([config.EXTRACTED_FILE])
    new = load_records(sorted(config.SPARK_ANIMALS_DIR.glob("part-*")))

    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))

    different = []
    for slug in set(old) & set(new):
        if old[slug] != new[slug]:
            different.append(slug)
    different.sort()

    print(f"Part 1 extractor: {len(old)} records")
    print(f"Spark:            {len(new)} records")
    print(f"\nOnly in part 1:   {len(only_old)}  {only_old[:10]}")
    print(f"Only in Spark:    {len(only_new)}  {only_new[:10]}")
    print(f"Different:        {len(different)}  {different[:10]}")

    if not only_old and not only_new and not different:
        print("\nOutputs are identical.")
