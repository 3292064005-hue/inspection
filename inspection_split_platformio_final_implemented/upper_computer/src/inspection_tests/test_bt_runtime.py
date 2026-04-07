from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def test_bt_sequence_and_selector_produce_expected_actions():
    tree = Selector(
        'root',
        Sequence(
            'healthy_path',
            Condition('healthy', lambda ctx: bool(ctx['healthy'])),
            Action('resume', lambda _ctx: [{'action': 'resume'}]),
        ),
        Action('pause', lambda _ctx: [{'action': 'pause'}]),
    )
    assert tree.evaluate({'healthy': True}).actions == [{'action': 'resume'}]
    assert tree.evaluate({'healthy': False}).actions == [{'action': 'pause'}]
