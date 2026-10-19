import ast
import collections
from pathlib import Path

root = Path("src/yuxiaoer")
files = list(root.rglob("*.py"))

print("== unused imports ==")
total = 0
for f in files:
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                imported[a.asname or a.name] = n.lineno
        elif isinstance(n, ast.Import):
            for a in n.names:
                imported[(a.asname or a.name).split(".")[0]] = n.lineno
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            pass
    # attribute roots: from x import y -> y used as Name usually; also string annotations
    used |= set(ast.get_docstring(tree) or "")
    unused = [name for name in imported if name not in used and name != "annotations"]
    if unused:
        total += len(unused)
        print(f.as_posix(), len(unused), ",".join(sorted(unused)[:12]))
print("total unused", total)

print("\n== repeated 5-line windows ==")
windows = collections.defaultdict(set)
for f in files:
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l and not l.startswith("#")]
    for i in range(len(lines) - 4):
        w = tuple(lines[i:i + 5])
        if sum(len(x) for x in w) < 60:
            continue
        windows[w].add(f.as_posix())
dups = [(len(v), w) for w, v in windows.items() if len(v) > 1]
for n, w in sorted(dups, reverse=True)[:8]:
    print(n, w[0][:90])
