"""Baseline census of the contract boundary. Read-only."""
import collections
import glob
import json


def leaves(doc):
    """(source_key, node_key, plain_text) for every leaf, in the API's walk order."""
    out = []
    def container(node, sk):
        for i, s in enumerate(node.get("sections") or []):
            out.append((f"{sk}/sections/{i}", s.get("node_key"), s.get("plain_text") or ""))
        for i, p in enumerate(node.get("parts") or []):
            container(p, f"{sk}/parts/{i}")
        for i, v in enumerate(node.get("divisions") or []):
            container(v, f"{sk}/divisions/{i}")
    for i, c in enumerate(doc.get("chapters") or []):
        container(c, f"/chapters/{i}")
    for i, s in enumerate(doc.get("schedules") or []):
        container(s, f"/schedules/{i}")
    return out

def all_nodes(doc):
    def walk(n):
        yield n
        for k in ("parts", "divisions", "sections"):
            for c in n.get(k) or []:
                yield from walk(c)
    for c in (doc.get("chapters") or []) + (doc.get("schedules") or []):
        yield from walk(c)

print(f"{'lane':10} {'docs':>5} {'leaves':>7} {'w/node_key':>11} {'nodes':>7} {'typed':>7} {'dupes':>6}")
tot_leaves = tot_nk = tot_dupe = 0
missing = collections.defaultdict(list)
for lane in ("acts", "rules", "ordinance"):
    files = sorted(glob.glob(f"data/corpora/{lane}/output/*.json"))
    n_leaves = n_nk = n_nodes = n_typed = n_dupe = 0
    docs_nk = 0
    for f in files:
        d = json.load(open(f))
        ls = leaves(d)
        n_leaves += len(ls)
        got = [nk for _, nk, _ in ls if nk]
        n_nk += len(got)
        if got:
            docs_nk += 1
        else:
            missing[lane].append(f.split("/")[-1])
        c = collections.Counter(got)
        n_dupe += sum(v - 1 for v in c.values() if v > 1)
        for node in all_nodes(d):
            n_nodes += 1
            if node.get("type"):
                n_typed += 1
    print(f"{lane:10} {len(files):5} {n_leaves:7} {n_nk:11} {n_nodes:7} {n_typed:7} {n_dupe:6}"
          f"   ({docs_nk}/{len(files)} docs)")
    tot_leaves += n_leaves
    tot_nk += n_nk
    tot_dupe += n_dupe
print(f"{'TOTAL':10} {'':5} {tot_leaves:7} {tot_nk:11} {'':7} {'':7} {tot_dupe:6}")
print()
for lane, names in missing.items():
    print(f"{lane}: {len(names)} documents with no node_key on any leaf")
    for n in sorted(names)[:20]:
        print("   ", n[:70])
