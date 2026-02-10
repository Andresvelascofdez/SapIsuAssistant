"""One-time CSV import for kanban tickets."""
import csv
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.kanban.storage.kanban_repository import KanbanRepository
from src.shared.client_manager import ClientManager


STATUS_MAP = {
    "No analizado": "NO_ANALIZADO",
    "En progreso": "EN_PROGRESO",
    "Mas info": "MAS_INFO",
    "Analizado": "ANALIZADO",
    "Analizado - Pendiente respuesta": "ANALIZADO_PENDIENTE_RESPUESTA",
    "Analizado- Pendiente respuesta": "ANALIZADO_PENDIENTE_RESPUESTA",
    "Pendiente de transporte": "PENDIENTE_DE_TRANSPORTE",
    "Testing": "TESTING",
    "Cerrado": "CERRADO",
}

PRIORITY_MAP = {
    "Alta": "HIGH",
    "Media": "MEDIUM",
    "Baja": "LOW",
    "": "MEDIUM",
}


def import_tickets_from_csv(csv_path: Path, data_root: Path) -> dict:
    """
    Import tickets from CSV into per-client kanban databases.

    Returns dict with counts per client and total.
    """
    csv_path = Path(csv_path)
    data_root = Path(data_root)
    cm = ClientManager(data_root)

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Ensure all referenced clients exist
    client_codes = set()
    for row in rows:
        code = row.get("Cliente", "").strip().upper()
        if code:
            client_codes.add(code)

    for code in sorted(client_codes):
        if not cm.get_client(code):
            cm.register_client(code, code)

    counts = {}
    for row in rows:
        code = row.get("Cliente", "").strip().upper()
        if not code:
            continue

        db_path = data_root / "clients" / code / "kanban.sqlite"
        repo = KanbanRepository(db_path, seed_columns=False)

        ticket_id = row.get("ID Tarea", "").strip() or None
        title = row.get("Nombre de tarea", "").strip()
        if not title:
            continue

        estado = row.get("Estado", "").strip()
        status = STATUS_MAP.get(estado, "EN_PROGRESO")

        prioridad = row.get("Prioridad", "").strip()
        priority = PRIORITY_MAP.get(prioridad, "MEDIUM")

        texto = row.get("Texto", "").strip()
        horas = row.get("Horas", "").strip()
        responsable = row.get("Responsable", "").strip()

        notes_parts = []
        if texto:
            notes_parts.append(texto)
        if horas:
            notes_parts.append(f"Horas: {horas}")
        if responsable:
            notes_parts.append(f"Responsable: {responsable}")
        notes = "\n".join(notes_parts) if notes_parts else None

        tags = []
        tipo = row.get("Tipo de tarea", "").strip()
        if tipo:
            # Strip emoji characters
            clean_tipo = re.sub(r"[^\w\s-]", "", tipo).strip()
            if clean_tipo:
                tags.append(clean_tipo)

        repo.create_ticket(
            title=title,
            priority=priority,
            ticket_id=ticket_id,
            notes=notes,
            tags=tags,
            status=status,
        )

        counts[code] = counts.get(code, 0) + 1

    return {"total": sum(counts.values()), "per_client": counts}
