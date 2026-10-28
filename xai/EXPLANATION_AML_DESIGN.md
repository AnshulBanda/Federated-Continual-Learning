# AML Operations visual refinement

The selected transaction now opens into one investigation hero: the transaction
network on the left and its approved simple explanation on the right. The page
uses the actual light design tokens from `streaming/web/index.html`, with no
duplicate global navigation. This record supersedes the layout described in the
original [UX v2 review](EXPLANATION_UX_V2.md); its explanation/evidence architecture
remains approved and unchanged.

## Branch and scope

- Branch: `xai/explanation-ux-v2`, continuing from
  `446709374636b8c954792c2caf3ef97156edaf49`.
- Main remains `6db498730f36f112ea89d183b4bec6b1178f80f7`. No merge or push to main.
- Implementation changes: `static/dashboard.css`, `static/dashboard.html`,
  `static/dashboard.js`, and `tests/test_dashboard_frontend.cjs`.
- Documentation/evidence: this report, the README, and
  `review/explanation-ux-v2-aml-design/`.
- Existing runtime cache changes were present before this task. Those and new
  live-review cache updates remain local and are excluded from the commit.

The deterministic summary module, Python server, grouped attribution, history
replay, story construction, counterfactual scoring, cache identity, provenance,
source engine, thresholds and parity guard were not modified. The complete
technical renderer is byte-for-byte identical to the approved revision. Source
hashes and preservation checks are recorded in `validation.json`.

## Adopted design system

| Component | Actual AML Operations token/style |
| --- | --- |
| Primary green | `--green: #14785f` |
| Heading ink | `--ink: #182a33` |
| Muted text | `--muted: #657580` |
| Card/section border | `--line: #dfe5e8` |
| Page background | `#f4f6f8` |
| Card/control background | White, `#ffffff` |
| Font | Inter, `-apple-system`, BlinkMacSystemFont, Segoe UI, sans-serif |
| Inputs | White; `#cdd7dd` border; 7px radius; `#92c8b7` focus outline |
| Primary button | `#14785f`, white text; hover `#0d604b` |
| Secondary button | White; `#cfd9de` border; `#40545f` text |
| Ordinary status | `#e6f3ed` background, `#22624e` text |
| Review attention | Restrained `#fbf2e4` background, `#906019` text |
| Cards | White, subtle border, 10–12px radius |
| Tables | `#f6f8f9` headers, `#edf1f3` separators, `#f8fbfa` hover |

There is no dark root theme, navy panel, decorative gradient or copied AML
global sidebar. The narrower transaction selector remains a search/filter tool.
The investigation is the visual focus.

## Hero and content order

After transaction identity, the first major block is a shared white card with
two columns, normally 57% network / 43% explanation. A subtle divider joins the
two halves into the same investigation.

The explanation shows the exact same deterministic primary sentence, decision,
rounded score and saved review cutoff, signed margin, up to three measured
feature cards with observed values and relative bars, a short earlier-activity
summary, and the truthful model scope. It contains no SHAP, logits, hashes or JSON.

Below the hero, the order is:

1. Earlier activity and tested history, with recorded-history disclosure.
2. Observed account patterns and their limitations.
3. Constrained amount sensitivity and its disclaimer.
4. Independent dataset label / model outcome.
5. Collapsed in-depth explanation, with nested collapsed raw audit record.

The network renders once. It is visible by default and is not repeated below.
All technical A–I sections and exact evidence remain available.

At widths of 1000px or less the hero stacks: explanation first, network directly
below it, then the lower sections. The selected investigation appears before
the picker, retaining the previously tested behavior and its link back to the
bank selector. Phone and tablet checks found no horizontal document overflow.

## Graph design and interaction

- Light neutral canvas with a soft border and generous spacing.
- Current sender/receiver accounts use larger, light-green cards with stronger
  green outlines. Context accounts use smaller white cards and sage/gray borders.
  Each shows its deterministic account alias, actual dataset ID and role. Model
  node IDs remain in tooltips and technical evidence.
- The selected transaction uses a solid green arrow, wider stroke and prominent
  green badge containing transaction ID and amount.
- Earlier observed edges are thinner, muted `#a9b8bf` and dashed. Verified
  raising effects use restrained amber `#b57728`; lowering effects use green
  `#27846c`; negligible tests use gray `#819197`. The existing `1e-6` visual
  materiality distinction is retained; no effect calculation was changed.
- Curves use deterministic separation and endpoint clipping. Badge placement
  considers account bounds, other badges, edge crossings and canvas bounds.
  A bounded search retains alternative whole-layout placements so early labels
  cannot consume the only space needed by later parallel transfers. Short
  callout leaders resolve crowded history labels without moving transaction
  evidence. In the final eight reviewed cases, browser-measured badge overlaps
  and labels covering accounts were both zero.
