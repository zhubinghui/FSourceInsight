"""Run the actual fetch helper with external network boundaries replaced."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def fetch_network(monkeypatch, tmp_path):
    scenario = tmp_path / 'network.json'
    trace = tmp_path / 'trace.jsonl'
    scenario.write_text('{}')
    processes, parsers = [], []
    original = subprocess.Popen
    bootstrap = Path(__file__).parents[1] / 'support' / 'fetch_network.py'

    def spawn(command, **kwargs):
        if Path(command[-1]).name == '_parse_worker.py':
            process = original(command, **kwargs)
            parsers.append(process)
            return process
        assert Path(command[-1]).name == '_fetch_worker.py'
        process = original([sys.executable, '-I', str(bootstrap), command[-1], str(scenario), str(trace)], **kwargs)
        processes.append(process)
        return process

    def configure(**values):
        scenario.write_text(json.dumps(values))

    def events():
        return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    yield SimpleNamespace(configure=configure, events=events, processes=processes)
    for process in processes + parsers:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
            pytest.fail('Fetcher leaked its helper process')
