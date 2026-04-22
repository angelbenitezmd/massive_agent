from app.services.trade_policy import build_trade_plan, evaluate_buy_gate, should_execute_auto_trade


def _make_bars(
    *,
    start: float = 100.0,
    step: float = 0.4,
    count: int = 50,
    base_volume: int = 100_000,
    recent_volume_multiplier: float = 1.0,
):
    bars = []
    for i in range(count):
        close = start + step * i
        open_price = close - (step * 0.4)
        bars.append(
            {
                "open": round(open_price, 2),
                "high": round(close * 1.004, 2),
                "low": round(close * 0.996, 2),
                "close": round(close, 2),
                "volume": int(base_volume * (recent_volume_multiplier if i >= count - 5 else 1.0)),
            }
        )
    return bars


def test_evaluate_buy_gate_rejects_bad_reward_risk():
    gate = evaluate_buy_gate(
        combined_score=82.0,
        ai_score=76.0,
        momentum_score=68.0,
        price_change_pct=1.1,
        technical_score=67.0,
        technical_regime="bullish",
        technical_rsi=61.0,
        relative_volume=1.1,
        resistance_room_pct=1.0,
        risk_reward_ratio=1.4,
        llm_enhanced=True,
    )

    assert gate["passed"] is False
    assert "risk_reward_too_low" in gate["reasons"]
    assert "resistance_too_close" in gate["reasons"]


def test_evaluate_buy_gate_allows_true_early_setup_with_lighter_confirmation():
    gate = evaluate_buy_gate(
        combined_score=68.0,
        ai_score=70.0,
        momentum_score=45.0,
        price_change_pct=0.6,
        technical_score=43.0,
        technical_regime="neutral",
        technical_rsi=76.0,
        relative_volume=0.95,
        resistance_room_pct=4.8,
        risk_reward_ratio=1.9,
        llm_enhanced=True,
        price=80.0,
        news_age_hours=0.4,
        entry_timing_score=64.0,
        entry_timing_state="early",
        price_vs_vwap_pct=0.55,
        session_range_position=0.58,
    )

    assert gate["passed"] is True
    assert gate["thresholds"]["combined_score_min"] == 68.0
    assert gate["thresholds"]["momentum_score_min"] == 44.0


def test_build_trade_plan_marks_aligned_setup_tradeable():
    bars = _make_bars(start=118.5, step=0.05, recent_volume_multiplier=1.6)
    plan = build_trade_plan(
        price=120.0,
        catalyst_score=84.0,
        ai_score=80.0,
        momentum_score=72.0,
        price_change_pct=0.8,
        llm_enhanced=True,
        technical_score=69.0,
        technical_regime="bullish",
        technical_rsi=58.0,
        support=117.0,
        resistance=126.0,
        relative_volume=1.35,
        bars=bars,
        buy_threshold=76.0,
    )

    assert plan["tradeable"] is True
    assert plan["action"] == "BUY"
    assert plan["risk_reward_ratio"] >= 1.8
    assert plan["size_multiplier"] >= 0.6
    assert plan["buy_gate"]["passed"] is True


def test_build_trade_plan_allows_fresh_catalyst_before_full_technical_confirmation():
    bars = _make_bars(start=99.8, step=0.03, recent_volume_multiplier=1.5)
    plan = build_trade_plan(
        price=101.0,
        catalyst_score=85.0,
        ai_score=82.0,
        momentum_score=49.0,
        price_change_pct=0.7,
        llm_enhanced=True,
        technical_score=48.0,
        technical_regime="neutral",
        technical_rsi=74.0,
        support=99.2,
        resistance=106.0,
        relative_volume=1.3,
        bars=bars,
        buy_threshold=72.0,
        news_age_hours=0.5,
    )

    assert plan["fresh_catalyst"] is True
    assert plan["tradeable"] is True
    assert plan["action"] == "BUY"
    assert plan["timing_state"] == "early"
    assert plan["buy_gate"]["passed"] is True


def test_build_trade_plan_blocks_overheated_countertrend_entry():
    bars = _make_bars(start=110.0, step=-0.35, recent_volume_multiplier=0.7)
    plan = build_trade_plan(
        price=96.0,
        catalyst_score=81.0,
        ai_score=78.0,
        momentum_score=60.0,
        price_change_pct=3.6,
        llm_enhanced=True,
        technical_score=42.0,
        technical_regime="bearish",
        technical_rsi=76.0,
        support=95.4,
        resistance=97.0,
        relative_volume=0.72,
        bars=bars,
        buy_threshold=76.0,
    )

    assert plan["tradeable"] is False
    assert plan["action"] == "WAIT"
    assert "bearish_regime" in plan["buy_gate"]["reasons"]
    assert "technical_score_below_threshold" in plan["buy_gate"]["reasons"]


def test_build_trade_plan_blocks_fresh_news_if_entry_is_already_stretched():
    bars = _make_bars(start=100.0, step=0.05, recent_volume_multiplier=1.4)
    plan = build_trade_plan(
        price=105.0,
        catalyst_score=86.0,
        ai_score=83.0,
        momentum_score=58.0,
        price_change_pct=2.3,
        llm_enhanced=True,
        technical_score=53.0,
        technical_regime="neutral",
        technical_rsi=74.0,
        support=101.4,
        resistance=105.8,
        relative_volume=1.2,
        bars=bars,
        buy_threshold=72.0,
        news_age_hours=0.4,
    )

    assert plan["fresh_catalyst"] is True
    assert plan["tradeable"] is False
    assert plan["timing_state"] in {"late", "extended"}
    assert any(
        reason in plan["buy_gate"]["reasons"]
        for reason in ["too_far_above_vwap", "near_session_high_chase", "score_below_threshold"]
    )


def test_build_trade_plan_blocks_stale_late_chase_even_with_ok_sentiment():
    bars = _make_bars(start=100.0, step=0.04, recent_volume_multiplier=1.1)
    plan = build_trade_plan(
        price=105.6,
        catalyst_score=80.0,
        ai_score=77.0,
        momentum_score=64.0,
        price_change_pct=3.1,
        llm_enhanced=True,
        technical_score=61.0,
        technical_regime="bullish",
        technical_rsi=71.0,
        support=101.5,
        resistance=106.3,
        relative_volume=1.05,
        bars=bars,
        buy_threshold=72.0,
        news_age_hours=8.0,
    )

    assert plan["tradeable"] is False
    assert plan["action"] == "WAIT"
    assert plan["timing_state"] in {"late", "extended"}
    assert any(
        reason in plan["buy_gate"]["reasons"]
        for reason in ["too_far_above_vwap", "near_session_high_chase", "score_below_threshold"]
    )


def test_should_execute_auto_trade_respects_gate_and_risk_reward():
    signal = {
        "action": "BUY",
        "combined_score": 84.0,
        "effective_score": 82.0,
        "risk_reward_ratio": 2.1,
        "buy_gate": {"passed": True, "reasons": []},
    }

    should_trade, reason = should_execute_auto_trade(signal, min_score=78.0)
    assert should_trade is True
    assert reason == "passed"

    signal["risk_reward_ratio"] = 1.49
    should_trade, reason = should_execute_auto_trade(signal, min_score=78.0)
    assert should_trade is False
    assert reason.startswith("risk_reward=")
