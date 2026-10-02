import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import COOKIE, current_user, login_user, user_dict
from .bootstrap import bootstrap
from .catalog import router as catalog_router
from .config import get_config
from .database import get_db, get_engine
from .import_routes import router as import_router
from .print_routes import router as print_router
from .schemas import Login
from .services.jobs import recover_stale_jobs

logging.basicConfig(level=logging.INFO)


def recover():
    with Session(get_engine()) as db:
        recover_stale_jobs(db)


async def recovery_loop():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(recover)
        except Exception:
            logging.getLogger(__name__).exception("Failed to recover stale print jobs")


@asynccontextmanager
async def lifespan(app):
    get_config()  # Validate secrets, timezone and limits before accepting requests.
    await asyncio.to_thread(bootstrap)
    await asyncio.to_thread(recover)
    task = asyncio.create_task(recovery_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="pi_printserver", version="1.0.0", lifespan=lifespan)
app.include_router(catalog_router)
app.include_router(print_router)
app.include_router(import_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(RequestValidationError)
async def input_errors(request, exc):
    # Avoid echoing submitted passwords, upload bytes or untrusted exception contexts.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
            ]
        },
    )


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "pi_printserver"}


@app.post("/api/auth/login")
def login(data: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    return login_user(data, request, response, db)


@app.get("/api/auth/me")
def me(request: Request, user=Depends(current_user)):
    return {"user": user_dict(user), "csrf_token": request.state.session.csrf_token}


@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request, response: Response, db: Session = Depends(get_db), user=Depends(current_user)
):
    db.delete(request.state.session)
    db.commit()
    response.delete_cookie(
        COOKIE, path="/api", secure=get_config().cookie_secure, httponly=True, samesite="strict"
    )
