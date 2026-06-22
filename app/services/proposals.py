from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import AuditAction, AuditLog, Proposal, ProposalItem, RequestType, Template, TemplateVersion, User, UserRole
from app.schemas import ProposalIn
from app.services.document import DEFAULT_SPECIFICATION_TEXT, default_intro_text, is_auto_intro_text
from app.services.money import (
    VAT_RATE,
    add_one_calendar_month,
    amount_to_words,
    line_total,
    outgoing_number_for_date,
    vat_from_gross,
)


def latest_template_version(db: Session, template_id: int) -> TemplateVersion:
    template = db.get(Template, template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    version = db.scalar(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version.desc())
        .limit(1)
    )
    if version is None:
        raise HTTPException(status_code=400, detail="У шаблона нет загруженной версии DOCX")
    return version


def get_proposal_for_user(db: Session, proposal_id: int, user: User) -> Proposal:
    proposal = db.scalar(
        select(Proposal)
        .options(selectinload(Proposal.items), selectinload(Proposal.template_version))
        .where(Proposal.id == proposal_id)
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="КП не найдено")
    if user.role != UserRole.admin and proposal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому КП")
    return proposal


def apply_calculations(proposal: Proposal) -> None:
    total = sum((item.line_total for item in proposal.items), Decimal("0.00"))
    proposal.total_amount = total
    proposal.vat_rate = VAT_RATE
    proposal.vat_amount = vat_from_gross(total)
    proposal.total_amount_words = amount_to_words(total)
    proposal.vat_amount_words = amount_to_words(proposal.vat_amount)
    proposal.outgoing_number = outgoing_number_for_date(proposal.quote_date, proposal.outgoing_number_middle)


def fill_proposal(proposal: Proposal, data: ProposalIn, db: Session, keep_template_version: bool = False) -> Proposal:
    if not keep_template_version:
        version = latest_template_version(db, data.template_id)
        proposal.template_version_id = version.id
    proposal.template_id = data.template_id
    proposal.recipient_name = data.recipient_name.strip()
    proposal.recipient_inn = data.recipient_inn
    proposal.recipient_address = data.recipient_address
    proposal.recipient_uppercase = data.recipient_uppercase
    proposal.quote_date = data.quote_date
    proposal.outgoing_number_middle = data.outgoing_number_middle.strip()
    proposal.request_type = data.request_type
    proposal.request_number = data.request_number if data.request_type == RequestType.with_request else None
    proposal.request_date = data.request_date if data.request_type == RequestType.with_request else None
    proposal.delivery_term_value = data.delivery_term_value
    proposal.delivery_term_unit = data.delivery_term_unit
    proposal.warranty_months = data.warranty_months
    proposal.valid_until = data.valid_until or add_one_calendar_month(data.quote_date)
    proposal.payment_terms = data.payment_terms
    proposal.delivery_terms = data.delivery_terms
    proposal.delivery_place = data.delivery_place
    proposal.intro_text = default_intro_text(proposal) if is_auto_intro_text(data.intro_text, proposal) else data.intro_text
    proposal.specification_text = DEFAULT_SPECIFICATION_TEXT if data.specification_text is None else data.specification_text

    proposal.items.clear()
    for index, item in enumerate(data.items, start=1):
        proposal.items.append(
            ProposalItem(
                sort_order=index,
                name=item.name,
                unit=item.unit,
                quantity=item.quantity,
                unit_price_vat=item.unit_price_vat,
                line_total=line_total(item.quantity, item.unit_price_vat),
            )
        )
    apply_calculations(proposal)
    return proposal


def create_proposal(db: Session, user: User, data: ProposalIn) -> Proposal:
    settings = get_settings()
    proposal = Proposal(
        user_id=user.id,
        template_id=data.template_id,
        template_version_id=latest_template_version(db, data.template_id).id,
        recipient_name=data.recipient_name,
        quote_date=data.quote_date,
        valid_until=data.valid_until or add_one_calendar_month(data.quote_date),
        auto_delete_at=date.today() + timedelta(days=settings.proposal_retention_days),
    )
    fill_proposal(proposal, data, db, keep_template_version=True)
    db.add(proposal)
    db.flush()
    db.add(AuditLog(user_id=user.id, action=AuditAction.proposal_created, entity_type="proposal", entity_id=proposal.id))
    db.commit()
    db.refresh(proposal)
    return get_proposal_for_user(db, proposal.id, user)


def update_proposal(db: Session, proposal: Proposal, data: ProposalIn, user: User) -> Proposal:
    fill_proposal(proposal, data, db, keep_template_version=True)
    db.add(AuditLog(user_id=user.id, action=AuditAction.proposal_updated, entity_type="proposal", entity_id=proposal.id))
    db.commit()
    return get_proposal_for_user(db, proposal.id, user)


def duplicate_proposal(db: Session, proposal: Proposal, user: User) -> Proposal:
    today = date.today()
    clone = Proposal(
        user_id=user.id,
        template_id=proposal.template_id,
        template_version_id=proposal.template_version_id,
        recipient_name=proposal.recipient_name,
        recipient_inn=proposal.recipient_inn,
        recipient_address=proposal.recipient_address,
        recipient_uppercase=proposal.recipient_uppercase,
        quote_date=today,
        outgoing_number_middle=proposal.outgoing_number_middle,
        request_type=proposal.request_type,
        request_number=proposal.request_number,
        request_date=proposal.request_date,
        delivery_term_value=proposal.delivery_term_value,
        delivery_term_unit=proposal.delivery_term_unit,
        warranty_months=proposal.warranty_months,
        valid_until=add_one_calendar_month(today),
        payment_terms=proposal.payment_terms,
        delivery_terms=proposal.delivery_terms,
        delivery_place=proposal.delivery_place,
        intro_text=proposal.intro_text,
        specification_text=proposal.specification_text,
        auto_delete_at=today + timedelta(days=get_settings().proposal_retention_days),
    )
    for item in sorted(proposal.items, key=lambda x: x.sort_order):
        clone.items.append(
            ProposalItem(
                sort_order=item.sort_order,
                name=item.name,
                unit=item.unit,
                quantity=item.quantity,
                unit_price_vat=item.unit_price_vat,
                line_total=item.line_total,
            )
        )
    apply_calculations(clone)
    db.add(clone)
    db.flush()
    db.add(AuditLog(user_id=user.id, action=AuditAction.proposal_created, entity_type="proposal", entity_id=clone.id, details="duplicate"))
    db.commit()
    return get_proposal_for_user(db, clone.id, user)


def delete_proposal(db: Session, proposal: Proposal, user: User | None) -> None:
    for file_path in [proposal.final_docx_path, proposal.final_pdf_path, proposal.preview_pdf_path]:
        if file_path:
            path = Path(file_path)
            if path.exists():
                path.unlink()
    proposal_dir = get_settings().generated_dir / str(proposal.id)
    if proposal_dir.exists():
        for child in proposal_dir.iterdir():
            if child.is_file():
                child.unlink()
        proposal_dir.rmdir()
    proposal_id = proposal.id
    db.delete(proposal)
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=AuditAction.proposal_deleted,
            entity_type="proposal",
            entity_id=proposal_id,
            details="expired" if user is None else None,
        )
    )
    db.commit()


def delete_expired_proposals(db: Session) -> int:
    expired = db.scalars(select(Proposal).where(Proposal.auto_delete_at <= date.today())).all()
    count = 0
    for proposal in expired:
        delete_proposal(db, proposal, None)
        count += 1
    return count
