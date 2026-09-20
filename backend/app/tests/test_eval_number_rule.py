"""The eval gate's invented-numbers rule (plan §5.6): the frozen unit cases for criteria_v1."""

from __future__ import annotations

from app.services.assistant.eval import number_rule as nr


def _check(answer, tools=None, **kw):
    return nr.check_numbers(answer, tool_results=tools or [], **kw)


def test_balance_matches_tool_value_in_any_formatting():
    assert _check("Your balance is $1,250.50.", [{"balance": "1250.50"}]).ok
    assert _check("Your balance is $1250.5.", [{"balance": "1250.50"}]).ok
    assert _check("Your balance is $1,250.", [{"balance": "1250.00"}]).ok


def test_balance_not_in_tools_fails():
    r = _check("Your balance is $1,300.", [{"balance": "1250.50"}])
    assert not r.ok and r.violations[0].number == "1300"


def test_derived_sum_passes():
    assert _check("Total $1,050 (1,000 + 50 fee).", [{"subtotal": 1000, "fee": 50}]).ok


def test_list_markers_and_small_counts_are_exempt():
    assert _check("3 steps:\n1. Sign in\n2. Verify\n3. Invest", []).ok
    assert _check("- 1) first\n- 2) second", []).ok


def test_percentage_without_source_fails_and_arabic_normalises():
    assert not _check("The fee is 2.5%.", []).ok
    assert _check("الرسوم ٢٫٥٪ من المبلغ", [{"platform_fee_pct": "2.5"}]).ok
    assert _check("الرصيد ١٬٢٥٠٫٥٠ دولار", [{"balance": "1250.50"}]).ok


def test_installment_months_from_tool_mapping():
    tools = [
        {"installment": {"down_pct_by_months": {"6": "30", "12": "25", "18": "20", "24": "15"}}}
    ]
    assert _check("You can pay over 6, 12, 18 or 24 months.", tools).ok


def test_date_expansion():
    tools = [{"as_of": "2026-09-16T10:30:00Z"}]
    assert _check("as of 16/09/2026", tools).ok
    assert _check("as of 16 September 2026", tools).ok
    assert _check("as of 17/09/2026", tools).ok is False  # a different day is invented


def test_unit_word_blocks_small_int_exemption():
    assert _check("you own 5 units", [{"holdings": [{"units": 5}]}]).ok
    r = _check("you own 5 units", [{"holdings": [{"units": 4}]}])
    assert not r.ok and r.violations[0].number == "5"
    assert _check("you have 5 open tickets", []).ok  # no unit word -> small count allowed


def test_ticket_numbers_and_ids_from_tools_pass():
    assert _check("Your ticket CPX-001007 is open.", [{"ticket_no": "CPX-001007"}]).ok
    assert not _check("Your ticket CPX-001008 is open.", [{"ticket_no": "CPX-001007"}]).ok


def test_fail_closed_on_too_many_numbers():
    tools = [{"rows": [{"v": i} for i in range(500)]}]
    r = _check("Anything 12345", tools)
    assert r.flags == ["too_many_numbers"] and r.violations == []


def test_user_typed_number_may_be_echoed():
    assert _check("You want to invest 5000; the minimum is lower.", user_text="invest 5000").ok
    assert not _check("You want to invest 6000.", user_text="invest 5000").ok


def test_schedule_row_sums_and_percent_of():
    tools = [{"schedule": [{"amount": "250.00"}, {"amount": "250.00"}, {"amount": "300.00"}]}]
    assert _check("The first two instalments add up to $500.00.", tools).ok
    assert _check("All three add up to $800.", tools).ok
    assert _check("2.5% of 1000 is 25.", [{"fee_pct": "2.5", "amount": "1000"}]).ok
    assert _check("Net of a 2.5% fee, 1000 becomes 975.", [{"fee_pct": "2.5", "amount": "1000"}]).ok


def test_kb_and_platform_context_numbers_are_allowed():
    kb = "Verification usually takes 24 hours."
    assert _check("Verification usually takes 24 hours.", kb_text=kb).ok
    # 48 would pass as 24+24 (derived); 36 has no arithmetic path from {24}
    assert not _check("Verification usually takes 36 hours.", kb_text=kb).ok
    assert _check("Today is 2026-09-20.", platform_context="today: 2026-09-20 (UTC)").ok
