"""Synthetic demo data (fictional agents Atlas/Birch/Cobalt, fictional company 'Example Bakery Co')."""

from __future__ import annotations

from .graph import TeamGraph, connect


def seed(tg: TeamGraph) -> None:
    tg.setup()
    for n, r in [("Atlas", "planner"), ("Birch", "writer"), ("Cobalt", "reviewer")]:
        tg.agent(n, r)
    tg.source("src-ftc", "FTC: Advertising FAQs for small business", "https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business")
    tg.source("src-w3c", "W3C WCAG 2.2 overview", "https://www.w3.org/WAI/standards-guidelines/wcag/")
    tg.procedure("Publish newsletter", "newsletter", ["draft copy", "check claims against sources", "accessibility check", "schedule send"])
    tg.task("T1", "Spring newsletter for Example Bakery Co", "Atlas")
    tg.fact("Example Bakery Co", "prefers tone", "warm and short", "")
    tg.fact("Newsletter", "must follow", "WCAG 2.2 alt text", "src-w3c")
    d1 = tg.decide("Atlas", "use 'up to 20% off' wording", "absolute discount claims need substantiation", ["src-ftc"], "T1")
    tg.decide("Cobalt", "drop the discount line entirely", "no price list on file to substantiate it", ["src-ftc"], "T1", supersedes=d1)
    tg.episode("Atlas", "draft copy written for spring issue", "s1", "T1")
    tg.handoff("Atlas", "Birch", "T1", "Draft is in; please check claims before Friday.")


if __name__ == "__main__":
    seed(connect())
    print("seeded")  # noqa: T201
