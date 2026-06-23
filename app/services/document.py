import shutil
import subprocess
import uuid
from copy import deepcopy
from datetime import date
from pathlib import Path

from docx import Document
from docx.table import _Cell, _Row, Table
from docx.oxml.ns import qn

from app.config import get_settings
from app.models import Proposal
from app.services.money import format_money, format_numeric_date, format_ru_date


DEFAULT_SPECIFICATION_TEXT = (
    "Данное коммерческое предложение действительно для конфигурации, описанной в приложении "
    "“Спецификация №1”, приложенном к письму."
)


def _set_times_new_roman(run) -> None:
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rpr.rFonts.set(qn("w:ascii"), "Times New Roman")
    rpr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    rpr.rFonts.set(qn("w:eastAsia"), "Times New Roman")


def default_intro_text(proposal: Proposal) -> str:
    if proposal.request_type.value == "with_request" and proposal.request_number and proposal.request_date:
        return (
            f"Изучив направленный Вами запрос №{proposal.request_number} от "
            f"{format_numeric_date(proposal.request_date)} о предоставлении ценовой информации, "
            "мы, нижеподписавшиеся, предлагаем осуществить поставку оборудования, указанного в запросе, "
            "подтвержденную прилагаемой таблицей, в которой указана цена единицы товара и общая стоимость:"
        )
    return "Предлагаем рассмотреть коммерческое предложение на поставку оборудования на следующих условиях."


def legacy_intro_text(proposal: Proposal) -> str:
    if proposal.request_type.value == "with_request" and proposal.request_number and proposal.request_date:
        return (
            f"Изучив направленный Вами запрос №{proposal.request_number} от "
            f"{format_ru_date(proposal.request_date)} о предоставлении ценовой информации, "
            "мы предлагаем поставку оборудования на следующих условиях."
        )
    return "Предлагаем рассмотреть коммерческое предложение на поставку оборудования на следующих условиях."


def is_auto_intro_text(candidate: str | None, proposal: Proposal) -> bool:
    if candidate is None:
        return True
    normalized = " ".join(candidate.split())
    auto_variants = {
        " ".join(default_intro_text(proposal).split()),
        " ".join(legacy_intro_text(proposal).split()),
    }
    return normalized == "" or normalized in auto_variants


def proposal_context(proposal: Proposal) -> dict[str, str]:
    recipient = proposal.recipient_name.upper() if proposal.recipient_uppercase else proposal.recipient_name
    delivery_unit = "рабочих дней" if proposal.delivery_term_unit == "working_days" else "календарных дней"
    delivery_term = f"{proposal.delivery_term_value} {delivery_unit}" if proposal.delivery_term_value else ""
    optional_conditions = []
    if proposal.payment_terms:
        optional_conditions.append(f"Условия оплаты: {proposal.payment_terms}")
    if proposal.delivery_terms:
        optional_conditions.append(f"Условия доставки: {proposal.delivery_terms}")
    if proposal.delivery_place:
        optional_conditions.append(f"Место поставки: {proposal.delivery_place}")

    return {
        "recipient_name": recipient,
        "recipient_inn": proposal.recipient_inn or "",
        "recipient_email": proposal.recipient_email or "",
        "recipient_address": proposal.recipient_address or "",
        "quote_date": format_ru_date(proposal.quote_date),
        "outgoing_number": proposal.outgoing_number,
        "intro_text": proposal.intro_text or default_intro_text(proposal),
        "specification_text": proposal.specification_text,
        "delivery_term": delivery_term,
        "warranty": f"{proposal.warranty_months} мес.",
        "valid_until": format_ru_date(proposal.valid_until),
        "payment_terms": proposal.payment_terms or "",
        "delivery_terms": proposal.delivery_terms or "",
        "delivery_place": proposal.delivery_place or "",
        "optional_conditions": "\n".join(optional_conditions),
        "total_amount": format_money(proposal.total_amount),
        "vat_rate": format_money(proposal.vat_rate).rstrip("0").rstrip(","),
        "vat_amount": format_money(proposal.vat_amount),
        "total_amount_words": proposal.total_amount_words,
        "vat_amount_words": proposal.vat_amount_words,
        "signer_title": "Генеральный директор",
        "signer_name": "В.О. Галустян",
    }


def _replace_in_paragraph(paragraph, context: dict[str, str]) -> None:
    for run in paragraph.runs:
        text = run.text
        changed = False
        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            if placeholder in text:
                text = text.replace(placeholder, value)
                changed = True
        if changed:
            if "\n" not in text:
                run.text = text
            else:
                parts = text.split("\n")
                run.text = parts[0]
                for part in parts[1:]:
                    run.add_break()
                    run.add_text(part)
            _set_times_new_roman(run)


def _replace_in_cell(cell: _Cell, context: dict[str, str]) -> None:
    for paragraph in cell.paragraphs:
        _replace_in_paragraph(paragraph, context)
    for table in cell.tables:
        _replace_in_table(table, context)


def _replace_in_table(table: Table, context: dict[str, str]) -> None:
    for row in table.rows:
        for cell in row.cells:
            _replace_in_cell(cell, context)


def _replace_everywhere(doc: Document, context: dict[str, str]) -> None:
    for paragraph in doc.paragraphs:
        _replace_in_paragraph(paragraph, context)
    for table in doc.tables:
        _replace_in_table(table, context)
    for section in doc.sections:
        for paragraph in section.header.paragraphs + section.footer.paragraphs:
            _replace_in_paragraph(paragraph, context)
        for table in section.header.tables + section.footer.tables:
            _replace_in_table(table, context)


def _paragraph_has_only_placeholder(paragraph, key: str) -> bool:
    text = paragraph.text.strip()
    return text == "{{" + key + "}}"


