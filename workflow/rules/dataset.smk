rule metadata:
    output:
        description=dataset_layout().raw_description,
        participants=dataset_layout().raw_participants,
    log:
        step_log("metadata"),
    resources:
        mem_mb=memory("metadata"),
    shell:
        "openneuro-t1 --step metadata --force"


rule template:
    output:
        brain=dataset_layout().template_brain,
    log:
        step_log("template"),
    resources:
        mem_mb=memory("template"),
    shell:
        "openneuro-t1 --step template --force"


rule describe:
    input:
        description=dataset_layout().raw_description,
    output:
        description=dataset_layout().dataset_description,
        labels=dataset_layout().dseg_tsv,
    log:
        step_log("describe"),
    resources:
        mem_mb=memory("describe"),
    shell:
        "openneuro-t1 --step describe --force"


rule qc_index:
    input:
        qc_index_inputs(),
    output:
        index=dataset_layout().qc_index,
    log:
        step_log("qc_index"),
    resources:
        mem_mb=memory("qc_index"),
    shell:
        "openneuro-t1 --step qc_index --force"
