

def test_seed_media_files_exist_on_disk() -> None:
    """Regression: the page builder must not prune runtime-referenced assets.

    Seed product and bundle media is fetched by the interaction layer from JSON,
    so it appears in no frozen page. An earlier builder pruned assets on page
    references alone and silently deleted 2,049 of 2,192 media files, breaking
    every non-frozen product gallery while the frozen pages still looked fine.
    """

    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    seed = json.loads((root / "backend" / "seed_data.json").read_text())
    present = {p.name for p in (root / "static" / "assets").iterdir() if p.is_file()}

    refs: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            local = node.get("local")
            if isinstance(local, str) and local.startswith("/static/assets/"):
                refs.append(local)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(seed)
    assert refs, "the seed must carry localized media references"
    missing = sorted({r for r in refs if r.rsplit("/", 1)[-1] not in present})
    assert not missing, f"{len(missing)} seed media files are absent, e.g. {missing[:3]}"
