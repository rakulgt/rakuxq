# Third-party notices

## xiangqi.js

RakuXQ bundles `xiangqi.min.js` from
[`lengyanyu258/xiangqi.js`](https://github.com/lengyanyu258/xiangqi.js), pinned to commit
`f9019ac2303d4b80ef0b82fd0515bfb55a80a62b`.

- Purpose: Xiangqi FEN loading, legal move generation, move validation, check/game-state detection,
  and undo support for the homepage interactive board.
- License: BSD 2-Clause License.
- Bundled license: `apps/api/src/rakuxq_api/static/vendor/xiangqi.LICENSE.txt`.
- RakuXQ provides its own board rendering and interaction design; no third-party board UI is bundled.

## Pikafish (optional, not bundled)

RakuXQ can control a separately installed
[`official-pikafish/Pikafish`](https://github.com/official-pikafish/Pikafish) executable through
the UCI protocol.

- Purpose: optional local best-move, score, principal-variation, and mate analysis.
- Engine license: GNU General Public License v3.0 (GPL-3.0).
- NNUE weights: separately licensed by the Pikafish Networks project; the official weights prohibit
  commercial use without permission.
- Distribution: neither the Pikafish executable nor its NNUE weights are included in this MIT
  repository, Python wheel, container image, or official production deployment.
- Current technical baseline: official `Pikafish-2026-09-06` release, downloaded independently for
  local non-commercial interoperability testing.

Users who install Pikafish separately are responsible for reviewing and complying with both the
engine and network terms. A future commercial hosted deployment requires explicit authorization for
the selected NNUE weights.
