"""Independent Zebra renderer based on printserver_win millimetres/font sizing.

Field bytes use ^FH so product text cannot become printer commands. QR sizing uses
the encoded version, including its quiet zone, instead of assuming 21 modules.
"""

import html
import math
import re
from datetime import datetime, timezone

import qrcode
from qrcode.exceptions import DataOverflowError
from qrcode.util import MODE_8BIT_BYTE, QRData

from ..schemas import VARIABLES, TemplateInput


def mm_to_dots(mm: float, dpi: int) -> int:
    if not math.isfinite(mm) or mm < 0 or dpi not in (203, 300, 600):
        raise ValueError("Invalid millimetres or DPI")
    return int(round(float(mm) * dpi / 25.4))


def sanitize_zpl(value: str) -> str:
    return "".join(c for c in str(value or "") if c not in "^~" and (ord(c) >= 32 or c == "\n"))


def resolve_variables(text: str, product: dict, username: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    values = {key: product.get(key, "") or "" for key in VARIABLES}
    values.update(
        text1=product.get("text_content", "") or "",
        operator=username,
        date=now.strftime("%d.%m.%Y"),
        time=now.strftime("%H:%M:%S"),
        datetime_iso=now.isoformat(timespec="seconds"),
    )

    def replacement(match):
        key = match.group(1)
        if key not in values:
            raise ValueError(f"Unknown variable: {key}")
        return sanitize_zpl(values[key])

    # One pass: braces in product fields remain literal.
    return sanitize_zpl(re.sub(r"\{([^{}]+)\}", replacement, text or ""))


def encode_field(value):
    return "".join(f"_{byte:02X}" for byte in sanitize_zpl(value).encode("utf-8"))


def set_quantity(zpl: str, quantity: int) -> str:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99999:
        raise ValueError("quantity must be an integer between 1 and 99999")
    if zpl.count("^XA") != 1 or zpl.count("^XZ") != 1:
        raise ValueError("Expected one complete label")
    clean = re.sub(r"\^PQ[^\^]*", "", zpl).replace("^XZ", "").rstrip()
    return f"{clean}\r\n^PQ{quantity},0,1,Y\r\n^XZ"


def layout(template, product, username, dpi, now):
    template = TemplateInput.model_validate(
        {k: template[k] for k in ("name", "width_mm", "height_mm", "elements")}
    )
    result = []
    for element in template.elements:
        value = resolve_variables(
            element.content or ("{qr_content}" if element.type == "qr" else ""),
            product,
            username,
            now,
        )
        item = element.model_dump() | {
            "resolved": value,
            "xd": mm_to_dots(element.x, dpi),
            "yd": mm_to_dots(element.y, dpi),
        }
        if element.type == "qr":
            if not value:
                raise ValueError("QR content cannot be empty")
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, mask_pattern=7
            )
            qr.add_data(QRData(value.encode("utf-8"), mode=MODE_8BIT_BYTE), optimize=0)
            try:
                qr.make(fit=True)
            except (DataOverflowError, ValueError) as exc:
                raise ValueError("QR content exceeds QR capacity") from exc
            matrix = qr.get_matrix()
            available = min(mm_to_dots(element.w, dpi), mm_to_dots(element.h, dpi))
            mag = min(10, available // len(matrix))
            if mag < 1:
                raise ValueError(f"QR element {element.name} is too small for its content")
            item.update(matrix=matrix, magnification=mag)
        else:
            if len(value.encode("utf-8")) > 3000:
                raise ValueError("Text field exceeds the Zebra field-block limit of 3000 bytes")
            font = max(20, int(element.font_size * dpi / 25.4 * 0.35))
            height, width = mm_to_dots(element.h, dpi), mm_to_dots(element.w, dpi)
            if font > height:
                raise ValueError(f"Text element {element.name} height is smaller than its font")
            item.update(
                font=font,
                wd=width,
                hd=height,
                lines=max(1, height // font),
                reverse=bool(product.get("highlight_right"))
                and product.get("side") == "R"
                and any(
                    "{" + token + "}" in element.content
                    for token in ("text_content", "text1", "text2", "text3", "text4")
                ),
            )
        result.append(item)
    return template, result


def render_zpl(
    template: dict,
    product: dict,
    username: str,
    dpi: int = 203,
    quantity: int = 1,
    now: datetime | None = None,
) -> str:
    template, elements = layout(template, product, username, dpi, now or datetime.now(timezone.utc))
    lines = [
        "^XA",
        "^CI28",
        "^MMT",
        f"^PW{mm_to_dots(template.width_mm, dpi)}",
        f"^LL{mm_to_dots(template.height_mm, dpi)}",
        "^LH0,0",
    ]
    for item in elements:
        x, y = item["xd"], item["yd"]
        if item["type"] == "qr":
            mag = item["magnification"]
            lines += [
                f"^FO{x + 4 * mag},{y + 4 * mag}",
                f"^BQN,2,{mag},M,7",
                # Manual byte mode accepts every UTF-8 byte. Zebra automatic mode
                # excludes some 0x80..0xFF values and can reinterpret the payload.
                f"^FH_^FDMM,B{len(item['resolved'].encode('utf-8')):04d}{encode_field(item['resolved'])}^FS",
            ]
        else:
            if item["reverse"]:
                lines += [f"^FO{x},{y}", f"^GB{item['wd']},{item['hd']},{item['hd']},B,0^FS"]
            text_data = item["resolved"].replace("\n", "\\&")
            lines += [
                f"^FO{x},{y}",
                "^FR" if item["reverse"] else "",
                f"^A0N,{item['font']},{item['font']}",
                f"^FB{item['wd']},{item['lines']},0,L,0",
                f"^FH_^FD{encode_field(text_data)}^FS",
            ]
    return set_quantity("\r\n".join(lines) + "\r\n^XZ", quantity)


def render_svg(
    template: dict, product: dict, username: str, dpi: int = 203, now: datetime | None = None
) -> str:
    template, elements = layout(template, product, username, dpi, now or datetime.now(timezone.utc))
    width, height = mm_to_dots(template.width_mm, dpi), mm_to_dots(template.height_mm, dpi)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Label preview">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]
    for index, item in enumerate(elements):
        x, y = item["xd"], item["yd"]
        if item["type"] == "qr":
            mag = item["magnification"]
            commands = [
                f"M{x + col * mag} {y + row * mag}h{mag}v{mag}h-{mag}z"
                for row, line in enumerate(item["matrix"])
                for col, on in enumerate(line)
                if on
            ]
            svg.append(f'<path d="{" ".join(commands)}" fill="black"/>')
        else:
            color = "white" if item["reverse"] else "black"
            if item["reverse"]:
                svg.append(
                    f'<rect x="{x}" y="{y}" width="{item["wd"]}" height="{item["hd"]}" fill="black"/>'
                )
            svg.append(
                f'<clipPath id="t{index}"><rect x="{x}" y="{y}" width="{item["wd"]}" height="{item["hd"]}"/></clipPath>'
            )
            # Font 0 metrics vary by printer; browser text preview is approximate.
            line = 0
            chars = max(1, int(item["wd"] / (item["font"] * 0.6)))
            for raw in item["resolved"].splitlines() or [""]:
                for start in range(0, max(1, len(raw)), chars):
                    if line < item["lines"]:
                        svg.append(
                            f'<text x="{x}" y="{y + item["font"] * (line + 0.8)}" font-family="Arial,sans-serif" font-size="{item["font"]}" fill="{color}" clip-path="url(#t{index})">{html.escape(raw[start : start + chars])}</text>'
                        )
                    line += 1
    return "".join(svg) + "</svg>"
