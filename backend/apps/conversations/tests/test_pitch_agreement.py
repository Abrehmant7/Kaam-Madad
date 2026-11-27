"""The pitch's agreement check in the real quote workflow (pitch item 5).

Customer: two fans, Rs. 1,200 including materials. Worker: Rs. 1,200 labour only, customer buys the materials.
→ exactly one materials finding; after clarifying and revising to labour + materials for Rs. 1,200 → no findings and
the quote is ready for acceptance. Groq runs through the same workflow (mocked HTTP): rate limits, outages and
ungrounded answers are never shown as a clean check; the manual review path stays available.
"""

import json
from unittest import mock

import httpx
from django.test import override_settings

from apps.conversations import quotes as rules
from apps.conversations.models import GapFinding, Quote
from apps.jobs.summary import matching_summary
from apps.providers import http as provider_http

from .test_conversations import ConversationTestCase, tomorrow

PITCH_REQUEST = "Please install two ceiling fans in G-9 tomorrow evening. My budget is Rs. 1,200 including materials."
LABOUR_ONLY = "Yes. Rs. 1,200 is for labour only. You will buy the fans and wiring yourself."
GROQ = {"AGREEMENT_CHECK_PROVIDER": "groq", "GROQ_API_KEY": "test-groq-key", "AI_PROVIDER_MAX_RETRIES": 0}


def groq_findings(*findings) -> httpx.Response:
    content = json.dumps({"findings": list(findings)}, ensure_ascii=False)
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})


MATERIALS = {"code": "materials_responsibility", "ask": "worker", "question": "Who buys the fans and wiring?",
             "sources": [{"kind": "request", "ref": "description", "text": "Rs. 1,200 including materials"},
                         {"kind": "quote", "ref": "materials", "text": "customer"}]}


class PitchAgreementWorkflowTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.job.description = PITCH_REQUEST
        self.job.save()
        self.invitation.shared_summary = matching_summary(self.job)
        self.invitation.save()

    def labour_only_quote(self, **overrides):
        self.send_text(self.customer, "Can you come tomorrow at 5 pm?")
        self.send_text(self.worker, LABOUR_ONLY)
        body = {"labour_basis": "total", "labour_amount": "1200", "materials": "customer", **overrides}
        self.assertEqual(self.save_draft(**body).status_code, 200)
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def ai_findings(self, quote):
        return [f for f in quote["findings"] if f["source"] == "ai"]

    def test_pitch_example_one_materials_finding_then_clean_after_revision(self):
        v1 = self.labour_only_quote()
        self.assertEqual(v1["check"]["status"], "findings")
        self.assertEqual([f["code"] for f in v1["findings"]], ["materials_responsibility"])  # exactly one
        self.assertEqual(v1["totals"]["known_total"], "1200.00")  # server-calculated
        finding = v1["findings"][0]
        self.assertIn("Who supplies and pays", finding["question"])  # English conversation → English question
        self.assertIn("unresolved_findings", self.readiness()["blocking"])
        # Both parties clarify, the point is recorded as a change of terms, and the worker revises.
        resolved = self.worker.post(self.url("conversation-finding-resolve", v1["id"], finding["id"]),
                                    {"resolution": "terms_changed", "note": "Worker brings the materials; Rs. 1,200 in total."},
                                    format="json")
        self.assertEqual(resolved.status_code, 200, resolved.content)
        self.assertIn("revision_required", self.readiness()["blocking"])
        self.send_text(self.worker, "OK, I will bring the fans and wiring. Rs. 1,200 including materials.")
        self.save_draft(labour_basis="total", labour_amount="1200", materials="included")
        v2 = self.submit().json()
        self.assertEqual((v2["version"], v2["check"]["status"], v2["findings"]), (2, "passed", []))
        self.assertTrue(self.readiness()["ready"])  # acceptance (M8) is still the customer's explicit step

    def test_roman_urdu_conversation(self):
        self.job.description = "G-9 mein do ceiling fan lagwane hain. 1200 rupay saman samet."
        self.job.save()
        self.invitation.shared_summary = matching_summary(self.job)
        self.invitation.save()
        self.send_text(self.worker, "Ji, 1200 sirf mazdoori hai. Saman aap khud le kar rakhein.")
        self.save_draft(labour_basis="total", labour_amount="1200", materials="customer")
        quote = self.submit().json()
        self.assertEqual([f["code"] for f in quote["findings"]], ["materials_responsibility"])
        self.assertIn("Saman kaun", quote["findings"][0]["question"])

    def test_separate_timing_disagreement_remains_a_second_finding(self):
        quote = self.labour_only_quote(start_at=tomorrow(9).isoformat(), end_at=tomorrow(11).isoformat())
        self.assertEqual(sorted(f["code"] for f in quote["findings"]), ["materials_responsibility", "timing_differs"])


