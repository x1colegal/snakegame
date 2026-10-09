#!/usr/bin/env python3

import asyncio
import math
import secrets
import signal
import socket
import ssl
import time

from hypercorn.asyncio import serve
from hypercorn.config import Config


HOST = "::"
PORT = 8443

CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"


# ============================================================
# WORLD
# ============================================================

WORLD_COLS = 120
WORLD_ROWS = 120

TICK_HZ = 10
TICK_INTERVAL = 1 / TICK_HZ

BOT_COUNT = 35
PELLET_TARGET = 140

START_LENGTH = 5


world_lock = asyncio.Lock()

players = {}
bots = {}
pellets = {}

tick_number = 0


SNAKE_COLORS = [
    "#69ff78",
    "#58b8ff",
    "#ff6f91",
    "#ffd75e",
    "#c277ff",
    "#ff974d",
    "#59f1e7",
    "#ff5d5d",
    "#8dff55",
    "#ff75da",
]


PELLET_COLORS = [
    "#ff5874",
    "#ffcf54",
    "#59e6ff",
    "#a8ff65",
    "#c989ff",
    "#ff8d4d",
    "#ffffff",
]


# ============================================================
# HELPERS
# ============================================================

def random_color():

    return secrets.choice(
        SNAKE_COLORS
    )


def random_pellet_color():

    return secrets.choice(
        PELLET_COLORS
    )


def all_snakes():

    result = {}

    result.update(
        players
    )

    result.update(
        bots
    )

    return result


def occupied_cells():

    occupied = set()

    for snake in all_snakes().values():

        if not snake["alive"]:
            continue

        for part in snake["body"]:

            occupied.add(
                tuple(part)
            )

    return occupied


def make_pellet(
    x,
    y,
    value=1
):

    pellets[
        (x, y)
    ] = {
        "x":
            x,

        "y":
            y,

        "value":
            value,

        "color":
            random_pellet_color()
    }


def refill_pellets():

    occupied = occupied_cells()

    attempts = 0

    alive_snakes = [
        snake
        for snake in all_snakes().values()
        if snake["alive"] and snake["body"]
    ]

    while (
        len(pellets) <
        PELLET_TARGET
    ):

        attempts += 1

        if attempts > 10000:
            break

        if alive_snakes:

            snake = secrets.choice(
                alive_snakes
            )

            center_x, center_y = (
                snake["body"][0]
            )

            x = (
                center_x +
                secrets.randbelow(81) -
                40
            )

            y = (
                center_y +
                secrets.randbelow(81) -
                40
            )

        else:

            x = secrets.randbelow(
                WORLD_COLS
            )

            y = secrets.randbelow(
                WORLD_ROWS
            )

        pos = (
            x,
            y
        )

        if (
            pos in occupied or
            pos in pellets
        ):
            continue

        make_pellet(
            x,
            y
        )


def valid_spawn_body(
    x,
    y,
    dx,
    dy
):

    body = []

    for index in range(
        START_LENGTH
    ):

        px = (
            x -
            dx * index
        )

        py = (
            y -
            dy * index
        )

        body.append(
            [
                px,
                py
            ]
        )

    return body


def find_spawn():

    occupied = occupied_cells()

    directions = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
    ]

    for _ in range(
        1000
    ):

        dx, dy = secrets.choice(
            directions
        )

        x = secrets.randbelow(
            WORLD_COLS
        )

        y = secrets.randbelow(
            WORLD_ROWS
        )

        body = valid_spawn_body(
            x,
            y,
            dx,
            dy
        )

        if body is None:
            continue

        if any(
            tuple(part)
            in occupied
            for part in body
        ):
            continue

        return (
            body,
            dx,
            dy
        )

    # fallback
    return (
        [
            [20, 30],
            [19, 30],
            [18, 30],
            [17, 30],
            [16, 30],
        ],
        1,
        0
    )


def new_snake(
    snake_id,
    name,
    is_bot
):

    body, dx, dy = find_spawn()

    return {
        "id":
            snake_id,

        "name":
            name,

        "bot":
            is_bot,

        "body":
            body,

        "dx":
            dx,

        "dy":
            dy,

        "wanted_dx":
            dx,

        "wanted_dy":
            dy,

        "score":
            0,

        "alive":
            True,

        "color":
            random_color(),

        "last_input":
            time.time(),

        "death_time":
            0
    }


def respawn_snake(
    snake
):

    body, dx, dy = find_spawn()

    snake["body"] = body

    snake["dx"] = dx
    snake["dy"] = dy

    snake["wanted_dx"] = dx
    snake["wanted_dy"] = dy

    snake["score"] = 0

    snake["alive"] = True

    snake["death_time"] = 0


def kill_snake(
    snake
):

    if not snake["alive"]:
        return

    snake["alive"] = False

    snake["death_time"] = time.time()

    # Dead snakes become food.
    #
    # Not every segment needs to become a pellet:
    # this prevents an excessive number of pellets.

    for index, part in enumerate(
        snake["body"]
    ):

        if index % 2 != 0:
            continue

        x, y = part

        make_pellet(
            x,
            y,
            value=2
        )


# ============================================================
# BOT AI
# ============================================================

def choose_bot_direction(
    bot
):

    if (
        not bot["alive"] or
        not bot["body"]
    ):
        return

    head_x, head_y = bot["body"][0]

    current_dx = bot["dx"]
    current_dy = bot["dy"]

    snakes = all_snakes()

    targets = [
        snake
        for snake in snakes.values()
        if (
            snake["alive"] and
            snake["id"] != bot["id"] and
            snake["body"]
        )
    ]

    target = None

    if targets:

        # Prioritize nearby snakes without being completely predictable.
        targets.sort(
            key=lambda snake: (
                abs(snake["body"][0][0] - head_x) +
                abs(snake["body"][0][1] - head_y)
            )
        )

        if (
            len(targets) > 1 and
            secrets.randbelow(8) == 0
        ):
            target = secrets.choice(targets[:min(4, len(targets))])
        else:
            target = targets[0]

    nearest_pellet = None
    nearest_pellet_distance = None

    for pellet in pellets.values():

        distance = (
            abs(pellet["x"] - head_x) +
            abs(pellet["y"] - head_y)
        )

        if (
            nearest_pellet_distance is None or
            distance < nearest_pellet_distance
        ):
            nearest_pellet = pellet
            nearest_pellet_distance = distance

    candidates = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
    ]

    candidates = [
        direction
        for direction in candidates
        if direction != (
            -current_dx,
            -current_dy
        )
    ]

    occupied = occupied_cells()

    safe = []

    for dx, dy in candidates:

        nx = head_x + dx
        ny = head_y + dy

        if (nx, ny) in occupied:
            continue

        safe.append((dx, dy))

    if not safe:
        return

    def score_direction(direction):

        dx, dy = direction

        nx = head_x + dx
        ny = head_y + dy

        score = 0

        if target is not None:

            tx, ty = target["body"][0]

            # Aim ahead of the target to intercept it.
            predicted_x = tx + target["dx"] * 3
            predicted_y = ty + target["dy"] * 3

            score += (
                abs(predicted_x - nx) +
                abs(predicted_y - ny)
            ) * 4

            # Encourage approaching the target body to intercept it.
            if len(target["body"]) > 2:

                body_distance = min(
                    abs(part[0] - nx) +
                    abs(part[1] - ny)
                    for part in target["body"]
                )

                score += body_distance

        elif nearest_pellet is not None:

            score += (
                abs(nearest_pellet["x"] - nx) +
                abs(nearest_pellet["y"] - ny)
            ) * 2

        return score

    safe.sort(key=score_direction)

    if (
        len(safe) > 1 and
        secrets.randbelow(12) == 0
    ):
        direction = secrets.choice(safe[:min(3, len(safe))])
    else:
        direction = safe[0]

    bot["wanted_dx"] = direction[0]
    bot["wanted_dy"] = direction[1]


