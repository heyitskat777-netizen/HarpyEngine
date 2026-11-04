import pytest

from girlframe.engine.m3_choices import Context, off_duty_modifier, plan


@pytest.mark.parametrize(
    "play",
    [
        "put_someone_beneath_you",
        "all_out_assault",
        "go_for_the_core",
        "dive_deep",
        "go_off_duty",
        "void_observation",
        "defeat",
    ],
)
@pytest.mark.parametrize("total", [5, 9, 12])
def test_each_shared_play_tier_has_an_owned_exact_contract(play, total):
    result = plan(play, Context(total=total))
    assert result.mechanical_application_required
    assert result.groups or result.fixed_followups
    for group in result.groups:
        group.select(group.owner, group.options[: group.minimum])
        with pytest.raises(ValueError):
            group.select(
                "table" if group.owner != "table" else "actor", group.options[: group.minimum]
            )
        with pytest.raises(ValueError):
            group.select(group.owner, ("not_a_printed_option",))
        if group.minimum > 0:
            with pytest.raises(ValueError):
                group.select(group.owner, ())


def test_put_beneath_high_requires_one_from_each_list_and_punishment_authority():
    result = plan("put_someone_beneath_you", Context(total=12))
    assert len(result.groups) == 2
    assert all(x.minimum == x.maximum == 1 for x in result.groups)
    assert "punish" not in result.groups[1].options
    assert (
        "punish"
        in plan("put_someone_beneath_you", Context(total=12, can_punish_target=True))
        .groups[1]
        .options
    )
    low = plan("put_someone_beneath_you", Context(total=5))
    assert low.groups[0].owner == "target" and "damage_actor_asset" in low.groups[0].options


def test_assault_handler_high_and_low_followups_cannot_be_omitted():
    result = plan("all_out_assault", Context(total=12))
    assert result.groups[0].owner == "handler"
    assert (result.groups[0].minimum, result.groups[0].maximum) == (1, 2)
    assert plan("all_out_assault", Context(total=5)).fixed_followups == (
        "enemy_damages_actor_asset",
        "handler_play",
    )


def test_core_exposure_and_npc_explosion_are_distinct():
    with pytest.raises(ValueError):
        plan("go_for_the_core", Context(total=9, target_is_gorgon_or_piloting=True))
    result = plan("go_for_the_core", Context(total=12, target_is_npc=True))
    assert (
        not result.groups
        and "every_other_character_damages_asset_or_dies" in result.fixed_followups
    )
    assert plan("go_for_the_core", Context(total=12)).groups[0].owner == "target"


def test_dive_high_has_both_owners_then_status_loss_and_low_only_handler():
    result = plan("dive_deep", Context(total=12))
    assert [x.owner for x in result.groups] == ["actor", "handler"]
    assert result.after_choices == ("handler_detects_spike_lower_actor_status",)
    assert plan("dive_deep", Context(total=5)).groups[0].owner == "handler"


def test_off_duty_harsh_scene_is_required_and_status_modifiers_are_not_heat():
    assert [off_duty_modifier(x) for x in ("Dog", "Wings", "Ace")] == [0, 2, 4]
    low = plan("go_off_duty", Context(total=5))
    assert low.groups[0].minimum == 1 and "punishments_must_happen_on_screen" in low.fixed_followups
    assert "unmark_one_identity" in low.after_choices
    assert plan("go_off_duty", Context(total=9)).groups[0].minimum == 0


def test_observation_choice_counts_and_suspicion_extension():
    high = plan("void_observation", Context(total=12, hide_void_suspected=True))
    assert [(x.owner, x.minimum, x.maximum) for x in high.groups] == [
        ("actor", 1, 1),
        ("handler", 2, 2),
    ]
    assert all("reprogram" in x.options for x in high.groups)
    assert "reprogram" not in plan("void_observation", Context(total=12)).groups[0].options
    assert len(plan("void_observation", Context(total=5)).groups) == 1


def test_defeat_low_one_or_two_and_high_two_are_exact():
    low = plan("defeat", Context(total=5)).groups[0]
    assert (low.minimum, low.maximum) == (1, 2)
    high = plan("defeat", Context(total=12))
    assert (high.groups[0].minimum, high.groups[0].maximum) == (2, 2)
    assert high.fixed_followups == ("handler_or_agents_rescue",)
