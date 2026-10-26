# Running the pipeline on AWS EC2

This guide repeats the ten-subject run on one rented Linux machine and then checks the outputs against the published fingerprints in [fingerprints.txt](fingerprints.txt). You need an AWS account, a terminal with `ssh`, and one to two hours, mostly waiting. Nothing in the pipeline depends on AWS: this is an optional way to run it without emulation.

## Choices

- **The machine:** `m7i-flex.large` (2 vCPU, 8 GiB), x86, Amazon Linux 2023, with a 30 GiB gp3 disk. It is x86 because the FSL image is amd64-only: a Graviton (Arm) machine would run it under emulation, as Apple Silicon does. The disk is 30 GiB because the FSL image does not fit in the default 8 GiB.
- **No AWS credentials on the machine.** The pipeline reads OpenNeuro anonymously (`--no-sign-request`), so do not run `aws configure` or `aws login` there, and do not give the machine an IAM role.
- **SSH only from your own IP address.** Leave HTTP and HTTPS closed.
- **An automatic shutdown,** so a forgotten machine does not run for days (see steps 3 and 5).

## 1. Launch the instance

In the EC2 console, in the Region you want, choose **Launch instance** and set:

| Section | Setting |
| --- | --- |
| Name | `t1-pipeline-run` |
| Application and OS Images | **Amazon Linux 2023 AMI**, architecture **64-bit (x86)**, not Arm |
| Instance type | `m7i-flex.large` |
| Key pair | Create a new key pair: type **ED25519**, format **.pem**. The file downloads once. |
| Network settings | Create a security group. Allow **SSH traffic from: My IP**. Leave HTTP and HTTPS unticked. |
| Storage | **30 GiB**, gp3 |
| Advanced details | Check that **Shutdown behavior** is **Stop** (the default). The automatic shutdown relies on it. |

Wait until the instance is *Running* and its status checks have passed, then copy its **Public IPv4 address**.

## 2. Connect

On your own computer, lock the key file down and connect. `203.0.113.10` is a placeholder: use your instance's address.

```bash
chmod 400 ~/.ssh/ec2-key.pem
ssh -i ~/.ssh/ec2-key.pem ec2-user@203.0.113.10
```

Answer `yes` to the first-time fingerprint question.

## 3. Set up the machine

Check what you got:

```bash
uname -m          # x86_64
nproc             # 2
free -h           # about 7.6Gi total
df -h /           # about 30G
```

Install Docker, git and tmux, start Docker, and let your user run it. The `exit` logs you out so the group change takes effect:

```bash
sudo dnf install -y docker git tmux
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
exit
```

Reconnect with the same `ssh` command, then check Docker works without `sudo`:

```bash
docker run --rm hello-world
```

Install uv, clone the repository and build the environment exactly from the lock file. `--locked` stops with an error if anything would differ from `uv.lock`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
git clone https://github.com/raihanvaheed/openneuro-t1-pipeline.git
cd openneuro-t1-pipeline
uv sync --locked
```

Schedule the safety shutdown now. It stops the machine in 4 hours whatever happens; `sudo shutdown -c` cancels it:

```bash
sudo shutdown -h +240
```

Pull the FSL image now, so the download is not counted in the pipeline's timings, and **check its digest before running**:

```bash
docker pull brainlife/fsl:6.0.4-patched2
docker image inspect --format '{{index .RepoDigests 0}}' brainlife/fsl:6.0.4-patched2
df -h /
```

The digest must be `brainlife/fsl@sha256:d51c8ddfe8caad59dd60cf7e75e254dc01093ec171cf6c75778953e8bb1c5389`. If it is different, stop: the fingerprint check only means something when the image is the same.

## 4. Test before running

```bash
uv run pytest -q
uv run snakemake -n
```

The tests should all pass. On a fresh machine the dry run lists every step: `metadata`, `template` and `describe` once each, `qc_index` once, and `fetch`, `bet`, `fast`, `flirt`, `qc` and `runinfo` ten times each, about 65 jobs.

## 5. Run it

Start tmux **first**, so the run survives a dropped connection:

```bash
tmux new -s run
```

Then paste the run command **on its own**, inside tmux:

```bash
cd ~/openneuro-t1-pipeline
time uv run snakemake --cores 2 2>&1 | tee ~/run.log; sudo shutdown -h now
```

> **The tmux pitfall:** if you paste several lines at once and one of them is `tmux new`, the lines after it wait in the shell outside tmux and do not run in the session. Start tmux first, then paste the run command separately.

- `--cores 2` overrides the profile's four jobs, because this machine has two vCPUs. The memory budget stays at 6000 MB.
- `; sudo shutdown -h now` stops the machine when the run ends, so it does not sit idle. With shutdown behavior *Stop*, the machine stops but its disk and instance remain until you terminate it (step 8). If you want to check the results on the machine first, leave `; sudo shutdown -h now` off and shut down by hand afterwards; the 4-hour safety shutdown still applies.
- To leave the run going, press `Ctrl-b` then `d`. After a dropped connection, reconnect and run `tmux attach -t run`.

The run is done when Snakemake prints `65 of 65 steps (100%) done`, followed by the `real` time.

## 6. Check the run

```bash
cd ~/openneuro-t1-pipeline
uv run snakemake -n
cat results/provenance/sub-01_runinfo.json
```

The dry run should say "Nothing to be done". `runinfo.json` should show the same image digest as in step 3 and `docker_default_platform` null. The image ID may differ from the digest: see the note at the end.

## 7. Check the outputs against the fingerprints

A fingerprint is the SHA-256 of the **uncompressed** content of a file, so the gzip wrapper cannot hide or cause a difference. The list covers 91 files: the 10 raw T1w scans, the template brain, and the 80 subject outputs (70 `.nii.gz` and 10 `.mat`), so that any difference can be traced to its step. QC PNGs are not compared: font rendering differs between macOS and Linux, so they differ even when the figure is the same.

**On Linux** (the EC2 machine), from the repository folder:

```bash
find results resources/ds000102 resources/templates -type f \( -name '*.nii.gz' -o -name '*.mat' \) | LC_ALL=C sort | while read -r f; do
  case "$f" in
    *.gz) h=$(gunzip -c "$f" | sha256sum | cut -d' ' -f1) ;;
    *)    h=$(sha256sum < "$f" | cut -d' ' -f1) ;;
  esac
  echo "$h  $f"
