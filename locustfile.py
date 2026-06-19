from locust import HttpUser, task, between


class AnonymousAuthUser(HttpUser):

    wait_time = between(0.01, 0.02)

    def on_start(self):
        self.create_session()

    def create_session(self):

        response = self.client.post("/auth/anonymous")

        if response.status_code != 200:
            print(f"Auth failed: {response.status_code}")

        # detener usuario después de 1 request
        self.stop(True)