@override_settings(**GROQ)
class GroqAgreementWorkflowTests(PitchAgreementWorkflowTests):
    """The same workflow with AGREEMENT_CHECK_PROVIDER=groq and the provider's HTTP mocked."""

    def run_with(self, *responses):
        replies = list(responses)
        calls = []

        def handler(request):
            calls.append(json.loads(request.content))
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        client = httpx.Client(transport=httpx.MockTransport(handler))
        patcher = mock.patch.object(provider_http, "default_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_pitch_example_one_materials_finding_then_clean_after_revision(self):
        duplicate = {**MATERIALS, "ask": "customer", "sources": [{"kind": "message", "ref": "x", "text": "ignored"}]}
        calls = self.run_with(groq_findings(MATERIALS, {**MATERIALS, "question": "Same point?"}, duplicate), groq_findings())
        v1 = self.labour_only_quote()
        self.assertEqual((v1["check"]["status"], v1["check"]["provider"]), ("findings", "groq"))
        self.assertFalse(v1["check"]["simulated"])
        self.assertEqual([f["code"] for f in v1["findings"]], ["materials_responsibility"])
        sent = json.loads(calls[0]["messages"][1]["content"])
        self.assertEqual(sent["conversation_language"], "English")
        self.assertEqual(sent["quote"]["materials"], "customer")
        for private in ("House 5", "Ring twice", "secret original"):
            self.assertNotIn(private, json.dumps(sent))
        finding = v1["findings"][0]
        self.worker.post(self.url("conversation-finding-resolve", v1["id"], finding["id"]),
                         {"resolution": "terms_changed", "note": "Worker brings the materials."}, format="json")
        self.save_draft(labour_basis="total", labour_amount="1200", materials="included")
        v2 = self.submit().json()
        self.assertEqual((v2["check"]["status"], v2["findings"]), ("passed", []))
        self.assertTrue(self.readiness()["ready"])

    def test_roman_urdu_conversation(self):
        roman = {**MATERIALS, "question": "Saman kaun laye ga?",
                 "sources": [{"kind": "request", "ref": "description", "text": "1200 rupay saman samet"}]}
        calls = self.run_with(groq_findings(roman))
        super().test_roman_urdu_conversation()
        self.assertIn("Roman Urdu", json.loads(calls[0]["messages"][1]["content"])["conversation_language"])

    def test_separate_timing_disagreement_remains_a_second_finding(self):
        timing = {"code": "timing_mismatch", "ask": "customer", "question": "Is 9 am acceptable?",
                  "sources": [{"kind": "quote", "ref": "start_at", "text": "+05:00"}]}
        self.run_with(groq_findings(MATERIALS, timing))
        quote = self.labour_only_quote(start_at=tomorrow(9).isoformat(), end_at=tomorrow(11).isoformat())
        # The rule already asks about the time outside the request: the AI's timing point is not asked twice.
        self.assertEqual(sorted((f["source"], f["code"]) for f in quote["findings"]),
                         [("ai", "materials_responsibility"), ("rule", "timing_differs")])

    def test_rate_limit_timeout_and_ungrounded_answers_are_never_clean(self):
        ungrounded = {**MATERIALS, "sources": [{"kind": "message", "ref": "m404", "text": "invented"}]}
        cases = [
            (httpx.Response(429, json={"error": {"message": "slow down"}}), "ai_provider_limit_reached:provider_rate_limited"),
            (httpx.ReadTimeout("slow"), "ai_provider_unavailable:timeout"),
            (groq_findings(ungrounded), "ai_output_invalid:findings_ungrounded"),
            (httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}),
             "ai_output_invalid:output_truncated"),
        ]
        for index, (reply, failure) in enumerate(cases):
            with self.subTest(failure=failure):
                self.run_with(reply)
                quote = self.labour_only_quote() if index == 0 else self._revise()
                self.assertEqual((quote["check"]["status"], quote["check"]["failure"]), ("unavailable", failure.split(":")[0]))
                stored = Quote.objects.get(pk=quote["id"])
                self.assertEqual(stored.check_failure, failure)
                self.assertFalse(stored.findings.filter(source=GapFinding.Source.AI).exists())
                self.assertIn("automated_check_unavailable", self.readiness()["blocking"])
        # The existing manual path: the customer confirms they compared the quote themselves.
        reviewed = self.customer.post(self.url("conversation-quote-manual-review", quote["id"])).json()
        self.assertEqual(reviewed["check"]["status"], "unavailable")
        self.assertNotIn("automated_check_unavailable", reviewed["readiness"]["blocking"])

    def test_a_late_result_for_an_old_version_is_discarded(self):
        self.run_with(groq_findings(MATERIALS), groq_findings())
        v1 = self.labour_only_quote()
        attempt = Quote.objects.get(pk=v1["id"]).check_attempt
        self.save_draft(labour_basis="total", labour_amount="1200", materials="included")
        self.submit()
        late = rules.store_check_result(v1["id"], attempt, result=mock.Mock(findings=[], provider="groq", simulated=False))
        self.assertFalse(late)
        self.assertEqual(Quote.objects.get(pk=v1["id"]).check_status, "findings")  # the superseded version is unchanged

    def _revise(self):
        self.save_draft(labour_basis="total", labour_amount="1200", materials="customer", scope=f"Install two fans {Quote.objects.count()}")
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()
