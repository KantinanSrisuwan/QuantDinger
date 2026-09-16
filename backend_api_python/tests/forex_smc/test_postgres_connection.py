# -*- coding: utf-8 -*-
"""
PostgreSQL Connection & Database Health Verification:
- Validates connection string parsing
- Mock test verifying query dispatch & error handling
- Live connection test (run when -CheckDB or RUN_DB_TESTS=1 is specified)
"""
import os
import pytest
import psycopg2
from urllib.parse import urlparse

def parse_db_url(url):
    parsed = urlparse(url)
    return {
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432
    }

def check_postgres_health(db_url):
    """
    Attempts to connect and execute SELECT 1 on PostgreSQL.
    """
    params = parse_db_url(db_url)
    conn = psycopg2.connect(
        dbname=params["dbname"],
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        connect_timeout=3
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1;")
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res == (1,)


# ================= TESTS =================

def test_db_url_parser():
    """Verify correct extraction of database credentials."""
    url = "postgresql://quantdinger:secret123@127.0.0.1:5432/quantdinger_db"
    cfg = parse_db_url(url)
    assert cfg["dbname"] == "quantdinger_db"
    assert cfg["user"] == "quantdinger"
    assert cfg["password"] == "secret123"
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == 5432

def test_postgres_connection_mock(mocker):
    """Test connection handling using mock without requiring live DB."""
    mock_connect = mocker.patch("psycopg2.connect")
    mock_conn = mock_connect.return_value
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchone.return_value = (1,)
    
    status = check_postgres_health("postgresql://test:test@127.0.0.1:5432/testdb")
    assert status is True
    mock_connect.assert_called_once()

@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Live PostgreSQL test requires RUN_DB_TESTS=1 (e.g. via .\\run_tests.ps1 -CheckDB)"
)
def test_postgres_live_connection():
    """
    Live PostgreSQL integration test.
    Only executed when -CheckDB is specified in PowerShell runner.
    """
    db_url = os.getenv("DATABASE_URL", "postgresql://quantdinger:quantdinger123@127.0.0.1:5432/quantdinger")
    try:
        assert check_postgres_health(db_url) is True
    except psycopg2.OperationalError as e:
        pytest.fail(f"Could not connect to live PostgreSQL at {db_url}. Is Docker or PostgreSQL service running? Error: {e}")
