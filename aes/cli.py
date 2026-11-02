"""aes: AI Edit Stack command line.

  aes doctor
  aes new <name> --brand latent --mode standard [--source inbox/<folder>] [--format reel]
  aes analyze <name> [--force]
  aes describe <name> --pending | --apply <file.json>
  aes candidates <name>
  aes library index | fetch music|sfx "<query>" [--mood m | --role r] [-n 5] | suggest [...] | roles
  aes build <name>
  aes framesheet <name> [--at 1.2,4.5]
  aes preview <name>            (live studio in the browser; no render)
  aes render <name> [--draft] [--no-precut]
  aes status <name>
  aes cache-clean [--yes]
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="aes", description="AI Edit Stack")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").add_argument("--no-gpu-test", action="store_true")

    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--brand", default="default")
    n.add_argument("--mode", default="standard", choices=["quick", "standard", "premium"])
    n.add_argument("--source", default=None, help="folder or file with raw clips (default inbox/<name>)")
    n.add_argument("--format", default="reel", help="reel | short | youtube | story (free text for the brief)")

    a = sub.add_parser("analyze")
    a.add_argument("name")
    a.add_argument("--force", action="store_true")

    ds = sub.add_parser("describe")
    ds.add_argument("name")
    g = ds.add_mutually_exclusive_group(required=True)
    g.add_argument("--pending", action="store_true")
    g.add_argument("--apply", metavar="FILE")

    sub.add_parser("candidates").add_argument("name")

    lib = sub.add_parser("library")
    lsub = lib.add_subparsers(dest="lcmd", required=True)
    lsub.add_parser("index").add_argument("--force", action="store_true")
    f = lsub.add_parser("fetch")
    f.add_argument("kind", choices=["music", "sfx"])
    f.add_argument("query")
    f.add_argument("-n", type=int, default=5)
    f.add_argument("--mood")
    f.add_argument("--role")
    f.add_argument("--licenses", default="cc0,by")
    f.add_argument("--provider", default="openverse", choices=["openverse", "freesound"])
    s = lsub.add_parser("suggest")
    s.add_argument("--mood")
    s.add_argument("--min-dur", type=float, default=30)
    s.add_argument("--energy", choices=["low", "mid", "high"])
    s.add_argument("--bpm", help="e.g. 100-128")
    s.add_argument("--top", type=int, default=6)
    lsub.add_parser("roles")

    sub.add_parser("build").add_argument("name")
    fs = sub.add_parser("framesheet")
    fs.add_argument("name")
    fs.add_argument("--at", help="comma-separated seconds (default: one frame per shot)")
    sub.add_parser("preview").add_argument("name")
    r = sub.add_parser("render")
    r.add_argument("name")
    r.add_argument("--draft", action="store_true")
    r.add_argument("--no-precut", action="store_true")
    sub.add_parser("status").add_argument("name")
    sub.add_parser("cache-clean").add_argument("--yes", action="store_true")

    args = p.parse_args(argv)
    c = args.cmd
    if c == "doctor":
        from .doctor import doctor
        doctor(gpu_test=not args.no_gpu_test)
    elif c == "new":
        from .project import new_project
        new_project(args.name, args.brand, args.mode, args.source, args.format)
    elif c == "analyze":
        from .project import analyze_project
        analyze_project(args.name, force=args.force)
    elif c == "describe":
        from .project import describe_apply, describe_pending
        describe_pending(args.name) if args.pending else describe_apply(args.name, args.apply)
    elif c == "candidates":
        from .project import write_candidates
        write_candidates(args.name)
    elif c == "library":
        from . import library as L
        if args.lcmd == "index":
            L.index(force=args.force)
        elif args.lcmd == "fetch":
            L.fetch(args.kind, args.query, args.n, args.mood, args.role, args.licenses, args.provider)
        elif args.lcmd == "suggest":
            L.suggest_music(args.mood, args.min_dur, args.energy, args.bpm, args.top)
        else:
            L.sfx_roles_summary()
    elif c == "build":
        from .build import build
        build(args.name)
    elif c == "framesheet":
        from .framesheet import make
        make(args.name, args.at)
    elif c == "preview":
        from .util import npx_hf, project_dir
        npx_hf(["preview", ".", "--background"], cwd=project_dir(args.name) / "hf", capture=False)
    elif c == "render":
        from .render import render
        render(args.name, quality="draft" if args.draft else "final", precut=not args.no_precut)
    elif c == "status":
        from .project import status
        status(args.name)
    elif c == "cache-clean":
        from .project import clean_cache
        clean_cache(dry=not args.yes)


if __name__ == "__main__":
    main(sys.argv[1:])
