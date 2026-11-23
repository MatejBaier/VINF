# VINF: Vyhľadávač zvierat

Semestrálny projekt z predmetu Vyhľadávanie informácií (FIIT STU, 2026/2027), autor Matej Baier.

Vyhľadávač zvierat nad encyklopédiou [A-Z Animals](https://a-z-animals.com/animals/), ktorá je spojená s anglickou Wikipédiou.

* **1. časť:** crawler, REGEX extraktor, vlastný TF index a vyhľadávanie s 5 metódami idf a 4 skórovacími funkciami
* **2. časť:** extrakcia v Apache Spark, spracovanie Wikipedia dumpu regexmi, join s Wikipédiou, index v PyLucene a evaluácia

## Požiadavky

| Čo | Verzia | Na čo |
|---|---|---|
| Python | 3.11 | celý projekt (Spark 3.4 nefunguje s Pythonom 3.14) |
| Java | 17 | Spark 3.4 (s Javou 21 padá na `DirectByteBuffer`) |
| Docker | | PyLucene, image `coady/pylucene` |
| Wikipedia dump | `enwiki-20261001-pages-articles.xml.bz2` (25,8 GB) | len pre položku 17, cesta je v `config.py` (`WIKI_DUMP_FILE`) |

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JAVA_HOME=$(/usr/libexec/java_home -v 17)     # macOS
```

## Spustenie

Program má textové menu:

```bash
python main.py
```

PyLucene sa nedá nainštalovať cez pip, preto položky 21 až 27 bežia v Dockeri (z priečinka projektu):

```bash
docker run --rm -it -v "$PWD":/project -w /project coady/pylucene python main.py
```

| Položky | Časť | Kde spustiť |
|---|---|---|
| 1 až 4 | crawler a štatistika crawlu | venv |
| 5 až 9 | REGEX extraktor, unit testy, tiktoken | venv |
| 10 až 13 | vlastný index a vyhľadávanie (1. časť) | venv |
| 14 až 15 | Spark: extrakcia zvierat, porovnanie s 1. časťou | venv |
| 16 až 18 | Spark: Wikipedia dump (vzorka, celý dump, ukážka záznamu) | venv |
| 19 až 20 | Spark: join zvierat s Wikipédiou, ukážka záznamu | venv |
| 21 až 25 | Lucene: index, štatistika, vyhľadávanie, typy dopytov, starý vs nový index | Docker |
| 26 | evaluácia: starý index, Lucene, Google a vyhľadávanie na a-z-animals | Docker |
| 27 | unit testy 2. časti (wiki extraktor, join, Lucene a evaluácia) | venv alebo Docker |

Poradie pri spracovaní od začiatku: 2 (crawl), 5 a 10 (starý index), 14, 17, 19 (Spark), 21 (Lucene) a potom vyhľadávanie (23) alebo evaluácia (26).

## Dáta

Priečinok `data/` nie je v gite, lebo má okolo 2 GB. Vzniká postupne pri spúšťaní:

| Súbor | Vytvára | Obsah |
|---|---|---|
| `raw_htmls.zip` | crawler (2) | stiahnuté stránky zvierat |
| `extracted.jsonl` | extraktor (5) | jedno zviera na riadok |
| `index/` | indexer (10) | vlastný index z 1. časti |
| `raw_pages.jsonl`, `spark/animals/` | Spark (14) | ZIP prevedený pre Spark, extrahované zvieratá |
| `spark/wiki_taxa/`, `spark/wiki_redirects/` | Spark (17) | články s taxonomickým alebo plemenným infoboxom, redirecty na ne |
| `spark/animals_wiki/`, `join_unmatched.tsv` | Spark (19) | zvieratá s pripojenou Wikipédiou, nenapojené zvieratá |
| `lucene_index/` | Lucene (21) | index PyLucene |

## Štruktúra

```
main.py                     textové menu
config.py                   cesty a nastavenia
requirements.txt
modules/
  crawler.py, stats.py, utils.py                 crawler (1. časť)
  extractor.py, tokenizer.py, token_stats.py     REGEX extraktor a tokenizer (1. časť)
  indexer.py, search.py                          vlastný index a vyhľadávanie (1. časť)
  spark_utils.py                                 Spark session (local[*])
  spark_animals.py                               extrakcia zvierat v Sparku
  wiki_extractor.py                              REGEX extrakcia z wikitextu
  spark_wiki.py                                  spracovanie Wikipedia dumpu v Sparku
  spark_join.py                                  join zvierat s Wikipédiou
  lucene_utils.py, lucene_indexer.py             schéma a tvorba indexu PyLucene
  lucene_search.py                               vyhľadávanie v PyLucene
  evaluation.py                                  evaluácia (P@5, P@10, R@10, RR)
tests/
  test_extractor.py, expected.json, unit_test_pages.zip    testy extraktora (1. časť)
  test_wiki_extractor.py, wiki_test_pages.xml.bz2          testy wiki extraktora na 9 stránkach z dumpu
  test_join.py                                             testy joinu
  test_lucene_helpers.py                                   testy hodnôt indexu, regexov dopytu a metrík
evaluation/
  queries.json              11 dopytov a ručne určené relevantné zvieratá
  external_results.tsv      výsledky z Google a z vyhľadávania na a-z-animals (zapísané ručne)
  results.txt               výstup evaluácie, textové tabuľky a tabuľky pre DokuWiki
```

## Evaluácia

`evaluation/queries.json` obsahuje 11 dopytov. Každý má textovú podobu (rovnakú pre všetky systémy), voliteľne dopyt s poľami pre Lucene a zoznam relevantných zvierat. Položka 26 spustí dopyty v starom indexe (spread / standard) a v Lucene, načíta výsledky Google a a-z-animals z `external_results.tsv` a vypočíta P@5, P@10, R@10 a RR. Výsledok uloží do `evaluation/results.txt`.

Google a vyhľadávanie na a-z-animals sa nedajú spúšťať z programu, preto sú ich výsledky v súbore. Pri Google je dopyt `site:a-z-animals.com/animals/ <dopyt>`, pri a-z-animals vyhľadávacie pole stránky. Z oboch sa berú len profily zvierat z prvej strany výsledkov (články a zoznamy sa vynechajú), aby sa porovnávali rovnaké dokumenty ako v mojom indexe.
