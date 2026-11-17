"""Runtime passage evidence lives separately from development reports."""
from pathlib import Path

DIAGNOSTIC_ROOT = Path(__file__).resolve().parents[3] / 'report_traffic'
ARCHIVE_ROOT = DIAGNOSTIC_ROOT / 'archives'
DOCUMENT_ROOT = DIAGNOSTIC_ROOT / 'documents'
