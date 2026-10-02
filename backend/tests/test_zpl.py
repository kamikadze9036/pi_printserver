from datetime import datetime

import pytest
from app.services.zpl import (
    mm_to_dots,
    render_svg,
    render_zpl,
    resolve_variables,
    sanitize_zpl,
    set_quantity,
)


def test_mm_to_dots():
    assert mm_to_dots(25.4, 203) == 203


def test_variables():
    out = resolve_variables(
        "{product_code}-{operator}-{date}",
        {"product_code": "ABC"},
        "martin",
        datetime(2026, 10, 2, 6, 30),
    )
    assert out == "ABC-martin-02.10.2026"


def test_quantity():
    out = set_quantity("^XA^FO0,0^FDTEST^FS^XZ", 40)
    assert "^PQ40,0,1,Y" in out
    assert out.endswith("^XZ")


def test_all_variables_and_one_pass_resolution():
    now = datetime(2026, 10, 2, 6, 30, 15)
    product = {
        "product_code": "{operator}",
        "qr_content": "QR",
        "text_content": "one",
        "text2": "two",
        "text3": "three",
        "text4": "four",
    }
    out = resolve_variables(
        "{product_code}|{qr_content}|{text1}|{text_content}|{text2}|{text3}|{text4}|{date}|{time}|{datetime_iso}|{operator}",
        product,
        "martin",
        now,
    )
    assert (
        out == "{operator}|QR|one|one|two|three|four|02.10.2026|06:30:15|2026-10-02T06:30:15|martin"
    )
    with pytest.raises(ValueError):
        resolve_variables("{unknown}", product, "martin", now)


@pytest.mark.parametrize("dpi", [203, 300, 600])
def test_qr_fields_safe_and_actual_size(dpi):
    template = {
        "name": "QR",
        "width_mm": 60,
        "height_mm": 40,
        "elements": [{"type": "qr", "x": 2, "y": 2, "w": 30, "h": 30, "content": "{qr_content}"}],
    }
    product = {"qr_content": "ABC^XZ~JA_<script>Český text</script>"}
    zpl = render_zpl(template, product, "user", dpi, 40)
    assert (
        zpl.count("^XZ") == 1
        and "^FH_^FDMM,B" in zpl
        and "<script>" not in zpl
        and "~JA" not in zpl
    )
    assert sanitize_zpl("^~a\x00\x1bb") == "ab"
    import re

    field = re.search(r"\^FDMM,B(\d{4})((?:_[0-9A-F]{2})+)\^FS", zpl)
    assert field
    payload = bytes.fromhex(field[2].replace("_", ""))
    assert len(payload) == int(field[1])
    assert payload.decode("utf-8") == sanitize_zpl(product["qr_content"])
    svg = render_svg(template, product, "user", dpi)
    assert "<script>" not in svg and "<path" in svg
    template["elements"][0]["w"] = 0.1
    with pytest.raises(ValueError, match="too small"):
        render_zpl(template, product, "user", dpi)


def test_quantity_replaces_existing_command():
    out = set_quantity("^XA^PQ1,0,1,Y^XZ", 40)
    assert out.count("^PQ") == 1 and "^PQ40" in out
    with pytest.raises(ValueError):
        set_quantity("^XA^XZ^XA^XZ", 1)


def test_byte_mode_capacity_even_for_numeric_qr():
    template = {
        "name": "QR",
        "width_mm": 100,
        "height_mm": 100,
        "elements": [{"type": "qr", "x": 0, "y": 0, "w": 100, "h": 100, "content": "{qr_content}"}],
    }
    with pytest.raises(ValueError, match="QR capacity"):
        render_zpl(template, {"qr_content": "1" * 3000}, "user")


def test_multiline_text_and_field_capacity():
    template = {
        "name": "Text",
        "width_mm": 60,
        "height_mm": 40,
        "elements": [{"type": "text", "x": 0, "y": 0, "w": 60, "h": 40, "content": "{text1}"}],
    }
    assert "_5C_26" in render_zpl(template, {"text_content": "line1\nline2"}, "user")
    with pytest.raises(ValueError, match="field-block limit"):
        render_zpl(template, {"text_content": "A" * 3001}, "user")
    with pytest.raises(ValueError, match="field-block limit"):
        render_zpl(template, {"text_content": "\n" * 1501}, "user")


def test_legacy_text_mode_retains_original_geometry_and_iso_value():
    from datetime import timedelta, timezone

    from app.schemas import TemplateInput
    from pydantic import ValidationError

    template = {
        "name": "Legacy32",
        "width_mm": 32,
        "height_mm": 20,
        "render_mode": "legacy",
        "elements": [
            {
                "type": "text",
                "x": 2,
                "y": 18,
                "w": 15,
                "h": 6,
                "font_size": 8,
                "content": "{datetime_iso}|{text1}",
            }
        ],
    }
    now = datetime(2026, 10, 2, 9, 30, 15, tzinfo=timezone(timedelta(hours=2)))
    zpl = render_zpl(
        template, {"text_content": "long text that should not wrap"}, "operator", 300, 40, now
    )
    assert "^FB" not in zpl and "^FO24,213" in zpl and "^A0N,33,33" in zpl
    import re

    field = re.search(r"\^FH_\^FD((?:_[0-9A-F]{2})+)\^FS", zpl)
    assert (
        bytes.fromhex(field[1].replace("_", "")).decode()
        == "2026-10-02T09:30:15|long text that should not wrap"
    )
    svg = render_svg(
        template, {"text_content": "long text that should not wrap"}, "operator", 300, now
    )
    assert "long text that should not wrap" in svg and "clipPath" not in svg
    with pytest.raises(ValidationError, match="exceeds label dimensions"):
        TemplateInput.model_validate(template | {"render_mode": "bounded"})
    template["elements"][0]["y"] = 20
    with pytest.raises(ValidationError, match="starts outside"):
        TemplateInput.model_validate(template)


def test_legacy_mode_still_rejects_qr_outside_label():
    from app.schemas import TemplateInput
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="exceeds label dimensions"):
        TemplateInput.model_validate(
            {
                "name": "Bad QR",
                "width_mm": 32,
                "height_mm": 20,
                "render_mode": "legacy",
                "elements": [{"type": "qr", "x": 30, "y": 0, "w": 10, "h": 10}],
            }
        )
