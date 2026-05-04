from cis_bench.catalog.fts import build_fts_query


def test_fts_query_basic():
    assert build_fts_query("ubuntu") == "ubuntu*"


def test_fts_query_version():
    assert build_fts_query("ubuntu 20.04") == "ubuntu* 20* 04*"


def test_fts_query_symbols():
    assert build_fts_query("test!!!") == "test*"


def test_fts_query_empty():
    assert build_fts_query("") == ""
