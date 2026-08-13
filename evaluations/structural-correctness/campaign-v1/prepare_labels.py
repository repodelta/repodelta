from __future__ import annotations

import json
import sys
from pathlib import Path

from repodelta.evaluation.structural_correctness import (
    HumanFileLabel,
    HumanFocusLabel,
    StructuralCorrectnessLabels,
    load_packet,
    write_json_artifact,
)


ROOT = Path(__file__).parent


def main() -> int:
    decisions = json.loads((ROOT / "decisions.json").read_text(encoding="utf-8"))
    for pull_request, decision in decisions["pull_requests"].items():
        packet = load_packet(ROOT / "packets" / f"pr-{pull_request}.json")
        candidate_by_path = {item.path: item for item in packet.candidates}
        changed_paths = {
            item.head_path or item.base_path for item in packet.changed_surfaces
        }
        bridges = set(decision["retained_bridge_paths"])
        contexts = set(decision["retained_context_paths"])
        unknown = (bridges | contexts) - set(candidate_by_path)
        if unknown:
            raise ValueError(f"PR {pull_request} decisions contain unknown files: {sorted(unknown)}")
        files = []
        for candidate in packet.candidates:
            if candidate.path in changed_paths:
                files.append(HumanFileLabel(candidate.file_node_id, "included", "changed"))
            elif candidate.path in bridges:
                files.append(HumanFileLabel(candidate.file_node_id, "included", "retained_bridge"))
            elif candidate.path in contexts:
                files.append(HumanFileLabel(candidate.file_node_id, "included", "retained_context"))
            else:
                files.append(HumanFileLabel(candidate.file_node_id, "excluded"))
        focus_decisions = {}
        for group in decision["focus_groups"]:
            for subject_id in group["subjects"]:
                if subject_id in focus_decisions:
                    raise ValueError(f"PR {pull_request} duplicates {subject_id}")
                focus_decisions[subject_id] = group
        packet_subjects = {item.subject_id for item in packet.subjects}
        if set(focus_decisions) != packet_subjects:
            raise ValueError(
                f"PR {pull_request} focus decisions diverge: "
                f"missing={sorted(packet_subjects-set(focus_decisions))} "
                f"extra={sorted(set(focus_decisions)-packet_subjects)}"
            )
        focuses = []
        for subject in packet.subjects:
            group = focus_decisions[subject.subject_id]
            direct_paths = (
                changed_paths & set(candidate_by_path)
                if group["direct_paths"] == ["*changed"]
                else set(group["direct_paths"])
            )
            context_paths = set(group["context_paths"])
            unknown = (direct_paths | context_paths) - set(candidate_by_path)
            if unknown:
                raise ValueError(
                    f"PR {pull_request} {subject.subject_id} contains unknown files: {sorted(unknown)}"
                )
            focuses.append(
                HumanFocusLabel(
                    subject_id=subject.subject_id,
                    direct_file_node_ids=tuple(
                        candidate_by_path[path].file_node_id
                        for path in sorted(direct_paths)
                    ),
                    context_file_node_ids=tuple(
                        candidate_by_path[path].file_node_id
                        for path in sorted(context_paths)
                    ),
                    unresolved=group["unresolved"],
                )
            )
        write_json_artifact(
            StructuralCorrectnessLabels(
                packet_digest=packet.digest,
                files=tuple(files),
                focuses=tuple(focuses),
            ),
            ROOT / "labels" / f"pr-{pull_request}.json",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
