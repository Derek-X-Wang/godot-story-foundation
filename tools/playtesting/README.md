# Experimental audience-first virtual playtesting

**Experimental method, not a validated substitute for human playtesting.** This
optional Python 3.11+ standard-library package plans a bounded round, ingests
consumer-owned reports, and produces evidence-linked recommendations. It has no
runtime, Godot, art, authoring, regression, provider, account, API-key or network
dependency. Copy this directory alone to use it. It never runs a game or a model,
executes a recommendation, reads evidence references, or uploads anything.

The tool validates record consistency. It cannot establish that a model followed
its instructions, that an adapter is truthful, or that a finding is correct.
Counts describe synthetic configurations and executions, **not people**, opinion
prevalence, statistical confidence, or a scientifically determined sample size.
Independent fresh contexts reduce context contamination; identical models may
still share biases. Repeated model agreement is not a vote or a human result.

## Start with the audience and the next decision

1. State the intended experience, core audience, adjacent audience and non-target
   audience. Define the round's questions and the decision each should inform.
   Do not optimize for everyone or average core and non-target feedback together.
2. Select motivation/behavior axes **within that intended audience**: reasons to
   explore, patience for ambiguity, attention to relationships, desire for visible
   consequences, or familiarity with the interaction format. Explain relevance.
   Avoid demographic stereotypes and elaborate fictional biographies. A profile
   is a flexible preference configuration, never a script forcing a choice.
3. Start small. For a narrow segment, **2–3 relevant configurations** may suffice
   to begin; for a new demo, **3–4 core preference configurations plus neutral**
   is another adjustable starting heuristic. Neither is a quota, minimum evidence
   threshold or statistical N. Fewer/more may be appropriate for the questions.
   Neutral means no imposed preference, with the same instructions and controls.
4. Freeze candidate/build, adapter, profiles, model/configurations, questions,
   scenario inventory, per-session and aggregate budgets. A changed plan has a new
   canonical hash; old reports cannot silently inherit it. Treat retrospective
   migration as retrospective, never as a preregistration.

Keep four dimensions separate: **profile configurations**, **independent repeats**,
**model/configurations**, and **scenario/route coverage**. A new model is not a new
person. A repeat tests stability for the same profile/model/mode/entry/prompt/initial-state identity; it is not
another audience segment. Distinct context IDs are declarations, not proof of
statistical independence. Scenario inventories are game-owned and incomplete
inventories cannot reveal their own missing routes.

## Actual play and blindness contract

The game-owned adapter must read the **actual engine's current text and offered
options**, return the selected offered action to that same engine, and capture its
next observation. Never maintain an invented parallel story or overwrite engine
state to agree with the player's guess. Keep vanilla controls available and
unchanged; do not add player-facing prompts that tell a player which route to take.
Use reproducible candidate, initial-state, prompt, adapter, model/config and seed
records (explicitly `unknown` when not obtainable).

Give a fresh player only what that play surface has revealed so far, including
accessible interface hints. No source, future scenes, other branches, hidden
flags, author explanations, answer keys, or other players' findings. Record actual
input/access evidence, isolation limits and any accidental exposure. A claim of
blindness is ineligible here after known/unknown exposure; restart cleanly if
strict blind evidence is needed. A procedural self-report is not OS isolation.

Capture feedback and the intended action **before revealing the outcome**. The
record uses ordered event sequence numbers, exact observation/action/feedback
excerpts, and source references/hashes. Feedback ordering checks do not prove an
unseen log's integrity; the consumer audits the real choice roundtrip, timing,
engine fidelity, exposure and unchanged controls. See the separate
[isolated-reader worksheet](../../docs/narrative-review.md) for author review.

Never require completion. Preserve a voluntary stop at its real observation and
reason. `resource_limit`, `harness_failure`, `blocked`, `player_quit`, and
`terminal_screen` are distinct. A harness/token/time ceiling is **not quitting**.
Natural play starts with free choices and permission to stop. Chapter-entry and
explicitly targeted routes are labeled `chapter` and `targeted`; they never count
as natural completion, natural discovery, or evidence about whether a player would
voluntarily reach that chapter. Text/choice fidelity does not establish rendered
UI, movement, physical input, discoverability, pacing, or audio quality.

## Offline commands

