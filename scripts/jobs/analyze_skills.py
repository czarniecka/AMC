"""Compare skill scope in requirements before and after 2023 (exploratory, small sample)."""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.jobs.analysis import (  # noqa: E402
    AdFlags,
    Codebook,
    bootstrap_ci,
    fisher_exact,
    flag_ad,
    holm,
    institution_group,
    mean,
    period_of,
    permutation_test,
)
from amc.jobs.storage import JobStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def esco_skills_per_ad(path: Path, codebook: Codebook, threshold: float):
    """Distinct ESCO skills and skill groups per ad from accepted top-1 matches.

    Fragments of formal lines (education, experience, ...) are skipped, as in the codebook
    scope measures. A match is accepted when its score reaches `threshold`.
    """
    skills, groups = defaultdict(set), defaultdict(set)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["rank"] != "1" or float(row["score"]) < threshold:
                continue
            if codebook.formal.search(row["line"]):
                continue
            ad_id = int(row["ad_id"])
            skills[ad_id].add(row["uri"])
            groups[ad_id].add(".".join(row["group_code"].split(".")[:2]))
    return skills, groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/jobs")
    parser.add_argument("--codebook", type=Path, default=ROOT / "config/jobs/skill_codebook.json")
    parser.add_argument(
        "--esco-matches",
        type=Path,
        help="esco_matches.csv (default: <data>/analysis/esco_matches.csv if it exists)",
    )
    parser.add_argument(
        "--esco-threshold",
        type=float,
        default=0.736,
        help="minimum top-1 similarity of an accepted ESCO match (from `calibrate`)",
    )
    parser.add_argument("--seed", type=int, default=1)
    options = parser.parse_args(argv)
    codebook = Codebook.load(options.codebook)
    store = JobStore(options.data)
    try:
        windows = {item.ad_id: item.window for item in store.sample}
        ads = [
            AdFlags(
                ad.ad_id,
                windows[ad.ad_id],
                period_of(ad.published_at),
                institution_group(ad.institution, ad.unit),
                *flag_ad(
                    codebook,
                    store.texts[ad.ad_id].requirements_required,
                    store.texts[ad.ad_id].requirements_optional,
                ),
            )
            for ad in sorted(store.ads.values(), key=lambda a: a.ad_id)
        ]
    finally:
        store.close()
    out = options.data / "analysis"
    out.mkdir(exist_ok=True)
    matches_path = options.esco_matches or out / "esco_matches.csv"
    esco = {}
    if matches_path.exists():
        esco_skills, esco_groups = esco_skills_per_ad(matches_path, codebook, options.esco_threshold)
        esco = {
            "distinct ESCO skills": lambda a: len(esco_skills[a.ad_id]),
            "distinct ESCO skill groups": lambda a: len(esco_groups[a.ad_id]),
        }
    else:
        print(f"No ESCO matches at {matches_path}; ESCO measures skipped.")
    names = list(codebook.skills)
    write(
        out / "skill_flags.csv",
        ["ad_id", "window", "period", "group", "n_items", "n_categories", *names, *esco],
        [
            [a.ad_id, a.window, a.period, a.group, a.n_items, len(a.categories)]
            + [int(n in a.categories) for n in names]
            + [getter(a) for getter in esco.values()]
            for a in ads
        ],
    )
    pre = [a for a in ads if a.period == "pre"]
    post = [a for a in ads if a.period == "post"]
    print(f"Ads: {len(ads)} (pre-2023: {len(pre)}, 2023 onward: {len(post)})")
    composition = Counter((a.period, a.group) for a in ads)
    print("\nComposition (pre/post):")
    for group in sorted({a.group for a in ads}):
        print(f"  {group:18} {composition[('pre', group)]:3} / {composition[('post', group)]:3}")

    labels = [a.period for a in ads]
    strata = [a.group for a in ads]
    print("\nScope measures, mean pre -> post [95% bootstrap CI of difference], permutation p")
    print("(unstratified p / p stratified by institution group)")
    scope_rows = []
    for label, getter in (
        ("distinct skill categories", lambda a: len(a.categories)),
        ("substantive requirement lines", lambda a: a.n_items),
        *esco.items(),
    ):
        values = [getter(a) for a in ads]
        a_pre, a_post = [getter(a) for a in pre], [getter(a) for a in post]
        low, high = bootstrap_ci(a_pre, a_post, seed=options.seed)
        p_all = permutation_test(values, labels, ["all"] * len(ads), seed=options.seed)
        p_strat = permutation_test(values, labels, strata, seed=options.seed)
        print(
            f"  {label:30} {mean(a_pre):5.2f} -> {mean(a_post):5.2f}"
            f"  [{low:+.2f}, {high:+.2f}]  p={p_all:.3f} / {p_strat:.3f}"
        )
        scope_rows.append([label, mean(a_pre), mean(a_post), low, high, p_all, p_strat])
    write(
        out / "scope_summary.csv",
        ["measure", "mean_pre", "mean_post", "ci_low", "ci_high", "p_perm", "p_perm_stratified"],
        scope_rows,
    )

    print("\nMean distinct skill categories by window:")
    for window in sorted({a.window for a in ads}):
        subset = [len(a.categories) for a in ads if a.window == window]
        print(f"  {window}: {mean(subset):.2f} (n={len(subset)})")

    raw = {}
    table = []
    for name in names:
        x_pre = sum(name in a.categories for a in pre)
        x_post = sum(name in a.categories for a in post)
        raw[name] = fisher_exact(x_post, len(post) - x_post, x_pre, len(pre) - x_pre)
        table.append((name, x_pre, x_post))
    adjusted = holm(raw)
    print("\nShare of ads mentioning each category (pre -> post), Fisher p, Holm-adjusted p")
    rows = []
    for name, x_pre, x_post in sorted(table, key=lambda r: raw[r[0]]):
        share_pre, share_post = x_pre / len(pre), x_post / len(post)
        print(
            f"  {name:22} {share_pre:5.0%} -> {share_post:5.0%}"
            f"  ({share_post - share_pre:+4.0%})  p={raw[name]:.3f}  adj={adjusted[name]:.3f}"
        )
        rows.append([name, x_pre, len(pre), x_post, len(post), raw[name], adjusted[name]])
    write(
        out / "skill_summary.csv",
        ["category", "pre_count", "pre_n", "post_count", "post_n", "p_fisher", "p_holm"],
        rows,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
