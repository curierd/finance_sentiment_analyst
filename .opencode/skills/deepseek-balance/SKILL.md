---
name: deepseek-balance
description: Query DeepSeek API account balance / remaining quota / 余额 using the DEEPSEEK_API_KEY environment variable. Use this skill whenever the user asks about DeepSeek credit, remaining balance, available quota, API usage cost, 余额, 额度, 充值, or any DeepSeek billing question — even if they don't name the skill or endpoint explicitly. Triggers on phrases like "DeepSeek 余额", "查一下 API 剩余额度", "how much DeepSeek credit do I have left", "DeepSeek quota", "还剩多少", "DeepSeek billing".
---

# DeepSeek Balance

Query DeepSeek's `/user/balance` endpoint using `DEEPSEEK_API_KEY` and present the result as a clean table.

## Cross-platform

Runs on **Linux / macOS / Windows** with the same entry point. The bundled script `scripts/check_balance.py` is pure-Python (stdlib only) and picks the right fallback per platform.

## When to use

- User asks for DeepSeek account balance / 余额 / 额度 / quota / credit
- User mentions DeepSeek billing or wants to check if they can keep calling the API
- User wants a one-shot check before/after a batch job

## Environment-variable visibility

Claude Code's bash subshell inherits env vars **at spawn time**. A key set **after** Claude started won't be visible to the Python child. The script handles this with platform-specific fallbacks:

| Source | Platform | When it applies |
|---|---|---|
| `os.environ['DEEPSEEK_API_KEY']` | all | User did `export` before launching Claude (normal Linux/macOS case) |
| Windows User scope (powershell probe) | win32 | User added DEEPSEEK_API_KEY in 系统属性 → 环境变量 after Claude started |
| Windows Machine scope (powershell probe) | win32 | Same, but Machine scope |
| `~/.bashrc`, `~/.zshrc`, `~/.profile`, `~/.bash_profile` | Linux/macOS | Desktop launcher started Claude without sourcing rc files |

If all sources fail, the script exits with code 2 and a clear, platform-specific hint. **Do not retry** in that case — surface the error to the user.

## Procedure

1. Invoke the bundled script:
   ```
   python3 <skill>/scripts/check_balance.py
   ```
   (Use `python` instead of `python3` on Windows if that's the default.)
2. Parse the output. The script prints:
   - `[auth] key prefix=sk-XXXX len=N` (safe to show — never echo the full key)
   - `=== RAW JSON ===` with the full response
   - `=== SUMMARY ===` with one row per currency showing total / granted / topped_up

## Output to user

Present a markdown table — always in CNY unless the response shows otherwise:

| 字段 | 值 |
|---|---|
| 账户状态 | is_available: true / false |
| 币种 | CNY |
| **总余额** | ¥xxx.xx |
| 赠送余额 | ¥x.xx |
| 充值余额 | ¥xxx.xx |

Followed by a one-line interpretation (e.g., "可用 ¥824.66，全部来自充值").

## Security

- Never echo the full API key. The script already truncates to prefix + length; do not change that.
- If the user pastes a key in chat, suggest they revoke it after the call.
- Don't write the API key to any file under the repo.

## Don't do

- Don't retry on `is_available: false` — surface the error, the account itself is the problem.
- Don't fetch balance more than once per user request; no need to poll.
- Don't add a separate PowerShell script — keep the skill single-language (Python).