# ============================================================
# SERVER TICK
# ============================================================

def server_tick():

    global tick_number

    tick_number += 1

    snakes = all_snakes()

    # Bots make their decisions on the server.
    for bot in bots.values():
        choose_bot_direction(bot)

    # Apply directions.
    for snake in snakes.values():

        if not snake["alive"]:
            continue

        wanted_dx = snake["wanted_dx"]
        wanted_dy = snake["wanted_dy"]

        if (
            wanted_dx == -snake["dx"] and
            wanted_dy == -snake["dy"]
        ):
            continue

        snake["dx"] = wanted_dx
        snake["dy"] = wanted_dy

    proposed = {}
    eating = {}

    for snake_id, snake in snakes.items():

        if not snake["alive"]:
            continue

        head_x, head_y = snake["body"][0]

        new_head = (
            head_x + snake["dx"],
            head_y + snake["dy"]
        )

        proposed[snake_id] = new_head
        eating[snake_id] = new_head in pellets

    # All currently visible cells count as occupied.
    # Do not remove the tail: if it exists during this tick,
    # it still counts for collision detection.
    #
    # Each cell can temporarily have multiple owners.
    cell_owners = {}

    for snake_id, snake in snakes.items():

        if not snake["alive"]:
            continue

        for part in snake["body"]:

            cell_owners.setdefault(
                tuple(part),
                set()
            ).add(
                snake_id
            )

    # Proposed new heads also count as occupied cells.
    # This handles two snakes entering the same empty cell
    # without requiring a special head-to-head rule.
    for snake_id, head in proposed.items():

        cell_owners.setdefault(
            head,
            set()
        ).add(
            snake_id
        )

    dead = set()
    killer_by_victim = {}

    # All snake collisions follow the same rule:
    #
    # smaller -> larger: smaller dies
    # larger -> smaller: smaller dies
    # equal size: both die
    #
    # Collision with the same snake is ignored.
    for snake_id, head in proposed.items():

        snake = snakes[snake_id]

        owners = cell_owners.get(
            head,
            set()
        )

        other_owners = [
            owner_id
            for owner_id in owners
            if owner_id != snake_id
        ]

        # Only the snake itself occupies the cell:
        # nothing happens.
        if not other_owners:
            continue

        attacker_length = len(
            snake["body"]
        )

        for owner_id in other_owners:

            owner = snakes.get(
                owner_id
            )

            if (
                owner is None or
                not owner["alive"]
            ):
                continue

            owner_length = len(
                owner["body"]
            )

            owner_current_head = tuple(
                owner["body"][0]
            )

            owner_proposed_head = proposed.get(
                owner_id
            )

            hit_owner_head = (
                head == owner_current_head or
                head == owner_proposed_head
            )

            # ------------------------------------------------
            # HEAD COLLISION
            # ------------------------------------------------
            if hit_owner_head:

                attacker_is_player = (
                    not snake["bot"]
                )

                owner_is_player = (
                    not owner["bot"]
                )

                # Players always beat bots in head collisions.
                if attacker_is_player and not owner_is_player:

                    dead.add(
                        owner_id
                    )

                    killer_by_victim[
                        owner_id
                    ] = snake_id

                    continue

                # Bots never kill players in head collisions.
                if not attacker_is_player and owner_is_player:

                    dead.add(
                        snake_id
                    )

                    killer_by_victim[
                        snake_id
                    ] = owner_id

                    continue

                # Between snakes of the same type,
                # the attacker kills the target,
                # regardless of size or score.
                dead.add(
                    owner_id
                )

                killer_by_victim[
                    owner_id
                ] = snake_id

                continue

            # ------------------------------------------------
            # BODY COLLISION
            # ------------------------------------------------

            # The moving snake is smaller.
            if attacker_length < owner_length:

                dead.add(
                    snake_id
                )

                killer_by_victim[
                    snake_id
                ] = owner_id

            # Equal size.
            elif attacker_length == owner_length:

                dead.add(
                    snake_id
                )

                dead.add(
                    owner_id
                )

                killer_by_victim[
                    snake_id
                ] = owner_id

                killer_by_victim[
                    owner_id
                ] = snake_id

            # The moving snake is larger.
            else:

                dead.add(
                    owner_id
                )

                killer_by_victim[
                    owner_id
                ] = snake_id

    # Freeze victim scores before distributing rewards.
    victim_scores = {
        snake_id: snakes[snake_id]["score"]
        for snake_id in dead
        if snake_id in snakes
    }

    # Reward killers even when deaths are resolved in the same tick.
    for victim_id, killer_id in killer_by_victim.items():

        if victim_id not in dead:
            continue

        killer = snakes.get(killer_id)
        victim = snakes.get(victim_id)

        if (
            killer is None or
            victim is None or
            killer_id == victim_id
        ):
            continue

        reward = victim_scores.get(victim_id, 0)

        killer["score"] += reward

        print(
            "[KILL]",
            "killer=" + killer["name"],
            "victim=" + victim["name"],
            "reward=" + str(reward),
            "killer_score=" + str(killer["score"]),
            flush=True
        )

    # Kill before moving.
    for snake_id in dead:

        snake = snakes.get(snake_id)

        if snake:
            kill_snake(snake)

    # Move survivors.
    for snake_id, snake in snakes.items():

        if not snake["alive"]:
            continue

        new_head = proposed[snake_id]

        snake["body"].insert(
            0,
            [new_head[0], new_head[1]]
        )

        pellet = pellets.pop(
            new_head,
            None
        )

        if pellet is not None:

            snake["score"] += pellet["value"]

        else:

            snake["body"].pop()

    # Bots respawn automatically.
    now = time.time()

    for bot in bots.values():

        if (
            not bot["alive"] and
            now - bot["death_time"] >= 2.0
        ):
            respawn_snake(bot)

    refill_pellets()


