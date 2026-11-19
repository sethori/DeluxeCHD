"""Release versioning: every push to main gets the next version.

Each part counts 0-9 and rolls over into the part on its left:
1.0.1 → 1.0.2 … 1.0.9 → 1.1.0 … 1.9.9 → 2.0.0

  python packaging/version.py next          print the next version, from the git tags
  python packaging/version.py stamp X.Y.Z   write it into src/deluxechd/__init__.py (CI only)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INIT = os.path.join(ROOT, "src", "deluxechd", "__init__.py")
FIRST = (1, 0, 1)


def parse_tag(tag):
    m = re.fullmatch(r"v(\d+)\.(\d+)(?:\.(\d+))?", tag.strip())
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def bump(v):
    major, minor, patch = v
    patch += 1
    if patch > 9:
        patch, minor = 0, minor + 1
    if minor > 9:
        minor, major = 0, major + 1
    return major, minor, patch


def next_version(tags):
    released = [v for v in map(parse_tag, tags) if v]
    if not released:
        return FIRST
    return max(FIRST, bump(max(released)))


def git_tags():
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def stamp(version):
    with open(INIT, encoding="utf-8") as fh:
        text = fh.read()
    new, n = re.subn(r'^__version__ = ".*"$', f'__version__ = "{version}"', text, flags=re.M)
    if n != 1:
        sys.exit("couldn't find __version__ in " + INIT)
    with open(INIT, "w", encoding="utf-8") as fh:
        fh.write(new)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "next":
        print(".".join(map(str, next_version(git_tags()))))
    elif len(sys.argv) == 3 and sys.argv[1] == "stamp":
        stamp(sys.argv[2])
    else:
        sys.exit(__doc__)
