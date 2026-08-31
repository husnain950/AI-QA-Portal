"""How many leaves does ONE inserted leaf falsely report as 'changed'?

Replicates json_parser's positional source_key walk and versions.diff_documents'
matching, then does the same keyed on node_key. Read-only.
"""
import copy
import glob
import json
import statistics


def maps(doc):
    sk, nk = {}, {}
    def container(node, p):
        for i, s in enumerate(node.get("sections") or []):
            sk[f"{p}/sections/{i}"] = s.get("plain_text") or ""
            if s.get("node_key"):
                nk[s["node_key"]] = s.get("plain_text") or ""
        for i, x in enumerate(node.get("parts") or []):
            container(x, f"{p}/parts/{i}")
        for i, x in enumerate(node.get("divisions") or []):
            container(x, f"{p}/divisions/{i}")
    for i, c in enumerate(doc.get("chapters") or []):
        container(c, f"/chapters/{i}")
    for i, c in enumerate(doc.get("schedules") or []):
        container(c, f"/schedules/{i}")
    return sk, nk

NEW = {"code": "0A", "heading": "Inserted", "html": "<p>x</p>", "plain_text": "x",
       "start_page": 1, "end_page": 1, "node_key": "ch:~inserted/s:0a", "footnotes": []}

rows = []
for f in sorted(glob.glob("data/corpora/*/output/*.json")):
    doc = json.load(open(f))
    b_sk, b_nk = maps(doc)
    if len(b_sk) < 3 or not b_nk:
        continue
    after = copy.deepcopy(doc)
    target = next((c for c in after.get("chapters") or [] if c.get("sections")), None)
    if target is None:
        continue
    target["sections"].insert(0, dict(NEW))
    a_sk, a_nk = maps(after)
    sk_changed = sum(1 for k, v in a_sk.items() if k in b_sk and b_sk[k] != v)
    nk_changed = sum(1 for k, v in a_nk.items() if k in b_nk and b_nk[k] != v)
    rows.append((f.split("/")[-3], f.split("/")[-1], len(b_sk), sk_changed, nk_changed))

tot_sk = sum(r[3] for r in rows)

tot_nk = sum(r[4] for r in rows)
leaves = sum(r[2] for r in rows)
pct = [100 * r[3] / r[2] for r in rows]
full = [r for r in rows if r[3] == r[2]]
print(f"{len(rows)} documents with node_key, {leaves} leaves")
print("ONE inserted leaf per document, truth = 0 changed + 1 added:")
print(f"  source_key identity -> {tot_sk} leaves falsely 'changed'")
print(f"  node_key   identity -> {tot_nk} leaves falsely 'changed'")
print(f"  median document churned {statistics.median(pct):.0f}%, mean {statistics.mean(pct):.0f}%")
print(f"  {len(full)} documents churn 100% of their leaves")
print("\nworst 6:")
for r in sorted(rows, key=lambda r:
    -r[3] / r[2])[:6]:
    print(f"  {100*r[3]/r[2]:3.0f}%  {r[3]:4d}/{r[2]:<5d}  {r[0]:9s} {r[1][:48]}")
