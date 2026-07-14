import tempfile
import unittest
from pathlib import Path

from docx import Document

from app.template_seed import prepare_beshtau_template_from_source


SOURCE = Path(__file__).resolve().parents[1] / "КП от Кристины.docx"


class BeshtauTemplateTest(unittest.TestCase):
    def test_replaces_hardcoded_signer_with_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "beshtau_prepared.docx"
            prepare_beshtau_template_from_source(SOURCE, output)

            doc = Document(output)
            document_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)

            self.assertIn("{{signer_title}}", document_text)
            self.assertIn("{{signer_name}}", document_text)
            self.assertNotIn("В.О. Галустян", document_text)


if __name__ == "__main__":
    unittest.main()
