param(
    [string]$RepoPath = ".",
    [string]$Config = "config/settings.example.yaml",
    [string]$BaseBranch = "main"
)

python -m app.cli run `
  --repo $RepoPath `
  --requirement-file app/examples/sample_requirement.md `
  --base-branch $BaseBranch `
  --config $Config
