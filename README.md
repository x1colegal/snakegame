
# 🐍 Snake Arena

A real-time multiplayer Snake game built with Python, Hypercorn, HTML5 Canvas, and a custom communication protocol called **SnakeProtocol 1**.

Snake Arena uses a fully server-authoritative architecture. All movement, collisions, scoring, bot AI, and respawning are controlled by the server.

## Features

- Real-time multiplayer gameplay
- Fully server-authoritative game engine
- 35 AI-controlled bots
- Custom SnakeProtocol 1
- Windows-1252 character encoding
- IPv6-only server
- TLS 1.3 only
- HTTP/2 and HTTP/1.1 support
- 10 Hz server tick rate
- Live leaderboard and King system
- Kill rewards and scoring
- Automatic bot respawning
- Manual player respawning
- Food generated from dead snakes
- HTTP response latency monitoring
- Mobile touch and desktop keyboard controls
- HTML5 Canvas rendering
- Square snake segments
- Dark gray background
- Apple-shaped food

## Requirements

- Python 3.10+
- Hypercorn
- TLS certificate and private key
- IPv6 networking
- Modern web browser

Install Hypercorn:

```bash
pip install hypercorn
```

## Project Structure

```text
snakegame/
├── snake.py
├── cert.pem
├── key.pem
└── README.md
```

## Running the Server

Start Snake Arena:

```bash
python snake.py
```

The server listens on:

```text
[::]:8443
```

Open the game in your browser:

```text
https://[YOUR_IPV6_ADDRESS]:8443/
```

A valid TLS certificate trusted by the browser is recommended.

## Server Configuration

| Setting | Value |
|---|---|
| Host | `::` |
| Port | `8443` |
| Address Family | IPv6 |
| IPv6 Only | Enabled |
| TLS | 1.3 only |
| ALPN | `h2`, `http/1.1` |
| Game Protocol | SnakeProtocol 1 |
| Encoding | Windows-1252 |
| World Size | 120 × 120 |
| Tick Rate | 10 Hz |
| Tick Interval | 100 ms |
| Bots | 35 |
| Food Target | 140 |
| Starting Length | 5 |

## Architecture

Snake Arena uses a fully server-authoritative game engine.

### Server Responsibilities

The Python server handles:

- Player movement
- Bot decisions
- Collision detection
- Deaths and kills
- Score calculation
- Food generation
- Food consumption
- Respawning
- Player sessions
- World state
- Leaderboard rankings

### Client Responsibilities

The browser handles:

- Rendering the game world
- Capturing keyboard and touch input
- Sending movement commands
- Receiving game-state snapshots
- Displaying scores and rankings
- Measuring HTTP response latency

Clients cannot directly set their scores, positions, or snake lengths.

## SnakeProtocol 1

SnakeProtocol 1 is a custom text-based application protocol used for communication between the browser and the Python server.

It operates over HTTPS using HTTP/2 or HTTP/1.1.

### Content Type

```http
Content-Type: application/x-snakeprotocol; charset=windows-1252
```

### Encoding

SnakeProtocol uses Windows-1252.

Messages contain key-value pairs separated by CRLF (`\r\n`).

### Example Message

```text
SnakeProtocol=1
type=input
session_id=abc123
direction=up
```

### Character Escaping

Special characters are escaped using percent-encoded sequences.

| Character | Escape |
|---|---|
| `%` | `%25` |
| `\|` | `%7C` |
| `;` | `%3B` |
| `,` | `%2C` |
| `=` | `%3D` |
| CR | `%0D` |
| LF | `%0A` |

## API Endpoints

### GET /

Returns the HTML5 game client.

Content type:

```http
Content-Type: text/html; charset=windows-1252
```

### POST /join

Creates a player session.

Example request:

```text
SnakeProtocol=1
type=join
session_id=abc123
name=Player1
```

Example response:

```text
SnakeProtocol=1
type=ok
ok=1
```

Existing session IDs retain their existing player objects.

### POST /input

Sends a movement command.

Supported directions:

- `up`
- `down`
- `left`
- `right`

Example request:

```text
SnakeProtocol=1
type=input
session_id=abc123
direction=left
```

The server validates movement commands.

Direct 180-degree reversals are rejected.

### GET /state

Returns the authoritative game state.

Example request:

```http
GET /state?session_id=abc123
```

Example response:

```text
SnakeProtocol=1
type=state
tick=1500
you=abc123
king=abc123
world=120,120
snake=abc123|Player1|0|1|0|50|1|1|#69ff78|10,10;9,10;8,10
pellet=25,30|1|#ff5874
leader=abc123|Player1|50|3
```

The response includes:

- Server tick
- Player session ID
- Current King
- World dimensions
- Snake positions
- Snake directions
- Snake scores
- Snake colors
- Alive/dead status
- Food positions and values
- Leaderboard entries

### POST /respawn

Respawns a dead player.

Example request:

```text
SnakeProtocol=1
type=respawn
session_id=abc123
```

Example response:

```text
SnakeProtocol=1
type=ok
ok=1
```

## Game Engine

The server runs at 10 ticks per second.

Each tick performs the following operations:

1. Update bot AI decisions.
2. Apply movement directions.
3. Calculate proposed snake positions.
4. Detect collisions.
5. Determine deaths and killers.
6. Distribute kill rewards.
7. Process snake deaths.
8. Move surviving snakes.
9. Process food consumption.
10. Respawn eligible bots.
11. Refill food.

