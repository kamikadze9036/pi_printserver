from datetime import datetime

def mm_to_dots(mm: float, dpi: int) -> int:
    return int(round(float(mm) * int(dpi) / 25.4))

def sanitize_zpl(value: str) -> str:
    return str(value or "").replace("^", "").replace("~", "")

def resolve_variables(text: str, product: dict, username: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    values = {
        "{product_code}": product.get("product_code", ""),
        "{qr_content}": product.get("qr_content", ""),
        "{text_content}": product.get("text_content", ""),
        "{text1}": product.get("text_content", ""),
        "{text2}": product.get("text2", "") or "",
        "{text3}": product.get("text3", "") or "",
        "{text4}": product.get("text4", "") or "",
        "{date}": now.strftime("%d.%m.%Y"),
        "{time}": now.strftime("%H:%M:%S"),
        "{datetime_iso}": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "{operator}": username,
    }
    result = str(text or "")
    for key, value in values.items():
        result = result.replace(key, sanitize_zpl(value))
    return result

def set_quantity(zpl: str, quantity: int) -> str:
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    clean = zpl.replace("^XZ", "")
    return f"{clean}^PQ{quantity},0,1,Y^XZ"
