from app.domain.models import StintPlan
from app.simulation.strategy import StrategySimulator


def test_candidate_strategies_have_two_compounds_on_one_stop():
    sim = StrategySimulator.__new__(StrategySimulator)
    strats = StrategySimulator._candidate_strategies(sim, 56)
    one = [s for s in strats if s["stops"] == 1]
    assert one
    assert all(len(set(s["compounds"])) >= 2 for s in one)


def test_stints_cover_full_race():
    sim = StrategySimulator.__new__(StrategySimulator)
    strategy = {"stops": 1, "compounds": ["MEDIUM", "HARD"], "pit_laps": [20], "label": "t"}
    stints = StrategySimulator._stints_from_strategy(sim, strategy, 56)
    assert stints[0].lap_start == 1
    assert stints[-1].lap_end == 56
    assert stints[0].lap_end == 20
    assert stints[1].lap_start == 21


def test_to_global_strategies_ranks_and_gaps():
    sim = StrategySimulator.__new__(StrategySimulator)
    stints = [
        StintPlan(compound="MEDIUM", lap_start=1, lap_end=20),
        StintPlan(compound="HARD", lap_start=21, lap_end=56),
    ]
    scored = [
        (5100.0, {"stops": 1, "compounds": ["SOFT", "HARD"], "pit_laps": [18], "label": "a"}, stints),
        (5000.0, {"stops": 1, "compounds": ["MEDIUM", "HARD"], "pit_laps": [22], "label": "b"}, stints),
        (5050.0, {"stops": 1, "compounds": ["HARD", "MEDIUM"], "pit_laps": [26], "label": "c"}, stints),
        (5200.0, {"stops": 2, "compounds": ["SOFT", "MEDIUM", "HARD"], "pit_laps": [12, 32], "label": "d"}, stints),
        (5300.0, {"stops": 2, "compounds": ["MEDIUM", "SOFT", "HARD"], "pit_laps": [15, 36], "label": "e"}, stints),
    ]
    out = StrategySimulator._to_global_strategies(sim, scored, 56, top_n=4)
    assert len(out) == 4
    assert [s.rank for s in out] == [1, 2, 3, 4]
    assert out[0].gap_to_best_s == 0.0
    assert out[0].compounds == ["MEDIUM", "HARD"]
    assert out[1].gap_to_best_s == 50.0
    assert out[2].gap_to_best_s == 100.0


def test_to_global_strategies_merges_pit_window():
    sim = StrategySimulator.__new__(StrategySimulator)
    stints = [
        StintPlan(compound="SOFT", lap_start=1, lap_end=26),
        StintPlan(compound="HARD", lap_start=27, lap_end=56),
    ]
    scored = [
        (5000.0, {"stops": 1, "compounds": ["SOFT", "HARD"], "pit_laps": [26], "label": "x"}, stints),
        (5000.2, {"stops": 1, "compounds": ["SOFT", "HARD"], "pit_laps": [30], "label": "y"}, stints),
        (5005.0, {"stops": 1, "compounds": ["SOFT", "HARD"], "pit_laps": [14], "label": "z"}, stints),
        (5100.0, {"stops": 1, "compounds": ["MEDIUM", "HARD"], "pit_laps": [22], "label": "m"}, stints),
    ]
    out = StrategySimulator._to_global_strategies(sim, scored, 56, top_n=4)
    assert len(out) == 2
    assert out[0].compounds == ["SOFT", "HARD"]
    assert out[0].pit_windows == [[26, 30]]
    assert out[0].pit_laps == [26]
    assert "26-30" in out[0].strategy_label
    assert out[1].compounds == ["MEDIUM", "HARD"]
