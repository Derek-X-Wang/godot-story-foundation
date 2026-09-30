"""Offline authoring contract, rejection paths, and end-to-end determinism tests."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.authoring import __version__
from tools.authoring.cli import main
from tools.authoring.simulation import Simulator, simulate_fixtures
from tools.authoring.validation import ValidationError, safe_prose, validate_content, validate_packet, validate_exact_integers, MAX_EXACT_INTEGER
from tools.authoring.workflow import (
    approve, build, canonical, create_review, digest, export_request,
    import_response, load, validate_candidate, write,
)

FIXTURE = ROOT / 'examples/village/authoring'


class AuthoringTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.packet, _ = load(FIXTURE / 'packet.json')
        self.content, _ = load(FIXTURE / 'response.json')
        self.packet_path = self.directory / 'packet.json'
        self.response_path = self.directory / 'response.json'
        self.candidate_path = self.directory / 'candidate.json'
        self.review_path = self.directory / 'review.json'
        self.approval_path = self.directory / 'approval.json'
        write(self.packet_path, self.packet)
        write(self.response_path, self.content)

    def pipeline(self):
        import_response(self.packet_path, self.response_path, 'offline-test-response', self.candidate_path)
        create_review(self.packet_path, self.candidate_path, self.review_path)

    def fixture_approval(self):
        """Test-only data creation, conspicuously not human approval."""
        self.pipeline()
        _, ph = load(self.packet_path)
        _, ch = load(self.candidate_path)
        _, rh = load(self.review_path)
        write(self.approval_path, {
            'schema_version':1, 'kind':'synthetic_test_approval', 'tool_version':__version__,
            'review_status':'approved', 'reviewer':'SYNTHETIC TEST - NOT HUMAN', 'test_fixture':True,
            'packet_hash':ph, 'candidate_hash':ch, 'review_hash':rh,
        })

    def build(self, output='build', allow=True):
        return build(self.packet_path, self.candidate_path, self.review_path, self.approval_path,
                     self.directory / output, allow)

    def reject_content(self, mutation, match=None):
        mutation(self.content)
        with self.assertRaisesRegex(ValidationError, match or '.'):
            validate_content(self.packet, self.content)

    def test_public_fixture_validates(self):
        validate_content(self.packet, self.content)

    def test_four_simulations_cover_every_branch(self):
        report = simulate_fixtures(self.packet, self.content)
        self.assertEqual(len(report['fixtures']), 4)
        self.assertEqual(report['coverage']['covered_count'], 3)
        self.assertEqual(report['coverage']['required_count'], 3)

    def test_world_truth_does_not_teach_npc(self):
        sim = Simulator(self.content)
        self.assertTrue(sim.state['facts']['bridge_closed'])
        self.assertEqual(sim.state['actors']['mira']['knowledge'], {})
        self.assertEqual(sim.selected_branch('mira_notice')['id'], 'ignorant')

    def test_observation_is_personal(self):
        sim = Simulator(self.content)
        self.assertEqual(sim.dispatch('inspect_bridge', 'look'), 'applied')
        self.assertTrue(sim.state['actors']['player']['knowledge']['bridge_closed'])
        self.assertEqual(sim.selected_branch('mira_notice')['id'], 'ignorant')

    def test_choice_command_revalidates_guard(self):
        sim = Simulator(self.content)
        before = deepcopy(sim.state)
        self.assertEqual(sim.choose('mira_notice', 'ignorant', 'share_bridge_news', 'tell'), 'blocked')
        self.assertEqual(sim.state, before)
        sim.dispatch('inspect_bridge', 'look')
        self.assertEqual(sim.choose('mira_notice', 'ignorant', 'share_bridge_news', 'tell'), 'applied')
        self.assertEqual(sim.selected_branch('mira_notice')['id'], 'informed')

    def test_stale_branch_choice_is_blocked(self):
        sim = Simulator(self.content)
        sim.dispatch('inspect_bridge', 'look')
        sim.dispatch('share_news', 'tell')
        self.assertEqual(sim.choose('mira_notice', 'ignorant', 'share_bridge_news', 'stale'), 'blocked')

    def test_choice_and_reward_idempotency(self):
        sim = Simulator(self.content)
        sim.dispatch('inspect_bridge', 'look')
        sim.dispatch('share_news', 'tell')
        self.assertEqual(sim.choose('mira_notice', 'informed', 'mark_safe_path', 'choice'), 'applied')
        self.assertEqual(sim.choose('mira_notice', 'informed', 'mark_safe_path', 'choice'), 'duplicate')
        self.assertEqual(sim.dispatch('mark_path', 'different'), 'blocked')
        self.assertEqual(sim.state['coins'], 5)
        self.assertEqual(sim.state['inventory'], {'chalk':0, 'map':1})
        self.assertEqual(sim.state['actors']['mira']['trust'], 2)

    def test_first_matching_branch_wins(self):
        sim = Simulator(self.content)
        for cmd in ['inspect_bridge', 'share_news', 'mark_path']:
            sim.dispatch(cmd, cmd)
        self.assertTrue(sim.matches(self.content['dialogues'][0]['branches'][1]['when']))
        self.assertEqual(sim.selected_branch('mira_notice')['id'], 'path_marked')

    def test_unknown_speaker_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0].update(speaker='stranger'), 'unknown dialogue speaker')

    def test_unknown_dialogue_field_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0].update(script='dangerous'), 'unknown field')

    def test_unknown_root_field_rejected(self):
        self.reject_content(lambda c: c.update(reasoning='not allowed'), 'unknown field')

    def test_unknown_choice_command_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['fallback']['choices'][0].update(command='unapproved'), 'unknown command')

    def test_unknown_condition_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][0]['when'].append({'op':'eval','value':'code'}), 'unsupported operation')

    def test_unknown_effect_rejected(self):
        self.packet['world']['rules'][0]['effects'].append({'op':'emit','event':{'type':'x'}})
        with self.assertRaises(ValidationError):
            validate_packet(self.packet)

    def test_unknown_effect_actor_rejected(self):
        self.packet['world']['rules'][0]['effects'][0]['npc'] = 'stranger'
        with self.assertRaisesRegex(ValidationError, 'unknown actor'):
            validate_packet(self.packet)

    def test_unknown_effect_item_rejected(self):
        self.packet['world']['rules'][2]['effects'][0]['key'] = 'unknown'
        with self.assertRaisesRegex(ValidationError, 'unknown item'):
            validate_packet(self.packet)

    def test_unknown_effect_memory_rejected(self):
        self.packet['world']['rules'][0]['effects'][1]['key'] = 'unknown'
        with self.assertRaisesRegex(ValidationError, 'unknown memory'):
            validate_packet(self.packet)

    def test_unknown_effect_reward_rejected(self):
        self.packet['world']['rules'][2]['effects'][-1]['key'] = 'unknown'
        with self.assertRaisesRegex(ValidationError, 'unknown reward'):
            validate_packet(self.packet)

    def test_unknown_condition_fact_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][0]['when'][0].update(key='unknown'), 'unknown fact')

    def test_mismatched_fact_type_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][0]['when'][0].update(value=1), 'wrong type')

    def test_boolean_not_numeric_delta(self):
        self.packet['world']['rules'][1]['effects'][2]['delta'] = True
        with self.assertRaises(ValidationError):
            validate_packet(self.packet)

    def test_policy_mutation_rejected(self):
        self.reject_content(lambda c: c['world']['rules'][2]['effects'][-1].update(coins=500), 'authoritative world')

    def test_boolean_integer_policy_equivalence_cannot_bypass_hash(self):
        self.reject_content(lambda c: c['world']['initial_facts'].update(bridge_closed=1), 'authoritative world')

    def test_missing_fallback_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0].pop('fallback'), 'missing fallback')

    def test_missing_branch_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'].pop(), 'required branches')

    def test_empty_branches_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0].update(branches=[]), 'missing required branches')

    def test_duplicate_branch_ids_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][1].update(id='path_marked'), 'duplicate branch')

    def test_duplicate_choice_ids_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['fallback']['choices'].append(deepcopy(c['dialogues'][0]['fallback']['choices'][0])), 'duplicate choice')

    def test_claim_without_speaker_knowledge_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][1]['when'].pop(), 'speaker-knowledge')

    def test_claim_without_truth_guard_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][1]['when'].pop(0), 'world-truth')

    def test_knowledge_of_other_actor_not_sufficient(self):
        self.reject_content(lambda c: c['dialogues'][0]['branches'][1]['when'][1].update(npc='player'), 'speaker-knowledge')

    def test_fallback_cannot_assert_claims(self):
        self.reject_content(lambda c: c['dialogues'][0]['fallback']['claims'].append({'fact':'bridge_closed','value':True}), 'too many items')

    def test_prose_dsl_injection_rejected(self):
        for text in ['Hello\ndo dangerous()', 'Hi {{secret}}', 'Hi [tag]', 'Go => title', 'One|Two', 'Hi #tag', 'Hi\\nthere']:
            with self.subTest(text=text), self.assertRaises(ValidationError):
                safe_prose(text)

    def test_choice_colon_cannot_be_reinterpreted_as_speaker(self):
        self.reject_content(lambda c: c['dialogues'][0]['fallback']['choices'][0].update(
            text='Plan A: Share what you saw.'), 'choice text cannot contain a colon')

    def test_reserved_speaker_prefix_rejected(self):
        def replace_actor(value, name):
            if isinstance(value, dict):
                return {k:replace_actor(v,name) for k,v in value.items()}
            if isinstance(value, list):
                return [replace_actor(v,name) for v in value]
            return name if value == 'mira' else value
        for name in ('else', 'elsewhere', 'elif', 'elifred'):
            with self.subTest(speaker=name), self.assertRaisesRegex(ValidationError, 'reserved Dialogue Manager condition prefix'):
                validate_content(replace_actor(self.packet,name),replace_actor(self.content,name))

    def test_identifier_injection_rejected(self):
        self.reject_content(lambda c: c['dialogues'][0].update(id='bad");do bad('), 'invalid identifier')

    def test_duplicate_command_policy_rejected(self):
        rule = deepcopy(self.packet['world']['rules'][0]);rule['id'] = 'second'
        self.packet['world']['rules'].append(rule)
        with self.assertRaisesRegex(ValidationError, 'exactly one'):
            validate_packet(self.packet)

    def test_inventory_debit_requires_guard(self):
        rule = self.packet['world']['rules'][2]
        rule['when'] = [c for c in rule['when'] if c['op'] != 'inventory_gte']
        with self.assertRaisesRegex(ValidationError, 'unguarded inventory debit'):
            validate_packet(self.packet)

    def test_missing_branch_coverage_rejected(self):
        self.packet['fixtures'] = self.packet['fixtures'][:3]
        with self.assertRaisesRegex(ValidationError, 'branch coverage missing'):
            simulate_fixtures(self.packet, self.content)

    def test_wrong_simulation_expectation_rejected(self):
        self.packet['fixtures'][0]['expect_dialogues']['mira_notice'] = 'informed'
        with self.assertRaisesRegex(ValidationError, 'expected informed'):
            simulate_fixtures(self.packet, self.content)

    def test_wrong_state_expectation_rejected(self):
        self.packet['fixtures'][0]['expect_state']['coins'] = 99
        with self.assertRaisesRegex(ValidationError, 'state mismatch'):
            simulate_fixtures(self.packet, self.content)

    def test_export_is_provider_neutral_and_has_schema(self):
        request = export_request(self.packet_path, self.directory / 'request.json')
        self.assertEqual(request['kind'], 'provider_neutral_request')
        self.assertEqual(request['packet'], self.packet)
        self.assertIn('response_schema', request)
        self.assertNotIn('api_key', json.dumps(request))

    def test_import_never_autoapproves(self):
        candidate = import_response(self.packet_path, self.response_path, 'offline-test', self.candidate_path)
        self.assertEqual(candidate['kind'], 'unapproved_candidate')
        self.assertFalse(self.approval_path.exists())

    def test_import_requires_declared_model(self):
        with self.assertRaisesRegex(ValidationError, 'declared model'):
            import_response(self.packet_path, self.response_path, '', self.candidate_path)

    def test_duplicate_json_keys_rejected(self):
        self.response_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValidationError, 'duplicate JSON key'):
            load(self.response_path)

    def test_nonfinite_json_rejected(self):
        self.response_path.write_text('{"number":NaN}')
        with self.assertRaisesRegex(ValidationError, 'non-finite'):
            load(self.response_path)

    def test_markdown_wrapped_response_rejected(self):
        self.response_path.write_text('```json\n{}\n```')
        with self.assertRaisesRegex(ValidationError, 'invalid UTF-8 JSON'):
            load(self.response_path)

    def test_review_has_text_diff_and_no_approval(self):
        self.pipeline()
        review, _ = load(self.review_path)
        self.assertIn('+++ candidate-content.json', review['diff'])
        self.assertIn('NOT APPROVED', self.review_path.with_suffix('.txt').read_text())
        self.assertFalse(self.approval_path.exists())

    def test_manual_approval_requires_affirmative_flag(self):
        self.pipeline()
        with self.assertRaisesRegex(ValidationError, 'yes-i-reviewed'):
            approve(self.packet_path, self.candidate_path, self.review_path, 'Test Reviewer', False, self.approval_path)
        self.assertFalse(self.approval_path.exists())

    def test_manual_approval_requires_reviewer(self):
        self.pipeline()
        with self.assertRaisesRegex(ValidationError, 'reviewer identity'):
            approve(self.packet_path, self.candidate_path, self.review_path, '', True, self.approval_path)

    def test_explicit_manual_approval_builds(self):
        self.pipeline()
        result = approve(self.packet_path, self.candidate_path, self.review_path, 'UNIT TEST HUMAN PATH', True, self.approval_path)
        self.assertFalse(result['test_fixture'])
        self.assertFalse(self.build(allow=False)['test_fixture'])

    def test_fixture_approval_requires_opt_in(self):
        self.fixture_approval()
        with self.assertRaisesRegex(ValidationError, 'allow-test-fixture'):
            self.build(allow=False)
        self.assertFalse((self.directory / 'build').exists())

    def test_packet_byte_mutation_invalidates_approval(self):
        self.fixture_approval()
        with self.packet_path.open('a') as handle:handle.write('\n')
        with self.assertRaisesRegex(ValidationError, 'packet changed'):
            self.build()

    def test_candidate_byte_mutation_invalidates_approval(self):
        self.fixture_approval()
        with self.candidate_path.open('a') as handle:handle.write('\n')
        with self.assertRaisesRegex(ValidationError, 'stale review'):
            self.build()

    def test_review_byte_mutation_invalidates_approval(self):
        self.fixture_approval()
        with self.review_path.open('a') as handle:handle.write('\n')
        with self.assertRaisesRegex(ValidationError, 'approval invalidated'):
            self.build()

    def test_candidate_content_mutation_invalidates_hash(self):
        self.pipeline()
        candidate, _ = load(self.candidate_path)
        candidate['content']['dialogues'][0]['fallback']['text'] = 'Changed words.'
        write(self.candidate_path, candidate)
        with self.assertRaisesRegex(ValidationError, 'content hash mismatch'):
            validate_candidate(self.packet_path, self.candidate_path)

    def test_forged_simulation_report_rejected(self):
        self.pipeline()
        review, _ = load(self.review_path)
        review['simulation']['coverage']['covered_count'] = 999
        write(self.review_path, review)
        with self.assertRaisesRegex(ValidationError, 'simulation does not match'):
            approve(self.packet_path, self.candidate_path, self.review_path, 'Test', True, self.approval_path)

    def test_build_is_byte_deterministic(self):
        self.fixture_approval()
        self.build('first');self.build('second')
        for filename in ['content.json','presentation.dialogue','audit.json','build-manifest.json']:
            self.assertEqual((self.directory/'first'/filename).read_bytes(), (self.directory/'second'/filename).read_bytes())

    def test_output_hashes_match_files(self):
        self.fixture_approval();manifest = self.build()
        for filename, expected in manifest['artifacts'].items():
            self.assertEqual(digest((self.directory/'build'/filename).read_bytes()), expected)

    def test_dm_has_only_fixed_adapter_calls(self):
        self.fixture_approval();self.build()
        source = (self.directory/'build/presentation.dialogue').read_text()
        self.assertIn('if story.branch_available("mira_notice", "path_marked")', source)
        self.assertIn('do story.choose("mira_notice", "informed", "mark_safe_path")', source)
        self.assertNotIn('eval(', source)

    def test_audit_has_hashes_not_paths_or_reasoning(self):
        self.fixture_approval();self.build()
        audit, _ = load(self.directory/'build/audit.json')
        self.assertEqual(audit['review_status'], 'synthetic_test_fixture')
        self.assertIn('model_declared', audit)
        text = json.dumps(audit)
        self.assertNotIn(str(self.directory), text)
        self.assertNotIn('reasoning', text)
        manifest, _ = load(self.directory/'build/build-manifest.json')
        self.assertNotIn('reviewer', manifest)

    def test_authoring_output_inside_godot_root_rejected(self):
        game = self.directory/'game';game.mkdir();(game/'project.godot').write_text('[application]\n')
        with self.assertRaisesRegex(ValidationError, 'outside a Godot project'):
            export_request(self.packet_path, game/'private/request.json')
        self.assertFalse((game/'private').exists())

    def test_exact_integer_boundaries_accepted(self):
        for value in (-MAX_EXACT_INTEGER, MAX_EXACT_INTEGER):
            with self.subTest(value=value):
                validate_exact_integers({'nested':[value]})
                path = self.directory/'integer.json'
                write(path, {'value':value})
                self.assertEqual(load(path)[0]['value'], value)
                packet = deepcopy(self.packet)
                packet['world']['initial_facts']['exact_integer'] = value
                packet['registry']['facts'].append('exact_integer')
                validate_packet(packet)

    def test_adjacent_inexact_integer_boundaries_rejected(self):
        for value in (-MAX_EXACT_INTEGER - 1, MAX_EXACT_INTEGER + 1, 9007199254740993):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, 'exact JSON/Godot range'):
                    validate_exact_integers({'nested':[{'value':value}]})
                path = self.directory/'integer.json'
                write(path, {'value':value})
                with self.assertRaisesRegex(ValidationError, 'exact JSON/Godot range'):
                    load(path)

    def test_global_integer_check_covers_schema_and_fixture_fields(self):
        for field in ('schema_version', 'content_version'):
            packet = deepcopy(self.packet);packet[field] = MAX_EXACT_INTEGER + 1
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, 'exact JSON/Godot range'):
                validate_packet(packet)
        self.packet['fixtures'][0]['expect_state']['coins'] = MAX_EXACT_INTEGER + 1
        with self.assertRaisesRegex(ValidationError, 'exact JSON/Godot range'):
            validate_packet(self.packet)

    def test_trust_arithmetic_overflow_rolls_back(self):
        sim = Simulator(self.content)
        sim.dispatch('inspect_bridge','look')
        sim.state['actors']['mira']['trust'] = MAX_EXACT_INTEGER
        before = deepcopy(sim.state)
        self.assertEqual(sim.dispatch('share_news','tell'), 'blocked')
        self.assertEqual(sim.state, before)

    def test_inventory_arithmetic_overflow_rolls_back(self):
        sim = Simulator(self.content)
        sim.dispatch('inspect_bridge','look');sim.dispatch('share_news','tell')
        sim.state['inventory']['map'] = MAX_EXACT_INTEGER
        before = deepcopy(sim.state)
        self.assertEqual(sim.dispatch('mark_path','choice'), 'blocked')
        self.assertEqual(sim.state, before)

    def test_reward_arithmetic_overflow_rolls_back(self):
        sim = Simulator(self.content)
        sim.dispatch('inspect_bridge','look');sim.dispatch('share_news','tell')
        sim.state['coins'] = MAX_EXACT_INTEGER - 4
        before = deepcopy(sim.state)
        self.assertEqual(sim.dispatch('mark_path','choice'), 'blocked')
        self.assertEqual(sim.state, before)

    def test_output_cannot_overwrite_input(self):
        with self.assertRaisesRegex(ValidationError, 'overwrite an input'):
            export_request(self.packet_path, self.packet_path)
        with self.assertRaisesRegex(ValidationError, 'overwrite an input'):
            import_response(self.packet_path, self.response_path, 'test', self.response_path)

    def test_review_text_output_collision_rejected(self):
        self.pipeline()
        with self.assertRaisesRegex(ValidationError, '.txt suffix'):
            create_review(self.packet_path,self.candidate_path,self.directory/'review.txt')

    def test_cli_help(self):
        result = subprocess.run([sys.executable,'-m','tools.authoring','--help'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('import-response',result.stdout)

    def test_cli_fails_closed_without_approval_flag(self):
        self.pipeline()
        with redirect_stderr(io.StringIO()) as error:
            code = main(['approve','--packet',str(self.packet_path),'--candidate',str(self.candidate_path),
                         '--review',str(self.review_path),'--reviewer','Test','--output',str(self.approval_path)])
        self.assertEqual(code,2)
        self.assertIn('yes-i-reviewed',error.getvalue())
        self.assertFalse(self.approval_path.exists())

    def test_checked_in_fixture_builds_offline(self):
        result = build(FIXTURE/'packet.json',FIXTURE/'candidate.json',FIXTURE/'review.json',
                       FIXTURE/'approval.fixture.json',self.directory/'checked-in',True)
        self.assertTrue(result['test_fixture'])


if __name__ == '__main__':
    unittest.main()
