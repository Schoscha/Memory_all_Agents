import sys, time
sys.path.insert(0, "/root/Second-Brain/scripts")
from vaultindex import Index

t = time.time()
ix = Index("/root/Second-Brain", db_path="/root/Second-Brain/.agent-memory-index.sqlite")
print("vektor:", ix.vec, getattr(ix, "vec_error", ""))
n = ix.build()
print("indexiert:", n, "in", round(time.time() - t, 1), "s")
print(ix.stats())
for r in ix.search("wie sichere ich Dienste auf dem Server", 3):
    print(round(r["score"], 4), r["path"], "|", r["heading"])
