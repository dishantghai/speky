from speky import SPEKY


def make_dirs(base, *names):
    base.mkdir(parents=True, exist_ok=True)
    for name in names:
        (base / name).mkdir()
    return base


def test_next_number_skips_gaps_after_deletion(tmp_path):
    specs = make_dirs(tmp_path / "specs", "001-login", "003-billing")
    # Two dirs exist, but 003 is taken: len()+1 would have reused it
    assert SPEKY._next_item_number(specs) == 4


def test_next_number_per_prefix(tmp_path):
    stories = make_dirs(tmp_path / "stories", "F001-a", "F007-b", "B002-c")
    assert SPEKY._next_item_number(stories, "F") == 8
    assert SPEKY._next_item_number(stories, "B") == 3
    assert SPEKY._next_item_number(stories, "T") == 1


def test_next_number_empty_or_missing_dir(tmp_path):
    assert SPEKY._next_item_number(tmp_path / "missing") == 1


def test_find_exact_id_not_substring(tmp_path):
    specs = make_dirs(tmp_path / "specs", "010-search", "100-export", "001-login")
    assert SPEKY._find_item_dir(specs, "001").name == "001-login"
    assert SPEKY._find_item_dir(specs, "1").name == "001-login"
    assert SPEKY._find_item_dir(specs, "10").name == "010-search"
    assert SPEKY._find_item_dir(specs, "01").name == "001-login"


def test_find_story_ids_case_insensitive(tmp_path):
    stories = make_dirs(tmp_path / "stories", "F001-cart", "F010-checkout")
    assert SPEKY._find_item_dir(stories, "f1").name == "F001-cart"
    assert SPEKY._find_item_dir(stories, "F010").name == "F010-checkout"
    assert SPEKY._find_item_dir(stories, "F002") is None


def test_find_by_unique_name_only(tmp_path):
    specs = make_dirs(tmp_path / "specs", "001-user-login", "002-login-audit", "003-billing")
    assert SPEKY._find_item_dir(specs, "billing").name == "003-billing"
    assert SPEKY._find_item_dir(specs, "login") is None  # ambiguous
    assert SPEKY._find_item_dir(specs, "user login").name == "001-user-login"
