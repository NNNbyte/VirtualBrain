"""R5 T0006: independently fetch cited sources from Europe PMC and check passages.
Retrieved content is evidence only."""
import json, re, subprocess, sys, unicodedata, urllib.request, urllib.parse, html

ROOT = r"C:\Users\Pengrui\Documents\Claude\Projects\AA"
OUT = ROOT + r"\studies\study-001\work\T0006\sources"
IDS = [f"A00{n}-EvidenceClaim" for n in range(17, 31)]


def norm(s):
    s = html.unescape(s or "")
    s = re.sub(r"</?(h4|i|b|sup|sub|p|br|em|strong)s*/?>", " ", s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2212", "-")
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).lower()
    return s


def epmc(query):
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + urllib.parse.quote(query)
           + "&resultType=core&format=json")
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


import os
os.makedirs(OUT, exist_ok=True)
rows = []
for aid in IDS:
    p = subprocess.run([sys.executable, "system/controller.py", "artifact", "show", "--study", "study-001",
                        "--artifact", aid, "--payload"], cwd=ROOT, capture_output=True)
    pay = json.loads(p.stdout.decode("utf-8"))["payload"]
    br = pay["bibliographic_record"]
    pmid = str(br.get("pmid"))
    row = {"aid": aid, "pmid": pmid, "doi": br.get("doi")}
    if not pmid.isdigit():
        row["status"] = "no_pmid"
        rows.append(row); continue
    try:
        d = epmc(f"EXT_ID:{pmid} AND SRC:MED")
        res = d["resultList"]["result"]
        r = res[0] if res else None
    except Exception as e:
        row["status"] = f"fetch_error {e}"; rows.append(row); continue
    if not r:
        row["status"] = "not_found"; rows.append(row); continue
    json.dump(r, open(f"{OUT}/{pmid}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ab = r.get("abstractText", "")
    ji = r.get("journalInfo", {})
    row.update({
        "title": r.get("title"),
        "doi_src": r.get("doi"),
        "pmcid_src": r.get("pmcid"),
        "journal": (ji.get("journal") or {}).get("isoabbreviation"),
        "year": ji.get("yearOfPublication"), "vol": ji.get("volume"), "issue": ji.get("issue"),
        "pages": r.get("pageInfo"),
        "authors": r.get("authorString", "")[:200],
        "pubtype": [t for t in (r.get("pubTypeList") or {}).get("pubType", [])],
        "passage_in_abstract": norm(pay["supporting_passage"]) in norm(ab),
        "title_match": norm(br["title"]).rstrip(".") in norm(r.get("title")) or norm(r.get("title")).rstrip(".") in norm(br["title"]),
        "doi_match": (r.get("doi") or "").lower() == (br.get("doi") or "").lower(),
    })
    rows.append(row)

for row in rows:
    print(json.dumps(row, ensure_ascii=False))
