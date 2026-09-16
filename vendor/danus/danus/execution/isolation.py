"""Docker deployment for DANUS durable rounds and lane-bound MCP capabilities.

The host worker directory, truth store, project, and Docker socket are NEVER
mounted. Codex gets a fresh stage, read-only credentials/config, and only the
bound capability surface. No native-host or sandbox-bypass fallback exists.
The process lifecycle remains execution.loop.run_round.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4
try:
    import tomllib
except ImportError:  # Python 3.10, supported by upstream DANUS.
    import tomli as tomllib

from .capabilities import CapabilityBroker, CapabilityTool
from .loop import ProcessCommand, run_round


class IsolationUnavailable(RuntimeError):
    pass


def _toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if type(value) is bool:
        return 'true' if value else 'false'
    if type(value) is int:
        return str(value)
    if isinstance(value, list):
        return '[' + ','.join(_toml(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(_toml(k) + '=' + _toml(v) for k, v in value.items()) + '}'
    raise ValueError('unsupported provider config value')


def provider_config(path: Path) -> dict:
    """Copy connection settings only, never hooks/MCP/plugins/instructions/trust."""
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    result = {key: raw[key] for key in ('model_provider', 'service_tier') if key in raw}
    selected = raw.get('model_provider')
    if selected and selected != 'openai':
        provider = raw.get('model_providers', {}).get(selected)
        if not isinstance(provider, dict):
            raise IsolationUnavailable('selected provider settings missing')
        allowed = {'name', 'base_url', 'wire_api', 'env_key', 'requires_openai_auth',
                   'env_http_headers', 'http_headers', 'query_params',
                   'supports_websockets', 'request_max_retries', 'stream_max_retries',
                   'stream_idle_timeout_ms', 'experimental_bearer_token'}
        result['model_providers'] = {selected: {k: v for k, v in provider.items() if k in allowed}}
    return result


def sandbox_config() -> dict:
    return {
        'approval_policy': 'never', 'sandbox_mode': 'read-only',
        'default_permissions': 'danus_local',
        'permissions': {'danus_local': {'extends': ':read-only',
                                       'network': {'enabled': False}}},
        'web_search': 'disabled', 'tools': {'web_search': False},
        'agents': {'enabled': False},
        'features': {name: False for name in ('multi_agent', 'multi_agent_mode', 'apps',
                    'plugins', 'remote_plugin', 'computer_use', 'browser_use',
                    'browser_use_external', 'in_app_browser', 'enable_mcp_apps',
                    'recommended_plugins', 'standalone_web_search', 'search_tool')},
    }


class DockerRoundRunner:
    def __init__(self, *, tools=None, auth_dir=None,
                 image='noespire-codex-isolated:local', docker=None):
        self.docker = docker or shutil.which('docker')
        if not self.docker:
            raise IsolationUnavailable('docker executable missing')
        self.auth_dir = Path(auth_dir or Path.home() / '.codex').resolve()
        if not (self.auth_dir / 'auth.json').is_file():
            raise IsolationUnavailable('Codex auth.json missing')
        self.tools = tools or (lambda worker, role: [])
        self.image = image
        self.config = provider_config(self.auth_dir / 'config.toml')
        self.image_id = self._check(['image', 'inspect', image, '--format', '{{.Id}}']).strip()
        if not self.image_id.startswith('sha256:'):
            raise IsolationUnavailable('unresolved Docker image identity')
        self.cli_version = self._check(['run', '--rm', '--entrypoint', 'codex',
                                       self.image_id, '--version']).strip()
        self.environment_names = set()
        for p in self.config.get('model_providers', {}).values():
            if p.get('env_key'):
                self.environment_names.add(p['env_key'])
            self.environment_names.update(p.get('env_http_headers', {}).values())
        if any(not isinstance(n, str) or not n or n not in os.environ for n in self.environment_names):
            raise IsolationUnavailable('provider environment credential unavailable')

    def _check(self, args):
        try:
            result = subprocess.run([self.docker, *args], capture_output=True, text=True,
                                    encoding='utf8', errors='replace', timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IsolationUnavailable('Docker preflight failed') from exc
        if result.returncode:
            raise IsolationUnavailable('Docker preflight returned nonzero')
        return result.stdout

    def fingerprint(self):
        config = dict(self.config, **sandbox_config())
        return {'backend': 'danus-docker-capabilities-v1', 'image': self.image_id,
                'cli': self.cli_version,
                'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                'proxy_sha256': hashlib.sha256(Path(__file__).with_name('mcp_proxy.cjs').read_bytes()).hexdigest(),
                'launcher_sha256': hashlib.sha256(Path(__file__).with_name('container_launch.cjs').read_bytes()).hexdigest()}

    def _configuration(self, broker):
        config = dict(self.config, **sandbox_config())
        if broker.tools:
            config['mcp_servers'] = {'danus': {
                'command': 'node', 'args': ['/work/mcp_proxy.cjs'],
                'env': {'DANUS_CAPABILITY_URL': f'http://host.docker.internal:{broker.port}/rpc',
                        'DANUS_CAPABILITY_TOKEN': broker.token},
                'startup_timeout_sec': 30, 'tool_timeout_sec': 600}}
        return '\n'.join(k + '=' + _toml(v) for k, v in config.items()) + '\n'

    def _command(self, name, stage, command):
        # Pin by image digest after preflight: changing a mutable tag cannot
        # silently alter an in-flight or recovered runtime.
        args = [self.docker, 'run', '--rm', '--name', name,
                '--security-opt', 'seccomp=unconfined',
                # UID 0 mapping in the nested read-only sandbox needs these
                # three capabilities; no SYS_ADMIN or privileged container.
                '--cap-drop', 'ALL', '--cap-add', 'SETUID', '--cap-add', 'SETGID', '--cap-add', 'SETFCAP',
                '--security-opt', 'no-new-privileges',
                '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
                '--tmpfs', '/root/.codex:rw,nosuid,nodev,size=64m',
                '--add-host', 'host.docker.internal:host-gateway',
                '--mount', f'type=bind,src={stage},dst=/work',
                '--mount', f'type=bind,src={self.auth_dir / "auth.json"},dst=/root/.codex/auth.json,readonly',
                '--mount', f'type=bind,src={stage / "config.toml"},dst=/root/.codex/config.toml,readonly',
                '-w', '/work', '--entrypoint', command[0]]
        for env in sorted(self.environment_names):
            args += ['--env', env]
        return args + [self.image_id, *command[1:]]

    def _remove(self, name):
        result = subprocess.run([self.docker, 'rm', '-f', name], capture_output=True, timeout=15)
        # Already removed by --rm is the ordinary completion case.
        if result.returncode and b'No such container' not in result.stderr:
            raise IsolationUnavailable('container cleanup failed')

    def __call__(self, wl, role, prompt, log_path, hard_timeout, *,
                 schema_path=None, output_path=None, safe_read_only=True):
        if not safe_read_only or schema_path is None or output_path is None:
            raise ValueError('isolated durable round requires schema/output and safe mode')
        if output_path.exists() or log_path.exists():
            raise FileExistsError('refusing to overwrite round evidence')
        bound_tools = list(self.tools(wl, role))
        name = 'danus-' + uuid4().hex
        with CapabilityBroker(bound_tools) as broker, tempfile.TemporaryDirectory(prefix='danus-') as tmp:
            stage = Path(tmp).resolve()
            (stage / 'schema.json').write_bytes(Path(schema_path).read_bytes())
            (stage / 'config.toml').write_text(self._configuration(broker), encoding='utf8')
            for name_file in ('mcp_proxy.cjs', 'container_launch.cjs'):
                shutil.copyfile(Path(__file__).with_name(name_file), stage / name_file)
            args = ['exec', '--ephemeral', '--ignore-rules', '--skip-git-repo-check',
                    '--model', role['MODEL'], '--config',
                    'model_reasoning_effort=' + _toml(role['REASONING_EFFORT']),
                    '--sandbox', 'read-only', '--json', '--color', 'never',
                    '--output-schema', '/work/schema.json',
                    '--output-last-message', '/work/response.json', '-C', '/work', '-']
            (stage / 'launch.json').write_text(json.dumps({'argv': args, 'prompt': prompt, 'timeout': hard_timeout}), encoding='utf8')
            command = self._command(name, stage, ['node', '/work/container_launch.cjs'])
            try:
                return run_round(wl, role, prompt, log_path, hard_timeout,
                    schema_path=schema_path, output_path=output_path, safe_read_only=True,
                    command_factory=lambda: ProcessCommand(command, stage, os.environ.copy(),
                                                            lambda: self._remove(name)))
            finally:
                self._remove(name)
                # Even timeout/error outputs are retained as unconfirmed evidence;
                # DurableRounds decides authority based solely on process status.
                response = stage / 'response.json'
                if response.exists():
                    if response.is_symlink() or not response.is_file() or response.stat().st_size > 16 * 1024 * 1024:
                        raise IsolationUnavailable('invalid response artifact')
                    with open(output_path, 'xb') as out:
                        out.write(response.read_bytes())
