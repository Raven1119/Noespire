# Reference-access audit

## Intended firewall

The frozen DANUS project inputs contained only each exact problem statement. The evaluator-only reference-proof notes remained under Noespire's offline `analysis/` directory and were not copied into any DANUS project context.

## Observed runtime access

The unchanged Baseline A configuration retained DANUS's normal retrieval and web tools. Worker instructions encouraged literature grounding and web fallback, and at least one worker on every diagnostic problem found or read a problem-specific official solution during its run:

| Problem | Conservative direct evidence |
| --- | --- |
| putnam-2024-a1 | `xhigh` stated that it found the official route, then downloaded and extracted a 2024 solutions PDF (`workers/xhigh/logs/round_1.log`, lines 303 and 314). |
| putnam-2024-a2 | `xhigh4` searched for the exact official solution and stated that it used the same reduction (`workers/xhigh4/logs/round_1.log`, lines 477 and 481). |
| putnam-2023-b1 | `xhigh3` stated that the official MAA solution used the empty-square path and changed to a diagonal-vacancy presentation (`workers/xhigh3/logs/round_1.log`, lines 376 and 381). |
| putnam-2024-b2 | `high3` recorded that it read the official solution PDF and used its finite-representation structure (`workers/high3/logs/round_1.log`, line 739). |

These are conservative witnesses, not a claim that only these workers accessed solution material. Other traces also mention official solutions.

## Diagnostic consequence

The experiment did not inject evaluator reference proofs into worker context, but the workers independently retrieved equivalent official material through unchanged upstream tools. Therefore the requested reference-proof firewall was not achieved in substance. The raw runs remain valid observations of unchanged DANUS under Baseline A tool access, but they are not a clean blind test of independent proof search. Their 4/4 solve rate and route choices cannot support a high-confidence claim that wide gaps or missing lemmas are absent.

The frozen set was not changed and no run was retried after discovering this condition.
