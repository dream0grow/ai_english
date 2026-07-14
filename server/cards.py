"""주제/롤플레이/슬랭 카드 (3단계).

카드를 고르면 그 시나리오가 시스템 프롬프트에 주입되어 새 대화가 시작된다.
child_ok=False 카드는 아이 프로필에게 보이지 않는다 (콘텐츠 필터의 UI 레이어).
scenario는 Emma에게 주는 영어 지시문 — 학습자에게 직접 보이지 않는다.
"""

CARDS = [
    # ── 주제 카드 ──────────────────────────────────────────────
    {"id": "t_food", "kind": "topic", "emoji": "🍕", "title": "음식 이야기",
     "desc": "좋아하는 음식, 오늘 먹은 것", "child_ok": True,
     "scenario": "Today's topic is food. Chat about favorite foods, what the learner "
                 "ate today, cooking, snacks. Start by sharing a food you love."},
    {"id": "t_hobby", "kind": "topic", "emoji": "⚽", "title": "취미와 놀이",
     "desc": "취미, 게임, 운동, 주말에 하는 것", "child_ok": True,
     "scenario": "Today's topic is hobbies and free time — games, sports, weekend fun. "
                 "Start by sharing one of your hobbies."},
    {"id": "t_school", "kind": "topic", "emoji": "🏫", "title": "학교 생활",
     "desc": "학교, 친구, 선생님, 급식", "child_ok": True,
     "scenario": "Today's topic is school life — classes, friends, teachers, lunch. "
                 "Ask about the learner's day at school."},
    {"id": "t_travel", "kind": "topic", "emoji": "✈️", "title": "여행 이야기",
     "desc": "가보고 싶은 곳, 여행 경험", "child_ok": True,
     "scenario": "Today's topic is travel — places visited, dream destinations. "
                 "Share a place you'd love to visit."},
    {"id": "t_work", "kind": "topic", "emoji": "💼", "title": "일과 커리어",
     "desc": "직장 생활, 업무 영어", "child_ok": False,
     "scenario": "Today's topic is work life — the learner's job, colleagues, "
                 "workplace situations. Practice natural office small talk."},
    {"id": "t_news", "kind": "topic", "emoji": "📱", "title": "요즘 사는 얘기",
     "desc": "일상, 요즘 관심사, 스몰토크", "child_ok": False,
     "scenario": "Casual adult small talk — daily life, what's been keeping them busy, "
                 "current interests. Keep it light and natural."},

    # ── 롤플레이 카드 ─────────────────────────────────────────
    {"id": "r_restaurant", "kind": "roleplay", "emoji": "🍔", "title": "식당에서 주문하기",
     "desc": "Emma가 점원, 내가 손님", "child_ok": True,
     "scenario": "ROLEPLAY: You are a friendly server at a casual American restaurant, "
                 "the learner is a customer. Greet them, take their order, make small "
                 "talk. Stay in character but keep recasting corrections."},
    {"id": "r_shopping", "kind": "roleplay", "emoji": "🛍️", "title": "가게에서 쇼핑하기",
     "desc": "Emma가 점원, 내가 쇼핑객", "child_ok": True,
     "scenario": "ROLEPLAY: You are a shop assistant, the learner is shopping for "
                 "something (let them decide what). Help them find it, discuss size, "
                 "color, price."},
    {"id": "r_friend", "kind": "roleplay", "emoji": "👋", "title": "새 친구 사귀기",
     "desc": "처음 만난 친구와 인사하고 친해지기", "child_ok": True,
     "scenario": "ROLEPLAY: You are a new kid who just moved to town and meets the "
                 "learner for the first time. Introduce yourselves, find things you "
                 "both like."},
    {"id": "r_airport", "kind": "roleplay", "emoji": "🛃", "title": "공항 입국 심사",
     "desc": "Emma가 심사관, 내가 여행객", "child_ok": False,
     "scenario": "ROLEPLAY: You are an immigration officer at a US airport, the learner "
                 "is a traveler. Ask standard questions (purpose, length of stay, "
                 "where staying). Be professional but not scary."},
    {"id": "r_hotel", "kind": "roleplay", "emoji": "🏨", "title": "호텔 체크인",
     "desc": "Emma가 프런트 직원, 내가 투숙객", "child_ok": False,
     "scenario": "ROLEPLAY: You are a hotel front-desk clerk, the learner is checking "
                 "in. Handle the reservation, room requests, hotel info questions."},

    # ── 오늘의 슬랭/표현 모드 ─────────────────────────────────
    {"id": "s_kids", "kind": "slang", "emoji": "✨", "title": "오늘의 꿀표현",
     "desc": "또래 아이들이 진짜 쓰는 쉬운 표현 배우기", "child_ok": True,
     "scenario": "EXPRESSION MODE: This session, teach 2-3 fun, kid-safe everyday "
                 "expressions American kids actually use (e.g. \"no way!\", \"piece of "
                 "cake\", \"hang out\"). Introduce ONE at a time through conversation, "
                 "show what it means by using it, and get the learner to try it. "
                 "Report each in <taught>."},
    {"id": "s_adult", "kind": "slang", "emoji": "🔥", "title": "오늘의 슬랭",
     "desc": "미국인이 실제로 쓰는 슬랭·구어체", "child_ok": False,
     "scenario": "EXPRESSION MODE: This session, teach 2-3 current, natural American "
                 "colloquial expressions or slang adults actually use in daily life. "
                 "Introduce ONE at a time through conversation, show the meaning by "
                 "using it, get the learner to try it. Report each in <taught>."},
]

_BY_ID = {c["id"]: c for c in CARDS}


def list_cards(profile_kind: str | None) -> list[dict]:
    """프로필 종류에 맞는 카드 목록 (아이에겐 child_ok만)."""
    cards = CARDS if profile_kind != "child" else [c for c in CARDS if c["child_ok"]]
    return [{k: v for k, v in c.items() if k != "scenario"} for c in cards]


def get_card(card_id: str, profile_kind: str | None = None) -> dict | None:
    """카드 조회 — 아이 프로필이 성인 카드를 (URL 조작 등으로) 요청하면 거부."""
    card = _BY_ID.get(card_id)
    if card and profile_kind == "child" and not card["child_ok"]:
        return None
    return card
