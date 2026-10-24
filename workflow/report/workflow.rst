openneuro-t1-pipeline processes public T1-weighted MRI scans from OpenNeuro dataset ds000102 with three FSL steps, run through NiWrap in Docker: BET skull stripping, FAST tissue segmentation and FLIRT affine registration to the MNI152NLin2009cAsym template.

Snakemake runs each step as its own job for every subject in ``config/config.yaml``. The workflow graph and the runtime of each job are listed in the sections of this report. The quality-check (QC) images are listed by category and subject; they are for visual review, and this report does not judge them.
