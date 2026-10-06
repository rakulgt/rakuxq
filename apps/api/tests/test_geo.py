from rakuxq_api.geo import GeoIPCityResolver


class _Reader:
    def get(self, address):
        assert address == "8.8.8.8"
        return {
            "country": {"iso_code": "US", "names": {"zh-CN": "美国", "en": "United States"}},
            "subdivisions": [{"names": {"zh-CN": "加利福尼亚州"}}],
            "city": {"names": {"zh-CN": "山景城", "en": "Mountain View"}},
            "location": {"latitude": 37.4229, "longitude": -122.085},
        }

    def close(self):
        pass


def test_geoip_resolver_returns_only_country_fields():
    resolver = GeoIPCityResolver()
    resolver._reader = _Reader()

    location = resolver.lookup("8.8.8.8")

    assert location is not None
    assert location.country_code == "US"
    assert location.country_name == "美国"
    assert location.__slots__ == ("country_code", "country_name")


def test_geoip_resolver_rejects_private_and_invalid_addresses():
    resolver = GeoIPCityResolver()
    resolver._reader = _Reader()

    assert resolver.lookup("127.0.0.1") is None
    assert resolver.lookup("192.168.1.1") is None
    assert resolver.lookup("not-an-ip") is None