All commands print JSON to stdout without changing inputs. Exit 0 means a valid
plan/bundle/recommendation, not a passed playtest. Invalid/stale records, duplicate
JSON keys, unknown fields, non-finite numbers and unavailable inputs exit 2.
Inputs must be regular files (symlinks are rejected where `O_NOFOLLOW` exists).
Bounds: 16 MiB per input, 8 MiB aggregate session records, 256 reports, 4,096 entries
per array/object, 16,384 characters per string, 32 nesting levels, numeric values
at most 10^12, and 16 MiB serialized CLI output (including its trailing newline). Successful
`ingest` output fits the input ceiling for `recommend`. Oversized records fail closed;
split the round or keep excerpts with opaque references to private full logs.
CLI limits protect accidental large local inputs, not a hostile-data sandbox.

```sh
python3 tools/playtesting/protocol.py plan --round tools/playtesting/examples/round.json
mkdir -p .build/playtesting
python3 tools/playtesting/protocol.py ingest \
  --round tools/playtesting/examples/round.json \
  --reports tools/playtesting/examples/session.json > .build/playtesting/bundle.json
python3 tools/playtesting/protocol.py recommend \
  --round tools/playtesting/examples/round.json \
  --bundle .build/playtesting/bundle.json \
  --review tools/playtesting/examples/review.json
python3 -m unittest discover -s tools/playtesting/tests -v
```

The examples are **hand-authored synthetic data**, including placeholder hashes
and audit assertions. They are not a real engine session, model evaluation,
production finding, or actual approval. They demonstrate a resource cutoff and an
unobserved optional route without claiming either voluntary quitting or complete
coverage. Copy/edit them **in private consuming-project storage** as templates.
Do not put private game text, raw logs, screenshots, assets, prompts, plot details,
credentials or filled reports in public Foundation or a game's export root.
Obtain appropriate authorization before sending private material to a provider.

Public Python API in `protocol.py`: `load(path)`, `validate_round(value)`,
`validate_report(validated_round, value)`, `plan(round)`, `ingest(round, reports)`,
`recommend(round, bundle, review=None)`, `digest(value)` and `ContractError`.
Inputs are treated as trusted local records, never mutated. Output contains the
supplied reports/excerpts; handle it with the same privacy as the input.
No JSON Schema runtime dependency is needed; the strict validator and neutral
JSON templates define experimental contract version 1.

## Record contract v1

Every object rejects unknown fields. Required arrays may be empty only where
there is no evidence yet. IDs are 1–128 ASCII letters/digits/dots/underscores/
hyphens, starting with an alphanumeric character. SHA256 values are lowercase
64-character hex. Schema versions are integer 1, never booleans. `digest` uses
UTF-8 canonical JSON (sorted keys, compact separators, no non-finite numbers);
these hashes detect record drift, not authenticate a reviewer or engine.

- **Round:** `id`, `candidate` (`id`, `build_sha256`, `engine`, `adapter`), audience
  descriptions, axes with `values`, `relevant_values` and `reason`; profiles with
  segment `core`/`adjacent`/`non_target`, role `motivated`/`neutral`, preferences
  keyed by axis, and rationale. A motivated profile needs preferences, a neutral
  profile has none. At least one core motivated profile is required. Model entries
  have `id`, `model`, `configuration` and declared `provenance`; different config
  IDs are tracked separately from underlying model names.
- **Questions:** `question`, `next_decision`, scenario IDs, modes and audience
  segments. Requirements are the Cartesian product of those lists; make separate
  questions if different routes need different modes. Non-target diagnostics
  cannot answer intended-audience questions. `scenarios` holds the game-owned
  catalog. Budget contains positive `max_sessions`, `max_total_minutes`,
  `max_session_minutes`, `max_turns`. The CLI reports ceilings; the adapter must
  enforce them during play. `starting_point` selects an advisory heuristic only.
- **Session:** unique `id`, `round_sha256`, `profile_id`, `model_id`, `mode`,
  `entry_point`, `context_id`, boolean `fresh_context`, `prior_exposure`
  (`none`/`known`/`unknown`), positive integer `repeat_index`, starting-state and
  prompt SHA256 (or null when unavailable), `seed` (including `unknown`), `fidelity`
  declarations and `audit_refs`. All five fidelity flags must be true, both hashes
  present, no prior exposure, fresh context and audit references present before
  the tool allows its evidence to support decision readiness. Incomplete records
  are retained for diagnosis, excluded from that judgment. Repeat indices are
  unique within profile/model/mode/entry/prompt/initial-state identity; duplicate context IDs never earn extra
  independent-repeat credit.
