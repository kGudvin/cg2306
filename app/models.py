import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    blocked = "blocked"


class RequestType(str, enum.Enum):
    with_request = "with_request"
    without_request = "without_request"


class AuditAction(str, enum.Enum):
    login = "login"
    proposal_created = "proposal_created"
    proposal_updated = "proposal_updated"
    proposal_generated = "proposal_generated"
    proposal_deleted = "proposal_deleted"
    template_uploaded = "template_uploaded"
    registry_imported = "registry_imported"
    user_blocked = "user_blocked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.manager)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    proposals: Mapped[list["Proposal"]] = relationship(back_populates="user")


class AllowedEmail(Base):
    __tablename__ = "allowed_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.manager)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signer(Base):
    __tablename__ = "signers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    organization: Mapped[str] = mapped_column(String(255))
    default_signer_id: Mapped[int | None] = mapped_column(ForeignKey("signers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    default_signer: Mapped[Signer | None] = relationship()
    versions: Mapped[list["TemplateVersion"]] = relationship(back_populates="template", cascade="all, delete-orphan")


class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255))
    placeholder_schema: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    template: Mapped[Template] = relationship(back_populates="versions")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="template_version")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), index=True)
    template_version_id: Mapped[int] = mapped_column(ForeignKey("template_versions.id"), index=True)
    signer_id: Mapped[int | None] = mapped_column(ForeignKey("signers.id"), nullable=True)

    recipient_name: Mapped[str] = mapped_column(String(500))
    recipient_inn: Mapped[str | None] = mapped_column(String(32))
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    recipient_address: Mapped[str | None] = mapped_column(Text)
    recipient_uppercase: Mapped[bool] = mapped_column(Boolean, default=False)

    quote_date: Mapped[date] = mapped_column(Date, default=date.today)
    outgoing_number_middle: Mapped[str] = mapped_column(String(64), default="")
    outgoing_number: Mapped[str] = mapped_column(String(128), default="")
    request_type: Mapped[RequestType] = mapped_column(Enum(RequestType), default=RequestType.without_request)
    request_number: Mapped[str | None] = mapped_column(String(128))
    request_date: Mapped[date | None] = mapped_column(Date)

    delivery_term_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_term_unit: Mapped[str] = mapped_column(String(32), default="working_days")
    warranty_months: Mapped[int] = mapped_column(Integer, default=12)
    valid_until: Mapped[date] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    delivery_terms: Mapped[str | None] = mapped_column(Text)
    delivery_place: Mapped[str | None] = mapped_column(Text)
    intro_text: Mapped[str] = mapped_column(Text, default="")
    specification_text: Mapped[str] = mapped_column(Text, default="")

    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("22.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_amount_words: Mapped[str] = mapped_column(Text, default="")
    vat_amount_words: Mapped[str] = mapped_column(Text, default="")

    final_docx_path: Mapped[str | None] = mapped_column(Text)
    final_pdf_path: Mapped[str | None] = mapped_column(Text)
    preview_pdf_path: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    auto_delete_at: Mapped[date] = mapped_column(Date, index=True)

    user: Mapped[User] = relationship(back_populates="proposals")
    template_version: Mapped[TemplateVersion] = relationship(back_populates="proposals")
    signer: Mapped[Signer | None] = relationship()
    items: Mapped[list["ProposalItem"]] = relationship(back_populates="proposal", cascade="all, delete-orphan")


class ProposalItem(Base):
    __tablename__ = "proposal_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    registry_number: Mapped[str | None] = mapped_column(String(128))
    product_name: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32), default="шт.")
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    proposal: Mapped[Proposal] = relationship(back_populates="items")


class RegistryProduct(Base):
    __tablename__ = "registry_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_number: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(Text)
    source_file_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
