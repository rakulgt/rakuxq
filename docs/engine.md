# RakuXQ engine integration

RakuXQ `v0.3` adds a replaceable Xiangqi-engine boundary. The first adapter controls Pikafish as a
separate persistent process through UCI; the vision provider does not import, link, or depend on the
engine implementation.

## License boundary

Pikafish and its official NNUE network are **not bundled** with RakuXQ. Pikafish source is GPL-3.0,
while the official network has separate terms that prohibit commercial use without permission.
The initial integration is therefore for local, non-commercial technical validation only. Do not
deploy the official network as part of a paid hosted service without permission from its owner.

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

To configure assets stored elsewhere, set the variables directly:

```powershell
$env:RAKUXQ_ENGINE_PATH = "D:\path\to\Pikafish-Windows-x86-64-universal.exe"
$env:RAKUXQ_ENGINE_NETWORK = "D:\path\to\pikafish.nnue"
$env:RAKUXQ_ENGINE_VERSION = "Pikafish-2026-09-06"
$env:RAKUXQ_ENGINE_THREADS = "1"
$env:RAKUXQ_ENGINE_HASH_MB = "64"
$env:RAKUXQ_ENGINE_DEFAULT_MOVETIME_MS = "500"
```

The service starts one persistent process and serializes searches through it. The conservative
one-thread/64-MiB defaults protect the vision process on a small host. Supported limits are:

- `RAKUXQ_ENGINE_DEFAULT_MOVETIME_MS`: default search budget, initially `500`.
- `RAKUXQ_ENGINE_MAX_MOVETIME_MS`: public request ceiling, initially `3000`.
- `RAKUXQ_ENGINE_COMMAND_TIMEOUT_MS`: protocol/startup timeout, initially `5000`.

## HTTP flow

Analyze an existing FEN:

```bash
curl -X POST http://127.0.0.1:8000/v1/analyses \
  -H "Content-Type: application/json" \
  -d '{"fen":"3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w","movetime_ms":500}'
```

Recognize an image and analyze only an accepted result:

```bash
curl -X POST http://127.0.0.1:8000/v1/solve \
  -F "image=@board.jpg" \
  -F "side_to_move=red" \
  -F "movetime_ms=500"
```

The engine is never invoked when recognition returns `review_required` or `rejected`.

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
- `KO(+N)`: engine reports a forced red mate at distance `N`;
- `KO(-N)`: engine reports a forced black mate at distance `N`.

The JSON retains structured `type`, `value`, and `perspective` fields. Clients that only need text
can display `score.display`. `best_move.iccs` and every entry in `pv` use ICCS coordinates.

Engine output is a bounded-compute recommendation, not a proof of an absolute best move unless the
reported line is a forced mate or independently solved position. Responses include the engine
version, network SHA-256, depth, nodes, elapsed time, and PV for reproducibility.
