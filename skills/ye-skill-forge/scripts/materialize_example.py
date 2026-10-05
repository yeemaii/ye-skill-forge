#!/usr/bin/env python3
"""Copy a teaching example into a standalone, discoverable test directory."""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.lifecycle import is_skill_package, iter_source_files, package_manifest
from core.package import local_path, package_children
from core.skill_utils import is_within


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def materialize_example(name, output_dir):
    source = (EXAMPLES / name).resolve()
    if source.parent != EXAMPLES.resolve() or not source.is_dir():
        raise ValueError("Choose a direct example directory under examples/")
    output = Path(output_dir).expanduser().resolve()
    if is_within(output, EXAMPLES):
        raise ValueError("Materialize outside examples/ so examples stay inactive")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    files = list(iter_source_files(source))
    if not any(rel.name == "SKILL.example.md" for _path, rel in files):
        raise ValueError("Example has no SKILL.example.md entrypoint")
    if any(rel.name == "SKILL.md" for _path, rel in files):
        raise ValueError("Example contains an active SKILL.md entrypoint")
    entries = {rel for _path, rel in files if rel.name == "SKILL.example.md"}
    expected = {Path("SKILL.example.md")}
    if is_skill_package(source):
        manifest = package_manifest(source)
        expected = {(local_path(source, manifest.get("router")) / "SKILL.example.md").relative_to(source)}
        expected.update(Path(child["path"]) / "SKILL.example.md" for child in package_children(source, manifest))
        if Path("SKILL.example.md") in entries:
            expected.add(Path("SKILL.example.md"))
    if entries != expected:
        raise ValueError("Choose a runnable single Skill or declared family; comparison directories are teaching-only")
    output.mkdir(parents=True)
    try:
        for path, rel in files:
            target = output / (rel.with_name("SKILL.md") if rel.name == "SKILL.example.md" else rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    except OSError:
        shutil.rmtree(output)
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", help="Example directory name")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(materialize_example(args.example, args.output_dir))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
