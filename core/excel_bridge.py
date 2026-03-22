"""
core/excel_bridge.py — Tích hợp Excel qua win32com.
Tách riêng để dễ mock/test và không làm ô nhiễm UI code.
"""
import os
from typing import List

import win32com.client as win32


def open_or_create_notes(file_path: str) -> None:
    """Mở Notes.xlsm (tạo mới nếu chưa có) bằng Excel."""
    excel = win32.Dispatch("Excel.Application")
    excel.Visible = True
    if not os.path.exists(file_path):
        wb = excel.Workbooks.Add()
        ws = wb.Worksheets(1)
        ws.Cells(1, 1).Value = "No"
        ws.Cells(1, 2).Value = "CONTENT"
        ws.Cells(1, 3).Value = "LINK"
        ws.Cells(1, 4).Value = "NOTES"
        wb.SaveAs(file_path, FileFormat=52)   # 52 = xlOpenXMLWorkbookMacroEnabled
    else:
        excel.Workbooks.Open(file_path)


def add_hyperlinks(excel_file: str, file_paths: List[str], cell_address: str) -> None:
    """Chèn HYPERLINK vào Excel bắt đầu từ cell_address."""
    excel = win32.Dispatch("Excel.Application")
    excel.Visible = True
    wb = excel.Workbooks.Open(excel_file)
    ws = wb.Sheets(1)
    cell = ws.Range(cell_address)
    for i, path in enumerate(file_paths):
        ws.Cells(cell.Row + i, cell.Column).Formula = (
            f'=HYPERLINK("{path}", "Open File")'
        )
    wb.Save()
