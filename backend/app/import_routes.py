import sqlite3
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import admin, aware
from .database import get_db
from .models import ImportRun, utcnow
from .services.importer import MAX_UPLOAD, execute_import, plan_import, read_copy

router = APIRouter(prefix="/api/import")


@router.post("/dry-run")
def dry_run(
    file: UploadFile = File(...),
    confirm_copy: bool = Form(False),
    db: Session = Depends(get_db),
    user=Depends(admin),
):
    if not confirm_copy:
        raise HTTPException(422, "Confirm that this file is an explicitly supplied database copy")
    content = file.file.read(MAX_UPLOAD + 1)
    try:
        payload, source_hash = read_copy(content)
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(422, str(exc))
    report = plan_import(db, payload)
    run = ImportRun(user_id=user.id, source_hash=source_hash, payload=payload, report=report)
    db.add(run)
    db.commit()
    return {"id": run.id, "source_hash": source_hash, "report": report, "expires_in_seconds": 3600}


@router.post("/{ident}/execute")
def execute(ident: str, db: Session = Depends(get_db), user=Depends(admin)):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7129038)"))
    run = db.scalar(select(ImportRun).where(ImportRun.id == ident).with_for_update())
    if not run or run.user_id != user.id:
        raise HTTPException(404, "Dry-run not found")
    if run.executed_at:
        return {
            "id": run.id,
            "executed_at": aware(run.executed_at).isoformat(),
            "report": run.report,
        }
    if aware(run.created_at) < utcnow() - timedelta(hours=1):
        raise HTTPException(409, "Dry-run expired; upload the copy again")
    current = plan_import(db, run.payload)
    if current["errors"]:
        raise HTTPException(
            409,
            {"message": "Resolve template conflicts before import", "errors": current["errors"]},
        )
    if current != run.report:
        raise HTTPException(409, "Target catalog changed since dry-run; repeat dry-run")
    execute_import(db, run.payload)
    run.executed_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Catalog changed during import; repeat dry-run")
    return {"id": run.id, "executed_at": aware(run.executed_at).isoformat(), "report": run.report}
