#!/usr/bin/env python3
"""Check Python files for leftover print() and pprint() calls.

Run: python3 src/python_print_checker.py app.py
     python3 src/python_print_checker.py project/
     python3 src/python_print_checker.py --stdin < app.py

A debug print left in shipped code leaks internal
state into logs and looks unprofessional — every
Python team has shipped one. This tool reads the
Python files you point it at, finds every print()
and pprint() call, and reports each one with the
file and the line number. It exits 1 when any call
is found, so it can fail a CI run. A file with no
print calls exits 0.

Calls are found with the standard library ast
module, by reading the code's real structure —
so a print inside a string or a comment is never
a call, and a print that only looks like one in a
docstring is never flagged. What is flagged is
exactly: a call to the builtin print(), a call to
pprint() imported from the pprint module, a call
to pprint.pprint(), and a call to builtins.print().
A method called print on some other object, like
logger.print(), is not the builtin and is left
alone, and mentioning print without calling it,
like f = print, is left alone too.

It never rewrites a file, never touches the
network, and reads only the files and folders
you point it at.
"""

import argparse
import ast
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"


def is_print_call(node):
    """True when a call node is a print() or pprint() call.

    Returns "print" or "pprint", or None when the call
    is something else. Only the builtin print, the
    pprint function, pprint.pprint, and builtins.print
    count — a method named print on another object
    does not.
    """
    func = node.func
    if isinstance(func, ast.Name):
        if func.id == "print":
            return "print"
        if func.id == "pprint":
            return "pprint"
        return None
    if isinstance(func, ast.Attribute):
        if func.attr == "pprint" and isinstance(func.value, ast.Name):
            if func.value.id == "pprint":
                return "pprint"
        if func.attr == "print" and isinstance(func.value, ast.Name):
            if func.value.id == "builtins":
                return "print"
        return None
    return None


def check_text(text):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "call": "print" or "pprint"}, in document order.
    A file that does not parse raises SyntaxError —
    the caller turns that into a finding of its own.
    """
    tree = ast.parse(text)
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = is_print_call(node)
            if call:
                findings.append({"line": node.lineno,
                                 "call": call})
    findings.sort(key=lambda item: item["line"])
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    try:
        return check_text(text), None
    except SyntaxError as exc:
        return [], "cannot be parsed as Python (%s)" % exc.msg


def _is_python_file(path):
    return Path(path).name.endswith(".py")


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of Python files.

    A file given directly is always checked, whatever
    its name. A folder is walked for files ending in
    .py only, recursively by default. .git folders are
    never walked, and directory links are never
    followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_python_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one leftover call."""
    return ("FAIL %s: %s() call line %d — remove it before "
            "shipping" % (path, finding["call"], finding["line"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except (FileNotFoundError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no Python files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d leftover print call(s) "
                  "in %d file(s)." % (len(files), findings,
                                      files_with_findings))
        else:
            print("OK — %d file(s) checked, no leftover print "
                  "calls." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one Python document read from standard input."""
    text = sys.stdin.read()
    try:
        bad = check_text(text)
    except SyntaxError as exc:
        bad = []
        error = "cannot be parsed as Python (%s)" % exc.msg
    else:
        error = None
    findings = len(bad) + (1 if error else 0)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": error}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        if error:
            print("FAIL <stdin>: %s" % error)
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d leftover print call(s) "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, no leftover print "
                  "calls.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python_print_checker",
        description="Check Python files for leftover print() "
                    "and pprint() calls, fail CI when one is "
                    "found. Report-only: it never edits a file.")
    parser.add_argument("paths", nargs="*",
                        help="Python files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one Python document from "
                             "standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one Python file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
