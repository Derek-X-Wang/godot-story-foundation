"""Fail-closed command wrapper. Usage: gate.py FOLDER [...] -- COMMAND [...]."""
import json
import subprocess
import sys
from pathlib import Path
from check import check

def main(args):
    if '--' not in args:
        print('expected character folders -- export command', file=sys.stderr)
        return 2
    cut = args.index('--')
    folders, command = args[:cut], args[cut + 1:]
    if not folders or not command:
        print('both character folders and export command are required', file=sys.stderr)
        return 2
    results = [check(Path(folder)) for folder in folders]
    print(json.dumps(results, indent=2), flush=True)
    if not all(result['passed'] for result in results):
        return 1
    try:
        result = subprocess.run(command, check=False)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except OSError as error:
        print(f'export command failed to start: {error}', file=sys.stderr)
        return 127

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
