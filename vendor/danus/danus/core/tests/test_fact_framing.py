"""Fact markdown framing preserves text and IDs before any truth publication."""
import json
import re

import pytest
from danus.core import FactGraph
from danus.core.factgraph import parse_fact, serialize_fact, statement_of
from danus.core.schema import Fact, compute_fact_id


def fact(statement='A precise statement.', proof='A complete proof.', intuition=''):
    values = dict(problem_id='p', statement=statement, proof=proof,
                  predecessors=[], glossary_introduces={})
    return Fact(fact_id=compute_fact_id(**values), author='test', intuition=intuition, **values)


@pytest.mark.parametrize('heading', ['## intuition', '## proof', '## statement', '---'])
def test_arbitrary_headings_in_every_section_are_preserved(tmp_path, heading):
    statement = 'First assertion.\n' + heading + '\nSecond assertion.'
    proof = 'First step.\n' + heading + '\nSecond step.'
    intuition = 'Explanation.\n' + heading + '\nMore explanation.'
    graph = FactGraph(tmp_path)
    fid = graph.add(problem_id='p', author='test', statement=statement, proof=proof, intuition=intuition)
    loaded = graph.get(fid)
    assert (loaded.statement, loaded.proof, loaded.intuition) == (statement, proof, intuition)
    assert loaded.fact_id == fact(statement, proof).fact_id
    assert statement_of(graph.get_raw(fid)) == ' '.join(statement.split())
    assert graph.search('Second')[0]['statement'] == ' '.join(statement.split())
    assert graph.supporting_closure(fid)[0].proof == proof


def test_unicode_and_crlf_are_framed_without_changing_identity(tmp_path):
    original = fact('For \u03bb\u22650,\r\n## proof\r\nclaim \U0001f4d0.',
                    'By \u03bb=1.\r\n## intuition\r\nDone.')
    raw = serialize_fact(original)
    loaded = parse_fact(raw)
    assert loaded.fact_id == original.fact_id
    assert loaded.statement == original.statement.replace('\r\n', '\n')
    assert loaded.proof == original.proof.replace('\r\n', '\n')
    assert '\r' not in raw


def test_old_upstream_file_is_readable_and_not_rewritten_on_same_fact(tmp_path):
    original = fact(intuition='Historical note.')
    raw = serialize_fact(original)
    legacy = re.sub(r'^body_(?:format|lengths):.*\n', '', raw, flags=re.MULTILINE)
    graph = FactGraph(tmp_path)
    graph.facts_dir.mkdir(parents=True)
    path = graph._path(original.fact_id)
    path.write_text(legacy, encoding='utf8')
    before = path.read_bytes()
    loaded = graph.get(original.fact_id)
    assert loaded == original
    assert graph.add(problem_id='p', author='new provenance must not replace old',
                     statement=original.statement, proof=original.proof) == original.fact_id
    assert path.read_bytes() == before
    assert 'body_format:' not in path.read_text(encoding='utf8')


@pytest.mark.parametrize('lengths', [None, [True, 1, 0], [-1, 1, 0], [1, 1], [1, 1, 0], [999999, 1, 0]])
def test_bad_section_framing_fails_closed(lengths):
    raw = serialize_fact(fact())
    changed = re.sub(r'^body_lengths:.*$', 'body_lengths: ' + json.dumps(lengths), raw, flags=re.MULTILINE)
    with pytest.raises(ValueError):
        parse_fact(changed)


@pytest.mark.parametrize('mutation', ['truncate', 'append', 'unknown_format'])
def test_framed_body_cannot_hide_missing_or_extra_data(mutation):
    raw = serialize_fact(fact())
    changed = {'truncate': raw[:-2], 'append': raw + 'extra',
               'unknown_format': raw.replace('length-framed-v1', 'unknown-format')}[mutation]
    with pytest.raises(ValueError):
        parse_fact(changed)


def test_serialization_failure_never_publishes_active_fact(tmp_path, monkeypatch):
    import danus.core.factgraph as module
    original = module.serialize_fact
    monkeypatch.setattr(module, 'serialize_fact', lambda value: original(value)[:-2])
    graph = FactGraph(tmp_path)
    with pytest.raises(ValueError):
        graph.add(problem_id='p', author='test', statement='S', proof='Complete proof')
    assert graph.list() == []
    assert not list(graph.facts_dir.glob('*.md'))


def test_header_provenance_injection_is_rejected_before_publication(tmp_path):
    graph = FactGraph(tmp_path)
    with pytest.raises(ValueError):
        graph.add(problem_id='p', author='legitimate\nextra: injected', statement='S', proof='P')
    assert graph.list() == []


def test_publication_failure_leaves_no_fact(tmp_path, monkeypatch):
    import danus.core.factgraph as module
    def fail(*args, **kwargs):
        raise OSError('storage unavailable')
    monkeypatch.setattr(module, 'atomic_text', fail)
    graph = FactGraph(tmp_path)
    with pytest.raises(OSError):
        graph.add(problem_id='p', author='test', statement='S', proof='P')
    assert graph.list() == []
