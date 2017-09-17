import collections
import enum

import attr
from frozendict import frozendict

WHITE = 0

RED = 1
YELLOW = 2
BLUE = 4

ORANGE = RED | YELLOW
GREEN = BLUE | YELLOW
PURPLE = RED | BLUE

BLACK = RED | YELLOW | BLUE

PRIMARY_COLORS = {RED, YELLOW, BLUE}
SECONDARY_COLORS = {ORANGE, GREEN, PURPLE}


class ConnectionType(enum.Enum):
    bridge = 1
    blocker = 2
    flippy = 3
    button = 4


frozen_setattr = object.__setattr__
terminal_colors = {
    WHITE: 15,
    RED: 1,
    ORANGE: 208,
    YELLOW: 11,
    GREEN: 2,
    BLUE: 4,
    PURPLE: 5,
    BLACK: 8,
}
clear = '\x1b[0m'
af = '\x1b[38;5;{}m{}\x1b[0m'.format


def convert_buttons(buttons):
    if isinstance(buttons, int):
        return (buttons,)
    return buttons


@attr.s(frozen=True, slots=True)
class Zone:
    uid = attr.ib()
    colorizers = attr.ib(default=[], convert=frozenset)  # [Color]
    goals = attr.ib(default=0)  # int
    buttons = attr.ib(default=None, convert=convert_buttons)  # (int, ...)


# Connection classes: used to define connections between zones
@attr.s(frozen=True, slots=True)
class Bridge:
    connection_type = ConnectionType.bridge
    zone1 = attr.ib()
    zone2 = attr.ib()
    color = attr.ib()


@attr.s(frozen=True, slots=True)
class Blocker:
    connection_type = ConnectionType.blocker
    zone1 = attr.ib()
    zone2 = attr.ib()
    color = attr.ib()


@attr.s(frozen=True, slots=True)
class Flippy:
    connection_type = ConnectionType.flippy
    zone1 = attr.ib()
    zone2 = attr.ib()


@attr.s(frozen=True, slots=True)
class ButtonBridge:
    connection_type = ConnectionType.button
    zone1 = attr.ib()
    zone2 = attr.ib()
    button_set = attr.ib(default=0)


# Class for modelling connections out of a zone
@attr.s(frozen=True, slots=True)
class DirectedConnection:
    to_zone = attr.ib()
    connection = attr.ib()


@attr.s(slots=True, frozen=True)
class Board:
    zones = attr.ib()  # [Zone]
    connections = attr.ib(convert=frozendict)  # {Zone: DirectedConnection}


def get_connections_by_zone(connections):
    connections_by_zone = collections.defaultdict(list)
    bridges_state = collections.Counter()

    for conn in connections:
        conn_12 = DirectedConnection(conn.zone2, conn)
        conn_21 = DirectedConnection(conn.zone1, conn)
        if conn.connection_type == ConnectionType.flippy:
            bridges_state[ConnectionType.flippy, conn.zone1, conn.zone2] += 1
            bridges_state.setdefault((ConnectionType.flippy, conn.zone2, conn.zone1), 0)
        connections_by_zone[conn.zone1].append(conn_12)
        connections_by_zone[conn.zone2].append(conn_21)
    return connections_by_zone, frozendict(bridges_state)


def serialized_counter(mushrooms):
    return frozendict(+collections.Counter(mushrooms))


@attr.s(frozen=True, slots=True)
class State:
    mushrooms = attr.ib(convert=serialized_counter)  # {(Color, Zone): int}
    bridges = attr.ib(convert=frozendict)  # {(ConnectionType, Zone, Zone): int}

    def __str__(self):
        by_zone = collections.defaultdict(list)
        for (color, zone), qty in self.mushrooms.items():
            by_zone[zone].append((color, qty))

        zones = ', '.join(
            'Zone {}[{}]'.format(
                zone.uid,
                ', '.join(
                    af(terminal_colors[color], qty)
                    for color, qty in shrooms
                )
            )
            for zone, shrooms in by_zone.items()
        )
        # TODO: should prob print bridges here but it's pretty verbose
        # return '{} {}'.format(zones, self.bridges)
        return zones


