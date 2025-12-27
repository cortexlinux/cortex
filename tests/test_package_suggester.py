from cortex.suggestions.package_suggester import suggest_alternatives


def test_apache_server_suggests_apache():
    results = suggest_alternatives("apache-server")
    assert "apache2" in results
    assert "nginx" in results


def test_unknown_package_returns_list():
    results = suggest_alternatives("some-random-package")
    assert isinstance(results, list)
