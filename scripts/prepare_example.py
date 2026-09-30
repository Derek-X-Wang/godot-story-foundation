#!/usr/bin/env python3
"""Assemble a disposable Godot project from approved static content only."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare() -> Path:
    dependency = ROOT / '.deps/dialogue_manager'
    if not (dependency / 'plugin.cfg').is_file():
        raise SystemExit('Missing pinned Dialogue Manager. Run python3 scripts/fetch_dependencies.py first.')
    build = ROOT / '.build'
    artifacts = build / 'approved-village'
    authoring = ROOT / 'examples/village/authoring'
    subprocess.run([
        sys.executable, '-m', 'tools.authoring', 'build',
        '--packet', str(authoring / 'packet.json'),
        '--candidate', str(authoring / 'candidate.json'),
        '--review', str(authoring / 'review.json'),
        '--approval', str(authoring / 'approval.fixture.json'),
        '--output', str(artifacts), '--allow-test-fixture',
    ], cwd=ROOT, check=True)
    project = build / 'village'
    stage = build / 'village.staging'
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(ROOT / 'examples/village/game', stage,
                    ignore=shutil.ignore_patterns('.godot', '*.log'))
    shutil.copytree(ROOT / 'addons/story_foundation', stage / 'addons/story_foundation')
    shutil.copytree(dependency, stage / 'addons/dialogue_manager')
    shutil.copytree(ROOT / 'tests/runtime', stage / 'tests/runtime')
    # Copy only public regression steps, never the source packet/review itself.
    fixtures = json.loads((authoring / 'packet.json').read_text())['fixtures']
    (stage / 'tests/runtime/village_fixtures.json').write_text(json.dumps(fixtures))
    (stage / 'content').mkdir()
    for name in ('content.json', 'presentation.dialogue', 'build-manifest.json'):
        shutil.copy2(artifacts / name, stage / 'content' / name)
    # Editor metadata is disposable and never copied from a previous project.
    if project.exists():
        shutil.rmtree(project)
    stage.rename(project)
    print('Prepared .build/village (synthetic approval fixture; no authoring records in project)')
    return project


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
