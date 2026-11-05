"""Offline regression coverage for medically grounded transcript correction."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from correction_engine import (glossary_from_pdf, correction_prompt,
                               shortlist_pages, alignment_prompt,
                               correction_warning)


class MedicalCorrectionTests(unittest.TestCase):
    def test_glossary_contains_real_pdf_terms(self):
        pages = [
            {"page": 1, "text": "ACTH aldosterone CYP21A2 21-hydroxylase and Na. " * 2},
            {"page": 2, "text": "Pheochromocytoma DHEAS hyperthyroidism"}
        ]
        out = glossary_from_pdf(pages)
        for term in ["ACTH", "aldosterone", "CYP21A2", "21-hydroxylase", "Pheochromocytoma"]:
            self.assertIn(term, out)
        self.assertNotIn(", and,", ", " + out + ",")

    def test_phonetic_medical_correction_and_filler_instruction(self):
        prompt = correction_prompt(
            [{"id": "T0001", "raw": "음, 에이씨티에이치가 증가"}],
            "ACTH, aldosterone", "", "", '[{"id":"T0001","raw":"음, 에이씨티에이치가 증가"}]'
        )
        self.assertIn("에이씨티에이치", prompt)
        self.assertIn("ACTH", prompt)
        self.assertIn("말버릇", prompt)
        self.assertIn("페이지 매칭이나 요약을 절대 하지 않는다", prompt)

    def test_numerical_change_is_flagged(self):
        self.assertIsNotNone(correction_warning("1.8 mg 이상", "2.0 mg 이상"))
        self.assertIsNone(correction_warning("1.8 mg 이상", "1.8 mg 이상"))

    def test_page_shortlist_uses_relevant_pdf_text(self):
        pages = [
            {"page": 1, "text": "부신과 adrenal cortex. ACTH is involved."},
            {"page": 2, "text": "갑상선 TSH와 T3"},
            {"page": 3, "text": "당뇨병 SGLT2 metformin 2형"},
        ]
        found = shortlist_pages("metformin과 SGLT2 억제제", pages, 1)
        self.assertIn(3, [x["page"] for x in found])
        prompt = alignment_prompt(
            [{"id": "T0010", "corrected": "SGLT2 억제제"}], found, 1)
        self.assertIn("JSON", prompt)
        self.assertIn("실제 PDF", prompt)


if __name__ == "__main__":
    unittest.main()
