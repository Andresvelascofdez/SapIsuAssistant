"""
Client manager: handles client registration, data directory layout, and active client state.
"""
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional


@dataclass
class Client:
    """Client entity."""
    code: str
    name: str
    created_at: str
    updated_at: str


class ClientManager:
    """Manages client registration and ensures strict folder/DB isolation."""

    def __init__(self, data_root: Path):
        """
        Initialize client manager.

        Args:
            data_root: Root data directory (e.g., ./data/)
        """
        self.data_root = Path(data_root)
        self.app_db_path = self.data_root / "app.sqlite"

        # Ensure data root exists
        self.data_root.mkdir(parents=True, exist_ok=True)

        # Initialize app DB
        self._init_app_db()

    def _init_app_db(self):
        """Initialize app.sqlite with clients table."""
        with sqlite3.connect(self.app_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def register_client(self, code: str, name: str) -> Client:
        """
        Register a new client and create its folder structure.

        Args:
            code: Client code (e.g., "SWE", "HERON")
            name: Client display name

        Returns:
            Client entity

        Raises:
            ValueError: If client code already exists
        """
        code = code.upper().strip()
        name = name.strip()

        if not code:
            raise ValueError("Client code cannot be empty")
        if not name:
            raise ValueError("Client name cannot be empty")

        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.app_db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO clients (code, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (code, name, now, now)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Client with code '{code}' already exists")

        # Create client folder structure
        self._create_client_folders(code)

        return Client(code=code, name=name, created_at=now, updated_at=now)

    def _create_client_folders(self, code: str):
        """
        Create folder structure for a client.

        Structure:
        data/clients/<CLIENT_CODE>/
          assistant_kb.sqlite
          uploads/
          kanban.sqlite
        """
        client_dir = self.get_client_dir(code)
        client_dir.mkdir(parents=True, exist_ok=True)

        uploads_dir = client_dir / "uploads"
        uploads_dir.mkdir(exist_ok=True)

        # Create empty SQLite files (will be initialized by respective modules)
        assistant_db = client_dir / "assistant_kb.sqlite"
        kanban_db = client_dir / "kanban.sqlite"

        for db_path in [assistant_db, kanban_db]:
            if not db_path.exists():
                # Create empty database file
                with sqlite3.connect(db_path):
                    pass

    def get_client(self, code: str) -> Optional[Client]:
        """
        Retrieve client by code.

        Args:
            code: Client code

        Returns:
            Client entity or None if not found
        """
        code = code.upper().strip()

        with sqlite3.connect(self.app_db_path) as conn:
            row = conn.execute(
                "SELECT code, name, created_at, updated_at FROM clients WHERE code = ?",
                (code,)
            ).fetchone()

            if row:
                return Client(code=row[0], name=row[1], created_at=row[2], updated_at=row[3])

        return None

    def list_clients(self) -> list[Client]:
        """List all registered clients."""
        with sqlite3.connect(self.app_db_path) as conn:
            rows = conn.execute(
                "SELECT code, name, created_at, updated_at FROM clients ORDER BY code"
            ).fetchall()

            return [Client(code=r[0], name=r[1], created_at=r[2], updated_at=r[3]) for r in rows]

    def get_client_dir(self, code: str) -> Path:
        """
        Get the data directory for a specific client.

        Args:
            code: Client code

        Returns:
            Path to client directory
        """
        return self.data_root / "clients" / code.upper()

    def get_standard_dir(self) -> Path:
        """
        Get the standard (non-client) data directory.

        Returns:
            Path to standard directory
        """
        standard_dir = self.data_root / "standard"
        standard_dir.mkdir(parents=True, exist_ok=True)

        uploads_dir = standard_dir / "uploads"
        uploads_dir.mkdir(exist_ok=True)

        # Ensure standard assistant DB exists
        assistant_db = standard_dir / "assistant_kb.sqlite"
        if not assistant_db.exists():
            with sqlite3.connect(assistant_db):
                pass

        return standard_dir
