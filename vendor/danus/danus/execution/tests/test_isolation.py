"""Capability permissions and real no-model container boundary checks."""
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest
from danus.core import LocalMemory
from danus.execution.capabilities import CapabilityBroker, CapabilityTool
from danus.execution.isolation import DockerRoundRunner, provider_config
from danus.execution.layout import WorkerLayout
from danus.execution import loop


SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'string'}},
          'required': ['text'], 'additionalProperties': False}


def test_allowlist_argument_validation_and_empty_role():
    calls = []
    broker = CapabilityBroker([CapabilityTool('local_append', 'Unverified note', SCHEMA,
                                              lambda arg: calls.append(arg) or {'saved': True})])
    try:
        assert broker.dispatch({'method': 'list'})['tools'][0]['name'] == 'local_append'
        for request in ({'method': 'call', 'name': 'fact_revoke', 'arguments': {}},
                        {'method': 'call', 'name': 'local_append', 'arguments': {'text': 'x', 'path': '/truth'}},
                        {'method': 'call', 'name': 'local_append', 'arguments': {'text': 12}}):
            with pytest.raises(Exception):
                broker.dispatch(request)
        assert not calls
        assert broker.dispatch({'method': 'call', 'name': 'local_append',
                                'arguments': {'text': 'partial proof'}})['result'] == {'saved': True}
        assert calls == [{'text': 'partial proof'}]
    finally:
        broker.server.server_close()
    empty = CapabilityBroker([])
    try:
        with pytest.raises(PermissionError):
            empty.dispatch({'method': 'call', 'name': 'local_append', 'arguments': {'text': 'x'}})
    finally:
        empty.server.server_close()


def test_unauthenticated_request_cannot_read_or_write():
    calls = []
    with CapabilityBroker([CapabilityTool('write', 'note', SCHEMA, calls.append)], bind='127.0.0.1') as b:
        endpoint = f'http://127.0.0.1:{b.port}/rpc'
        data = json.dumps({'method': 'call', 'name': 'write', 'arguments': {'text': 'x'}}).encode()
        for token in ('', 'wrong'):
            request = urllib.request.Request(endpoint, data=data,
                        headers={'Authorization': 'Bearer ' + token})
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request, timeout=5)
            assert exc.value.code == 403
        request = urllib.request.Request(endpoint, data=data,
                    headers={'Authorization': 'Bearer ' + b.token})
        assert json.loads(urllib.request.urlopen(request, timeout=5).read()) == {'result': None}
    assert calls == [{'text': 'x'}]


def test_provider_configuration_drops_host_instructions_and_tools(tmp_path):
    p = tmp_path / 'config.toml'
    p.write_text('''model_provider="sample"
service_tier="priority"
notify=["secret-command"]
instructions="host-only"
[mcp_servers.unsafe]
command="shell"
[model_providers.sample]
name="test"
base_url="https://provider.invalid/v1"
wire_api="responses"
unknown_hook="must drop"
''', encoding='utf8')
    config = provider_config(p)
    assert set(config) == {'model_provider', 'service_tier', 'model_providers'}
    assert set(config['model_providers']['sample']) == {'name', 'base_url', 'wire_api'}


def fake_runner(tmp_path, tools=None):
    auth = tmp_path / 'auth'
    auth.mkdir()
    (auth / 'auth.json').write_text('{}', encoding='utf8')
    with patch.object(DockerRoundRunner, '_check', side_effect=lambda args:
                       'sha256:' + 'a' * 64 if args[0] == 'image' else 'codex test'):
        return DockerRoundRunner(auth_dir=auth, docker='docker', tools=tools)


def test_durable_runner_mounts_only_stage_and_credentials(tmp_path, monkeypatch):
    runner = fake_runner(tmp_path)
    wl = WorkerLayout(tmp_path / 'project' / 'workers' / 'lane')
    wl.dir.mkdir(parents=True)
    schema = wl.dir / 'schema.json'
    schema.write_text('{}', encoding='utf8')
    commands = []
    def fake_round(wl, role, prompt, log, timeout, **kwargs):
        process = kwargs['command_factory']()
        commands.append(process.argv)
        config = (process.cwd / 'config.toml').read_text(encoding='utf8')
        assert __import__('tomllib').loads(config)['permissions']['danus_local']['network']['enabled'] is False
        assert 'mcp_servers' not in config
        assert not (process.cwd / 'project').exists()
        (process.cwd / 'response.json').write_text('{"done":true}', encoding='utf8')
        log.write_text('public\n', encoding='utf8')
        return 124
    monkeypatch.setattr('danus.execution.isolation.run_round', fake_round)
    monkeypatch.setattr(runner, '_remove', lambda name: None)
    result = runner(wl, {'MODEL': 'gpt-5.6-sol', 'REASONING_EFFORT': 'xhigh'},
                    'task', wl.dir / 'public.jsonl', 600, schema_path=schema,
                    output_path=wl.dir / 'response.json')
    assert result == 124
    assert json.loads((wl.dir / 'response.json').read_text()) == {'done': True}
    command = commands[0]
    assert str(wl.dir) not in ' '.join(command)
    assert 'docker.sock' not in ' '.join(command)
    assert '--privileged' not in command
    assert runner.image_id in command
    mounts = [command[i+1] for i, x in enumerate(command) if x == '--mount']
    assert len(mounts) == 3
    assert sum('readonly' not in m for m in mounts) == 1
    assert not Path(mounts[0].split('src=', 1)[1].split(',dst=')[0]).exists()


