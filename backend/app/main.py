from fastapi import FastAPI
from .services.zpl import mm_to_dots

app = FastAPI(title="pi_printserver", version="0.1.0")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "pi_printserver"}

@app.get("/api/info")
def info():
    return {
        "printing": "ZPL over RAW TCP",
        "default_port": 9100,
        "example_10mm_at_203dpi": mm_to_dots(10, 203),
    }