# ============================================================
# SNAPSHOT
# ============================================================

def get_king_id():

    alive = [
        snake
        for snake in all_snakes().values()
        if snake["alive"]
    ]

    if not alive:
        return None

    king = max(
        alive,
        key=lambda snake: (
            snake["score"],
            len(
                snake["body"]
            )
        )
    )

    return king["id"]


def leaderboard():

    alive = [
        snake
        for snake in all_snakes().values()
        if snake["alive"]
    ]

    alive.sort(
        key=lambda snake: (
            snake["score"],
            len(
                snake["body"]
            )
        ),
        reverse=True
    )

    return [
        {
            "id":
                snake["id"],

            "name":
                snake["name"],

            "score":
                snake["score"],

            "length":
                len(
                    snake["body"]
                )
        }

        for snake in alive[:5]
    ]


def make_state(
    session_id
):

    snakes = all_snakes()

    king_id = get_king_id()

    result_snakes = []


    for snake in snakes.values():

        result_snakes.append(
            {
                "id":
                    snake["id"],

                "name":
                    snake["name"],

                "bot":
                    snake["bot"],

                "body":
                    snake["body"],

                "dx":
                    snake["dx"],

                "dy":
                    snake["dy"],

                "score":
                    snake["score"],

                "alive":
                    snake["alive"],

                "color":
                    snake["color"],

                "king":
                    (
                        snake["id"] ==
                        king_id
                    )
            }
        )


    return {
        "tick":
            tick_number,

        "world": {
            "cols":
                WORLD_COLS,

            "rows":
                WORLD_ROWS
        },

        "you":
            session_id,

        "king":
            king_id,

        "snakes":
            result_snakes,

        "pellets":
            list(
                pellets.values()
            ),

        "leaderboard":
            leaderboard()
    }




# ============================================================
# SNAKEPROTOCOL
# ============================================================

SNAKE_PROTOCOL_CONTENT_TYPE = (
    "application/x-snakeprotocol; charset=windows-1252"
)


def snake_escape(value):

    value = str(value)

    return (
        value
        .replace("%", "%25")
        .replace("|", "%7C")
        .replace(";", "%3B")
        .replace(",", "%2C")
        .replace("=", "%3D")
        .replace("\\r", "%0D")
        .replace("\\n", "%0A")
    )


def snake_unescape(value):

    return (
        value
        .replace("%0A", "\\n")
        .replace("%0D", "\\r")
        .replace("%3D", "=")
        .replace("%2C", ",")
        .replace("%3B", ";")
        .replace("%7C", "|")
        .replace("%25", "%")
    )


def parse_snake_protocol(raw):

    text = raw.decode(
        "windows-1252"
    )

    result = {}

    for line in text.splitlines():

        if "=" not in line:
            continue

        key, value = line.split(
            "=",
            1
        )

        result[key] = snake_unescape(
            value
        )

    return result


def make_state_protocol(session_id):

    king_id = get_king_id()

    lines = [
        "SnakeProtocol=1",
        "type=state",
        "tick=" + str(tick_number),
        "you=" + snake_escape(session_id),
        "king=" + snake_escape(king_id or ""),
        "world=" + str(WORLD_COLS) + "," + str(WORLD_ROWS),
    ]

    for snake in all_snakes().values():

        body = ";".join(
            str(part[0]) + "," + str(part[1])
            for part in snake["body"]
        )

        lines.append(
            "snake=" + "|".join(
                [
                    snake_escape(snake["id"]),
                    snake_escape(snake["name"]),
                    "1" if snake["bot"] else "0",
                    str(snake["dx"]),
                    str(snake["dy"]),
                    str(snake["score"]),
                    "1" if snake["alive"] else "0",
                    "1" if snake["id"] == king_id else "0",
                    snake_escape(snake["color"]),
                    body,
                ]
            )
        )

    for pellet in pellets.values():

        lines.append(
            "pellet=" + "|".join(
                [
                    str(pellet["x"]) + "," + str(pellet["y"]),
                    str(pellet["value"]),
                    snake_escape(pellet["color"]),
                ]
            )
        )

    for entry in leaderboard():

        lines.append(
            "leader=" + "|".join(
                [
                    snake_escape(entry["id"]),
                    snake_escape(entry["name"]),
                    str(entry["score"]),
                    str(entry["length"]),
                ]
            )
        )

    return "\r\n".join(lines) + "\r\n"


# ============================================================
# HTML
# ============================================================

