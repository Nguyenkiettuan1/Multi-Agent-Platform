from core.database.engines import to_psycopg_conninfo


def test_to_psycopg_conninfo_strips_sqlalchemy_driver():
    url = (
        "postgresql+psycopg://multiagent:multiagent@localhost:5434/multiagent"
        "?options=-csearch_path%3Dplatform"
    )
    assert to_psycopg_conninfo(url) == (
        "postgresql://multiagent:multiagent@localhost:5434/multiagent"
        "?options=-csearch_path%3Dplatform"
    )


def test_to_psycopg_conninfo_passthrough_plain_postgresql():
    url = "postgresql://multiagent:multiagent@localhost:5434/multiagent"
    assert to_psycopg_conninfo(url) == url
