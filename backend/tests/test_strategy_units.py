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
