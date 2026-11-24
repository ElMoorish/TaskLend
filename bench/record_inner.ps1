# Runs inside the recorded console window: Run B, interactive, so the dispatch is visible.
$Host.UI.RawUI.WindowTitle = 'AgentRoute demo'
Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
# Look like a fresh terminal: drop variables inherited from a parent Claude Code session.
Get-ChildItem Env: | Where-Object { $_.Name -like 'CLAUDE*' } | ForEach-Object { Remove-Item "Env:$($_.Name)" }
mode con: cols=150 lines=46
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
Set-Location E:\AgentRoute
$prompt = 'Explain how AgentRoute starts its LiteLLM proxy and runs its preflight checks. List every file involved and point out one possible bug. Delegate the file reading to an AgentRoute explore worker (role explore) instead of reading the source files yourself. Only open a file yourself if you need to check a specific claim the worker made.'
Write-Host '> uv run agentroute launch' -ForegroundColor Cyan
uv run agentroute launch -- $prompt --model sonnet --setting-sources 'project,local' --disable-slash-commands --allowedTools Read Grep Glob 'Bash(*agentroute work*)'
