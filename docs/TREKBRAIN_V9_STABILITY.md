# TrekBrain v9 stability phase

## Why this exists

TrekBrain v9 accumulated many useful specialised layers: request reconciliation,
GR/GRP discovery, route-network planning, ORS resilience, campsite recovery,
water discovery, failure previews and diagnostics. Several production regressions
came from those layers being individually correct but interacting in the wrong
order.

The stability phase changes the rule: **a local fix is not considered safe until
all reference scenarios pass together in the fully wired v9 process**.

## Frozen reference scenarios

1. **Belle-Île, GR 340, no camping constraint**
   - natural language must override a stale `Traversée` form value;
   - walking geometry stays on Belle-Île;
   - ferry access is transport metadata only;
   - GR 340 remains the walking backbone;
   - five sensible hiking days.

2. **Belle-Île, GR 340, camping requested**
   - same walking backbone as the no-camping case;
   - lodging is solved after the route;
   - a lodging problem must not reshape or delete a valid hiking route;
   - partial lodging is allowed to degrade gracefully instead of becoming an
     unrelated internal server error.

3. **Mont-Saint-Michel loop**
   - natural-language location overrides stale form geography;
   - the loop must actually close;
   - the daily-km value is a target, not a demand to invent distance;
   - a deliberately shorter day can be valid when the geography requires it.

4. **Generic loop without a GR**
   - the generic path/ORS planner remains usable;
   - no feature may assume that every trek has a named hiking relation;
   - lodging and water remain secondary to the validated pedestrian geometry.

5. **Generic point-to-point traverse without a GR**
   - start and end remain distinct;
   - loop recovery must never silently convert a traverse into a loop;
   - duration and daily-distance interpretation remain stable.

## Critical wrapper topology

The stability gate imports `backend.app_v5` once and inspects the installed
`smart_planner_v3._build` closure chain. The following order is protected because
we have already seen regressions when it changed accidentally:

`failure diagnostics -> lodging fail-open guard -> route-first lodging -> Belle-Île canonical planner`

Other wrappers may exist outside or between these layers, but these four must
remain in that relative order.

## Merge rule during stabilization

Until the architecture has been simplified, TrekBrain changes should go through
a branch/PR and the **TrekBrain v9 stability gate** must be green alongside the
existing v9 suite. A green unit test for one specialised module is not enough.

The next refactor target is a smaller explicit pipeline:

`understand request -> build route -> split days -> attach logistics -> validate`

The stability contracts deliberately describe outputs rather than implementation,
so wrappers can be removed later without rewriting the expected behaviour.
