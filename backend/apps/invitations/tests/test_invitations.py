import threading

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.invitations.models import Invitation
from apps.invitations.views import InvitationActive, send_invitation
from apps.jobs.summary import matching_summary
from apps.workers.models import IdentityVerification

from .helpers import PASSWORD, User, client_for, make_confirmed_job, make_worker, next_phone, seed


class M6TestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.client = client_for(self.customer)
        self.job = make_confirmed_job(self.customer)

    def recommendations(self, client=None, job=None):
        return (client or self.client).get(reverse("job-recommendations", args=[(job or self.job).id]))

    def send(self, worker_id, client=None, job=None):
        return (client or self.client).post(reverse("job-invitations", args=[(job or self.job).id]),
                                            {"worker_id": str(worker_id)}, format="json")


class RecommendationTests(M6TestCase):
    def test_only_eligible_matching_workers_appear_in_a_stable_order_with_reasons(self):
        speciality = make_worker()  # fan installation is a main speciality
        offers_only = make_worker(primary=("elec_wiring_repair",))
        speciality_two = make_worker()
        excluded = [
            make_worker(accepting=False),                       # paused
            make_worker(identity=None),                         # identity not started
            make_worker(identity="in_progress"),                # not approved
            make_worker(areas=("isb-g-10",)),                    # wrong area
            make_worker(trade="plumber", offered=("plmb_leak_repair",), primary=("plmb_leak_repair",)),  # wrong trade
            make_worker(offered=("elec_wiring_repair",), primary=("elec_wiring_repair",),
                        excluded=("elec_fan_install",)),        # explicitly does not offer the service
            make_worker(active=False),                          # inactive account
        ]
        body = self.recommendations().json()
        ids = [card["worker_id"] for card in body["workers"]]
        expected_top = sorted([str(speciality.id), str(speciality_two.id)])
        self.assertEqual(ids, expected_top + [str(offers_only.id)])
        self.assertTrue(all(str(p.id) not in ids for p in excluded))
        self.assertEqual(ids, [card["worker_id"] for card in self.recommendations().json()["workers"]])  # stable

        top = body["workers"][0]
        self.assertEqual(top["reasons"], [{"code": "speciality", "services": ["elec_fan_install"]},
                                          {"code": "serves_area", "area": "isb-g-9"}])
        self.assertEqual(top["verification"], {"status": "demo_approved", "simulated": True})
        self.assertTrue(top["is_new"])
        last = body["workers"][2]
        self.assertEqual(last["reasons"][0], {"code": "offers", "services": ["elec_fan_install"]})
        self.assertEqual(last["specialities_matched"], [])

    def test_all_requested_services_must_be_covered(self):
        job = make_confirmed_job(self.customer, services=("elec_fan_install", "elec_light_fitting"))
        make_worker()  # does not offer light fitting
        both = make_worker(offered=("elec_fan_install", "elec_light_fitting"), primary=("elec_light_fitting",))
        ids = [card["worker_id"] for card in self.recommendations(job=job).json()["workers"]]
        self.assertEqual(ids, [str(both.id)])

    def test_cards_contain_no_private_details(self):
        make_worker()
        response = self.recommendations()
        text = response.content.decode()
        for private in ("+92301", "0301", "*****", "DEMO-REG", "Bilal", "House 5", "Ring twice", "secret original"):
            self.assertNotIn(private, text)
        self.assertEqual(response.json()["shared_preview"]["description"], "Two ceiling fans to install.")
        self.assertNotIn("address_private", response.json()["shared_preview"])

    @override_settings(DEPLOYMENT_MODE="live")
    def test_demo_approvals_do_not_count_in_live_mode(self):
        make_worker()
        self.assertEqual(self.recommendations().json()["workers"], [])

    def test_empty_result_and_access_rules(self):
        body = self.recommendations().json()
        self.assertEqual(body["workers"], [])
        self.assertEqual(body["request"]["area"], "isb-g-9")
        other = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(self.recommendations(client=other).status_code, 404)
        worker = client_for(make_worker().user)
        self.assertEqual(self.recommendations(client=worker).status_code, 403)

    def test_draft_requests_cannot_be_matched(self):
        self.job.status, self.job.confirmed_at = "draft", None
        self.job.save()
        response = self.recommendations()
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "request_not_confirmed"))


