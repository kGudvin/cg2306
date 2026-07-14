from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import AllowedEmail, AuditAction, AuditLog, Proposal, RegistryProduct, Signer, Template, TemplateVersion, User, UserRole, UserStatus
from app.schemas import (
    AllowedEmailIn,
    AllowedEmailRead,
    GenerateResponse,
    LoginRequest,
    OrganizationLookupRead,
    ProposalIn,
    ProposalRead,
    RegisterRequest,
    RegistryImportResult,
    RegistryProductRead,
    SignerIn,
    SignerRead,
    TemplateRead,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from app.security import create_access_token, get_current_user, hash_password, login_with_password, register_user, require_admin
from app.services.document import generate_files, generate_preview
from app.services.organizations import OrganizationLookupError, OrganizationNotFoundError, find_organization_by_inn
from app.services.proposals import (
    create_proposal,
    delete_expired_proposals,
    delete_proposal,
    duplicate_proposal,
    get_proposal_for_user,
    update_proposal,
)
from app.services.registry import display_name_for_registry_product, import_registry_products
from app.template_seed import (
    create_demo_beshtau_template,
    prepare_beshtau_template_from_source,
    prepare_kartas_template_from_source,
    prepare_nitrino_template_from_source,
)

settings = get_settings()
app = FastAPI(title=settings.app_name)


def apply_schema_compatibility() -> None:
    inspector = inspect(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'pending'"))
    if inspector.has_table("users"):
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "password_hash" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
    if inspector.has_table("proposals"):
        proposal_columns = {column["name"] for column in inspector.get_columns("proposals")}
        if "recipient_email" not in proposal_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE proposals ADD COLUMN recipient_email VARCHAR(255)"))
        if "signer_id" not in proposal_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE proposals ADD COLUMN signer_id INTEGER"))
    if inspector.has_table("templates"):
        template_columns = {column["name"] for column in inspector.get_columns("templates")}
        if "default_signer_id" not in template_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE templates ADD COLUMN default_signer_id INTEGER"))
    if inspector.has_table("proposal_items"):
        item_columns = {column["name"] for column in inspector.get_columns("proposal_items")}
        with engine.begin() as connection:
            if "registry_number" not in item_columns:
                connection.execute(text("ALTER TABLE proposal_items ADD COLUMN registry_number VARCHAR(128)"))
            if "product_name" not in item_columns:
                connection.execute(text("ALTER TABLE proposal_items ADD COLUMN product_name TEXT"))
            if "display_name" not in item_columns:
                connection.execute(text("ALTER TABLE proposal_items ADD COLUMN display_name TEXT"))
    if engine.dialect.name == "sqlite" and inspector.has_table("proposals"):
        proposal_columns = inspector.get_columns("proposals")
        proposal_indexes = inspector.get_indexes("proposals")
        delivery_column = next((column for column in proposal_columns if column["name"] == "delivery_term_value"), None)
        if delivery_column and not delivery_column.get("nullable", True):
            with engine.begin() as connection:
                connection.execute(text("PRAGMA foreign_keys=OFF"))
                for index in proposal_indexes:
                    connection.execute(text(f"DROP INDEX IF EXISTS {index['name']}"))
                connection.execute(text("ALTER TABLE proposals RENAME TO proposals_old"))
                Proposal.__table__.create(bind=connection)
                new_columns = {column.name for column in Proposal.__table__.columns}
                old_columns = {column["name"] for column in proposal_columns}
                copy_columns = [column for column in Proposal.__table__.columns.keys() if column in old_columns and column in new_columns]
                column_sql = ", ".join(copy_columns)
                connection.execute(text(f"INSERT INTO proposals ({column_sql}) SELECT {column_sql} FROM proposals_old"))
                connection.execute(text("DROP TABLE proposals_old"))
                connection.execute(text("PRAGMA foreign_keys=ON"))
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE IF EXISTS proposals ALTER COLUMN delivery_term_value DROP NOT NULL"))


def proposal_read(proposal: Proposal) -> ProposalRead:
    data = ProposalRead.model_validate(proposal)
    data.delete_warning = proposal.auto_delete_at <= date.today() + timedelta(days=settings.deletion_warning_days)
    return data


def seed_initial_data(db: Session) -> None:
    email = settings.seed_admin_email.strip().lower()
    if email and db.scalar(select(AllowedEmail).where(AllowedEmail.email == email)) is None:
        db.add(AllowedEmail(email=email, role=UserRole.admin, is_active=True))
    if email and db.scalar(select(User).where(User.email == email)) is None:
        db.add(
            User(
                email=email,
                password_hash=hash_password(settings.seed_admin_password),
                role=UserRole.admin,
                status=UserStatus.active,
            )
        )

    signer = db.scalar(select(Signer).where(Signer.name == "В.А. Кузнецов"))
    if signer is None:
        signer = Signer(title="Генеральный директор", name="В.А. Кузнецов", is_active=True)
        db.add(signer)
        db.flush()

    template = db.scalar(select(Template).where(Template.name == "КП ООО «Бештау Электроникс»"))
    if template is None:
        template = Template(
            name="КП ООО «Бештау Электроникс»",
            organization="ООО «Бештау Электроникс»",
            default_signer_id=signer.id,
        )
        db.add(template)
        db.flush()
    elif template.default_signer_id != signer.id:
        template.default_signer_id = signer.id
    version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template.id))
    if version is None:
        path = settings.templates_dir / "beshtau_prepared_v1.docx"
        if settings.beshtau_source_template_path.exists():
            create_from = settings.beshtau_source_template_path
            prepare_beshtau_template_from_source(create_from, path)
            original = create_from.name
        else:
            create_demo_beshtau_template(path)
            original = "beshtau_demo_v1.docx"
        db.add(
            TemplateVersion(
                template_id=template.id,
                version=1,
                file_path=str(path),
                original_filename=original,
                placeholder_schema="builtin-beshtau-v1",
            )
        )
    elif settings.beshtau_source_template_path.exists() and Path(version.file_path).name == "beshtau_prepared_v1.docx":
        prepare_beshtau_template_from_source(settings.beshtau_source_template_path, Path(version.file_path))
    elif version.placeholder_schema == "builtin-beshtau-v1" and Path(version.file_path).exists():
        create_demo_beshtau_template(Path(version.file_path))

    kartas_template = db.scalar(select(Template).where(Template.name == "КП ООО «КАРТАС»"))
    if kartas_template is None:
        kartas_template = Template(name="КП ООО «КАРТАС»", organization="ООО «КАРТАС»")
        db.add(kartas_template)
        db.flush()
    kartas_version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == kartas_template.id))
    if kartas_version is None and settings.kartas_source_template_path.exists():
        kartas_path = settings.templates_dir / "kartas_prepared_v1.docx"
        prepare_kartas_template_from_source(settings.kartas_source_template_path, kartas_path)
        db.add(
            TemplateVersion(
                template_id=kartas_template.id,
                version=1,
                file_path=str(kartas_path),
                original_filename=settings.kartas_source_template_path.name,
                placeholder_schema="builtin-kartas-v1",
            )
        )
    elif (
        kartas_version is not None
        and settings.kartas_source_template_path.exists()
        and Path(kartas_version.file_path).name == "kartas_prepared_v1.docx"
    ):
        prepare_kartas_template_from_source(settings.kartas_source_template_path, Path(kartas_version.file_path))

    nitrino_signer = db.scalar(select(Signer).where(Signer.name == "Тюрин Д. А."))
    if nitrino_signer is None:
        nitrino_signer = Signer(title="Директор НЬЮ АЙ ТИ", name="Тюрин Д. А.", is_active=True)
        db.add(nitrino_signer)
        db.flush()
    nitrino_template = db.scalar(select(Template).where(Template.name == "НИТРИНО"))
    if nitrino_template is None:
        nitrino_template = Template(
            name="НИТРИНО",
            organization="НИТРИНО",
            default_signer_id=nitrino_signer.id,
        )
        db.add(nitrino_template)
        db.flush()
    elif nitrino_template.default_signer_id is None:
        nitrino_template.default_signer_id = nitrino_signer.id
    nitrino_version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == nitrino_template.id))
    if nitrino_version is None and settings.nitrino_source_template_path.exists():
        nitrino_path = settings.templates_dir / "nitrino_prepared_v1.docx"
        prepare_nitrino_template_from_source(settings.nitrino_source_template_path, nitrino_path)
        db.add(
            TemplateVersion(
                template_id=nitrino_template.id,
                version=1,
                file_path=str(nitrino_path),
                original_filename=settings.nitrino_source_template_path.name,
                placeholder_schema="builtin-nitrino-v1",
            )
        )
    elif (
        nitrino_version is not None
        and settings.nitrino_source_template_path.exists()
        and Path(nitrino_version.file_path).name == "nitrino_prepared_v1.docx"
    ):
        prepare_nitrino_template_from_source(settings.nitrino_source_template_path, Path(nitrino_version.file_path))
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    apply_schema_compatibility()
    with SessionLocal() as db:
        seed_initial_data(db)
        delete_expired_proposals(db)


