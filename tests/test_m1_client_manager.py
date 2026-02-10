"""
M1 Acceptance Tests: Client Manager + Storage Layout

Tests verify strict folder/DB isolation per PLAN.md section 3.
"""
import sqlite3
from pathlib import Path

import pytest

from src.shared.client_manager import Client, ClientManager


def test_client_manager_initialization(tmp_path):
    """Test client manager initializes app.sqlite correctly."""
    data_root = tmp_path / "data"

    manager = ClientManager(data_root)

    # Verify data root created
    assert data_root.exists()
    assert data_root.is_dir()

    # Verify app.sqlite created
    app_db = data_root / "app.sqlite"
    assert app_db.exists()

    # Verify clients table exists
    with sqlite3.connect(app_db) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clients'"
        )
        assert cursor.fetchone() is not None


def test_register_client_creates_folder_structure(tmp_path):
    """Test client registration creates correct folder structure."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    # Register client
    client = manager.register_client("SWE", "Swedish Client")

    assert client.code == "SWE"
    assert client.name == "Swedish Client"
    assert client.created_at
    assert client.updated_at

    # Verify folder structure
    client_dir = data_root / "clients" / "SWE"
    assert client_dir.exists()
    assert client_dir.is_dir()

    # Verify uploads folder
    uploads_dir = client_dir / "uploads"
    assert uploads_dir.exists()
    assert uploads_dir.is_dir()

    # Verify databases created
    assistant_db = client_dir / "assistant_kb.sqlite"
    assert assistant_db.exists()

    kanban_db = client_dir / "kanban.sqlite"
    assert kanban_db.exists()


def test_register_client_normalizes_code(tmp_path):
    """Test client code is normalized to uppercase."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    client = manager.register_client("swe", "Swedish Client")
    assert client.code == "SWE"

    # Verify folder uses normalized code
    client_dir = data_root / "clients" / "SWE"
    assert client_dir.exists()


def test_register_duplicate_client_raises_error(tmp_path):
    """Test registering duplicate client code raises error."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    manager.register_client("SWE", "Swedish Client")

    with pytest.raises(ValueError, match="already exists"):
        manager.register_client("SWE", "Another Swedish Client")


def test_register_client_validates_input(tmp_path):
    """Test client registration validates input."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    with pytest.raises(ValueError, match="code cannot be empty"):
        manager.register_client("", "Name")

    with pytest.raises(ValueError, match="name cannot be empty"):
        manager.register_client("CODE", "")


def test_get_client(tmp_path):
    """Test retrieving client by code."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    manager.register_client("SWE", "Swedish Client")

    client = manager.get_client("SWE")
    assert client is not None
    assert client.code == "SWE"
    assert client.name == "Swedish Client"

    # Test case insensitive
    client2 = manager.get_client("swe")
    assert client2 is not None
    assert client2.code == "SWE"

    # Test non-existent
    client3 = manager.get_client("NONEXISTENT")
    assert client3 is None


def test_list_clients(tmp_path):
    """Test listing all clients."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    # Empty list initially
    assert manager.list_clients() == []

    # Register multiple clients
    manager.register_client("SWE", "Swedish Client")
    manager.register_client("HERON", "Heron Client")
    manager.register_client("ABC", "ABC Client")

    clients = manager.list_clients()
    assert len(clients) == 3

    # Verify sorted by code
    codes = [c.code for c in clients]
    assert codes == ["ABC", "HERON", "SWE"]


def test_get_client_dir(tmp_path):
    """Test getting client directory path."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    client_dir = manager.get_client_dir("SWE")
    expected = data_root / "clients" / "SWE"
    assert client_dir == expected

    # Test normalization
    client_dir2 = manager.get_client_dir("swe")
    assert client_dir2 == expected


def test_get_standard_dir(tmp_path):
    """Test getting standard directory."""
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    standard_dir = manager.get_standard_dir()
    expected = data_root / "standard"
    assert standard_dir == expected
    assert standard_dir.exists()

    # Verify uploads folder created
    uploads_dir = standard_dir / "uploads"
    assert uploads_dir.exists()

    # Verify assistant DB created
    assistant_db = standard_dir / "assistant_kb.sqlite"
    assert assistant_db.exists()


def test_strict_client_isolation(tmp_path):
    """
    Critical test: Verify strict physical isolation between clients.

    Each client must have completely separate:
    - Folder
    - SQLite databases
    - Uploads directory
    """
    data_root = tmp_path / "data"
    manager = ClientManager(data_root)

    # Register two clients
    manager.register_client("SWE", "Swedish Client")
    manager.register_client("HERON", "Heron Client")

    # Get directories
    swe_dir = manager.get_client_dir("SWE")
    heron_dir = manager.get_client_dir("HERON")
    standard_dir = manager.get_standard_dir()

    # Verify directories are completely separate
    assert swe_dir != heron_dir
    assert swe_dir != standard_dir
    assert heron_dir != standard_dir

    # Verify no overlap in paths
    assert not str(swe_dir).startswith(str(heron_dir))
    assert not str(heron_dir).startswith(str(swe_dir))
    assert not str(swe_dir).startswith(str(standard_dir))
    assert not str(standard_dir).startswith(str(swe_dir))

    # Verify each has its own databases
    swe_assistant_db = swe_dir / "assistant_kb.sqlite"
    swe_kanban_db = swe_dir / "kanban.sqlite"
    heron_assistant_db = heron_dir / "assistant_kb.sqlite"
    heron_kanban_db = heron_dir / "kanban.sqlite"
    standard_assistant_db = standard_dir / "assistant_kb.sqlite"

    all_dbs = [
        swe_assistant_db,
        swe_kanban_db,
        heron_assistant_db,
        heron_kanban_db,
        standard_assistant_db,
    ]

    for db in all_dbs:
        assert db.exists(), f"Database {db} should exist"

    # Verify all databases are physically different files
    db_paths = [db.resolve() for db in all_dbs]
    assert len(set(db_paths)) == len(db_paths), "All databases must be separate files"

    # Write test data to one client's DB to verify isolation
    with sqlite3.connect(swe_assistant_db) as conn:
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO test_table (data) VALUES ('SWE data')")
        conn.commit()

    # Verify other client's DB does not have this table
    with sqlite3.connect(heron_assistant_db) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'"
        )
        assert cursor.fetchone() is None, "HERON DB must not have SWE's tables"
