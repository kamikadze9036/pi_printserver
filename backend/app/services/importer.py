"""Import a user-uploaded, self-contained SQLite backup, always read-only.

No endpoint accepts a filesystem path. Legacy spooler destinations, credentials,
production orders and kiosk history are intentionally not imported.
"""

import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from sqlalchemy import select

from ..catalog import snapshot
from ..models import Product, Template
from ..schemas import ProductInput, TemplateInput
from .jobs import digest

MAX_UPLOAD = 20 * 1024 * 1024
MAX_ROWS = 10000


def read_copy(content: bytes):
    if not content.startswith(b"SQLite format 3\x00"):
        raise ValueError("Upload a standalone SQLite backup (.db/.sqlite), not a WAL or ZIP file")
    if len(content) > MAX_UPLOAD:
        raise ValueError("Maximum SQLite copy size is 20 MiB")
    with tempfile.TemporaryDirectory(prefix="pi-import-") as directory:
        path = Path(directory) / "copy.sqlite"
        path.write_bytes(content)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as source:
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only=ON")
            source.execute("PRAGMA trusted_schema=OFF")
            budget = [0]

            def limit_query():
                budget[0] += 1
                return int(budget[0] > 10000)

            source.set_progress_handler(limit_query, 1000)
            tables = {
                r["name"]
                for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"templates", "products"} <= tables:
                raise ValueError(
                    "The copy must contain printserver_win templates and products tables"
                )
            for table, expected in {
                "templates": {"id", "name", "width_mm", "height_mm", "elements"},
                "products": {"id", "product_code", "qr_content"},
            }.items():
                columns = {row["name"] for row in source.execute(f"PRAGMA table_info({table})")}
                if not expected <= columns:
                    raise ValueError(
                        f"Invalid source {table} schema; missing columns: {sorted(expected - columns)}"
                    )
            payload = {
                "templates": [],
                "products": [],
                "warnings": [
                    "Legacy users/passwords, print_log and production_orders are not imported.",
                    "Windows/TSPL printer settings are not network Zebra addresses; configure printers separately.",
                ],
            }
            ids, codes, names = set(), set(), set()
            for row in source.execute(f"SELECT * FROM templates LIMIT {MAX_ROWS + 1}"):
                if len(payload["templates"]) >= MAX_ROWS:
                    raise ValueError("Too many templates")
                row = dict(row)
                try:
                    elements = (
                        json.loads(row["elements"])
                        if isinstance(row["elements"], str)
                        else row["elements"]
                    )
                    item = TemplateInput(
                        name=row["name"],
                        width_mm=row["width_mm"],
                        height_mm=row["height_mm"],
                        elements=elements,
                        active=bool(row.get("active", True)),
                    ).model_dump()
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid legacy template {row.get('id')}: {exc}") from exc
                if row["id"] in ids or item["name"] in names:
                    raise ValueError("Duplicate template ID/name in source")
                ids.add(row["id"])
                names.add(item["name"])
                payload["templates"].append({"source_id": row["id"], "data": item})
            for row in source.execute(f"SELECT * FROM products LIMIT {MAX_ROWS + 1}"):
                if len(payload["products"]) >= MAX_ROWS:
                    raise ValueError("Too many products")
                row = dict(row)
                tid = row.get("template_id")
                if tid is not None and tid not in ids:
                    raise ValueError(
                        f"Product {row.get('product_code')} references missing source template {tid}"
                    )
                fields = {
                    k: row.get(k) or ""
                    for k in (
                        "product_code",
                        "qr_content",
                        "text_content",
                        "text2",
                        "text3",
                        "text4",
                    )
                }
                fields.update(
                    description=row.get("description") or (row.get("text_content") or "")[:500],
                    side=row.get("side") or "both",
                    active=bool(row.get("active", True)),
                    highlight_right=str(row.get("highlight_right", 0)).lower()
                    in ("1", "true", "yes", "on"),
                )
                try:
                    item = ProductInput(**fields).model_dump()
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid legacy product {row.get('product_code')}: {exc}"
                    ) from exc
                if item["product_code"] in codes:
                    raise ValueError("Duplicate normalized product code in source")
                codes.add(item["product_code"])
                if tid is None:
                    payload["warnings"].append(
                        f"Product {item['product_code']} has no template; assign one before printing."
                    )
                payload["products"].append({"source_template_id": tid, "data": item})
    return payload, hashlib.sha256(content).hexdigest()


def plan_import(db, payload):
    current_templates = {obj.name: obj for obj in db.scalars(select(Template))}
    current_products = {obj.product_code: obj for obj in db.scalars(select(Product))}
    report = {
        "templates_create": [],
        "templates_existing": [],
        "products_create": [],
        "products_skip": [],
        "warnings": list(payload["warnings"]),
        "errors": [],
    }
    relevant = []
    for entry in payload["templates"]:
        item = entry["data"]
        old = current_templates.get(item["name"])
        if old:
            relevant.append(snapshot(old))
            original = {key: getattr(old, key) for key in TemplateInput.model_fields}
            if digest(original) != digest(item):
                report["errors"].append(
                    f"Template '{item['name']}' already exists with different data. Rename it before repeating dry-run."
                )
            report["templates_existing"].append(item["name"])
        else:
            report["templates_create"].append(item["name"])
    for entry in payload["products"]:
        code = entry["data"]["product_code"]
        old = current_products.get(code)
        if old:
            relevant.append(snapshot(old))
            report["products_skip"].append(code)
        else:
            report["products_create"].append(code)
    report["target_hash"] = digest(relevant)
    return report


def execute_import(db, payload):
    mapping = {}
    for entry in payload["templates"]:
        item = entry["data"]
        template = db.scalar(select(Template).where(Template.name == item["name"]))
        if template is None:
            template = Template(**item)
            db.add(template)
            db.flush()
        mapping[entry["source_id"]] = template.id
    for entry in payload["products"]:
        item = dict(entry["data"])
        if db.scalar(select(Product.id).where(Product.product_code == item["product_code"])):
            continue
        item["template_id"] = mapping.get(entry["source_template_id"])
        db.add(Product(**item))
