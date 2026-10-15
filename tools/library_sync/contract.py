"""Offline, read-only creative-library snapshot contract. No IO or credentials."""
from copy import deepcopy
import hashlib
import json
import re


class ContractError(ValueError):
    pass


def digest(value):
    """SHA-256 of canonical JSON (not original source bytes)."""
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as error:
        raise ContractError('Not canonical JSON') from error
    return hashlib.sha256(raw).hexdigest()


def obj(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ContractError('Invalid object fields')


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ContractError('Expected nonempty bounded string')


def sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ContractError('Expected lowercase SHA-256')


def rows(value):
    if not isinstance(value, list) or len(value) > 500:
        raise ContractError('Expected list of at most 500 entries')
    return value


def index(values, key='id'):
    result = {}
    for value in rows(values):
        if not isinstance(value, dict):
            raise ContractError('Expected record')
        text(value.get(key))
        if value[key] in result:
            raise ContractError('Duplicate identity')
        result[value[key]] = value
    return result


CARD_FIELDS = ('id', 'kind', 'layer', 'title', 'body', 'paragraph_id', 'quote')


def card_digest(card):
    """Analysis and anchors only; personal notes/review flags are not canon."""
    if not isinstance(card, dict) or any(not isinstance(card.get(k), str) for k in CARD_FIELDS):
        raise ContractError('Incomplete library card')
    return digest({k: card[k] for k in CARD_FIELDS})


def snapshot_from_pages(pages):
    """Adapt complete ordered read_source results; caller supplies both offsets.

    Each entry is {paragraph_offset, card_offset, result}. Fetch serially, following
    both returned offsets (use the total count for an already exhausted stream).
    This checks completeness/consistency, not atomicity of the remote reads.
    """
    if not isinstance(pages, list) or not pages or len(pages) > 10000:
        raise ContractError('Missing or oversized pages')
    book = None
    paragraphs, cards = [], []
    totals = None
    for page in pages:
        obj(page, ('paragraph_offset', 'card_offset', 'result'))
        if type(page['paragraph_offset']) is not int or type(page['card_offset']) is not int:
            raise ContractError('Invalid offset')
        if page['paragraph_offset'] != len(paragraphs) or page['card_offset'] != len(cards):
            raise ContractError('Skipped, duplicate or unordered page')
        data = page['result']
        obj(data, ('book', 'paragraphs', 'cards', 'paragraph_count', 'card_count',
                   'next_paragraph_offset', 'next_card_offset'))
        if not isinstance(data['book'], dict):
            raise ContractError('Missing book')
        identity = {k: data['book'].get(k) for k in ('id', 'source_hash')}
        text(identity['id']); sha(identity['source_hash'])
        if book is not None and identity != book:
            raise ContractError('Mixed source versions')
        book = identity
        counts = (data['paragraph_count'], data['card_count'])
        if any(type(c) is not int or c < 0 for c in counts) or counts[0] > 1000000 or counts[1] > 500:
            raise ContractError('Invalid counts')
        if totals is not None and counts != totals:
            raise ContractError('Library changed during pagination; restart')
        totals = counts
        if not isinstance(data['paragraphs'], list) or len(data['paragraphs']) > 50 or not isinstance(data['cards'], list) or len(data['cards']) > 50:
            raise ContractError('Invalid page size')
        paragraphs.extend(deepcopy(data['paragraphs'])); cards.extend(deepcopy(data['cards']))
        for count, total, nxt in zip((len(paragraphs), len(cards)), totals,
                                     (data['next_paragraph_offset'], data['next_card_offset'])):
            if count > total or (nxt is not None and type(nxt) is not int) or nxt != (count if count < total else None):
                raise ContractError('Invalid continuation')
    if (len(paragraphs), len(cards)) != totals:
        raise ContractError('Incomplete pagination')
    anchors = {}
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise ContractError('Invalid paragraph')
        text(paragraph.get('id'))
        if paragraph['id'] in anchors or not isinstance(paragraph.get('text'), str):
            raise ContractError('Invalid paragraph identity/text')
        anchors[paragraph['id']] = paragraph['text']
    result = {}
    for card in cards:
        if not isinstance(card, dict):
            raise ContractError('Invalid card')
        fingerprint = card_digest(card)
        text(card.get('id'))
        if card['id'] in result or card.get('book_id') != book['id']:
            raise ContractError('Duplicate or foreign card')
        if not card.get('quote') or card.get('paragraph_id') not in anchors or card['quote'] not in anchors[card['paragraph_id']]:
            raise ContractError('Invalid card anchor')
        result[card['id']] = fingerprint
    return {'book_id': book['id'], 'source_hash': book['source_hash'], 'cards': result}


def validate_manifest(value):
    obj(value, ('schema_version', 'project_id', 'revision_id', 'sources', 'artifacts', 'records', 'nodes'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ContractError('Unsupported schema')
    text(value['project_id']); text(value['revision_id'])
    sources = index(value['sources']); artifacts = index(value['artifacts']); records = index(value['records'])
    for source in sources.values():
        obj(source, ('id', 'role', 'book_id', 'source_hash'))
        if source['role'] not in ('current', 'reference'):
            raise ContractError('Invalid source role')
        text(source['book_id']); sha(source['source_hash'])
    for artifact in artifacts.values():
        obj(artifact, ('id', 'path', 'sha256'))
        text(artifact['path']); sha(artifact['sha256'])
        # A locator, never a path to open automatically.
    for record in records.values():
        obj(record, ('id', 'kind', 'status', 'links', 'artifact_ids'), ('confirmation',))
        if record['kind'] not in ('character', 'plot', 'rule', 'decision') or record['status'] not in ('draft', 'confirmed'):
            raise ContractError('Invalid record kind/status')
        for link in rows(record['links']):
            obj(link, ('source_id', 'card_id', 'card_digest'))
            text(link['source_id']); text(link['card_id']); sha(link['card_digest'])
            if link['source_id'] not in sources:
                raise ContractError('Unknown source')
        for aid in rows(record['artifact_ids']):
            text(aid)
            if aid not in artifacts:
                raise ContractError('Unknown artifact')
        if not record['links'] and not record['artifact_ids']:
            raise ContractError('Record has no evidence')
        if record['status'] == 'confirmed':
            if not record['artifact_ids'] and not any(sources[l['source_id']]['role'] == 'current' for l in record['links']):
                raise ContractError('References alone cannot confirm current canon')
            confirmation = record.get('confirmation')
            obj(confirmation, ('record_digest', 'evidence'))
            sha(confirmation['record_digest']); text(confirmation['evidence'])
            if confirmation['record_digest'] != record_digest(value, record):
                raise ContractError('Stale confirmation')
        elif 'confirmation' in record:
            raise ContractError('Draft must not carry confirmation')
    for node in index(value['nodes']).values():
        obj(node, ('id', 'record_ids', 'script_artifact_id', 'script_node_id'))
        text(node['script_artifact_id']); text(node['script_node_id'])
        if node['script_artifact_id'] not in artifacts:
            raise ContractError('Unknown script artifact')
        for rid in rows(node['record_ids']):
            text(rid)
            if rid not in records:
                raise ContractError('Unknown record on graph node')
    return deepcopy(value)


def record_digest(manifest, record):
    """Bind confirmation to referenced source/artifact identities and bytes."""
    sources = {s['id']: s for s in manifest['sources']}
    artifacts = {a['id']: a for a in manifest['artifacts']}
    return digest({'project_id': manifest['project_id'],
                   'record': {k: v for k, v in record.items() if k != 'confirmation'},
                   'sources': [sources[l['source_id']] for l in record['links']],
                   'artifacts': [artifacts[a] for a in record['artifact_ids']]})


def assess(manifest, snapshots, artifact_hashes):
    """Return explicit drift findings; unknown is never current. No writes."""
    m = validate_manifest(manifest)
    if not isinstance(snapshots, dict) or not isinstance(artifact_hashes, dict):
        raise ContractError('Expected observation mappings')
    findings = []
    def report(kind, target):
        item = {'kind': kind, 'target': target}
        if item not in findings:
            findings.append(item)
    sources = {s['id']: s for s in m['sources']}
    for source in sources.values():
        snap = snapshots.get(source['id'])
        if snap is None:
            report('source_unobserved', source['id']); continue
        obj(snap, ('book_id', 'source_hash', 'cards'))
        text(snap['book_id']); sha(snap['source_hash'])
        if not isinstance(snap['cards'], dict):
            raise ContractError('Invalid snapshot cards')
        for cid, fingerprint in snap['cards'].items():
            text(cid); sha(fingerprint)
        if snap['book_id'] != source['book_id'] or snap['source_hash'] != source['source_hash']:
            report('source_mismatch', source['id'])
    for artifact in m['artifacts']:
        observed = artifact_hashes.get(artifact['id'])
        if observed is None:
            report('artifact_unobserved', artifact['id'])
        else:
            sha(observed)
            if observed != artifact['sha256']:
                report('artifact_changed', artifact['id'])
    for record in m['records']:
        if record['status'] == 'draft':
            report('record_draft', record['id'])
        for link in record['links']:
            snap = snapshots.get(link['source_id'])
            if snap is None:
                continue
            actual = snap['cards'].get(link['card_id'])
            if actual is None:
                report('card_missing', record['id'])
            elif actual != link['card_digest']:
                report('card_changed', record['id'])
    return {'project_id': m['project_id'], 'revision_id': m['revision_id'],
            'manifest_digest': digest(m), 'findings': findings}


def check_transition(current, proposed, expected_digest):
    """Pure preflight only; a storage adapter MUST enforce atomic compare-and-swap."""
    current = validate_manifest(current); proposed = validate_manifest(proposed)
    sha(expected_digest)
    if digest(current) != expected_digest:
        raise ContractError('Conflict: current manifest changed; re-read and reconcile')
    if current['project_id'] != proposed['project_id']:
        raise ContractError('Cross-project transition')
    if current == proposed:
        return 'unchanged'
    if current['revision_id'] == proposed['revision_id']:
        raise ContractError('Changed content requires a new revision')
    return 'candidate_only'
