import json
from typing import NamedTuple


class ProfileData(NamedTuple):
    ipv4: str | None
    normal_sub: str | None


def parse_profile_json(json_str: str) -> ProfileData:
    """Парсит JSON ответ API и извлекает ipv4 и normal_sub."""
    try:
        data = json.loads(json_str)
        ipv4 = data.get("ipv4")
        normal_sub = data.get("normal_sub")
        return ProfileData(ipv4=ipv4, normal_sub=normal_sub)
    except (json.JSONDecodeError, TypeError):
        return ProfileData(ipv4=None, normal_sub=None)