- The legend explains selected, observed, raising, lowering and negligible
  tested transfers. The observed-only disclaimer remains immediately below it.

Click, Enter and Space inspection are retained. Active items now expose
`aria-pressed` and a visible focus/selection outline. Accounts show ID, role,
displayed transfer count and buttons for connected transfers. Transfers show ID,
endpoints, timestamp, amount and method. Verified history additionally shows
direction, original score, score without the update and signed measured
difference. The selected transfer shows its model score.

Live interaction example: inspecting JPMorgan Chase TX 180238 displayed
“Helped lower the score”, original `0.0862`, without update `0.2785`, and measured
difference `-0.1924`. Inspecting account 268537464 showed its sender role and nine
displayed transfers; its connected-transfer button opened TX 180245 with model
score `0.0862`. These are measured model effects, not fraud or purpose claims.

## Visual review on 28 October 2026

The real dashboard stayed running at `http://127.0.0.1:8766/`. Fresh screenshots
and DOM geometry checks are under
[`review/explanation-ux-v2-aml-design/`](review/explanation-ux-v2-aml-design/).

| Scenario | Transaction | Screenshot |
| --- | --- | --- |
| False positive / no history | Wells Fargo 2954161 | `false-positive-no-history.png` |
| True positive / untested history / fan-out | JPMorgan Chase 2580817 | `true-positive-untested-fan-out.png` |
| True positive / fan-in | JPMorgan Chase 3008974 | `true-positive-fan-in.png` |
| True negative | Wells Fargo 2965480 | `true-negative.png` |
| Missed fraud | Wells Fargo 2794670 | `missed-fraud.png` |
| Verified positive history effect | Key Bank 2974317 | `verified-positive-history.png` |
| Verified negative history effect | JPMorgan Chase 180245 | `verified-negative-history.png` |
| Chronological cycle | JPMorgan Chase 66943 | `chronological-cycle.png` |
| Narrow phone, 390px | JPMorgan Chase 66943 | `mobile-explanation.png`, `mobile-network.png` |
| Tablet, 980px | JPMorgan Chase 66943 | `tablet-explanation.png` |
| Keyboard transfer/account inspection | JPMorgan Chase 180238 / 268537464 | `tested-transfer-inspector.png`, `account-inspector.png` |
| Full technical / history evidence | JPMorgan Chase 180245 / 66943 | `technical-evidence.png`, `history-evidence.png` |

Review iteration found crowded labels in the negative-history example. The final
placement search separated them; both unit geometry checks and real SVG bounds
checks now verify they do not overlap or cover account cards. The selected green
transfer remains the focal point, while earlier observations recede and verified
effects retain distinct semantic styling. The explanation is readable alongside
the graph, with a quieter palette and compact factor cards. This is an internal
human-style visual review; human approval before merge is still outstanding.

The eight final desktop cases have exactly one visible graph in the shared hero,
no overlapping badges or labels covering accounts, no document overflow, and
collapsed technical/raw disclosures. Phone/tablet checks verify explanation →
network → lower sections → picker. Keyboard, connected-transfer, in-depth,
history and nested raw controls were exercised. No console warnings or errors
were captured. Temporary browser viewport overrides were reset.

## Regression results

| Check | Result |
| --- | --- |
| `python -m unittest discover -s xai/tests -v` | **35 passed**, unchanged Python test suite |
| `node --test xai/tests/test_dashboard_frontend.cjs` | **29 passed**: original 17 retained, 12 visual/layout/interaction tests added |
| Existing XAI evaluation | **17 real cases**, **49 independent historical interventions**, passed |
| Maximum target/saved score error | `7.81343665323675e-08`, below unchanged **1e-6** guard |
| Maximum independent replay error | `1.1102230246251565e-16` |
| Faithfulness / stability | 33/34 perturbation directions agree; largest group stable in 16/17, all directions stable in 13/17. Existing limitations remain visible |
| Script syntax | `node --check xai/static/dashboard.js` passed |
| Source/evidence preservation | Approved summary, Python engine-related sources and complete technical renderer unchanged |
| `git diff --check` | Passed |
| Main / canonical DP pipeline | Untouched; no merge and no push to main |

Evaluation ran the existing `evaluate_xai.main()` and scoring code unchanged,
redirecting only its output directory to ignored scratch storage. This preserved
the already-open dashboard's local caches. The 17 cases include the original
16-case review set and the additional transaction 3008973 already cached by the
user. It did not retune thresholds, repeat September inference or claim universal
faithfulness/stability.

Detailed records: `python-tests.txt`, `frontend-tests.txt`, `evaluation.json`,
`browser-checks.json`, `mobile-checks.json`, `tablet-checks.json`,
`technical-checks.json`, `interaction-checks.json` and `validation.json`.

The branch is ready for human visual approval before any merge. The final pushed
commit SHA is reported in the chat rather than embedded into its own commit.