def get_next_states(board, state):
    shrooms = state.mushrooms

    for color, zone in shrooms:
        # split
        if color in SECONDARY_COLORS:
            shroom_clone = collections.Counter(shrooms)
            shroom_clone[color, zone] -= 1
            if color & RED:
                shroom_clone[RED, zone] += 1
            if color & YELLOW:
                shroom_clone[YELLOW, zone] += 1
            if color & BLUE:
                shroom_clone[BLUE, zone] += 1
            yield State(shroom_clone, state.bridges)

        # join
        if color in PRIMARY_COLORS:
            for other_color in PRIMARY_COLORS - {color}:
                if (other_color, zone) in shrooms:
                    shroom_clone = collections.Counter(shrooms)
                    shroom_clone[other_color, zone] -= 1
                    shroom_clone[color, zone] -= 1
                    shroom_clone[color | other_color, zone] += 1
                    yield State(shroom_clone, state.bridges)

        # colorize
        if color == WHITE:
            for new_color in zone.colorizers:
                shroom_clone = collections.Counter(shrooms)
                shroom_clone[color, zone] -= 1
                shroom_clone[new_color, zone] += 1
                yield State(shroom_clone, state.bridges)

        # decolorize
        if color in zone.colorizers:
            shroom_clone = collections.Counter(shrooms)
            shroom_clone[color, zone] -= 1
            shroom_clone[WHITE, zone] += 1
            yield State(shroom_clone, state.bridges)

        # move
        for direction in board.connections[zone]:
            connected = False
            bridges = state.bridges
            connection_type = direction.connection.connection_type
            if connection_type == ConnectionType.bridge:
                connected = (color & direction.connection.color) == direction.connection.color
            elif connection_type == ConnectionType.blocker:
                connected = not bool(color & direction.connection.color)
            elif connection_type == ConnectionType.flippy:
                connected = (
                    color not in SECONDARY_COLORS and
                    bridges[ConnectionType.flippy, zone, direction.to_zone]
                )
                if connected:
                    bridges = dict(bridges)
                    bridges[ConnectionType.flippy, zone, direction.to_zone] -= 1
                    bridges[ConnectionType.flippy, direction.to_zone, zone] += 1
                    bridges = frozendict(bridges)
            elif connection_type == ConnectionType.button:
                index = direction.connection.button_set
                buttons = collections.Counter({
                    zone_: zone_.buttons[index]
                    for zone_ in board.zones
                    if zone_.buttons and zone_.buttons[index]
                })
                for (color_, zone_), qty in shrooms.items():
                    if (color_, zone_) == (color, zone):  # can't hold button for yourself
                        qty -= 1
                    buttons[zone_] -= qty
                connected = not +buttons
            else:
                raise NotImplementedError(connection_type)

            if connected:
                shroom_clone = collections.Counter(shrooms)
                shroom_clone[color, zone] -= 1
                shroom_clone[color, direction.to_zone] += 1
                yield State(shroom_clone, bridges)


def is_victory(board, state):
    goals = collections.Counter({
        zone: zone.goals
        for zone in board.zones
        if zone.goals
    })
    for (_, zone), qty in state.mushrooms.items():
        goals[zone] -= qty

    return not (+goals or -goals)


def solve(board, start_state):
    paths = {}
    seen = {start_state}
    queue = collections.deque(seen)

    while queue:
        state = queue.popleft()

        if is_victory(board, state):
            return reconstruct_paths(paths, state)

        for next_state in get_next_states(board, state):
            if next_state not in seen:
                seen.add(next_state)
                queue.append(next_state)
                paths[next_state] = state


def reconstruct_paths(paths, state):
    path = collections.deque()
    while state in paths:
        path.appendleft(state)
        state = paths[state]
    path.appendleft(state)
    return path

# ---

