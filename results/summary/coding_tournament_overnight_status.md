# Coding Tournament Overnight Status

Date: 2026-06-26
Machine: configured GEEKOM host / configured GEEKOM host
Repo: `<repo-root>`
Endpoint: `http://127.0.0.1:13305/api/v1`

## Summary

The requested preflight agent sanity check and coding-model tournament completed. The long all-model benchmark sweep was not run; this run focused on the coding tournament.

No commits were made and nothing was pushed.

## Agent Workflow Sanity Check

Command:

```powershell
python scripts\run_agent_workflow.py --models "Nemotron-Cascade-2-30B-A3B" --trials 3
```

Final sanity run:

- Run ID: `agent_workflow_20260626-130557`
- Result: 0/3 passed
- Pattern: plan and metadata-tool use usually worked, but the final emitted file/verification step still did not pass.
- Policy compliance: `preserve_title` improved to 3/3 after scoring was made casing-tolerant, but `tool_before_edit`, `no_fabricated_year`, and `honest_verification` remained 0/3.
- Decision: exclude agent workflow from the overnight scoring recommendation until the task/prompt/scoring loop is redesigned or validated separately.

## Prep Changes Made Before Tournament

The following framework fixes were made before the final tournament result:

- `scripts\run_coding_tasks.py`: explicit comma-separated model lists are now honored; the `uses=coding` filter is applied only for default `--models all`.
- `src\geekom_benchmarks\runners\coding.py`: code extraction now falls back to the first `import`, `from ... import`, or `def ...` line when a model returns prose before code without a fenced code block.
- `src\geekom_benchmarks\runners\coding.py`: the static safe-delete grader now treats `is_file()` / `isfile()` as a valid guard that skips directories.
- `src\geekom_benchmarks\runners\agent.py`: agent file-block scoring is casing-tolerant for `TITLE:` and `YEAR:` labels.
- `src\geekom_benchmarks\clients\lemonade.py`: blocking responses fall back to `reasoning_content` when `message.content` is empty.

Validation:

- `python -m compileall src scripts` passed.
- A first comparable coding run (`coding_20260626-130947`) exposed the grader fairness issues and was superseded by the final fair run.

## Final Coding Tournament

Command:

```powershell
python scripts\run_coding_tasks.py --models "Qwen3-Coder-30B-A3B,Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B,Qwen3.6-35B-A3B,gpt-oss-20b"
```

Run ID: `coding_20260626-132144`

Raw results:

`results\raw\coding\coding_20260626-132144.jsonl`

Summary:

`results\summary\coding_20260626-132144.json`

Total: 16/20 task passes.

| Model | Passed | Total | Mean score | Approx elapsed |
| --- | ---: | ---: | ---: | ---: |
| Qwen3-Coder-30B-A3B | 4 | 4 | 1.00 | 33.3s |
| gpt-oss-20b | 4 | 4 | 1.00 | 99.6s |
| Qwen3-30B-A3B | 3 | 4 | 0.75 | 132.1s |
| Nemotron-Cascade-2-30B-A3B | 3 | 4 | 0.75 | 138.5s |
| Qwen3.6-35B-A3B | 2 | 4 | 0.50 | 231.0s |

Tasks:

- `fix_bug`
- `refactor_dedupe`
- `windows_path_repair`
- `detect_unsafe_delete`

## Interpretation

Primary coding recommendation:

`Qwen3-Coder-30B-A3B`

It tied gpt-oss-20b on score at 4/4, but completed the task set much faster in this run and is purpose-built for coding.

Secondary coding/general recommendation:

`gpt-oss-20b`

It also scored 4/4 and handled the Windows path repair and safe-delete tasks cleanly, but took roughly 3x longer than Qwen3-Coder on this task set.

Useful generalist:

`Qwen3-30B-A3B`

It scored 3/4 and was the only non-coder MoE besides gpt-oss/Nemotron to pass the safe-delete static task in the earlier comparable run. In the final fair run it also scored 3/4.

Not recommended as a coding default from this run:

- `Nemotron-Cascade-2-30B-A3B`: still useful for tool reliability, but coding score was 3/4 and slower than Qwen3-Coder.
- `Qwen3.6-35B-A3B`: slowest and lowest score in this coding tournament.

## Reports

Generated after the tournament:

- Latest JSON: `results\summary\latest_summary.json`
- Stamped JSON: `results\summary\summary_20260626-133324.json`
- Latest CSV: `results\summary\latest_summary.csv`
- Latest HTML: `results\reports\latest_report.html`
- Stamped HTML: `results\reports\report_20260626-133324.html`

## Remaining Operational Constraints

- Results are uncommitted. Commit result files and framework fixes only after review.
- Do not push without explicit user instruction.
- The agent workflow benchmark remains unsuitable for overnight ranking until separately fixed.
- The coding tournament is still a compact deterministic benchmark, not a full software-engineering eval. A future expanded tournament should add patch/diff application, unit-test generation, traceback repair, multi-file refactor, and safer file-operation scenarios.
