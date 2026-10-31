import run


def test_all_queries_print(db_path, capsys):
    assert run.main(["--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    for number in range(1, len(run.query_files()) + 1):
        assert f"Q{number:02d}." in out
    assert "Ran 30 queries" in out


def test_selected_queries_only(db_path, capsys):
    assert run.main(["--db", str(db_path), "3", "17"]) == 0
    out = capsys.readouterr().out
    assert "Q03." in out and "Q17." in out
    assert "Q01." not in out
    assert "Ran 2 queries" in out


def test_max_rows_truncates(db_path, capsys):
    assert run.main(["--db", str(db_path), "1", "--max-rows", "5"]) == 0
    out = capsys.readouterr().out
    assert "... 19 more rows" in out


def test_missing_database_is_reported(tmp_path, capsys):
    assert run.main(["--db", str(tmp_path / "missing.db")]) == 1
    assert "python seed.py" in capsys.readouterr().err


def test_unknown_query_number(db_path, capsys):
    assert run.main(["--db", str(db_path), "99"]) == 1
    assert "99" in capsys.readouterr().err


def test_read_question_uses_first_comment():
    sql = "-- Q42. How many?\n-- more detail\nSELECT 1;"
    assert run.read_question(sql) == "Q42. How many?"


def test_format_table_aligns_columns():
    table = run.format_table(
        ["name", "customer_id", "revenue_qar", "share_pct"],
        [("Al Sadd", 1234, 1500.5, 12.25), ("Lusail", 7, 80.0, None)],
    )
    lines = table.splitlines()
    assert lines[0].split() == ["name", "customer_id", "revenue_qar", "share_pct"]
    assert set(lines[1].replace(" ", "")) == {"-"}
    # money columns always get two decimals and a thousands separator
    assert "1,500.50" in lines[2] and "80.00" in lines[3]
    # id columns skip the separator, missing values show as a dash
    assert "1234" in lines[2] and lines[3].endswith("-")
    # numbers are right-aligned, so rows end at the same column
    assert len(lines[2]) == len(lines[3])
    assert all(len(line) <= len(lines[1]) for line in lines)