HTML = r'''<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="windows-1252">

<meta name="viewport"
      content="width=device-width,
               initial-scale=1,
               maximum-scale=1,
               user-scalable=no,
               viewport-fit=cover">

<title>Snake Arena</title>

<style>

* {
  box-sizing: border-box;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
}

html,
body {
  margin: 0;
  padding: 0;

  width: 100%;
  height: 100%;

  overflow: hidden;

  background: #292929;
}

body {
  position: fixed;
  inset: 0;

  font-family:
    Arial,
    sans-serif;
}

canvas {
  position: fixed;
  inset: 0;

  width: 100vw;
  height: 100dvh;

  display: block;
}


#hud {
  position: fixed;

  top:
    max(
      10px,
      env(safe-area-inset-top)
    );

  left:
    max(
      10px,
      env(safe-area-inset-left)
    );

  z-index: 10;

  display: flex;
  flex-direction: column;

  align-items: flex-start;

  gap: 5px;

  pointer-events: none;
}


.pill {
  display: inline-block;

  padding:
    5px 10px;

  border-radius:
    999px;

  color:
    white;

  background:
    rgba(
      0,
      0,
      0,
      0.38
    );

  border:
    1px solid
    rgba(
      255,
      255,
      255,
      0.16
    );

  box-shadow:
    0 3px 12px
    rgba(
      0,
      0,
      0,
      0.15
    );

  backdrop-filter:
    blur(8px);

  -webkit-backdrop-filter:
    blur(8px);

  font-weight:
    700;

  font-size:
    12px;
}


#score {
  font-size:
    18px;

  padding:
    7px 13px;
}


#connection {
  color:
    #adffb1;
}


#nick-screen {
  position: fixed;
  inset: 0;
  z-index: 1000;

  display: flex;
  align-items: center;
  justify-content: center;

  background:
    rgba(35, 35, 35, 0.92);

  backdrop-filter:
    blur(6px);
}


#nick-box {
  width: min(
    86vw,
    320px
  );

  padding: 24px;

  border-radius: 0;

  background:
    rgba(255,255,255,0.16);

  border:
    1px solid
    rgba(255,255,255,0.35);

  box-shadow:
    0 10px 40px
    rgba(0,0,0,0.25);

  text-align: center;
}


#nick-title {
  margin-bottom: 16px;

  font-size: 28px;
  font-weight: 900;

  color: white;
}


#nick-input {
  width: 100%;

  box-sizing: border-box;

  padding: 14px 16px;

  border: 0;
  border-radius: 0;

  outline: none;

  font-size: 18px;

  background:
    rgba(255,255,255,0.95);
}


#nick-play {
  width: 100%;

  margin-top: 12px;

  padding: 14px;

  border: 0;
  border-radius: 0;

  font-size: 18px;
  font-weight: 800;

  background: white;
}


#nick-hint {
  margin-top: 10px;

  color:
    rgba(255,255,255,0.85);

  font-size: 13px;
}


#leaderboard {
  position: fixed;

  top:
    max(
      10px,
      env(safe-area-inset-top)
    );

  right:
    max(
      10px,
      env(safe-area-inset-right)
    );

  z-index:
    10;

  min-width:
    120px;

  color:
    white;

  background:
    rgba(
      0,
      0,
      0,
      0.26
    );

  border-radius:
    14px;

  padding:
    8px 10px;

  font-size:
    11px;

  line-height:
    1.5;

  pointer-events:
    none;

  backdrop-filter:
    blur(7px);

  -webkit-backdrop-filter:
    blur(7px);
}


#controls {
  display: none !important;
  position: fixed;

  right:
    max(
      18px,
      env(safe-area-inset-right)
    );

  bottom:
    max(
      18px,
      env(safe-area-inset-bottom)
    );

  z-index:
    30;

  display:
    grid;

  grid-template-columns:
    58px 58px 58px;

  grid-template-rows:
    58px 58px 58px;

  gap:
    5px;

  pointer-events:
    auto;
}


.control-button {
  width:
    58px;

  height:
    58px;

  border:
    1px solid
    rgba(
      255,
      255,
      255,
      0.28
    );

  border-radius:
    50%;

  background:
    rgba(
      0,
      0,
      0,
      0.34
    );

  color:
    white;

  font-size:
    25px;

  font-weight:
    bold;

  backdrop-filter:
    blur(8px);

  -webkit-backdrop-filter:
    blur(8px);

  touch-action:
    manipulation;
}


#control-up {
  grid-column: 2;
  grid-row: 1;
}


#control-left {
  grid-column: 1;
  grid-row: 2;
}


#control-right {
  grid-column: 3;
  grid-row: 2;
}


#control-down {
  grid-column: 2;
  grid-row: 3;
}


#gameover {
  display:
    none;

  position:
    fixed;

  left:
    50%;

  top:
    50%;

  transform:
    translate(
      -50%,
      -50%
    );

  z-index:
    20;

  color:
    white;

  background:
    rgba(
      0,
      0,
      0,
      0.55
    );

  border:
    1px solid
    rgba(
      255,
      255,
      255,
      0.18
    );

  border-radius:
    22px;

  padding:
    18px 24px;

  text-align:
    center;

  font-weight:
    bold;

  pointer-events:
    none;

  backdrop-filter:
    blur(12px);

  -webkit-backdrop-filter:
    blur(12px);
}

</style>

</head>

<body>


<div id="hud">

  <div
    id="score"
    class="pill">
    Score: 0
  </div>

  <div
    id="length"
    class="pill">
    Length: 0
  </div>

  <div
    id="king"
    class="pill">
    King: -
  </div>

  <div
    id="players"
    class="pill">
    Snakes: 0
  </div>

  <div
    id="connection"
    class="pill">
    Connecting...
  </div>

</div>


<div id="leaderboard">
  Loading...
</div>


<div id="gameover">
  You died<br>
  <small>Tap to respawn</small>
</div>


<div id="controls">

  <button
    id="control-up"
    class="control-button"
    type="button">
    &#x2191;
  </button>

  <button
    id="control-left"
    class="control-button"
    type="button">
    &#x2190;
  </button>

  <button
    id="control-right"
    class="control-button"
    type="button">
    &#x2192;
  </button>

  <button
    id="control-down"
    class="control-button"
    type="button">
    &#x2193;
  </button>

</div>


<div id="nick-screen">
  <div id="nick-box">
    <div id="nick-title">Snake Arena</div>

    <input
      id="nick-input"
      type="text"
      maxlength="20"
      placeholder="Enter your nickname"
      autocomplete="off"
    >

    <button id="nick-play">
      Jogar
    </button>

    <div id="nick-hint">
      Empty = random nickname
    </div>
  </div>
</div>

<canvas id="game"></canvas>


<script>

const canvas =
  document.getElementById(
    "game"
  );

const ctx =
  canvas.getContext(
    "2d"
  );


const scoreElement =
  document.getElementById(
    "score"
  );

const lengthElement =
  document.getElementById(
    "length"
  );

const kingElement =
  document.getElementById(
    "king"
  );

const playersElement =
  document.getElementById(
    "players"
  );

const connectionElement =
  document.getElementById(
    "connection"
  );

const leaderboardElement =
  document.getElementById(
    "leaderboard"
  );


const nickScreen =
  document.getElementById(
    "nick-screen"
  );


const nickInput =
  document.getElementById(
    "nick-input"
  );


const nickPlay =
  document.getElementById(
    "nick-play"
  );


let playerName = "";


const htmlGlyph = value => {

  const element =
    document.createElement(
      "span"
    );

  element.innerHTML =
    value;

  return element.textContent;
};


const crownGlyph =
  htmlGlyph(
    "&#x1F451;"
  );


const trophyGlyph =
  htmlGlyph(
    "&#x1F3C6;"
  );

const gameOverElement =
  document.getElementById(
    "gameover"
  );


let state = null;

let polling = false;
let measuredRTT = null;

let touchStartX = 0;
let touchStartY = 0;


let sessionId =
  localStorage.getItem(
    "snake_session_id"
  );


if (!sessionId) {

  sessionId =
    crypto.randomUUID();

  localStorage.setItem(
    "snake_session_id",
    sessionId
  );
}


// ============================================================
// CANVAS
// ============================================================

function resizeCanvas() {

  const dpr =
    window.devicePixelRatio || 1;

  const width =
    window.innerWidth;

  const height =
    window.innerHeight;


  canvas.width =
    Math.floor(
      width *
      dpr
    );

  canvas.height =
    Math.floor(
      height *
      dpr
    );


  ctx.setTransform(
    dpr,
    0,
    0,
    dpr,
    0,
    0
  );
}


// ============================================================
// HTTP
// ============================================================

async function joinGame() {

  const response =
    await fetch(
      "/join",
      {
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/x-snakeprotocol; charset=windows-1252"
        },

        body:
          "SnakeProtocol=1\r\n" +
          "type=join\r\n" +
          "session_id=" +
          sessionId +
          "\r\n" +
          "name=" +
          playerName +
          "\r\n"
      }
    );


  if (!response.ok) {
    throw new Error(
      "join HTTP " +
      response.status
    );
  }
}


async function sendInput(
  direction
) {

  try {

    const response =
      await fetch(
        "/input",
        {
          method:
            "POST",

          headers: {
            "Content-Type":
              "application/x-snakeprotocol; charset=windows-1252"
          },

          body:
            "SnakeProtocol=1\r\n" +
            "type=input\r\n" +
            "session_id=" +
            sessionId +
            "\r\n" +
            "direction=" +
            direction +
            "\r\n"
        }
      );


    if (!response.ok) {
      throw new Error(
        "input HTTP " +
        response.status
      );
    }
  }

  catch (error) {

    connectionElement.textContent =
      "Offline";
  }
}


async function respawn() {

  try {

    const response =
      await fetch(
        "/respawn",
        {
          method:
            "POST",

          headers: {
            "Content-Type":
              "application/x-snakeprotocol; charset=windows-1252"
          },

          body:
            "SnakeProtocol=1\r\n" +
            "type=respawn\r\n" +
            "session_id=" +
            sessionId +
            "\r\n"
        }
      );


    if (!response.ok) {
      throw new Error(
        "respawn HTTP " +
        response.status
      );
    }
  }

  catch (error) {

    connectionElement.textContent =
      "Offline";
  }
}


async function getState() {

  if (polling) {
    return;
  }

  polling =
    true;


  try {

    const rttStart = performance.now();
    const response =
      await fetch(
        "/state?session_id=" +
        encodeURIComponent(
          sessionId
        ),
        {
          cache:
            "no-store"
        }
      );


    if (!response.ok) {

      throw new Error(
        "HTTP " +
        response.status
      );
    }


    measuredRTT = Math.round(performance.now() - rttStart);
    const rawState =
      await response.arrayBuffer();

    const stateText =
      new TextDecoder(
        "windows-1252"
      ).decode(
        rawState
      );

    state =
      parseSnakeProtocolState(
        stateText
      );


    connectionElement.textContent =
      "Online S:" +
      state.snakes.length +
      " P:" +
      state.pellets.length +
      " RTT: " +
      (measuredRTT !== null ? measuredRTT + " ms" : "N/D");


    updateHUD();

    draw();

  }

  catch (error) {

    connectionElement.textContent =
      "Offline";
  }

  finally {

    polling =
      false;
  }
}


function snakeProtocolUnescape(value) {

  return value
    .replaceAll("%0A", "\\n")
    .replaceAll("%0D", "\\r")
    .replaceAll("%3D", "=")
    .replaceAll("%2C", ",")
    .replaceAll("%3B", ";")
    .replaceAll("%7C", "|")
    .replaceAll("%25", "%");
}


function parseSnakeProtocolState(text) {

  const result = {
    tick: 0,
    you: "",
    king: null,
    world: {
      cols: 0,
      rows: 0
    },
    snakes: [],
    pellets: [],
    leaderboard: []
  };


  const lines =
    text.split(/\r?\n/);


  for (const line of lines) {

    if (!line) {
      continue;
    }


    const equals =
      line.indexOf("=");


    if (equals < 0) {
      continue;
    }


    const key =
      line.slice(
        0,
        equals
      );


    const value =
      line.slice(
        equals + 1
      );


    if (key === "tick") {

      result.tick =
        Number(value);
    }


    else if (key === "you") {

      result.you =
        snakeProtocolUnescape(
          value
        );
    }


    else if (key === "king") {

      result.king =
        snakeProtocolUnescape(
          value
        ) || null;
    }


    else if (key === "world") {

      const parts =
        value.split(",");


      result.world.cols =
        Number(parts[0]);

      result.world.rows =
        Number(parts[1]);
    }


    else if (key === "snake") {

      const parts =
        value.split("|");


      if (parts.length < 10) {
        continue;
      }


      const bodyText =
        parts.slice(9).join("|");


      const body = [];


      if (bodyText) {

        for (
          const point
          of bodyText.split(";")
        ) {

          const xy =
            point.split(",");


          if (xy.length !== 2) {
            continue;
          }


          body.push(
            [
              Number(xy[0]),
              Number(xy[1])
            ]
          );
        }
      }


      result.snakes.push(
        {
          id:
            snakeProtocolUnescape(
              parts[0]
            ),

          name:
            snakeProtocolUnescape(
              parts[1]
            ),

          bot:
            parts[2] === "1",

          dx:
            Number(parts[3]),

          dy:
            Number(parts[4]),

          score:
            Number(parts[5]),

          alive:
            parts[6] === "1",

          king:
            parts[7] === "1",

          color:
            snakeProtocolUnescape(
              parts[8]
            ),

          body:
            body
        }
      );
    }


    else if (key === "pellet") {

      const parts =
        value.split("|");


      if (parts.length < 3) {
        continue;
      }


      const xy =
        parts[0].split(",");


      if (xy.length !== 2) {
        continue;
      }


      result.pellets.push(
        {
          x:
            Number(xy[0]),

          y:
            Number(xy[1]),

          value:
            Number(parts[1]),

          color:
            snakeProtocolUnescape(
              parts[2]
            )
        }
      );
    }


    else if (key === "leader") {

      const parts =
        value.split("|");


      if (parts.length < 4) {
        continue;
      }


      result.leaderboard.push(
        {
          id:
            snakeProtocolUnescape(
              parts[0]
            ),

          name:
            snakeProtocolUnescape(
              parts[1]
            ),

          score:
            Number(parts[2]),

          length:
            Number(parts[3])
        }
      );
    }
  }


  return result;
}


// ============================================================
// HUD
// ============================================================

function getMySnake() {

  if (!state) {
    return null;
  }

  return (
    state.snakes.find(
      snake =>
        snake.id ===
        state.you
    ) ||
    null
  );
}


function updateHUD() {

  const me =
    getMySnake();


  if (!me) {
    return;
  }


  scoreElement.textContent =
    "Score: " +
    me.score;


  lengthElement.textContent =
    "Length: " +
    me.body.length;


  const king =
    state.snakes.find(
      snake =>
        snake.id ===
        state.king
    );


  kingElement.innerHTML =
    "&#x1F451; King: " +
    (
      king
        ? king.name
        : "-"
    );


  playersElement.textContent =
    "Snakes: " +
    state.snakes.filter(
      snake =>
        snake.alive
    ).length;


  leaderboardElement.innerHTML =
    "<b>&#127942; Leaderboard</b><br>" +

    state.leaderboard
      .map(
        (entry, index) =>
          (index + 1) +
          ". " +
          entry.name +
          " — " +
          entry.score
      )
      .join(
        "<br>"
      );


  gameOverElement.style.display =
    me.alive
      ? "none"
      : "block";
}


// ============================================================
// DRAW
// ============================================================

function drawHexGrid(
  width,
  height
) {

  const size =
    23;

  const hexHeight =
    Math.sqrt(3) *
    size;

  const horizontal =
    size * 1.5;


  ctx.strokeStyle =
    "rgba(255,255,255,0.19)";

  ctx.lineWidth =
    1;


  for (
    let column = -1;
    column <
      width / horizontal + 2;
    column++
  ) {

    for (
      let row = -1;
      row <
        height / hexHeight + 2;
      row++
    ) {

      const cx =
        column *
        horizontal;


      const cy =
        row *
        hexHeight +
        (
          column % 2
            ? hexHeight / 2
            : 0
        );


      ctx.beginPath();


      for (
        let side = 0;
        side < 6;
        side++
      ) {

        const angle =
          Math.PI / 3 *
          side;


        const x =
          cx +
          size *
          Math.cos(
            angle
          );


        const y =
          cy +
          size *
          Math.sin(
            angle
          );


        if (side === 0) {

          ctx.moveTo(
            x,
            y
          );

        }

        else {

          ctx.lineTo(
            x,
            y
          );
        }
      }


      ctx.closePath();
      ctx.stroke();
    }
  }
}


function drawSnakeEyes(
  snake,
  headX,
  headY,
  radius
) {

  let forwardX =
    snake.dx;

  let forwardY =
    snake.dy;


  let sideX =
    -forwardY;

  let sideY =
    forwardX;


  const eyeForward =
    radius * 0.38;

  const eyeSide =
    radius * 0.38;


  const eyeRadius =
    Math.max(
      2.2,
      radius * 0.24
    );


  for (
    const sign of [-1, 1]
  ) {

    const eyeX =
      headX +
      forwardX *
      eyeForward +
      sideX *
      eyeSide *
      sign;


    const eyeY =
      headY +
      forwardY *
      eyeForward +
      sideY *
      eyeSide *
      sign;


    ctx.fillStyle =
      "white";

    ctx.beginPath();

    ctx.arc(
      eyeX,
      eyeY,
      eyeRadius,
      0,
      Math.PI * 2
    );

    ctx.fill();


    ctx.fillStyle =
      "#111";


    ctx.beginPath();

    ctx.arc(
      eyeX +
        forwardX *
        eyeRadius *
        0.28,

      eyeY +
        forwardY *
        eyeRadius *
        0.28,

      eyeRadius *
        0.46,

      0,
      Math.PI * 2
    );

    ctx.fill();
  }
}


function draw() {

  const width =
    window.innerWidth;

  const height =
    window.innerHeight;


  const gradient =
    ctx.createLinearGradient(
      0,
      0,
      0,
      height
    );


  gradient.addColorStop(
    0,
    "#333333"
  );

  gradient.addColorStop(
    1,
    "#333333"
  );


  ctx.fillStyle =
    gradient;


  ctx.fillRect(
    0,
    0,
    width,
    height
  );




  if (!state) {
    return;
  }


  const me =
    getMySnake();


  const CELL =
    28;


  let cameraX =
    state.world.cols /
    2;


  let cameraY =
    state.world.rows /
    2;


  if (
    me &&
    me.body.length > 0
  ) {

    cameraX =
      me.body[0][0] +
      0.5;


    cameraY =
      me.body[0][1] +
      0.5;
  }


  const offsetX =
    width /
    2 -
    cameraX *
    CELL;


  const offsetY =
    height /
    2 -
    cameraY *
    CELL;


  // pellets

  for (
    const pellet
    of state.pellets
  ) {

    const x =
      offsetX +
      pellet.x *
      CELL +
      CELL / 2;


    const y =
      offsetY +
      pellet.y *
      CELL +
      CELL / 2;


    if (
      x < -30 ||
      x > width + 30 ||
      y < -30 ||
      y > height + 30
    ) {
      continue;
    }


    const radius =
      pellet.value > 1
        ? 6.5
        : 4.5;


    ctx.save();


    ctx.shadowColor =
      pellet.color;


    ctx.shadowBlur =
      12;


    ctx.fillStyle =
      pellet.color;


    ctx.beginPath();


    ctx.arc(
      x,
      y,
      radius,
      0,
      Math.PI * 2
    );


    ctx.font = "20px Arial"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String.fromCodePoint(0x1F34E), x, y);


    ctx.restore();
  }


  // cobras

  for (
    const snake
    of state.snakes
  ) {

    if (!snake.alive) {
      continue;
    }


    const radius =
      13.2;


    for (
      let index =
        snake.body.length - 1;

      index >= 0;

      index--
    ) {

      const part =
        snake.body[index];


      const x =
        offsetX +
        part[0] *
        CELL +
        CELL / 2;


      const y =
        offsetY +
        part[1] *
        CELL +
        CELL / 2;


      if (
        x < -40 ||
        x > width + 40 ||
        y < -40 ||
        y > height + 40
      ) {
        continue;
      }


      ctx.save();


      ctx.fillStyle =
        snake.color;


      ctx.shadowColor =
        snake.color;


      ctx.shadowBlur =
        index === 0
          ? 12
          : 5;


      ctx.beginPath();


      ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);


      ctx.fill();


      if (
        index === 0
      ) {



        if (
          snake.king
        ) {

          ctx.font =
            "23px Arial";


          ctx.textAlign =
            "center";


          ctx.fillText(
            "\uD83D\uDC51",
            x,
            y -
              radius -
              7
          );
        }
      }


      ctx.restore();
    }
  }


  // indicador central do jogador

  if (
    me &&
    me.alive
  ) {

    ctx.save();


    ctx.strokeStyle =
      "rgba(255,255,255,0.42)";


    ctx.lineWidth =
      2;


    ctx.beginPath();


    ctx.arc(
      width / 2,
      height / 2,
      20,
      0,
      Math.PI * 2
    );


    ctx.stroke();


    ctx.restore();
  }
}


// ============================================================
// CONTROLES
// ============================================================

function bindDirectionButton(
  id,
  direction
) {

  const button =
    document.getElementById(
      id
    );


  button.addEventListener(
    "pointerdown",

    event => {

      event.preventDefault();

      sendInput(
        direction
      );
    }
  );
}


bindDirectionButton(
  "control-up",
  "up"
);


bindDirectionButton(
  "control-down",
  "down"
);


bindDirectionButton(
  "control-left",
  "left"
);


bindDirectionButton(
  "control-right",
  "right"
);


// ============================================================
// TOUCH
// ============================================================

canvas.addEventListener(
  "touchstart",

  event => {

    event.preventDefault();


    const me =
      getMySnake();


    if (
      me &&
      !me.alive
    ) {

      respawn();

      return;
    }


    const touch =
      event.touches[0];


    touchStartX =
      touch.clientX;

    touchStartY =
      touch.clientY;
  },

  {
    passive:
      false
  }
);


canvas.addEventListener(
  "touchend",

  event => {

    event.preventDefault();


    const touch =
      event.changedTouches[0];


    const differenceX =
      touch.clientX -
      touchStartX;


    const differenceY =
      touch.clientY -
      touchStartY;


    const absX =
      Math.abs(
        differenceX
      );


    const absY =
      Math.abs(
        differenceY
      );


    if (
      absX < 12 &&
      absY < 12
    ) {
      return;
    }


    if (
      absX >
      absY
    ) {

      sendInput(
        differenceX > 0
          ? "right"
          : "left"
      );

    }

    else {

      sendInput(
        differenceY > 0
          ? "down"
          : "up"
      );
    }
  },

  {
    passive:
      false
  }
);


document.addEventListener(
  "touchmove",

  event => {

    event.preventDefault();
  },

  {
    passive:
      false
  }
);


// keyboard

window.addEventListener(
  "keydown",

  event => {

    const keys = {
      ArrowUp:
        "up",

      ArrowDown:
        "down",

      ArrowLeft:
        "left",

      ArrowRight:
        "right"
    };


    const direction =
      keys[
        event.key
      ];


    if (direction) {

      event.preventDefault();

      sendInput(
        direction
      );
    }
  }
);


// ============================================================
// START
// ============================================================

window.addEventListener(
  "resize",

  () => {

    resizeCanvas();

    draw();
  }
);


async function start() {

  resizeCanvas();

  await joinGame();

  await getState();


  setInterval(
    getState,
    80
  );
}





let gameStarted = false;


async function startGame() {

  if (gameStarted) {
    return;
  }


  let chosen =
    nickInput.value.trim();


  if (!chosen) {

    const randomId =
      crypto.randomUUID();

    chosen =
      randomId.slice(
        0,
        4
      );
  }


  playerName =
    chosen.slice(
      0,
      20
    );


  gameStarted = true;

  nickPlay.disabled =
    true;


  try {

    await joinGame();

    nickScreen.style.display =
      "none";

    resizeCanvas();

    await getState();

    setInterval(
      getState,
      80
    );
  }

  catch (error) {

    gameStarted = false;

    nickPlay.disabled =
      false;

    connectionElement.textContent =
      "Offline";

    console.error(
      error
    );
  }
}


nickPlay.addEventListener(
  "click",
  event => {

    event.preventDefault();

    startGame();
  }
);


nickInput.addEventListener(
  "keydown",
  event => {

    if (
      event.key ===
      "Enter"
    ) {

      event.preventDefault();

      startGame();
    }
  }
);


</script>

</body>
</html>
'''


