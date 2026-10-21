// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Li Guotai
// Artifact-ID: rakuxq.native.engine
// Role: Independent experimental Xiangqi rules, search, incremental evaluation and UCI.
// Inputs: Valid FEN/UCI and optional RAKUXQ_NNUE_V1 parameters. Outputs: legal moves/PV.
// Provenance: Project-authored, AI-assisted; no imported engine implementation or weights.
// State: experimental, NOT approved to replace production. Version/evidence: manifest.json/CI.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace raku {
constexpr int Hidden = 32, Features = 1262, Mate = 30000, Infinity = 32000;
constexpr const char* Version = "0.1.0-experimental";
const std::string Pieces = "KABNRCPkabnrcp";
const std::string Start = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w";
std::mutex OutputMutex;
void emit(const std::string& text) {
    std::lock_guard<std::mutex> lock(OutputMutex);
    std::cout << text << std::endl;
}
bool red(char p) { return p >= 'A' && p <= 'Z'; }
char kind(char p) { return static_cast<char>(p >= 'A' && p <= 'Z' ? p + 32 : p); }
bool inside(int r, int f) { return r >= 0 && r < 10 && f >= 0 && f < 9; }
bool palace(int s, bool side) {
    return s % 9 >= 3 && s % 9 <= 5 && (side ? s / 9 >= 7 : s / 9 <= 2);
}
int feature(char p, int square) { return static_cast<int>(Pieces.find(p)) * 90 + square; }
std::uint64_t mix(std::uint64_t n) {
    n += 0x9e3779b97f4a7c15ULL;
    n = (n ^ (n >> 30)) * 0xbf58476d1ce4e5b9ULL;
    n = (n ^ (n >> 27)) * 0x94d049bb133111ebULL;
    return n ^ (n >> 31);
}
std::uint64_t piece_key(char p, int square) { return mix(static_cast<unsigned>(feature(p, square)) + 1); }
constexpr std::uint64_t TurnKey = 0x780baa10994312efULL;
struct Move {
    int from = -1, to = -1;
    bool operator==(const Move& m) const { return from == m.from && to == m.to; }
    std::string text() const {
        if (from < 0 || to < 0) return "0000";
        return std::string{static_cast<char>('a' + from % 9), static_cast<char>('0' + 9 - from / 9),
                           static_cast<char>('a' + to % 9), static_cast<char>('0' + 9 - to / 9)};
    }
};
struct Network {
    std::array<std::array<int, Hidden>, Features> weights{};
    std::array<int, Hidden> bias{}, output{};
    int output_bias = 0;
    static std::shared_ptr<Network> load(const std::string& path) {
        std::ifstream in(path);
        std::string magic;
        int f = 0, h = 0, scale = 0;
        if (!(in >> magic >> f >> h >> scale) || magic != "RAKUXQ_NNUE_V1" ||
            f != Features || h != Hidden || scale != 256)
            throw std::runtime_error("unsupported or corrupt RakuXQ network");
        auto net = std::make_shared<Network>();
        auto read = [&in](int& v, int bound) {
            long long x = 0;
            if (!(in >> x) || std::abs(x) > bound) throw std::runtime_error("invalid network parameter");
            v = static_cast<int>(x);
        };
        for (auto& v : net->bias) read(v, 1000000);
        for (auto& row : net->weights) for (auto& v : row) read(v, 32767);
        for (auto& v : net->output) read(v, 32767);
        read(net->output_bias, 1000000);
        std::string extra;
        if (in >> extra) throw std::runtime_error("unexpected trailing network content");
        return net;
    }
    int evaluate(const std::array<int, Hidden>& accumulator) const {
        std::int64_t value = static_cast<std::int64_t>(output_bias) * 256;
        for (int i = 0; i < Hidden; ++i)
            value += static_cast<std::int64_t>(std::clamp(accumulator[i], 0, 256)) * output[i];
        return static_cast<int>(std::clamp<std::int64_t>(value * 1000 / 65536, -15000, 15000));
    }
};
struct Position {
    std::array<char, 90> cells{};
    bool side = true;
    std::uint64_t key = 0;
    std::shared_ptr<const Network> network;
    std::array<int, Hidden> accumulator{};
    void add_feature(int f, int sign) {
        if (network) for (int i = 0; i < Hidden; ++i) accumulator[i] += sign * network->weights[f][i];
    }
    void refresh() {
        accumulator.fill(0);
        if (!network) return;
        accumulator = network->bias;
        for (int s = 0; s < 90; ++s) if (cells[s] != '.') add_feature(feature(cells[s], s), 1);
        add_feature(side ? 1260 : 1261, 1);
    }
    static Position parse(const std::string& fen, std::shared_ptr<const Network> net = {}) {
        Position p;
        p.cells.fill('.'); p.network = std::move(net);
        std::istringstream input(fen);
        std::string board, active, extra;
        if (!(input >> board >> active) || (active != "w" && active != "b"))
            throw std::runtime_error("FEN requires placement and w/b");
        std::vector<std::string> trailing;
        while (input >> extra) trailing.push_back(extra);
        if (!trailing.empty()) {
            if (trailing.size() != 4 || trailing[0] != "-" || trailing[1] != "-")
                throw std::runtime_error("FEN requires two or six fields");
            for (int i = 2; i < 4; ++i) {
                if (trailing[i].empty() || trailing[i].find_first_not_of("0123456789") != std::string::npos ||
                    trailing[i].size() > 9 || (i == 3 && std::stoll(trailing[i]) < 1))
                    throw std::runtime_error("invalid FEN counters");
            }
        }
        int row = 0, file = 0, kings[2] = {0, 0};
        for (char c : board) {
            if (c == '/') {
                if (file != 9 || row == 9) throw std::runtime_error("invalid FEN rank");
                ++row; file = 0;
            } else if (c >= '1' && c <= '9') {
                file += c - '0';
                if (file > 9) throw std::runtime_error("oversized FEN rank");
            } else {
                if (Pieces.find(c) == std::string::npos || file >= 9) throw std::runtime_error("invalid FEN piece");
                int s = row * 9 + file++;
                p.cells[s] = c; p.key ^= piece_key(c, s);
                if (kind(c) == 'k') {
                    ++kings[red(c) ? 1 : 0];
                    if (!palace(s, red(c))) throw std::runtime_error("king outside palace");
                }
            }
        }
        if (row != 9 || file != 9 || kings[0] != 1 || kings[1] != 1) throw std::runtime_error("invalid FEN board/kings");
        p.side = active == "w";
        if (p.side) p.key ^= TurnKey;
        if (p.checked(!p.side)) throw std::runtime_error("non-moving king is in check");
        p.refresh(); return p;
    }
    std::string fen() const {
        std::string out;
        for (int r = 0; r < 10; ++r) {
            int empty = 0;
            for (int f = 0; f < 9; ++f) {
                char c = cells[r * 9 + f];
                if (c == '.') ++empty;
                else { if (empty) out += static_cast<char>('0' + empty); empty = 0; out += c; }
            }
            if (empty) out += static_cast<char>('0' + empty);
            if (r != 9) out += '/';
        }
        return out + (side ? " w" : " b");
    }
    Position after(Move m) const {
        Position next = *this;
        char p = cells[m.from], captured = cells[m.to];
        next.key ^= piece_key(p, m.from) ^ piece_key(p, m.to) ^ TurnKey;
        next.add_feature(feature(p, m.from), -1); next.add_feature(feature(p, m.to), 1);
        if (captured != '.') {
            next.key ^= piece_key(captured, m.to);
            next.add_feature(feature(captured, m.to), -1);
        }
        next.add_feature(side ? 1260 : 1261, -1);
        next.add_feature(side ? 1261 : 1260, 1);
        next.cells[m.to] = p; next.cells[m.from] = '.'; next.side = !side;
        return next;
    }
    bool attacks(int from, int to) const {
        if (from == to) return false;
        char p = cells[from];
        int r = from / 9, f = from % 9, tr = to / 9, tf = to % 9;
        int dr = tr - r, df = tf - f;
        char type = kind(p);
        if ((type == 'r' || type == 'c' || type == 'k') && (dr == 0 || df == 0)) {
            int step = dr == 0 ? (df > 0 ? 1 : -1) : (dr > 0 ? 9 : -9);
            int screens = 0;
            for (int s = from + step; s != to; s += step) screens += cells[s] != '.';
            if (type == 'r') return screens == 0;
            if (type == 'c') return screens == (cells[to] == '.' ? 0 : 1);
            if (df == 0 && kind(cells[to]) == 'k') return screens == 0;
        }
        if (type == 'k') return std::abs(dr) + std::abs(df) == 1 && palace(to, red(p));
        if (type == 'a') return std::abs(dr) == 1 && std::abs(df) == 1 && palace(to, red(p));
        if (type == 'b') return std::abs(dr) == 2 && std::abs(df) == 2 &&
            (red(p) ? tr >= 5 : tr <= 4) && cells[(r + dr / 2) * 9 + f + df / 2] == '.';
        if (type == 'n') {
            if (std::abs(dr) == 2 && std::abs(df) == 1) return cells[(r + dr / 2) * 9 + f] == '.';
            if (std::abs(dr) == 1 && std::abs(df) == 2) return cells[r * 9 + f + df / 2] == '.';
        }
        if (type == 'p') return (dr == (red(p) ? -1 : 1) && df == 0) ||
            ((red(p) ? r <= 4 : r >= 5) && dr == 0 && std::abs(df) == 1);
        return false;
    }
    bool checked(bool color) const {
        int king = -1;
        for (int s = 0; s < 90; ++s) if (cells[s] == (color ? 'K' : 'k')) king = s;
        if (king < 0) return true;
        for (int s = 0; s < 90; ++s)
            if (cells[s] != '.' && red(cells[s]) != color && attacks(s, king)) return true;
        return false;
    }
    std::vector<Move> legal() const {
        std::vector<Move> result;
        auto offer = [&](int from, int r, int f) {
            if (!inside(r, f)) return;
            int to = r * 9 + f;
            char target = cells[to];
            if (target != '.' && (red(target) == side || kind(target) == 'k')) return;
            if (attacks(from, to) && !after({from, to}).checked(side)) result.push_back({from, to});
        };
        for (int from = 0; from < 90; ++from) {
            char p = cells[from];
            if (p == '.' || red(p) != side) continue;
            int r = from / 9, f = from % 9;
            char type = kind(p);
            if (type == 'r' || type == 'c') {
                for (auto d : {std::pair<int,int>{1,0}, {-1,0}, {0,1}, {0,-1}}) {
                    bool screen = false;
                    for (int tr = r + d.first, tf = f + d.second; inside(tr, tf); tr += d.first, tf += d.second) {
                        char t = cells[tr * 9 + tf];
                        if (!screen) {
                            offer(from, tr, tf);
                            if (t != '.') { if (type == 'r') break; screen = true; }
                        } else if (t != '.') { offer(from, tr, tf); break; }
                    }
                }
            } else if (type == 'n') {
                for (int dr : {-2,-1,1,2}) for (int df : {-2,-1,1,2})
                    if (std::abs(dr) + std::abs(df) == 3) offer(from, r + dr, f + df);
            } else if (type == 'a' || type == 'b') {
                int step = type == 'a' ? 1 : 2;
                for (int dr : {-step, step}) for (int df : {-step, step}) offer(from, r + dr, f + df);
            } else if (type == 'k') {
                offer(from, r + 1, f); offer(from, r - 1, f);
                offer(from, r, f + 1); offer(from, r, f - 1);
            } else if (type == 'p') {
                offer(from, r + (side ? -1 : 1), f); offer(from, r, f + 1); offer(from, r, f - 1);
            }
        }
        return result;
    }
    int red_evaluation() const {
        if (network) return network->evaluate(accumulator);
        int value = 0;
        for (int s = 0; s < 90; ++s) {
            char p = cells[s]; if (p == '.') continue;
            char k = kind(p); int score = 0;
            if (k == 'r') score = 800;
            if (k == 'n') score = 350;
            if (k == 'c') score = 400;
            if (k == 'a' || k == 'b') score = 120;
            if (k == 'p') {
                int advance = red(p) ? 9 - s / 9 : s / 9;
                score = 100 + 5 * advance + (advance >= 5 ? 40 : 0);
            }
            if (k == 'n' || k == 'r' || k == 'c') score += 3 * (4 - std::abs(s % 9 - 4));
            value += red(p) ? score : -score;
        }
        return value;
    }
};
std::uint64_t perft(const Position& p, int depth) {
    if (!depth) return 1;
    std::uint64_t nodes = 0;
    for (Move m : p.legal()) nodes += perft(p.after(m), depth - 1);
    return nodes;
}
struct Entry { std::uint64_t key = 0; int depth = -1, score = 0; int bound = 0; Move move; };
struct RootLine { Move move; int score = -Infinity; std::vector<Move> pv; };
struct SearchResult { Move move; int score = 0, depth = 0; std::uint64_t nodes = 0; std::vector<Move> pv; };
class Search {
    std::vector<Entry> table;
    std::atomic<bool>& stop;
    std::chrono::steady_clock::time_point deadline;
    std::uint64_t node_limit = std::numeric_limits<std::uint64_t>::max(), nodes = 0;
    std::vector<std::uint64_t> path;
    bool expired() {
        if (stop.load() || nodes >= node_limit || std::chrono::steady_clock::now() >= deadline) {
            stop.store(true); return true;
        }
        return false;
    }
    static int capture_value(char p) {
        switch (kind(p)) { case 'r': return 800; case 'c': return 400; case 'n': return 350;
            case 'a': case 'b': return 120; case 'p': return 100; default: return 0; }
    }
    void order(const Position& p, std::vector<Move>& moves, Move preferred) {
        std::stable_sort(moves.begin(), moves.end(), [&](Move a, Move b) {
            auto score = [&](Move m) { return (m == preferred ? 100000 : 0) +
                (p.cells[m.to] == '.' ? 0 : 10000 + 16 * capture_value(p.cells[m.to]) - capture_value(p.cells[m.from])); };
            return score(a) > score(b);
        });
    }
    int visit(const Position& p, int depth, int alpha, int beta, int ply, int qdepth, std::vector<Move>& pv) {
        ++nodes;
        if (expired()) return 0;
        if (ply >= 96) return p.side ? p.red_evaluation() : -p.red_evaluation();
        if (std::count(path.begin(), path.end(), p.key) >= 2) return 0;
        auto moves = p.legal();
        if (moves.empty()) return -Mate + ply;
        bool checked = p.checked(p.side);
        int original_alpha = alpha;
        Entry& slot = table[p.key % table.size()];
        Entry cached = slot;
        Move preferred;
        // Path-dependent repetition values are deliberately not used for TT cutoffs.
        if (cached.key == p.key) preferred = cached.move;
        if (depth <= 0) {
            int stand = p.side ? p.red_evaluation() : -p.red_evaluation();
            if (qdepth >= 8) return stand;
            if (!checked) {
                if (stand >= beta) return stand;
                alpha = std::max(alpha, stand);
                moves.erase(std::remove_if(moves.begin(), moves.end(), [&](Move m) { return p.cells[m.to] == '.'; }), moves.end());
            }
        }
        order(p, moves, preferred);
        int best = depth <= 0 && !checked ? alpha : -Infinity;
        Move best_move;
        path.push_back(p.key);
        for (Move move : moves) {
            std::vector<Move> child;
            int value = -visit(p.after(move), depth - 1, -beta, -alpha, ply + 1, depth <= 0 ? qdepth + 1 : 0, child);
            if (stop.load()) break;
            if (value > best) {
                best = value; best_move = move; pv = {move}; pv.insert(pv.end(), child.begin(), child.end());
            }
            alpha = std::max(alpha, value);
            if (alpha >= beta) break;
        }
        path.pop_back();
        if (!stop.load() && depth > 0 && best_move.from >= 0) {
            slot = {p.key, depth, best, best <= original_alpha ? -1 : best >= beta ? 1 : 0, best_move};
        }
        return best;
    }
public:
    explicit Search(std::atomic<bool>& flag, int hash_mb = 16) : stop(flag) {
        table.resize(static_cast<std::size_t>(std::clamp(hash_mb, 1, 128)) * 1024 * 1024 / sizeof(Entry));
    }
    void clear() { std::fill(table.begin(), table.end(), Entry{}); }
    SearchResult run(const Position& p, int ms, int max_depth = 32, int multipv = 1,
                     std::uint64_t max_nodes = std::numeric_limits<std::uint64_t>::max(), bool report = true,
                     const std::vector<std::uint64_t>& history = {}) {
        auto started = std::chrono::steady_clock::now();
        deadline = started + std::chrono::milliseconds(std::clamp(ms, 1, 9000));
        nodes = 0; node_limit = max_nodes; path = history;
        auto moves = p.legal();
        SearchResult result;
        if (moves.empty()) { result.score = -Mate; return result; }
        result.move = moves.front(); result.pv = {result.move};
        result.score = p.side ? p.red_evaluation() : -p.red_evaluation();
        for (int depth = 1; depth <= std::clamp(max_depth, 1, 64); ++depth) {
            std::vector<RootLine> lines;
            order(p, moves, result.move);
            int alpha = -Infinity;
            for (Move move : moves) {
                if (expired()) break;
                std::vector<Move> child;
                path.push_back(p.key);
                int score = -visit(p.after(move), depth - 1, -Infinity, multipv == 1 ? -alpha : Infinity, 1, 0, child);
                path.pop_back();
                if (stop.load()) break;
                RootLine line{move, score, {move}};
                line.pv.insert(line.pv.end(), child.begin(), child.end());
                lines.push_back(std::move(line)); alpha = std::max(alpha, score);
            }
            if (stop.load()) break;
            std::stable_sort(lines.begin(), lines.end(), [](const RootLine& a, const RootLine& b) { return a.score > b.score; });
            if (lines.empty()) break;
            result = {lines.front().move, lines.front().score, depth, nodes, lines.front().pv};
            int elapsed = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count());
            if (report) for (int i = 0; i < std::min(multipv, static_cast<int>(lines.size())); ++i) {
                const auto& line = lines[i];
                std::ostringstream info;
                info << "info depth " << depth << " multipv " << i + 1 << " score ";
                if (std::abs(line.score) > Mate - 100) {
                    int distance = (Mate - std::abs(line.score) + 1) / 2;
                    info << "mate " << (line.score < 0 ? -distance : distance);
                } else info << "cp " << line.score;
                info << " nodes " << nodes << " time " << elapsed << " nps " << nodes * 1000 / std::max(1, elapsed) << " pv";
                for (Move m : line.pv) info << ' ' << m.text();
                emit(info.str());
            }
            if (std::abs(result.score) > Mate - 100) break;
        }
        result.nodes = nodes;
        return result;
    }
};
int bounded_integer(const std::string& value, int low, int high) {
    std::size_t end = 0; long long n = std::stoll(value, &end);
    if (end != value.size() || n < low || n > high) throw std::runtime_error("integer outside limits");
    return static_cast<int>(n);
}
void selfplay(int games, int max_ply, int ms, unsigned seed, std::shared_ptr<const Network> network) {
    std::mt19937 random(seed);
    std::atomic<bool> stop{false}; Search search(stop, 4);
    struct Sample { std::string fen; int score, depth; };
    for (int game = 0; game < games; ++game) {
        Position p = Position::parse(Start, network);
        std::vector<Sample> samples;
        std::vector<std::uint64_t> history;
        int winner = 0; // 0 means unknown, not an adjudicated draw.
        for (int ply = 0; ply < max_ply; ++ply) {
            auto moves = p.legal();
            if (moves.empty()) { winner = p.side ? -1 : 1; break; }
            if (std::count(history.begin(), history.end(), p.key) >= 2) break;
            stop.store(false);
            auto answer = search.run(p, ms, 16, 1, 100000, false, history);
            if (answer.depth > 0) samples.push_back({p.fen(), p.side ? answer.score : -answer.score, answer.depth});
            Move move = ply < 12 || random() % 10 == 0 ? moves[random() % moves.size()] : answer.move;
            history.push_back(p.key); p = p.after(move);
        }
        if (!winner && p.legal().empty()) winner = p.side ? -1 : 1;
        for (const auto& sample : samples) {
            std::cout << "{\"game_id\":\"selfplay-" << seed << '-' << game << "\",\"fen\":\"" << sample.fen
                      << "\",\"score_cp\":" << sample.score << ",\"depth\":" << sample.depth
                      << ",\"outcome\":" << (winner ? std::to_string(winner) : "null")
                      << ",\"source\":\"rakuxq_selfplay\",\"network_used\":" << (network ? "true" : "false")
                      << ",\"engine_version\":\"" << Version << "\"}" << std::endl;
        }
    }
}
int cli(int argc, char** argv) {
    std::shared_ptr<const Network> network;
    int i = 1;
    if (i < argc && std::string(argv[i]) == "--network") {
        if (++i >= argc) throw std::runtime_error("missing network path");
        network = Network::load(argv[i++]);
    }
    if (i >= argc) throw std::runtime_error("missing operation");
    std::string command = argv[i++];
    if (command == "--version") { std::cout << "RakuXQ " << Version << std::endl; return 0; }
    if (command == "--selfplay") {
        if (argc - i != 4) throw std::runtime_error("selfplay requires games max-ply ms seed");
        int games = bounded_integer(argv[i], 2, 10000), plies = bounded_integer(argv[i+1], 2, 512);
        int ms = bounded_integer(argv[i+2], 1, 1000), seed = bounded_integer(argv[i+3], 0, 2147483647);
        selfplay(games, plies, ms, static_cast<unsigned>(seed), network); return 0;
    }
    int depth = 0;
    if (command == "--perft") {
        if (i >= argc) throw std::runtime_error("missing perft depth");
        depth = bounded_integer(argv[i++], 0, 5);
    }
    if (i + 1 != argc) throw std::runtime_error("one quoted FEN is required");
    Position p = Position::parse(argv[i], network);
    if (command == "--legal") {
        std::vector<std::string> moves;
        for (Move m : p.legal()) moves.push_back(m.text());
        std::sort(moves.begin(), moves.end());
        for (const auto& move : moves) std::cout << move << ' ';
        std::cout << std::endl;
    } else if (command == "--perft") std::cout << perft(p, depth) << std::endl;
    else if (command == "--evaluate") std::cout << p.red_evaluation() << std::endl;
    else if (command == "--verify-accumulator") {
        auto verify = [](const Position& pos) { Position copy = pos; copy.refresh(); return copy.accumulator == pos.accumulator; };
        if (!verify(p)) throw std::runtime_error("root accumulator mismatch");
        for (Move m : p.legal()) {
            Position child = p.after(m);
            if (!verify(child)) throw std::runtime_error("incremental accumulator mismatch");
            for (Move reply : child.legal()) if (!verify(child.after(reply))) throw std::runtime_error("reply accumulator mismatch");
        }
        std::cout << "ok" << std::endl;
    } else throw std::runtime_error("unknown operation");
    return 0;
}
int uci() {
    std::atomic<bool> stop{false};
    std::thread worker;
    auto join = [&] { stop.store(true); if (worker.joinable()) worker.join(); };
    std::shared_ptr<const Network> network;
    Position position = Position::parse(Start);
    std::vector<std::uint64_t> history;
    int hash_mb = 16, multipv = 1;
    auto search = std::make_unique<Search>(stop, hash_mb);
    bool network_error = false, position_error = false;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream input(line);
        std::string command; input >> command;
        try {
            if (command == "uci") {
                emit(std::string("id name RakuXQ ") + Version + "\nid author Li Guotai / RakuXQ contributors\n"
                    "option name Hash type spin default 16 min 1 max 128\n"
                    "option name Threads type spin default 1 min 1 max 1\n"
                    "option name MultiPV type spin default 1 min 1 max 2\n"
                    "option name EvalFile type string default <empty>\nuciok");
            } else if (command == "isready") emit("readyok");
            else if (command == "quit") { join(); break; }
            else if (command == "stop") join();
            else if (command == "ucinewgame") { join(); history.clear(); search->clear(); }
            else if (command == "setoption") {
                join(); auto start = line.find("name "), value = line.find(" value ");
                if (start == std::string::npos || value == std::string::npos) continue;
                std::string name = line.substr(start + 5, value - start - 5), setting = line.substr(value + 7);
                if (name == "Hash") {
                    hash_mb = bounded_integer(setting, 1, 128);
                    search = std::make_unique<Search>(stop, hash_mb);
                }
                if (name == "Threads") (void)bounded_integer(setting, 1, 1);
                if (name == "MultiPV") multipv = bounded_integer(setting, 1, 2);
                if (name == "EvalFile") {
                    network_error = true;
                    network = setting.empty() || setting == "<empty>" ? nullptr : Network::load(setting);
                    position.network = network; position.refresh(); network_error = false;
                    search->clear();
                }
            } else if (command == "position") {
                join(); position_error = true;
                std::string mode; input >> mode;
                std::vector<std::string> tokens; std::string token;
                while (input >> token) tokens.push_back(token);
                auto moves_at = std::find(tokens.begin(), tokens.end(), "moves");
                std::string fen = Start;
                if (mode == "fen") { fen.clear(); for (auto at = tokens.begin(); at != moves_at; ++at) fen += *at + " "; }
                else if (mode != "startpos") throw std::runtime_error("unsupported position mode");
                Position candidate = Position::parse(fen, network);
                std::vector<std::uint64_t> next_history;
                if (moves_at != tokens.end()) for (auto at = moves_at + 1; at != tokens.end(); ++at) {
                    auto moves = candidate.legal();
                    auto selected = std::find_if(moves.begin(), moves.end(), [&](Move m) { return m.text() == *at; });
                    if (selected == moves.end()) throw std::runtime_error("illegal position move");
                    next_history.push_back(candidate.key); candidate = candidate.after(*selected);
                }
                position = candidate; history = std::move(next_history); position_error = false;
            } else if (command == "go") {
                join();
                if (network_error || position_error) { emit("info string invalid position/network\nbestmove 0000"); continue; }
                int ms = 3000, depth = 32;
                std::uint64_t nodes = std::numeric_limits<std::uint64_t>::max();
                std::string token, value;
                while (input >> token) {
                    if (token == "movetime" || token == "depth" || token == "nodes") {
                        if (!(input >> value)) throw std::runtime_error("missing go value");
                        int parsed = bounded_integer(value, 1, token == "depth" ? 64 : 1000000000);
                        if (token == "movetime") ms = std::min(parsed, 9000);
                        if (token == "depth") depth = parsed;
                        if (token == "nodes") nodes = static_cast<std::uint64_t>(parsed);
                    }
                }
                stop.store(false);
                worker = std::thread([&, board = position, past = history, ms, depth, nodes] {
                    try {
                        auto result = search->run(board, ms, depth, multipv, nodes, true, past);
                        if (result.depth == 0) emit("info depth 0 score cp " + std::to_string(result.score) + " pv " + result.move.text());
                        emit("bestmove " + result.move.text());
                    } catch (const std::exception&) { emit("info string search failed\nbestmove 0000"); }
                });
            }
        } catch (const std::exception& error) { emit(std::string("info string ERROR: ") + error.what()); }
    }
    join(); return 0;
}
} // namespace raku
int main(int argc, char** argv) {
    try { return argc > 1 ? raku::cli(argc, argv) : raku::uci(); }
    catch (const std::exception& e) { std::cerr << "RakuXQ: " << e.what() << std::endl; return 2; }
}
