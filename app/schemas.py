from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import RequestType, UserRole, UserStatus


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleLoginRequest(BaseModel):
    credential: str


class DevLoginRequest(BaseModel):
    email: str
    full_name: str | None = None


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
    name: str
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
    recipient_address: str | None = None
    recipient_uppercase: bool = False
    quote_date: date
    outgoing_number_middle: str = ""
    request_type: RequestType = RequestType.without_request
    request_number: str | None = None
    request_date: date | None = None
    delivery_term_value: int = Field(default=45, ge=1)
    delivery_term_unit: str = "working_days"
    warranty_months: int = Field(default=12, ge=0)
    valid_until: date | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    delivery_place: str | None = None
    intro_text: str | None = None
    specification_text: str | None = None
    items: list[ProposalItemIn] = Field(default_factory=list)


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    template_id: int
    template_version_id: int
    recipient_name: str
    recipient_inn: str | None
    recipient_address: str | None
    recipient_uppercase: bool
    quote_date: date
    outgoing_number_middle: str
    outgoing_number: str
    request_type: RequestType
    request_number: str | None
    request_date: date | None
    delivery_term_value: int
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
    pdf_url: str


class UserUpdate(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None
