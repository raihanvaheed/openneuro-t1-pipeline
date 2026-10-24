## Summary

<!-- Two or three sentences: what this step does and why. -->

## What changed

<!-- Files and behaviour that changed, grouped by area. Short. -->

## Decisions I made

<!-- Every decision the instructions did not specify, with the reason. "None" if there were none. -->

## Acceptance checks

<!-- Real output, pasted, not summarised: uv run pytest -q, uv run ruff check ., uv run ruff format --check ., plus any step-specific checks the prompt lists. -->

## Invariants

<!-- Real output of: uv run pytest tests/test_invariants.py -q and git status --short --ignored. Confirm no imaging data, credentials or local/ files are tracked. -->

## Run status

<!-- Real output from running the pipeline on data: the command, seconds per step, Docker images with digests, and the rerun showing finished steps were skipped. "None" if this step didn't run the pipeline. -->

## QC images

<!-- Path to each QC image, with what you see in it. Describe; don't declare QC passed. "None" if no step produced images. -->

## Documentation mismatches found

<!-- Differences between NiWrap's docs and the installed 1.1.0 API. "None" if none. -->

## Open questions

<!-- Anything the owner needs to decide. "None" if none. -->

## Reviewer checklist (owner only)

- [ ] I looked at every QC image.
- [ ] Output names match the BIDS derivative names in the prompt.
- [ ] `git status` shows no imaging data, credentials or `local/` files staged.
- [ ] README and docs make no research claims.
- [ ] Decisions and open questions are acceptable.
