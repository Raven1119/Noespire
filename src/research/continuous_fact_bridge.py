"""One automatic discovery/inspection/bridge opportunity; stop before proof service.

The existing scheduler chooses the Study. This entry never commits that service,
calls its Worker, or composes a Support. Resume is the same immutable opportunity.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from .continuous_materials import load_materials
from .continuous_network import ContinuousNetwork
from .continuous_research import _Research, _object, _TEXT, _InvocationFailure
from .dynamic_run import _code_digest
from .fact import _normalize
from .fact_bridge import _bridge_fact_locked, _write_once, read_bridge
from .graph import FactGraph
from .proof_graph import ProofObligation
from .run_invocations import RunStopped, SolInvoker, real_runtime
from .run_storage import read_json, write_json, run_lock


_REQUEST = _object({key:_TEXT for key in ('source_fact_id','target_claim_id','target_scope',
    'target_auxiliary_statement','correspondence')})
_SCHEMA = _object({'action':{'type':'string','enum':['IGNORE','REQUEST_BRIDGE']}, 'reason':_TEXT,
    'bridge_request':{'anyOf':[{'type':'null'},_REQUEST]}})
_PROMPT = """You are the fresh local Research Selector, now after requested material inspection.
Decide IGNORE or REQUEST_BRIDGE for at most one actually inspected BRIDGE_CANDIDATE.
No bridge is automatic merely because a Fact was discovered. You may ignore it if
unrelated, unjustified, or requiring further inspection. State the reason honestly.
REQUEST_BRIDGE is a request for a Worker proof and fresh independent verification,
not approval, mathematical authority, or permission to use the source as a premise.
Choose only the current Study's existing target Claim and exact target scope.
The target_auxiliary_statement must be a complete, independently reusable auxiliary
proposition in that scope. Include necessary definitions and ALL source conditions;
establish them under the target interface or explicitly retain them as hypotheses.
Never turn an unproved conditional assumption into a conclusion, or restate/prove
the enclosing requirement as the auxiliary result. correspondence must explicitly
describe source/target definitions, variables, domains and conditions and how they
map. 'Same notation' or 'clearly equivalent' is not a correspondence. The mapping
is unverified; similarity alone has no authority. Source scope and complete source
statement remain together in inspection, never in target accepted_facts.
Do not write a requirement proof. No requirement Worker or COMPOSE will run here.
For IGNORE return bridge_request=null. Closed book; use only this local packet.
PACKET:
"""
_TERMINAL = {'MATERIALIZED','NO_BRIDGE_REQUEST','INVALID_BRIDGE_REQUEST','BRIDGE_FAILED',
             'MATERIALIZATION_FAILED','TIMEOUT','ERROR','INTERRUPTED'}


def _paths(root, step=None):
    state = read_json(root/'continuous_run/state.json')
    if step is None:
        step = state['step']
    if type(step) is not int or step < 0:
        raise ValueError('invalid opportunity step')
    return state, root/'continuous_run/visits'/f'{step:08d}'/'automatic_bridge'


def read_materialization(problem_dir, *, step=None):
    """Historical receipt plus current truth validity; never returns stale premises."""
    root = Path(problem_dir).resolve()
    state, directory = _paths(root, step)
    origin = read_json(directory/'origin.json')
    result = read_json(directory/'state.json') if (directory/'state.json').exists() else {'status':'PENDING'}
    calls = [read_json(p) for p in (root/'continuous_run').glob('calls/*/request.json')]
    result = {**result, 'run_id':origin['run_id'], 'step':origin['step'],
        'selector_calls':sum(r['scope'].startswith(str(origin['step'])+':selector') for r in calls),
        'usable':False}
    if (directory/'bridge_reference.json').exists():
        result['bridge_id'] = read_json(directory/'bridge_reference.json')['bridge_id']
    if result.get('bridge_id'):
        result['bridge'] = read_bridge(root, result['bridge_id'])
    if result['status'] == 'MATERIALIZED':
        try:
            network = ContinuousNetwork(root)
            packet = read_json(directory/'material_packet.json')
            _validate_request(root, read_json(directory/'inspection_packet.json'),
                              read_json(directory/'bridge_request.json'))
            if not result['bridge']['usable']:
                raise ValueError('bridge output is no longer usable')
            facts, _, _ = load_materials(root, packet['study'],
                ['fact:'+f['fact_id'] for f in packet['accepted_facts']], {}, network)
            if (result['fact_id'] not in facts or
                    not set(packet['required_fact_ids']).issubset(facts)):
                raise ValueError('material receipt lost a required Fact')
            if packet['accepted_facts'] != list(facts.values()):
                raise ValueError('material receipt differs from the ordinary resolver')
            result['usable'] = True
        except (ValueError,KeyError,OSError) as error:
            result['unavailable_reason'] = str(error)
    return result


def _validate_request(root, packet, request):
    """Validate authority/bindings, not mathematical equivalence or sufficiency."""
    if (not isinstance(request,dict) or set(request) != set(_REQUEST['required']) or
            any(not isinstance(v,str) for v in request.values()) or
            any(not request[k].strip() for k in request if k != 'target_scope')):
        raise ValueError('bridge request needs a complete string interface and explicit correspondence')
    network = ContinuousNetwork(root)
    claim = network.claim(request['target_claim_id'])
    if (packet['claim'] != asdict(claim) or packet['study'].get('claim_id') != claim.obligation_id or
            _normalize(packet['study']['scope']) != claim.context or
            _normalize(request['target_scope']) != claim.context):
        raise ValueError('target Claim/scope must be the selected Study in this problem')
    source = network.inspect_fact(request['source_fact_id'])
    inspected = [n for n in packet['material_notices'] if n.get('kind')=='BRIDGE_CANDIDATE_INSPECTION'
                 and n.get('study_id')==packet['study']['study_id']
                 and n.get('source_fact_id')==source['fact_id']]
    if (len(inspected)!=1 or inspected[0]['source_scope']!=source['scope'] or
            inspected[0]['exact_statement']!=source['statement'] or
            inspected[0]['provenance']['problem_id']!=network.problem_id or source['scope']==claim.context):
        raise ValueError('source must be an actually inspected cross-scope candidate with its original interface')
    auxiliary = ProofObligation.create(network.problem_id, claim.context, request['target_auxiliary_statement'])
    if auxiliary.obligation_id in (claim.obligation_id,network.target_id):
        raise ValueError('auxiliary cannot be the enclosing requirement or root Claim')
    return auxiliary


def materialize_once(problem_dir, *, invoker=None, on_event=None):
    """Run/resume one current pre-Worker opportunity, without retries or service.

    A changed checkout needs a new labelled run, never a forged old fingerprint.
    The enclosing PAUSED run is unchanged; evidence lives in its current visit.
    """
    root = Path(problem_dir).resolve()
    with run_lock(root/'continuous_run'):
        state, directory = _paths(root)
        if state['code_digest'] != _code_digest():
            raise ValueError('code fingerprint changed; create a new isolated evaluation run')
        if (state['runtime']['backend']=='injected') != (invoker is not None):
            raise ValueError('cannot change runtime backend')
        if state['status']!='PAUSED' or state.get('retry_role'):
            raise ValueError('materialization needs a paused pre-Worker opportunity without a pending retry')
        visit = directory.parent
        calls = [read_json(p) for p in (root/'continuous_run').glob('calls/*/request.json')]
        if (visit/'packet.json').exists() or any(r['scope'].startswith(str(state['step'])+':') and
                r['label'] not in ('continuous_selector','continuous_selector_bridge') for r in calls):
            raise ValueError('proof service already started; cannot replace its frozen material packet')
        backend = invoker
        if backend is None:
            runtime = state['runtime']
            if real_runtime(runtime['image']) != runtime:
                raise ValueError('runtime fingerprint changed')
            backend = SolInvoker(image=runtime['image'], timeout_seconds=runtime['timeout_seconds'],
                                 audit_dir=root/'continuous_run/invocations')
        run = _Research(root,state,backend,on_event)
        return _materialize_locked(run, invoker=invoker, on_event=on_event)


class _LoopPause(BaseException):
    """Carry loop control through the bridge without making it a bridge failure."""
    def __init__(self, reason):
        self.reason = reason


def _materialize_locked(run, *, packet=None, invoker=None, on_event=None, integrated=False):
    """Shared durable opportunity. Caller owns the continuous-run writer lock."""
    root, state = run.root, run.state
    directory = run.step_dir/'automatic_bridge'
    origin = {k:state[k] for k in ('run_id','step','code_digest','runtime','studies','schedule','settings','retries')}
    if integrated and (directory/'origin.json').exists():
        frozen = read_json(directory/'origin.json')
        # A successful material binding may already have changed the Study ref.
        # The original opportunity remains immutable; only its identity is checked.
        if any(frozen[k] != origin[k] for k in ('run_id','step','code_digest','runtime','settings','retries')):
            raise ValueError('bridge opportunity fingerprint changed')
    else:
        _write_once(directory/'origin.json',origin)
    if (directory/'state.json').exists() and read_json(directory/'state.json')['status'] in _TERMINAL:
        return read_materialization(root)
    phase = 'INSPECTION'
    bridge = None
    def save(**value):
        write_json(directory/'state.json', {**({'bridge_id':bridge['bridge_id']} if bridge else {}), **value})
    try:
        path = directory/'inspection_packet.json'
        if not path.exists():
            _write_once(path, packet if packet is not None else run.select_work(ContinuousNetwork(root)))
            run.event('inspection_saved')
        packet = read_json(path)
        inspections = [n for n in packet['material_notices'] if n.get('kind')=='BRIDGE_CANDIDATE_INSPECTION']
        if not inspections or packet['claim'] is None:
            save(status='NO_BRIDGE_REQUEST',reason='No inspected cross-scope candidate and target Claim.')
            return read_materialization(root)
        if ContinuousNetwork(root).truth(packet['claim']['obligation_id']) != 'OPEN':
            raise ValueError('enclosing requirement is no longer OPEN')
        phase = 'SELECTOR'
        response = run.invoker('selector-bridge').invoke(prompt=_PROMPT+json.dumps(packet,ensure_ascii=False),
            schema=_SCHEMA,label='continuous_selector_bridge')
        _write_once(directory/'selector_result.json',response)
        phase = 'REQUEST'
        if (set(response)!=set(_SCHEMA['required']) or not isinstance(response['reason'],str)
                or not response['reason'].strip()):
            raise ValueError('malformed Selector bridge decision')
        if response['action']=='IGNORE':
            if response['bridge_request'] is not None:
                raise ValueError('IGNORE must not carry a bridge request')
            save(status='NO_BRIDGE_REQUEST',reason=response['reason'])
            return read_materialization(root)
        request = response['bridge_request']
        if _write_once(directory/'bridge_request.json',request):
            run.event('bridge_request_saved')
        _validate_request(root,packet,request)
        phase = 'RUNTIME'
        if integrated and state['runtime']['backend'] != 'injected':
            if real_runtime(state['runtime']['image']) != state['runtime']:
                raise ValueError('runtime fingerprint changed')
        phase = 'BRIDGE'
        bridge = _bridge_fact_locked(root,source_fact_id=request['source_fact_id'],
            target_context=request['target_scope'],target_goal=request['target_auxiliary_statement'],
            correspondence=request['correspondence'],invoker=invoker,on_event=on_event,
            image=state['runtime'].get('image','noespire-codex-isolated:local'),
            expected_runtime=state['runtime'] if integrated else None,
            on_prepared=lambda key:_write_once(directory/'bridge_reference.json',{'bridge_id':key}))
        if bridge['status']!='COMPLETED' or not bridge['usable']:
            save(status='PAUSED' if bridge['status']=='PAUSED' else 'BRIDGE_FAILED',
                 bridge_id=bridge['bridge_id'],reason=bridge.get('reason') or bridge.get('unavailable_reason'))
            if integrated and bridge['status']=='PAUSED':
                raise RunStopped('RUNTIME_UNAVAILABLE')
            return read_materialization(root)
        phase = 'MATERIALIZATION'
        _validate_request(root,packet,request)
        network = ContinuousNetwork(root)
        refs = ['fact:'+f['fact_id'] for f in packet['accepted_facts']] + ['fact:'+bridge['fact_id']]
        facts, _, _ = load_materials(root,packet['study'],refs,state['studies'],network)
        if not set(packet['required_fact_ids']).issubset(facts):
            raise ValueError('missing required local Fact')
        # Revalidate and retain existing local premises; add only the new
        # auxiliary. Foreign inspections never become accepted predecessors.
        output = {**packet,'accepted_facts':list(facts.values())}
        closure = [f.fact_id for f in FactGraph(root).supporting_closure(bridge['fact_id'])]
        if request['source_fact_id'] not in closure:
            raise ValueError('bridge lost source lineage')
        _write_once(directory/'material_packet.json',output)
        _write_once(directory/'closure.json',closure)
        save(status='MATERIALIZED',bridge_id=bridge['bridge_id'],fact_id=bridge['fact_id'],closure=closure)
        run.event('materialized',fact_id=bridge['fact_id'])
    except _LoopPause as error:
        save(status='PAUSED',reason=error.reason,phase=phase)
        raise RunStopped(error.reason) from error
    except RunStopped as error:
        save(status='INTERRUPTED' if error.reason=='INTERRUPTED' else 'PAUSED',reason=error.reason,phase=phase)
        if integrated and error.reason != 'INTERRUPTED':
            raise
    except subprocess.TimeoutExpired as error:
        if integrated and phase=='RUNTIME':
            save(status='PAUSED',reason=str(error),phase=phase)
            raise RunStopped('RUNTIME_UNAVAILABLE') from error
        save(status='TIMEOUT',reason=str(error),phase=phase)
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError,RuntimeError,_InvocationFailure) as error:
        if integrated and phase=='RUNTIME':
            save(status='PAUSED',reason=str(error),phase=phase)
            raise RunStopped('RUNTIME_UNAVAILABLE') from error
        status = ('INVALID_BRIDGE_REQUEST' if phase=='REQUEST' and isinstance(error,(ValueError,KeyError,TypeError))
                  else 'MATERIALIZATION_FAILED' if phase=='MATERIALIZATION' else 'ERROR')
        save(status=status,reason=f'{type(error).__name__}: {error}',phase=phase)
    return read_materialization(root)

def prepare_loop_materials(run, network):
    """Refresh a selected opportunity before freezing its ordinary Worker packet.

    Bridging neither completes a visit nor commits its proposed next_schedule.
    Immutable material-only Study metadata keeps future navigation aware of F'.
    """
    directory = run.step_dir/'automatic_bridge'
    inspection = directory/'inspection_packet.json'
    packet = read_json(inspection) if inspection.exists() else run.select_work(network)
    if not directory.exists() and not any(n.get('kind')=='BRIDGE_CANDIDATE_INSPECTION'
                                         for n in packet['material_notices']):
        return packet

    def event(name, details):
        try:
            run.event(name, **details)
        except RunStopped as error:
            raise _LoopPause(error.reason) from error

    result = _materialize_locked(run, packet=packet, integrated=True,
        invoker=run.backend if run.state['runtime']['backend']=='injected' else None, on_event=event)
    if not result['usable']:
        return {**packet, 'material_notices':[*packet['material_notices'],
            {'kind':'BRIDGE_RESULT','status':result['status'],'reason':result.get('reason') or result.get('unavailable_reason'),
             'evidence_ref':(directory/'state.json').relative_to(run.directory).as_posix()}]}
    packet = read_json(directory/'material_packet.json')
    key = packet['study']['study_id']
    ref = f"studies/{key}/materials-{run.state['step']:08d}.json"
    if not (run.directory/ref).exists():
        previous = run.state['studies'][key]
        study = read_json(run.directory/previous)
        _write_once(run.directory/ref, {**study,
            'known_fact_ids':list(dict.fromkeys([*study.get('known_fact_ids',[]),result['fact_id']])),
            'previous_material_revision':previous})
    if run.state['studies'][key] != ref:
        run.state['studies'][key] = ref
        run.save()
        run.event('bridge_materials_bound',fact_id=result['fact_id'],study_id=key)
    return packet



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','resume','status'])
    parser.add_argument('workspace')
    args = parser.parse_args(argv)
    result = read_materialization(args.workspace) if args.command=='status' else materialize_once(args.workspace)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='MATERIALIZED' and result['usable'] else 1


if __name__=='__main__':
    raise SystemExit(main())
