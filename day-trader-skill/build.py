#!/usr/bin/env python3
"""Sync shared/tradelib.py into every skill and build one .zip per skill in dist/
(the format claude.ai expects when you upload a skill).

    python3 build.py
"""
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(ROOT, "shared", "tradelib.py")
SKILLS = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")


def write_skill_md():
    sys.path.insert(0, os.path.join(ROOT, "shared"))
    from skills_src import SKILLS as SRC  # noqa: E402
    with open(os.path.join(ROOT, "shared", "COMMON.md"), encoding="utf-8") as f:
        common = f.read()
    for name, (desc, body) in SRC.items():
        desc = " ".join(desc.split())
        assert len(desc) <= 1024, f"{name}: description too long ({len(desc)})"
        os.makedirs(os.path.join(SKILLS, name), exist_ok=True)
        with open(os.path.join(SKILLS, name, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(f"---\nname: {name}\ndescription: {json.dumps(desc, ensure_ascii=False)}\n---\n{body.rstrip()}\n\n{common}")


def main():
    write_skill_md()
    os.makedirs(DIST, exist_ok=True)
    for name in sorted(os.listdir(SKILLS)):
        sd = os.path.join(SKILLS, name)
        if not os.path.isfile(os.path.join(sd, "SKILL.md")):
            continue
        scripts = os.path.join(sd, "scripts")
        if os.path.isdir(scripts):
            shutil.copyfile(SHARED, os.path.join(scripts, "tradelib.py"))
        zp = os.path.join(DIST, f"{name}.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for base, dirs, files in os.walk(sd):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith(".pyc"):
                        continue
                    full = os.path.join(base, f)
                    z.write(full, os.path.join(name, os.path.relpath(full, sd)))
        print(f"built {os.path.relpath(zp, ROOT)}")


if __name__ == "__main__":
    main()
