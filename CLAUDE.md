# CLAUDE.md

## What this is

openneuro-t1-pipeline is a reproducible neuroimaging pipeline. It pulls public T1-weighted MRI scans from OpenNeuro on AWS S3 (anonymously), runs three FSL steps (BET skull stripping, FAST tissue segmentation, FLIRT registration to MNI space) through NiWrap in Docker, writes the outputs as BIDS derivatives, and saves a quality-check (QC) image for every step. Snakemake runs it per subject. It is an engineering project: it describes a pipeline and makes no research claims.

## Commands

Run these yourself. Never assume a check passes.

- Install or sync the environment: `uv sync`
- Run one subject: `uv run python3 -m openneuro_t1.run_subject --subject 01` (add `--force` to redo finished steps)
- Test: `uv run pytest -q` — single file: `uv run pytest tests/test_paths.py -q`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .` — check only: `uv run ruff format --check .`
- Workflow dry run (from step 2): `uv run snakemake -n`
- Workflow run (from step 2): `uv run snakemake --cores 4`
- Rule graph (from step 2): `uv run snakemake --rulegraph | dot -Tsvg > docs/rulegraph.svg`
- Setup check: `bash local/check_setup.sh` (never with `--aws`: that option signs in to the owner's AWS account)

Every Python command goes through `uv run`. Never `pip`, and never `python`: always `python3`.

## Architecture

Only what the file tree does not already show.

- Every output filename comes from `openneuro_t1.paths`, which builds BIDS derivative names in BIDS entity order. A hand-built filename anywhere, including in a Snakemake rule, is a bug: Snakemake decides what to rerun by matching paths, so one drifted name silently breaks resumability.
- `results/` is a BIDS derivatives dataset with its own `dataset_description.json` (`DatasetType` "derivative"). `resources/` holds downloaded and derived inputs: the raw OpenNeuro data, the TemplateFlow cache and the template brain. Both are regenerable and gitignored.
- The logic lives in functions in `src/openneuro_t1/`. `run_subject.py` is the single-subject command line, and from step 2 the Snakemake rules in `workflow/rules/` call the same functions. Don't put processing logic in a Snakefile.
- NiWrap's Docker runner is configured in exactly one place. Snakemake never wraps rules in containers of its own: one container layer only.
- `TEMPLATEFLOW_HOME` is set to `resources/templateflow` before TemplateFlow is imported, so the template lives with the project instead of a hidden cache.
- The FSL image is amd64 and runs under emulation on Apple Silicon. If it fails because of the platform, `DOCKER_DEFAULT_PLATFORM=linux/amd64` is the one allowed fix, and using it must be recorded.
- A step is finished only when all its outputs exist. A failed step must not leave partial outputs that a later run would mistake for finished ones.
- Every run that executes at least one step writes `results/provenance/sub-<id>_runinfo.json`: package versions, every Docker image used with its digest, and seconds per step. A run where every step is skipped leaves the existing record untouched, so it always describes the run that made the outputs.

## Invariants

Permanent. A change that breaks one is wrong even if it works and the tests pass.

- Only public OpenNeuro data, currently `ds000102`. Never add data from a patient, a hospital, or any dataset that is not openly licensed.
- Imaging data is never committed. `resources/`, `results/`, `logs/` and `local/` stay gitignored, and no `.nii` or `.nii.gz` file is ever tracked. `tests/test_invariants.py` enforces this; never weaken its checks.
- S3 reads are anonymous (`--no-sign-request`). No AWS credentials, profiles or account IDs in code, config, logs, tests or committed files. Secrets live in `.env` only. Anything that touches the owner's AWS account (EC2, billing) is the owner's to do.
- Don't use the AWS MCP server or AWS skills, and don't make AWS API calls with any profile. S3 reads use the AWS CLI with `--no-sign-request` only. EC2 and other account work happen only in a step that explicitly allows it.
- No research claims. The README, docs and write-ups describe what the pipeline does, not findings. Don't add statistics or interpretations of the outputs.
- Pinned versions: `niwrap==1.1.0` and `uv.lock`, and Docker images recorded by digest. Changing a pinned version needs approval.
- `README.md`, `LICENSE`, `CLAUDE.md` and `.github/pull_request_template.md` are owner-edited. Don't modify them unless a step's instructions say to.
- The reference repos in `~/Documents/CodeProjects/references/` are read-only. `rbc` is LGPL-licensed: read only its README and `docs/`, never its source code. Borrowed patterns are credited in the README.

## Conventions

Only the ones the existing code does not already demonstrate.

- Parameters live in `config/config.yaml`. No tool settings hard-coded in functions.
- Every processing step has a QC image. Describe what you see in each one, but never declare QC passed: the owner reviews the images before any output is trusted.
- Trust the installed NiWrap 1.1.0 signatures over its documentation, and record every mismatch you find. They feed an upstream documentation issue.
- matplotlib uses the `Agg` backend. Nothing opens a window.
- A new dependency needs approval first. Prefer the standard library and what is already installed. When approved, add it with `uv add`, never `pip`.

## Working agreement

- Never run `git add`, `git commit`, `git push`, or anything that rewrites history or discards work
  (`git reset --hard`, `git checkout -- .`, `git clean`, `--amend`). Commits are checkpoints the owner
  declares after reviewing the work.
- Do the described change, then stop. No unrequested features, refactors, renames, dependency bumps,
  or formatting sweeps beyond `ruff format` on files you touched.
- Read a file before editing it. Search for an existing helper before writing a new one.
- If an instruction cannot be followed as written, stop and report why. Do not substitute your own approach.
- If the task turns out to be larger or different from how it was described, stop and say so before continuing.
- Record every decision you had to make that the instructions did not specify.
- Never weaken a check to make it pass: no edited assertions, deleted or skipped tests, `pytest.skip`,
  `# noqa`, `# type: ignore`, `--no-verify`, or mocked-away failures. A failing check is a finding. Report it.
