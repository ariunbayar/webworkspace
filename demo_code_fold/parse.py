import sys
import io

from CodeRaw import CodeRaw


filename = sys.argv[1]
with io.open(filename, encoding="utf-8") as f:
    coderaw = CodeRaw(f.readlines())

coderaw.parse()
coderaw.dump()