def _paragraph_contains_placeholder(paragraph, key: str) -> bool:
    return "{{" + key + "}}" in paragraph.text


def _remove_paragraph(paragraph) -> None:
    element = paragraph._element
    element.getparent().remove(element)


def _remove_empty_block_placeholders(doc: Document, context: dict[str, str]) -> None:
    removable_keys = ["specification_text", "optional_conditions"]
    for key in removable_keys:
        if context.get(key, "") != "":
            continue
        for paragraph in list(doc.paragraphs):
            if _paragraph_has_only_placeholder(paragraph, key):
                _remove_paragraph(paragraph)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in list(cell.paragraphs):
                        if _paragraph_has_only_placeholder(paragraph, key):
                            _remove_paragraph(paragraph)
    if context.get("delivery_term", "") == "":
        for paragraph in list(doc.paragraphs):
            if _paragraph_contains_placeholder(paragraph, "delivery_term"):
                _remove_paragraph(paragraph)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in list(cell.paragraphs):
                        if _paragraph_contains_placeholder(paragraph, "delivery_term"):
                            _remove_paragraph(paragraph)


def _force_body_times_new_roman(doc: Document) -> None:
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            _set_times_new_roman(run)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        _set_times_new_roman(run)


def _row_has_item_placeholders(row: _Row) -> bool:
    return any("{{item_" in cell.text for cell in row.cells)


def _row_context(item, index: int) -> dict[str, str]:
    return {
        "item_no": str(index),
        "item_name": item.display_name or item.name,
        "item_unit": item.unit,
        "item_quantity": str(item.quantity),
        "item_unit_price": format_money(item.unit_price_vat),
        "item_line_total": format_money(item.line_total),
    }


def _replace_items_table(doc: Document, proposal: Proposal) -> None:
    for table in doc.tables:
        marker_index = next((idx for idx, row in enumerate(table.rows) if _row_has_item_placeholders(row)), None)
        if marker_index is None:
            continue
        marker_row = table.rows[marker_index]
        template_tr = deepcopy(marker_row._tr)

        for index, item in enumerate(sorted(proposal.items, key=lambda x: x.sort_order), start=1):
            new_tr = deepcopy(template_tr)
            marker_row._tr.addprevious(new_tr)
            row = _Row(new_tr, table)
            for cell in row.cells:
                _replace_in_cell(cell, _row_context(item, index))
        marker_row._tr.getparent().remove(marker_row._tr)
        return


def _filename_part(value: str | None, fallback: str, max_len: int = 80) -> str:
    invalid_chars = set(r'\/:*?"<>|')
    cleaned = "".join("-" if char in invalid_chars else char for char in str(value or fallback))
    cleaned = " ".join(cleaned.split()).strip(" .,-")
    return (cleaned[:max_len].strip(" .,-") or fallback)


def _output_stem(proposal: Proposal, suffix: str = "") -> str:
    template_name = getattr(getattr(proposal.template_version, "template", None), "name", None)
    parts = [
        _filename_part(template_name, "Шаблон"),
        _filename_part(proposal.recipient_name, "Адресат"),
        _filename_part(proposal.outgoing_number, "без номера", max_len=40),
    ]
    return f"{', '.join(parts)}{suffix}"


def _make_output_paths(proposal: Proposal, suffix: str = "") -> tuple[Path, Path]:
    settings = get_settings()
    stem = _output_stem(proposal, suffix=suffix)
    proposal_dir = settings.generated_dir / str(proposal.id)
    proposal_dir.mkdir(parents=True, exist_ok=True)
    return proposal_dir / f"{stem}.docx", proposal_dir / f"{stem}.pdf"


def render_docx(proposal: Proposal, template_path: Path, preview: bool = False) -> Path:
    doc = Document(str(template_path))
    context = proposal_context(proposal)
    _replace_items_table(doc, proposal)
    _remove_empty_block_placeholders(doc, context)
    _replace_everywhere(doc, context)
    _force_body_times_new_roman(doc)
    suffix = f"_preview_{uuid.uuid4().hex[:8]}" if preview else ""
    docx_path, _ = _make_output_paths(proposal, suffix=suffix)
    if preview:
        docx_path = get_settings().previews_dir / docx_path.name
    doc.save(str(docx_path))
    return docx_path


def convert_docx_to_pdf(docx_path: Path, output_dir: Path | None = None) -> Path:
    settings = get_settings()
    soffice = settings.libreoffice_bin
    if shutil.which(soffice) is None and not Path(soffice).exists():
        raise RuntimeError("LibreOffice не найден. Укажите LIBREOFFICE_BIN или установите libreoffice в контейнер.")
    out_dir = output_dir or docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(docx_path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=90,
    )
    pdf_path = out_dir / f"{docx_path.stem}.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Не удалось сконвертировать DOCX в PDF: {result.stderr or result.stdout}")
    return pdf_path


def generate_files(proposal: Proposal, template_path: Path) -> tuple[Path, Path]:
    docx_path, pdf_path = _make_output_paths(proposal)
    rendered_docx = render_docx(proposal, template_path, preview=False)
    if rendered_docx != docx_path:
        shutil.move(str(rendered_docx), str(docx_path))
    converted_pdf = convert_docx_to_pdf(docx_path, output_dir=docx_path.parent)
    if converted_pdf != pdf_path:
        shutil.move(str(converted_pdf), str(pdf_path))
    return docx_path, pdf_path


def generate_preview(proposal: Proposal, template_path: Path) -> Path:
    docx_path = render_docx(proposal, template_path, preview=True)
    return convert_docx_to_pdf(docx_path, output_dir=get_settings().previews_dir)