- **Evidence:** unique `id`, catalog `scenario_id`, `location`, `source_ref`,
  source SHA256, observation/feedback/outcome sequence numbers, and exact
  `visible_observation`, intended `action`, and contemporaneous `feedback`.
  Observation precedes feedback, which precedes a non-null revealed outcome.
  Null outcome means no next outcome was observed. Evidence references are opaque;
  the tool never opens a path/URL, executes text, or verifies the source's hash.
- **Features/findings:** choices (`location`, `option_id`), interpretations
  (`location`, `meaning`), counterexamples (`claim`, `observation`), and findings
  (`id`, `location`, `behavior`, `consequence`, `kind`, `severity`, `contract_ref`)
  all require local `evidence_ids`. Findings distinguish `contract_defect`,
  `suspected_issue`, and `preference`; only a contract defect requires a non-null
  authored contract reference. That reference alone does not prove a defect.
  Critical aesthetic preferences are rejected. Issues deduplicate only by exact
  case/whitespace-normalized location + behavior + consequence; semantic merging
  and divergent interpretations remain a reviewer responsibility, never voting.
- **End/usage:** end `reason`, `detail`, `evidence_ids`; voluntary stop, terminal
  screen and blocker need evidence. Usage has integer `turns`, nullable nonnegative `minutes`, nullable integer
  `model_calls`/`tokens`, and `cost`/`currency` (both
  known or both null). Unknown duration is retained and known total minutes remain a lower bound.
  No invented provider cost or inference-only timing.
- **Bundle:** round hash, reports and each canonical report hash. The recommender
  revalidates every report and hash; editing reports invalidates the bundle.
- **Review:** same round hash, exact `bundle_sha256`, `reviewer`, question assessments (`id`, boolean
  `ready`, `answer`, `decision`, evidence references) and optional adaptive signals
  (`kind`, `profile_id`, `compared_with`, `rationale`, evidence references).
  Replacing or appending any report changes the bundle hash and requires a new
  assessment; old answers never silently approve new evidence. References name
  both `session_id` and `evidence_id`. Questions can remain absent
  or unresolved. Coverage alone never answers a question. Signals are explicit
  reviewer judgments: `unstable`, `shared_bias`, or `redundant`.

## Adapt and stop for a reason

The output keeps evidence and findings before conclusions in the underlying
records; recommendations always include their reason and relevant identifiers.
Treat `status` as advice for the operator, never an instruction to force players:

- Add a **profile** for a missing audience-relevant perspective. A planned but
  unobserved configuration needs its initial run, not yet another profile.
- **Repeat the same configuration** in a fresh context for unstable results or a
  one-context critical issue. Do not resample until an inconvenient finding goes
  away. Keep disconfirming observations and uncertainty.
- **Cross-check a model** when an evidence-linked review suspects shared bias.
  Switching a prompt is not automatically an independent model. If another model
  is unavailable, retain that gap; do not require new accounts or credentials.
- Use **targeted route checks** for coverage gaps. Their output stays targeted;
  missing natural-play evidence remains missing. Never force a natural player to
  finish just to fill a coverage table.
- **Consider reducing** a reviewer-flagged redundant configuration only when its
  recorded choices, problems, interpretations and counterexamples add nothing
  over comparable segment/role/model/mode/entry contexts. Exact text matching is
  conservative; semantic novelty still needs review. Empty reports cannot establish
  redundancy, and the tool never removes profiles or rewrites the plan itself.
- `stop_fix_blocker`: a critical obstacle appears in at least two distinct eligible
  core contexts. This is a small procedural corroboration rule, not a validated N
  or defect verdict. Review/fix the common obstacle and replay affected routes.
- `stop_decision_ready`: explicit reviewer answers cite eligible evidence covering
  each question's required scenario/mode/segment combinations. This supports only
  the stated next decision. Unobserved routes and human-validation needs remain.
- `stop_budget_with_gaps`: the declared aggregate budget is exhausted and questions
  remain unresolved. Keep all gaps and stop spending; a budget never creates an
  answer. Otherwise `continue_or_review` identifies missing evidence or judgment.

A severe one-off can warrant author action without repeating when its direct
contract evidence is already decisive; the operator owns that judgment. Recommendations
are not a compulsory gate. After an accepted repair, freeze a new candidate/round,
run affected deterministic checks and route replays, and obtain the game's normal
review approval. Preserve the old records and neutral/vanilla baseline. Before
claiming this method predicts player experience, compare its specific predictions
with actual intended-audience human sessions, including missed issues and false
positives. No such general predictive validation is claimed by this package.