- Breakage you find that is unrelated to the task: report it, do not fix it.
- Leave nothing behind: no dead code, commented-out blocks, scratch files, or debug logging.

# The `local/` folder

`local/` is at the repository root and is gitignored. Nothing in it is ever committed, staged or pushed.
It holds two kinds of thing:

- **Files you produce for the owner and no one else:** `local/explanation.md` and `local/.pr-description.md`.
  Never write these to the repository root.
- **Files the owner gives you to refer to:** step prompts, `check_setup.sh`, briefs, screenshots, anything else
  handed over. Look here when the owner mentions a file you have not seen. Read them; do not edit or delete
  them unless asked.

Scratch output that no one asked for still belongs in the session scratchpad, not here. If `local/` does
not exist, create it. Anything you put there must not be needed to build, test or run the project.

# Explanation file

At the end of every step, before writing the pull request description, write `local/explanation.md`. It is
gitignored (with the rest of `local/`) and must never be committed. Overwrite it each step — it describes
the current state, not a history.

It is read before the PR description and exists to be short. Under 400 words. Plain language. No
command output, no file lists, no test names, no counts unless a count is the point.

Five parts, in this order:

**Anything waiting on me.** One line at the top if a decision is needed, or omit the section entirely.

**Where the project is.** What the pipeline can actually do today, in two or three sentences, written so
someone who has not read the code would understand it.

**What this step changed.** Two or three sentences. What is true now that was not true before.

**What I can see.** Whether there are QC images or outputs to look at yet, and where to start. If not,
say so plainly rather than describing internal progress as though it were visible.

**What is next.** The next step's number and what it will do, in one sentence.

Write it as though explaining to someone who has been away for a week. The PR description is where
detail belongs; this file is where clarity does.

# Definition of done

Before the final message, all of these are true.

1. The change is complete and scoped to exactly what was asked.
2. Test, lint and format-check commands were run, and their real output is included.
3. Any step that touches processing was run on real data, and its real output and timings are included.
4. New behaviour has a test that fails without the change.
5. No invariant was weakened.
6. Unspecified decisions and open questions are written down.

## Final message

Fill in `.github/pull_request_template.md` completely and save the result as `local/.pr-description.md`. Do not modify the template. Answer every section, writing "None" where nothing applies;
do not delete sections. Paste real command output in Acceptance checks, Invariants and Run status;
never paraphrase or summarise it. Include any step-specific checks the prompt asks for under Acceptance
checks. Leave the reviewer checklist unticked — it belongs to the repository owner. `local/.pr-description.md`
is gitignored and must never be committed. Your final message in the session is the full contents of that file.
Consider the fact a human has to read and parse the text of the PR so do not write it as a super long document.
Be direct, and explain in as little as possible the most amount of info while following the template.

Never state that something works if you did not run it.
