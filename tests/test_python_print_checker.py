#!/usr/bin/env python3
"""Tests for python_print_checker — stdlib unittest only."""

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import python_print_checker as checker

REPO = Path(__file__).resolve().parent.parent


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestPrintCallsFlagged(unittest.TestCase):
    def test_plain_print_flagged(self):
        self.assertEqual(findings_of('print("hello")'),
                         [{"line": 1, "call": "print"}])

    def test_print_with_no_args_flagged(self):
        self.assertEqual(findings_of("print()"),
                         [{"line": 1, "call": "print"}])

    def test_print_with_kwargs_flagged(self):
        self.assertEqual(findings_of('print("x", end="")'),
                         [{"line": 1, "call": "print"}])

    def test_print_inside_function_flagged(self):
        text = "def run():\n    print('debug')\n"
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "print"}])

    def test_print_inside_nested_function_flagged(self):
        text = ("def outer():\n"
                "    def inner():\n"
                "        print('deep')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 3, "call": "print"}])

    def test_print_inside_async_function_flagged(self):
        text = ("async def fetch():\n"
                "    print('fetching')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "print"}])

    def test_print_inside_lambda_flagged(self):
        self.assertEqual(findings_of("show = lambda x: print(x)"),
                         [{"line": 1, "call": "print"}])

    def test_print_inside_class_method_flagged(self):
        text = ("class Worker:\n"
                "    def run(self):\n"
                "        print('running')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 3, "call": "print"}])

    def test_pprint_call_flagged(self):
        text = ("from pprint import pprint\n"
                "pprint({'a': 1})\n")
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "pprint"}])

    def test_pprint_module_call_flagged(self):
        text = ("import pprint\n"
                "pprint.pprint({'a': 1})\n")
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "pprint"}])

    def test_builtins_print_flagged(self):
        text = ("import builtins\n"
                "builtins.print('hello')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "print"}])

    def test_multiple_calls_all_reported(self):
        text = ("print('one')\n"
                "x = 1\n"
                "print('two')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 1, "call": "print"},
                          {"line": 3, "call": "print"}])

    def test_findings_sorted_by_line(self):
        # ast.walk visits breadth-first, so a top-level
        # call can surface before a deeper one above it.
        text = ("def f():\n"
                "    print('deep')\n"
                "print('top')\n")
        self.assertEqual(findings_of(text),
                         [{"line": 2, "call": "print"},
                          {"line": 3, "call": "print"}])

    def test_multiline_call_line_is_the_print_line(self):
        text = ("print(\n"
                "    'hello',\n"
                ")\n")
        self.assertEqual(findings_of(text),
                         [{"line": 1, "call": "print"}])

    def test_print_as_argument_flagged(self):
        self.assertEqual(findings_of("log(print('x'))"),
                         [{"line": 1, "call": "print"}])


class TestLookalikesPass(unittest.TestCase):
    def test_print_in_comment_passes(self):
        self.assertEqual(findings_of("# print('hello')\n"), [])

    def test_print_in_string_passes(self):
        self.assertEqual(
            findings_of("message = \"print('hello')\"\n"), [])

    def test_print_in_docstring_passes(self):
        text = ("def f():\n"
                "    \"\"\"Call print('hello') to say hello.\"\"\"\n"
                "    return 1\n")
        self.assertEqual(findings_of(text), [])

    def test_print_in_fstring_passes(self):
        text = "text = f\"print('hello')\"\n"
        self.assertEqual(findings_of(text), [])

    def test_method_named_print_passes(self):
        text = ("logger.print('hello')\n")
        self.assertEqual(findings_of(text), [])

    def test_print_method_definition_passes(self):
        text = ("class Logger:\n"
                "    def print(self, message):\n"
                "        pass\n")
        self.assertEqual(findings_of(text), [])

    def test_bare_reference_passes(self):
        self.assertEqual(findings_of("printer = print\n"), [])

    def test_print_passed_as_argument_passes(self):
        self.assertEqual(findings_of("run(print)\n"), [])

    def test_getattr_print_passes(self):
        self.assertEqual(
            findings_of("getattr(x, 'print')()\n"), [])

    def test_empty_file_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_file_without_prints_passes(self):
        self.assertEqual(findings_of("x = 1\ny = x + 2\n"), [])

    def test_word_print_in_name_passes(self):
        self.assertEqual(findings_of("printer = 1\n"), [])
        self.assertEqual(findings_of("my_print = 1\n"), [])


