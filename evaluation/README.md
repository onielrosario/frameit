# Evaluation

The protocol is owned by [../docs/evaluation.md](../docs/evaluation.md). This file is only how to
run things.

```
make setup              # once, from the repo root
make eval-mock          # whole harness, no model, no key
make validate-dataset   # format and composition checks

# against a running API:
cd evaluation && PYTHONPATH=runners:../services/api python -m frame_eval.cli --split dev --analyzer http
```

`--analyzer mock` runs the whole harness with no model and no tokens spent. That is what makes the
harness itself testable.

Tests:

```
cd evaluation && pytest      # paths are configured in pytest.ini
```

## State

The harness is built. **The dataset is empty**, and that is deliberate — see
[dataset/GUIDELINES.md](dataset/GUIDELINES.md). Labels are written by a human, blind, before any
system output is seen (§2.2). `dataset/TEMPLATE.jsonl` shows the record shape.

## Grounding is measured here, not reported by the system

The runner re-checks every displayed excerpt against the normalized submission itself. A system
reporting its own grounding rate is not a measurement.
