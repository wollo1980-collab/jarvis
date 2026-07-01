"""Tests für commands/excel.py - openpyxl wird gemockt, es wird nie
wirklich eine Excel-Datei geöffnet."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from commands.excel import ReadExcelCommand
from core.models import Plan, Status


def _fake_workbook(sheets: dict[str, list[tuple]]) -> MagicMock:
    workbook = MagicMock()
    workbook.sheetnames = list(sheets.keys())

    def getitem(name):
        ws = MagicMock()
        rows = sheets[name]
        ws.iter_rows.return_value = iter(rows)
        ws.max_row = len(rows)
        ws.max_column = len(rows[0]) if rows else 0
        return ws

    workbook.__getitem__.side_effect = getitem
    return workbook


def test_read_excel_needs_target():
    cmd = ReadExcelCommand()
    result = cmd.execute(Plan(intent="read_excel", target=None))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_read_excel_file_not_found(tmp_path):
    cmd = ReadExcelCommand()
    missing = tmp_path / "does_not_exist.xlsx"
    result = cmd.execute(Plan(intent="read_excel", target=str(missing)))
    assert result.status == Status.FAILED


def test_read_excel_rejects_unsupported_extension(tmp_path):
    cmd = ReadExcelCommand()
    bad_file = tmp_path / "report.xls"
    bad_file.touch()
    with patch("commands.excel.openpyxl.load_workbook") as load:
        result = cmd.execute(Plan(intent="read_excel", target=str(bad_file)))
    assert result.status == Status.FAILED
    load.assert_not_called()


def test_read_excel_success_reads_all_sheets(tmp_path):
    cmd = ReadExcelCommand()
    xlsx = tmp_path / "report.xlsx"
    xlsx.touch()
    fake_wb = _fake_workbook(
        {"Tabelle1": [("A", "B"), (1, 2)], "Tabelle2": [("X",)]}
    )
    with patch("commands.excel.openpyxl.load_workbook", return_value=fake_wb):
        result = cmd.execute(Plan(intent="read_excel", target=str(xlsx)))
    assert result.status == Status.SUCCESS
    assert "Tabelle1" in result.message
    assert "Tabelle2" in result.message
    assert result.data["sheets"]["Tabelle1"] == [("A", "B"), (1, 2)]
    assert result.data["sheets"]["Tabelle2"] == [("X",)]
    fake_wb.close.assert_called_once()


def test_read_excel_specific_sheet_via_parameters(tmp_path):
    cmd = ReadExcelCommand()
    xlsx = tmp_path / "report.xlsx"
    xlsx.touch()
    fake_wb = _fake_workbook({"Tabelle1": [("A",)], "Tabelle2": [("B",)]})
    with patch("commands.excel.openpyxl.load_workbook", return_value=fake_wb):
        result = cmd.execute(
            Plan(intent="read_excel", target=str(xlsx), parameters={"sheet": "Tabelle2"})
        )
    assert result.status == Status.SUCCESS
    assert list(result.data["sheets"].keys()) == ["Tabelle2"]
    assert "Tabelle1" not in result.message


def test_read_excel_unknown_sheet_name_fails(tmp_path):
    cmd = ReadExcelCommand()
    xlsx = tmp_path / "report.xlsx"
    xlsx.touch()
    fake_wb = _fake_workbook({"Tabelle1": [("A",)]})
    with patch("commands.excel.openpyxl.load_workbook", return_value=fake_wb):
        result = cmd.execute(
            Plan(intent="read_excel", target=str(xlsx), parameters={"sheet": "Nope"})
        )
    assert result.status == Status.FAILED
    fake_wb.close.assert_called_once()


def test_read_excel_load_failure_reported_not_silent(tmp_path):
    cmd = ReadExcelCommand()
    xlsx = tmp_path / "report.xlsx"
    xlsx.touch()
    with patch("commands.excel.openpyxl.load_workbook", side_effect=OSError("corrupt")):
        result = cmd.execute(Plan(intent="read_excel", target=str(xlsx)))
    assert result.status == Status.FAILED


def test_read_excel_caps_rows_per_sheet(tmp_path):
    cmd = ReadExcelCommand()
    xlsx = tmp_path / "big.xlsx"
    xlsx.touch()
    many_rows = [(i,) for i in range(1000)]
    fake_wb = _fake_workbook({"Tabelle1": many_rows})
    with patch("commands.excel.openpyxl.load_workbook", return_value=fake_wb):
        result = cmd.execute(Plan(intent="read_excel", target=str(xlsx)))
    assert result.status == Status.SUCCESS
    assert len(result.data["sheets"]["Tabelle1"]) == 500


def test_read_excel_requires_no_confirmation():
    assert ReadExcelCommand().requires_confirmation is False
