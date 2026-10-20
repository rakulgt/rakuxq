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

- `RAKUXQ_ENGINE_DEFAULT_MOVETIME_MS`: default primary budget, initially `3000`.
- `RAKUXQ_ENGINE_MAX_MOVETIME_MS`: legacy input validation ceiling, initially `10000`;
  the effective primary budget is always capped at `3000` under the four-second policy.
- `RAKUXQ_ENGINE_COMMAND_TIMEOUT_MS`: protocol/startup timeout, initially `5000`.
- `RAKUXQ_ENGINE_CANDIDATE_MAX_LOSS_CP`: maximum exact-score loss for an alternative,
  initially `150` engine score points (not a calibrated win-probability threshold).

## Candidate moves

The default is a `MultiPV=1` primary search of up to 3000 ms, followed by an optional verification
stage of up to 1000 ms. The primary result is frozen before verification and never replaced by it.
Both stages reuse the same hash and hold one engine lock, with no interleaved requests or additional
processes. A single monotonic deadline caps their total budget at 4000 ms; 25 ms is reserved for
protocol/scheduling completion before the optional stage. Short primary requests allocate one-third
as much optional time (up to 1000 ms); a stage with less than 50 ms usable time is skipped. Unused
primary time is not converted into a longer alternative search. A unique legal move or terminal
position skips verification entirely. `best_move`, `score`, `depth`, nodes, nps and PV retain the
primary snapshot; `time_ms` now covers both stages. Automatic play never executes both suggestions.
`recommendations` contains one or two sibling moves, each with `move`, fixed-red `score`, `depth`,
`pv`, and `pv_notation`. A terminal position has an empty list. The Lab displays both when present;
the anonymous homepage feed continues to publish only the primary notation.

Verification uses `MultiPV=2` to compare two legal roots at the same completed depth, including the
frozen primary root. If that root is absent or the exact pair is unavailable, no alternative is
invented. The same-depth gap limit remains 150 engine points. A further conservative cross-stage
check rejects a large deterioration relative to the deeper primary, a huge apparent improvement
which may reflect unstable shallow search, or a degraded mate outcome. This is not a claim that
the 3-second and 1-second evaluations have equal precision. Two proven winning mates can both be
shown if the alternative is not shorter than the primary's known mate distance; a faster forced
loss is not offered. These are bounded-search heuristics, not game-theoretic guarantees.
Only one move is returned if a trustworthy pair is unavailable. `alternative_omitted_reason` is
`only_legal_move`, `score_gap`, `mate_outcome`, `insufficient_search`, `budget_exhausted`, or
`alternative_failed`; it is null when two moves are included (and for terminal results).
An optional failure still returns the completed primary result, never a full solve failure.
Incomplete verification iterations can fall back to a completed matching pair at most one ply
below the latest matching verification depth. No score from a different root is reused.

`search` exposes `strategy=primary_then_alternative`, `primary_budget_ms`, `alternative_budget_ms`,
`total_budget_ms`, both stage `*_time_ms`, `alternative_status`, `comparison_depth` and
`comparison_primary_score`. The comparison reference is from the short stage; top-level `score`
remains the deeper primary's score. Each recommendation reports its own depth and score.
`/v1/solutions` additionally includes requested/effective/actual time; `effective_time_ms` is the
total reserved budget, and `primary_budget_capped` discloses when an old larger request was capped.

`display_text` retains its old format for one move; for two it becomes, for example,
`首选：炮二平五 红优 80；备选：炮八平五 红优 50`. Both are choices for the current mover, not
consecutive plies. Existing Shortcuts reading this field need no changes.

The primary no longer shares its 3-second budget with another candidate, but wall-clock scheduling
and hash state can still vary; identical depth or Elo is not promised. Early primary mates may
still add up to one second of optional work. Upload, vision, queueing and response transport remain
outside the engine budget; this is not a millisecond-precise end-to-end response-time guarantee.
The API returns one final JSON response, not a streamed primary at 3 seconds and another message
at 4 seconds. This API sends only the current
FEN, not prior moves: two choices do **not** implement perpetual-check/chase adjudication or guarantee
avoidance of repetition. History-aware rules remain separate work.

## HTTP flow

The product-level FEN-to-solution endpoint uses `time_ms`, an optional primary budget defaulting to
three seconds, with up to one additional second for an alternative:

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