HTML_BYTES = (
    HTML.encode(
        "windows-1252",
        errors="replace"
    )
)


# ============================================================
# ASGI HELPERS
# ============================================================

async def read_body(
    receive
):

    chunks = []

    while True:

        message = await receive()

        if (
            message["type"] !=
            "http.request"
        ):
            continue

        chunks.append(
            message.get(
                "body",
                b""
            )
        )

        if not message.get(
            "more_body",
            False
        ):
            break

    return b"".join(
        chunks
    )


async def send_response(
    send,
    status,
    body,
    content_type
):

    headers = [
        (
            b"content-type",
            content_type.encode(
                "ascii"
            )
        ),

        (
            b"content-length",
            str(
                len(body)
            ).encode(
                "ascii"
            )
        ),

        (
            b"cache-control",
            b"no-store"
        )
    ]


    await send(
        {
            "type":
                "http.response.start",

            "status":
                status,

            "headers":
                headers
        }
    )


    await send(
        {
            "type":
                "http.response.body",

            "body":
                body
        }
    )


async def send_snake_protocol(
    send,
    text,
    status=200
):

    raw = text.encode(
        "windows-1252",
        errors="strict"
    )

    await send_response(
        send,
        status,
        raw,
        SNAKE_PROTOCOL_CONTENT_TYPE
    )


