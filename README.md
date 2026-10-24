# openneuro-t1-pipeline

This pipeline downloads public T1-weighted MRI scans from OpenNeuro on AWS S3 (anonymously) and runs three FSL steps on each one: BET skull stripping, FAST tissue segmentation and FLIRT registration to MNI space, all through NiWrap in Docker. The outputs are written as BIDS derivatives, with a quality-check image for every step.

**Status:** work in progress. One subject runs end to end; running many subjects with Snakemake and an HTML QC report are not built yet.

This is an engineering project: it describes a pipeline and makes no research claims.

## Requirements

- [uv](https://docs.astral.sh/uv/) to manage the Python environment
- [Docker](https://www.docker.com/), which runs the FSL image (it is amd64, so it runs under emulation on Apple Silicon)
- the [AWS CLI](https://aws.amazon.com/cli/); reads are anonymous, so no AWS account or credentials are needed

## Run one subject

```bash
uv sync
uv run python3 -m openneuro_t1.run_subject --subject 01
```

Finished steps are skipped on a rerun; add `--force` to redo them. The first run pulls the FSL Docker image, so it is slow.

| Folder | Holds |
| --- | --- |
| `resources/` | downloaded OpenNeuro data, the TemplateFlow cache and the template brain |
| `results/` | the BIDS derivatives dataset: images, QC figures and `provenance/` |
| `logs/` | one log per step: its command, stdout and stderr |

All three are regenerable and gitignored. The pipeline is described in [docs/architecture.md](docs/architecture.md).

## Data

The input is OpenNeuro dataset [ds000102](https://openneuro.org/datasets/ds000102), "Flanker task (event-related)", by Kelly AMC, Uddin LQ, Biswal BB, Castellanos FX and Milham MP. It is released under the PDDL (Public Domain Dedication and License). Its `dataset_description.json` asks for this acknowledgement: "This data was obtained from the OpenfMRI database. Its accession number is ds000102". No imaging data is stored in this repository.

## Credits

The project structure follows [styx-api/niwrap-workflow-examples](https://github.com/styx-api/niwrap-workflow-examples) and Snakemake's recommended workflow layout.

## License

[MIT](LICENSE)
