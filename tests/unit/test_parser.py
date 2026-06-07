"""Tests for the tolerant model-output parser."""

from netbrace.evals.parser import parse_prediction


def test_parses_fenced_json_block():
    text = """I think the answer is:
```json
{"sessions_lost": [{"node": "r1", "peer_ip": "10.0.0.2"}],
 "prefixes_lost": [], "reachability_lost": []}
```
Done."""
    br = parse_prediction(text)
    assert br is not None
    assert br.key_sets()["sessions"] == {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}


def test_parses_compact_list_form():
    text = '{"sessions_lost": [["r1", "10.0.0.2"]], "prefixes_lost": [["r3", "10.0.0.2"]]}'
    br = parse_prediction(text)
    assert br is not None
    assert br.key_sets()["sessions"] == {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}
    assert br.key_sets()["prefixes"] == {"route|node=r3|vrf=default|prefix=10.0.0.2/32"}


def test_prefers_last_json_block():
    text = """First draft:
```json
{"sessions_lost": [["r1","10.0.0.9"]]}
```
On reflection:
```json
{"sessions_lost": [["r1","10.0.0.2"]]}
```"""
    br = parse_prediction(text)
    assert br.key_sets()["sessions"] == {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}


def test_missing_keys_default_to_empty():
    br = parse_prediction('{"sessions_lost": [["r1","10.0.0.2"]]}')
    assert br.key_sets()["prefixes"] == set()
    assert br.key_sets()["reachability"] == set()


def test_unparseable_returns_none():
    assert parse_prediction("no json here at all") is None
    assert parse_prediction("") is None


def test_malformed_elements_are_dropped_not_fatal():
    # one good, one garbage element
    text = '{"sessions_lost": [["r1","10.0.0.2"], ["only_one_field"]]}'
    br = parse_prediction(text)
    assert br is not None
    assert len(br.sessions_lost) == 1


def test_bare_object_without_fence():
    text = 'Answer: {"prefixes_lost": [["r3","10.0.0.2/32"]]} -- that is my final answer'
    br = parse_prediction(text)
    assert br.key_sets()["prefixes"] == {"route|node=r3|vrf=default|prefix=10.0.0.2/32"}
