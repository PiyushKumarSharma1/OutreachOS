import json
import subprocess
import sys
import os


def _rpc(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line) if line.strip() else None


def test_mcp_server_full_flow(tmp_path):
    env = {**os.environ, "OUTREACHOS_DB": str(tmp_path / "mcp.db")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "outreachos.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True,
        cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
        env=env)

    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"]["name"] == "outreachos"

        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in tools["result"]["tools"]]
        assert "outreachos_run_cycle" in names and "outreachos_overview" in names

        created = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "outreachos_create_campaign",
                                         "arguments": {"name": "mcp-camp",
                                                       "industries": ["SaaS"],
                                                       "titles": ["VP of Sales"]}}})
        payload = json.loads(created["result"]["content"][0]["text"])
        assert payload["name"] == "mcp-camp"

        ran = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "outreachos_run_cycle",
                                     "arguments": {"campaign": "mcp-camp", "limit": 10}}})
        summary = json.loads(ran["result"]["content"][0]["text"])["summary"]
        assert "hunted" in summary and "booked" in summary

        overview = _rpc(proc, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                               "params": {"name": "outreachos_overview", "arguments": {}}})
        data = json.loads(overview["result"]["content"][0]["text"])
        assert any(c["name"] == "mcp-camp" for c in data["campaigns"])

        unknown = _rpc(proc, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                              "params": {"name": "nope", "arguments": {}}})
        assert unknown["error"]["code"] == -32602
    finally:
        proc.stdin.close()
        proc.terminate()
