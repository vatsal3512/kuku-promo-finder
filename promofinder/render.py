from .features import beats_in, clip_time
from .models import Candidate, Show

RENDER_VERSION = "render-v1"


def render_clip(candidate: Candidate, show: Show) -> str:
    rows = []
    current = 0
    for seg_index, beat in beats_in(candidate, show):
        if seg_index != current:
            rows.append("--- CUT ---")
            current = seg_index
        t = clip_time(candidate, seg_index, beat.start)
        stamp = f"[{int(t // 60)}:{int(t % 60):02d}]"
        if beat.kind == "DIALOGUE":
            tone = f" ({', '.join(beat.delivery[:2])})" if beat.delivery else ""
            rows.append(f'{stamp} {beat.speaker}{tone}: "{beat.text}"')
        elif beat.kind == "ACTION":
            rows.append(f"{stamp} VISUAL: {beat.text}")
        elif beat.kind == "SFX":
            rows.append(f"{stamp} SOUND: {beat.text}")
    return "\n".join(rows)
