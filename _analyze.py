import ast
from pathlib import Path

root = Path("src/yuxiaoer")
funcs = []
for f in root.rglob("*.py"):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((n.end_lineno - n.lineno + 1, f.as_posix(), n.name, n.lineno))
print("functions", len(funcs), "avg", round(sum(x[0] for x in funcs) / len(funcs), 1))
for n, f, name, line in sorted(funcs, reverse=True)[:20]:
    print(n, f, line, name)
