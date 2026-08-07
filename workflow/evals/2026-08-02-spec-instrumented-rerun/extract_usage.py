#!/usr/bin/env python3
"""Extract per-agent usage numbers from Claude Code workflow transcripts (agent-*.jsonl).

Usage: python3 extract_usage.py <transcript-dir>

Counts, per agent file:
- requests      = assistant messages carrying a usage block (one per API request)
- tool_calls    = tool_use blocks in assistant messages
- output_tokens = sum of usage.output_tokens
- peak_context  = max over requests of (input_tokens + cache_read_input_tokens
                  + cache_creation_input_tokens + output_tokens) — the fullest the
                  context window got during the pass
- wall_s        = last timestamp minus first timestamp

Stdlib only.
"""
import datetime
import glob
import json
import os
import sys

d = sys.argv[1]
for f in sorted(glob.glob(d + '/agent-*.jsonl')):
    aid = os.path.basename(f)[6:-6]
    reqs = out_tok = peak = tools = 0
    t0 = t1 = None
    for line in open(f):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = e.get('timestamp')
        if ts:
            t0 = t0 or ts
            t1 = ts
        m = e.get('message') or {}
        if m.get('role') != 'assistant':
            continue
        u = m.get('usage')
        if u:
            reqs += 1
            out_tok += u.get('output_tokens', 0)
            ctx = (u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
                   + u.get('cache_creation_input_tokens', 0) + u.get('output_tokens', 0))
            peak = max(peak, ctx)
        for c in (m.get('content') or []):
            if isinstance(c, dict) and c.get('type') == 'tool_use':
                tools += 1

    def p(t):
        return datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))

    wall = (p(t1) - p(t0)).total_seconds() if t0 and t1 else 0
    print(f"{aid}  requests={reqs}  tool_calls={tools}  output_tokens={out_tok}"
          f"  peak_context={peak}  wall_s={wall:.0f}")