class InvitationTests(M6TestCase):
    def test_send_retry_conflict_withdraw_and_reinvite(self):
        first, second = make_worker(), make_worker()
        sent = self.send(first.id)
        self.assertEqual(sent.status_code, 201, sent.content)
        invitation_id = sent.json()["id"]
        retry = self.send(first.id)
        self.assertEqual((retry.status_code, retry.json()["id"], retry.json()["created"]), (200, invitation_id, False))
        conflict = self.send(second.id)
        self.assertEqual((conflict.status_code, conflict.json()["error"]["code"]), (409, "invitation_already_active"))
        self.assertEqual(conflict.json()["error"]["details"]["invitation_id"], invitation_id)
        self.assertEqual(self.recommendations().json()["active_invitation"]["id"], invitation_id)

        withdrawn = self.client.post(reverse("job-invitation-withdraw", args=[self.job.id, invitation_id]))
        self.assertEqual(withdrawn.json()["status"], "withdrawn")
        again = self.send(first.id)
        self.assertEqual(again.status_code, 201)
        self.assertNotEqual(again.json()["id"], invitation_id)  # a fresh invitation gets a new identity
        history = self.client.get(reverse("job-invitations", args=[self.job.id])).json()["results"]
        self.assertEqual([item["status"] for item in history], ["active", "withdrawn"])
        cards = {c["worker_id"]: c for c in self.recommendations().json()["workers"]}
        self.assertEqual(cards[str(first.id)]["previous_invitation"], "active")

    def test_worker_who_became_ineligible_cannot_be_invited(self):
        worker = make_worker()
        self.assertEqual(len(self.recommendations().json()["workers"]), 1)
        worker.accepting_requests = False
        worker.save()
        response = self.send(worker.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["fields"]["worker_id"][0]["code"], "worker_not_available")
        worker.accepting_requests = True
        worker.save()
        IdentityVerification.objects.filter(user=worker.user).update(status="suspended")
        self.assertEqual(self.send(worker.id).status_code, 400)
        self.assertFalse(Invitation.objects.exists())

    def test_decline_releases_the_slot(self):
        first, second = make_worker(), make_worker()
        invitation_id = self.send(first.id).json()["id"]
        declined = client_for(first.user).post(reverse("invitation-decline", args=[invitation_id]), {"reason": "too_far"},
                                               format="json")
        self.assertEqual((declined.json()["status"], declined.json()["decline_reason"]), ("declined", "too_far"))
        self.assertEqual(self.client.post(reverse("job-invitation-withdraw", args=[self.job.id, invitation_id])).status_code, 409)
        fresh = self.send(second.id)
        self.assertEqual(fresh.status_code, 201)
        self.assertEqual(Invitation.objects.filter(job=self.job, status="active").count(), 1)

    def test_only_the_targeted_worker_sees_and_declines(self):
        target, unrelated = make_worker(), make_worker()
        invitation_id = self.send(target.id).json()["id"]
        target_client = client_for(target.user)
        inbox = target_client.get(reverse("invitations")).json()
        self.assertEqual([item["id"] for item in inbox["results"]], [invitation_id])
        detail = target_client.get(reverse("invitation", args=[invitation_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertIsNotNone(Invitation.objects.get(pk=invitation_id).seen_at)
        job = detail.json()["job"]
        self.assertEqual(job["area"], "isb-g-9")
        self.assertEqual(set(job), {"description", "trade", "services", "services_excluded", "city", "area", "window_start",
                                    "window_end", "budget_preference_pkr", "has_photos"})
        text = detail.content.decode()
        for private in ("House 5", "Ring twice", "secret original", str(self.job.id), self.customer.phone_number):
            self.assertNotIn(private, text)

        other = client_for(unrelated.user)
        self.assertEqual(other.get(reverse("invitations")).json()["count"], 0)
        self.assertEqual(other.get(reverse("invitation", args=[invitation_id])).status_code, 404)
        self.assertEqual(other.post(reverse("invitation-decline", args=[invitation_id])).status_code, 404)
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(stranger.get(reverse("invitations")).status_code, 403)
        self.assertEqual(stranger.post(reverse("job-invitation-withdraw", args=[self.job.id, invitation_id])).status_code, 404)
        # Workers still cannot open the customer's job or its media (M5 endpoints).
        self.assertEqual(target_client.get(reverse("job", args=[self.job.id])).status_code, 403)

    def test_shared_snapshot_is_the_matching_summary(self):
        worker = make_worker()
        invitation_id = self.send(worker.id).json()["id"]
        self.assertEqual(Invitation.objects.get(pk=invitation_id).shared_summary, matching_summary(self.job))

    def test_database_allows_only_one_active_invitation(self):
        first, second = make_worker(), make_worker()
        Invitation.objects.create(job=self.job, worker_profile=first, shared_summary={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invitation.objects.create(job=self.job, worker_profile=second, shared_summary={})


class SharedDescriptionTests(M6TestCase):
    def edit(self, text):
        return self.client.patch(reverse("job-shared-description", args=[self.job.id]), {"description": text}, format="json")

    def test_customer_can_remove_private_text_before_inviting(self):
        self.job.description = "Two fans. Call 0300 1234567, House 5 Street 9"
        self.job.save()
        self.assertEqual(self.recommendations().json()["privacy_warnings"], ["phone_number", "address"])
        edited = self.edit("Two fans in the lounge.")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["privacy_warnings"], [])
        self.assertEqual(self.recommendations().json()["shared_preview"]["description"], "Two fans in the lounge.")

    def test_not_while_an_invitation_is_active(self):
        self.send(make_worker().id)
        response = self.edit("changed")
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "invitation_already_active"))


class ConcurrencyTests(TransactionTestCase):
    """Real concurrent transactions against PostgreSQL (separate connections per thread)."""

    def setUp(self):
        seed()
        self.customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.job = make_confirmed_job(self.customer)

    def race(self, worker_ids):
        barrier = threading.Barrier(len(worker_ids))
        results = []

        def run(worker_id):
            try:
                barrier.wait()
                invitation, created = send_invitation(self.job.id, self.customer, worker_id)
                results.append(("ok", str(invitation.id), created))
            except InvitationActive:
                results.append(("conflict", None, False))
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(worker_id,)) for worker_id in worker_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def test_concurrent_sends_to_different_workers_create_one_active_invitation(self):
        workers = [make_worker() for _ in range(4)]
        results = self.race([w.id for w in workers])
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(1 for r in results if r[0] == "ok" and r[2]), 1)
        self.assertEqual(sum(1 for r in results if r[0] == "conflict"), 3)
        self.assertEqual(Invitation.objects.filter(job=self.job, status="active").count(), 1)

    def test_concurrent_retries_to_the_same_worker_return_one_invitation(self):
        worker = make_worker()
        results = self.race([worker.id] * 3)
        self.assertEqual(len({r[1] for r in results}), 1)
        self.assertEqual(sum(1 for r in results if r[2]), 1)
        self.assertEqual(Invitation.objects.filter(job=self.job).count(), 1)


class DemoWorkerSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_seed_is_idempotent_and_recommendable(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo_workers", stdout=StringIO())
        call_command("seed_demo_workers", stdout=StringIO())
        self.assertEqual(User.objects.filter(phone_number__startswith="+92300999010").count(), 4)
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        job = make_confirmed_job(customer)
        body = client_for(customer).get(reverse("job-recommendations", args=[job.id])).json()
        self.assertEqual(len(body["workers"]), 2)  # two electricians in G-9; the paused one is left out
        self.assertEqual(body["workers"][0]["specialities_matched"], ["elec_fan_install"])

    @override_settings(DEPLOYMENT_MODE="live")
    def test_refused_in_live_mode(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command("seed_demo_workers")
