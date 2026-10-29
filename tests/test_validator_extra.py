import pytest

from sql_validator import SQLValidationError, validate_select


def test_extract_year_is_allowed():
    sql = validate_select(
        "SELECT COUNT(*) FROM orders WHERE EXTRACT(YEAR FROM created_at) = 2019"
    )
    assert "EXTRACT" in sql.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM orders WHERE id = (SELECT current_setting('server_version_num')::int)",
    ],
)
def test_dangerous_constructs_stay_blocked(sql):
    with pytest.raises(SQLValidationError) as error:
        validate_select(sql)
    assert error.value.code == "UNSUPPORTED_SQL"
