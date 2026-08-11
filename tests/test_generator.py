from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.render import render_html, render_html_body, render_text, to_dict


def test_generate_produces_rooms_up_to_target():
    gen = DungeonGenerator(seed=1)
    dungeon = gen.generate()
    assert dungeon.room_count >= 1
    assert dungeon.room_count <= dungeon.target_rooms + 1  # +1: the room that meets the target may still resolve
    assert dungeon.root.children


def test_generate_is_reproducible_with_same_seed():
    d1 = DungeonGenerator(seed=555).generate()
    d2 = DungeonGenerator(seed=555).generate()
    assert to_dict(d1) == to_dict(d2)


def test_generate_varies_across_seeds():
    d1 = DungeonGenerator(seed=1).generate()
    d2 = DungeonGenerator(seed=2).generate()
    assert to_dict(d1) != to_dict(d2)


def test_render_text_contains_header_and_rooms():
    dungeon = DungeonGenerator(seed=3).generate()
    text = render_text(dungeon)
    assert "DUNGEON SIMULATOR" in text
    assert "ROOM" in text or "EDGE OF DUNGEON" in text


def test_many_seeds_do_not_crash_and_respect_node_cap():
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=15).generate()
        assert dungeon.node_count <= 4000
        assert dungeon.room_count <= dungeon.target_rooms + 1


def test_render_html_is_a_full_document_containing_the_tree():
    dungeon = DungeonGenerator(seed=5).generate()
    page = render_html(dungeon)
    assert page.startswith("<!doctype html>")
    assert "<html" in page and "</html>" in page
    assert "dg-tree" in page
    assert dungeon.dungeon_type in page


def test_render_html_body_has_no_document_wrapper():
    dungeon = DungeonGenerator(seed=6).generate()
    fragment = render_html_body(dungeon)
    assert "<!doctype" not in fragment.lower()
    assert "<html" not in fragment.lower()
    assert "<body" not in fragment.lower()
    assert "dg-tree" in fragment


def test_render_html_escapes_generated_content():
    dungeon = DungeonGenerator(seed=6).generate()
    dungeon.root.lines.append('<script>alert("x")</script> & "quotes"')
    page = render_html(dungeon)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_limitless_size_is_capped():
    # Seed chosen offline for a d20 size roll of 20 ("Limitless").
    found_limitless = False
    for seed in range(200):
        gen = DungeonGenerator(seed=seed, limitless_room_cap=5)
        dungeon = gen.generate()
        if "Limitless" in dungeon.size_label:
            found_limitless = True
            assert dungeon.target_rooms == 5
    assert found_limitless, "expected at least one 'Limitless' roll across 200 seeds"
