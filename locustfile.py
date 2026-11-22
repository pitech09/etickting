import os

from locust import HttpUser, between, task


class TicketingReadinessUser(HttpUser):
    wait_time = between(1, 3)
    host = os.getenv("LOAD_TEST_HOST", "http://127.0.0.1:8000")

    @task
    def readiness(self):
        self.client.get("/health/ready/", name="readiness")

    @task
    def public_ticket_verification_page(self):
        self.client.get("/tickets/verify/page/", name="verification-page")