def test_factory_uses_existing_loop_on_windows_and_cleanup_on_timeout(tmp_path, monkeypatch):
    wl = WorkerLayout(tmp_path / 'p' / 'workers' / 's')
    wl.dir.mkdir(parents=True)
    stopped = []
    class Proc:
        def wait(self, timeout):
            if timeout == 600:
                raise subprocess.TimeoutExpired('docker', timeout)
            return 0
        def terminate(self):
            stopped.append('client')
    monkeypatch.setattr(loop.subprocess, 'Popen', lambda *args, **kw: Proc())
    with patch.object(loop.os, 'name', 'nt'):
        result = loop.run_round(wl, {}, 'prompt', wl.dir / 'public.jsonl', 600,
                    safe_read_only=True, command_factory=lambda:
                    loop.ProcessCommand(['docker', 'run'], wl.dir, {}, lambda: stopped.append('container')))
    assert result == 124
    assert stopped == ['container', 'client']


@pytest.mark.skipif(os.environ.get('DANUS_RUN_DOCKER_PROBE') != '1', reason='explicit no-model Docker probe')
def test_real_container_permissions_and_capabilities(tmp_path):
    auth = tmp_path / 'auth'
    auth.mkdir()
    (auth / 'auth.json').write_text('{"sentinel":"not-a-real-credential"}', encoding='utf8')
    host_truth = tmp_path / 'private-truth'
    host_truth.write_text('host authority remains private', encoding='utf8')
    stage = tmp_path / 'stage'
    stage.mkdir()
    lane = tmp_path / 'project' / 'workers' / 'lane'
    memory = LocalMemory(lane)
    tools = [CapabilityTool('local_append', 'Persist unverified local note', SCHEMA,
                            lambda arg: memory.append('notes', arg))]
    runner = DockerRoundRunner(auth_dir=auth)
    with CapabilityBroker(tools) as broker:
        (stage / 'config.toml').write_text(runner._configuration(broker), encoding='utf8')
        shutil.copyfile(Path(__file__).parents[1] / 'mcp_proxy.cjs', stage / 'mcp_proxy.cjs')
        js = r'''
const fs=require('node:fs'), {spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
(async()=>{
assert(!fs.existsSync(HOST_PATH));
assert(!fs.existsSync('/var/run/docker.sock'));
let immutable=false;
try {fs.writeFileSync('/root/.codex/auth.json','changed')} catch(e){immutable=true}
assert(immutable);
let r=await fetch(URL,{method:'POST',body:JSON.stringify({method:'list'})});
assert.equal(r.status,403);
const messages=[{jsonrpc:'2.0',id:1,method:'initialize'},
{jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'local_append',arguments:{text:'durable before timeout'}}},
{jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'fact_revoke',arguments:{}}}];
const p=spawnSync('node',['/work/mcp_proxy.cjs'],{input:messages.map(x=>JSON.stringify(x)).join('\n')+'\n',
env:{...process.env,DANUS_CAPABILITY_URL:URL,DANUS_CAPABILITY_TOKEN:TOKEN},encoding:'utf8',timeout:10000});
assert.equal(p.status,0,p.stderr);
const replies=p.stdout.trim().split('\n').map(JSON.parse);
assert.equal(replies.find(x=>x.id===2).result.isError,false);
assert.equal(replies.find(x=>x.id===3).result.isError,true);
const inner=`const fs=require('node:fs'); let denied=false;try{fs.writeFileSync('/work/forbidden','x')}catch(e){denied=true};if(!denied)process.exit(3);fs.writeSync(1,'write_denied');const keepalive=setTimeout(()=>process.exit(8),7000);fetch(${JSON.stringify(URL)},{signal:AbortSignal.timeout(3000)}).then(()=>process.exit(4)).catch(()=>{clearTimeout(keepalive);fs.writeSync(1,'sandbox_network_and_write_denied')})`;
const s=spawnSync('codex',['sandbox','-P','danus_local','-C','/work','--','node','-e',inner],{encoding:'utf8',timeout:15000});
assert.equal(s.status,0,s.stderr);
assert(s.stdout.includes('sandbox_network_and_write_denied'),JSON.stringify(s));
console.log(JSON.stringify({host_private:true,auth_readonly:true,broker_authenticated:true,
allowlisted_memory:true,truth_tool_denied:true,sandbox_network_denied:true,sandbox_write_denied:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        js = 'const HOST_PATH=' + json.dumps(str(host_truth)) + ';const URL=' + json.dumps(
            f'http://host.docker.internal:{broker.port}/rpc') + ';const TOKEN=' + json.dumps(broker.token) + ';\n' + js
        (stage / 'probe.cjs').write_text(js, encoding='utf8')
        name = 'danus-probe-' + __import__('uuid').uuid4().hex
        try:
            result = subprocess.run(runner._command(name, stage, ['node', '/work/probe.cjs']),
                capture_output=True, text=True, encoding='utf8', timeout=40)
        finally:
            runner._remove(name)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)['allowlisted_memory'] is True
    assert host_truth.read_text() == 'host authority remains private'
    assert json.loads((auth / 'auth.json').read_text()) == {'sentinel': 'not-a-real-credential'}
    assert memory.read('notes')[0]['record']['text'] == 'durable before timeout'
