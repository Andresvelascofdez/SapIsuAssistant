"""
M0 Acceptance Test: Verify basic repo setup.
"""


def test_repo_structure():
    """Verify basic repository structure exists."""
    import os
    from pathlib import Path

    repo_root = Path(__file__).parent.parent

    # Check required files
    assert (repo_root / "pyproject.toml").exists()
    assert (repo_root / ".gitignore").exists()
    assert (repo_root / "docker-compose.yml").exists()
    assert (repo_root / ".github" / "workflows" / "ci.yml").exists()

    # Check source structure
    assert (repo_root / "src").is_dir()
    assert (repo_root / "src" / "assistant").is_dir()
    assert (repo_root / "src" / "kanban").is_dir()
    assert (repo_root / "src" / "shared").is_dir()

    # Check tests directory
    assert (repo_root / "tests").is_dir()
