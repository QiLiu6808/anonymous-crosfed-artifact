from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "crosfed"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_has_no_framework_or_outer_layer_dependencies() -> None:
    forbidden = ("torch", "torchvision", "charm", "crosfed.ml", "crosfed.crypto",
                 "crosfed.ledger", "crosfed.orchestration", "crosfed.experiments",
                 "crosfed.integrations", "crosfed.cli")
    for path in (PACKAGE_ROOT / "domain").glob("*.py"):
        for module in imported_modules(path):
            assert not module.startswith(forbidden), f"{path.name} imports {module}"


def test_core_layers_do_not_depend_on_experiment_or_cli_layers() -> None:
    forbidden = ("crosfed.experiments", "crosfed.integrations", "crosfed.cli")
    core = ["domain", "crypto", "ml", "ledger", "metrics", "orchestration", "baselines"]
    for directory in core:
        for path in (PACKAGE_ROOT / directory).glob("*.py"):
            for module in imported_modules(path):
                assert not module.startswith(forbidden), f"{path.name} imports {module}"
