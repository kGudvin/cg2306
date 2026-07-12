import re

import requests


DADATA_FIND_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"


class OrganizationLookupError(Exception):
    pass


class OrganizationNotFoundError(OrganizationLookupError):
    pass


def normalize_inn(value: str) -> str:
    inn = re.sub(r"\D", "", value)
    if len(inn) not in {10, 12}:
        raise ValueError("ИНН должен содержать 10 или 12 цифр")
    return inn


def find_organization_by_inn(inn: str, token: str, timeout: float = 7.0) -> dict[str, str | None]:
    normalized_inn = normalize_inn(inn)
    if not token:
        raise OrganizationLookupError("Сервис поиска организаций не настроен")

    try:
        response = requests.post(
            DADATA_FIND_PARTY_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            },
            json={"query": normalized_inn, "count": 1},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OrganizationLookupError("Не удалось получить данные организации") from exc

    suggestions = payload.get("suggestions") or []
    if not suggestions:
        raise OrganizationNotFoundError("Организация с таким ИНН не найдена")

    suggestion = suggestions[0]
    data = suggestion.get("data") or {}
    name = (data.get("name") or {}).get("full_with_opf") or suggestion.get("unrestricted_value") or suggestion.get("value")
    if not name:
        raise OrganizationLookupError("Сервис не вернул наименование организации")

    address = data.get("address") or {}
    return {
        "inn": normalized_inn,
        "name": name,
        "address": address.get("unrestricted_value") or address.get("value"),
        "kpp": data.get("kpp"),
        "ogrn": data.get("ogrn"),
        "status": (data.get("state") or {}).get("status"),
    }
