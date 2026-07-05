#!/usr/bin/env python3
"""Generate the Basil trust-boundary excalidraw diagram (clean, deterministic).

Companion to the "Threat model" page. Shows the single-host trust boundary:
what is trusted (green), what is attested but not trusted (amber), and what is
out of scope / not defended (red), plus the flows that cross the socket.
"""

import json, sys

elements = []
_seed = [2000]


def nxt():
    _seed[0] += 7
    return _seed[0]


def rect(id, x, y, w, h, stroke, bg, sw=2, round=True, style="solid"):
    elements.append(
        {
            "id": id,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": stroke,
            "backgroundColor": bg,
            "fillStyle": "solid",
            "strokeWidth": sw,
            "strokeStyle": style,
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 3} if round else None,
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
        }
    )


def text(id, x, y, w, h, s, color, size=16, align="left"):
    lines = s.count("\n") + 1
    elements.append(
        {
            "id": id,
            "type": "text",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "text": s,
            "fontSize": size,
            "fontFamily": 2,
            "textAlign": align,
            "verticalAlign": "top",
            "baseline": int(size * 0.9 * lines),
            "containerId": None,
            "originalText": s,
            "lineHeight": 1.25,
        }
    )


def arrow(id, x, y, dx, dy, color="#5b6670", style="solid"):
    elements.append(
        {
            "id": id,
            "type": "arrow",
            "x": x,
            "y": y,
            "width": abs(dx),
            "height": abs(dy),
            "angle": 0,
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": style,
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 2},
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "points": [[0, 0], [dx, dy]],
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
        }
    )


GREEN = "#1f7a4d"
DGREEN = "#13603a"
INK = "#1c2420"
MUTE = "#44504a"
GREY = "#5b6670"
AMBER = "#b7791f"
RED = "#b23b3b"

TRUST_BG = "#eef7f1"
AMBER_BG = "#fdf6ec"
RED_BG = "#fbeceb"
NEUT_BG = "#f1f3f5"

# --- Title ---
text("title", 360, 32, 520, 30, "Basil trust boundaries (one host)", DGREEN, 22, "center")

# --- Host trust boundary (dashed) ---
rect("host", 40, 84, 864, 616, INK, "transparent", sw=2, style="dashed")
text(
    "host_t",
    60,
    94,
    760,
    20,
    "Trust boundary: the host   ·   Basil's trusted computing base",
    MUTE,
    15,
)

# --- Workload (attested, not trusted) ---
rect("wl", 84, 150, 252, 128, AMBER, AMBER_BG, sw=2)
text(
    "wl_t",
    100,
    162,
    224,
    108,
    "Workload / app  (or basil CLI)\n\nattested, not trusted:\nproves only its uid;\nholds no backend token",
    INK,
    13,
)

# --- Sealed bundle (trusted) ---
rect("bundle", 84, 312, 252, 122, GREEN, TRUST_BG, sw=2)
text(
    "bundle_t",
    100,
    324,
    224,
    102,
    "Sealed bundle  ·  trusted\n\nthe one secret at rest;\nan unlock slot opens it at boot\n(passphrase · age/YubiKey · BIP39)",
    INK,
    12,
)

# --- Basil broker (trusted, prominent) ---
rect("basil", 472, 150, 360, 264, GREEN, "#ffffff", sw=3)
text("basil_t", 492, 164, 320, 26, "Basil broker  ·  trusted", DGREEN, 20)
text(
    "basil_b",
    492,
    202,
    320,
    200,
    "1 · attest the caller (kernel)\n2 · check policy (default-deny)\n3 · broker the operation, in place\n\nowns AEAD nonces\naudits every decision\nhands out no backend credential",
    INK,
    14,
)

# --- Audit log ---
rect("audit", 472, 444, 252, 58, GREY, NEUT_BG, sw=2)
text("audit_t", 486, 456, 224, 34, "Audit log — every decision recorded", INK, 13)

# --- Kernel (trust root) ---
rect("kernel", 84, 566, 748, 80, GREEN, TRUST_BG, sw=2)
text(
    "kernel_t",
    100,
    580,
    720,
    56,
    "Kernel — trust root\nSO_PEERCRED: uid · gid · pid   ·   a compromised kernel breaks attestation",
    INK,
    13,
)

# --- In-place transit backend (separate trust domain, outside the host TCB) ---
rect("be", 968, 132, 244, 158, GREEN, TRUST_BG, sw=2)
text(
    "be_t",
    984,
    144,
    216,
    134,
    "In-place transit backend\n(OpenBao · Vault ·\n AWS KMS · GCP KMS)\n\nkeys live here and stay here\n\ntrusted for custody\n(separate trust domain)",
    INK,
    13,
)

# --- Store-only backend (materialize-to-use, separate trust domain) ---
rect("be2", 968, 306, 244, 150, GREEN, TRUST_BG, sw=2)
text(
    "be2_t",
    984,
    318,
    216,
    126,
    "Store-only backend\n(db-keystore · 1Password)\n\nmaterialize-to-use:\nkey briefly in-process,\nthen wiped\n\ntrusted for custody",
    INK,
    13,
)

# --- Out of scope (not defended) ---
rect("oos", 968, 472, 244, 204, RED, RED_BG, sw=2, style="dashed")
text(
    "oos_t",
    984,
    484,
    216,
    180,
    "Not defended (out of scope)\n\n· host root / kernel compromise\n· backend compromise\n· a workload abusing what\n  it is allowed to do\n· a bad policy you authored\n· supply chain · side channels",
    INK,
    12,
)

# --- Flows ---
arrow("a_wl", 336, 216, 136, 14)  # workload -> basil (over the socket)
arrow("a_be", 832, 210, 136, 8)  # basil -> in-place backend (crosses the host boundary)
arrow("a_be2", 832, 372, 136, 8)  # basil -> store-only backend (crosses the host boundary)
arrow("a_au", 598, 414, 0, 30)  # basil -> audit
arrow("a_k", 762, 566, 0, -152, color=GREY, style="dashed")  # kernel vouches -> basil

# --- Flow labels ---
text("l_sock", 330, 184, 150, 18, "local socket · gRPC", GREY, 12, "center")
text("l_op", 812, 168, 176, 34, "operation, in place\nprivate key never crosses", GREY, 12, "center")
text("l_mat", 812, 344, 176, 20, "key materialized for one op", GREY, 12, "center")
text("l_vouch", 772, 476, 128, 18, "vouches for caller", GREY, 12)

# --- Legend ---
rect("lg1", 84, 724, 20, 20, GREEN, TRUST_BG, sw=2)
text("lg1_t", 112, 726, 90, 18, "trusted", MUTE, 13)
rect("lg2", 232, 724, 20, 20, AMBER, AMBER_BG, sw=2)
text("lg2_t", 260, 726, 190, 18, "attested, not trusted", MUTE, 13)
rect("lg3", 452, 724, 20, 20, RED, RED_BG, sw=2, style="dashed")
text("lg3_t", 480, 726, 260, 18, "out of scope (not defended)", MUTE, 13)

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
    "files": {},
}
out = sys.argv[1] if len(sys.argv) > 1 else "trust-boundaries.excalidraw"
with open(out, "w") as f:
    json.dump(doc, f, indent=2)
print("wrote", out, "with", len(elements), "elements")
