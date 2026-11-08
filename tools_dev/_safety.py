"""Guard for test scripts that press real keys, move the mouse or cover the screen.

They must never run while a game or an anti-cheat program is active: the simulated
input would land in the game (this happened once, 2026-11-08, in a League of Legends match).
"""
from __future__ import annotations

import subprocess
import sys

# process names (lower case, without .exe) of games / launchers / anti-cheat we know of
GAME_PROCESSES = {
    "league of legends", "leagueclient", "valorant", "valorant-win64-shipping", "vgc", "vgtray",
    "riotclientservices", "cs2", "csgo", "dota2", "steam", "epicgameslauncher", "battle.net",
    "easyanticheat", "easyanticheat_eos", "beservice", "battleye", "faceit", "faceitclient",
    "r5apex", "fortniteclient-win64-shipping", "overwatch", "genshinimpact", "yuanshen",
    "starrail", "zenlesszonezero", "eldenring", "gta5", "rocketleague",
}


def running_games() -> list[str]:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        name = line.split('","')[0].strip('"').lower()
        if name.endswith(".exe"):
            name = name[:-4]
        names.add(name)
    return sorted(n for n in names if n in GAME_PROCESSES)


def refuse_if_gaming() -> None:
    games = running_games()
    if games:
        print("STOP: games / anti-cheat running (" + ", ".join(games) + ").")
        print("This test presses real keys; run it only when no game is open.")
        sys.exit(2)
