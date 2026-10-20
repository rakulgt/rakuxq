# RakuXQ engine integration

RakuXQ `v0.3` adds a replaceable Xiangqi-engine boundary. The first adapter controls Pikafish as a
separate persistent process through UCI; the vision provider does not import, link, or depend on the
engine implementation.

## License boundary

Pikafish and its official NNUE network are **not bundled** with RakuXQ. Pikafish source is GPL-3.0,
while the official network has separate terms that prohibit commercial use without permission.
The initial integration is therefore for non-commercial technical validation only. A maintainer may
run a private server-side installation for personal use, but it must not be exposed to trial or
customer keys. Do not offer the official network as part of a paid hosted service without permission
from its owner.

Read [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) and the upstream
[network license](https://github.com/official-pikafish/Networks/blob/master/README.md) before use.

## Local configuration

Install the separately downloaded Pikafish executable and compatible `pikafish.nnue` outside Git,
then set:

```powershell
pwsh -NoProfile -File scripts/setup-pikafish.ps1
```

The pinned setup script downloads the official `Pikafish-2026-09-06` archive, verifies GitHub's
published SHA-256, extracts it under the ignored `tmp/` directory, reports the network SHA-256, and
prints the exact environment variables. It does not commit or redistribute either artifact. The
verified release, executable, and network metadata are recorded in
[`engines/manifest.json`](../engines/manifest.json).

The maintainer-only hosted validation baseline currently pins Pikafish commit
`1c66b9b21cf2f280ce3b3ffa80c1c6609f2b29ff` and the matching `master-net` network SHA-256
`6b74ac7bbd299dc26a17803135b616eda9248bef0cbfc7b811bfcf981832ba29`. It was built in Rocky
Linux 9 for the production OpenCloudOS 9 runtime. This rolling baseline is available only to the
maintainer's allowlisted key and does not change the commercial-use restriction.

For repeatable upgrades, `.github/workflows/build-pikafish-master.yml` builds a pinned upstream
commit in a production-compatible container, `scripts/install-pikafish-master-server.sh` stages and
verifies the engine/network pair without switching traffic, and
`scripts/activate-pikafish-master-server.sh` performs an atomic environment switch with automatic
rollback. Run `scripts/benchmark-pikafish.py` against both pairs before activation. Never combine a
rolling engine commit with an unverified or unrelated network.

To configure assets stored elsewhere, set the variables directly:

```powershell
$env:RAKUXQ_ENGINE_PATH = "D:\path\to\Pikafish-Windows-x86-64-universal.exe"
$env:RAKUXQ_ENGINE_NETWORK = "D:\path\to\pikafish.nnue"
$env:RAKUXQ_ENGINE_VERSION = "Pikafish-2026-09-06"
$env:RAKUXQ_ENGINE_THREADS = "1"
$env:RAKUXQ_ENGINE_HASH_MB = "64"
$env:RAKUXQ_ENGINE_DEFAULT_MOVETIME_MS = "3000"
```

The service starts one persistent process and serializes searches through it. The conservative
one-thread/64-MiB defaults protect the vision process on a small host. Supported limits are:

- `RAKUXQ_ENGINE_ALLOWED_KEY_IDS`: comma-separated key IDs allowed to call engine routes when API
  authentication is enabled. An empty value denies every hosted key; it never contains plaintext
  keys.

- `RAKUXQ_ENGINE_DEFAULT_MOVETIME_MS`: default search budget, initially `3000`.
- `RAKUXQ_ENGINE_MAX_MOVETIME_MS`: public request ceiling, initially `10000`.
- `RAKUXQ_ENGINE_COMMAND_TIMEOUT_MS`: protocol/startup timeout, initially `5000`.
- `RAKUXQ_ENGINE_CANDIDATE_MAX_LOSS_CP`: maximum exact-score loss for an alternative,
  initially `150` engine score points (not a calibrated win-probability threshold).

## Candidate moves

The default is a single `MultiPV=2` search within the existing shared time budget (3000 ms unless
overridden), not two sequential searches. One legal evasion uses `MultiPV=1`. `best_move`, `score`,
and `pv` still describe the first choice; automatic play never executes both suggestions.
`recommendations` contains one or two sibling moves, each with `move`, fixed-red `score`, `depth`,
`pv`, and `pv_notation`. A terminal position has an empty list. The Lab displays both when present;
the anonymous homepage feed continues to publish only the primary notation.

An alternative requires a distinct legal root, a same-depth pair of exact (not bound) scores, and
at most a 150-point loss in mover perspective. It cannot replace a known winning mate with an
unproven/mated line, nor introduce a forced loss where the first line has none. Two proven winning
mates can both be shown, even if the second is longer. With two losing mate lines, an earlier loss
is suppressed. These are bounded-search heuristics, not guaranteed game-theoretic evaluations.
Only one move is returned if a trustworthy pair is unavailable. `alternative_omitted_reason` is
`only_legal_move`, `score_gap`, `mate_outcome`, or `insufficient_search`; it is null when two moves
are included (and for terminal results). Incomplete iterations may fall back to a completed pair
at a reported lower depth matching the actual bestmove (at most one ply below that move's latest
reported depth); no score from a different root is reused.

`display_text` retains its old format for one move; for two it becomes, for example,
`首选：炮二平五 红优 80；备选：炮八平五 红优 50`. Both are choices for the current mover, not
consecutive plies. Existing Shortcuts reading this field need no changes.

At fixed wall time, MultiPV trades some depth for breadth and does not guarantee unchanged strength.
Early mate searches that previously finished immediately may now consume the full budget. Upload,
queueing and response transport remain outside the engine budget. This API sends only the current
FEN, not prior moves: two choices do **not** implement perpetual-check/chase adjudication or guarantee
avoidance of repetition. History-aware rules remain separate work.

## HTTP flow

The product-level FEN-to-solution endpoint uses `time_ms`, which is optional and defaults to three
seconds:

```bash
curl -X POST http://127.0.0.1:8000/v1/solutions \
  -H "Content-Type: application/json" \
  -d '{"fen":"3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w","time_ms":3000}'
```

It returns `best_move.notation` using red Chinese numerals and black Arabic numerals,
`display_text` for direct UI or notification use, a fixed-red-perspective score, `pv_notation`,
and explicit requested/effective/actual timing metadata.

Analyze an existing FEN:

```bash
curl -X POST http://127.0.0.1:8000/v1/analyses \
  -H "Content-Type: application/json" \
  -d '{"fen":"3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w","movetime_ms":3000}'
```

Recognize an image and analyze only an accepted result:

```bash
curl -X POST http://127.0.0.1:8000/v1/solve \
  -F "image=@board.jpg" \
  -F "side_to_move=red" \
  -F "movetime_ms=3000"
```

The engine is never invoked when recognition returns `review_required` or `rejected`.

### Check, terminal positions and partial results

Before UCI, the server rejects positions where the non-moving king is in check with
`SIDE_TO_MOVE_CONFLICT`. Being in check on the moving side is valid, including a position with
only one legal evasion. Forced-mate scores do not mean the game is already over. The server
enumerates legal moves to distinguish checkmate from Xiangqi stalemate (both losses for the mover);
terminal results have `status=terminal`, `best_move=null`, `score=null`, explicit winner/reason in
`position`, and a readable `display_text`. The product solution wrapper retains `status=accepted`
and adds `analysis_status=terminal` or `completed`.

Once image recognition succeeds, `/v1/solve` returns HTTP 200 even if analysis fails, preserving
the original FEN and full `recognition`. A position conflict uses `status=review_required` and
`analysis_status=invalid_position`; a runtime analysis failure uses `status=partial_success` and
`analysis_status=failed`. Both include `analysis=null`, `display_text`, and `error` with `code`,
`message`, and the original analysis `http_status`. Callers must inspect the business status.
FEN-only endpoints retain their non-2xx error contract. No path silently changes the supplied mover.
See [`api.md`](api.md) for the full response matrix. Run `npm run test:engine-rules` to compare the
server checks against the pinned browser rules on a deterministic 724-position corpus.

## Browser lab

Open `http://127.0.0.1:8000/lab` after starting the configured service. A standard position can be
opened without any separate import step by appending its FEN to `/fen/`:

```text
http://127.0.0.1:8000/fen/3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4%20w
```

Red and black assistance are independent: off, score only, best-move hint, or automatic play.
Analysis metadata is stored with the corresponding local variation-tree node. A key entered in the
lab is kept in page memory only and is never exported or written to browser-local storage.

## Stable score semantics

All scores use a fixed **red perspective**, independent of the side to move:

- positive integer: red advantage, for example `+186`;
- negative integer: black advantage, for example `-243`;
- zero: approximately balanced;
- `红方 KO(N)`: engine reports a forced red mate at distance `N`;
- `黑方 KO(N)`: engine reports a forced black mate at distance `N`.

For non-mate scores the human-facing display is `红优 N`, `黑优 N`, or `均势 0`.
The structured `score.value` remains a signed integer from Red's fixed perspective for sorting,
thresholds, and backward-compatible program logic.

The JSON retains structured `type`, `value`, and `perspective` fields. Clients that only need text
can display `score.display`. `best_move.notation` and `pv_notation` use standard Chinese notation;
`best_move.iccs` and every entry in `pv` retain ICCS coordinates for software clients.

Engine output is a bounded-compute recommendation, not a proof of an absolute best move unless the
reported line is a forced mate or independently solved position. Responses include the engine
version, network SHA-256, depth, nodes, elapsed time, and PV for reproducibility.
