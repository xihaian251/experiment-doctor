"""Synthetic experiment script for Phase 2 run-capture tests.

Behavior is switched by flags so one fixture covers exit 0/1, stderr output and
artifact creation; it also echoes an env marker so tests can prove the child
inherits the caller's environment without any config file existing.
"""

import argparse
import os
import time
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--exit", type=int, default=0)
parser.add_argument("--noise", action="store_true", help="write to stderr")
parser.add_argument("--artifact", help="write results/<name> inside the project")
parser.add_argument("--echo-env", metavar="NAME", help="print an env var to stderr")
args = parser.parse_args()

if args.echo_env:
    print(f"{args.echo_env}={os.environ.get(args.echo_env, '<missing>')}", file=sys.stderr)
if args.noise:
    print("warning: synthetic stderr line", file=sys.stderr)
if args.artifact:
    target = pathlib.Path("results") / args.artifact
    target.parent.mkdir(exist_ok=True)
    target.write_text(f"epoch,acc\n1,{time.time()}\n", encoding="utf-8")

sys.exit(args.exit)
