# Arc-GIS-Python-Tools

A collection of ArcGIS Pro script tools built with ArcPy.

---

## Tools

| Tool | Description |
|------|-------------|
| [Feature Class Field Builder](Feature_Class_Field_Builder/) | Creates or appends fields to a feature class. |
| [UDF](UDF/) | User-Defined Functions helper. |

---

## Contributing

### Do NOT replace scripts with stubs

Each `.py` file in this repo is a **complete, functional ArcGIS Pro script tool**.
Never commit a file that replaces the full implementation with a placeholder or stub
(e.g., a function with `# logic goes here` and no real body).

If you need to change a function signature or add a parameter, make an **incremental
change** to the existing file—do not delete the surrounding implementation.

A GitHub Actions workflow (`.github/workflows/guard-script-size.yml`) will fail the
CI check if any critical script drops below a minimum line-count threshold.
A `pre-commit` hook enforces the same check locally before you can commit.

### Setting up pre-commit (recommended)

```bash
pip install pre-commit
pre-commit install        # installs the git hook
pre-commit run --all-files  # run all hooks manually once
```

### How to revert an accidental commit

If a commit accidentally replaced a script with a stub (or made any other
destructive change), **revert it** rather than resetting history:

```bash
git switch main
git pull

# Replace <BAD_SHA> with the commit hash you want to undo
git revert <BAD_SHA>

git push
```

This creates a new commit that undoes the bad commit, keeping full history intact.

> **Avoid `git reset --hard`** on commits that have already been pushed to GitHub—
> it rewrites history and can break collaborators' branches.

### Branch protection (maintainers)

To prevent direct pushes and enforce review:

1. Go to **Settings → Branches** in the GitHub repo.
2. Add a branch protection rule for `main`.
3. Enable: *Require a pull request before merging*, *Require status checks to pass*
   (select the `Guard Script Size` workflow), and *Require at least 1 approving review*.

---