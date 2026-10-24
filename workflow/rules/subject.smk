rule fetch:
    output:
        t1w=subject_layout().raw_t1w,
        fragment=subject_layout().fragments["fetch"],
    log:
        step_log("fetch", SUBJECT),
    resources:
        mem_mb=memory("fetch"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step fetch --force"


rule bet:
    input:
        t1w=subject_layout().raw_t1w,
    output:
        brain=subject_layout().brain,
        mask=subject_layout().mask,
        fragment=subject_layout().fragments["bet"],
    log:
        step_log("bet", SUBJECT),
    resources:
        mem_mb=memory("bet"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step bet --force"


rule fast:
    input:
        brain=subject_layout().brain,
    output:
        dseg=subject_layout().dseg,
        csf=subject_layout().probseg["CSF"],
        gm=subject_layout().probseg["GM"],
        wm=subject_layout().probseg["WM"],
        fragment=subject_layout().fragments["fast"],
    log:
        step_log("fast", SUBJECT),
    resources:
        mem_mb=memory("fast"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step fast --force"


rule flirt:
    input:
        brain=subject_layout().brain,
        template=dataset_layout().template_brain,
    output:
        registered=subject_layout().registered,
        matrix=subject_layout().matrix,
        fragment=subject_layout().fragments["flirt"],
    log:
        step_log("flirt", SUBJECT),
    resources:
        mem_mb=memory("flirt"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step flirt --force"


rule qc:
    input:
        t1w=subject_layout().raw_t1w,
        mask=subject_layout().mask,
        brain=subject_layout().brain,
        dseg=subject_layout().dseg,
        registered=subject_layout().registered,
        template=dataset_layout().template_brain,
    output:
        skullstrip=report(
            subject_layout().skullstrip_png,
            caption="../report/skullstrip.rst",
            category="Skull strip",
            subcategory="Subject {subject}",
        ),
        tissues=report(
            subject_layout().tissues_png,
            caption="../report/tissues.rst",
            category="Tissues",
            subcategory="Subject {subject}",
        ),
        registration=report(
            subject_layout().registration_png,
            caption="../report/registration.rst",
            category="Registration",
            subcategory="Subject {subject}",
        ),
        fragment=subject_layout().fragments["qc"],
    log:
        step_log("qc", SUBJECT),
    resources:
        mem_mb=memory("qc"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step qc --force"


rule runinfo:
    input:
        fragments=list(subject_layout().fragments.values()),
    output:
        runinfo=subject_layout().runinfo,
    log:
        step_log("runinfo", SUBJECT),
    resources:
        mem_mb=memory("runinfo"),
    shell:
        "openneuro-t1 --subject {wildcards.subject} --step runinfo --force"
