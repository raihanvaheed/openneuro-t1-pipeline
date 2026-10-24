# Architecture

The pipeline reads a public T1-weighted scan from OpenNeuro `ds000102` on AWS S3 (anonymously, with the AWS CLI) and builds a template brain from TemplateFlow `MNI152NLin2009cAsym`; both land in `resources/`. FSL BET strips the skull, then FAST segments tissue and FLIRT registers the brain to the template brain. Each tool runs through NiWrap in a Docker container. Every output is written to `results/` as a BIDS derivatives dataset, and each step gets a QC image. The dashed parts are not built yet: step 2 runs the same functions per subject with Snakemake and adds an HTML QC report.

```mermaid
flowchart LR
    subgraph snakemake["Snakemake runs this per subject (step 2)"]
        direction LR
        S3[("OpenNeuro ds000102<br/>AWS S3, public")]
        TF[("TemplateFlow<br/>MNI152NLin2009cAsym")]
        RES["resources/"]
        S3 -->|"fetch with the AWS CLI"| RES
        TF --> RES

        subgraph niwrap["NiWrap → Docker: FSL"]
            BET["BET<br/>skull stripping"]
            FAST["FAST<br/>tissue segmentation"]
            FLIRT["FLIRT<br/>registration to MNI"]
            BET --> FAST
            BET --> FLIRT
        end

        RES -->|"raw T1w"| BET
        RES -->|"template brain"| FLIRT
        BET --> RESULTS
        FAST --> RESULTS
        FLIRT --> RESULTS
        RESULTS["results/<br/>BIDS derivatives"] --> QC["QC images"]
    end

    QC -.-> REPORT["HTML QC report (step 2)"]

    style snakemake stroke-dasharray: 6 4
    style REPORT stroke-dasharray: 6 4
```
