import ast
import sys

try:
    with open('/app/create_project_validator_tool.py', 'r') as f:
        content = f.read()
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error at line {e.lineno}: {e.msg}")
    # Show context around the error
    lines = content.split('\n')
    start = max(0, e.lineno - 5)
    end = min(len(lines), e.lineno + 5)
    for i in range(start, end):
        marker = ">>> " if i + 1 == e.lineno else "    "
        print(f"{marker}{i+1}: {lines[i]}")
