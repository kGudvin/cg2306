import unittest
from unittest.mock import Mock, patch

from app.services.organizations import OrganizationNotFoundError, find_organization_by_inn, normalize_inn


class OrganizationLookupTest(unittest.TestCase):
    def test_normalize_inn(self):
        self.assertEqual(normalize_inn("77 07-083893"), "7707083893")
        with self.assertRaises(ValueError):
            normalize_inn("123")

    @patch("app.services.organizations.requests.post")
    def test_find_organization(self, post: Mock):
        response = Mock()
        response.json.return_value = {
            "suggestions": [{
                "value": "ПАО СБЕРБАНК",
                "data": {
                    "inn": "7707083893",
                    "kpp": "773601001",
                    "ogrn": "1027700132195",
                    "name": {"full_with_opf": "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО СБЕРБАНК РОССИИ"},
                    "address": {"unrestricted_value": "г Москва"},
                    "state": {"status": "ACTIVE"},
                },
            }]
        }
        post.return_value = response

        result = find_organization_by_inn("7707083893", "secret")

        self.assertEqual(result["name"], "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО СБЕРБАНК РОССИИ")
        self.assertEqual(result["address"], "г Москва")
        post.assert_called_once()

    @patch("app.services.organizations.requests.post")
    def test_not_found(self, post: Mock):
        response = Mock()
        response.json.return_value = {"suggestions": []}
        post.return_value = response

        with self.assertRaises(OrganizationNotFoundError):
            find_organization_by_inn("7707083893", "secret")


if __name__ == "__main__":
    unittest.main()
