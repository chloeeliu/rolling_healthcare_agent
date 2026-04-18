from __future__ import annotations

import unittest
from pathlib import Path

from sepsis_mvp.gradio_demo import (
    _build_structured_rationale,
    _chatbot_messages,
    _decision_user_payload,
    _load_guideline_documents,
)


class GradioDemoHelpersTest(unittest.TestCase):
    def test_load_guideline_documents_reads_examples(self):
        docs = _load_guideline_documents(Path("clinical_guidelines"))
        self.assertGreaterEqual(len(docs), 3)
        self.assertTrue(any("Sepsis" in doc.title for doc in docs))

    def test_structured_rationale_reflects_infection_without_alert_threshold(self):
        rationale = _build_structured_rationale(
            "infection_suspect",
            {
                "query_infection": {
                    "has_suspected_infection": True,
                    "first_visible_suspected_infection_hour": 4,
                    "evidence": [{"antibiotic": "cefepime"}],
                },
                "query_sofa_by_hour": {
                    "latest_visible_hr": 4,
                    "latest_sofa_24hours": 1,
                    "max_sofa_24hours_so_far": 1,
                },
            },
            "Visible infection but SOFA remains below the alert threshold.",
        )
        self.assertIn("Suspected infection is visible", rationale["infection_status"])
        self.assertIn("does not yet meet the alert threshold", rationale["organ_dysfunction_status"])
        self.assertIn(
            "alert-level organ dysfunction is not yet clearly visible",
            rationale["why_not_trigger_sepsis_alert"].lower(),
        )

    def test_decision_user_payload_accepts_serialized_checkpoint_dict(self):
        payload = _decision_user_payload(
            {
                "instruction": "Monitor this patient.",
                "patient_summary": {"stay_id": 30157290},
                "completed_steps": [],
                "next_step_index": 0,
            },
            {
                "t_hour": 4,
                "checkpoint_time": "2156-04-17 22:44:00",
                "state_label": "infection_suspect",
            },
        )
        self.assertEqual(payload["current_checkpoint"]["t_hour"], 4)
        self.assertEqual(payload["current_checkpoint"]["reference_label"], "infection_suspect")

    def test_chatbot_messages_are_gradio_message_dicts(self):
        messages = _chatbot_messages(
            {
                "completed_steps": [
                    {
                        "investigation_turns": [
                            {"question": "Why?", "answer": "Because infection is visible."}
                        ]
                    }
                ]
            }
        )
        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "Why?"},
                {"role": "assistant", "content": "Because infection is visible."},
            ],
        )


if __name__ == "__main__":
    unittest.main()
