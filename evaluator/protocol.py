"""Shared response validation from the original evaluators."""

def check_text(obj, key):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        raise ValueError('Missing text field: ' + key)

def check_refs(refs, allowed):
    if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs) or not set(refs) <= allowed:
        raise ValueError('Invalid evidence references')

def score_label(score):
    if score == 2:
        return 'pass'
    if score == 0:
        return 'fail'
    return 'unknown'
