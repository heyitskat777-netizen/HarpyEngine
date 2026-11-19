"""M3 rolled Plays routed through the existing owned roll/Tag/chat-lock protocol."""

ROLL_IDS = ("go_off_duty", "void_observation")
FIXED_IDS = ("consume_feral",)
HEAT_IDS = (
    "all_out_assault",
    "go_for_the_core",
    "put_someone_beneath_you",
    "dive_deep",
    "enforcement_initiative",
    "mockingbird_person",
    "mockingbird_sex",
    "snoop",
    "brutalize",
    "alpha_sex",
    "am_scrutinized",
    "am_just_code",
    "nanobot_injection",
    "doctor_support",
    "dose_up",
    "princess_sex",
    "stim_sex",
    "old_dog_new_pups",
    "oldgen_sex",
    "casualty_sex",
    "vatgrown_sex",
    "newgirl_sex",
    "easy_target",
    "unassuming_doll",
    "prince_performer",
    "consume_eat",
    "ankou_processor",
    "changeling_blank_slate",
    "changeling_body_of_clay",
    "red_queen_consult",
    "red_queen_panopticon",
    "red_queen_memory",
    "wyvern_explore",
    "wyvern_rouse",
    "wyvern_wraith",
    "wyvern_protector",
    "bonded_side",
    "bonded_sex",
)
ASSET_IDS = ("defeat",)

JANUS_ROLL_IDS = ("living_battery", "pandora_birth")

GIRL_ROLL_RULES = {
    "mockingbird_person": "girl.mockingbird.bad-at-being-a-person",
    "mockingbird_sex": "girl.mockingbird.sex-play",
    "brutalize": "girl.alpha.brutalize",
    "alpha_sex": "girl.alpha.sex-play",
    "am_scrutinized": "girl.am.scrutinized",
    "am_just_code": "girl.am.just-code",
    "dose_up": "girl.stim-blissed.dose-up",
    "princess_sex": "girl.princess.sex-play",
    "stim_sex": "girl.stim-blissed.sex-play",
    "old_dog_new_pups": "girl.oldgen.old-dog-new-pups",
    "oldgen_sex": "girl.oldgen.sex-play",
    "casualty_sex": "girl.casualty.sex-play",
    "vatgrown_sex": "girl.vatgrown.sex-play",
    "newgirl_sex": "girl.newgirl.sex-play",
    "easy_target": "girl.newgirl.easy-target",
    "unassuming_doll": "girl.vatgrown.unassuming-doll",
    "bonded_side": "girl.bonded.always-by-her-side",
    "bonded_sex": "girl.bonded.sex-play",
}

# Base Frame rolls whose entitlement is the named installed Frame, without buying an ability.
FRAME_ROLL_BOOKS = {"nanobot_injection": "DOCTORDOCTOR MK. II"}