def query_param(
    scope,
    name
):

    from urllib.parse import (
        parse_qs
    )


    raw = scope.get(
        "query_string",
        b""
    ).decode(
        "ascii",
        errors="ignore"
    )


    parsed = parse_qs(
        raw
    )


    values = parsed.get(
        name
    )


    if not values:
        return ""


    return values[0]


# ============================================================
# API
# ============================================================

async def app(
    scope,
    receive,
    send
):

    if (
        scope["type"] !=
        "http"
    ):
        return


    method = scope[
        "method"
    ]

    path = scope[
        "path"
    ]


    client = scope.get(
        "client"
    )


    ip = (
        client[0]
        if client
        else "?"
    )


    http_version = scope.get(
        "http_version",
        "?"
    )


    # --------------------------------------------------------
    # /
    # --------------------------------------------------------

    if (
        method == "GET" and
        path == "/"
    ):

        print(
            "[HTTP]",
            ip,
            "GET /",
            "HTTP/" +
            http_version,
            flush=True
        )


        await send_response(
            send,
            200,
            HTML_BYTES,
            "text/html; charset=windows-1252"
        )

        return


    # --------------------------------------------------------
    # JOIN
    # --------------------------------------------------------

    if (
        method == "POST" and
        path == "/join"
    ):

        try:

            raw = await read_body(
                receive
            )


            data = parse_snake_protocol(
                raw
            )


            session_id = str(
                data.get(
                    "session_id",
                    ""
                )
            )


            player_name = str(
                data.get(
                    "name",
                    ""
                )
            ).strip()


            if (
                not session_id or
                len(session_id) > 128
            ):

                raise ValueError(
                    "invalid session"
                )


            if (
                not player_name or
                len(player_name) > 20
            ):

                player_name = (
                    session_id[:4]
                )


            async with world_lock:

                if (
                    session_id
                    not in players
                ):

                    players[
                        session_id
                    ] = new_snake(
                        session_id,
                        player_name,
                        False
                    )


                response = make_state(
                    session_id
                )


            print(
                "[JOIN]",
                "ip=" + ip,
                "session=" +
                session_id,
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=ok\r\nok=1\r\n"
            )


        except Exception as exc:

            print(
                "[BAD JOIN]",
                ip,
                "raw=" + repr(raw if "raw" in locals() else b""),
                "parsed=" + repr(data if "data" in locals() else None),
                "error=" + repr(exc),
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=error\r\nerror=bad request\r\n",
                400
            )


        return


    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    if (
        method == "POST" and
        path == "/input"
    ):

        try:

            raw = await read_body(
                receive
            )


            data = parse_snake_protocol(
                raw
            )


            session_id = str(
                data.get(
                    "session_id",
                    ""
                )
            )


            direction = str(
                data.get(
                    "direction",
                    ""
                )
            )


            directions = {
                "up":
                    (0, -1),

                "down":
                    (0, 1),

                "left":
                    (-1, 0),

                "right":
                    (1, 0)
            }


            if (
                direction
                not in directions
            ):

                raise ValueError(
                    "invalid direction"
                )


            async with world_lock:

                snake = players.get(
                    session_id
                )


                if snake is None:

                    raise ValueError(
                        "unknown session"
                    )


                dx, dy = (
                    directions[
                        direction
                    ]
                )


                # Server decides
                # whether to accept or reject.

                if not (
                    dx ==
                    -snake["dx"] and
                    dy ==
                    -snake["dy"]
                ):

                    snake[
                        "wanted_dx"
                    ] = dx

                    snake[
                        "wanted_dy"
                    ] = dy


                snake[
                    "last_input"
                ] = time.time()


            print(
                "[INPUT]",
                "ip=" + ip,
                "session=" +
                session_id,
                "direction=" +
                direction,
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=ok\r\nok=1\r\n"
            )


        except Exception as exc:

            print(
                "[BAD INPUT]",
                ip,
                repr(
                    exc
                ),
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=error\r\nerror=bad request\r\n",
                400
            )


        return


    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    if (
        method == "GET" and
        path == "/state"
    ):

        session_id = query_param(
            scope,
            "session_id"
        )


        async with world_lock:

            if (
                session_id
                not in players
            ):

                await send_snake_protocol(
                    send,
                    "SnakeProtocol=1\r\ntype=error\r\nerror=not joined\r\n",
                    404
                )

                return


            response = make_state_protocol(
                session_id
            )


        await send_snake_protocol(
            send,
            response
        )

        return


    # --------------------------------------------------------
    # RESPAWN
    # --------------------------------------------------------

    if (
        method == "POST" and
        path == "/respawn"
    ):

        try:

            raw = await read_body(
                receive
            )


            data = parse_snake_protocol(
                raw
            )


            session_id = str(
                data.get(
                    "session_id",
                    ""
                )
            )


            async with world_lock:

                snake = players.get(
                    session_id
                )


                if snake is None:

                    raise ValueError(
                        "unknown player"
                    )


                if not snake[
                    "alive"
                ]:

                    respawn_snake(
                        snake
                    )


            print(
                "[RESPAWN]",
                "session=" +
                session_id,
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=ok\r\nok=1\r\n"
            )


        except Exception as exc:

            print(
                "[BAD RESPAWN]",
                repr(
                    exc
                ),
                flush=True
            )


            await send_snake_protocol(
                send,
                "SnakeProtocol=1\r\ntype=error\r\nerror=bad request\r\n",
                400
            )


        return


    await send_snake_protocol(
        send,
        "SnakeProtocol=1\r\ntype=error\r\nerror=not found\r\n",
        404
    )


