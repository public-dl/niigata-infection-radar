"""Freshness checks shared by scheduled and manual weekly output workflows."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    try:
        value = Path(path).read_text(encoding='utf-8')
        result = json.loads(value)
        return result if isinstance(result, dict) else None
    except (OSError, ValueError):
        return None


def source_week(value):
    """Normalize a reporting year/week, never a calendar date or filename."""
    if not isinstance(value, dict):
        return None
    try:
        year, week = value['year'], value['week']
        if isinstance(year, bool) or isinstance(week, bool):
            return None
        if not str(year).isdigit() or not str(week).isdigit():
            return None
        year, week = int(year), int(week)
        return (year, week) if year > 0 and 1 <= week <= 53 else None
    except (KeyError, TypeError, ValueError):
        return None


def file_hash(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def metadata_path(pdf):
    return Path(pdf).with_suffix('.meta.json')


def is_pdf(path):
    try:
        with Path(path).open('rb') as stream:
            return stream.read(5) == b'%PDF-'
    except OSError:
        return False


def write_pdf_metadata(pdf, latest, ai_path, history_path):
    """Called only after successful rendering; bind metadata to these exact bytes."""
    week = source_week(latest)
    if week is None or not is_pdf(pdf):
        raise ValueError('Cannot mark an invalid PDF/reporting week as current')
    metadata = {
        'schema_version': 1,
        'source_week': {'year': week[0], 'week': week[1]},
        'pdf_sha256': file_hash(pdf),
        'ai_sha256': file_hash(ai_path),
        'history_sha256': file_hash(history_path),
    }
    path = metadata_path(pdf)
    pending = path.with_suffix('.json.pending')
    try:
        pending.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def output_plan(history_path, ai_path, pdf_path, data_changed=False):
    history = read_json(history_path)
    weeks = history.get('weeks') if history else None
    if not isinstance(weeks, list) or not weeks:
        raise ValueError('History must contain at least one reporting week')
    keys = [source_week(week) for week in weeks]
    if any(key is None for key in keys):
        raise ValueError('History contains an invalid reporting year/week')
    latest = max(keys)
    ai = read_json(ai_path)
    ai_current = bool(ai and source_week(ai.get('source_week')) == latest)
    meta = read_json(metadata_path(pdf_path))
    pdf_current = bool(
        meta and meta.get('schema_version') == 1
        and source_week(meta.get('source_week')) == latest
        and is_pdf(pdf_path)
        and meta.get('pdf_sha256') == file_hash(pdf_path)
        and ai_current
        and meta.get('ai_sha256') == file_hash(ai_path)
        and meta.get('history_sha256') == file_hash(history_path)
    )
    return {
        'source_week': {'year': latest[0], 'week': latest[1]},
        'ai_current': ai_current,
        'pdf_current': pdf_current,
        'generate_ai': not ai_current,
        'generate_pdf': bool(data_changed or not pdf_current),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, default=ROOT / 'data/influenza_history.json')
    parser.add_argument('--ai', type=Path, default=ROOT / 'data/ai_comment.json')
    parser.add_argument('--pdf', type=Path, default=ROOT / 'reports/latest.pdf')
    parser.add_argument('--data-changed', choices=('true', 'false'), default='false')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--require-current', action='store_true')
    parser.add_argument('--require-ai', action='store_true')
    args = parser.parse_args()
    plan = output_plan(args.history, args.ai, args.pdf, args.data_changed == 'true')
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as stream:
            for key in ('ai_current', 'pdf_current', 'generate_ai', 'generate_pdf'):
                stream.write(f'{key}={str(plan[key]).lower()}\n')
    if args.require_ai and not plan['ai_current']:
        raise SystemExit('AI source week does not match the latest history week')
    if args.require_current and (not plan['ai_current'] or not plan['pdf_current']):
        raise SystemExit('AI/PDF outputs are not current')


if __name__ == '__main__':
    main()
