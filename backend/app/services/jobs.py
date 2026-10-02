import hashlib
import json
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import user_dict
from ..catalog import settings_dict, snapshot
from ..config import get_config
from ..models import Printer, PrintJob, Product, Template, utcnow
from . import printing
from .zpl import render_zpl

logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def job_dict(job, detail=True):
    data = snapshot(job)
    data.pop("request_hash", None)
    data.pop("idempotency_key", None)
    if not detail:
        data.pop("zpl", None)
    data["delivery_message"] = (
        "Data sent to printer endpoint; physical label output is not confirmed."
        if job.status == "sent"
        else "No automatic retry. Check printer before reprinting."
        if job.status == "failed"
        else "Processing; do not submit a new request."
    )
    return data


def existing_job(db, user_id, key, fingerprint):
    job = db.scalar(
        select(PrintJob).where(PrintJob.user_id == user_id, PrintJob.idempotency_key == key)
    )
    if job and job.request_hash != fingerprint:
        raise HTTPException(409, "Idempotency key was already used for different parameters")
    return job


TEST_TEMPLATE = {
    "name": "Printer test 60x40",
    "width_mm": 60,
    "height_mm": 40,
    "elements": [
        {"type": "qr", "x": 2, "y": 2, "w": 20, "h": 20, "content": "{qr_content}"},
        {"type": "text", "x": 24, "y": 2, "w": 34, "h": 8, "content": "{product_code}"},
        {"type": "text", "x": 2, "y": 28, "w": 56, "h": 8, "content": "{date} {time}"},
    ],
}


def create_job(db: Session, user, data, original=None, test_printer=None):
    kind = "test" if test_printer is not None else "reprint" if original is not None else "print"
    fingerprint = digest(
        {
            "kind": kind,
            "original": original.id if original else None,
            "test_printer": test_printer,
            "input": data.model_dump(exclude={"idempotency_key"}),
        }
    )
    prior = existing_job(db, user.id, data.idempotency_key, fingerprint)
    if prior:
        return prior
    now = utcnow()
    job = PrintJob(
        user_id=user.id,
        user_snapshot=user_dict(user),
        quantity=data.quantity,
        reason=data.reason,
        note=data.note,
        reference=data.reference,
        original_job_id=original.id if original else None,
        idempotency_key=data.idempotency_key,
        request_hash=fingerprint,
        created_at=now,
        product_snapshot={},
        template_snapshot={},
        printer_snapshot={},
        status="queued",
    )
    error = None
    printer_id = (
        test_printer
        if test_printer is not None
        else (
            data.printer_id or original.printer_snapshot.get("id") if original else data.printer_id
        )
    )
    printer = db.get(Printer, printer_id) if printer_id else None
    job.printer_snapshot = snapshot(printer) or {"id": printer_id}
    if test_printer is not None:
        job.product_snapshot = {
            "product_code": "PRINTER TEST",
            "qr_content": "pi_printserver",
            "active": True,
        }
        job.template_snapshot = TEST_TEMPLATE | {"active": True}
    else:
        product_id = original.product_snapshot.get("id") if original else data.product_id
        product = db.get(Product, product_id) if product_id else None
        template = (
            db.get(Template, product.template_id) if product and product.template_id else None
        )
        # Reprints use the original immutable label data; current records still control availability.
        job.product_snapshot = (
            original.product_snapshot if original else (snapshot(product) or {"id": product_id})
        )
        job.template_snapshot = original.template_snapshot if original else snapshot(template)
        if not product or not product.active:
            error = "Product is missing or inactive"
        elif original and not original.zpl:
            error = "Original job had no valid label; create a new print request after fixing the product"
        elif original and not db.get(Template, original.template_snapshot.get("id")):
            error = "Original template no longer exists"
        elif not original and (not template or not template.active):
            error = "Assigned template is missing or inactive"
        elif original and not db.get(Template, original.template_snapshot.get("id")).active:
            error = "Original template is inactive"
    settings = settings_dict(db)
    if not printer or not printer.active or printer.protocol != "zpl":
        error = error or "Printer is missing, inactive or does not support ZPL"
    if data.quantity > settings["max_quantity"]:
        error = error or f"Quantity exceeds maximum {settings['max_quantity']}"
    if test_printer is None:
        if not data.reason and settings["reason_required"]:
            error = error or "Print reason is required"
        elif data.reason and data.reason not in settings["reasons"]:
            error = error or "Select a configured print reason"
    if error is None:
        try:
            job.zpl = render_zpl(
                job.template_snapshot,
                job.product_snapshot,
                user.username,
                printer.dpi,
                data.quantity,
                now.astimezone(ZoneInfo(get_config().timezone)),
            )
            job.zpl_hash = hashlib.sha256(job.zpl.encode("utf-8")).hexdigest()
        except ValueError as exc:
            error = str(exc)
    if error:
        job.status, job.error, job.finished_at = "failed", error, utcnow()
    db.add(job)
    try:
        db.commit()  # Durable audit and unique key before any network I/O.
    except IntegrityError:
        db.rollback()
        prior = existing_job(db, user.id, data.idempotency_key, fingerprint)
        if prior:
            return prior
        raise
    if error:
        logger.warning("Print job %s rejected: %s", job.id, error)
        return job
    ident = job.id
    # End the read transaction; immutable snapshots alone determine the send.
    destination, zpl = dict(job.printer_snapshot), job.zpl
    try:
        printing.send_zpl(
            destination["host"], zpl, destination["port"], get_config().printer_timeout
        )
        status, error = "sent", None
    except (OSError, ValueError) as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        logger.warning("Print job %s failed: %s", ident, error)
    db.execute(
        update(PrintJob)
        .where(PrintJob.id == ident, PrintJob.status == "queued")
        .values(status=status, error=error, finished_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.refresh(job)
    return job


def recover_stale_jobs(db):
    # Never resend after a crash: TCP may already have delivered some/all bytes.
    before = utcnow() - timedelta(minutes=5)
    db.execute(
        update(PrintJob)
        .where(PrintJob.status == "queued", PrintJob.created_at < before)
        .values(
            status="failed",
            finished_at=utcnow(),
            error="Interrupted or timed out; delivery is uncertain. Check printer before reprinting.",
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
