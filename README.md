# python-print-checker-cli

Check Python files for leftover `print()` and `pprint()` calls, fail CI when one is found — it never runs your code.

[![CI](https://github.com/haiderstudio/python-print-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/python-print-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`python_print_checker` reads the Python files you
point it at, finds every `print()` and `pprint()`
call, and reports each one with the file and the
line number. It exits 1 when any call is found, so
it can fail a CI run. A file with no print calls
exits 0.

- A debug print left in shipped code leaks
  internal state into logs and looks
  unprofessional — every Python team has shipped
  one. This gate names the exact line, so the
  print is gone before the merge.
- Calls are found with the standard library `ast`
  module, by reading the code's real structure —
  so a print inside a string or a comment is
  never a call, and a print that only looks like
  one in a docstring is never flagged.
- What counts as a call is exactly: the builtin
  `print()`, `pprint()` imported from the pprint
  module, `pprint.pprint()`, and
  `builtins.print()`. A method called print on
  some other object, like `logger.print()`, is
  not the builtin and is left alone, and
  mentioning print without calling it, like
  `f = print`, is left alone too.
- A file given directly on the command line is
  always checked, whatever its name. A folder is
  walked for files ending in `.py` only,
  recursively by default (`--no-recursive` stops
  at the top level). `.git` folders are never
  walked, and directory links are never followed.
- `--json` prints the result as JSON, and
  `--stdin` checks one Python document read from
  standard input.
- A file that does not parse as Python is reported
  as a problem, not skipped — a file that cannot
  be read cannot be proven clean.

## Who it is for

Any Python team that has ever shipped a debug
print to production — which is every Python team.
One gate in CI, run over the files in the pull
request, and the stray `print("here")` never
reaches the main branch again.

## What it does NOT do

- It does not remove the prints it finds. That
  is a human decision — a print in a small script
  may be the whole point of the script. This tool
  reports, and you decide.
- It does not check logging calls. A `print`
  replaced by `logging.debug` is the usual fix,
  but whether logging is used well is a different
  job.
- It does not run the code it checks. The files
  are parsed with Python's own `ast` module, so
  a print call in a checked file is reported,
  never executed.
- It never rewrites a file, and it never touches
  the network.

## How this differs

- A fresh search of GitHub on Nov 14, 2026 found 0
  results for `"python-print-checker-cli"` and 88
  results for `python print checker`, all scripts
  that print things (a ticket checker, a Discord
  generator, a Bitcoin address checker, a
  plagiarism checker, an RSS checker) — pages
  that merely contain the words "python", "print"
  and "checker". None of them checks for leftover
  prints.
- The most established single-job rival is
  [JBKahn/flake8-print](https://github.com/JBKahn/flake8-print)
  (121 stars, checked Nov 14, 2026), a flake8
  plugin that forbids print statements — it needs
  flake8 installed and configured, and it only
  runs inside a flake8 setup. Ruff's T201 rule
  also flags prints, as one rule among hundreds
  in a whole linter. A linter plugin is their
  job, not this repo's: this is a tested
  standard-library CLI with per-call file-and-line
  reporting and a CI exit code, zero install —
  one check only, nothing to configure.
- So the narrow slice stands: leftover prints
  only, found by real parsing, with a CI exit
  code, and no dependency to install.

## Install

```sh
git clone https://github.com/haiderstudio/python-print-checker-cli.git
cd python-print-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one Python file:

```sh
python3 src/python_print_checker.py app.py
```

A file with no leftover prints passes:

```sh
$ python3 src/python_print_checker.py examples/clean.py
OK — 1 file(s) checked, no leftover print calls.
```

A file with leftover prints fails, with the call
and line for each one:

```sh
$ python3 src/python_print_checker.py examples/flagged.py
FAIL examples/flagged.py: print() call line 7 — remove it before shipping
FAIL examples/flagged.py: print() call line 10 — remove it before shipping
FAIL examples/flagged.py: pprint() call line 15 — remove it before shipping
FAIL examples/flagged.py: print() call line 16 — remove it before shipping
Checked 1 file(s), 4 leftover print call(s) in 1 file(s).
```

Check a whole folder (`.py` files only — other
files are never opened):

```sh
$ python3 src/python_print_checker.py examples/
FAIL examples/flagged.py: print() call line 7 — remove it before shipping
FAIL examples/flagged.py: print() call line 10 — remove it before shipping
FAIL examples/flagged.py: pprint() call line 15 — remove it before shipping
FAIL examples/flagged.py: print() call line 16 — remove it before shipping
Checked 3 file(s), 4 leftover print call(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ printf 'print("debug")\n' | python3 src/python_print_checker.py --stdin
FAIL <stdin>: print() call line 1 — remove it before shipping
Checked 1 file(s), 1 leftover print call(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/python_print_checker.py --json examples/flagged.py
{
  "files": [
    {
      "path": "examples/flagged.py",
      "findings": [
        {
          "line": 7,
          "call": "print"
        },
        {
          "line": 10,
          "call": "print"
        },
        {
          "line": 15,
          "call": "pprint"
        },
        {
          "line": 16,
          "call": "print"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 4
}
```

Exit codes: 0 when no leftover print calls are
found, 1 when any call is found or a file cannot
be read or parsed, 2 for a usage error (a missing
path, a bad flag, or no Python files found).

## Examples

Prints inside strings and comments are not calls
— `examples/edge.py` has a print in a comment, a
print in a docstring, a print inside a string, a
method called print, and a bare mention of print,
and it passes:

```sh
$ python3 src/python_print_checker.py examples/edge.py
OK — 1 file(s) checked, no leftover print calls.
```

A file that does not parse is reported, not
skipped:

```sh
$ printf 'def broken(:\n' | python3 src/python_print_checker.py --stdin
FAIL <stdin>: cannot be parsed as Python (invalid syntax)
Checked 1 file(s), 1 leftover print call(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_python_print_checker.py
```

The tests cover flagged calls (plain prints,
prints with no arguments, prints with keyword
arguments, prints inside functions, nested
functions, async functions, lambdas, class
methods, `pprint()` imported from pprint,
`pprint.pprint()`, `builtins.print()`, several
calls in one file, findings sorted by line, a
multi-line call reported on its print line, a
print nested inside another call), lookalikes
that must pass (prints in comments, strings,
docstrings and f-strings, a method named print,
a print method definition, a bare mention of
print, print passed as an argument, a print
reached through getattr, an empty file, a file
with no prints, the word print inside another
name), file problems (a file that does not parse,
a file that is not valid UTF-8, a missing file),
the CLI (exit 0/1/2, folder walking for several
Python files, nested folders, `--no-recursive`,
`--exclude` for files and folders, `.git` skipped,
a direct file checked whatever its name,
duplicate paths checked once, `--json` output,
`--stdin` clean, flagged, and unparseable,
`--stdin` with paths refused, `--version`, a
non-UTF-8 file reported, input files left
unchanged, the tool run from another folder and
from the filesystem root, the tool run under a
fake HOME), the bundled examples (sample output
compared byte-for-byte against a fresh run, and
the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no
absolute paths, stdlib imports only, no network
use in the source, `.env` first in `.gitignore`,
CI file runs the test file, README names
flake8-print and Ruff T201).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo.
The idea of forbidding print statements is not
new — flake8-print and Ruff's T201 rule do it as
part of a linter — but no existing tool does this
one job, checking Python files for leftover
prints as a tested zero-install command-line gate,
as the search above shows — and every line of
code here is original, built on nothing but
Python's standard library.
