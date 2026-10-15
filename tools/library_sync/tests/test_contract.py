import copy
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'contract.py'
spec = importlib.util.spec_from_file_location('library_contract', MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def fixture():
    card = dict(id='book:keeper', book_id='book', kind='character', layer='fact',
                title='Keeper', body='Keeps a lantern.', paragraph_id='abc:0', quote='灯',
                annotation='Personal note', reviewed=1, edited=1)
    page = dict(paragraph_offset=0, card_offset=0, result=dict(
        book=dict(id='book', source_hash='a'*64), paragraphs=[dict(id='abc:0', text='灯 remains.')],
        cards=[card], paragraph_count=1, card_count=1,
        next_paragraph_offset=None, next_card_offset=None))
    manifest = dict(schema_version=1, project_id='neutral-project', revision_id='r1',
        sources=[dict(id='canon', role='current', book_id='book', source_hash='a'*64)],
        artifacts=[dict(id='scene', path='story/scene.txt', sha256='b'*64)],
        records=[dict(id='keeper', kind='character', status='draft',
            links=[dict(source_id='canon', card_id='book:keeper', card_digest=c.card_digest(card))],
            artifact_ids=['scene'])],
        nodes=[dict(id='arrival', record_ids=['keeper'], script_artifact_id='scene', script_node_id='arrival')])
    return manifest, page


def confirm(m):
    record = m['records'][0]
    record['status'] = 'confirmed'
    record['confirmation'] = dict(record_digest=c.record_digest(m, record), evidence='author-decision-17')


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.m, self.p = fixture()

    def test_real_read_source_shape_and_notes(self):
        snap = c.snapshot_from_pages([self.p])
        self.assertEqual(snap['book_id'], 'book')
        self.assertEqual(list(snap['cards']), ['book:keeper'])
        before = snap['cards']
        self.p['result']['cards'][0].update(annotation='New', reviewed=0, edited=0)
        self.assertEqual(c.snapshot_from_pages([self.p])['cards'], before)

    def test_changed_human_analysis_detected(self):
        self.p['result']['cards'][0]['body'] = 'Human replacement'
        result = c.assess(self.m, {'canon': c.snapshot_from_pages([self.p])}, {'scene': 'b'*64})
        self.assertIn({'kind':'card_changed', 'target':'keeper'}, result['findings'])

    def test_confirmed_current(self):
        confirm(self.m)
        self.assertEqual(c.assess(self.m, {'canon':c.snapshot_from_pages([self.p])}, {'scene':'b'*64})['findings'], [])

    def test_draft_never_auto_promoted(self):
        report = c.assess(self.m, {'canon':c.snapshot_from_pages([self.p])}, {'scene':'b'*64})
        self.assertEqual(report['findings'], [{'kind':'record_draft', 'target':'keeper'}])
        self.assertNotIn('confirmation', self.m['records'][0])

    def test_stale_confirmation(self):
        confirm(self.m)
        for mutate in (lambda m:m['artifacts'][0].update(sha256='c'*64),
                       lambda m:m['sources'][0].update(source_hash='d'*64),
                       lambda m:m['records'][0]['links'][0].update(card_digest='e'*64)):
            m = copy.deepcopy(self.m); mutate(m)
            with self.assertRaises(c.ContractError): c.validate_manifest(m)

    def test_reference_cannot_be_canon(self):
        self.m['sources'][0]['role'] = 'reference'
        self.m['records'][0]['artifact_ids'] = []
        confirm(self.m)
        with self.assertRaises(c.ContractError): c.validate_manifest(self.m)

    def test_revision_only_does_not_stale_narrative(self):
        confirm(self.m)
        self.m['revision_id'] = 'r2-visual-only'
        c.validate_manifest(self.m)
        self.assertEqual(c.assess(self.m, {'canon':c.snapshot_from_pages([self.p])}, {'scene':'b'*64})['findings'], [])

    def test_missing_observations_are_explicit(self):
        kinds = {f['kind'] for f in c.assess(self.m, {}, {})['findings']}
        self.assertEqual(kinds, {'source_unobserved','artifact_unobserved','record_draft'})

    def test_changed_artifact(self):
        self.assertIn({'kind':'artifact_changed','target':'scene'},c.assess(self.m, {}, {'scene':'c'*64})['findings'])

    def test_source_mismatch_and_missing_card(self):
        snap = dict(book_id='other', source_hash='c'*64, cards={})
        kinds = {f['kind'] for f in c.assess(self.m, {'canon':snap}, {})['findings']}
        self.assertTrue({'source_mismatch','card_missing'} <= kinds)

    def test_exact_expected_manifest_conflict(self):
        proposed=copy.deepcopy(self.m); proposed['revision_id']='r2'
        self.assertEqual(c.check_transition(self.m, proposed, c.digest(self.m)), 'candidate_only')
        with self.assertRaises(c.ContractError): c.check_transition(self.m, proposed, 'e'*64)
        self.assertEqual(c.check_transition(self.m, self.m, c.digest(self.m)), 'unchanged')

    def test_cross_project_and_reused_revision(self):
        for field,value in [('project_id','other'),('nodes',[])]:
            proposed=copy.deepcopy(self.m); proposed[field]=value
            with self.assertRaises(c.ContractError): c.check_transition(self.m, proposed, c.digest(self.m))

    def test_dangling_graph_links(self):
        for field,value in [('record_ids',['unknown']),('script_artifact_id','unknown')]:
            m=copy.deepcopy(self.m); m['nodes'][0][field]=value
            with self.assertRaises(c.ContractError): c.validate_manifest(m)

    def test_reject_boolean_schema_duplicate_id_unknown_field(self):
        for mutate in (lambda m:m.update(schema_version=True),lambda m:m['sources'].append(m['sources'][0]),lambda m:m.update(secret='bad')):
            m=copy.deepcopy(self.m); mutate(m)
            with self.assertRaises(c.ContractError): c.validate_manifest(m)

    def test_separate_pagination_exhaustion(self):
        self.p['result'].update(paragraph_count=2,next_paragraph_offset=1)
        p2=copy.deepcopy(self.p)
        p2.update(paragraph_offset=1,card_offset=1)
        p2['result'].update(paragraphs=[dict(id='abc:1',text='Second')], cards=[], next_paragraph_offset=None)
        self.assertEqual(c.snapshot_from_pages([self.p,p2])['book_id'],'book')
        with self.assertRaises(c.ContractError): c.snapshot_from_pages([self.p])
        p2['card_offset']=0
        with self.assertRaises(c.ContractError): c.snapshot_from_pages([self.p,p2])

    def test_count_drift_mixed_source_and_duplicate(self):
        self.p['result'].update(paragraph_count=2,next_paragraph_offset=1)
        for mutate, message in (
            (lambda p:p['result'].update(card_count=2), 'changed during pagination'),
            (lambda p:p['result']['book'].update(id='another'), 'Mixed source versions')):
            p=copy.deepcopy(self.p)
            p.update(paragraph_offset=1,card_offset=1)
            p['result'].update(paragraphs=[dict(id='abc:1',text='Second')], cards=[], next_paragraph_offset=None)
            mutate(p)
            with self.assertRaisesRegex(c.ContractError, message):
                c.snapshot_from_pages([self.p,p])
        with self.assertRaisesRegex(c.ContractError, 'duplicate or unordered'):
            c.snapshot_from_pages([self.p,self.p])

    def test_bad_anchor_and_foreign_card(self):
        for field,value in [('quote','missing'),('quote',1),('paragraph_id',[]),('book_id','other'),('body',None)]:
            p=copy.deepcopy(self.p); p['result']['cards'][0][field]=value
            with self.assertRaises(c.ContractError): c.snapshot_from_pages([p])

    def test_invalid_snapshot_hash(self):
        with self.assertRaises(c.ContractError):
            c.assess(self.m, {'canon':dict(book_id='book',source_hash='a'*64,cards={'card':'bad'})}, {})

    def test_no_mutation(self):
        before=copy.deepcopy(self.m); page=copy.deepcopy(self.p)
        c.assess(self.m, {'canon':c.snapshot_from_pages([self.p])}, {'scene':'b'*64})
        self.assertEqual(self.m,before); self.assertEqual(self.p,page)

    def test_standalone_module_no_network_or_runtime(self):
        import ast
        imports = set()
        for node in ast.walk(ast.parse(MODULE.read_text())):
            if isinstance(node, ast.Import): imports.update(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom): imports.add(node.module)
        self.assertEqual(imports, {'copy','hashlib','json','re'})


if __name__ == '__main__': unittest.main()
