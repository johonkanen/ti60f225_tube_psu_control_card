"""Summary of a kicad-cli DRC JSON report: counts per type, unconnected items per net, parity."""
import collections
import json
import re
import sys

d = json.load(open(sys.argv[1]))
QUIET = ("silk", "lib_footprint", "courtyard")
kinds = collections.Counter((v["type"], v["severity"]) for v in d.get("violations", []))
print("DRC violations:", sum(kinds.values()),
      "| without silkscreen/library/courtyard:", sum(c for (t, _), c in kinds.items() if not t.startswith(QUIET)))
for (t, s), c in sorted(kinds.items(), key=lambda kv: -kv[1]):
    print(f"  {c:4} {t} ({s})")
for v in d.get("violations", []):
    if not v["type"].startswith(QUIET):
        its = "; ".join(f"{i['description']} @({i['pos']['x']:.2f},{i['pos']['y']:.2f})" for i in v["items"])
        print(f"    {v['type']}: {v['description'][:70]} | {its[:230]}")
un = d.get("unconnected_items", [])
nets = collections.Counter()
for u in un:
    m = re.search(r"\[([^\]]+)\]", u["items"][0]["description"])
    nets[m.group(1) if m else "?"] += 1
print("unconnected items:", len(un), "on", len(nets), "nets")
for n, c in sorted(nets.items()):
    print(f"  {c} {n}")
par = d.get("schematic_parity", [])
print("schematic parity:", len(par))
for p in par[:10]:
    print("  ", p["description"], "|", "; ".join(i["description"] for i in p["items"])[:160])
