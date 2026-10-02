import ipaddress
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

VARIABLES = {
    "product_code",
    "qr_content",
    "text_content",
    "text1",
    "text2",
    "text3",
    "text4",
    "date",
    "time",
    "datetime_iso",
    "operator",
}
Role = Literal["admin", "engineer", "team_leader", "viewer"]
Password = Annotated[str, StringConstraints(strip_whitespace=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Login(Input):
    username: str = Field(min_length=1, max_length=80)
    password: Password = Field(min_length=1, max_length=256)


class UserInput(Input):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(default="", max_length=160)
    role: Role = "team_leader"
    active: bool = True
    password: Password | None = Field(default=None, min_length=12, max_length=256)


class Element(Input):
    type: Literal["text", "qr"]
    name: str = Field(default="", max_length=160)
    x: float = Field(default=0, ge=0, le=500)
    y: float = Field(default=0, ge=0, le=500)
    w: float = Field(default=20, gt=0, le=500)
    h: float = Field(default=6, gt=0, le=500)
    font_size: float = Field(default=8, gt=0, le=100)
    content: str = Field(default="", max_length=4000)

    @field_validator("content")
    @classmethod
    def variables(cls, value):
        tokens = re.findall(r"\{([^{}]*)\}", value)
        unknown = set(tokens) - VARIABLES
        if unknown or value.count("{") != len(tokens) or value.count("}") != len(tokens):
            raise ValueError("Unknown or malformed variable: " + ", ".join(sorted(unknown)))
        return value


class TemplateInput(Input):
    name: str = Field(min_length=1, max_length=160)
    width_mm: float = Field(gt=0, le=500)
    height_mm: float = Field(gt=0, le=500)
    elements: list[Element] = Field(min_length=1, max_length=100)
    render_mode: Literal["bounded", "legacy"] = "bounded"
    active: bool = True

    @model_validator(mode="after")
    def bounds(self):
        for element in self.elements:
            if self.render_mode == "legacy" and element.type == "text":
                # The source ZPL generator never used a text element's w/h.
                # Preserve its data; only its origin must be on the label.
                if element.x >= self.width_mm or element.y >= self.height_mm:
                    raise ValueError(
                        f"Element {element.name or element.type} starts outside label dimensions"
                    )
                continue
            if (
                element.x + element.w > self.width_mm + 0.001
                or element.y + element.h > self.height_mm + 0.001
            ):
                raise ValueError(f"Element {element.name or element.type} exceeds label dimensions")
        return self


class ProductInput(Input):
    product_code: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    qr_content: str = Field(default="", max_length=4000)
    text_content: str = Field(default="", max_length=4000)
    text2: str = Field(default="", max_length=4000)
    text3: str = Field(default="", max_length=4000)
    text4: str = Field(default="", max_length=4000)
    side: Literal["L", "R", "both"] = "both"
    highlight_right: bool = False
    template_id: int | None = Field(default=None, gt=0)
    preferred_printer_id: int | None = Field(default=None, gt=0)
    active: bool = True

    @field_validator("product_code")
    @classmethod
    def normalize(cls, value):
        return value.upper()


class PrinterInput(Input):
    name: str = Field(min_length=1, max_length=160)
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9100, ge=1, le=65535, strict=True)
    protocol: Literal["zpl"] = "zpl"
    dpi: Literal[203, 300, 600] = 203
    active: bool = True
    location: str = Field(default="", max_length=200)
    side: str = Field(default="", max_length=32)
    group: str = Field(default="", max_length=80)

    @field_validator("host")
    @classmethod
    def hostname(cls, value):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", part)
                for part in value.rstrip(".").split(".")
            ):
                raise ValueError("Use a hostname or IP address, without URL or port")
        return value


class Duplicate(Input):
    name: str = Field(min_length=1, max_length=120)


class PrintInput(Input):
    product_id: int = Field(gt=0, strict=True)
    printer_id: int = Field(gt=0, strict=True)
    quantity: int = Field(default=1, ge=1, le=99999, strict=True)
    reason: str = Field(max_length=200)
    note: str = Field(default="", max_length=4000)
    reference: str = Field(default="", max_length=200)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class ReprintInput(Input):
    printer_id: int | None = Field(default=None, gt=0, strict=True)
    quantity: int = Field(default=1, ge=1, le=99999, strict=True)
    reason: str = Field(max_length=200)
    note: str = Field(default="", max_length=4000)
    reference: str = Field(default="", max_length=200)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class Preview(Input):
    product_id: int = Field(gt=0)
    printer_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=99999, strict=True)


class TemplatePreview(Input):
    template: TemplateInput
    product: ProductInput
    dpi: Literal[203, 300, 600] = 203


class SettingsInput(Input):
    default_quantity: int = Field(ge=1, le=99999, strict=True)
    max_quantity: int = Field(ge=1, le=99999, strict=True)
    reason_required: bool
    reasons: list[str] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def settings(self):
        if self.default_quantity > self.max_quantity:
            raise ValueError("Default quantity exceeds maximum")
        if len(set(self.reasons)) != len(self.reasons) or any(
            not r.strip() or len(r) > 200 for r in self.reasons
        ):
            raise ValueError("Reasons must be unique nonempty strings, at most 200 characters")
        self.reasons = [r.strip() for r in self.reasons]
        return self
