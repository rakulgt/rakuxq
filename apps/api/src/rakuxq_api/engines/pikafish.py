from __future__ import annotations

import hashlib
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .base import (
    AnalysisResult,
    EngineAnalysisError,
    EngineIdentity,
    EngineMove,
    EngineNotConfigured,
    EngineScore,
    EngineTimeout,
    normalize_engine_fen,
    score_from_side_to_move,
)


@dataclass(slots=True)
class _InfoLine:
    depth: int = 0
    seldepth: int | None = None
    nodes: int | None = None
    time_ms: int = 0
    nps: int | None = None
    score_type: str | None = None
    score_value: int | None = None
    score_bound: str | None = None
    pv: list[str] | None = None


def _integer_after(tokens: list[str], name: str) -> int | None:
    try:
        return int(tokens[tokens.index(name) + 1])
    except (ValueError, IndexError):
        return None


def parse_uci_info(line: str) -> _InfoLine | None:
    tokens = line.split()
    if not tokens or tokens[0] != "info":
        return None
    multipv = _integer_after(tokens, "multipv")
    if multipv not in {None, 1}:
        return None

    parsed = _InfoLine(
        depth=_integer_after(tokens, "depth") or 0,
        seldepth=_integer_after(tokens, "seldepth"),
        nodes=_integer_after(tokens, "nodes"),
        time_ms=_integer_after(tokens, "time") or 0,
        nps=_integer_after(tokens, "nps"),
    )
    try:
        score_index = tokens.index("score")
        parsed.score_type = tokens[score_index + 1]
        parsed.score_value = int(tokens[score_index + 2])
        remainder = tokens[score_index + 3 :]
        if "lowerbound" in remainder:
            parsed.score_bound = "lower"
        elif "upperbound" in remainder:
            parsed.score_bound = "upper"
    except (ValueError, IndexError):
        pass
    try:
        pv_index = tokens.index("pv")
        parsed.pv = tokens[pv_index + 1 :]
    except ValueError:
        pass
    return parsed