def test1():
    # Test dem flippy doors
    zones = [
        Zone(uid='left'),
        Zone(uid='right', goals=2),
    ]
    connections, bridges_state = get_connections_by_zone([
        Flippy(zones[1], zones[0]),
        Blocker(zones[0], zones[1], color=BLUE),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (BLUE, zones[0]),
            (RED, zones[0]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test2():
    # test flippy doors impassible to secondary colors
    zones = [
        Zone(uid='left'),
        Zone(uid='right', goals=2),
    ]
    connections, bridges_state = get_connections_by_zone([
        Flippy(zones[0], zones[1]),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (PURPLE, zones[0]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_6_1():
    zones = [
        Zone(uid='top', goals=1),
        Zone(uid='right', goals=1),
        Zone(uid='left'),
        Zone(uid='bottom', goals=2),
    ]
    connections, bridges_state = get_connections_by_zone([
        Flippy(zones[0], zones[1]),
        Flippy(zones[2], zones[1]),
        Bridge(zones[2], zones[3], color=ORANGE),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (ORANGE, zones[0]),
            (BLUE, zones[2]),
            (BLUE, zones[2]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_inspiration():
    zones = [
        Zone(uid='top left', colorizers=[BLUE]),
        Zone(uid='top', colorizers=[RED, YELLOW]),
        Zone(uid='left'),
        Zone(uid='middle'),
        Zone(uid='right'),
        Zone(uid='bottom', goals=3),
    ]
    connections, bridges_state = get_connections_by_zone([
        Blocker(zones[0], zones[1], color=BLUE),
        Bridge(zones[0], zones[2], color=PURPLE),
        Blocker(zones[2], zones[3], color=RED),
        Blocker(zones[1], zones[3], color=PURPLE),
        Bridge(zones[1], zones[4], color=BLUE),
        Bridge(zones[4], zones[5], color=RED),
        Flippy(zones[3], zones[4]),
        Flippy(zones[3], zones[4]),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (ORANGE, zones[1]),
            (RED, zones[3]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_6_7():
    zones = [
        Zone(uid='top', goals=2, colorizers=[RED]),
        Zone(uid='middle'),
        Zone(uid='right', buttons=1),
        Zone(uid='left', goals=1, colorizers=[BLUE]),
        Zone(uid='bottom', buttons=1),
    ]
    connections, bridges_state = get_connections_by_zone([
        Bridge(zones[0], zones[1], color=BLUE),
        Blocker(zones[0], zones[1], color=ORANGE),
        Blocker(zones[1], zones[2], color=BLUE),
        Bridge(zones[2], zones[3], color=YELLOW),
        ButtonBridge(zones[1], zones[3]),
        Bridge(zones[3], zones[4], color=BLUE),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (BLUE, zones[3]),
            (RED, zones[3]),
            (YELLOW, zones[3]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_7_2():
    zones = [
        Zone(uid='top left', goals=1, buttons=(1, 0)),
        Zone(uid='top', buttons=(0, 1)),
        Zone(uid='top right', goals=1),
        Zone(uid='bottom left', buttons=(1, 0)),
        Zone(uid='bottom'),
        Zone(uid='bottom right', goals=2, buttons=(1, 0)),
    ]
    connections, bridges_state = get_connections_by_zone([
        Bridge(zones[0], zones[1], color=BLUE),
        Blocker(zones[1], zones[2], color=YELLOW),
        Bridge(zones[0], zones[3], color=PURPLE),
        Blocker(zones[3], zones[4], color=RED),
        ButtonBridge(zones[1], zones[4], button_set=1),
        ButtonBridge(zones[4], zones[5], button_set=0),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (RED, zones[0]),
            (PURPLE, zones[3]),
            (YELLOW, zones[5]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_7_4():
    zones = [
        Zone(uid='top', colorizers=[BLUE, RED]),
        Zone(uid='right'),
        Zone(uid='middle', colorizers=[YELLOW]),
        Zone(uid='left', buttons=1, goals=1),
        Zone(uid='bottom right'),
        Zone(uid='bottom', goals=2),
    ]
    connections, bridges_state = get_connections_by_zone([
        ButtonBridge(zones[0], zones[1]),
        Blocker(zones[0], zones[1], color=ORANGE),
        Blocker(zones[0], zones[2], color=ORANGE),
        Bridge(zones[1], zones[2], color=BLUE),
        Flippy(zones[1], zones[4]),
        Bridge(zones[2], zones[3], color=RED),
        Bridge(zones[4], zones[5], color=ORANGE),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (PURPLE, zones[1]),
            (RED, zones[4]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


def test_8_1():
    zones = [
        Zone(uid='top', colorizers=[BLUE, YELLOW], buttons=1),
        Zone(uid='top left', buttons=1),
        Zone(uid='left'),
        Zone(uid='bottom left'),
        Zone(uid='right', colorizers=[RED]),
        Zone(uid='goal', goals=3),
        Zone(uid='bottom', goals=1),
        Zone(uid='middle'),
        Zone(uid='red', colorizers=[RED]),
    ]
    connections, bridges_state = get_connections_by_zone([
        Bridge(zones[0], zones[1], color=ORANGE),
        Bridge(zones[1], zones[2], color=BLUE),
        ButtonBridge(zones[2], zones[7]),
        Flippy(zones[2], zones[3]),
        Blocker(zones[3], zones[6], color=YELLOW),
        Bridge(zones[6], zones[8], color=PURPLE),
        Flippy(zones[8], zones[7]),
        Blocker(zones[0], zones[7], color=YELLOW),
        Bridge(zones[0], zones[4], color=RED),
        Blocker(zones[4], zones[5], color=BLACK),
    ])
    board = Board(
        zones=zones,
        connections=connections,
    )
    state = State(
        mushrooms=[
            (BLACK, zones[0]),
            (PURPLE, zones[7]),
            (YELLOW, zones[3]),
        ],
        bridges=bridges_state,
    )
    return solve(board, state)


if __name__ == '__main__':
    paths = test_7_2()
    if paths:
        print()
        print("SOLUTION")
        for path in paths:
            print(path)
    else:
        print("NO SOLUTION I GUESS :T")