class TestCheckFile(unittest.TestCase):
    def test_syntax_error_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.py", "def broken(:\n")
            bad, error = checker.check_file(path)
            self.assertEqual(bad, [])
            self.assertIn("cannot be parsed", error)

    def test_non_utf8_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.py", b"\xff\xfe\n")
            bad, error = checker.check_file(path)
            self.assertEqual(bad, [])
            self.assertIn("UTF-8", error)

    def test_missing_file_is_an_error(self):
        bad, error = checker.check_file("/nonexistent/missing.py")
        self.assertEqual(bad, [])
        self.assertTrue(error)


class TestCLI(unittest.TestCase):
    def test_clean_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "clean.py", "x = 1\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK —", out)

    def test_flagged_file_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "flagged.py", "print('x')\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("FAIL", out)
            self.assertIn("print() call line 1", out)
            self.assertIn("1 leftover print call(s)", out)

    def test_syntax_error_file_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.py", "def broken(:\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("cannot be parsed", out)

    def test_no_paths_is_usage_error(self):
        code, _out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("give at least one", err)

    def test_missing_path_is_usage_error(self):
        code, _out, err = run_cli(["no-such-file.py"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no Python files found", err)

    def test_bad_flag_is_usage_error(self):
        code, _out, _err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_folder_walk_finds_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.py", "print('a')\n")
            write(tmp, "b.py", "x = 1\n")
            write(tmp, "notes.txt", "print('not python')\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("a.py", out)
            self.assertNotIn("notes.txt", out)
            self.assertIn("Checked 2 file(s)", out)

    def test_nested_folders_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "sub/deep.py", "print('deep')\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("deep.py", out)

    def test_no_recursive_stops_at_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "top.py", "x = 1\n")
            write(tmp, "sub/deep.py", "print('deep')\n")
            code, out, _err = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_exclude_pattern_skips_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "keep.py", "x = 1\n")
            write(tmp, "skip.py", "print('x')\n")
            code, out, _err = run_cli(["--exclude", "*skip.py", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_exclude_pattern_skips_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "keep.py", "x = 1\n")
            write(tmp, "vendor/bad.py", "print('x')\n")
            code, out, _err = run_cli(["--exclude", "vendor", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_never_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".git/hooks/sample.py", "print('hook')\n")
            write(tmp, "app.py", "x = 1\n")
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "script.txt", "print('x')\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("print() call line 1", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.py", "print('x')\n")
            code, out, _err = run_cli([path, path])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.py", "print('x')\n")
            code, out, _err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["findings"],
                             [{"line": 1, "call": "print"}])
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("x = 1\n")
            code, out, _err = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("OK —", out)

    def test_stdin_flagged(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("print('x')\n")
            code, out, _err = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: print() call line 1", out)

    def test_stdin_syntax_error(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("def broken(:\n")
            code, out, _err = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("cannot be parsed", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _out, err = run_cli(["--stdin", "a.py"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("python_print_checker 1.0.0", out)

    def test_non_utf8_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.py", b"\xff\xfe\n")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.py", "print('x')\n")
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.py", "print('x')\n")
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src/python_print_checker.py"),
                 path],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("print() call line 1", result.stdout)

    def test_cli_runs_from_filesystem_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.py", "x = 1\n")
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src/python_print_checker.py"),
                 path],
                cwd="/", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("OK —", result.stdout)

    def test_cli_runs_under_fake_home(self):
        # A test that only passes because a local path exists
        # is not a passing test: HOME must not matter.
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = str(Path(tmp) / "fakehome")
            os.makedirs(fake_home)
            path = write(tmp, "a.py", "print('x')\n")
            env = dict(os.environ, HOME=fake_home)
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src/python_print_checker.py"),
                 path],
                cwd=tmp, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1)
            self.assertIn("print() call line 1", result.stdout)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/python_print_checker.py",
             "examples/clean.py"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/python_print_checker.py",
             "examples/flagged.py"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/python_print_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 4 leftover print call(s) "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 4 leftover print call(s) "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/python_print_checker.py",
             "examples/edge.py"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/python_print_checker.py",
             "--json", "examples/flagged.py"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\", "/tmp/"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/python_print_checker.py",
                       REPO / "tests/test_python_print_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"python_print_checker"},
                (target.name, imported))

    def test_no_network_use_in_src(self):
        src = (REPO / "src/python_print_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_python_print_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_flake8_print_and_ruff(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("flake8-print", readme)
        self.assertIn("121 stars", readme)
        self.assertIn("Ruff", readme)
        self.assertIn("T201", readme)


if __name__ == "__main__":
    unittest.main()
