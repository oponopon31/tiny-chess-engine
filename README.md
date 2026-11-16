# tiny-chess-01

A compact chess engine in at most 4,096 bytes of Python, written for
make.fun's tiny-chess-01 competition. Alpha-beta search with a transposition
table, quiescence, and a piece-square evaluation, under a fixed node budget
per move (no clock, so every trial replays identically).

Run: `MAKEFUN_ENV_URL=<env> python3 -P -s main.py`
