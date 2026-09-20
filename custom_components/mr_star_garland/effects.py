"""Effect table for MR Star garlands.

Mode numbers and names are taken from the MR Star Android app
(com.frok.mrstar 1.0.0): the numbers from ModeFragment.setModeData and
sendModeByIndex, the names from the app's own cmode<n> string resources.

`app_listed` marks the modes the official app offers in its Mode tab. The
remainder are modes the firmware answers to that the app does not list; they
are included because mr_star_ble enumerates them.
"""

from __future__ import annotations

from typing import Final, NamedTuple


class EffectDef(NamedTuple):
    """One firmware mode."""

    mode: int
    name: str
    app_listed: bool


EFFECT_DEFS: Final[tuple[EffectDef, ...]] = (
    EffectDef(1, 'Automatic loop', True),
    EffectDef(2, 'Symphony', True),
    EffectDef(3, 'Colorful energy', True),
    EffectDef(4, 'Colorful jumps', True),
    EffectDef(7, '7 colors strobe', True),
    EffectDef(9, 'Yellow-purple-blue strobe', False),
    EffectDef(10, '7 colors gradient', True),
    EffectDef(26, 'Colorful fluttering', True),
    EffectDef(27, 'Red-green-blue fluttering', True),
    EffectDef(28, 'Yellow-cyan-purple fluttering', False),
    EffectDef(29, 'Colorful brushing', True),
    EffectDef(30, 'Red-green-blue color brushing', True),
    EffectDef(31, 'Yellow-cyan-purple color brushing', True),
    EffectDef(32, 'Colorful brush color brush closed-pull', True),
    EffectDef(35, '7 colors opening-closing', True),
    EffectDef(36, 'Red-green-blue opening-closing', True),
    EffectDef(37, 'Yellow-cyan-purple opening-closes', True),
    EffectDef(38, 'Red opening-closing', True),
    EffectDef(39, 'Green opening-closing', True),
    EffectDef(40, 'Blue opening-closing', True),
    EffectDef(41, 'Yellow opening-closing', True),
    EffectDef(42, 'Cyan opening-closing', True),
    EffectDef(43, 'Purple opening-closing', True),
    EffectDef(44, 'White opening-closing', True),
    EffectDef(45, '7 colors light-dark transition', True),
    EffectDef(46, 'Blue-red-green light-dark transition', True),
    EffectDef(47, 'Violet-green-yellow light-dark transition', True),
    EffectDef(48, '6 colors light-dark transition red', True),
    EffectDef(49, '6 colors light-dark transition green', True),
    EffectDef(50, '6 colors light-dark transition blue', True),
    EffectDef(51, '6 colors light-dark transition cyan', True),
    EffectDef(52, '6 colors light-dark transition yellow', True),
    EffectDef(53, '6 colors light-dark transition purple', True),
    EffectDef(54, '6 colors light-dark transition white', True),
    EffectDef(55, '7 colors flowing water', True),
    EffectDef(56, 'Blue-green-red running water', True),
    EffectDef(57, 'Purple-green-yellow running water', True),
    EffectDef(58, 'Red-green running water', True),
    EffectDef(59, 'Green-blue running water', True),
    EffectDef(60, 'Yellow-blue running water', True),
    EffectDef(61, 'Yellow-cyan running water', True),
    EffectDef(62, 'Blue-purple running water', True),
    EffectDef(63, 'Black-white running water', True),
    EffectDef(64, 'White-red-white flow', True),
    EffectDef(65, 'White-green-white flow (65)', True),
    EffectDef(66, 'White-blue-white flow', True),
    EffectDef(67, 'White-yellow-white flow', True),
    EffectDef(68, 'White-green-white flow (68)', True),
    EffectDef(69, 'White purple-white flow', True),
    EffectDef(70, 'Red-white-red flow', True),
    EffectDef(71, 'Green-white-green flow', True),
    EffectDef(72, 'Blue-white-blue flow (72)', True),
    EffectDef(73, 'Yellow-white-yellow flow', True),
    EffectDef(74, 'Blue-white-blue flow (74)', True),
    EffectDef(75, 'Purple-white-purple flow', True),
    EffectDef(76, '7 colors trailing', True),
    EffectDef(77, 'Red trailing', True),
    EffectDef(78, 'Green trailing', True),
    EffectDef(79, 'Blue trailing', True),
    EffectDef(80, 'Yellow trailing', True),
    EffectDef(81, 'Cyan tailing', True),
    EffectDef(82, 'Purple tailing', True),
    EffectDef(83, 'White trailing', True),
    EffectDef(84, 'Red running', True),
    EffectDef(85, 'Green running', True),
    EffectDef(86, 'Blue running', True),
    EffectDef(87, 'Yellow running', True),
    EffectDef(88, 'Cyan running', True),
    EffectDef(89, 'Purple running', True),
    EffectDef(90, 'White running', True),
    EffectDef(91, '7 colors running', True),
    EffectDef(92, 'Blue-green-red running', True),
    EffectDef(93, 'Purple-cyan-yellow running', True),
    EffectDef(94, 'Blue-purple-cyan-yellow running', False),
    EffectDef(95, 'Blue-green-cyan-yellow running', False),
)

#: Display name -> firmware mode number.
EFFECTS: Final[dict[str, int]] = {d.name: d.mode for d in EFFECT_DEFS}

#: Sorted list for the light entity's effect_list.
EFFECT_LIST: Final[list[str]] = sorted(EFFECTS)

#: Names used by this integration before the app was decompiled, kept so that
#: existing automations and scenes selecting an effect by name keep working.
LEGACY_EFFECT_ALIASES: Final[dict[str, int]] = {
    "Automatic Loop": 1,
    "Symphony": 2,
    "Fluttering": 26,
    "Open & Close": 35,
    "Light & Dark Transition": 45,
    "Flowing Water": 55,
}
