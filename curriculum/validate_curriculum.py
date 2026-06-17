"""Validate all curriculum YAML files against the loader schema."""
import yaml
from pathlib import Path

REQUIRED = ['id', 'day', 'topic', 'language', 'title', 'content', 'quiz']


def main():
    errors = 0
    ok = 0
    for f in sorted(Path(__file__).parent.rglob('*.yaml')):
        try:
            d = yaml.safe_load(f.read_text(encoding='utf-8'))
            missing = [k for k in REQUIRED if k not in d]
            assert not missing, f'missing {missing}'
            expected_id = f'day{d["day"]}_{d["topic"]}_{d["language"]}'
            assert d['id'] == expected_id, f'id {d["id"]} != {expected_id}'
            assert f.stem == f'{d["topic"]}_{d["language"]}', f'filename mismatch'
            assert len(d['quiz']) == 5, f'quiz has {len(d["quiz"])} questions'
            for i, q in enumerate(d['quiz']):
                assert all(k in q for k in ['question', 'options', 'correct']), f'q{i+1} bad keys'
                assert len(q['options']) == 4, f'q{i+1} has {len(q["options"])} options'
                assert isinstance(q['correct'], int) and 0 <= q['correct'] <= 3, f'q{i+1} bad correct'
            words = len(d['content'].split())
            if words < 120:
                print(f'WARN {f.parent.name}/{f.name}: only {words} words')
            ok += 1
        except Exception as e:
            errors += 1
            print(f'FAIL {f.parent.name}/{f.name}: {e}')
    print(f'{ok} valid, {errors} errors')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
