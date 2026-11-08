"""Synthetic-only scoped policy; no actors, consent, outcomes or release certification."""

from pathlib import Path

from girlframe.engine.m3_policy import Approval, Rulings
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.onboarding import OnboardingStore


def configure_m3_fixture(store: OnboardingStore) -> Registry:
    registry = Registry.model_validate_json(
        (Path(__file__).resolve().parents[2] / "rules/registry.json").read_text()
    )
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": Approval(
                registry_sha256=digest(registry),
                scope="rules_subset",
                subsystems=frozenset({"missions", "discipline"}),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
            "owner_m3_rulings": Rulings(
                provenance="owner_approved_campaign_ruling",
                ace_bonus="current_ace",
                standard_unpriced_cost=1,
                extra_repairs="handler_quote",
                repair_shortage_timing="next_dispatch_from_off_duty",
                supply_observation="both_off_duty_routes",
                scientific_observation_selection="handler_represents_demand",
                scientific_observation_overlap="one_roll_distinct_causes",
                director_adjudicator="explicit_cast_director",
                actor_tag_disputes="scene_unanimous_discussion",
                comforts_qualification="ordinary_go_off_duty_only",
                comforts_stacking="one_opportunity_per_paid_purchase",
                comforts_decline="consume_without_refund",
                reprogramming_fallback="owner_selects_ordinary_slot",
                reprogramming_reset_marks="baseline_preserve_protected_locks",
                identity_duplicate_labels="distinct_ids",
                frame_reward_eligibility="roll_event_except_doctor_start",
                frame_reward_observation="both_routes",
                queen_reward_dog="self_only",
                frame_prisoner_reward_repeat="new_delivery_per_character",
                observation_choice_overlap="distinct_shared_list",
                observation_reprogram_owner="affected_player",
                observation_populace_controller="handler",
                director_overlap="one_presence_episode",
                director_exit_resources="retain_without_recovery",
                director_controller="separate_from_handler",
                punishment_details="inflictor_selects",
                regulation_breach_review="informed_handler",
                failure_dog_overlap="one_punishment_both_causes",
                sedation_small_set="mark_all_remaining",
                princess_ace_check="after_promotion",
                compulsory_frame_package="handler_defined",
                replacement_frame_repeat="different_playbook",
                compulsory_frame_charge="free",
                doctor_credit_recipients="current_pilots",
                sedation_duration="current_off_duty_period",
                sedation_identity_replacement="retain_slot_lock",
                strain_repeat_timing="next_period_start",
                strain_cascade_count="prior_occurrences_same_track",
                doctor_start_order="credit_before_budget",
                world_grid_steps="eight_neighbors",
                gorgon_class_change="preserve_body",
                gorgon_reappearance="preserve_old_assets_new_core_plan",
                gorgon_destroyed_core_guard="satisfies_asset_condition",
                benevolent_defense="defensive_contest_only",
                refusal_bonus_overlap="stack_on_next_refusal",
            ),
        }
    )
    return registry
