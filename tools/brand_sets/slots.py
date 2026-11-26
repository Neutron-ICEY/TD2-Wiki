SLOT_LABELS = {
    "mask": "面具", "backpack": "背包", "chest": "胸甲",
    "gloves": "手套", "holster": "枪套", "kneepads": "护膝",
}
SLOTS = tuple(SLOT_LABELS)
CARD_ORDER = ("mask", "backpack", "chest", "gloves", "holster", "kneepads")


def gear_anchor(slot):
    if slot not in SLOT_LABELS:
        raise ValueError("装备部位必须使用六个 canonical ID")
    return "gear-" + slot
