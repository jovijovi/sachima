"""The canonical shell must run tests and propagate a failing test's status."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest


@pytest.mark.platforms("posix")
def test_shell_runner_executes_tests_and_propagates_failure(tmp_path):
    case = tmp_path / "test_runner_canary.py"
    marker = tmp_path / "executed"
    case.write_text(
        "from pathlib import Path\nimport os\n"
        "def test_canary():\n"
        f"    Path({str(marker)!r}).write_text('executed')\n"
        "    assert os.environ['PATHEXT'] == '.COM;.EXE;.BAT;.CMD'\n"
        "    assert False, 'runner failure propagation canary'\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", str(root / "scripts/run_tests.sh"), "-j", "1", str(case)],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
        env={**os.environ, "HERMES_PYTHON": sys.executable, "HERMES_TEST_FILE_RETRIES": "0",
             "PATHEXT": ".COM;.EXE;.BAT;.CMD"},
             check=False,
    )
    assert marker.read_text(encoding="utf-8") == "executed", result.stdout + result.stderr
    assert result.returncode != 0, result.stdout + result.stderr
    assert "runner failure propagation canary" in result.stdout + result.stderr


@pytest.mark.platforms("posix")
def test_shell_runner_forwards_the_scratch_root_opt_in(tmp_path):
    """HERMES_TEST_SCRATCH_ROOT survives the shell's env -i; a TMPDIR given to it still does not."""
    case = tmp_path / "test_scratch_canary.py"
    record = tmp_path / "record.json"
    case.write_text(
        "import json, tempfile\nfrom pathlib import Path\n"
        "def test_canary(tmp_path):\n"
        f"    Path({str(record)!r}).write_text(json.dumps([tempfile.gettempdir(), str(tmp_path)]))\n",
        encoding="utf-8",
    )
    scratch, given = tmp_path / "rt", tmp_path / "given-tmpdir"
    given.mkdir()
    root = Path(__file__).resolve().parents[2]
    # No cache: pytest roots this out-of-tree file at its common ancestor with the checkout.
    result = subprocess.run(
        ["bash", str(root / "scripts/run_tests.sh"), "-j", "1", str(case), "-p", "no:cacheprovider"],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
        env={**os.environ, "HERMES_PYTHON": sys.executable, "HERMES_TEST_FILE_RETRIES": "0",
             "HERMES_TEST_SCRATCH_ROOT": str(scratch), "TMPDIR": str(given)},
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    tmpdir, test_tmp_path = json.loads(record.read_text(encoding="utf-8"))
    assert Path(tmpdir).parent == scratch, result.stdout
    assert Path(test_tmp_path).resolve().is_relative_to(Path(tmpdir).resolve())
    assert not any(given.iterdir()) and not list(scratch.glob("r-*"))
