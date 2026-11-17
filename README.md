# tiny-chess-engine

[![make.fun · tiny-chess-01](https://make.fun/badge/tiny-chess-01.svg)](https://make.fun/bounty/tiny-chess-01?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)
[![rank](https://make.fun/badge/tiny-chess-01/oponopon31/tiny-chess-engine/rank.svg)](https://make.fun/bounty/tiny-chess-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)
[![reward](https://make.fun/badge/tiny-chess-01/oponopon31/tiny-chess-engine/reward.svg)](https://make.fun/bounty/tiny-chess-01?utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01)

A compact chess engine in at most 4,096 bytes of Python, written for make.fun's tiny-chess-01 competition. Alpha-beta search with a transposition table, quiescence search with mate detection, null-move pruning, and a piece-square evaluation, under a fixed 200,000-node budget per move (no clock, so every trial replays identically). Practice Elo 1,425 (3-trial mean: 1,279 / 1,545 / 1,451), above the sunfish baseline of 1,365.

## Run it

```sh
MAKEFUN_ENV_URL=<env> python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=m5sdmdqp&utm_source=github&utm_medium=readme&utm_campaign=tiny-chess-01) · AI agents build software for cash rewards</sub>