class PikafishEngine:
    """Persistent Pikafish subprocess controlled through the UCI protocol."""

    def __init__(
        self,
        executable: str,
        network: str,
        *,
        threads: int = 1,
        hash_mb: int = 64,
        command_timeout_ms: int = 5_000,
        version: str = "unknown",
    ) -> None:
        self.executable = Path(executable).expanduser() if executable else None
        self.network = Path(network).expanduser() if network else None
        self.threads = max(1, threads)
        self.hash_mb = max(16, hash_mb)
        self.command_timeout_ms = max(1_000, command_timeout_ms)
        self.version = version
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._identity: EngineIdentity | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.executable
            and self.executable.is_file()
            and self.network
            and self.network.is_file()
        )

    @property
    def ready(self) -> bool:
        return bool(self._process and self._process.poll() is None and self._identity)

    @property
    def identity(self) -> EngineIdentity | None:
        return self._identity

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                self._lines.put(line.rstrip("\r\n"))
        finally:
            self._lines.put(None)

    def _send(self, command: str) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise EngineAnalysisError("Pikafish process is not running")
        try:
            process.stdin.write(f"{command}\n")
            process.stdin.flush()
        except OSError as exc:
            raise EngineAnalysisError("failed to write to Pikafish") from exc

    def _read_until(self, target: str, timeout_ms: int) -> list[str]:
        deadline = time.monotonic() + timeout_ms / 1000
        lines: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EngineTimeout(f"timed out waiting for Pikafish {target}")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise EngineTimeout(f"timed out waiting for Pikafish {target}") from exc
            if line is None:
                raise EngineAnalysisError("Pikafish terminated unexpectedly")
            lines.append(line)
            if "CRITICAL ERROR" in line or "ERROR:" in line:
                raise EngineAnalysisError(line)
            if line == target or line.startswith(f"{target} "):
                return lines

    def start(self) -> None:
        with self._lock:
            if self.ready:
                return
            if not self.configured:
                raise EngineNotConfigured(
                    "set RAKUXQ_ENGINE_PATH and RAKUXQ_ENGINE_NETWORK to readable files"
                )
            self._terminate()
            self._lines = queue.Queue()
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            assert self.executable is not None
            try:
                self._process = subprocess.Popen(
                    [str(self.executable.resolve())],
                    cwd=str(self.executable.resolve().parent),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise EngineAnalysisError("failed to start Pikafish executable") from exc
            self._reader = threading.Thread(
                target=self._read_stdout,
                name="rakuxq-pikafish-output",
                daemon=True,
            )
            self._reader.start()

            self._send("uci")
            startup_lines = self._read_until("uciok", self.command_timeout_ms)
            name = "Pikafish"
            author: str | None = None
            for line in startup_lines:
                if line.startswith("id name "):
                    name = line.removeprefix("id name ").strip()
                elif line.startswith("id author "):
                    author = line.removeprefix("id author ").strip()

            assert self.network is not None
            self._send(f"setoption name Threads value {self.threads}")
            self._send(f"setoption name Hash value {self.hash_mb}")
            self._send("setoption name MultiPV value 1")
            self._send(f"setoption name EvalFile value {self.network.resolve()}")
            self._send("isready")
            self._read_until("readyok", self.command_timeout_ms)
            self._send("ucinewgame")
            self._send("isready")
            self._read_until("readyok", self.command_timeout_ms)

            digest_builder = hashlib.sha256()
            with self.network.open("rb") as network_file:
                for block in iter(lambda: network_file.read(1024 * 1024), b""):
                    digest_builder.update(block)
            digest = digest_builder.hexdigest()
            self._identity = EngineIdentity(
                name=name,
                author=author,
                version=self.version,
                network_sha256=digest,
            )

    def _terminate(self) -> None:
        process = self._process
        self._process = None
        self._identity = None
        if process is None:
            return
        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write("quit\n")
                    process.stdin.flush()
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=2)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()

    def close(self) -> None:
        with self._lock:
            self._terminate()

    def _recover_after_failure(self) -> None:
        self._terminate()

    def analyze(self, fen: str, movetime_ms: int) -> AnalysisResult:
        normalized_fen = normalize_engine_fen(fen)
        active_color = normalized_fen.split()[1]
        with self._lock:
            if not self.ready:
                # start() owns the same lock, so perform startup before entering analysis.
                pass
        if not self.ready:
            self.start()

        with self._lock:
            started = time.monotonic()
            try:
                self._send(f"position fen {normalized_fen}")
                self._send(f"go movetime {movetime_ms}")
                timeout_ms = max(self.command_timeout_ms, movetime_ms + 2_000)
                lines = self._read_until("bestmove", timeout_ms)
            except Exception:
                self._recover_after_failure()
                raise

            latest = _InfoLine()
            best_move_value: str | None = None
            ponder: str | None = None
            for line in lines:
                parsed = parse_uci_info(line)
                if (
                    parsed is not None
                    and parsed.score_value is not None
                    and parsed.pv is not None
                    and (
                    parsed.depth > latest.depth
                    or (parsed.depth == latest.depth and parsed.pv is not None)
                    )
                ):
                    latest = parsed
                if line.startswith("bestmove"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] not in {"(none)", "0000"}:
                        best_move_value = parts[1]
                    if "ponder" in parts:
                        index = parts.index("ponder")
                        if index + 1 < len(parts):
                            ponder = parts[index + 1]

            score: EngineScore | None = None
            if latest.score_type is not None and latest.score_value is not None:
                score = score_from_side_to_move(
                    latest.score_type,
                    latest.score_value,
                    active_color,
                    latest.score_bound,
                )
            best_move = None
            if best_move_value is not None:
                best_move = EngineMove(
                    iccs=best_move_value,
                    from_square=best_move_value[:2],
                    to_square=best_move_value[2:4],
                )
            elapsed_ms = max(latest.time_ms, round((time.monotonic() - started) * 1000))
            return AnalysisResult(
                status="completed",
                fen=normalized_fen,
                best_move=best_move,
                ponder=ponder,
                score=score,
                depth=latest.depth,
                seldepth=latest.seldepth,
                nodes=latest.nodes,
                time_ms=elapsed_ms,
                nps=latest.nps,
                pv=latest.pv or [],
                engine=self._identity,
            )
