from app.models import version_sort_key


def test_numeric_versions_sort_correctly():
    versions = ["1.9.0", "1.10.0", "1.2.0"]
    assert sorted(versions, key=version_sort_key, reverse=True) == [
        "1.10.0",
        "1.9.0",
        "1.2.0",
    ]


def test_non_pep440_versions_do_not_crash():
    versions = ["1.0.0", "not-a-version", "2.0.0-beta"]
    ordered = sorted(versions, key=version_sort_key, reverse=True)
    assert ordered == ["2.0.0-beta", "1.0.0", "not-a-version"]
    # PEP 440 parses the beta as a pre-release; the unparseable string sorts last.