The simulation runs independently of client rendering.

An asynchronous lock protects shared world-state operations.

## Collision System

### Head Collisions

Player-controlled snakes have priority over bots in head collisions.

- Player vs Bot: Player wins.
- Bot vs Player: Player wins.
- Same-type collisions: The attacking snake kills the target.

In simultaneous collisions, multiple collision evaluations may affect the result.

### Body Collisions

Body collisions use snake length.

- Smaller vs Larger: Smaller snake dies.
- Larger vs Smaller: Smaller snake dies.
- Equal Length: Both snakes die.

Self-collisions are ignored by the current engine.

## Scoring

Players earn points by collecting food and eliminating opponents.

Normal food:

```text
Value: 1 point
```

Food dropped by dead snakes:

```text
Value: 2 points
```

Eliminating another snake awards its current score to the killer.

All scores are maintained by the server.

## Food System

Food is generated automatically.

The server attempts to maintain at least 140 food items.

When a snake dies, every second body segment becomes food.

Food can accumulate beyond the initial target.

Food positions are generated around living snakes when possible.

## Bot AI

Snake Arena includes 35 server-controlled bots.

Bots can:

- Search for nearby opponents
- Predict opponent movement
- Attempt to intercept other snakes
- Avoid currently occupied cells
- Seek food when no opponent is available
- Change movement directions
- Respawn automatically

Bots respawn approximately two seconds after death.

All bot decisions are made on the server.

## Leaderboard

The leaderboard displays the five highest-ranked living snakes.

Ranking priority:

1. Score
2. Snake length

The highest-ranked living snake becomes the King.

The King receives a crown indicator above its head.

## Multiplayer Sessions

Each browser generates a UUID for its session.

The session ID is stored in `localStorage`.

The server uses the session ID to identify players.

Players can choose nicknames up to 20 characters long.

If no nickname is provided, the browser generates a random four-character nickname.

## Client Communication

The browser communicates with the server using HTTPS requests.

The client polls `/state` approximately every 80 milliseconds.

The server simulation runs at 10 Hz.

Consequently, multiple state requests can return snapshots from the same server tick.

Movement commands are submitted through `/input`.

The server remains authoritative regardless of client timing.

## RTT Monitoring

Snake Arena measures HTTP response latency using the browser's `performance.now()` API.

The measurement starts before requesting `/state` and ends when the response headers become available.

It includes:

- Request transmission time
- Server-side processing
- SnakeProtocol state serialization
- HTTP response-header delivery

It does not wait for the complete response body.

This is an application-level HTTP response-time measurement, not a direct TCP RTT measurement.

No additional network requests are required.

## Controls

### Desktop

Use the arrow keys:

```text
Up Arrow    Move up
Down Arrow  Move down
Left Arrow  Move left
Right Arrow Move right
```

### Mobile

Swipe in the desired direction.

Tap the game area after dying to respawn.

## Graphics

The game uses HTML5 Canvas.

Visual features include:

- Dark gray background
- Square snake segments
- Apple-shaped food
- Colored snakes
- King crown indicator
- Score HUD
- Leaderboard
- Connection status
- RTT indicator

The camera follows the player's snake.

## HTTPS and TLS

Snake Arena uses TLS 1.3 exclusively.

Supported ALPN protocols:

```text
h2
http/1.1
```

Hypercorn handles the ASGI HTTP server.

Certificate files:

```text
cert.pem
key.pem
```

The application does not directly accept unencrypted HTTP connections.

## IPv6

Snake Arena explicitly creates an IPv6 socket:

```python
socket.socket(
    socket.AF_INET6,
    socket.SOCK_STREAM
)
```

IPv6-only mode is enabled:

```python
sock.setsockopt(
    socket.IPPROTO_IPV6,
    socket.IPV6_V6ONLY,
    1
)
```

Listening address:

```text
[::]:8443
```

IPv4 connections are not accepted directly by the application socket.

## HTTP Responses

SnakeProtocol responses use:

```http
Content-Type: application/x-snakeprotocol; charset=windows-1252
Cache-Control: no-store
```

HTML responses use:

```http
Content-Type: text/html; charset=windows-1252
Cache-Control: no-store
```

Responses include an explicit Content-Length header.

## Server Logs

The server prints events such as:

```text
[JOIN]
[INPUT]
[KILL]
[RESPAWN]
[BAD JOIN]
[BAD INPUT]
[BAD RESPAWN]
```

Kill events include:

- Killer name
- Victim name
- Reward
- Killer score

HTTP access and error logging are provided by Hypercorn.

## Technical Stack

| Component | Technology |
|---|---|
| Backend | Python |
| Async Runtime | asyncio |
| HTTP Server | Hypercorn |
| Interface | HTML5 / CSS / JavaScript |
| Rendering | Canvas 2D |
| Application Protocol | SnakeProtocol 1 |
| Character Encoding | Windows-1252 |
| Transport | HTTPS |
| TLS | TLS 1.3 |
| HTTP | HTTP/2 and HTTP/1.1 |
| Network | IPv6-only |
| Game Simulation | Server-authoritative |

## Notes

- The game world is stored in server memory.
- Player sessions are not persisted across server restarts.
- Game state is shared by all connected players.
- Bots run inside the same Python server process.
- State synchronization uses HTTP polling.
- WebSockets and WebRTC are not required.
- The game uses a custom protocol instead of JSON for its primary client-server communication.
- All gameplay decisions are made by the server.


## License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for the full license text.

