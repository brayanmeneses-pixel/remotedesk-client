#!/usr/bin/env python3
"""Generate .github/workflows/remotedesk-windows.yml from upstream flutter-build.yml.

Keeps only the Windows x64 Flutter build (and the jobs it needs), injects the
branding step, renames outputs to the product name and publishes a GitHub
Release. Re-run after rebasing on a new upstream tag:
    python remotedesk/gen_workflow.py
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".github/workflows/flutter-build.yml"
DST = ROOT / ".github/workflows/remotedesk-windows.yml"

text = SRC.read_text(encoding="utf-8")
# Resolve the reusable-workflow inputs to constants.
text = text.replace("${{ inputs.upload-artifact }}", "true")
text = text.replace("inputs.upload-artifact", "true")
text = text.replace("${{ inputs.publish-update-metadata }}", "false")
text = text.replace("inputs.publish-update-metadata", "false")
text = text.replace("${{ inputs.upload-tag }}", "${{ github.ref_type == 'tag' && github.ref_name || 'rd-nightly' }}")

wf = yaml.safe_load(text)
wf.pop(True, None)  # PyYAML parses the key `on` as boolean True
wf.pop("on", None)
wf["name"] = "RemoteDesk Windows build"
wf["on"] = {"workflow_dispatch": {}, "push": {"tags": ["rd-*"]}}
wf["permissions"] = {"contents": "write"}

keep = ["validate-update-metadata-keys", "generate-bridge",
        "build-RustDeskTempTopMostWindow", "build-for-windows-flutter"]
wf["jobs"] = {k: wf["jobs"][k] for k in keep}

top = wf["jobs"]["build-RustDeskTempTopMostWindow"]
top["strategy"]["matrix"]["job"] = [j for j in top["strategy"]["matrix"]["job"] if j["platform"] == "x64"]

win = wf["jobs"]["build-for-windows-flutter"]
win["strategy"]["matrix"]["job"] = [j for j in win["strategy"]["matrix"]["job"] if j["arch"] == "x86_64"]

drop = {"Run the Rust tests", "Build pre-built MSI template", "Upload unsigned msi template",
        "Sign rustdesk files", "Sign rustdesk self-extracted file", "Verify template payload signatures",
        "Upload unsigned template packer", "Upload signed Windows Flutter EXE",
        "Upload signed Windows Flutter MSI", "Verify Windows Flutter version", "Build template packer"}
steps = []
found = set()
for st in win["steps"]:
    name = st.get("name", "")
    if name in drop:
        continue
    if name == "Checkout source code":
        steps.append(st)
        steps.append({
            "name": "Apply RemoteDesk branding",
            "shell": "bash",
            "env": {
                "RD_APP_NAME": "${{ vars.RD_APP_NAME }}",
                "RD_SERVER": "${{ vars.RD_SERVER }}",
                "RD_KEY": "${{ vars.RD_KEY }}",
            },
            "run": "pip3 install pillow pyyaml && python3 remotedesk/brand.py",
        })
        found.add(name)
        continue
    if name == "Upload unsigned":
        steps.append({
            "name": "Rename main exe to product name",
            "shell": "bash",
            "run": 'mv ./rustdesk/rustdesk.exe "./rustdesk/${RD_APP_NAME}.exe"',
        })
        st["with"]["name"] = "remotedesk-unpacked-windows-x86_64"
        found.add(name)
    if name == "Build self-extracted executable":
        st["run"] = st["run"].replace("-e ../../rustdesk/rustdesk.exe", '-e "../../rustdesk/${RD_APP_NAME}.exe"')
        st["run"] = st["run"].replace(
            "./SignOutput/rustdesk-${{ env.VERSION }}-${{ matrix.job.arch }}.exe",
            '"./SignOutput/${RD_APP_NAME}-${{ env.VERSION }}-portable.exe"')
        found.add(name)
    if name == "Build msi":
        st["run"] = st["run"].replace("python preprocess.py --arp -d ../../rustdesk",
                                      "python preprocess.py --arp -d ../../rustdesk --app-name $env:RD_APP_NAME")
        st["run"] = st["run"].replace(
            "../../SignOutput/rustdesk-${{ env.VERSION }}-${{ matrix.job.arch }}.msi",
            '"../../SignOutput/$($env:RD_APP_NAME)-${{ env.VERSION }}-Setup.msi"')
        st["run"] = st["run"].replace("sha256sum ../../SignOutput/rustdesk-*.msi", "Get-FileHash ../../SignOutput/*.msi")
        found.add(name)
    if name == "Publish Release":
        st["with"]["files"] = "./SignOutput/*.msi\n./SignOutput/*.exe\n./SignOutput/SHA256SUMS.txt\n"
        steps.append({
            "name": "Checksums",
            "shell": "bash",
            "run": "cd SignOutput && sha256sum *.exe *.msi > SHA256SUMS.txt && cat SHA256SUMS.txt",
        })
        found.add(name)
    steps.append(st)
win["steps"] = steps

needed = {"Checkout source code", "Upload unsigned", "Build self-extracted executable", "Build msi", "Publish Release"}
missing = needed - found
if missing:
    raise SystemExit(f"upstream workflow changed, steps not found: {missing}")
for st in steps:
    if st.get("name") == "Build self-extracted executable" and "RD_APP_NAME" not in st["run"]:
        raise SystemExit("could not patch portable packer step")
    if st.get("name") == "Build msi" and "--app-name" not in st["run"]:
        raise SystemExit("could not patch msi step")

header = "# GENERATED by remotedesk/gen_workflow.py from flutter-build.yml. Do not edit by hand.\n"
DST.write_text(header + yaml.safe_dump(wf, sort_keys=False, width=200, allow_unicode=True), encoding="utf-8")
print(f"wrote {DST.relative_to(ROOT)}")
