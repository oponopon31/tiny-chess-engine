# tiny-chess-01 entry (MIT): a compact 0x88 chess engine.
# Alpha-beta + transposition table + quiescence under a fixed node budget
# (no clock, so a trial replays identically). Talks to the env at
# MAKEFUN_ENV_URL: POST /game, /move, /resign. Python 3 stdlib only.
import json, os, sys, urllib.request, urllib.error, random

ENV = os.environ.get("MAKEFUN_ENV_URL") or sys.exit("MAKEFUN_ENV_URL is not set")
BUDGET = 200000  # nodes per move; clean-CPU speed is ~85k nps, so ~2-4 s/move

# --- piece codes: 1..6 white, 9..14 black; type = p & 7, colour = p >> 3
VAL = [0, 100, 320, 330, 500, 900, 0]
# Piece-square tables, rows rank 8 first. Own values, standard shapes.
PST = [
 [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10, 5, 5, 10, 25, 25, 10, 5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5, 5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
 [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40, -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30, -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
 [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
 [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0],
 [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5, 0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10, -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
 [-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20, -20, -20, -20, -10, 20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30, 20],
]
KEG = [-50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0, 0, -10, -20, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -30, 0, 0, 0, 0, -30, -30, -50, -30, -30, -30, -30, -30, -30, -50]
# PST index for white: M[sq]; for black: M[sq] ^ 56.
M = [(7 - (s >> 4)) * 8 + (s & 7) for s in range(128)]
PIDX = [M, [m ^ 56 for m in M]]

# Zobrist keys, fixed seed (deterministic across runs).
_rng = random.Random(20261117)
ZK = [[_rng.getrandbits(64) for _ in range(128)] for _ in range(15)]
ZKS = _rng.getrandbits(64)
ZKC = [_rng.getrandbits(64) for _ in range(16)]
ZKE = [_rng.getrandbits(64) for _ in range(8)]

KN = [-33, -31, -18, -14, 14, 18, 31, 33]
KI = [-17, -16, -15, -1, 1, 15, 16, 17]
BI = [-17, -15, 15, 17]
RO = [-16, -1, 1, 16]
DIRS = [[], [], KN, BI, RO, BI + RO, KI]
# Castling rights to keep after a move from/to a square (15 = keep all).
KEEP = [15] * 128
KEEP[0] = 13; KEEP[7] = 14; KEEP[4] = 12; KEEP[112] = 7; KEEP[119] = 11; KEEP[116] = 3

# --- mutable state (module globals for speed)
B = [0] * 128          # board
T = 0                  # side to move: 0 white, 1 black
CR = 0                 # castling rights: 1 WK 2 WQ 4 BK 8 BQ
EP = -1                # en passant square, or -1
HC = 0                 # halfmove clock
Z = 0                  # zobrist key
V = 0                  # incremental mg score, white-relative
K = 0                  # incremental king eg-mg difference, white-relative
NPM = 0                # non-pawn material (both sides)
CNT = [0] * 15         # piece counts by code
PF = [0] * 16          # pawn counts by colour*8+file
KSQ = [0, 0]           # king squares
nodes = 0
TT = {}
KIL = [[0, 0] for _ in range(256)]
HIS = [0] * (15 * 128)
hist = {}              # game repetition keys
path = {}              # search-path keys


def upd(sq, p, s):
    """Add (s=+1) or remove (s=-1) piece p on sq from the incremental score."""
    global V, K, NPM
    t = p & 7; c = p >> 3; sg = 1 if c == 0 else -1
    i = PIDX[c][sq]
    V += s * sg * (VAL[t] + PST[t - 1][i])
    if t == 6:
        K += s * sg * (KEG[i] - PST[5][i])
    elif t == 1:
        PF[c * 8 + (sq & 7)] += s
    else:
        NPM += s * VAL[t]
    CNT[p] += s


def att(sq, by):
    """Is sq attacked by colour `by`?"""
    b = B
    if by == 0:
        for d in (-15, -17):
            q = sq + d
            if 0 <= q < 128 and not (q & 0x88) and b[q] == 1:
                return True
    else:
        for d in (15, 17):
            q = sq + d
            if 0 <= q < 128 and not (q & 0x88) and b[q] == 9:
                return True
    for d in KN:
        q = sq + d
        if 0 <= q < 128 and not (q & 0x88) and b[q] == 2 + by * 8:
            return True
    for d in KI:
        q = sq + d
        if 0 <= q < 128 and not (q & 0x88) and b[q] == 6 + by * 8:
            return True
    for d in BI:
        q = sq + d
        while not (q & 0x88):
            p = b[q]
            if p:
                if (p >> 3) == by and (p & 7) in (3, 5):
                    return True
                break
            q += d
    for d in RO:
        q = sq + d
        while not (q & 0x88):
            p = b[q]
            if p:
                if (p >> 3) == by and (p & 7) in (4, 5):
                    return True
                break
            q += d
    return False


SQ64 = tuple(s for s in range(128) if not s & 0x88)


def gen(caps=False):
    """Pseudo-legal moves for the side to move, as ints f | t<<7 | promo<<14.
    With caps=True, only captures, promotions and en-passant captures."""
    ms = []
    b = B
    for sq in SQ64:
        p = b[sq]
        if not p or (p >> 3) != T:
            continue
        t = p & 7
        if t == 1:
            d = 16 if T == 0 else -16
            last = 7 if T == 0 else 0
            to = sq + d
            if not (to & 0x88) and b[to] == 0:
                if (to >> 4) == last:
                    for pr in (5, 4, 3, 2):
                        ms.append(sq | to << 7 | pr << 14)
                elif not caps:
                    ms.append(sq | to << 7)
                    if (sq >> 4) == (1 if T == 0 else 6):
                        to2 = sq + 2 * d
                        if b[to2] == 0:
                            ms.append(sq | to2 << 7)
            for df in (-1, 1):
                to = sq + d + df
                if to & 0x88:
                    continue
                q = b[to]
                if q and (q >> 3) != T:
                    if (to >> 4) == last:
                        for pr in (5, 4, 3, 2):
                            ms.append(sq | to << 7 | pr << 14)
                    else:
                        ms.append(sq | to << 7)
                elif to == EP and EP >= 0:
                    ms.append(sq | to << 7)
        elif t == 2 or t == 6:
            for d in DIRS[t]:
                to = sq + d
                if to & 0x88:
                    continue
                q = b[to]
                if caps:
                    if q and (q >> 3) != T:
                        ms.append(sq | to << 7)
                elif not q or (q >> 3) != T:
                    ms.append(sq | to << 7)
            if t == 6 and not caps:
                if T == 0:
                    if CR & 1 and b[5] == 0 and b[6] == 0 and b[7] == 4 and not att(4, 1) and not att(5, 1) and not att(6, 1):
                        ms.append(4 | 6 << 7)
                    if CR & 2 and b[3] == 0 and b[2] == 0 and b[1] == 0 and b[0] == 4 and not att(4, 1) and not att(3, 1) and not att(2, 1):
                        ms.append(4 | 2 << 7)
                else:
                    if CR & 4 and b[117] == 0 and b[118] == 0 and b[119] == 12 and not att(116, 0) and not att(117, 0) and not att(118, 0):
                        ms.append(116 | 118 << 7)
                    if CR & 8 and b[115] == 0 and b[114] == 0 and b[113] == 0 and b[112] == 12 and not att(116, 0) and not att(115, 0) and not att(114, 0):
                        ms.append(116 | 114 << 7)
        else:
            for d in DIRS[t]:
                to = sq + d
                while not (to & 0x88):
                    q = b[to]
                    if not q:
                        if not caps:
                            ms.append(sq | to << 7)
                    else:
                        if (q >> 3) != T:
                            ms.append(sq | to << 7)
                        break
                    to += d
    return ms


def make(m):
    """Play move m; return an undo record."""
    global CR, EP, HC, Z, V, K, NPM, T
    f = m & 127; t = (m >> 7) & 127; pr = (m >> 14) & 7
    p = B[f]; c = p >> 3; tp = p & 7
    cap = B[t]
    ocr, oep, ohc, oz, ov, ok, onpm = CR, EP, HC, Z, V, K, NPM
    upd(f, p, -1); B[f] = 0; Z ^= ZK[p][f]
    ec = -1
    if cap:
        upd(t, cap, -1); B[t] = 0; Z ^= ZK[cap][t]
    elif tp == 1 and t == EP and EP >= 0:
        ec = t + (-16 if c == 0 else 16)
        cp = B[ec]
        upd(ec, cp, -1); B[ec] = 0; Z ^= ZK[cp][ec]
        cap = cp
    np = pr + c * 8 if pr else p
    upd(t, np, 1); B[t] = np; Z ^= ZK[np][t]
    if tp == 6:
        KSQ[c] = t
    rm = 0
    if tp == 6 and abs(t - f) == 2:
        rf, rt = (f + 3, f + 1) if t > f else (f - 4, f - 1)
        rp = B[rf]
        upd(rf, rp, -1); B[rf] = 0; Z ^= ZK[rp][rf]
        upd(rt, rp, 1); B[rt] = rp; Z ^= ZK[rp][rt]
        rm = rf | rt << 7
    Z ^= ZKC[CR]
    CR &= KEEP[f] & KEEP[t]
    Z ^= ZKC[CR]
    if EP >= 0:
        Z ^= ZKE[EP & 7]
    EP = -1
    if tp == 1 and abs(t - f) == 32:
        EP = (f + t) // 2
        Z ^= ZKE[EP & 7]
    HC = 0 if (tp == 1 or cap) else HC + 1
    Z ^= ZKS
    T ^= 1
    path[Z] = path.get(Z, 0) + 1
    return (m, cap, ocr, oep, ohc, oz, ov, ok, onpm, ec, rm)


def unmake(u):
    """Undo a move made by make()."""
    global CR, EP, HC, Z, V, K, NPM, T
    m, cap, cr, ep, hc, z, v, k, npm, ec, rm = u
    path[Z] -= 1
    if path[Z] == 0:
        del path[Z]
    f = m & 127; t = (m >> 7) & 127; pr = (m >> 14) & 7
    c = T ^ 1
    p = B[t]
    if rm:
        rf = rm & 127; rt = (rm >> 7) & 127
        rp = B[rt]
        upd(rt, rp, -1); B[rt] = 0
        upd(rf, rp, 1); B[rf] = rp
    upd(t, p, -1); B[t] = 0
    if pr:
        pw = 1 + c * 8
        upd(f, pw, 1); B[f] = pw
    else:
        upd(f, p, 1); B[f] = p
    if (p & 7) == 6:
        KSQ[c] = f
    if cap:
        csq = ec if ec >= 0 else t
        upd(csq, cap, 1); B[csq] = cap
    CR, EP, HC, Z, V, K, NPM = cr, ep, hc, z, v, k, npm
    T ^= 1


def evaluate():
    """Side-to-move score in centipawns."""
    ph = NPM / 4100.0
    if ph > 1:
        ph = 1
    s = V + (1 - ph) * K
    if CNT[3] == 2:
        s += 25
    if CNT[11] == 2:
        s -= 25
    for c in (0, 1):
        sg = 1 if c == 0 else -1
        k = KSQ[c]
        d = 16 if c == 0 else -16
        for df in (-1, 0, 1):
            q = k + d + df
            if 0 <= q < 128 and not (q & 0x88) and B[q] == 1 + c * 8:
                s += sg * 6
    s += 8 if T == 0 else -8
    return s if T == 0 else -s


class Abort(Exception):
    pass


def order(moves, ttmove, ply):
    """Sort moves best-first: TT move, captures (MVV-LVA), killers, history."""
    b = B; v = VAL; kl = KIL[ply]; hi = HIS; ep = EP

    def sc(m):
        if m == ttmove:
            return 1 << 20
        t = (m >> 7) & 127; f = m & 127
        cap = b[t]
        if cap:
            return 100000 + 10 * v[cap & 7] - v[b[f] & 7]
        if (b[f] & 7) == 1 and t == ep and ep >= 0:
            return 100900
        if m == kl[0]:
            return 90000
        if m == kl[1]:
            return 80000
        return hi[b[f] * 128 + t]
    moves.sort(key=sc, reverse=True)
    return moves


def qs(alpha, beta, ply):
    global nodes
    nodes += 1
    if nodes > BUDGET:
        raise Abort
    s = evaluate()
    if s >= beta:
        return beta
    if s > alpha:
        alpha = s
    chk = att(KSQ[T], T ^ 1)
    if chk:
        moves = order(gen(), 0, ply)
    else:
        moves = order(gen(True), 0, ply)
    for m in moves:
        f = m & 127; t = (m >> 7) & 127
        p = B[f]
        if not chk:
            # Delta pruning: a capture too small to reach alpha is skipped.
            cap = B[t]
            v = VAL[cap & 7] if cap else (100 if t == EP and EP >= 0 else 0)
            pr = (m >> 14) & 7
            if pr:
                v += VAL[pr] - 100
            if s + v + 200 < alpha:
                continue
        kf = KSQ[T]
        rf = f >> 4; cf = f & 7; rk = kf >> 4; ck = kf & 7
        nc = chk or (p & 7) == 6 or ((p & 7) == 1 and t == EP and EP >= 0 and not B[t]) or rf == rk or cf == ck or abs(rf - rk) == abs(cf - ck)
        u = make(m)
        if nc and att(KSQ[T ^ 1], T):
            unmake(u)
            continue
        s = -qs(-beta, -alpha, ply + 1)
        unmake(u)
        if s >= beta:
            return beta
        if s > alpha:
            alpha = s
    return alpha


def ab(depth, alpha, beta, ply):
    global nodes
    nodes += 1
    if nodes > BUDGET:
        raise Abort
    if ply > 0 and (path.get(Z, 0) > 1 or Z in hist or HC >= 100):
        return 0
    if depth <= 0:
        return qs(alpha, beta, ply)
    chk = att(KSQ[T], T ^ 1)
    if chk:
        depth += 1
    a0 = alpha
    e = TT.get(Z)
    ttmove = 0
    if e:
        d0, s0, fl, mv = e
        if s0 > 90000:
            s0 -= ply
        elif s0 < -90000:
            s0 += ply
        if d0 >= depth:
            if fl == 0:
                return s0
            if fl == 1 and s0 > alpha:
                alpha = s0
            elif fl == 2 and s0 < beta:
                beta = s0
            if alpha >= beta:
                return s0
        ttmove = mv
    moves = order(gen(), ttmove, ply)
    best = -1000000
    bestm = 0
    legal = 0
    for m in moves:
        f = m & 127; t = (m >> 7) & 127
        cap = B[t]
        iscap = cap or ((B[f] & 7) == 1 and t == EP and EP >= 0) or ((m >> 14) & 7)
        p = B[f]
        kf = KSQ[T]
        rf = f >> 4; cf = f & 7; rk = kf >> 4; ck = kf & 7
        nc = chk or (p & 7) == 6 or ((p & 7) == 1 and t == EP and EP >= 0 and not cap) or rf == rk or cf == ck or abs(rf - rk) == abs(cf - ck)
        u = make(m)
        if nc and att(KSQ[T ^ 1], T):
            unmake(u)
            continue
        legal += 1
        s = -ab(depth - 1, -beta, -alpha, ply + 1)
        unmake(u)
        if s > best:
            best = s
            bestm = m
        if s > alpha:
            alpha = s
        if alpha >= beta:
            if not iscap:
                KIL[ply][1] = KIL[ply][0]
                KIL[ply][0] = m
                hi = B[f] * 128 + t
                HIS[hi] = min(HIS[hi] + depth * depth, 100000)
            break
    if legal == 0:
        return -100000 + ply if chk else 0
    if best <= a0:
        fl = 2
    elif best >= beta:
        fl = 1
    else:
        fl = 0
    sv = best
    if sv > 90000:
        sv += ply
    elif sv < -90000:
        sv -= ply
    if len(TT) > 200000:
        TT.clear()
    TT[Z] = (depth, sv, fl, bestm)
    return best


def root(legal_uci):
    """Iterative deepening at the root; returns moves ordered best-first."""
    moves = [uci_to_move(u) for u in legal_uci]
    scores = {}
    for depth in range(1, 20):
        try:
            moves.sort(key=lambda m: -scores.get(m, 0))
            alpha = -1000000
            bests = -1000000
            for m in moves:
                u = make(m)
                s = -ab(depth - 1, -1000000, -alpha, 1)
                unmake(u)
                scores[m] = s
                if s > bests:
                    bests = s
                if s > alpha:
                    alpha = s
            moves.sort(key=lambda m: -scores.get(m, 0))
        except Abort:
            break
    moves.sort(key=lambda m: -scores.get(m, 0))
    return moves


def parse_fen(fen):
    global B, T, CR, EP, HC, Z, V, K, NPM, CNT, PF, KSQ
    parts = fen.split()
    B = [0] * 128
    Z = 0; V = 0; K = 0; NPM = 0
    CNT = [0] * 15; PF = [0] * 16; KSQ = [0, 0]
    for r, row in enumerate(parts[0].split("/")):
        rank = 7 - r
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
            else:
                code = "PNBRQKpnbrqk".index(ch)
                p = (code % 6) + 1 + (8 if code >= 6 else 0)
                sq = rank * 16 + f
                B[sq] = p
                Z ^= ZK[p][sq]
                upd(sq, p, 1)
                if (p & 7) == 6:
                    KSQ[p >> 3] = sq
                f += 1
    T = 0 if parts[1] == "w" else 1
    CR = 0
    if parts[2] != "-":
        for ch in parts[2]:
            CR |= {"K": 1, "Q": 2, "k": 4, "q": 8}[ch]
    EP = -1
    if parts[3] != "-":
        EP = (int(parts[3][1]) - 1) * 16 + (ord(parts[3][0]) - 97)
    HC = int(parts[4]) if len(parts) > 4 else 0
    if T:
        Z ^= ZKS
    Z ^= ZKC[CR]
    if EP >= 0:
        Z ^= ZKE[EP & 7]


def uci_to_move(u):
    f = (ord(u[1]) - 49) * 16 + (ord(u[0]) - 97)
    t = (ord(u[3]) - 49) * 16 + (ord(u[2]) - 97)
    pr = {"q": 5, "r": 4, "b": 3, "n": 2}.get(u[4], 0) if len(u) > 4 else 0
    return f | t << 7 | pr << 14


def move_to_uci(m):
    f = m & 127; t = (m >> 7) & 127
    s = chr(97 + (f & 7)) + str((f >> 4) + 1) + chr(97 + (t & 7)) + str((t >> 4) + 1)
    pr = (m >> 14) & 7
    if pr:
        s += "qrbn"[5 - pr]
    return s


def post(path_, body):
    req = urllib.request.Request(
        ENV + path_, data=json.dumps(body).encode(),
        headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, None


def main():
    global nodes
    cur = None
    while True:
        _, g = post("/game", {})
        if g is None or g.get("status") == "done":
            break
        if g["game"] != cur:
            cur = g["game"]
            hist.clear()
        while g["status"] == "your_move":
            parse_fen(g["fen"])
            hist[Z] = hist.get(Z, 0) + 1
            path.clear()
            path[Z] = 1
            nodes = 0
            import time as _time
            _t0 = _time.time()
            cands = root(g["legal_moves"])
            _dt = _time.time() - _t0
            print(f"game {g['game']} ply {g['plies']}: {len(cands)} cands, {nodes} nodes, {_dt:.2f}s, best {move_to_uci(cands[0])}", file=sys.stderr)
            played = None
            for m in cands:
                _, g2 = post("/move", {"game": g["game"], "move": move_to_uci(m)})
                if g2 is not None:
                    played = m
                    g = g2
                    break
            if played is None:
                sys.exit("no legal move accepted")
            u = make(played)
            hist[Z] = hist.get(Z, 0) + 1
            unmake(u)
        print(f"game {g['game']}: {g['outcome']} by {g['reason']}", file=sys.stderr)
    print(f"done: {g.get('wins')} won, {g.get('draws')} drawn, {g.get('losses')} lost", file=sys.stderr)


if __name__ == "__main__":
    main()
