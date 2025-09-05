from .AbstractRequester import AbstractRequester
from .CookieRequester import CookieRequester
from .Enums import Environment


class RequesterFactory:
    first_part_url_dict = {
        Environment.PRD: 'https://services.apps.mow.vlaanderen.be/',
        Environment.TEI: 'https://services.apps-tei.mow.vlaanderen.be/',
        Environment.DEV: 'https://services.apps-dev.mow.vlaanderen.be/',
        Environment.AIM: 'https://services-aim.apps-dev.mow.vlaanderen.be/'
    }

    @classmethod
    def create_requester(cls, env: Environment, cookie: str = None) -> AbstractRequester:
        first_part_url = cls.first_part_url_dict.get(env)
        if first_part_url is None:
            raise ValueError(f"Invalid environment: {env}")


        if cookie is None:
            raise ValueError("argument cookie is required for COOKIE authentication")
        return CookieRequester(cookie=cookie, first_part_url=first_part_url.replace('services.', ''))

