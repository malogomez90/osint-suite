import subprocess
import sys
import tempfile
import venv
from contextlib import contextmanager
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root():
    return Path(__file__).resolve().parents[1]


def run_command(args, cwd):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@contextmanager
def temporary_venv():
    with tempfile.TemporaryDirectory() as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(venv_dir)

        if sys.platform == "win32":
            python_bin = venv_dir / "Scripts" / "python.exe"
        else:
            python_bin = venv_dir / "bin" / "python"

        yield python_bin


def install_package(python_bin, repo_root, editable):
    command = [str(python_bin), "-m", "pip", "install", "--no-deps"]
    if editable:
        command.append("-e")
    command.append(str(repo_root))
    return run_command(command, cwd=repo_root)


def run_python_code(python_bin, code, cwd):
    return run_command([str(python_bin), "-c", code], cwd=cwd)
