from datetime import datetime
from app.services.zpl import mm_to_dots, resolve_variables, set_quantity

def test_mm_to_dots():
    assert mm_to_dots(25.4, 203) == 203

def test_variables():
    out = resolve_variables("{product_code}-{operator}-{date}", {"product_code":"ABC"}, "martin", datetime(2026,10,2,6,30))
    assert out == "ABC-martin-02.10.2026"

def test_quantity():
    out = set_quantity("^XA^FO0,0^FDTEST^FS^XZ", 40)
    assert "^PQ40,0,1,Y" in out
    assert out.endswith("^XZ")