done > ~/hashes.txt
wc -l ~/hashes.txt
diff ~/hashes.txt docs/fingerprints.txt && echo "ALL IDENTICAL"
```

**On macOS**, from the repository folder. It is the same loop with `shasum -a 256`:

```bash
find results resources/ds000102 resources/templates -type f \( -name '*.nii.gz' -o -name '*.mat' \) | LC_ALL=C sort | while read -r f; do
  case "$f" in
    *.gz) h=$(gunzip -c "$f" | shasum -a 256 | cut -d' ' -f1) ;;
    *)    h=$(shasum -a 256 < "$f" | cut -d' ' -f1) ;;
  esac
  echo "$h  $f"
done > ~/hashes.txt
wc -l ~/hashes.txt
diff ~/hashes.txt docs/fingerprints.txt && echo "ALL IDENTICAL"
```

`diff` prints nothing when the lists match. If it prints lines, the ones starting with `>` are the expected fingerprints and the ones starting with `<` are yours.

- **Differences in the raw inputs** (`resources/ds000102`): stop. Everything downstream would differ for that reason alone.
- **Differences in outputs:** not automatically a bug, because floating-point maths can differ between processors. Note which step the files belong to (BET, FAST or FLIRT).
- The list is only valid for the pinned image digest, `uv.lock` and these ten subjects. Changing any of them means regenerating it.

## 8. Terminate the machine

Do not skip this. In the EC2 console, select the instance, then **Instance state** then **Terminate (delete) instance**, and wait until it says *Terminated*. Its disk is deleted with it. Then check that **Volumes** shows nothing left over and that **Elastic IPs** is empty (this guide never creates one). The security group and key pair cost nothing; keep them for next time or delete them.

Terminating, rather than stopping, means nothing keeps costing money. Setting up again takes about 15 minutes.

## Cost

About $0.10 an hour on demand in us-east-2, as of October 2026.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| `ssh` connection timed out | The instance is not ready, the address is wrong, or your own IP changed (another network, a VPN). Edit the security group's inbound rule and set the source to **My IP** again. |
| `Permission denied (publickey)` | Use the user `ec2-user`, the right `.pem` file, and run `chmod 400` on it. |
| `permission denied ... docker.sock` | You did not log out and back in after `usermod`. Run `exit`, then reconnect. |
| `no space left on device` | The disk is not 30 GiB. Terminate the instance and launch again; that is quicker than resizing. |
| `uv sync --locked` fails | The lock file and the project disagree. Do not run `uv lock`; that failure is a finding to report. |
| Snakemake says the directory is locked | A previous run was interrupted. Run `uv run snakemake --unlock`, then start again. |
| The connection dropped during the run | Reconnect, then `tmux attach -t run`. The run kept going. |

## Results from one run

The same ten subjects of `ds000102` ran on an EC2 machine (26 October 2026) and on an Apple Silicon Mac (24 October 2026).

| | EC2 | Mac |
| --- | --- | --- |
| Machine | `m7i-flex.large`: 2 vCPU, 8 GiB, x86, Amazon Linux 2023, us-east-2, 30 GiB gp3 | Apple Silicon; Docker Desktop given 10 CPUs and 8 GB; FSL under amd64 emulation |
| Command | `uv run snakemake --cores 2` | `uv run snakemake`, with the default profile (4 jobs) |
| Jobs at a time | 2 | 4, so at most 3 FAST jobs together |
| Memory budget | 6000 MB | 6000 MB |
| Jobs | 65 of 65, on a fresh machine | 62 |
| Wall time | 26 min 6 s, not counting the image pull | 30 min 56 s |
| FAST per subject | 220.3 to 231.8 s | 304.0 to 446.9 s |
| FLIRT per subject | 53.3 to 67.3 s | 80.3 to 99.7 s |

On EC2 the other steps took, per subject: fetch 0.9 to 1.5 s, BET 2.9 to 3.2 s and QC 4.4 to 4.6 s. On the Mac, FAST took 314.2 s for a single subject on its own in an earlier run, with nothing else running.

**The FSL image.** Its digest, `sha256:d51c8ddfe8caad59dd60cf7e75e254dc01093ec171cf6c75778953e8bb1c5389`, was the same on both machines. Its image ID differed: `sha256:3077e50b…` on EC2, and equal to the digest on the Mac, because the Mac's Docker uses the containerd image store, which reports the manifest digest as the image ID. Compare images by digest, which the pipeline's provenance records.

On these two machines, all 91 checked files were bit-for-bit identical.
