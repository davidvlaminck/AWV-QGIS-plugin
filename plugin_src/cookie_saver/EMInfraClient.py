from .Enums import Environment
from .RequesterFactory import RequesterFactory



class EMInfraClient:
    def __init__(self, env: Environment, cookie: str = None):
        self.requester = RequesterFactory.create_requester(env=env, cookie=cookie)
        self.requester.first_part_url += 'eminfra/'

    def test_connection(self):
        return self.requester.get("core/api/gebruikers/ik").json()
