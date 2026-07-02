from datetime import date, datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import RequestType, UserRole, UserStatus


def is_valid_inn(value: str) -> bool:
    if not re.fullmatch(r"\d{10}|\d{12}", value):
        return False
    digits = [int(char) for char in value]
    if len(digits) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(weight * digit for weight, digit in zip(weights, digits[:9])) % 11 % 10
        return checksum == digits[9]
    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    checksum_11 = sum(weight * digit for weight, digit in zip(weights_11, digits[:10])) % 11 % 10
    checksum_12 = sum(weight * digit for weight, digit in zip(weights_12, digits[:11])) % 11 % 10
    return checksum_11 == digits[10] and checksum_12 == digits[11]


def is_valid_email(value: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None
    role: UserRole
    status: UserStatus


class AllowedEmailIn(BaseModel):
    email: str
    role: UserRole = UserRole.manager
    is_active: bool = True


class AllowedEmailRead(AllowedEmailIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class TemplateRead(BaseModel):
    id: int
    name: str
    organization: str
    is_active: bool
    latest_version_id: int | None = None


class ProposalItemIn(BaseModel):
    name: str = ""
    registry_number: str | None = None
    product_name: str | None = None
    display_name: str | None = None
    unit: str = "шт."
    quantity: int = Field(ge=1)
    unit_price_vat: Decimal = Field(ge=0)


class ProposalItemRead(ProposalItemIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int
    line_total: Decimal


class ProposalIn(BaseModel):
    template_id: int
    recipient_name: str
    recipient_inn: str | None = None
    recipient_email: str | None = None
    recipient_address: str | None = None
    recipient_uppercase: bool = False
    quote_date: date
    outgoing_number_middle: str = ""
    request_type: RequestType = RequestType.without_request
    request_number: str | None = None
    request_date: date | None = None
    delivery_term_value: int | None = Field(default=None, ge=1)
    delivery_term_unit: str = "working_days"
    warranty_months: int = Field(default=12, ge=0)
    valid_until: date | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    delivery_place: str | None = None
    intro_text: str | None = None
    specification_text: str | None = None
    items: list[ProposalItemIn] = Field(default_factory=list)

    @field_validator("recipient_inn", "recipient_email", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("recipient_inn")
    @classmethod
    def validate_recipient_inn(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_inn(value):
            raise ValueError("ИНН должен состоять из 10 или 12 цифр и проходить проверку контрольной суммы")
        return value

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_email(value):
            raise ValueError("Укажите корректный email адресата")
        return value


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    template_id: int
    template_version_id: int
    recipient_name: str
    recipient_inn: str | None
    recipient_email: str | None
    recipient_address: str | None
    recipient_uppercase: bool
    quote_date: date
    outgoing_number_middle: str
    outgoing_number: str
    request_type: RequestType
    request_number: str | None
    request_date: date | None
    delivery_term_value: int | None
    delivery_term_unit: str
    warranty_months: int
    valid_until: date
    payment_terms: str | None
    delivery_terms: str | None
    delivery_place: str | None
    intro_text: str
    specification_text: str
    total_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_amount_words: str
    vat_amount_words: str
    final_docx_path: str | None
    final_pdf_path: str | None
    preview_pdf_path: str | None
    created_at: datetime
    updated_at: datetime
    auto_delete_at: date
    delete_warning: bool = False
    items: list[ProposalItemRead]


class GenerateResponse(BaseModel):
    proposal_id: int
    docx_url: str | None = None
    docx_filename: str | None = None
    pdf_url: str
    pdf_filename: str | None = None


class RegistryProductRead(BaseModel):
    registry_number: str
    name: str
    display_name: str


class RegistryImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None
