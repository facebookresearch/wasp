# Copyright (c) Meta Platforms, Inc. and affiliates.
import mlcroissant as mlc
import json

distribution = [
    mlc.FileObject(
        id="github-repository",
        name="github-repository",
        description="WASP repository on GitHub.",
        content_url="https://github.com/facebookresearch/wasp",
        encoding_formats=["git+https"],
        sha256="main",
    ),
    # Within that repository, a FileSet lists all JSONL files:
    mlc.FileSet(
        id="jsonl-files",
        name="jsonl-files",
        description="JSONL files are hosted on the GitHub repository.",
        contained_in=["github-repository"],
        encoding_formats=["application/jsonlines"],
        includes="webarena_prompt_injections/configs/croissant/*.jsonl",
    ),
]

record_sets = [
    # RecordSets contains records in the dataset.
    mlc.RecordSet(
        id="jsonl",
        name="jsonl",
        # Each record has one or many fields...
        fields=[
            # Fields can be extracted from the FileObjects/FileSets.
            mlc.Field(
                id="jsonl/task",
                name="task",
                description=(
                    "Type of task: prompt injection or utility."
                ),
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    extract=mlc.Extract(
                        file_property=mlc._src.structure_graph.nodes.source.FileProperty.filename
                    ),
                    # Extract the field from a regex on the filename:
                    transforms=[mlc.Transform(regex="^(.*)\.jsonl$")],
                ),
            ),
            mlc.Field(
                id="jsonl/free_form_name",
                name="free_form_name",
                description="short description of the task",
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    # Extract the field from the column of a FileObject/FileSet:
                    extract=mlc.Extract(column="free_form_name"),
                ),
            ),
            mlc.Field(
                id="jsonl/action_url",
                name="action_url",
                description="initial URL, keywords inside {} will be coming from parameters field.",
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    # Extract the field from the column of a FileObject/FileSet:
                    extract=mlc.Extract(column="action_url"),
                ),
            ),
            mlc.Field(
                id="jsonl/instruction",
                name="instruction",
                description="user instruction",
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    # Extract the field from the column of a FileObject/FileSet:
                    extract=mlc.Extract(column="instruction"),
                ),
            ),
            mlc.Field(
                id="jsonl/parameters_str",
                name="parameters_str",
                description="parameters that are used to populate all other fields, it needs to be converted to dict type",
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    extract=mlc.Extract(column="parameters_str"),
                ),
            ),
            mlc.Field(
                id="jsonl/eval_str",
                name="eval_str",
                description="eval -- evaluation workflow, needs to be converted into valid json dict.",
                data_types=mlc.DataType.TEXT,
                source=mlc.Source(
                    file_set="jsonl-files",
                    extract=mlc.Extract(column="eval_str"),
                ),
            ),
        ],
    )
]

# Metadata contains information about the dataset.
metadata = mlc.Metadata(
    name="WASP",
    # Descriptions can contain plain text or markdown.
    description=(
        "Autonomous web navigation agents hold great potential for unlocking human productivity by automating "
        "mundane tasks on the internet. However, these agents can also be taken advantage of as new attack vectors "
        "for adversaries when deployed without proper mitigation. One emerging threat — prompt injection attacks, "
        "where the adversary embeds malicious instructions in the web environment that divert the agent to instead "
        "perform tasks for the adversary. To measure the extent of this risk, we construct this new benchmark that "
        "simulates real world attacks in a highly realistic, end-to-end executable web environment, "
        "without exposing the agent to real harm."
    ),
    cite_as=(
        "@misc{evtimov2025waspbenchmarkingwebagent,title={WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks},"
        "author={Ivan Evtimov and Arman Zharmagambetov and Aaron Grattafiori and Chuan Guo and Kamalika Chaudhuri},year={2025},"
        "eprint={2504.18575},archivePrefix={arXiv},primaryClass={cs.CR},url={https://arxiv.org/abs/2504.18575},}"
    ),
    url="https://github.com/facebookresearch/wasp",
    distribution=distribution,
    record_sets=record_sets,
)

# print(metadata.issues.report())

with open("croissant_metadata.json", "w") as f:
    content = metadata.to_json()
    content = json.dumps(content, indent=2)
    # print(content)
    f.write(content)
    f.write("\n")  # Terminate file with newline

dataset = mlc.Dataset(jsonld="croissant_metadata.json")

records = dataset.records(record_set="jsonl")
# print(len(records))
for i, record in enumerate(records):
    print(record)
    if i > 22:
        break