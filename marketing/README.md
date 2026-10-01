# Marketing assets

Rendered from the repo so a published claim and the code that backs it never drift.

## Mirror-pair asset

The strongest demo this product has, and the one that answers the objection that matters:
*structurally identical left- and right-leaning passages, treated the same way.*

```bash
# with the API running (see ../README.md)
python marketing/mirror/render.py --api http://localhost:8000
```

1. Write the pair by hand in `mirror/pair.json`. See
   [docs/evaluation.md §4](../docs/evaluation.md#4-mirror-tests) — same rhetorical structure,
   same loaded-language density, swapped actors and policy direction. **Not** a mechanical
   word swap.
2. Run the renderer. It sends both passages to a live Frame API and renders **what came
   back**.
3. Read the verdict it prints before you post anything.

## It cannot fake symmetry

The renderer does not take the result as an input. It calls the API, applies
`frame_eval.metrics.compare_predictions` — the same function the evaluation harness uses, so
the demo and the test agree on what "symmetric" means — and stamps the outcome on the image.

If the pair comes back asymmetric, the image says **ASYMMETRIC** and names which assertion
failed. That is the honest outcome and, per
[docs/evaluation.md §7](../docs/evaluation.md#7-reporting-honesty), a published failure is
worth more to this product's credibility than a withheld success.

It also refuses to render a symmetry claim from mocked output: if both analyses come back
identical, that is the mock agreeing with itself, not evidence of anything.

## Known limitations

- One pair proves nothing statistically. It demonstrates the *property being tested*, not that
  the property holds. Say so in the caption.
- The pair is hand-written by one person, who has politics. That is the same limitation as
  the evaluation set (§2.4) and belongs in any published material.
