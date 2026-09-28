# Evaluation

The current model evaluation is a reproducibility check on a synthetic corpus,
not an estimate of performance on future applicants.

## Reproduce

```bash
python -m qadam.data.generate
python -m eval.train
```

Generated artefacts:

- [`eval/metrics.json`](../eval/metrics.json) — model, baseline and robustness metrics;
- [`eval/fairness.json`](../eval/fairness.json) — counterfactual comparisons;
- [`eval/report.md`](../eval/report.md) — readable experiment report;
- `qadam/data/corpus/` — versioned synthetic examples;
- `qadam/data/counterfactual/` — controlled background-attribute pairs.

## Required next evidence

- expert content review of QEF anchors;
- blind inter-rater agreement on boundary cases;
- separate evaluation by language and input modality;
- calibration and abstention rates;
- reviewer override rate and reasons;
- accessibility and completion outcomes;
- prospective pilot analysis under approved governance.

No synthetic metric should be presented as validated admission accuracy.
