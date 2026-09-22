"""Run, status, pause/resume and explicit migration; no lifetime attempt limit."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4
from danus.core.durable_io import atomic_text, locked
from .model import Network


def status(root):
    n = Network(root)
    control = n.data.get('control', {})
    return {'run_id': control.get('run_id'), 'problem_id': n.problem_id,
            'target': n.target_id, 'target_truth': n.truth(n.target_id),
            'claims': len(n.data['claims']), 'supports': len(n.data['supports']),
            'active_studies': len(n.active_studies()), 'accepted_facts': len(n.proof_ids()),
            'revoked_facts': len(n.revoked_ids()), 'effective_depth': n.effective_depth(),
            'service_index': control.get('visit', 0), 'schedule': n.data.get('schedule', {}),
            'pending': bool(control.get('pending')), 'paused': (Path(root) / '.pause').exists()}


def run(root, *, resume=False, image='noespire-codex-isolated:local'):
    from danus.execution.isolation import DockerRoundRunner
    from substrate.runtime import Runtime
    from .engine import Research
    from .materials import capability_tools
    root = Path(root).resolve()
    if resume:
        (root / '.pause').unlink(missing_ok=True)
    runner = DockerRoundRunner(image=image, tools=lambda wl, role:
        capability_tools(Network(root), wl, role['ROLE']))
    runtime = Runtime(root, runner=runner, fingerprint=runner.fingerprint())
    research = Research(root, runtime)
    try:
        while not (root / '.pause').exists():
            result = research.step()
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if result['status'] in ('TARGET_SOLVED', 'NO_ACTIVE_STUDY'):
                return result
    except (RuntimeError, ValueError, OSError) as error:
        atomic_text(root / '.pause', 'BLOCKING_ENGINEERING_FAILURE\n' + str(error) + '\n')
        return {'status': 'BLOCKING_ENGINEERING_FAILURE', 'error': str(error)}
    except KeyboardInterrupt:
        atomic_text(root / '.pause', 'USER_EXPLICIT_PAUSE\n')
    return {'status': 'USER_EXPLICIT_PAUSE'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init'); p.add_argument('root'); p.add_argument('--problem-id', required=True)
    p.add_argument('--statement-file', required=True); p.add_argument('--context', default='')
    for command in ('status','run','resume','pause','export'):
        p = sub.add_parser(command); p.add_argument('root')
        if command in ('run','resume'): p.add_argument('--image', default='noespire-codex-isolated:local')
    p = sub.add_parser('migrate'); p.add_argument('source'); p.add_argument('destination')
    p = sub.add_parser('revoke'); p.add_argument('root'); p.add_argument('fact_id'); p.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    if args.command == 'init':
        Network.create(args.root, args.problem_id, Path(args.statement_file).read_text(encoding='utf-8'), args.context)
        result = status(args.root)
    elif args.command == 'migrate':
        from .migrate import migrate
        result = migrate(args.source, args.destination)
    elif args.command == 'status': result = status(args.root)
    elif args.command == 'pause':
        atomic_text(Path(args.root) / '.pause', 'USER_EXPLICIT_PAUSE\n')
        result = {'status': 'PAUSE_REQUESTED'}
    elif args.command == 'export': result = Network(args.root).export()
    elif args.command == 'revoke':
        with locked(Path(args.root) / '.crpn.lock'):
            n = Network(args.root)
            result = {'revoked': n.revoke(args.fact_id, args.reason)}
    else: result = run(args.root, resume=args.command == 'resume', image=args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
