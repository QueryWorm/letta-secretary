#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone

SERVER = "letta-letta-server-1"
LITELLM = "letta-litellm-1"
CHANNELS = "letta-letta-code-channels-1"

RE_HTTP = re.compile(r'HTTP Request: POST http://litellm:4000/chat/completions "HTTP/1.1 (\d+)')
RE_RETRY = re.compile(r'Retrying request to /chat/completions in ([\d.]+) seconds')
RE_STREAM = re.compile(r'Stream processing complete. Received (\d+) events')
RE_CTX = re.compile(r'Context token estimate after LLM request: (\d+)')
RE_STEP = re.compile(r'Running final update. Step Progression: (\w+)')
RE_RUN = re.compile(r'Run (run-[\w-]+).*?completed')
RE_CHANNEL_DROP = re.compile(r'drop non-self message')
RE_CHANNEL_CONN = re.compile(r'Connected as (\S+)')


def docker_logs(container, since):
    out = subprocess.run(
        ["docker", "logs", "-t", container, "--since", str(since) + "m"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    ).stdout
    events = []
    for line in out.splitlines():
        m = re.match(r"^(\S+) (.*)$", line)
        if not m:
            continue
        try:
            t = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except ValueError:
            continue
        events.append((t, m.group(2)))
    return events


def classify(msg):
    m = RE_HTTP.search(msg)
    if m:
        return ("http", int(m.group(1)))
    m = RE_RETRY.search(msg)
    if m:
        return ("retry", float(m.group(1)))
    m = RE_STREAM.search(msg)
    if m:
        return ("stream", int(m.group(1)))
    m = RE_CTX.search(msg)
    if m:
        return ("ctx", int(m.group(1)))
    m = RE_STEP.search(msg)
    if m:
        return ("step", m.group(1))
    m = RE_RUN.search(msg)
    if m:
        return ("run_end", m.group(1))
    if "Chat Completions stream iterator exited" in msg:
        return ("iter_end", None)
    m = RE_CHANNEL_DROP.search(msg)
    if m:
        return ("wa_drop", None)
    m = RE_CHANNEL_CONN.search(msg)
    if m:
        return ("wa_conn", m.group(1))
    if "disconnected" in msg and "reconnecting" in msg:
        return ("wa_disconn", None)
    stripped = msg.strip()
    if stripped.startswith("{"):
        try:
            j = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if j.get("object") == "chat.completion":
            return ("llm_done", j)
    return None


def fmt_dt(t):
    return t.strftime("%H:%M:%S.%f")[:-3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=120, help="минут назад")
    args = ap.parse_args()

    all_events = []
    for c in (SERVER, LITELLM, CHANNELS):
        for t, msg in docker_logs(c, args.since):
            cls = classify(msg)
            if cls is None:
                continue
            kind, val = cls
            if kind == "llm_done":
                j = val
                model = j.get("model", "?")
                prov = j.get("provider", "?")
                u = j.get("usage", {})
                fin = j.get("choices", [{}])[0].get("finish_reason", "?")
                extra = f"model={model} provider={prov} tok={u.get('total_tokens', '?')} finish={fin}"
                all_events.append((t, c, kind, "", extra))
                continue
            all_events.append((t, c, kind, val, ""))

    all_events.sort(key=lambda e: e[0])

    ends = [(t, v) for t, c, k, v, _ in all_events if k == "run_end"]

    def assign_run(t):
        best = None
        for et, rid in ends:
            if et >= t:
                return rid
        return "active"

    runs = {}
    for t, c, kind, val, extra in all_events:
        run = assign_run(t)
        runs.setdefault(run, []).append((t, c, kind, val, extra))

    label = {
        "http": lambda v: f"POST->litellm {v}",
        "retry": lambda v: f"retry через {v}s",
        "stream": lambda v: f"stream complete ({v} events)",
        "ctx": lambda v: f"ctx токенов {v}",
        "step": lambda v: f"step {v}",
        "iter_end": lambda v: "stream iterator exit",
        "run_end": lambda v: "RUN DONE",
        "wa_drop": lambda v: "wa: drop non-self",
        "wa_conn": lambda v: f"wa: connect {v}",
        "wa_disconn": lambda v: "wa: disconnect/reconnect",
        "llm_done": lambda v: "LLM ответил",
    }

    for run, evs in runs.items():
        base = evs[0][0]
        print(f"### run {run}  (старт {fmt_dt(base)} UTC)")
        print(f"{'DELTA':<10} {'SRV':<12} {'ШАГ':<24} ДЕТАЛИ")
        for t, c, kind, val, extra in evs:
            delta = t - base
            print(f"{'+'+format(delta.total_seconds(), '.2f')+'s':<10} {c.replace('letta-',''):<12} {label[kind](val):<24} {extra}")
        print()

    print("=== СВОДКА: LLM-запросы (server -> litellm -> LLM) ===")
    for run, evs in runs.items():
        if not run.startswith("run-"):
            continue
        server_evs = [(t, k, v, e) for t, c, k, v, e in evs if c == SERVER or k == "llm_done"]
        if not any(k in ("http", "llm_done") for _, k, _, _ in server_evs):
            continue
        print(f"{run}:")
        prev = None
        for t, k, v, extra in server_evs:
            d = (t - prev).total_seconds() if prev else 0.0
            prev = t
            print(f"   {fmt_dt(t)}  +{d:7.2f}s  {label[k](v)} {extra}")
        total = (server_evs[-1][0] - server_evs[0][0]).total_seconds()
        print(f"   итого: {total:.2f}s")

if __name__ == "__main__":
    main()
