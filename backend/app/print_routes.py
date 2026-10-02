from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import admin, current_user, operator
from .catalog import required, snapshot
from .config import get_config
from .database import get_db
from .models import Printer, PrintJob, Product, Template, utcnow
from .schemas import Preview, PrintInput, ReprintInput, TemplatePreview
from .services import printing
from .services.jobs import create_job, job_dict
from .services.zpl import render_svg, render_zpl

router = APIRouter(prefix="/api")


def preview_result(template, product, user, dpi, quantity=1):
    now = utcnow().astimezone(ZoneInfo(get_config().timezone))
    try:
        return {
            "svg": render_svg(template, product, user.username, dpi, now),
            "zpl": render_zpl(template, product, user.username, dpi, quantity, now),
            "preview_note": "Text font metrics are approximate; QR data, dimensions and positions follow the renderer.",
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/preview")
def preview(data: Preview, db: Session = Depends(get_db), user=Depends(current_user)):
    product = required(db, Product, data.product_id)
    printer = required(db, Printer, data.printer_id)
    if not product.template_id:
        raise HTTPException(422, "Product has no assigned template")
    template = required(db, Template, product.template_id)
    if not product.active or not template.active or not printer.active:
        raise HTTPException(422, "Product, template and printer must be active")
    return preview_result(snapshot(template), snapshot(product), user, printer.dpi, data.quantity)


@router.post("/templates/preview")
def template_preview(data: TemplatePreview, user=Depends(current_user)):
    return preview_result(data.template.model_dump(), data.product.model_dump(), user, data.dpi)


@router.post("/templates/{ident}/preview")
def saved_template_preview(
    ident: int, data: Preview, db: Session = Depends(get_db), user=Depends(current_user)
):
    return preview_result(
        snapshot(required(db, Template, ident)),
        snapshot(required(db, Product, data.product_id)),
        user,
        required(db, Printer, data.printer_id).dpi,
        data.quantity,
    )


@router.post("/print-jobs", status_code=201)
def print_job(data: PrintInput, db: Session = Depends(get_db), user=Depends(operator)):
    return job_dict(create_job(db, user, data))


@router.get("/print-jobs")
def history(
    status: str | None = Query(None, pattern="^(queued|sent|failed)$"),
    q: str = Query("", max_length=200),
    user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    query = select(PrintJob)
    if status:
        query = query.where(PrintJob.status == status)
    if user_id is not None:
        query = query.where(PrintJob.user_id == user_id)
    if since:
        query = query.where(PrintJob.created_at >= since)
    if until:
        query = query.where(PrintJob.created_at <= until)
    if q:
        # JSON string extraction is portable to PostgreSQL and test SQLite.
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            PrintJob.product_snapshot["product_code"].as_string().ilike(pattern, escape="\\")
        )
    return [
        job_dict(obj, detail=False)
        for obj in db.scalars(
            query.order_by(PrintJob.created_at.desc(), PrintJob.id).offset(offset).limit(limit)
        )
    ]


@router.get("/print-jobs/{ident}")
def job_detail(ident: str, db: Session = Depends(get_db), user=Depends(current_user)):
    return job_dict(required(db, PrintJob, ident))


@router.post("/print-jobs/{ident}/reprint", status_code=201)
def reprint(ident: str, data: ReprintInput, db: Session = Depends(get_db), user=Depends(operator)):
    original = required(db, PrintJob, ident)
    if original.status == "queued":
        raise HTTPException(409, "Original job is still processing")
    if original.product_snapshot.get("product_code") == "PRINTER TEST":
        raise HTTPException(422, "Use the administrator printer test action")
    return job_dict(create_job(db, user, data, original=original))


@router.post("/printers/{ident}/test-connection")
def printer_connection(ident: int, db: Session = Depends(get_db), user=Depends(admin)):
    printer = required(db, Printer, ident)
    try:
        printing.test_connection(printer.host, printer.port, get_config().printer_timeout)
        return {
            "status": "reachable",
            "message": "TCP connection succeeded; physical printing is not confirmed.",
        }
    except OSError as exc:
        return {"status": "failed", "error": str(exc)}


@router.post("/printers/{ident}/test-print", status_code=201)
def printer_test(
    ident: int, data: ReprintInput, db: Session = Depends(get_db), user=Depends(admin)
):
    if data.quantity != 1 or data.printer_id is not None:
        raise HTTPException(422, "Printer test sends exactly one label to the selected printer")
    return job_dict(create_job(db, user, data, test_printer=ident))
