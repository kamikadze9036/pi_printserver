from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import admin, aware, current_user, editor, hash_password, user_dict
from .database import get_db
from .models import AuthSession, Printer, Product, Setting, Template, User
from .schemas import Duplicate, PrinterInput, ProductInput, SettingsInput, TemplateInput, UserInput

router = APIRouter(prefix="/api")


def snapshot(obj):
    if obj is None:
        return {}
    return {
        column.name: (aware(value).isoformat() if isinstance(value, datetime) else value)
        for column in obj.__table__.columns
        if column.name != "password_hash"
        for value in [getattr(obj, column.name)]
    }


def required(db, model, ident):
    obj = db.get(model, ident)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate name/code or a record is still referenced")


def save(db, model, data, ident=None):
    if model in (Product, Template):
        lock_catalog(db)
    obj = required(db, model, ident) if ident is not None else model()
    for key, value in data.items():
        setattr(obj, key, value)
    db.add(obj)
    commit(db)
    db.refresh(obj)
    return snapshot(obj)


def lock_catalog(db):
    # Share the import execution lock so a dry-run target cannot change mid-import.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7129038)"))


def product_links(db, data):
    if data.template_id:
        required(db, Template, data.template_id)
    if data.preferred_printer_id:
        required(db, Printer, data.preferred_printer_id)


@router.get("/products")
def products(
    q: str = Query(default="", max_length=200),
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    query = select(Product)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                Product.product_code.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )
    if active is not None:
        query = query.where(Product.active == active)
    return [
        snapshot(obj)
        for obj in db.scalars(query.order_by(Product.product_code).offset(offset).limit(limit))
    ]


@router.get("/products/{ident}")
def product(ident: int, db: Session = Depends(get_db), user=Depends(current_user)):
    return snapshot(required(db, Product, ident))


@router.post("/products", status_code=201)
def create_product(data: ProductInput, db: Session = Depends(get_db), user=Depends(editor)):
    product_links(db, data)
    return save(db, Product, data.model_dump())


@router.put("/products/{ident}")
def update_product(
    ident: int, data: ProductInput, db: Session = Depends(get_db), user=Depends(editor)
):
    product_links(db, data)
    return save(db, Product, data.model_dump(), ident)


@router.delete("/products/{ident}", status_code=204)
def delete_product(ident: int, db: Session = Depends(get_db), user=Depends(editor)):
    lock_catalog(db)
    db.delete(required(db, Product, ident))
    commit(db)


@router.post("/products/{ident}/duplicate", status_code=201)
def duplicate_product(
    ident: int, data: Duplicate, db: Session = Depends(get_db), user=Depends(editor)
):
    source = snapshot(required(db, Product, ident))
    values = {key: source[key] for key in ProductInput.model_fields}
    values["product_code"] = data.name
    validated = ProductInput.model_validate(values)
    return save(db, Product, validated.model_dump())


@router.get("/templates")
def templates(
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    query = select(Template)
    if active is not None:
        query = query.where(Template.active == active)
    return [
        snapshot(obj)
        for obj in db.scalars(query.order_by(Template.name).offset(offset).limit(limit))
    ]


@router.get("/templates/{ident}")
def template(ident: int, db: Session = Depends(get_db), user=Depends(current_user)):
    return snapshot(required(db, Template, ident))


@router.post("/templates", status_code=201)
def create_template(data: TemplateInput, db: Session = Depends(get_db), user=Depends(editor)):
    return save(db, Template, data.model_dump())


@router.put("/templates/{ident}")
def update_template(
    ident: int, data: TemplateInput, db: Session = Depends(get_db), user=Depends(editor)
):
    return save(db, Template, data.model_dump(), ident)


@router.delete("/templates/{ident}", status_code=204)
def delete_template(ident: int, db: Session = Depends(get_db), user=Depends(editor)):
    lock_catalog(db)
    obj = required(db, Template, ident)
    if db.scalar(select(Product.id).where(Product.template_id == ident).limit(1)):
        raise HTTPException(409, "Template is assigned to products; deactivate it instead")
    db.delete(obj)
    commit(db)


@router.post("/templates/{ident}/duplicate", status_code=201)
def duplicate_template(
    ident: int, data: Duplicate, db: Session = Depends(get_db), user=Depends(editor)
):
    source = snapshot(required(db, Template, ident))
    values = {key: source[key] for key in TemplateInput.model_fields}
    values["name"] = data.name
    return save(db, Template, values)


@router.get("/printers")
def printers(
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    query = select(Printer)
    if active is not None:
        query = query.where(Printer.active == active)
    return [
        snapshot(obj)
        for obj in db.scalars(query.order_by(Printer.name).offset(offset).limit(limit))
    ]


@router.get("/printers/{ident}")
def printer(ident: int, db: Session = Depends(get_db), user=Depends(current_user)):
    return snapshot(required(db, Printer, ident))


@router.post("/printers", status_code=201)
def create_printer(data: PrinterInput, db: Session = Depends(get_db), user=Depends(admin)):
    return save(db, Printer, data.model_dump())


@router.put("/printers/{ident}")
def update_printer(
    ident: int, data: PrinterInput, db: Session = Depends(get_db), user=Depends(admin)
):
    return save(db, Printer, data.model_dump(), ident)


@router.delete("/printers/{ident}", status_code=204)
def delete_printer(ident: int, db: Session = Depends(get_db), user=Depends(admin)):
    db.delete(required(db, Printer, ident))
    commit(db)


def lock_users(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7129037)"))


def protect_admin(db, obj, role, active):
    if obj.role == "admin" and obj.active and (role != "admin" or not active):
        others = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.active.is_(True), User.id != obj.id)
        )
        if not others:
            raise HTTPException(409, "At least one active administrator is required")


@router.get("/users")
def users(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(admin),
):
    return [
        user_dict(obj)
        for obj in db.scalars(select(User).order_by(User.username).offset(offset).limit(limit))
    ]


@router.get("/users/{ident}")
def get_user(ident: int, db: Session = Depends(get_db), user=Depends(admin)):
    return user_dict(required(db, User, ident))


@router.post("/users", status_code=201)
def create_user(data: UserInput, db: Session = Depends(get_db), user=Depends(admin)):
    if data.password is None:
        raise HTTPException(422, "Password is required for a new user")
    values = data.model_dump(exclude={"password"}) | {"password_hash": hash_password(data.password)}
    return save(db, User, values)


@router.put("/users/{ident}")
def update_user(ident: int, data: UserInput, db: Session = Depends(get_db), user=Depends(admin)):
    lock_users(db)
    obj = required(db, User, ident)
    protect_admin(db, obj, data.role, data.active)
    values = data.model_dump(exclude={"password"})
    if data.password:
        values["password_hash"] = hash_password(data.password)
    if data.password or not data.active:
        db.execute(delete(AuthSession).where(AuthSession.user_id == ident))
    return save(db, User, values, ident)


@router.delete("/users/{ident}", status_code=204)
def delete_user(ident: int, db: Session = Depends(get_db), user=Depends(admin)):
    lock_users(db)
    obj = required(db, User, ident)
    protect_admin(db, obj, "", False)
    db.delete(obj)
    commit(db)


def settings_dict(db):
    return {obj.key: obj.value for obj in db.scalars(select(Setting))}


@router.get("/settings")
def settings(db: Session = Depends(get_db), user=Depends(current_user)):
    return settings_dict(db)


@router.put("/settings")
def update_settings(data: SettingsInput, db: Session = Depends(get_db), user=Depends(admin)):
    for key, value in data.model_dump().items():
        db.merge(Setting(key=key, value=value))
    commit(db)
    return settings_dict(db)
