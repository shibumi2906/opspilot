from opspilot.agent.state import merge_by_id


def test_replay_upserts_and_is_associative():
    left = {"ev1": {"fact": "401"}}
    middle = {"ev2": {"fact": "expired"}}
    right = {"ev1": {"fact": "401"}}
    assert merge_by_id(left, left) == left
    assert merge_by_id(merge_by_id(left, middle), right) == merge_by_id(
        left, merge_by_id(middle, right)
    )
    assert len(merge_by_id(merge_by_id(left, middle), right)) == 2
    assert left == {"ev1": {"fact": "401"}}
