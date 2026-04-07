import ast

import pytest
from packaging.requirements import Requirement

from tests.conftest import install_package, run_command, run_python_code, temporary_venv


CLI_MODULES = [
    "osint_suite.main",
    "osint_suite.telegram_bot",
    "osint_suite.username_search",
    "osint_suite.email_osint",
    "osint_suite.phone_investigator",
    "osint_suite.social_analyzer",
    "osint_suite.image_metadata",
    "osint_suite.document_analyzer",
    "osint_suite.geolocation_helper",
    "osint_suite.breach_checker",
    "osint_suite.company_research",
]

OPERATIONAL_DOCS = [
    ("codex/status.md", ["Current Status", "Active Loop", "Next Queue"]),
    ("codex/error_handling.md", ["Error Handling", "Severity", "Recovery"]),
    ("codex/quality_gates.md", ["Quality Gates", "Required Checks", "Do Not Claim Success"]),
    ("codex/module_protocol.md", ["Module Protocol", "Ownership", "Handoff"]),
]

GITIGNORE_ENTRIES = [
    ".env",
    ".vscode/",
    ".pytest_cache/",
    "build/",
    "*.egg-info/",
    "__pycache__/",
    "*.py[cod]",
]


def load_runtime_requirements(repo_root):
    return {
        normalize_requirement(line.strip())
        for line in (repo_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def normalize_requirement(requirement_string):
    requirement = Requirement(requirement_string)
    return f"{requirement.name.lower()}{requirement.specifier}"


def load_declared_console_scripts(repo_root):
    setup_contents = (repo_root / "setup.py").read_text(encoding="utf-8")
    setup_ast = ast.parse(setup_contents)

    for node in ast.walk(setup_ast):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "setup":
            continue

        for keyword in node.keywords:
            if keyword.arg != "entry_points" or not isinstance(keyword.value, ast.Dict):
                continue

            for key_node, value_node in zip(keyword.value.keys, keyword.value.values):
                if not isinstance(key_node, ast.Constant) or key_node.value != "console_scripts":
                    continue
                if not isinstance(value_node, ast.List):
                    continue

                return {
                    entry.value.split("=", 1)[0]: entry.value.split("=", 1)[1]
                    for entry in value_node.elts
                    if isinstance(entry, ast.Constant) and isinstance(entry.value, str)
                }

    raise AssertionError("setup.py does not declare console_scripts entry points")


def test_setup_py_name_command_succeeds(repo_root):
    result = run_command(["python", "setup.py", "--name"], cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "osint-suite"


def test_help_tools_output_uses_expected_spanish_accents(repo_root):
    result = run_command(["python", "-m", "osint_suite.main", "--help-tools"], cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert "Teléfonos" in result.stdout
    assert "Investigación de Empresas" in result.stdout


def test_cursorrules_loads_autonomous_mode_documents(repo_root):
    contents = (repo_root / ".cursorrules").read_text(encoding="utf-8")

    assert "codex/intelligence/autonomous_loop.md" in contents
    assert "codex/intelligence/project_scanner.md" in contents
    assert "codex/intelligence/task_planner.md" in contents
    assert "codex/intelligence/executor.md" in contents


def test_docs_do_not_reference_missing_readme_file(repo_root):
    for relative_path in ("README.md", "SUITE_SUMMARY.md"):
        contents = (repo_root / relative_path).read_text(encoding="utf-8")
        assert "README_OSINT_SUITE.md" not in contents, relative_path


def test_routing_rules_do_not_contain_mojibake(repo_root):
    contents = (repo_root / "codex" / "routing_rules.md").read_text(encoding="utf-8")

    assert "Ã¢â€ â€™" not in contents
    assert "API / server logic → backend" in contents
    assert "UI / UX → frontend" in contents
    assert "Database / storage → data" in contents
    assert "Deployment / docker / CI → infra" in contents
    assert "Automation / AI / workflows → agents" in contents


@pytest.mark.parametrize("module_name", CLI_MODULES)
def test_cli_entrypoints_respond_to_help(repo_root, module_name):
    result = run_command(["python", "-m", module_name, "--help"], cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize(("relative_path", "required_phrases"), OPERATIONAL_DOCS)
def test_codex_operational_docs_have_minimum_content(repo_root, relative_path, required_phrases):
    contents = (repo_root / relative_path).read_text(encoding="utf-8")

    assert contents.strip(), relative_path
    for phrase in required_phrases:
        assert phrase in contents, f"{relative_path} missing {phrase!r}"


def test_setup_script_exists_and_bootstraps_codex_files(repo_root):
    setup_script = repo_root / "setup-cursor-system.sh"
    contents = setup_script.read_text(encoding="utf-8")

    assert setup_script.exists()
    assert "codex/status.md" in contents
    assert "codex/error_handling.md" in contents
    assert "codex/quality_gates.md" in contents
    assert "codex/module_protocol.md" in contents
    assert "codex/intelligence/project_scanner.md" in contents


def test_gitignore_covers_local_generated_artifacts(repo_root):
    gitignore_path = repo_root / ".gitignore"
    contents = gitignore_path.read_text(encoding="utf-8")

    assert gitignore_path.exists()
    for entry in GITIGNORE_ENTRIES:
        assert entry in contents


def test_repo_does_not_track_python_bytecode(repo_root):
    result = run_command(["git", "ls-files", "osint_suite/__pycache__"], cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_requirements_files_separate_runtime_and_dev_dependencies(repo_root):
    runtime_requirements = {
        line.strip()
        for line in (repo_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    dev_requirements = {
        line.strip()
        for line in (repo_root / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert (repo_root / "requirements-dev.txt").exists()
    assert "pytest>=7.0.0" not in runtime_requirements
    assert "black>=22.0.0" not in runtime_requirements
    assert "flake8>=4.0.0" not in runtime_requirements
    assert "pytest>=7.0.0" in dev_requirements
    assert "black>=22.0.0" in dev_requirements
    assert "flake8>=4.0.0" in dev_requirements


def test_setup_py_uses_package_version_as_single_source_of_truth(repo_root):
    setup_contents = (repo_root / "setup.py").read_text(encoding="utf-8")

    assert 'from osint_suite import __version__' in setup_contents
    assert "version=__version__" in setup_contents
    assert 'version="1.0.0"' not in setup_contents


def test_setup_py_declares_python_compatibility_consistent_with_telegram_dependency(repo_root):
    setup_contents = (repo_root / "setup.py").read_text(encoding="utf-8")

    assert 'python_requires=">=3.9"' in setup_contents
    assert '"Programming Language :: Python :: 3.9"' in setup_contents
    assert '"Programming Language :: Python :: 3.10"' in setup_contents
    assert '"Programming Language :: Python :: 3.11"' in setup_contents
    assert '"Programming Language :: Python :: 3.7"' not in setup_contents
    assert '"Programming Language :: Python :: 3.8"' not in setup_contents


@pytest.mark.parametrize("editable", [True, False], ids=["editable", "non_editable"])
def test_package_install_exposes_expected_package_metadata(repo_root, editable):
    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=editable)
        assert install_result.returncode == 0, install_result.stderr

        metadata_check = """
from importlib import metadata
import osint_suite

distribution = metadata.distribution("osint-suite")
assert distribution.version == osint_suite.__version__
assert metadata.version("osint-suite") == osint_suite.__version__
print("ok")
"""
        metadata_result = run_python_code(python_bin, metadata_check, cwd=repo_root)
        assert metadata_result.returncode == 0, metadata_result.stderr
        assert metadata_result.stdout.strip() == "ok"


def test_editable_install_exposes_expected_console_scripts_and_runtime_deps(repo_root):
    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=True)
        assert install_result.returncode == 0, install_result.stderr

        import_check = """
import osint_suite

assert osint_suite.__name__ == "osint_suite"
print("ok")
"""
        import_result = run_python_code(python_bin, import_check, cwd=repo_root)
        assert import_result.returncode == 0, import_result.stderr
        assert import_result.stdout.strip() == "ok"

        check = """
from importlib import metadata
import osint_suite
 
distribution = metadata.distribution("osint-suite")
console_scripts = {
    entry.name: entry.value
    for entry in distribution.entry_points
    if entry.group == "console_scripts"
}
requirements = {req.lower() for req in metadata.requires("osint-suite") or []}

assert osint_suite.__version__ == "1.0.0"
assert distribution.version == osint_suite.__version__
assert console_scripts["osint-suite"] == "osint_suite.main:main"
assert console_scripts["osint-username"] == "osint_suite.username_search:main"
assert console_scripts["osint-company"] == "osint_suite.company_research:main"
for forbidden in ("pytest", "black", "flake8"):
    assert not any(req.startswith(forbidden) for req in requirements), requirements
print("ok")
"""
        result = run_python_code(python_bin, check, cwd=repo_root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"


def test_editable_install_registers_declared_console_scripts_in_entry_points(repo_root):
    declared_console_scripts = load_declared_console_scripts(repo_root)

    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=True)
        assert install_result.returncode == 0, install_result.stderr

        registration_check = f"""
from importlib import metadata

declared_console_scripts = {declared_console_scripts!r}
distribution = metadata.distribution("osint-suite")
distribution_console_scripts = {{
    entry.name: entry.value
    for entry in distribution.entry_points
    if entry.group == "console_scripts"
}}

all_console_scripts = metadata.entry_points()
if hasattr(all_console_scripts, "select"):
    registered_console_scripts = {{
        entry.name: entry.value
        for entry in all_console_scripts.select(group="console_scripts")
    }}
else:
    registered_console_scripts = {{
        entry.name: entry.value
        for entry in all_console_scripts.get("console_scripts", [])
    }}

for name, value in declared_console_scripts.items():
    assert distribution_console_scripts[name] == value
    assert registered_console_scripts[name] == value

print("ok")
"""
        result = run_python_code(python_bin, registration_check, cwd=repo_root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"


@pytest.mark.parametrize("editable", [True, False], ids=["editable", "non_editable"])
def test_installed_runtime_requirements_match_requirements_txt(repo_root, editable):
    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=editable)
        assert install_result.returncode == 0, install_result.stderr

        metadata_check = """
from importlib import metadata

requirements = sorted(req.lower() for req in metadata.requires("osint-suite") or [])
print("\\n".join(requirements))
"""
        result = run_python_code(python_bin, metadata_check, cwd=repo_root)
        assert result.returncode == 0, result.stderr

        installed_requirements = {
            normalize_requirement(line.strip())
            for line in result.stdout.splitlines()
            if line.strip()
        }
        assert installed_requirements == load_runtime_requirements(repo_root)


def test_non_editable_install_exposes_expected_console_scripts(repo_root):
    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=False)
        assert install_result.returncode == 0, install_result.stderr

        entrypoint_check = """
from importlib import metadata

distribution = metadata.distribution("osint-suite")
console_scripts = {
    entry.name: entry.value
    for entry in distribution.entry_points
    if entry.group == "console_scripts"
}

assert console_scripts["osint-suite"] == "osint_suite.main:main"
assert console_scripts["osint-email"] == "osint_suite.email_osint:main"
assert console_scripts["osint-geo"] == "osint_suite.geolocation_helper:main"
print("ok")
"""
        entrypoint_result = run_python_code(python_bin, entrypoint_check, cwd=repo_root)
        assert entrypoint_result.returncode == 0, entrypoint_result.stderr
        assert entrypoint_result.stdout.strip() == "ok"


@pytest.mark.parametrize("editable", [True, False], ids=["editable", "non_editable"])
def test_telegram_bot_check_config_smoke_after_install(repo_root, editable):
    with temporary_venv() as python_bin:
        install_result = install_package(python_bin, repo_root, editable=editable)
        assert install_result.returncode == 0, install_result.stderr
        requirements_install = run_command(
            [str(python_bin), "-m", "pip", "install", "-r", str(repo_root / "requirements.txt")],
            cwd=repo_root,
        )
        assert requirements_install.returncode == 0, requirements_install.stderr

        check_config = """
import os
import subprocess
import sys

env = os.environ.copy()
env["TELEGRAM_BOT_TOKEN"] = "dummy-token"
result = subprocess.run(
    [sys.executable, "-m", "osint_suite.telegram_bot", "--check-config"],
    capture_output=True,
    text=True,
    env=env,
)
assert result.returncode == 0, result.stderr
assert "Telegram bot configuration OK" in result.stdout
print("ok")
"""
        result = run_python_code(python_bin, check_config, cwd=repo_root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"


def test_install_script_supports_optional_dev_dependencies(repo_root):
    install_contents = (repo_root / "install.py").read_text(encoding="utf-8")

    assert "requirements-dev.txt" in install_contents
    assert "--dev" in install_contents