# ============================================================
# GAME LOOP
# ============================================================

async def game_loop():

    while True:

        start = time.monotonic()


        async with world_lock:

            server_tick()


        elapsed = (
            time.monotonic() -
            start
        )


        await asyncio.sleep(
            max(
                0,
                TICK_INTERVAL -
                elapsed
            )
        )


# ============================================================
# TLS
# ============================================================

class TLS13Config(
    Config
):

    def create_ssl_context(
        self
    ):

        context = (
            super()
            .create_ssl_context()
        )


        if context is None:
            return None


        context.minimum_version = (
            ssl.TLSVersion.TLSv1_3
        )

        context.maximum_version = (
            ssl.TLSVersion.TLSv1_3
        )


        context.set_alpn_protocols(
            [
                "h2",
                "http/1.1"
            ]
        )


        return context


# ============================================================
# MAIN
# ============================================================

async def main():

    config = TLS13Config()


    sock = socket.socket(
        socket.AF_INET6,
        socket.SOCK_STREAM
    )


    sock.setsockopt(
        socket.IPPROTO_IPV6,
        socket.IPV6_V6ONLY,
        1
    )


    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )


    sock.bind(
        (
            HOST,
            PORT
        )
    )


    sock.listen(
        100
    )


    sock.set_inheritable(
        True
    )


    config.bind = [
        "fd://" +
        str(
            sock.fileno()
        )
    ]


    config.certfile = (
        CERT_FILE
    )

    config.keyfile = (
        KEY_FILE
    )


    config.alpn_protocols = [
        "h2",
        "http/1.1"
    ]


    config.accesslog = "-"
    config.errorlog = "-"

    config.include_server_header = (
        False
    )


    # Create bots ON THE SERVER

    async with world_lock:

        for number in range(
            1,
            BOT_COUNT + 1
        ):

            bot_id = (
                "bot-" +
                str(
                    number
                )
            )


            bots[
                bot_id
            ] = new_snake(
                bot_id,
                "Bot " +
                str(
                    number
                ),
                True
            )


        refill_pellets()


    print(
        "Snake Arena Server",
        flush=True
    )

    print(
        "HTTPS: [::]:8443",
        flush=True
    )

    print(
        "IPv6-only: IPV6_V6ONLY=1",
        flush=True
    )

    print(
        "TLS: 1.3 only",
        flush=True
    )

    print(
        "ALPN: h2, http/1.1",
        flush=True
    )

    print(
        "Server-authoritative: YES",
        flush=True
    )

    print(
        "Bots: " +
        str(
            BOT_COUNT
        ),
        flush=True
    )

    print(
        "Tick rate: " +
        str(
            TICK_HZ
        ) +
        " Hz",
        flush=True
    )


    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    for signum in (
        signal.SIGINT,
        signal.SIGTERM
    ):

        try:
            loop.add_signal_handler(
                signum,
                shutdown_event.set
            )
        except NotImplementedError:
            pass


    tick_task = asyncio.create_task(
        game_loop()
    )


    try:

        await serve(
            app,
            config,
            shutdown_trigger=shutdown_event.wait
        )

    finally:

        tick_task.cancel()

        try:
            await tick_task
        except asyncio.CancelledError:
            pass

        sock.close()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