@app.post("/api/auth/register", response_model=UserRead, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload.email, payload.password, payload.full_name)


@app.post("/api/auth/login", response_model=TokenResponse)
def password_login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = login_with_password(db, payload.email, payload.password)
    return TokenResponse(access_token=create_access_token(user))


@app.get("/api/config")
def public_config() -> dict[str, str | bool]:
    return {"password_login_enabled": True, "registration_enabled": True}


@app.get("/api/auth/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@app.get("/api/organizations/by-inn/{inn}", response_model=OrganizationLookupRead)
def organization_by_inn(inn: str, user: User = Depends(get_current_user)) -> OrganizationLookupRead:
    try:
        result = find_organization_by_inn(inn, settings.dadata_api_token, settings.dadata_timeout_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrganizationLookupError as exc:
        status_code = 503 if not settings.dadata_api_token else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return OrganizationLookupRead(**result)


@app.get("/api/templates", response_model=list[TemplateRead])
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[TemplateRead]:
    templates = db.scalars(select(Template).where(Template.is_active.is_(True)).options(selectinload(Template.versions))).all()
    result = []
    for template in templates:
        latest = max(template.versions, key=lambda x: x.version, default=None)
        result.append(
            TemplateRead(
                id=template.id,
                name=template.name,
                organization=template.organization,
                is_active=template.is_active,
                default_signer_id=template.default_signer_id,
                latest_version_id=latest.id if latest else None,
            )
        )
    return result


@app.get("/api/signers", response_model=list[SignerRead])
def list_signers(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Signer]:
    return db.scalars(select(Signer).where(Signer.is_active.is_(True)).order_by(Signer.name)).all()


@app.post("/api/admin/templates", response_model=TemplateRead)
def upload_template(
    name: str = Form(...),
    organization: str = Form(...),
    default_signer_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplateRead:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Можно загрузить только DOCX")
    if default_signer_id is not None and db.get(Signer, default_signer_id) is None:
        raise HTTPException(status_code=404, detail="Подписант не найден")
    template = Template(name=name, organization=organization, default_signer_id=default_signer_id)
    db.add(template)
    db.flush()
    path = settings.templates_dir / f"template_{template.id}_v1.docx"
    with path.open("wb") as output:
        output.write(file.file.read())
    version = TemplateVersion(template_id=template.id, version=1, file_path=str(path), original_filename=file.filename)
    db.add(version)
    db.add(AuditLog(user_id=user.id, action=AuditAction.template_uploaded, entity_type="template", entity_id=template.id))
    db.commit()
    return TemplateRead(
        id=template.id,
        name=template.name,
        organization=template.organization,
        is_active=True,
        default_signer_id=template.default_signer_id,
        latest_version_id=version.id,
    )


@app.post("/api/admin/registry-products/import", response_model=RegistryImportResult)
def import_registry_products_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> RegistryImportResult:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Можно загрузить только XLSX")
    stats = import_registry_products(db, file.file.read(), file.filename)
    db.add(AuditLog(user_id=user.id, action=AuditAction.registry_imported, entity_type="registry_products", details=file.filename))
    db.commit()
    return RegistryImportResult(created=stats.created, updated=stats.updated, skipped=stats.skipped, errors=stats.errors)


@app.get("/api/registry-products/by-number/{registry_number}", response_model=RegistryProductRead)
def get_registry_product_by_number(
    registry_number: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RegistryProductRead:
    normalized = registry_number.strip()
    product = db.scalar(select(RegistryProduct).where(RegistryProduct.registry_number == normalized))
    if product is None:
        raise HTTPException(status_code=404, detail="Реестровый номер не найден")
    return RegistryProductRead(
        registry_number=product.registry_number,
        name=product.name,
        display_name=display_name_for_registry_product(product.name, product.registry_number),
    )


@app.get("/api/proposals", response_model=list[ProposalRead])
def list_proposals(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ProposalRead]:
    query = select(Proposal).options(selectinload(Proposal.items), selectinload(Proposal.signer)).order_by(Proposal.updated_at.desc())
    if user.role != UserRole.admin:
        query = query.where(Proposal.user_id == user.id)
    return [proposal_read(item) for item in db.scalars(query).all()]


@app.post("/api/proposals", response_model=ProposalRead)
def create_proposal_endpoint(payload: ProposalIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ProposalRead:
    return proposal_read(create_proposal(db, user, payload))


@app.get("/api/proposals/{proposal_id}", response_model=ProposalRead)
def read_proposal(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ProposalRead:
    return proposal_read(get_proposal_for_user(db, proposal_id, user))


@app.put("/api/proposals/{proposal_id}", response_model=ProposalRead)
def update_proposal_endpoint(
    proposal_id: int,
    payload: ProposalIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProposalRead:
    proposal = get_proposal_for_user(db, proposal_id, user)
    return proposal_read(update_proposal(db, proposal, payload, user))


@app.post("/api/proposals/{proposal_id}/duplicate", response_model=ProposalRead)
def duplicate_proposal_endpoint(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ProposalRead:
    proposal = get_proposal_for_user(db, proposal_id, user)
    return proposal_read(duplicate_proposal(db, proposal, user))


@app.delete("/api/proposals/{proposal_id}")
def delete_proposal_endpoint(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    proposal = get_proposal_for_user(db, proposal_id, user)
    delete_proposal(db, proposal, user)
    return {"ok": True}


@app.post("/api/proposals/{proposal_id}/preview", response_model=GenerateResponse)
def preview_proposal(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> GenerateResponse:
    proposal = get_proposal_for_user(db, proposal_id, user)
    pdf_path = generate_preview(proposal, Path(proposal.template_version.file_path))
    proposal.preview_pdf_path = str(pdf_path)
    db.commit()
    return GenerateResponse(proposal_id=proposal.id, pdf_url=f"/api/proposals/{proposal.id}/download/preview", pdf_filename=pdf_path.name)


@app.post("/api/proposals/{proposal_id}/generate", response_model=GenerateResponse)
def generate_proposal(proposal_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> GenerateResponse:
    proposal = get_proposal_for_user(db, proposal_id, user)
    docx_path, pdf_path = generate_files(proposal, Path(proposal.template_version.file_path))
    proposal.final_docx_path = str(docx_path)
    proposal.final_pdf_path = str(pdf_path)
    db.add(AuditLog(user_id=user.id, action=AuditAction.proposal_generated, entity_type="proposal", entity_id=proposal.id))
    db.commit()
    return GenerateResponse(
        proposal_id=proposal.id,
        docx_url=f"/api/proposals/{proposal.id}/download/docx",
        docx_filename=docx_path.name,
        pdf_url=f"/api/proposals/{proposal.id}/download/pdf",
        pdf_filename=pdf_path.name,
    )


@app.get("/api/proposals/{proposal_id}/download/{kind}")
def download_file(proposal_id: int, kind: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    proposal = get_proposal_for_user(db, proposal_id, user)
    path_by_kind = {
        "docx": proposal.final_docx_path,
        "pdf": proposal.final_pdf_path,
        "preview": proposal.preview_pdf_path,
    }
    file_path = path_by_kind.get(kind)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Файл еще не создан")
    media_type = "application/pdf" if kind in {"pdf", "preview"} else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(file_path, media_type=media_type, filename=Path(file_path).name)


@app.get("/api/admin/allowed-emails", response_model=list[AllowedEmailRead])
def list_allowed_emails(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> list[AllowedEmail]:
    return db.scalars(select(AllowedEmail).order_by(AllowedEmail.email)).all()


@app.post("/api/admin/allowed-emails", response_model=AllowedEmailRead)
def upsert_allowed_email(payload: AllowedEmailIn, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> AllowedEmail:
    email = payload.email.strip().lower()
    item = db.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
    if item is None:
        item = AllowedEmail(email=email)
        db.add(item)
    item.role = payload.role
    item.is_active = payload.is_active
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/admin/signers", response_model=list[SignerRead])
def list_admin_signers(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> list[Signer]:
    return db.scalars(select(Signer).order_by(Signer.name)).all()


@app.post("/api/admin/signers", response_model=SignerRead)
def create_signer(payload: SignerIn, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> Signer:
    signer = Signer(title=payload.title.strip(), name=payload.name.strip(), is_active=payload.is_active)
    if not signer.title or not signer.name:
        raise HTTPException(status_code=400, detail="Укажите должность и ФИО подписанта")
    db.add(signer)
    db.commit()
    db.refresh(signer)
    return signer


@app.patch("/api/admin/signers/{signer_id}", response_model=SignerRead)
def update_signer(signer_id: int, payload: SignerIn, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> Signer:
    signer = db.get(Signer, signer_id)
    if signer is None:
        raise HTTPException(status_code=404, detail="Подписант не найден")
    signer.title = payload.title.strip()
    signer.name = payload.name.strip()
    signer.is_active = payload.is_active
    if not signer.title or not signer.name:
        raise HTTPException(status_code=400, detail="Укажите должность и ФИО подписанта")
    db.commit()
    db.refresh(signer)
    return signer


@app.get("/api/admin/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> list[User]:
    return db.scalars(select(User).order_by(User.email)).all()


@app.patch("/api/admin/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if payload.role is not None:
        target.role = payload.role
    if payload.status is not None:
        target.status = payload.status
        if payload.status.value == "blocked":
            db.add(AuditLog(user_id=user.id, action=AuditAction.user_blocked, entity_type="user", entity_id=target.id))
    db.commit()
    db.refresh(target)
    return target


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
