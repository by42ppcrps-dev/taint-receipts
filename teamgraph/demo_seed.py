"""Synthetic, redacted story: a 3-bot content team; reach figures are made-up estimates for a fictional product 'Acme Notes'."""

from __future__ import annotations

from .taint import Taint


def seed(t: Taint) -> None:
    t.wipe()
    for n, r in [("Scout", "researcher"), ("Quill", "writer"), ("Reel", "video"), ("Lens", "QA")]:
        t.agent(n, r)
    t.source("spec", "Acme Notes spec sheet (synthetic)", "Battery life: 3.5 hours of recording. Price: $29 per month. Supports 12 languages.")
    t.source("pricing", "Pricing page v2 (synthetic)", "Starter plan $29/month. Pro plan $59/month.")
    c_batt = t.claim("Scout", "Records for 35 hours on one charge", "35", ["spec"], "Battery life: 3.5 hours", id="c-battery")
    c_price = t.claim("Scout", "Starts at $29/month", "29", ["pricing"], "Starter plan $29/month", id="c-price")
    c_lang = t.claim("Scout", "Supports 12 languages", "12", ["spec"], "Supports 12 languages", id="c-lang")
    c_users = t.claim("Quill", "Trusted by 10000 teams", "10000", [], id="c-users")
    t.artifact("Quill", "brief", "brief", "Launch brief", [c_batt, c_price, c_lang], url=None, reach=0)
    t.artifact("Quill", "blog", "blog", "Launch blog post", ["brief", c_users], url="https://acme.example/blog/launch", reach=4200)
    t.artifact("Quill", "landing", "page", "Landing page hero", ["brief"], url="https://acme.example/", reach=18500)
    t.artifact("Quill", "og", "image", "Link preview image", ["landing"], url="https://acme.example/og.png", reach=9300)
    t.artifact("Reel", "script", "script", "30s Short script", ["blog"], url=None, reach=0)
    t.artifact("Reel", "short", "video", "YouTube Short", ["script"], url="https://youtube.example/shorts/acme", reach=27400)
    t.artifact("Reel", "captions", "captions", "Short captions", ["script"], url=None, reach=0)
    t.artifact("Quill", "x1", "post", "X launch post", ["blog"], url="https://x.example/acme/1", reach=12100)
    t.artifact("Quill", "x2", "post", "X reply thread", ["x1"], url="https://x.example/acme/2", reach=1800)
    t.artifact("Quill", "email", "email", "Waitlist email", ["landing", c_price], url=None, reach=6400)
    t.artifact("Quill", "faq", "page", "FAQ page", [c_lang, c_price], url="https://acme.example/faq", reach=2100)
